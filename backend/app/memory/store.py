"""Long-term memory on top of a LangGraph store (in-memory locally, Postgres + pgvector in production).

Namespaces:
  ("patterns", <provider>)     curated library of known scam templates (synthetic, labelled)
  ("community", <provider>)    redacted messages people shared, added once the report is approved
  ("users", <user hash>)       per-user preferences (reply language) and simple counters

Phone and account fingerprints live in the database (report_indicators), where a number only
counts once a reviewer approved it or several different people reported it.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from langgraph.store.base import BaseStore, PutOp

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def patterns_ns(provider: str) -> tuple[str, ...]:
    return ("patterns", provider)


def community_ns(provider: str) -> tuple[str, ...]:
    return ("community", provider)


def user_ns(user_hash: str) -> tuple[str, ...]:
    return ("users", user_hash)


async def search_similar(
    store: BaseStore, provider: str, text: str, threshold: float, limit: int = 5, exclude_key: str | None = None
) -> list[dict]:
    """Find stored scam messages whose meaning is close to `text`."""
    matches: list[dict] = []
    for ns, source in ((patterns_ns(provider), "pattern_library"), (community_ns(provider), "community")):
        try:
            items = await store.asearch(ns, query=text[:2000], limit=limit)
        except Exception as exc:  # embedding provider errors must not break an analysis
            log.warning("memory search failed in %s: %s", ns, exc)
            continue
        for item in items:
            if item.key == exclude_key or item.score is None or item.score < threshold:
                continue
            v = item.value
            matches.append(
                {
                    "key": item.key,
                    "source": source,
                    "similarity": round(float(item.score), 3),
                    "verdict": v.get("verdict", "likely_scam"),
                    "category": v.get("category", "other"),
                    # Text shared by other people is shown only after a person reviewed it.
                    "excerpt": (v.get("text") or "")[:160] if source == "pattern_library" or v.get("reviewed") else "",
                    "reviewed": source == "pattern_library" or bool(v.get("reviewed")),
                    "synthetic": bool(v.get("synthetic")),
                }
            )
    matches.sort(key=lambda m: -m["similarity"])
    return matches[:limit]


async def save_report(
    store: BaseStore,
    provider: str,
    *,
    key: str,
    redacted_text: str,
    verdict: str,
    category: str,
    language: str,
    domains: list[str],
    reviewed: bool = False,
) -> None:
    await store.aput(
        community_ns(provider),
        key,
        {
            "text": redacted_text[:2000],
            "verdict": verdict,
            "category": category,
            "language": language,
            "domains": domains,
            "reviewed": reviewed,
            "created_at": datetime.now(UTC).isoformat(),
        },
        index=["text"],
    )


async def delete_report(store: BaseStore, provider: str, key: str) -> None:
    try:
        await store.adelete(community_ns(provider), key)
    except Exception as exc:
        log.warning("could not remove %s from memory: %s", key, exc)


async def forget_user(store: BaseStore, user_hash: str | None) -> None:
    if user_hash:
        await store.adelete(user_ns(user_hash), "profile")


async def get_user_profile(store: BaseStore, user_hash: str | None) -> dict:
    if not user_hash:
        return {}
    item = await store.aget(user_ns(user_hash), "profile")
    return dict(item.value) if item else {}


async def update_user_profile(store: BaseStore, user_hash: str | None, **changes) -> dict:
    if not user_hash:
        return {}
    profile = await get_user_profile(store, user_hash)
    profile.update({k: v for k, v in changes.items() if v is not None})
    profile["updated_at"] = datetime.now(UTC).isoformat()
    await store.aput(user_ns(user_hash), "profile", profile, index=False)
    return profile


async def record_user_check(store: BaseStore, user_hash: str | None, verdict: str) -> dict:
    if not user_hash:
        return {}
    profile = await get_user_profile(store, user_hash)
    counts = dict(profile.get("checks", {}))
    counts[verdict] = counts.get(verdict, 0) + 1
    return await update_user_profile(store, user_hash, checks=counts)


async def seed_pattern_library(store: BaseStore, provider: str, path: Path | None = None) -> int:
    """Load the curated scam pattern library once. Returns how many items were added."""
    path = path or DATA_DIR / "pattern_library.jsonl"
    existing = await store.asearch(patterns_ns(provider), limit=1)
    if existing or not path.exists():
        return 0
    ops = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ops.append(
            PutOp(
                namespace=patterns_ns(provider),
                key=row.get("id") or str(uuid.uuid4()),
                value={
                    "text": row["text"],
                    "verdict": "likely_scam",
                    "category": row["category"],
                    "language": row.get("language", "en"),
                    "synthetic": True,
                },
                index=["text"],
            )
        )
    try:
        await store.abatch(ops)
    except Exception as exc:
        log.warning("Could not seed pattern library: %s", exc)
        return 0
    return len(ops)
