"""The review queue and campaign grouping.

A shared message becomes a report. It is approved straight away only when the rule book
found a decisive, pattern-backed sign (a request for an OTP, a look-alike bank site...).
Everything else waits for an analyst. Only approved reports enter the community memory.
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Analysis, Campaign, Indicator, Report
from app.intel.indicators import indicators_from_state, trusted_site
from app.memory import store as memory
from app.rules.engine import CATEGORY_LABELS

log = logging.getLogger(__name__)

# Hard rules that may approve a report on their own: deterministic, and not about the checker itself.
_AUTO_SOURCES = {"pattern", "link-check", "sender", "file-check"}
_NOT_ENOUGH = {"manipulation_attempt", "watchlist_match"}


def auto_approvable(verdict: str, rule_hits: list[dict]) -> bool:
    if verdict != "likely_scam":
        return False
    return any(
        h["hard"] and h["id"] not in _NOT_ENOUGH and set(h.get("sources", [])) & _AUTO_SOURCES
        for h in rule_hits
    )


async def submit_report(deps, state: dict) -> Report:
    """Store a shared message. Returns the report (approved or pending)."""
    sig_brands = state.get("signals", {}).get("brands", [])
    report = Report(
        id=state["analysis_id"],
        status="pending",
        reporter_hash=state.get("user_hash"),
        channel=state.get("channel", "web"),
        source_kind=state.get("source_kind", "text"),
        verdict=state["verdict"],
        score=state["score"],
        category=state["category"],
        language=state["language"],
        redacted_text=state["redacted_text"][:4000],
        rule_ids=[h["id"] for h in state["rule_hits"]],
        hard_rule_ids=[h["id"] for h in state["rule_hits"] if h["hard"]],
        brands=list(sig_brands),
    )
    async with deps.sessionmaker() as session:
        session.add(report)
        await session.flush()  # the report row must exist before its indicators (foreign key)
        for kind, value, verified in indicators_from_state(state):
            session.add(Indicator(report_id=report.id, kind=kind, value=value, verified=verified))
        await session.commit()
    if auto_approvable(state["verdict"], state["rule_hits"]):
        await approve_report(deps, report.id, reviewer=None)
        report.status = "approved"
        report.auto_approved = True
    return report


async def approve_report(deps, report_id: str, reviewer: str | None, note: str | None = None) -> Report | None:
    async with deps.sessionmaker() as session:
        report = await session.get(Report, report_id)
        if not report:
            return None
        report.status = "approved"
        report.auto_approved = reviewer is None
        if reviewer:
            report.reviewed_by = reviewer
            report.reviewed_at = datetime.now(UTC)
            report.review_note = note
        domains = [
            v for (v,) in (await session.execute(
                select(Indicator.value).where(Indicator.report_id == report_id, Indicator.kind == "domain"))).all()
        ]
        await session.commit()
    # A person's approval also re-saves an auto-approved entry, marking it as reviewed.
    if not report.in_memory or reviewer:
        try:
            await memory.save_report(
                deps.store, deps.embed_provider, key=report.id, redacted_text=report.redacted_text,
                verdict="likely_scam" if reviewer else report.verdict, category=report.category,
                language=report.language, domains=domains, reviewed=bool(reviewer),
            )
            async with deps.sessionmaker() as session:
                row = await session.get(Report, report_id)
                row.in_memory = True
                await session.commit()
            report.in_memory = True
        except Exception as exc:
            log.warning("could not add report %s to memory: %s", report_id, exc)
    await assign_campaign(deps, report_id)
    return report


async def reject_report(deps, report_id: str, reviewer: str, note: str | None = None) -> Report | None:
    async with deps.sessionmaker() as session:
        report = await session.get(Report, report_id)
        if not report:
            return None
        old_campaign = report.campaign_id
        report.status = "rejected"
        report.reviewed_by = reviewer
        report.reviewed_at = datetime.now(UTC)
        report.review_note = note
        report.campaign_id = None
        was_in_memory = report.in_memory
        report.in_memory = False
        # Take the text off the public dashboard too.
        await session.execute(update(Analysis).where(Analysis.id == report_id).values(excerpt=None, shared=False))
        await session.commit()
    if was_in_memory:
        await memory.delete_report(deps.store, deps.embed_provider, report_id)
    if old_campaign:
        await refresh_campaign(deps, old_campaign)
    return report


async def delete_reports(deps, session: AsyncSession, ids: list[str]) -> int:
    """Remove reports, their indicators and their memory entries (used by the retention purge)."""
    if not ids:
        return 0
    for rid in ids:
        await memory.delete_report(deps.store, deps.embed_provider, rid)
    await session.execute(delete(Indicator).where(Indicator.report_id.in_(ids)))
    result = await session.execute(delete(Report).where(Report.id.in_(ids)))
    return result.rowcount or 0


# --- Campaigns -----------------------------------------------------------------

async def assign_campaign(deps, report_id: str) -> str | None:
    """Join a campaign that shares an indicator, else one with a very similar message in the
    same category, else start a new one."""
    async with deps.sessionmaker() as session:
        report = await session.get(Report, report_id)
        if not report or report.status != "approved":
            return None
        if report.campaign_id:
            return report.campaign_id
        mine = (await session.execute(
            select(Indicator.kind, Indicator.value).where(Indicator.report_id == report_id))).all()
        shared_values = [v for k, v in mine if k in ("domain", "url", "phone_fp", "account_fp")]
        campaign_id = None
        if shared_values:
            row = (await session.execute(
                select(Report.campaign_id)
                .join(Indicator, Indicator.report_id == Report.id)
                .where(Indicator.value.in_(shared_values), Report.id != report_id,
                       Report.status == "approved", Report.campaign_id.is_not(None))
                .order_by(Report.created_at.desc())
                .limit(1)
            )).first()
            campaign_id = row[0] if row else None
        text, category = report.redacted_text, report.category

    if not campaign_id:
        try:
            matches = await memory.search_similar(
                deps.store, deps.embed_provider, text, deps.settings.similarity_threshold, limit=5, exclude_key=report_id)
        except Exception:
            matches = []
        keys = [m["key"] for m in matches if m["source"] == "community"]
        if keys:
            async with deps.sessionmaker() as session:
                row = (await session.execute(
                    select(Report.campaign_id).where(Report.id.in_(keys), Report.category == category,
                                                     Report.campaign_id.is_not(None)).limit(1))).first()
                campaign_id = row[0] if row else None

    async with deps.sessionmaker() as session:
        report = await session.get(Report, report_id)
        if not campaign_id:
            campaign_id = str(uuid.uuid4())
            session.add(Campaign(id=campaign_id, category=report.category, label="", report_count=0,
                                 first_seen=report.created_at, last_seen=report.created_at))
            await session.flush()
        report.campaign_id = campaign_id
        await session.commit()
    await refresh_campaign(deps, campaign_id)
    return campaign_id


async def refresh_campaign(deps, campaign_id: str) -> None:
    async with deps.sessionmaker() as session:
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            return
        reports = (await session.execute(
            select(Report).where(Report.campaign_id == campaign_id, Report.status == "approved"))).scalars().all()
        if not reports:
            await session.delete(campaign)
            await session.commit()
            return
        ids = [r.id for r in reports]
        domains = Counter(v for (v,) in (await session.execute(
            select(Indicator.value).join(Report, Report.id == Indicator.report_id)
            .where(Indicator.report_id.in_(ids), Indicator.kind == "domain", trusted_site()))).all())
        brands = Counter(b for r in reports for b in (r.brands or []))
        categories = Counter(r.category for r in reports)
        category = categories.most_common(1)[0][0]
        parts = [CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])["en"]]
        if brands:
            parts.append(brands.most_common(1)[0][0].upper())
        if domains:
            parts.append(domains.most_common(1)[0][0])
        campaign.label = " · ".join(parts)[:200]
        campaign.category = category
        campaign.report_count = len(reports)
        campaign.brands = [b for b, _ in brands.most_common(4)]
        campaign.first_seen = min(_aware(r.created_at) for r in reports)
        campaign.last_seen = max(_aware(r.created_at) for r in reports)
        await session.commit()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def campaign_list(deps, min_reports: int = 2, limit: int = 30, with_indicators: bool = False) -> list[dict]:
    async with deps.sessionmaker() as session:
        rows = (await session.execute(
            select(Campaign).where(Campaign.report_count >= min_reports)
            .order_by(Campaign.last_seen.desc()).limit(limit))).scalars().all()
        out = []
        for c in rows:
            item = {
                "id": c.id, "label": c.label, "category": c.category, "report_count": c.report_count,
                "brands": c.brands or [], "first_seen": _aware(c.first_seen).isoformat(),
                "last_seen": _aware(c.last_seen).isoformat(),
            }
            # Analysts see every indicator. The public sees only confirmed scam sites, never fingerprints.
            q = (select(Indicator.kind, Indicator.value).join(Report, Report.id == Indicator.report_id)
                 .where(Report.campaign_id == c.id, Report.status == "approved"))
            if not with_indicators:
                q = q.where(Indicator.kind == "domain", trusted_site())
            ind = (await session.execute(q.distinct().limit(40))).all()
            item["indicators"] = [{"kind": k, "value": v} for k, v in ind]
            out.append(item)
    return out
