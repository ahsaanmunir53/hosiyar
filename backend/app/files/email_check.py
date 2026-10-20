"""Read an email (.eml file or the "show original" source pasted in) and check its sender.

Checks, all deterministic:
* the receiving server's SPF / DKIM / DMARC results (Authentication-Results header)
* a bank, wallet or government name in the sender name or subject, sent from another domain
* an organisation's name on a free webmail address (gmail.com, yahoo.com...)
* replies going to a different domain than the sender
* attachments that can run code or open a fake page
* links hidden behind different link text in the HTML body
"""

import email
import re
from email import policy
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser

from app.core.text import normalize
from app.core.urls import split_url
from app.files import FileReading, FileUnreadable, risky_names
from app.rules.brands import find_claimed_brands, official_brand_for

FREEMAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "outlook.com", "hotmail.com",
    "live.com", "msn.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "gmx.com",
    "mail.com", "yandex.com", "zoho.com",
}
_AUTH = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.I)
_HEADER_LINE = re.compile(r"^(from|to|subject|date|received|return-path|message-id|authentication-results)\s*:", re.I | re.M)
# Words that claim to be an organisation even when no known brand is named.
_ORG_WORDS = re.compile(r"\b(bank|support|security|verification|billing|government|ministry|customs|courier|hr department|recruitment)\b", re.I)


class _Html(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.links: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.lower().startswith(("http://", "https://")):
                self.links.append(href[:500])
        if tag in ("br", "p", "div", "tr", "li"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)


def html_to_text(html: str) -> tuple[str, list[str]]:
    parser = _Html()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = re.sub(r"[ \t]+", " ", "".join(parser.text))
    return re.sub(r"\n\s*\n+", "\n", text).strip(), parser.links


def looks_like_email_source(raw: str) -> bool:
    head = "\n".join(raw.splitlines()[:60])
    return bool(re.search(r"^from\s*:", head, re.I | re.M)) and len(_HEADER_LINE.findall(head)) >= 2


def _registered(domain: str) -> str:
    return split_url(domain)["registered_domain"] or domain


def read_email(raw: bytes | str) -> FileReading:
    if isinstance(raw, bytes):
        msg = email.message_from_bytes(raw, policy=policy.default)
    else:
        if not looks_like_email_source(raw):
            raise FileUnreadable(
                "This does not look like an email's full source. In Gmail open the email, choose "
                "\"Show original\" and copy everything; in Outlook choose \"View message source\".")
        msg = email.message_from_string(raw, policy=policy.default)

    display, address = parseaddr(str(msg.get("From", "")))
    from_domain = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
    reply_pairs = getaddresses([str(v) for v in msg.get_all("Reply-To", [])])
    reply_domain = next((a.rsplit("@", 1)[-1].lower() for _, a in reply_pairs if "@" in a), "")
    subject = str(msg.get("Subject", ""))[:300]

    auth: dict[str, str] = {}
    for header in msg.get_all("Authentication-Results", []) or []:
        for check, result in _AUTH.findall(str(header)):
            auth.setdefault(check.lower(), result.lower())

    body_text, links = "", []
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            content = part.get_content()
            if part.get_content_type() == "text/html":
                body_text, links = html_to_text(content)
            else:
                body_text = content
        html_part = msg.get_body(preferencelist=("html",))
        if html_part is not None and html_part is not part:
            _, links = html_to_text(html_part.get_content())
    except (KeyError, LookupError, ValueError):
        body_text = ""
    if not body_text and not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        body_text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(payload or "")

    attachments = []
    for part in msg.iter_attachments() if msg.is_multipart() else []:
        name = part.get_filename()
        if name:
            attachments.append(name)

    signals: list[tuple[str, str]] = []
    failed = [f"{k}={v}" for k, v in sorted(auth.items()) if v in ("fail", "softfail") or (k == "dmarc" and v == "fail")]
    if failed and (auth.get("dmarc") == "fail" or len(failed) >= 2 or auth.get("spf") == "fail"):
        signals.append(("email_auth_failed", ", ".join(failed)))

    # Only the sender name counts as a claim: newsletters mention brands in subjects all the time.
    claimed = find_claimed_brands(normalize(display))
    registered_from = _registered(from_domain) if from_domain else ""
    if from_domain and claimed:
        b = claimed[0]
        if not official_brand_for(registered_from, from_domain):
            signals.append(("email_brand_mismatch", f"{b.key}|{from_domain}"))
    if registered_from in FREEMAIL and (claimed or _ORG_WORDS.search(display)):
        signals.append(("email_freemail_brand", from_domain))
    if reply_domain and from_domain and _registered(reply_domain) != registered_from:
        signals.append(("email_reply_to_mismatch", reply_domain))
    for name in risky_names(attachments):
        signals.append(("risky_attachment", name))

    unique_links = list(dict.fromkeys(links))[:20]
    text = f"Subject: {subject}\n{body_text.strip()}"
    if unique_links:
        text += "\n\nLinks in the email: " + " ".join(unique_links)
    if not body_text.strip() and not subject:
        raise FileUnreadable("No readable text was found in this email.")

    info = {
        "kind": "email",
        "from_name": display[:120],
        "from_domain": from_domain,
        "reply_to_domain": reply_domain or None,
        "subject": subject,
        "auth": auth,
        "attachments": attachments[:20],
        "links": unique_links,
    }
    return FileReading(text=text, signals=signals, info=info)
