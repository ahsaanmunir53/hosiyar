"""Remove personal data before any text leaves the server or is stored.

Phone numbers, bank accounts and IBANs are replaced with placeholders, but an HMAC
fingerprint of each one is kept so the system can notice when the same number shows up in
several reports without ever storing the number itself.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass, field

_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+|\b[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s<>\"']*)?")
_CNIC = re.compile(r"\b\d{5}[-\s]?\d{7}[-\s]?\d\b")
_IBAN = re.compile(r"(?i)\bPK\d{2}\s?[A-Z]{4}(?:\s?\d){16}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Pakistani mobile numbers: 03xx-xxxxxxx, 0300 123 4567, +92 3xx xxxxxxx, 0092...
_PK_MOBILE = re.compile(r"(?<!\d)(?:\+92|0092|92|0)[\s-]?3\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)")
# International numbers written with a plus sign.
_INTL_PHONE = re.compile(r"(?<!\w)\+(?!92)\d[\d\s-]{8,14}\d(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
# Bank account numbers written next to a word like "account" or "A/C" (wallet accounts are phone numbers).
_ACCOUNT = re.compile(
    r"(?i)(\b(?:account|acct|acc|a/c|ac no|khata|account no|account number|title)\b\.?\s*(?:no\.?|number|#)?\s*[:#-]?\s*|اکاؤنٹ(?: نمبر)?\s*:?\s*)"
    r"(\d[\d -]{7,22}\d)(?!\d)"
)
_CODE_CONTEXT = re.compile(
    r"(?i)(otp|code|pin|password|passcode|cvv|کوڈ|پن|پاس ورڈ|تصدیقی)\D{0,25}(\d{4,8})(?!\d)"
)


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0092"):
        digits = digits[4:]
    elif digits.startswith("92") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


def normalize_account(raw: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", raw.upper())


def fingerprint(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]


def phone_fingerprint(raw: str, secret: str) -> str:
    return fingerprint(normalize_phone(raw), secret)


def account_fingerprint(raw: str, secret: str) -> str:
    return fingerprint("acct:" + normalize_account(raw), secret)


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)
    phone_fingerprints: list[str] = field(default_factory=list)
    phones_found: int = 0
    account_fingerprints: list[str] = field(default_factory=list)
    # Placeholder -> fingerprint, in the order they appear, e.g. {"[PHONE_1]": "ab12..."}.
    placeholders: dict[str, str] = field(default_factory=dict)


def redact(text: str, secret: str) -> RedactionResult:
    """Replace personal identifiers with placeholders like [PHONE_1].

    Links are set aside first so digits inside them are not mistaken for phone or card numbers,
    but their query strings (where sites put ?phone=, ?cnic= or an email) are redacted too.
    Emails are handled before links, because "name@gmail.com" contains a domain."""
    counts: dict[str, int] = {}
    fps: list[str] = []
    accounts: list[str] = []
    placeholders: dict[str, str] = {}

    def _sub(pattern: re.Pattern, label: str, s: str, check=None, fp=None) -> str:
        def repl(m: re.Match) -> str:
            raw = m.group(0)
            if check and not check(raw):
                return raw
            counts[label] = counts.get(label, 0) + 1
            tag = f"[{label}_{counts[label]}]"
            if fp:
                placeholders[tag] = fp(raw)
            return tag

        return pattern.sub(repl, s)

    def _phone(raw: str) -> str:
        value = phone_fingerprint(raw, secret)
        fps.append(value)
        return value

    def _account(raw: str) -> str:
        value = account_fingerprint(raw, secret)
        accounts.append(value)
        return value

    def _account_repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(2))
        if len(digits) < 8 or len(digits) > 20:
            return m.group(0)
        counts["ACCOUNT"] = counts.get("ACCOUNT", 0) + 1
        tag = f"[ACCOUNT_{counts['ACCOUNT']}]"
        placeholders[tag] = _account(m.group(2))
        return m.group(1) + tag

    def _code_repl(m: re.Match) -> str:
        counts["CODE"] = counts.get("CODE", 0) + 1
        return m.group(0).replace(m.group(2), f"[CODE_{counts['CODE']}]")

    def _numbers(s: str) -> str:
        s = _sub(_IBAN, "IBAN", s, fp=_account)
        s = _sub(_CNIC, "CNIC", s)
        s = _sub(_PK_MOBILE, "PHONE", s, fp=_phone)
        s = _sub(_INTL_PHONE, "PHONE", s, fp=_phone)
        return _sub(_CARD, "CARD", s, check=lambda raw: _luhn_ok(re.sub(r"\D", "", raw)))

    work = _sub(_EMAIL, "EMAIL", text)
    urls: list[str] = []

    def _stash_url(m: re.Match) -> str:
        urls.append(m.group(0))
        return f"\x00URL{len(urls) - 1}\x00"

    work = _URL.sub(_stash_url, work)
    work = _numbers(work)
    work = _ACCOUNT.sub(_account_repl, work)
    work = _CODE_CONTEXT.sub(_code_repl, work)

    for i, url in enumerate(urls):
        base, sep, query = url.partition("?")
        if sep:
            query = _numbers(query)
            query = re.sub(r"(?<==)\d{6,}", lambda m: "[NUMBER]", query)
        work = work.replace(f"\x00URL{i}\x00", base + sep + query)

    return RedactionResult(
        text=work,
        counts=counts,
        phone_fingerprints=sorted(set(fps)),
        phones_found=counts.get("PHONE", 0),
        account_fingerprints=sorted(set(accounts)),
        placeholders=placeholders,
    )


def sender_kind(sender: str | None) -> str:
    """Classify the sender field a user typed: shortcode, mobile, alphanumeric or unknown."""
    if not sender or not sender.strip():
        return "unknown"
    s = sender.strip()
    digits = re.sub(r"\D", "", s)
    if re.fullmatch(r"\d{3,6}", s.replace(" ", "")):
        return "shortcode"
    if _PK_MOBILE.search(s) or (digits and len(digits) >= 10):
        return "mobile"
    if re.search(r"[A-Za-z]", s):
        return "alphanumeric"
    return "unknown"


def normalize_sender(sender: str | None) -> str:
    if not sender:
        return ""
    return re.sub(r"[^0-9a-z]", "", sender.lower())
