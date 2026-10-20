"""Review panel API for analysts and admins (login required)."""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.api.routes import limit
from app.auth import (
    Principal,
    hash_password,
    login_available,
    make_token,
    require_admin,
    require_analyst,
    verify_password,
)
from app.core.redaction import account_fingerprint, normalize_phone, phone_fingerprint
from app.core.urls import split_url
from app.db.models import (
    Campaign,
    Indicator,
    OfficialDomainExtra,
    Report,
    RuleSuggestion,
    User,
    WatchlistEntry,
)
from app.intel import retention, rule_ideas
from app.intel.indicators import mask_phone
from app.intel.official import load_extra_official
from app.intel.reports import approve_report, campaign_list, reject_report
from app.intel.stix import build_bundle

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class ReviewBody(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class WatchBody(BaseModel):
    kind: str = Field(pattern="^(domain|phone|account)$")
    value: str = Field(min_length=3, max_length=255)
    note: str | None = Field(default=None, max_length=500)


class OfficialBody(BaseModel):
    domain: str = Field(min_length=4, max_length=255)
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(default="platform", pattern="^(bank|wallet|government|telecom|courier|platform|utility)$")


class UserBody(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=10, max_length=200)
    role: str = Field(default="analyst", pattern="^(analyst|admin)$")


class SuggestBody(BaseModel):
    source: str = Field(default="reports", pattern="^(reports|dev_misses|examples)$")
    examples: list[str] = Field(default_factory=list, max_length=8)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


# --- Auth --------------------------------------------------------------------

@router.post("/auth/login")
async def login(body: LoginBody, request: Request) -> dict:
    limit(request)
    request.app.state.limiter.check(f"login:{body.email.lower().strip()}", limit=8)
    s = request.app.state.settings
    problem = login_available(s)
    if problem:
        raise HTTPException(503, problem)
    async with request.app.state.deps.sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == body.email.lower().strip()))).scalar_one_or_none()
        if not user or not user.active or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Wrong email or password.")
        user.last_login_at = datetime.now(UTC)
        await session.commit()
        return {"token": make_token(s, user.email, user.role), "email": user.email, "role": user.role,
                "expires_in_hours": s.token_hours}


@router.get("/auth/me")
async def me(user: Principal = Depends(require_analyst)) -> dict:
    return {"email": user.email, "role": user.role}


# --- Review queue --------------------------------------------------------------

def _report_dict(r: Report, indicators: list[tuple[str, str]]) -> dict:
    return {
        "id": r.id, "created_at": _iso(r.created_at), "status": r.status, "auto_approved": r.auto_approved,
        "channel": r.channel, "source_kind": r.source_kind, "verdict": r.verdict, "score": r.score,
        "category": r.category, "language": r.language, "text": r.redacted_text, "rules": r.rule_ids,
        "hard_rules": r.hard_rule_ids, "brands": r.brands, "campaign_id": r.campaign_id,
        "reviewed_by": r.reviewed_by, "reviewed_at": _iso(r.reviewed_at), "note": r.review_note,
        "indicators": [{"kind": k, "value": v if k in ("domain", "url") else v[:8] + "…"} for k, v in indicators],
    }


@router.get("/admin/reports")
async def list_reports(request: Request, status: str = "pending", limit_: int = 50,
                       _: Principal = Depends(require_analyst)) -> dict:
    if status not in ("pending", "approved", "rejected", "all"):
        raise HTTPException(422, "status must be pending, approved, rejected or all")
    async with request.app.state.deps.sessionmaker() as session:
        q = select(Report).order_by(Report.created_at.desc()).limit(max(1, min(limit_, 200)))
        if status != "all":
            q = q.where(Report.status == status)
        rows = (await session.execute(q)).scalars().all()
        ids = [r.id for r in rows]
        ind = (await session.execute(select(Indicator.report_id, Indicator.kind, Indicator.value)
                                     .where(Indicator.report_id.in_(ids)))).all() if ids else []
        counts = dict((await session.execute(select(Report.status, func.count(Report.id)).group_by(Report.status))).all())
    by_report: dict[str, list] = {}
    for rid, k, v in ind:
        by_report.setdefault(rid, []).append((k, v))
    return {"counts": counts, "reports": [_report_dict(r, by_report.get(r.id, [])) for r in rows]}


@router.post("/admin/reports/{report_id}/approve")
async def approve(report_id: str, body: ReviewBody, request: Request, user: Principal = Depends(require_analyst)) -> dict:
    report = await approve_report(request.app.state.deps, report_id, reviewer=user.email, note=body.note)
    if not report:
        raise HTTPException(404, "Report not found.")
    return {"id": report_id, "status": "approved"}


@router.post("/admin/reports/{report_id}/reject")
async def reject(report_id: str, body: ReviewBody, request: Request, user: Principal = Depends(require_analyst)) -> dict:
    report = await reject_report(request.app.state.deps, report_id, reviewer=user.email, note=body.note)
    if not report:
        raise HTTPException(404, "Report not found.")
    return {"id": report_id, "status": "rejected"}


