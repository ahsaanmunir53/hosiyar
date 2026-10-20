"""Indicators (domains, URLs, phone and account fingerprints) and how they are counted.

Poisoning: anyone can paste a message containing someone else's phone number or website, and a
web browser id costs nothing to fake. So:
* a number or account counts as "reported" only after a reviewer approved a report containing
  it, or after several different Telegram accounts (each tied to a phone number) reported it;
* a website counts only after a reviewer approved the report, or when a deterministic link check
  itself confirmed the site (look-alike domain, Safe Browsing, look-alike letters).
Only those trusted indicators appear in public lists, lookups, the weekly warning and STIX.
"""

import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Indicator, Report, WatchlistEntry
from app.rules.brands import URL_SHORTENERS

_LONG_NUMBER = re.compile(r"\d{10,}")


def clean_url(url: str) -> str | None:
    """A URL as stored and exported: no query string or fragment (they can carry personal data),
    and nothing at all if the path holds a phone-length number (wa.me/923001234567)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if _LONG_NUMBER.search(parts.path):
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:500]


def _confirmed(report: dict) -> bool:
    return bool(report.get("lookalike_brand") or report.get("safe_browsing_threats") or report.get("homograph_of"))


def indicators_from_state(state: dict) -> list[tuple[str, str, bool]]:
    """(kind, value, verified) for a shared report."""
    out: list[tuple[str, str, bool]] = []
    for r in state.get("link_reports", []):
        if r.get("official_brand"):
            continue
        verified = _confirmed(r)
        for url in (r["url"], r.get("expanded_url")):
            cleaned = clean_url(url) if url else None
            if cleaned:
                out.append(("url", cleaned, verified))
        domain = r.get("final_registered_domain") or r.get("registered_domain")
        if domain and domain not in URL_SHORTENERS:
            out.append(("domain", domain.lower(), verified))
    out += [("phone_fp", fp, False) for fp in state.get("phone_fingerprints", [])]
    out += [("account_fp", fp, False) for fp in state.get("account_fingerprints", [])]
    seen: set[tuple[str, str]] = set()
    unique = []
    for kind, value, verified in out:
        if (kind, value) not in seen:
            seen.add((kind, value))
            unique.append((kind, value, verified))
    return unique


def trusted_site():
    """SQL condition: a domain or URL indicator that may be shown publicly."""
    return or_(Report.reviewed_by.is_not(None), Indicator.verified.is_(True))


async def reported_count(session: AsyncSession, kind: str, values: list[str], min_reporters: int) -> int:
    """How many approved scam reports contain one of these fingerprints and can be trusted."""
    if not values:
        return 0
    telegram_reporter = case((Report.channel == "telegram", Report.reporter_hash))
    rows = (
        await session.execute(
            select(
                Indicator.value,
                func.count(func.distinct(Report.id)),
                func.count(func.distinct(telegram_reporter)),
                func.count(Report.reviewed_by),
            )
            .join(Report, Report.id == Indicator.report_id)
            .where(Indicator.kind == kind, Indicator.value.in_(values), Report.status == "approved",
                   Report.verdict != "no_red_flags")
            .group_by(Indicator.value)
        )
    ).all()
    total = 0
    for _value, reports, reporters, reviewed in rows:
        if reviewed or reporters >= min_reporters:
            total = max(total, reports)
    return total


def mask_phone(raw: str) -> str:
    """0300-***-4567 style label. Pakistani mobiles are shown with their leading 0."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10 and digits.startswith("3"):
        digits = "0" + digits
    if len(digits) < 7:
        return "***"
    return f"{digits[:4]}-***-{digits[-4:]}"


async def watchlist_hits(session: AsyncSession, domains: list[str], phone_fps: list[str], account_fps: list[str]) -> list[dict]:
    wanted = [("domain", d.lower()) for d in domains] + [("phone_fp", f) for f in phone_fps] + [("account_fp", f) for f in account_fps]
    if not wanted:
        return []
    values = [v for _, v in wanted]
    rows = (await session.execute(select(WatchlistEntry).where(WatchlistEntry.value.in_(values)))).scalars().all()
    kinds = {"domain": "domain", "phone_fp": "phone", "account_fp": "account"}
    found = []
    for row in rows:
        if (row.kind, row.value) in wanted:
            found.append({"kind": kinds.get(row.kind, row.kind), "label": row.label, "note": row.note})
    return found
