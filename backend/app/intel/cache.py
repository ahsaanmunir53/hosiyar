"""Cache of model readings keyed by a hash of the redacted text, model and prompt version.

Scam campaigns send the same text to thousands of people. Reading it once saves free-tier
quota and makes repeated checks faster. Only redacted text is ever hashed or stored.
"""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AICache

PROMPT_VERSION = "signals-v3"


def cache_key(kind: str, model: str, text: str) -> str:
    return hashlib.sha256(f"{kind}|{model}|{PROMPT_VERSION}|{text}".encode()).hexdigest()


async def get(sessionmaker: async_sessionmaker, key: str, max_age_days: int) -> dict | None:
    async with sessionmaker() as session:
        row = await session.get(AICache, key)
        if not row:
            return None
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - created > timedelta(days=max_age_days):
            return None
        row.hits += 1
        value = dict(row.value)
        await session.commit()
        return value


async def put(sessionmaker: async_sessionmaker, key: str, kind: str, model: str, value: dict) -> None:
    async with sessionmaker() as session:
        row = await session.get(AICache, key)
        if row:
            row.value, row.model, row.created_at = value, model, datetime.now(UTC)
        else:
            session.add(AICache(key=key, kind=kind, model=model, value=value))
        await session.commit()