# --- Campaigns and exports -------------------------------------------------------

@router.get("/admin/campaigns")
async def admin_campaigns(request: Request, min_reports: int = 1, _: Principal = Depends(require_analyst)) -> dict:
    return {"campaigns": await campaign_list(request.app.state.deps, min_reports=max(1, min_reports), limit=100, with_indicators=True)}


@router.get("/admin/export/stix")
async def export_stix(request: Request, campaign_id: str | None = None, _: Principal = Depends(require_analyst)) -> dict:
    return await build_bundle(request.app.state.deps.sessionmaker, campaign_id)


# --- Watchlist ---------------------------------------------------------------------

def _watch_value(kind: str, raw: str, secret: str) -> tuple[str, str, str]:
    """(stored kind, stored value, label). Numbers are kept only as fingerprints."""
    if kind == "domain":
        p = split_url(raw.strip())
        domain = p["registered_domain"] or p["host"]
        if not domain:
            raise HTTPException(422, "That does not look like a website address.")
        return "domain", domain.lower(), domain.lower()
    if kind == "phone":
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 7:
            raise HTTPException(422, "That does not look like a phone number.")
        return "phone_fp", phone_fingerprint(raw, secret), mask_phone(normalize_phone(raw))
    digits = re.sub(r"\s", "", raw)
    if len(re.sub(r"\D", "", digits)) < 8:
        raise HTTPException(422, "That does not look like an account number.")
    return "account_fp", account_fingerprint(raw, secret), "acct " + "•" * 4 + digits[-4:]


@router.get("/admin/watchlist")
async def get_watchlist(request: Request, _: Principal = Depends(require_analyst)) -> dict:
    async with request.app.state.deps.sessionmaker() as session:
        rows = (await session.execute(select(WatchlistEntry).order_by(WatchlistEntry.created_at.desc()))).scalars().all()
    return {"entries": [{"id": r.id, "kind": r.kind, "label": r.label, "note": r.note, "added_by": r.added_by,
                         "created_at": _iso(r.created_at)} for r in rows]}


@router.post("/admin/watchlist")
async def add_watch(body: WatchBody, request: Request, user: Principal = Depends(require_analyst)) -> dict:
    s = request.app.state.settings
    kind, value, label = _watch_value(body.kind, body.value, s.fingerprint_secret)
    async with request.app.state.deps.sessionmaker() as session:
        exists = (await session.execute(select(WatchlistEntry).where(WatchlistEntry.kind == kind, WatchlistEntry.value == value))).scalar_one_or_none()
        if exists:
            raise HTTPException(409, "Already on the watchlist.")
        entry = WatchlistEntry(kind=kind, value=value, label=label, note=body.note, added_by=user.email)
        session.add(entry)
        await session.commit()
        return {"id": entry.id, "kind": kind, "label": label}


@router.delete("/admin/watchlist/{entry_id}")
async def remove_watch(entry_id: int, request: Request, _: Principal = Depends(require_analyst)) -> dict:
    async with request.app.state.deps.sessionmaker() as session:
        res = await session.execute(delete(WatchlistEntry).where(WatchlistEntry.id == entry_id))
        await session.commit()
    return {"removed": res.rowcount or 0}


# --- Official domains (admin only) -------------------------------------------------

@router.get("/admin/official-domains")
async def get_official(request: Request, _: Principal = Depends(require_analyst)) -> dict:
    from app.rules.brands import BRANDS

    async with request.app.state.deps.sessionmaker() as session:
        rows = (await session.execute(select(OfficialDomainExtra).order_by(OfficialDomainExtra.domain))).scalars().all()
    return {
        "built_in": [{"name": b.name, "kind": b.kind, "domains": list(b.domains)} for b in BRANDS],
        "extra": [{"id": r.id, "domain": r.domain, "name": r.name, "kind": r.kind, "added_by": r.added_by} for r in rows],
    }


@router.post("/admin/official-domains")
async def add_official(body: OfficialBody, request: Request, user: Principal = Depends(require_admin)) -> dict:
    p = split_url(body.domain.strip())
    domain = (p["host"] or "").removeprefix("www.")
    if not p["registered_domain"]:
        raise HTTPException(422, "That does not look like a website address.")
    deps = request.app.state.deps
    async with deps.sessionmaker() as session:
        if (await session.execute(select(OfficialDomainExtra).where(OfficialDomainExtra.domain == domain))).scalar_one_or_none():
            raise HTTPException(409, "Already listed.")
        session.add(OfficialDomainExtra(domain=domain, name=body.name.strip(), kind=body.kind, added_by=user.email))
        await session.commit()
    await load_extra_official(deps.sessionmaker)
    return {"domain": domain}


@router.delete("/admin/official-domains/{row_id}")
async def remove_official(row_id: int, request: Request, _: Principal = Depends(require_admin)) -> dict:
    deps = request.app.state.deps
    async with deps.sessionmaker() as session:
        res = await session.execute(delete(OfficialDomainExtra).where(OfficialDomainExtra.id == row_id))
        await session.commit()
    await load_extra_official(deps.sessionmaker)
    return {"removed": res.rowcount or 0}


