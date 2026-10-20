"""Aggregates for the trends dashboard, plus optional demo rows so a fresh deploy is not empty."""

import hashlib
import random
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import RULES_VERSION
from app.db.models import Analysis, Report


async def compute_stats(sessionmaker: async_sessionmaker, days: int = 14) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    async with sessionmaker() as session:
        rows = (
            await session.execute(select(Analysis).where(Analysis.created_at >= since))
        ).scalars().all()
        total_all = (await session.execute(select(func.count(Analysis.id)))).scalar_one()
        recent = (
            await session.execute(
                select(Analysis)
                .where(Analysis.shared.is_(True), Analysis.excerpt.is_not(None), Analysis.verdict != "no_red_flags",
                       # Shared text goes public only after a person reviewed it (labelled samples excepted).
                       or_(Analysis.is_seed.is_(True), Analysis.id.in_(
                           select(Report.id).where(Report.status == "approved", Report.reviewed_by.is_not(None)))))
                .order_by(Analysis.created_at.desc())
                .limit(8)
            )
        ).scalars().all()

    today = datetime.now(UTC).date()
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    daily = {d: {"likely_scam": 0, "suspicious": 0, "no_red_flags": 0} for d in day_keys}
    verdicts: Counter = Counter()
    categories: Counter = Counter()
    brands: Counter = Counter()
    rules: Counter = Counter()
    seed_rows = 0
    for r in rows:
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
        key = created.date().isoformat()
        if key in daily:
            daily[key][r.verdict] = daily[key].get(r.verdict, 0) + 1
        verdicts[r.verdict] += 1
        if r.verdict != "no_red_flags":
            categories[r.category] += 1
            brands.update(r.brands or [])
            rules.update(r.rule_ids or [])
        seed_rows += int(r.is_seed)

    return {
        "window_days": days,
        "total_checks": len(rows),
        "total_all_time": total_all,
        "verdicts": dict(verdicts),
        "daily": [{"date": d, **daily[d]} for d in day_keys],
        "top_categories": [{"category": c, "count": n} for c, n in categories.most_common(6)],
        "top_brands": [{"brand": b, "count": n} for b, n in brands.most_common(6)],
        "top_rules": [{"rule": r, "count": n} for r, n in rules.most_common(6)],
        "recent_reports": [
            {
                # Not the real id: that is also the check's follow-up thread.
                "id": hashlib.sha256(r.id.encode()).hexdigest()[:12],
                "created_at": r.created_at.isoformat(),
                "verdict": r.verdict,
                "category": r.category,
                "excerpt": r.excerpt,
                "sample": r.is_seed,
            }
            for r in recent
        ],
        "includes_sample_data": seed_rows > 0,
        "sample_rows": seed_rows,
    }


_SEED_MIX = [
    ("likely_scam", "government_benefit", ["bisp"], ["claims_government", "fee_request", "advance_fee", "sender_mismatch"]),
    ("likely_scam", "account_takeover", ["whatsapp"], ["code_hijack", "secret_request"]),
    ("likely_scam", "bank_wallet", ["jazzcash"], ["secret_request", "threat", "link_lookalike"]),
    ("likely_scam", "bank_wallet", ["hbl"], ["link_lookalike", "urgency", "claims_bank"]),
    ("likely_scam", "family_emergency", [], ["family_emergency", "money_transfer", "urgency"]),
    ("likely_scam", "job_task", [], ["job_with_payment", "fee_request", "too_good"]),
    ("likely_scam", "prize", ["jazz"], ["prize", "prize_with_contact", "advance_fee", "fee_request"]),
    ("suspicious", "delivery", ["pakpost"], ["delivery_bait", "link_risky_tld"]),
    ("suspicious", "investment", [], ["too_good", "urgency"]),
    ("suspicious", "loan", [], ["loan_with_fee", "fee_request"]),
    ("no_red_flags", "none", ["hbl"], ["claims_bank", "safety_notice"]),
    ("no_red_flags", "none", [], []),
]

_SEED_EXCERPTS = {
    "government_benefit": "Mubarak ho! Benazir program ki [AMOUNT] ki qist manzoor. Registration fee [PHONE_1] par bhejein",
    "account_takeover": "Ghalti se aap ke number par 6 digit code chala gaya, please wapas bhej dein",
    "bank_wallet": "Dear customer your wallet will be suspended. Verify at jazzcash-verify.com with your MPIN",
    "family_emergency": "Ammi ye mera naya number hai, foran [AMOUNT] easypaisa kar dein, mushkil mein hoon",
    "job_task": "Like YouTube videos and earn daily from home. Registration fee only [AMOUNT]",
    "prize": "Congratulations! Your number won the annual lucky draw. Call [PHONE_1] to claim",
    "delivery": "Pakistan Post: parcel on hold, update address at pakpost-delivery.top",
}


async def seed_demo_analyses(sessionmaker: async_sessionmaker, rows: int = 140) -> int:
    """Insert clearly labelled sample rows (is_seed=True) if the table is empty."""
    async with sessionmaker() as session:
        existing = (await session.execute(select(func.count(Analysis.id)))).scalar_one()
        if existing:
            return 0
        rng = random.Random(42)
        now = datetime.now(UTC)
        weights = [9, 7, 8, 5, 6, 6, 7, 4, 3, 2, 8, 10]
        objs = []
        for _ in range(rows):
            verdict, category, brands, rule_ids = rng.choices(_SEED_MIX, weights=weights)[0]
            created = now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            shared = verdict != "no_red_flags" and rng.random() < 0.35
            objs.append(
                Analysis(
                    id=str(uuid.uuid4()),
                    created_at=created,
                    channel=rng.choice(["web", "web", "telegram"]),
                    verdict=verdict,
                    score={"likely_scam": rng.randint(60, 100), "suspicious": rng.randint(25, 54), "no_red_flags": rng.randint(0, 15)}[verdict],
                    category=category,
                    language=rng.choice(["en", "roman", "roman", "ur"]),
                    rule_ids=rule_ids,
                    hard_rule_ids=[],
                    brands=brands,
                    link_domains=[],
                    memory_matches=rng.randint(0, 4) if verdict == "likely_scam" else 0,
                    llm_model="sample",
                    rules_version=RULES_VERSION,
                    degraded=[],
                    tool_calls=[],
                    shared=shared,
                    excerpt=_SEED_EXCERPTS.get(category) if shared else None,
                    latency_ms=rng.randint(400, 2400),
                    is_seed=True,
                )
            )
        session.add_all(objs)
        await session.commit()
        return len(objs)
