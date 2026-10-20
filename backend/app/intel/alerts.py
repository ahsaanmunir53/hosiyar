"""The weekly warning: what scams were most common in the last seven days."""

import html
import logging
from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.db.models import AlertLog, Analysis, Campaign, Indicator, Report
from app.intel.indicators import trusted_site
from app.rules.engine import CATEGORY_LABELS

log = logging.getLogger(__name__)


async def weekly_summary(sessionmaker, days: int = 7) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    async with sessionmaker() as session:
        rows = (await session.execute(
            select(Analysis.verdict, Analysis.category, Analysis.brands)
            .where(Analysis.created_at >= since, Analysis.is_seed.is_(False)))).all()
        campaigns = (await session.execute(
            select(Campaign).where(Campaign.last_seen >= since, Campaign.report_count >= 2)
            .order_by(Campaign.report_count.desc()).limit(3))).scalars().all()
        domains = Counter(v for (v,) in (await session.execute(
            select(Indicator.value).join(Report, Report.id == Indicator.report_id)
            .where(Indicator.kind == "domain", Report.status == "approved", Report.created_at >= since,
                   trusted_site()))).all())
    flagged = [r for r in rows if r.verdict != "no_red_flags"]
    categories = Counter(r.category for r in flagged)
    brands = Counter(b for r in flagged for b in (r.brands or []))
    return {
        "from": since.date().isoformat(),
        "to": datetime.now(UTC).date().isoformat(),
        "checks": len(rows),
        "flagged": len(flagged),
        "top_categories": [{"category": c, "count": n} for c, n in categories.most_common(3)],
        "top_brands": [{"brand": b, "count": n} for b, n in brands.most_common(3)],
        "campaigns": [{"label": c.label, "reports": c.report_count} for c in campaigns],
        "domains": [d for d, _ in domains.most_common(5)],
    }


def format_weekly(summary: dict, app_url: str = "") -> str:
    e = html.escape
    lines = [f"<b>Hoshiyar weekly warning</b> · {summary['from']} to {summary['to']}", ""]
    if not summary["top_categories"]:
        lines.append("Few scam checks this week. Stay alert: never share an OTP, PIN or password.")
    else:
        lines.append("Most common scams this week / Is hafte sab se aam fraud:")
        for c in summary["top_categories"]:
            label = CATEGORY_LABELS.get(c["category"], CATEGORY_LABELS["other"])
            lines.append(f"• {e(label['en'])} / {e(label['roman'])} / {e(label['ur'])} ({c['count']})")
    if summary["top_brands"]:
        lines += ["", "Names most often faked: " + ", ".join(e(b["brand"].upper()) for b in summary["top_brands"])]
    if summary["domains"]:
        lines += ["", "Do not open: " + ", ".join(e(d.replace(".", "[.]")) for d in summary["domains"])]
    lines += ["", "Banks, wallets and government offices never ask for your OTP, PIN or a fee by SMS.",
              "Bank, wallet aur sarkari idaray kabhi SMS par OTP, PIN ya fee nahi mangte."]
    if app_url:
        lines += ["", f"Check a message: {app_url}"]
    return "\n".join(lines)


async def send_weekly(deps, chat_id: str | None) -> dict:
    s = deps.settings
    summary = await weekly_summary(deps.sessionmaker)
    text = format_weekly(summary, s.public_app_url)
    delivered = False
    if chat_id and s.telegram_bot_token and deps.http:
        try:
            resp = await deps.http.post(f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                                        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                              "disable_web_page_preview": True})
            delivered = resp.status_code == 200
            if not delivered:
                log.warning("weekly alert not delivered: HTTP %s", resp.status_code)
        except httpx.HTTPError as exc:
            log.warning("weekly alert failed: %s", type(exc).__name__)
    async with deps.sessionmaker() as session:
        session.add(AlertLog(kind="weekly", summary=summary, delivered=delivered))
        await session.commit()
    return {"summary": summary, "text": text, "delivered": delivered}


async def latest_weekly(sessionmaker) -> dict | None:
    async with sessionmaker() as session:
        row = (await session.execute(
            select(AlertLog).where(AlertLog.kind == "weekly").order_by(AlertLog.created_at.desc()).limit(1))).scalar_one_or_none()
    if not row:
        return None
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
    return {"created_at": created.isoformat(), **row.summary}
