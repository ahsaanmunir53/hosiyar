"""Admin-added official domains, loaded into the brand list at start-up and after changes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import OfficialDomainExtra
from app.rules import brands


async def load_extra_official(sessionmaker: async_sessionmaker) -> int:
    async with sessionmaker() as session:
        rows = (await session.execute(select(OfficialDomainExtra))).scalars().all()
    brands.set_extra_official([(r.domain, r.name, r.kind) for r in rows])
    return len(rows)