# --- Rule ideas --------------------------------------------------------------------

def _suggestion_dict(r: RuleSuggestion) -> dict:
    return {"id": r.id, "created_at": _iso(r.created_at), "status": r.status, "signal": r.signal, "pattern": r.pattern,
            "rationale": r.rationale, "examples": r.examples, "test": r.test_results, "model": r.model,
            "created_by": r.created_by, "decided_by": r.decided_by,
            "snippet": rule_ideas.snippet(r) if r.status == "accepted" else None}


@router.get("/admin/rule-ideas")
async def list_ideas(request: Request, _: Principal = Depends(require_analyst)) -> dict:
    async with request.app.state.deps.sessionmaker() as session:
        rows = (await session.execute(select(RuleSuggestion).order_by(RuleSuggestion.created_at.desc()).limit(50))).scalars().all()
    return {"ideas": [_suggestion_dict(r) for r in rows]}


@router.post("/admin/rule-ideas")
async def new_idea(body: SuggestBody, request: Request, user: Principal = Depends(require_analyst)) -> dict:
    limit(request)
    deps = request.app.state.deps
    if body.source == "reports":
        examples = await rule_ideas.missed_reports(deps.sessionmaker)
    elif body.source == "dev_misses":
        examples = rule_ideas.dev_misses()
    else:
        examples = body.examples
    try:
        row = await rule_ideas.suggest(deps, examples, user.email)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return _suggestion_dict(row)


@router.post("/admin/rule-ideas/{idea_id}/{decision}")
async def decide_idea(idea_id: str, decision: str, request: Request, user: Principal = Depends(require_analyst)) -> dict:
    if decision not in ("accept", "reject"):
        raise HTTPException(404, "Unknown action.")
    async with request.app.state.deps.sessionmaker() as session:
        row = await session.get(RuleSuggestion, idea_id)
        if not row:
            raise HTTPException(404, "Suggestion not found.")
        if decision == "accept" and not row.test_results.get("passes"):
            raise HTTPException(409, "This pattern failed its tests, so it cannot be accepted.")
        row.status = "accepted" if decision == "accept" else "rejected"
        row.decided_by = user.email
        await session.commit()
        return _suggestion_dict(row)


# --- Users (admin only) --------------------------------------------------------------

@router.get("/admin/users")
async def list_users(request: Request, _: Principal = Depends(require_admin)) -> dict:
    async with request.app.state.deps.sessionmaker() as session:
        rows = (await session.execute(select(User).order_by(User.created_at))).scalars().all()
    return {"users": [{"id": u.id, "email": u.email, "role": u.role, "active": u.active,
                       "last_login_at": _iso(u.last_login_at)} for u in rows]}


@router.post("/admin/users")
async def create_user(body: UserBody, request: Request, _: Principal = Depends(require_admin)) -> dict:
    email = body.email.lower().strip()
    async with request.app.state.deps.sessionmaker() as session:
        if (await session.execute(select(User).where(User.email == email))).scalar_one_or_none():
            raise HTTPException(409, "That email already has an account.")
        user = User(email=email, password_hash=hash_password(body.password), role=body.role)
        session.add(user)
        await session.commit()
        request.app.state.has_users = True
        return {"id": user.id, "email": email, "role": body.role}


@router.post("/admin/users/{user_id}/{action}")
async def change_user(user_id: int, action: str, request: Request, me_: Principal = Depends(require_admin)) -> dict:
    if action not in ("deactivate", "activate"):
        raise HTTPException(404, "Unknown action.")
    async with request.app.state.deps.sessionmaker() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(404, "User not found.")
        if user.email == me_.email and action == "deactivate":
            raise HTTPException(409, "You cannot deactivate your own account.")
        user.active = action == "activate"
        await session.commit()
        return {"id": user.id, "active": user.active}


# --- Data ----------------------------------------------------------------------------

@router.get("/admin/overview")
async def overview(request: Request, _: Principal = Depends(require_analyst)) -> dict:
    async with request.app.state.deps.sessionmaker() as session:
        reports = dict((await session.execute(select(Report.status, func.count(Report.id)).group_by(Report.status))).all())
        campaigns = (await session.execute(select(func.count(Campaign.id)).where(Campaign.report_count >= 2))).scalar_one()
        watch = (await session.execute(select(func.count(WatchlistEntry.id)))).scalar_one()
        indicators = dict((await session.execute(select(Indicator.kind, func.count(func.distinct(Indicator.value)))
                                                 .group_by(Indicator.kind))).all())
    return {"reports": reports, "campaigns": campaigns, "watchlist": watch, "indicators": indicators}


@router.post("/admin/purge")
async def purge_now(request: Request, _: Principal = Depends(require_admin)) -> dict:
    return {"deleted": await retention.purge(request.app.state.deps)}
