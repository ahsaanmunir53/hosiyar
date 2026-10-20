"""Model chain, the start-up model check and parking of failing models."""

import json
import warnings

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.ai import model_status
from app.ai.llm import (
    build_model_chains,
    check_models,
    gemini_chat,
    groq_chat,
    model_label,
    pick_gemini,
)
from app.ai.signals import AISignals
from app.config import Settings
from tests.fakes import FakeLLM
from tests.test_graph import analyze, make_graph  # noqa: F401  (fixture)


class NotFoundError(Exception):
    status_code = 404


class RateLimitError(Exception):
    status_code = 429


def keyed(**extra) -> Settings:
    return Settings(_env_file=None, app_env="test", groq_api_key="gsk_test", google_api_key="g_test", **extra)


# --------------------------------------------------------------------------- classify

@pytest.mark.parametrize(("exc", "kind", "low", "high"), [
    (NotFoundError("The model `llama-3.3-70b-versatile` does not exist or you do not have access to it."), "retired", 3600, None),
    (RuntimeError("Error code: 400 - model has been decommissioned"), "retired", 3600, None),
    (RuntimeError("Error calling model 'gemini-3.5-flash-lite' (RESOURCE_EXHAUSTED): 429. Please retry in 52.1s."),
     "rate_limited", 52, 53),
    (RateLimitError("Rate limit reached on tokens per minute (TPM). Please try again in 3m25.6s."), "rate_limited", 205, 206),
    (RuntimeError("429 {'retryDelay': '17s'}"), "rate_limited", 17, 17),
    (RuntimeError("Error code: 401 - Invalid API Key"), "bad_key", 3600, None),
    (RuntimeError("Error code: 400 - tool_use_failed"), "request", 0, 0),
])
def test_errors_are_classified(exc, kind, low, high):
    got, seconds = model_status.classify(exc)
    assert got == kind
    assert seconds >= low
    if high is not None:
        assert seconds <= high


def test_a_retired_model_is_parked_and_a_success_frees_it():
    a, b = FakeLLM(model_name="a"), FakeLLM(model_name="b")
    model_status.note_failure(a, NotFoundError("model_not_found"))
    assert model_status.usable([a, b]) == [b]
    assert model_status.describe(a)["status"] == "retired"
    assert "hint" in model_status.describe(a) and "hint" not in model_status.describe(a, detail=False)
    model_status.note_success(a)
    assert model_status.usable([a, b]) == [a, b]


def test_one_timeout_is_tolerated_two_park_the_model():
    a = FakeLLM(model_name="a")
    model_status.note_failure(a, TimeoutError())
    assert model_status.usable([a]) == [a]
    model_status.note_failure(a, TimeoutError())
    assert model_status.usable([a]) == []
    assert 0 < model_status.seconds_until_free([a]) <= model_status.TRANSIENT_PARK


def test_a_bad_request_does_not_park_the_model():
    a = FakeLLM(model_name="a")
    for _ in range(3):
        model_status.note_failure(a, RuntimeError("Error code: 400 - tool_use_failed"))
    assert model_status.usable([a]) == [a]


# --------------------------------------------------------------------------- the chain

def test_chain_order_spreads_the_quota():
    s = keyed()
    models, agent = build_model_chains(s)
    names = [model_status.model_key(m) for m in models]
    assert names == ["groq:openai/gpt-oss-120b", "gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b"]
    assert model_status.model_key(agent[0]) == "groq:openai/gpt-oss-20b"
    assert {id(m) for m in agent} == {id(m) for m in models}
    assert model_label(s) == "groq/openai/gpt-oss-120b → gemini/gemini-3.5-flash-lite → groq/openai/gpt-oss-20b"


def test_chain_without_the_fast_model_or_with_one_key():
    models, agent = build_model_chains(keyed(groq_fast_model=""))
    assert len(models) == 2 and agent == models
    only_gemini = Settings(_env_file=None, app_env="test", google_api_key="g_test")
    assert model_label(only_gemini) == "gemini/gemini-3.5-flash-lite"


def test_model_settings_per_family():
    s = keyed()
    assert groq_chat(s, "openai/gpt-oss-120b").reasoning_effort == "low"
    assert groq_chat(s, "qwen/qwen3.8-27b").reasoning_format == "parsed"
    assert groq_chat(s, "llama-3.1-8b-instant").reasoning_effort is None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        g3 = gemini_chat(s, "gemini-3.5-flash-lite")
    assert g3.temperature is None  # Gemini 3 keeps its fixed sampling, so no warning per call
    assert gemini_chat(s, "gemini-2.5-flash").temperature == 0


# --------------------------------------------------------------------------- start-up check

