"""STIX 2.1 export of confirmed scam websites and links, for sharing with CERTs and police.

Only sites a reviewer approved, or that a deterministic link check confirmed, are exported.

Only domains and URLs are exported. Phone and account fingerprints are keyed hashes that mean
nothing outside this deployment, and exporting them could still single people out, so they
stay private. IDs are UUIDv5, so exporting twice gives the same objects.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Campaign, Indicator, Report
from app.intel.indicators import trusted_site
from app.rules.engine import CATEGORY_LABELS

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/hoshiyar/stix")
# The TLP:WHITE marking definition predefined in the STIX 2.1 specification.
TLP_WHITE = "marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9"


def _id(kind: str, key: str) -> str:
    return f"{kind}--{uuid.uuid5(_NS, f'{kind}:{key}')}"


def _ts(dt: datetime) -> str:
    dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def build_bundle(sessionmaker, campaign_id: str | None = None, app_name: str = "Hoshiyar") -> dict:
    async with sessionmaker() as session:
        q = (select(Indicator.kind, Indicator.value, Report.created_at, Report.category, Report.campaign_id)
             .join(Report, Report.id == Indicator.report_id)
             .where(Report.status == "approved", Indicator.kind.in_(("domain", "url")), trusted_site()))
        if campaign_id:
            q = q.where(Report.campaign_id == campaign_id)
        rows = (await session.execute(q)).all()
        cids = {r.campaign_id for r in rows if r.campaign_id}
        campaigns = (await session.execute(select(Campaign).where(Campaign.id.in_(cids)))).scalars().all() if cids else []

    identity_id = _id("identity", app_name)
    epoch = "2026-01-01T00:00:00.000Z"
    objects: list[dict] = [{
        "type": "identity", "spec_version": "2.1", "id": identity_id, "created": epoch, "modified": epoch,
        "name": app_name, "identity_class": "system",
        "description": "Community scam checker for Pakistan. Indicators come from reviewed or rule-confirmed user reports.",
    }]
    for c in campaigns:
        objects.append({
            "type": "campaign", "spec_version": "2.1", "id": _id("campaign", c.id), "created_by_ref": identity_id,
            "created": _ts(c.created_at), "modified": _ts(c.last_seen), "name": c.label or c.id,
            "description": f"{CATEGORY_LABELS.get(c.category, CATEGORY_LABELS['other'])['en']} · {c.report_count} reports",
            "first_seen": _ts(c.first_seen), "last_seen": _ts(c.last_seen), "object_marking_refs": [TLP_WHITE],
        })
    seen: dict[str, dict] = {}
    for kind, value, created, category, cid in rows:
        key = f"{kind}:{value}"
        if key not in seen:
            pattern = f"[domain-name:value = '{_escape(value)}']" if kind == "domain" else f"[url:value = '{_escape(value)}']"
            seen[key] = {
                "type": "indicator", "spec_version": "2.1", "id": _id("indicator", key), "created_by_ref": identity_id,
                "created": _ts(created), "modified": _ts(created), "name": value,
                "description": f"Seen in {CATEGORY_LABELS.get(category, CATEGORY_LABELS['other'])['en'].lower()} reports",
                "indicator_types": ["malicious-activity"], "pattern": pattern, "pattern_type": "stix",
                "valid_from": _ts(created), "labels": [category], "object_marking_refs": [TLP_WHITE],
                "_campaigns": set(),
            }
        if cid:
            seen[key]["_campaigns"].add(cid)
    for ind in seen.values():
        for cid in sorted(ind.pop("_campaigns")):
            objects.append({
                "type": "relationship", "spec_version": "2.1",
                "id": _id("relationship", f"{ind['id']}>{cid}"), "created_by_ref": identity_id,
                "created": ind["created"], "modified": ind["created"], "relationship_type": "indicates",
                "source_ref": ind["id"], "target_ref": _id("campaign", cid),
            })
        objects.append(ind)
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": objects}
