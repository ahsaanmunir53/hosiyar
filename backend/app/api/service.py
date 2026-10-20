"""Shared helpers used by the web API and the Telegram bot."""

import re
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app import RULES_VERSION
from app.config import Settings
from app.core.redaction import fingerprint, normalize_phone, phone_fingerprint, redact, sender_kind
from app.intel.indicators import mask_phone
from app.rules.engine import CATEGORY_LABELS

_CLIENT_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def user_hash(settings: Settings, raw_id: str | None) -> str | None:
    """Hash of a browser's random id. Web ids live in their own namespace, so a web client can
    never claim a Telegram chat's identity."""
    if not raw_id or not _CLIENT_ID.match(raw_id):
        return None
    return fingerprint(f"user:web:{raw_id}", settings.fingerprint_secret)


def telegram_user_hash(settings: Settings, chat_id: int | str) -> str:
    return fingerprint(f"user:tg:{chat_id}", settings.fingerprint_secret)


INPUT_DEFAULTS = {
    "sender": None, "share": False, "requested_language": None, "user_hash": None, "channel": "web",
    "source_kind": "text", "extra_signals": [], "file_info": None, "pre_redacted": False, "sender_kind": None,
    "analysis_id_hint": None,
}


def redact_inputs(settings: Settings, text: str, sender: str | None) -> dict:
    """Redact before the graph runs, so the raw message and the sender's number never reach the
    checkpointer (which keeps thread state for follow-up questions)."""
    red = redact(text[: settings.max_text_chars * 4], settings.fingerprint_secret)
    phones = list(red.phone_fingerprints)
    kind = sender_kind(sender)
    if kind == "mobile" and sender:
        phones.append(phone_fingerprint(sender, settings.fingerprint_secret))
        sender = mask_phone(normalize_phone(sender))
    return {
        "text": red.text,
        "pre_redacted": True,
        "redactions": red.counts,
        "phone_fingerprints": sorted(set(phones)),
        "account_fingerprints": red.account_fingerprints,
        "sender": sender,
        "sender_kind": kind,
    }


async def run_analysis(graph, *, thread_id: str | None = None, **inputs) -> tuple[str, dict]:
    # Every input is set on every run, so nothing leaks from an earlier check in the same thread.
    inputs = {**INPUT_DEFAULTS, **inputs}
    deps = getattr(graph, "deps", None)
    if deps is not None and not inputs.get("pre_redacted"):
        inputs.update(redact_inputs(deps.settings, inputs.get("text") or "", inputs.get("sender")))
    if thread_id is None:
        thread_id = str(uuid.uuid4())
        inputs["analysis_id_hint"] = thread_id
    elif deps is not None and deps.checkpointer is not None:
        # A reused thread (Telegram) keeps only the latest check, for follow-up questions.
        try:
            await deps.checkpointer.adelete_thread(thread_id)
        except Exception:
            pass
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}
    state = await graph.ainvoke({"mode": "analyze", **inputs}, config)
    return thread_id, state


async def run_followup(graph, thread_id: str, **inputs) -> dict:
    deps = getattr(graph, "deps", None)
    if deps is not None and inputs.get("question"):
        inputs["question"] = redact(inputs["question"], deps.settings.fingerprint_secret).text
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 10}
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.values.get("verdict"):
        raise HTTPException(status_code=404, detail="That check was not found. Run a new check first.")
    state = await graph.ainvoke({"mode": "followup", **inputs}, config)
    return state["answer"]


def to_response(thread_id: str, state: dict) -> dict:
    links = [
        {
            k: r.get(k)
            for k in (
                "url", "host", "registered_domain", "final_registered_domain", "expanded_url", "is_shortener",
                "official_brand", "lookalike_brand", "domain_age_days", "safe_browsing_threats",
                "risky_tld", "is_ip", "is_punycode", "homograph_of", "checks", "errors",
            )
        }
        for r in state.get("link_reports", [])
    ]
    category = state.get("category", "other")
    return {
        "id": state["analysis_id"],
        "thread_id": thread_id,
        "verdict": state["verdict"],
        "score": state["score"],
        "category": {"id": category, "label": CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])},
        "language": state["language"],
        "explanation": state["explanation"],
        "reasons": state["rule_hits"],
        "links": links,
        "similar": state.get("memory_matches", []),
        "reported_number_count": state.get("reported_number_count", 0),
        "next_steps": state["next_steps"],
        "investigation": state.get("tool_trace", []),
        "redactions": state.get("redactions", {}),
        "analyzed_text": state.get("redacted_text", ""),
        "source_kind": state.get("source_kind", "text"),
        "source_language": state.get("source_language", state["language"]),
        "file_info": state.get("file_info"),
        "reported_account_count": state.get("reported_account_count", 0),
        "watchlist": state.get("watchlist", []),
        "report_status": state.get("report_status"),
        "ai_summary": state.get("ai_summary"),
        "model": state.get("model", "none"),
        "rules_version": RULES_VERSION,
        "degraded": state.get("degraded", []),
        "shared": bool(state.get("share")),
    }


class RateLimiter:
    """Small in-memory sliding window per client IP. Protects free API quotas."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int | None = None) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= (limit or self.per_minute):
            raise HTTPException(status_code=429, detail="Too many requests in a minute. Wait a moment and try again.")
        q.append(now)
        if len(self.hits) > 5000:
            self._evict(now)

    def _evict(self, now: float) -> None:
        """Drop idle keys only, so a flood of new keys cannot reset everyone's counters."""
        for k in [k for k, q in self.hits.items() if not q or now - q[-1] > 60]:
            del self.hits[k]


def client_ip(request: Request) -> str:
    """The visitor's address as the hosting proxies saw it. Entries a client writes into
    X-Forwarded-For itself come first and are never used (see Settings.client_ip_header)."""
    settings = request.app.state.settings
    hops = settings.trusted_proxy_hops
    if hops and settings.client_ip_header:
        value = request.headers.get(settings.client_ip_header, "").strip()
        if value:
            return value
    forwarded = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if hops and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.client.host if request.client else "unknown"
