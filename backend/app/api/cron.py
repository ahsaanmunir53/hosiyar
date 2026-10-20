"""Scheduled jobs, called by GitHub Actions (free) with the X-Cron-Secret header."""

import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.intel import alerts, retention

router = APIRouter(prefix="/api/cron")


def _check(request: Request, secret: str | None) -> None:
    expected = request.app.state.settings.cron_secret
    if not expected:
        raise HTTPException(404, "Scheduled jobs are not configured (set CRON_SECRET).")
    if not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(401, "Bad cron secret.")


@router.post("/weekly")
async def weekly(request: Request, x_cron_secret: str | None = Header(default=None)) -> dict:
    _check(request, x_cron_secret)
    deps = request.app.state.deps
    result = await alerts.send_weekly(deps, deps.settings.telegram_alert_chat_id)
    return {"delivered": result["delivered"], "summary": result["summary"]}


@router.post("/purge")
async def purge(request: Request, x_cron_secret: str | None = Header(default=None)) -> dict:
    _check(request, x_cron_secret)
    return {"deleted": await retention.purge(request.app.state.deps)}
