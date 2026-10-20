"""Public API for checking messages, files and emails."""

import re
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app import RULES_VERSION
from app.ai import model_status
from app.ai.media import MediaUnavailable, audio_to_text, image_to_text
from app.ai.signals import extract_ai_signals, model_name, short_error
from app.api.captcha import check_captcha
from app.api.service import client_ip, run_analysis, run_followup, to_response, user_hash
from app.db.stats import compute_stats
from app.files import FileReading, FileUnreadable, sanitize_info
from app.files.email_check import read_email
from app.files.pdf import read_pdf
from app.files.qr import describe_qr
from app.guidance.next_steps import channels
from app.rules.engine import rulebook
from app.schemas import (
    AnalysisResponse,
    AnalyzeRequest,
    EmailRequest,
    FollowupRequest,
    FollowupResponse,
)

router = APIRouter(prefix="/api")

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
AUDIO_TYPES = {
    "audio/ogg", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/wav",
    "audio/x-wav", "audio/webm", "audio/flac", "video/webm", "application/ogg",
}
PDF_TYPES = {"application/pdf", "application/x-pdf"}
_RECEIVE_WORDS = re.compile(r"(?i)\b(refund|prize|reward|lottery|lucky|winner|relief|bisp|benazir|ehsaas|government|govt|cash ?back|inaam|imdad|subsidy|claim)\b")
EMAIL_TYPES = {"message/rfc822", "application/eml"}


def limit(request: Request) -> None:
    request.app.state.limiter.check(client_ip(request))


def _signals(reading: FileReading) -> list[dict]:
    return [{"name": n, "evidence": e} for n, e in reading.signals]


@router.get("/health")
async def health(request: Request) -> dict:
    s = request.app.state.settings
    deps = request.app.state.deps
    return {
        "status": "ok",
        "app": "Hoshiyar",
        "llm": deps.llm is not None and s.resolved_llm_provider,
        "llm_fallback": len(deps.models) > 1,
        "model": request.app.state.model_label,
        "models": [model_status.describe(m, detail=False) for m in deps.models],
        "embeddings": deps.embed_provider,
        "storage": "postgres" if s.uses_postgres else "local",
        "network_checks": s.enable_network_checks,
        "safe_browsing": bool(s.safe_browsing_api_key),
        "screenshots": bool(s.google_api_key),
        "voice_notes": bool(s.groq_api_key),
        "telegram": bool(s.telegram_bot_token),
        "captcha": bool(s.turnstile_secret),
        "review_panel": bool(s.admin_email) or request.app.state.has_users,
        "rules_version": RULES_VERSION,
    }


@router.get("/health/ai")
async def health_ai(request: Request) -> dict:
    """Make one small test call to each configured model and report what happened."""
    limit(request)
    s = request.app.state.settings
    deps = request.app.state.deps
    if not deps.models:
        return {"ok": False, "models": [], "detail": "No AI key is configured, so the app runs on rules only."}
    sample = "Pakistan Post: your parcel is on hold. Pay Rs 150 at pakpost-delivery.top today."
    results = []
    for model in deps.models:
        started = time.monotonic()
        try:
            ai = await extract_ai_signals(model, sample, s.llm_timeout_seconds)
            model_status.note_success(model)
            results.append({"model": model_name(model), "ok": True, "summary": ai.summary})
        except Exception as exc:
            kind = model_status.note_failure(model, exc)
            results.append({"model": model_name(model), "ok": False, "error": short_error(exc),
                            "kind": kind, "hint": model_status.HINTS.get(kind, "")})
        results[-1]["ms"] = int((time.monotonic() - started) * 1000)
    return {"ok": any(r["ok"] for r in results), "models": results,
            "chain": request.app.state.model_label,
            "replaced": getattr(request.app.state, "model_changes", [])}


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(body: AnalyzeRequest, request: Request) -> dict:
    limit(request)
    await check_captcha(request, body.captcha_token)
    s = request.app.state.settings
    text, file_info, extra = body.text, None, []
    if body.source_kind == "qr":
        file_info = describe_qr(body.text)
        payment = file_info.get("payment")
        if payment:
            who = payment.get("merchant_name") or "an unnamed merchant"
            text = f"QR code: a payment code that pays {who}" + (f" {payment.get('currency') or ''} {payment['amount']}" if payment.get("amount") else "")
            # A payment code named like a refund, prize or relief desk is the "scan to receive money" trick.
            if _RECEIVE_WORDS.search(who):
                extra.append({"name": "receive_by_scan", "evidence": f"payment QR named \"{who}\""})
        else:
            text = f"QR code content: {body.text}"
    thread_id, state = await run_analysis(
        request.app.state.graph,
        text=text,
        sender=body.sender,
        share=body.share,
        requested_language=body.language,
        user_hash=user_hash(s, body.client_id),
        channel="web",
        source_kind=body.source_kind,
        file_info=file_info,
        extra_signals=extra,
    )
    return to_response(thread_id, state)


