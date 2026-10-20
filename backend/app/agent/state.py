"""Graph state. Everything here is plain JSON-friendly data so the checkpointer can save it."""

from dataclasses import dataclass, field
from typing import Any, TypedDict

import httpx
from langchain_core.language_models import BaseChatModel
from langgraph.store.base import BaseStore
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.rules.brands import BRANDS
from app.rules.signals import Signal, SignalSet


class AnalysisState(TypedDict, total=False):
    # Inputs
    mode: str  # "analyze" | "followup"
    text: str
    sender: str | None
    channel: str
    user_hash: str | None
    share: bool
    requested_language: str | None
    source_kind: str  # text | image | audio | qr | pdf | email
    question: str | None
    # Signals from a file reader (PDF scripts, email sender checks) and what to show about the file.
    extra_signals: list[dict]
    file_info: dict | None
    # Set by the API layer, which redacts the text (and masks a mobile sender) before the graph runs.
    pre_redacted: bool
    sender_kind: str | None
    # One-off checks use their thread id as the analysis id, so retention can delete the thread.
    analysis_id_hint: str | None

    # Working data
    analysis_id: str
    started_at: float
    language: str
    source_language: str
    redacted_text: str
    redactions: dict[str, int]
    phone_fingerprints: list[str]
    account_fingerprints: list[str]
    urls: list[str]
    signals: dict
    ai_summary: str | None
    plan: list[str]
    link_agent_out: dict
    memory_agent_out: dict
    link_reports: list[dict]
    memory_matches: list[dict]
    reported_number_count: int
    reported_account_count: int
    watchlist: list[dict]
    tool_trace: list[dict]
    degraded: list[str]
    report_status: str | None

    # Result
    rule_hits: list[dict]
    score: int
    verdict: str
    category: str
    explanation: dict
    next_steps: list[dict]
    model: str

    # Conversation memory for follow-up questions
    followups: list[dict]
    answer: dict | None


@dataclass
class Deps:
    settings: Settings
    llm: BaseChatModel | None
    store: BaseStore
    embed_provider: str
    sessionmaker: async_sessionmaker
    http: httpx.AsyncClient | None
    fallbacks: list[BaseChatModel] = field(default_factory=list)
    checkpointer: Any = None
    # The same models in the order the tool-calling agents should try them (fast model first).
    # None means the normal order.
    agent_order: list[BaseChatModel] | None = None

    @property
    def models(self) -> list[BaseChatModel]:
        """Main model first, then fallbacks."""
        return [m for m in [self.llm, *self.fallbacks] if m is not None]

    @property
    def agent_models(self) -> list[BaseChatModel]:
        return list(self.agent_order) if self.agent_order else self.models


_BRAND_BY_KEY = {b.key: b for b in BRANDS}


def signals_to_dict(s: SignalSet) -> dict:
    return {
        "signals": {
            name: {"evidence": sig.evidence, "sources": sorted(sig.sources)} for name, sig in s.signals.items()
        },
        "brands": [b.key for b in s.brands],
        "ai_claimed_identity": s.ai_claimed_identity,
        "ai_summary": s.ai_summary,
    }


def signals_from_dict(d: dict[str, Any]) -> SignalSet:
    s = SignalSet()
    for name, data in (d.get("signals") or {}).items():
        s.signals[name] = Signal(name, list(data.get("evidence", [])), set(data.get("sources", [])))
    s.brands = [_BRAND_BY_KEY[k] for k in d.get("brands", []) if k in _BRAND_BY_KEY]
    s.ai_claimed_identity = d.get("ai_claimed_identity")
    s.ai_summary = d.get("ai_summary")
    return s
