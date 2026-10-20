"""Optional Cloudflare Turnstile check for the web form (free). Off unless TURNSTILE_SECRET is set."""

import hmac
import logging

import httpx
from fastapi import HTTPException, Request

from app.api.service import client_ip

log = logging.getLogger(__name__)
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def check_captcha(request: Request, token: str | None) -> None:
    s = request.app.state.settings
    if not s.turnstile_secret:
        return
    # The browser extension and the MCP server cannot show a captcha; they send the integration key.
    sent = request.headers.get("x-hoshiyar-key", "")
    if s.integration_key and sent.isascii() and hmac.compare_digest(sent, s.integration_key):
        return
    token = token or request.headers.get("x-captcha-token")
    if not token:
        raise HTTPException(403, "Please complete the captcha and try again.")
    http = request.app.state.deps.http
    try:
        resp = await http.post(VERIFY_URL, data={"secret": s.turnstile_secret, "response": token, "remoteip": client_ip(request)})
        ok = bool(resp.json().get("success"))
    except (httpx.HTTPError, ValueError) as exc:
        # Do not lock everyone out when Cloudflare is unreachable; the rate limit still applies.
        log.warning("Turnstile verification unavailable: %s", type(exc).__name__)
        return
    if not ok:
        raise HTTPException(403, "The captcha check failed. Reload the page and try again.")
