"""Family alerts. Someone who often gets scam messages (say, a parent) shares a code with a
relative. When one of their checks comes back "likely scam", the relative gets a Telegram
message with the scam type only, never the message itself."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AlertLog, FamilyLink
from app.rules.engine import CATEGORY_LABELS

log = logging.getLogger(__name__)

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_HOURS = 24


def _code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


async def create_code(sessionmaker: async_sessionmaker, member_hash: str) -> str:
    async with sessionmaker() as session:
        await session.execute(delete(FamilyLink).where(FamilyLink.member_hash == member_hash,
                                                       FamilyLink.guardian_chat_id.is_(None)))
        code = _code()
        session.add(FamilyLink(code=code, member_hash=member_hash))
        await session.commit()
    return code


async def link_guardian(sessionmaker: async_sessionmaker, code: str, guardian_chat_id: str) -> bool:
    code = code.strip().upper()
    async with sessionmaker() as session:
        row = (await session.execute(select(FamilyLink).where(FamilyLink.code == code))).scalar_one_or_none()
        if not row or row.guardian_chat_id:
            return False
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - created > timedelta(hours=CODE_HOURS):
            return False
        row.guardian_chat_id = str(guardian_chat_id)
        row.linked_at = datetime.now(UTC)
        await session.commit()
    return True


async def status(sessionmaker: async_sessionmaker, member_hash: str) -> dict:
    async with sessionmaker() as session:
        rows = (await session.execute(select(FamilyLink).where(FamilyLink.member_hash == member_hash))).scalars().all()
    return {
        "guardians": sum(1 for r in rows if r.guardian_chat_id),
        "pending_code": next((r.code for r in rows if not r.guardian_chat_id), None),
    }


async def remove_member(sessionmaker: async_sessionmaker, member_hash: str) -> int:
    async with sessionmaker() as session:
        result = await session.execute(delete(FamilyLink).where(FamilyLink.member_hash == member_hash))
        await session.commit()
    return result.rowcount or 0


async def remove_guardian(sessionmaker: async_sessionmaker, chat_id: str) -> int:
    async with sessionmaker() as session:
        result = await session.execute(delete(FamilyLink).where(FamilyLink.guardian_chat_id == str(chat_id)))
        await session.commit()
    return result.rowcount or 0


def alert_text(category: str, app_url: str = "") -> str:
    label = CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])
    lines = [
        "🔔 <b>Hoshiyar family alert</b>",
        f"Someone in your family just checked a message that looks like a scam: <b>{label['en']}</b>.",
        "They were told not to reply, open links or send money. A quick call from you can help.",
        "",
        f"Aap ke ghar ke kisi fard ne abhi ek message check kiya jo fraud lagta hai: <b>{label['roman']}</b>. "
        "Unhein ek call kar lein.",
        "",
        "/unguard to stop these alerts.",
    ]
    if app_url:
        lines.insert(4, app_url)
    return "\n".join(lines)


async def alert_guardians(sessionmaker: async_sessionmaker, http: httpx.AsyncClient | None, token: str | None,
                          member_hash: str | None, category: str, app_url: str = "") -> int:
    if not (http and token and member_hash):
        return 0
    async with sessionmaker() as session:
        chats = [r.guardian_chat_id for r in (await session.execute(
            select(FamilyLink).where(FamilyLink.member_hash == member_hash, FamilyLink.guardian_chat_id.is_not(None))
        )).scalars().all()]
    sent = 0
    for chat in chats:
        try:
            resp = await http.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                   json={"chat_id": chat, "text": alert_text(category, app_url), "parse_mode": "HTML"})
            sent += int(resp.status_code == 200)
        except httpx.HTTPError as exc:
            log.warning("family alert failed: %s", type(exc).__name__)
    if chats:
        async with sessionmaker() as session:
            session.add(AlertLog(kind="family", summary={"category": category, "guardians": len(chats)}, delivered=sent > 0))
            await session.commit()
    return sent
