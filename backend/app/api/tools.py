"""Public helper endpoints: lookups, takedown help, payment screenshots, family alerts,
campaigns, the weekly warning, quality numbers and privacy controls."""

import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.ai.media import MediaUnavailable
from app.api.captcha import check_captcha
from app.api.routes import IMAGE_TYPES, limit
from app.api.service import user_hash
from app.files.receipt import ADVICE, read_receipt
from app.intel import alerts, family, retention
from app.intel.lookup import lookup
from app.intel.reports import campaign_list
from app.intel.takedown import takedown_info
from app.schemas import LookupRequest

router = APIRouter(prefix="/api")
EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"


class ClientBody(BaseModel):
    client_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")


class TakedownBody(BaseModel):
    url: str = Field(min_length=4, max_length=500)


@router.post("/lookup")
async def lookup_value(body: LookupRequest, request: Request) -> dict:
    limit(request)
    await check_captcha(request, body.captcha_token)
    try:
        return await lookup(request.app.state.deps, body.value, body.kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/takedown")
async def takedown(body: TakedownBody, request: Request) -> dict:
    limit(request)
    deps = request.app.state.deps
    try:
        return await takedown_info(deps.settings, deps.http, body.url)
    except ValueError as exc:
        raise HTTPException(422, "That does not look like a website address.") from exc


@router.post("/receipt")
async def receipt_check(request: Request, file: UploadFile = File(...), captcha_token: str | None = Form(default=None)) -> dict:
    """Experimental. Reads a 'payment sent' screenshot; gives findings, never a verdict. Not stored."""
    limit(request)
    await check_captcha(request, captcha_token)
    s = request.app.state.settings
    content_type = (file.content_type or "").split(";")[0].lower()
    if content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Upload the payment screenshot as PNG, JPG or WebP.")
    data = await file.read()
    if len(data) > s.max_image_mb * 1024 * 1024:
        raise HTTPException(413, f"Screenshot is larger than {s.max_image_mb:g} MB.")
    try:
        return await read_receipt(s, data, content_type)
    except MediaUnavailable as exc:
        return {"experimental": True, "fields": {}, "findings": [], "advice": ADVICE, "unavailable": str(exc)}
    except Exception as exc:
        raise HTTPException(502, "Could not read the screenshot. The advice below still applies.") from exc


async def _bot_username(request: Request) -> str | None:
    s = request.app.state.settings
    if not s.telegram_bot_token:
        return None
    if getattr(request.app.state, "bot_username", None) is None:
        try:
            resp = await request.app.state.deps.http.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe")
            request.app.state.bot_username = resp.json().get("result", {}).get("username") or ""
        except Exception:
            return None
    return request.app.state.bot_username or None


@router.post("/family/code")
async def family_code(body: ClientBody, request: Request) -> dict:
    limit(request)
    s = request.app.state.settings
    if not s.telegram_bot_token:
        raise HTTPException(503, "Family alerts need the Telegram bot (TELEGRAM_BOT_TOKEN).")
    code = await family.create_code(request.app.state.deps.sessionmaker, user_hash(s, body.client_id))
    return {"code": code, "expires_hours": family.CODE_HOURS, "bot": await _bot_username(request)}


@router.post("/family/status")
async def family_status(body: ClientBody, request: Request) -> dict:
    s = request.app.state.settings
    status = await family.status(request.app.state.deps.sessionmaker, user_hash(s, body.client_id))
    return {**status, "available": bool(s.telegram_bot_token), "bot": await _bot_username(request)}


@router.post("/family/remove")
async def family_remove(body: ClientBody, request: Request) -> dict:
    s = request.app.state.settings
    removed = await family.remove_member(request.app.state.deps.sessionmaker, user_hash(s, body.client_id))
    return {"removed": removed}


@router.post("/me/forget")
async def forget_me(body: ClientBody, request: Request) -> dict:
    limit(request)
    s = request.app.state.settings
    return {"deleted": await retention.forget(request.app.state.deps, user_hash(s, body.client_id))}


@router.get("/campaigns")
async def public_campaigns(request: Request) -> dict:
    return {"campaigns": await campaign_list(request.app.state.deps, min_reports=2, limit=12)}


@router.get("/alerts/latest")
async def latest_alert(request: Request) -> dict:
    return {"alert": await alerts.latest_weekly(request.app.state.deps.sessionmaker)}


@router.get("/quality")
async def quality() -> dict:
    out = {}
    for key, name in (("eval", "results.json"), ("redteam", "redteam_results.json")):
        path = EVAL_DIR / name
        out[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return out


@router.get("/privacy")
async def privacy(request: Request) -> dict:
    s = request.app.state.settings
    return {
        "retention_days": {
            "checks": s.retention_analyses_days,
            "rejected_reports": s.retention_rejected_days,
            "pending_reports": s.retention_pending_days,
            "ai_cache": s.ai_cache_days,
            "alerts": s.retention_alerts_days,
            "family_codes_hours": family.CODE_HOURS,
        },
        "providers": {
            "groq": bool(s.groq_api_key),
            "gemini": bool(s.google_api_key),
            "safe_browsing": bool(s.safe_browsing_api_key),
            "telegram": bool(s.telegram_bot_token),
            "turnstile": bool(s.turnstile_secret),
            "postgres": s.uses_postgres,
        },
    }
