"""Delete old data on a schedule, and delete one person's data on request."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update

from app.db.models import AICache, AlertLog, Analysis, FamilyLink, ReceiptSeen, Report
from app.intel import family
from app.intel.reports import delete_reports
from app.memory import store as memory


async def _delete_threads(deps, thread_ids: list[str]) -> int:
    """Remove the stored conversation state (redacted message, follow-ups) of finished checks."""
    if deps.checkpointer is None:
        return 0
    n = 0
    for tid in thread_ids:
        try:
            await deps.checkpointer.adelete_thread(tid)
            n += 1
        except Exception:
            continue
    return n


async def purge(deps) -> dict:
    s = deps.settings
    now = datetime.now(UTC)
    counts: dict[str, int] = {}
    cutoff = now - timedelta(days=s.retention_analyses_days)
    async with deps.sessionmaker() as session:
        old_ids = [r for (r,) in (await session.execute(
            select(Analysis.id).where(Analysis.created_at < cutoff, Analysis.is_seed.is_(False)))).all()]
        # Telegram keeps one thread per chat (its latest check); drop it once the chat has gone quiet.
        tg = select(Analysis.user_hash).where(Analysis.channel == "telegram", Analysis.user_hash.is_not(None))
        quiet = {h for (h,) in (await session.execute(tg.where(Analysis.created_at < cutoff))).all()}
        active = {h for (h,) in (await session.execute(tg.where(Analysis.created_at >= cutoff))).all()}
        counts["threads"] = await _delete_threads(deps, old_ids + [f"tg-{h}" for h in quiet - active])
        res = await session.execute(delete(Analysis).where(Analysis.created_at < cutoff))
        counts["analyses"] = res.rowcount or 0
        old_rejected = [r for (r,) in (await session.execute(select(Report.id).where(
            Report.status == "rejected", Report.created_at < now - timedelta(days=s.retention_rejected_days)))).all()]
        old_pending = [r for (r,) in (await session.execute(select(Report.id).where(
            Report.status == "pending", Report.created_at < now - timedelta(days=s.retention_pending_days)))).all()]
        counts["rejected_reports"] = await delete_reports(deps, session, old_rejected)
        counts["pending_reports"] = await delete_reports(deps, session, old_pending)
        res = await session.execute(delete(AICache).where(AICache.created_at < now - timedelta(days=s.ai_cache_days)))
        counts["ai_cache"] = res.rowcount or 0
        res = await session.execute(delete(FamilyLink).where(
            FamilyLink.guardian_chat_id.is_(None), FamilyLink.created_at < now - timedelta(hours=family.CODE_HOURS)))
        counts["family_codes"] = res.rowcount or 0
        res = await session.execute(delete(AlertLog).where(AlertLog.created_at < now - timedelta(days=s.retention_alerts_days)))
        counts["alerts"] = res.rowcount or 0
        res = await session.execute(delete(ReceiptSeen).where(
            ReceiptSeen.last_seen < now - timedelta(days=s.retention_receipts_days)))
        counts["receipts"] = res.rowcount or 0
        await session.commit()
    return counts


async def forget(deps, user_hash: str) -> dict:
    """Remove what is linked to one browser or Telegram chat. Approved reports stay, but are
    no longer linked to the person (they were already redacted)."""
    async with deps.sessionmaker() as session:
        ids = [r for (r,) in (await session.execute(select(Analysis.id).where(Analysis.user_hash == user_hash))).all()]
        await _delete_threads(deps, [*ids, f"tg-{user_hash}"])
        res = await session.execute(delete(Analysis).where(Analysis.user_hash == user_hash))
        analyses = res.rowcount or 0
        res = await session.execute(update(Report).where(Report.reporter_hash == user_hash).values(reporter_hash=None))
        reports = res.rowcount or 0
        await session.commit()
    links = await family.remove_member(deps.sessionmaker, user_hash)
    await memory.forget_user(deps.store, user_hash)
    return {"analyses": analyses, "reports_unlinked": reports, "family_links": links, "preferences": 1}