def fake_api(groq_ids, gemini_names, unusable=(), calls=None):
    calls = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.host == "api.groq.com" and request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": i, "active": True} for i in groq_ids]})
        if request.url.host == "api.groq.com" and request.url.path.endswith("/chat/completions"):
            model = json.loads(request.content)["model"]
            if model in unusable:
                return httpx.Response(404, json={"error": {"code": "model_not_found"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        if request.url.host == "generativelanguage.googleapis.com":
            assert "key=" not in str(request.url)  # the key goes in a header, never the URL
            return httpx.Response(200, json={"models": [
                {"name": f"models/{n}", "supportedGenerationMethods": ["embedContent" if "embedding" in n else "generateContent"]}
                for n in gemini_names]})
        return httpx.Response(500)

    return httpx.MockTransport(handler), calls


async def test_a_retired_configured_model_is_replaced_at_start_up():
    s = keyed(groq_model="llama-3.3-70b-versatile", gemini_model="gemini-2.0-flash-lite",
              gemini_vision_model="gemini-3.5-flash-lite")
    transport, _ = fake_api(
        ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "whisper-large-v3"],
        ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash-lite-preview", "gemini-embedding-001"],
    )
    changes = await check_models(s, transport=transport)
    assert s.groq_model == "openai/gpt-oss-120b"
    assert s.groq_fast_model == "openai/gpt-oss-20b"
    assert s.gemini_model == "gemini-3.5-flash-lite"
    assert s.gemini_vision_model == "gemini-3.5-flash-lite"
    assert len(changes) == 2 and "llama-3.3-70b-versatile" in changes[0]


async def test_a_listed_model_the_key_cannot_use_is_skipped():
    s = keyed()
    transport, _ = fake_api(["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"], ["gemini-3.5-flash-lite"],
                            unusable={"openai/gpt-oss-120b"})
    await check_models(s, transport=transport)
    assert s.groq_model == "qwen/qwen3.8-27b"
    assert s.groq_fast_model == "openai/gpt-oss-20b"


async def test_working_models_are_kept_with_one_probe_each():
    s = keyed()
    transport, calls = fake_api(["openai/gpt-oss-120b", "openai/gpt-oss-20b"], ["gemini-3.5-flash-lite"])
    assert await check_models(s, transport=transport) == []
    assert sum(path.endswith("/chat/completions") for _, path in calls) == 2


async def test_network_trouble_keeps_the_settings():
    s = keyed(groq_model="llama-3.3-70b-versatile")

    def boom(request):
        raise httpx.ConnectError("offline")

    assert await check_models(s, transport=httpx.MockTransport(boom)) == []
    assert s.groq_model == "llama-3.3-70b-versatile"


async def test_check_is_skipped_without_keys_or_when_switched_off():
    assert await check_models(Settings(_env_file=None, app_env="test")) == []
    assert await check_models(keyed(model_autoselect=False)) == []


def test_pick_gemini_prefers_stable_flash_lite():
    available = ["gemini-3.6-flash", "gemini-3.7-flash-lite-preview", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"]
    assert pick_gemini("gemini-1.5-flash", available) == "gemini-3.5-flash-lite"
    assert pick_gemini("gemini-3.6-flash", available) == "gemini-3.6-flash"
    assert pick_gemini("x", []) is None


# --------------------------------------------------------------------------- in the pipeline

async def test_a_retired_model_is_tried_once_then_skipped(make_graph):  # noqa: F811
    retired = FakeLLM(error=NotFoundError("model_not_found"), model_name="retired-model")
    backup = FakeLLM(signals=AISignals(claimed_identity="bank", asks_for=["otp_or_pin"], summary="Asks for an OTP."),
                     model_name="backup-model")
    graph, _ = make_graph(retired, fallbacks=[backup])
    first = await analyze(graph, "HBL: share the OTP you received to keep your account active", thread="a")
    calls_after_first = retired.structured_calls + retired.plain_calls
    assert retired.structured_calls == 1
    second = await analyze(graph, "HBL: share the OTP you received to keep your account active", thread="b")
    assert retired.structured_calls + retired.plain_calls == calls_after_first
    for state in (first, second):
        read = next(t for t in state["tool_trace"] if t["step"] == "read_with_ai")
        assert read["detail"]["model"] == "backup-model"
        assert state["model"] == "backup-model"
        assert state["explanation"]["source"] == "ai"


async def test_when_every_model_rests_the_rules_answer_at_once(make_graph):  # noqa: F811
    a, b = FakeLLM(model_name="a"), FakeLLM(model_name="b")
    for m in (a, b):
        model_status.note_failure(m, RateLimitError("Please try again in 30s"))
    graph, _ = make_graph(a, fallbacks=[b])
    state = await analyze(graph, "Maine galti se aap ko code bhej diya, wapas bhej dein")
    assert a.structured_calls == b.structured_calls == 0
    assert "ai_signals_failed" in state["degraded"]
    assert state["verdict"] == "likely_scam"
    read = next(t for t in state["tool_trace"] if t["step"] == "read_with_ai")
    assert "resting" in read["detail"]["errors"][0]


async def test_agents_try_the_fast_model_first_and_memory_agent_stops_after_two_rounds(make_graph):  # noqa: F811
    search = lambda: AIMessage(content="", tool_calls=[  # noqa: E731
        {"name": "search_similar_reports", "args": {"description": "code returned by mistake"}, "id": "c1"}])
    main = FakeLLM(model_name="main")
    fast = FakeLLM(model_name="fast", tool_plans={"search_similar_reports": [search(), search(), search()]})
    graph, _ = make_graph(main, fallbacks=[fast])
    graph.deps.agent_order = [fast, main]
    state = await analyze(graph, "Maine galti se aap ko code bhej diya, wapas bhej dein")
    assert main.bound_tool_names == []
    assert fast.bound_tool_names.count("search_similar_reports") == 2
    runs = [t for t in state["tool_trace"] if t["step"] == "search_similar_reports" and t["by"] == "agent"]
    assert len(runs) == 2