@router.post("/analyze/email", response_model=AnalysisResponse)
async def analyze_email(body: EmailRequest, request: Request) -> dict:
    limit(request)
    await check_captcha(request, body.captcha_token)
    s = request.app.state.settings
    if len(body.raw.encode()) > s.max_email_kb * 1024:
        raise HTTPException(413, f"The email is larger than {s.max_email_kb} KB. Remove attachments or paste the text instead.")
    try:
        reading = read_email(body.raw)
    except FileUnreadable as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _analyze_reading(request, reading, "email", None, body.share, body.language, body.client_id)


async def _analyze_reading(request: Request, reading: FileReading, kind: str, sender: str | None, share: bool,
                           language: str | None, client_id: str | None, note: str | None = None) -> dict:
    s = request.app.state.settings
    text = "\n".join(p for p in (reading.text, note or "") if p and p.strip())
    thread_id, state = await run_analysis(
        request.app.state.graph,
        text=text,
        sender=sender,
        share=share,
        requested_language=language if language in ("en", "ur", "roman") else None,
        user_hash=user_hash(s, client_id),
        channel="web",
        source_kind=kind,
        extra_signals=_signals(reading),
        file_info=sanitize_info(reading.info, s.fingerprint_secret),
    )
    return to_response(thread_id, state)


@router.post("/analyze/upload", response_model=AnalysisResponse)
async def analyze_upload(
    request: Request,
    file: UploadFile = File(...),
    sender: str | None = Form(default=None),
    share: bool = Form(default=False),
    language: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    note: str | None = Form(default=None),
    captcha_token: str | None = Form(default=None),
) -> dict:
    limit(request)
    await check_captcha(request, captcha_token)
    s = request.app.state.settings
    content_type = (file.content_type or "").split(";")[0].lower()
    name = (file.filename or "").lower()
    data = await file.read()
    if content_type in PDF_TYPES or name.endswith(".pdf"):
        if len(data) > s.max_pdf_mb * 1024 * 1024:
            raise HTTPException(413, f"The PDF is larger than {s.max_pdf_mb:g} MB.")
        try:
            reading = read_pdf(data, s.max_pdf_pages)
        except FileUnreadable as exc:
            raise HTTPException(422, str(exc)) from exc
        return await _analyze_reading(request, reading, "pdf", sender, share, language, client_id, note)
    if content_type in EMAIL_TYPES or name.endswith(".eml"):
        if len(data) > s.max_email_kb * 1024:
            raise HTTPException(413, f"The email file is larger than {s.max_email_kb} KB.")
        try:
            reading = read_email(data)
        except FileUnreadable as exc:
            raise HTTPException(422, str(exc)) from exc
        return await _analyze_reading(request, reading, "email", sender, share, language, client_id, note)
    try:
        if content_type in IMAGE_TYPES:
            if len(data) > s.max_image_mb * 1024 * 1024:
                raise HTTPException(413, f"Screenshot is larger than {s.max_image_mb:g} MB.")
            text, kind = await image_to_text(s, data, content_type), "image"
        elif content_type in AUDIO_TYPES:
            if len(data) > s.max_audio_mb * 1024 * 1024:
                raise HTTPException(413, f"Voice note is larger than {s.max_audio_mb:g} MB.")
            text, kind = await audio_to_text(s, data, file.filename or "voice.ogg"), "audio"
        else:
            raise HTTPException(415, "Upload a screenshot (PNG, JPG, WebP), a voice note (OGG, MP3, M4A, WAV, WebM), a PDF or an email (.eml).")
    except MediaUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Could not read the file. Try again, or paste the text instead.") from exc

    combined = "\n".join(p for p in (text, note or "") if p.strip())
    if not combined.strip():
        raise HTTPException(422, "No text was found in that file. Paste the message text instead.")
    thread_id, state = await run_analysis(
        request.app.state.graph,
        text=combined,
        sender=sender,
        share=share,
        requested_language=language if language in ("en", "ur", "roman") else None,
        user_hash=user_hash(s, client_id),
        channel="web",
        source_kind=kind,
    )
    return to_response(thread_id, state)


@router.post("/followup", response_model=FollowupResponse)
async def followup(body: FollowupRequest, request: Request) -> dict:
    limit(request)
    s = request.app.state.settings
    answer = await run_followup(
        request.app.state.graph,
        body.thread_id,
        question=body.question,
        requested_language=body.language,
        user_hash=user_hash(s, body.client_id),
    )
    return {"thread_id": body.thread_id, "answer": answer}


@router.get("/stats")
async def stats(request: Request, days: int = 14) -> dict:
    return await compute_stats(request.app.state.deps.sessionmaker, max(1, min(days, 60)))


@router.get("/rules")
async def rules() -> dict:
    return {"version": RULES_VERSION, "rules": rulebook()}


@router.get("/channels")
async def reporting_channels() -> dict:
    return channels()
