"""Look up a phone number, website or bank account before you trust it.

The value is fingerprinted (numbers) or checked (links) and then forgotten; it is never stored.
"""

import re

from sqlalchemy import func, select

from app.core.redaction import (
    _IBAN,
    _PK_MOBILE,
    account_fingerprint,
    normalize_phone,
    phone_fingerprint,
    sender_kind,
)
from app.core.urls import extract_urls, split_url
from app.db.models import Indicator, Report, WatchlistEntry
from app.intel.indicators import mask_phone, reported_count, trusted_site
from app.tools.links import check_links

# Short codes whose owners say official messages come only from them.
KNOWN_SHORTCODES = {
    "8171": {"en": "BISP says its official SMS come only from 8171.",
             "ur": "بی آئی ایس پی کے مطابق اس کے سرکاری ایس ایم ایس صرف 8171 سے آتے ہیں۔",
             "roman": "BISP ke mutabiq us ke sarkari SMS sirf 8171 se aate hain."},
}


def _t(en: str, ur: str, roman: str) -> dict:
    return {"en": en, "ur": ur, "roman": roman}


def guess_kind(value: str) -> str | None:
    v = value.strip()
    if "@" in v:
        return None  # email addresses are not looked up (they would be checked as their mail provider)
    if _IBAN.search(v.replace(" ", "")):
        return "account"
    if extract_urls(v) and not re.fullmatch(r"[\d\s+()-]+", v):
        return "link"
    digits = re.sub(r"\D", "", v)
    if _PK_MOBILE.search(v) or (v.startswith("+") and 10 <= len(digits) <= 15) or re.fullmatch(r"\d{3,6}", digits or "x"):
        return "phone"
    if 8 <= len(digits) <= 24:
        return "account"
    return None


async def _watch(session, kind: str, value: str) -> dict | None:
    row = (await session.execute(select(WatchlistEntry).where(WatchlistEntry.kind == kind, WatchlistEntry.value == value))).scalar_one_or_none()
    return {"label": row.label, "note": row.note} if row else None


def _message(confirmed: int, watch: dict | None, what: dict) -> tuple[str, dict]:
    # Unreviewed reports are deliberately not mentioned: one person could otherwise cast doubt on
    # an innocent number or website just by reporting it.
    if watch:
        return "known_scam", _t(
            f"Reviewers have confirmed this {what['en']} as part of a scam. Do not pay, reply or open it.",
            f"جائزہ کاروں نے تصدیق کی ہے کہ یہ {what['ur']} فراڈ کا حصہ ہے۔ نہ ادائیگی کریں، نہ جواب دیں، نہ کھولیں۔",
            f"Reviewers ne tasdeeq ki hai ke yeh {what['roman']} fraud ka hissa hai. Na payment karein, na jawab dein, na kholein.")
    if confirmed:
        return "reported", _t(
            f"This {what['en']} appears in {confirmed} confirmed scam report(s).",
            f"یہ {what['ur']} {confirmed} تصدیق شدہ فراڈ رپورٹس میں موجود ہے۔",
            f"Yeh {what['roman']} {confirmed} tasdeeq shuda fraud reports mein mojood hai.")
    return "no_reports", _t(
        f"No confirmed reports about this {what['en']}. That is not a guarantee: new scam numbers and sites appear every day.",
        f"اس {what['ur']} کے بارے میں کوئی تصدیق شدہ رپورٹ نہیں۔ یہ ضمانت نہیں: نئے فراڈ نمبر اور ویب سائٹس روز بنتے ہیں۔",
        f"Is {what['roman']} ke baare mein koi tasdeeq shuda report nahi. Yeh guarantee nahi: naye fraud number aur websites roz bante hain.")


WHAT = {
    "phone": _t("number", "نمبر", "number"),
    "account": _t("account", "اکاؤنٹ", "account"),
    "link": _t("website", "ویب سائٹ", "website"),
}


async def lookup(deps, value: str, kind: str = "auto") -> dict:
    s = deps.settings
    kind = guess_kind(value) if kind == "auto" else kind
    if kind is None:
        raise ValueError("Enter a phone number, a website or a bank account number.")
    out: dict = {"kind": kind}
    async with deps.sessionmaker() as session:
        if kind == "phone":
            digits = re.sub(r"\D", "", value)
            out["display"] = mask_phone(normalize_phone(value)) if len(digits) >= 7 else digits
            out["sender_kind"] = sender_kind(value)
            if out["sender_kind"] == "shortcode":
                out["shortcode_note"] = KNOWN_SHORTCODES.get(digits)
            fp = phone_fingerprint(value, s.fingerprint_secret)
            confirmed = await reported_count(session, "phone_fp", [fp], s.min_independent_reporters)
            watch = await _watch(session, "phone_fp", fp)
        elif kind == "account":
            out["display"] = re.sub(r"\w(?=\w{4})", "•", re.sub(r"\s", "", value))[-12:]
            fp = account_fingerprint(value, s.fingerprint_secret)
            confirmed = await reported_count(session, "account_fp", [fp], s.min_independent_reporters)
            watch = await _watch(session, "account_fp", fp)
        elif kind == "link":
            urls = extract_urls(value) or [value]
            report = (await check_links(urls[:1], s, deps.http))[0]
            domain = report.get("final_registered_domain") or report.get("registered_domain") or split_url(urls[0])["host"]
            out["display"] = domain
            out["link_report"] = report
            confirmed = (await session.execute(
                select(func.count(func.distinct(Report.id))).join(Indicator, Indicator.report_id == Report.id)
                .where(Indicator.kind == "domain", Indicator.value == domain, Report.status == "approved",
                       trusted_site()))).scalar_one()
            watch = await _watch(session, "domain", domain)
        else:
            raise ValueError("Unknown lookup type.")
    status, message = _message(confirmed, watch, WHAT[kind])
    if kind == "link" and status == "no_reports":
        rep = out["link_report"]
        if rep.get("official_brand"):
            status, message = "official", _t(
                f"This is the official website of {rep['official_brand']['name']}.",
                f"یہ {rep['official_brand']['name']} کی اصل ویب سائٹ ہے۔",
                f"Yeh {rep['official_brand']['name']} ki asli website hai.")
        elif rep.get("lookalike_brand") or rep.get("safe_browsing_threats"):
            name = (rep.get("lookalike_brand") or {}).get("name", "a known organisation")
            status, message = "lookalike", _t(
                f"This website imitates {name}. Do not enter any details on it.",
                f"یہ ویب سائٹ {name} کی نقل ہے۔ اس پر کوئی تفصیل نہ ڈالیں۔",
                f"Yeh website {name} ki naqal hai. Is par koi detail na dalein.")
    out.update({"status": status, "message": message, "confirmed_reports": confirmed,
                "watchlist": watch})
    return out
