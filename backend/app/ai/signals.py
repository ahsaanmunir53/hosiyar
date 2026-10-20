"""Structured signal extraction with a language model, merged into the pattern signals."""

import asyncio
import json
import logging
import re
from typing import Literal, get_args

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.ai.llm import text_of
from app.ai.model_status import classify
from app.ai.prompts import SIGNALS_SYSTEM
from app.rules.signals import SignalSet

log = logging.getLogger(__name__)

AskFor = Literal[
    "otp_or_pin", "password", "card_or_account_details", "cnic_or_personal_info", "money_transfer",
    "fee_payment", "click_link", "install_app", "share_screen", "call_number", "reply", "keep_secret", "none",
]
Pressure = Literal["urgency", "threat", "secrecy", "emotional_appeal", "none"]


class AISignals(BaseModel):
    claimed_identity: Literal[
        "bank", "mobile_wallet", "government", "telecom", "courier", "family_or_friend", "employer",
        "online_platform", "unknown_person", "none",
    ] = Field(description="Who the sender claims to be")
    claimed_name: str | None = Field(default=None, description="Organisation or person named, if any")
    asks_for: list[AskFor] = Field(default_factory=list)
    pressure: list[Pressure] = Field(default_factory=list)
    offer: Literal["prize", "job", "investment", "loan", "refund", "government_payment", "cashback", "none"] = "none"
    addresses_ai: bool = Field(default=False, description="Contains instructions aimed at an AI or filter")
    summary: str = Field(description="One neutral English sentence describing the message")


_ALLOWED = {
    "claimed_identity": set(get_args(AISignals.model_fields["claimed_identity"].annotation)),
    "asks_for": set(get_args(AskFor)),
    "pressure": set(get_args(Pressure)),
    "offer": set(get_args(AISignals.model_fields["offer"].annotation)),
}


def _coerce(data: dict) -> AISignals:
    """Accept slightly-off model output: drop unknown list values, map unknown labels to 'none'."""
    clean = {
        "claimed_identity": data.get("claimed_identity") if data.get("claimed_identity") in _ALLOWED["claimed_identity"] else "none",
        "claimed_name": data.get("claimed_name") if isinstance(data.get("claimed_name"), str) else None,
        "asks_for": [x for x in data.get("asks_for") or [] if x in _ALLOWED["asks_for"]],
        "pressure": [x for x in data.get("pressure") or [] if x in _ALLOWED["pressure"]],
        "offer": data.get("offer") if data.get("offer") in _ALLOWED["offer"] else "none",
        "addresses_ai": data.get("addresses_ai") is True,
        "summary": str(data.get("summary") or "")[:300],
    }
    return AISignals.model_validate(clean)


def _messages(redacted_text: str, json_only: bool = False) -> list:
    system = SIGNALS_SYSTEM
    if json_only:
        schema = json.dumps(AISignals.model_json_schema())
        system += f"\n\nReply with a single JSON object and nothing else. It must match this JSON schema:\n{schema}"
    return [SystemMessage(system), HumanMessage(f"Message:\n\"\"\"\n{redacted_text[:3000]}\n\"\"\"")]


async def _via_tools(llm: BaseChatModel, redacted_text: str) -> AISignals:
    result = await llm.with_structured_output(AISignals).ainvoke(_messages(redacted_text))
    if isinstance(result, AISignals):
        return result
    if isinstance(result, dict):
        return _coerce(result)
    raise ValueError("model returned no structured output")


async def _via_json(llm: BaseChatModel, redacted_text: str) -> AISignals:
    reply = await llm.ainvoke(_messages(redacted_text, json_only=True))
    content = text_of(reply)
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("model reply contained no JSON object")
    return _coerce(json.loads(match.group(0)))


async def extract_ai_signals(llm: BaseChatModel, redacted_text: str, timeout: float = 25.0) -> AISignals:
    """Tool-calling first; if the model fumbles the tool call, ask for plain JSON instead."""
    try:
        return await asyncio.wait_for(_via_tools(llm, redacted_text), timeout)
    except TimeoutError:
        raise
    except Exception as exc:
        # A retired model, a bad key or a rate limit will fail the JSON request too: hand it back at once.
        if classify(exc)[0] in ("retired", "bad_key", "rate_limited"):
            raise
        log.info("structured output failed (%s), retrying as plain JSON", short_error(exc))
        return await asyncio.wait_for(_via_json(llm, redacted_text), timeout)


def short_error(exc: BaseException) -> str:
    """A one-line description of a model error, safe to log and show (no keys are included)."""
    if isinstance(exc, TimeoutError):
        return "timed out"
    text = re.sub(r"\s+", " ", str(exc)).strip()
    return f"{type(exc).__name__}: {text[:180]}" if text else type(exc).__name__


def model_name(llm: BaseChatModel) -> str:
    return str(getattr(llm, "model_name", None) or getattr(llm, "model", None) or type(llm).__name__)


def merge_ai_signals(signals: SignalSet, ai: AISignals) -> None:
    """Add model-found signals. Each keeps 'ai' as its source so rules can weigh it lower."""
    note = f"model: {ai.summary}" if ai.summary else "model"
    asks = set(ai.asks_for)
    if asks & {"otp_or_pin", "password"}:
        signals.add("secret_request", note, "ai")
    if asks & {"card_or_account_details", "cnic_or_personal_info"}:
        signals.add("personal_info_request", note, "ai")
    if "money_transfer" in asks:
        signals.add("money_transfer", note, "ai")
    if "fee_payment" in asks:
        signals.add("fee_request", note, "ai")
    if asks & {"install_app", "share_screen"}:
        signals.add("remote_app", note, "ai")
    pressure = set(ai.pressure)
    if "urgency" in pressure:
        signals.add("urgency", note, "ai")
    if "threat" in pressure:
        signals.add("threat", note, "ai")
    if ai.offer == "prize":
        signals.add("prize", note, "ai")
    elif ai.offer == "investment":
        signals.add("too_good", note, "ai")
    elif ai.offer == "job":
        signals.add("job_offer", note, "ai")
    elif ai.offer == "loan":
        signals.add("loan", note, "ai")
    elif ai.offer in ("refund", "cashback"):
        signals.add("refund", note, "ai")
    elif ai.offer == "government_payment":
        signals.add("claims_government", note, "ai")
    if ai.claimed_identity == "government":
        signals.add("claims_government", note, "ai")
    elif ai.claimed_identity in ("bank", "mobile_wallet"):
        signals.add("claims_bank", note, "ai")
    if ai.claimed_identity == "family_or_friend" and "money_transfer" in asks and "emotional_appeal" in pressure:
        signals.add("family_emergency", note, "ai")
    if ai.addresses_ai:
        signals.add("manipulation_attempt", note, "ai")
    signals.ai_claimed_identity = ai.claimed_identity
    signals.ai_summary = ai.summary
