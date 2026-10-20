"""Help someone report a scam website: who registered it, where to send an abuse report,
and a ready-to-send email. The site itself is never visited."""

from urllib.parse import quote

from app.config import Settings
from app.core.urls import split_url
from app.rules.catalog import official_brand_dict
from app.tools.links import rdap_info

GOOGLE_REPORT_URL = "https://www.google.com/safebrowsing/report_phish/"


def abuse_email_draft(url: str, domain: str, registrar: str | None) -> dict:
    subject = f"Phishing / scam website: {domain}"
    body = (
        f"Hello{' ' + registrar if registrar else ''} abuse team,\n\n"
        f"The domain {domain} is being used in a scam that targets people in Pakistan through SMS and WhatsApp.\n\n"
        f"URL: {url.replace('.', '[.]')}\n"
        "It impersonates a bank, wallet or government service to collect payments or login details.\n\n"
        "Please investigate and suspend the domain under your abuse policy.\n\n"
        "Thank you."
    )
    return {"subject": subject, "body": body}


async def takedown_info(settings: Settings, http, url: str) -> dict:
    p = split_url(url)
    domain = p["registered_domain"] or p["host"]
    official = official_brand_dict(p["registered_domain"], p["host"])
    info = {"url": p["url"], "domain": domain, "official": official, "registrar": None, "abuse_email": None,
            "registered": None, "rdap_url": None, "google_report_url": GOOGLE_REPORT_URL, "errors": []}
    if official:
        return info
    if http is not None and settings.enable_network_checks and domain and not p["is_ip"]:
        try:
            rd = await rdap_info(http, domain)
            info.update({k: rd.get(k) for k in ("registrar", "abuse_email", "registered", "rdap_url")})
        except Exception as exc:
            info["errors"].append(f"rdap: {type(exc).__name__}")
    draft = abuse_email_draft(p["url"], domain, info["registrar"])
    info["email"] = draft
    if info["abuse_email"]:
        info["mailto"] = f"mailto:{info['abuse_email']}?subject={quote(draft['subject'])}&body={quote(draft['body'])}"
    return info
