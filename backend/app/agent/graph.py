"""The LangGraph pipeline: a small team of agents around a fixed rule book.

    START ─┬─ followup ───────────────────────────────────────────────────────────────► END
           └─ prepare ─► read_with_ai ─► plan ─┬─► link_agent ───┐
                                               ├─► memory_agent ─┤
                                               └─────────────────┴─► gather ─► assess ─► explain ─► persist ─► END

* prepare       redacts personal data, finds links (also disguised ones) and pattern signals
* read_with_ai  the model describes the message as structured data (cached per redacted text)
* plan          a rules-based planner picks which specialists to run
* link_agent    LLM specialist with a check_link tool (manual tool loop, runs in parallel)
* memory_agent  LLM specialist with a search_similar_reports tool (runs in parallel)
* gather        the guard: checks every link and searches memory if a specialist skipped it or
                failed, then looks up the watchlist and reported numbers/accounts in the database
* assess        the rule book turns everything into a score and verdict
* explain       plain-language explanation (model or template) and next steps
* persist       audit log, shared report (review queue), family alert, user memory
"""

import asyncio
import json
import logging
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from app import RULES_VERSION
from app.agent.explain import ai_explanation, ai_followup, canned_answer, template_explanation
from app.agent.state import AnalysisState, Deps, signals_from_dict, signals_to_dict
from app.ai.llm import model_label, text_of
from app.ai.model_status import note_failure, note_success, usable
from app.ai.prompts import LINK_AGENT_SYSTEM, MEMORY_AGENT_SYSTEM
from app.ai.signals import AISignals, extract_ai_signals, merge_ai_signals, model_name, short_error
from app.core.redaction import RedactionResult, redact, sender_kind
from app.core.text import detect_language_request, detect_source_language, reply_language_for
from app.core.urls import extract_urls, split_url
from app.db.models import Analysis
from app.guidance.next_steps import next_steps
from app.intel import cache as ai_cache
from app.intel import family
from app.intel.indicators import reported_count, watchlist_hits
from app.intel.reports import submit_report
from app.memory import store as memory
from app.rules.catalog import EvalContext
from app.rules.engine import assess, render_hit
from app.rules.signals import detect_signals
from app.tools.links import check_links

log = logging.getLogger(__name__)
MAX_CALLS_PER_ROUND = 4


# Tool schemas the specialists see. They are executed by the specialist loop below, which
# adds the safety checks (only links from the message, bounded output).
@tool
def check_link(url: str) -> str:
    """Inspect one link from the message: look-alike domains, shorteners, domain age and Google Safe Browsing."""
    return ""


@tool
def search_similar_reports(description: str) -> str:
    """Search known scam messages for ones similar to a short English description of the scam pattern."""
    return ""


def build_graph(deps: Deps, checkpointer=None):
    settings = deps.settings

    # ---------------------------------------------------------------- tool bodies
    async def run_check_link(args: dict, state: AnalysisState) -> dict:
        allowed = {split_url(u)["host"]: u for u in state.get("urls", [])}
        host = split_url(str(args.get("url", "")))["host"]
        if host not in allowed:
            return {"error": "Only links that appear in the message can be checked."}
        return {"link_report": (await check_links([allowed[host]], settings, deps.http))[0]}

    async def run_search(args: dict, state: AnalysisState) -> dict:
        query = f"{str(args.get('description', ''))[:300]}\n{state.get('redacted_text', '')[:600]}"
        return {"matches": await memory.search_similar(deps.store, deps.embed_provider, query, settings.similarity_threshold)}

    async def specialist(name: str, system: str, brief: str, schema, body, state: AnalysisState,
                         rounds: int | None = None) -> dict:
        """A manual tool loop: ask the model, run the tools it calls, feed results back, repeat."""
        messages = [SystemMessage(system), HumanMessage(brief)]
        out: dict = {"trace": [], "results": [], "failed": False, "summary": None, "model": None, "errors": []}
        for _ in range(rounds or settings.agent_max_tool_rounds):
            reply = None
            candidates = usable(deps.agent_models)
            if not candidates:
                out["errors"].append("every model is resting after errors or rate limits")
            for model in candidates:
                try:
                    reply = await asyncio.wait_for(model.bind_tools([schema]).ainvoke(messages), settings.llm_timeout_seconds)
                    note_success(model)
                    out["model"] = model_name(model)
                    break
                except Exception as exc:
                    note_failure(model, exc)
                    out["errors"].append(f"{model_name(model)}: {short_error(exc)}")
                    log.warning("%s failed on %s", name, out["errors"][-1])
            if reply is None:
                out["failed"] = True
                break
            messages.append(reply)
            calls = list(getattr(reply, "tool_calls", None) or [])[:MAX_CALLS_PER_ROUND]
            if not calls:
                out["summary"] = text_of(reply).strip()[:300] or None
                break
            for call in calls:
                if call.get("name") != schema.name:
                    result = {"error": f"Unknown tool {call.get('name')}."}
                else:
                    try:
                        result = await body(call.get("args") or {}, state)
                    except Exception as exc:
                        result = {"error": short_error(exc)}
                out["results"].append(result)
                out["trace"].append({"step": schema.name, "by": "agent", "detail": {
                    "agent": name, "args": call.get("args") or {}, "ok": "error" not in result}})
                messages.append(ToolMessage(content=json.dumps(result)[:6000], tool_call_id=call.get("id") or str(uuid.uuid4()),
                                            name=schema.name))
        return out

    # ---------------------------------------------------------------- nodes
    async def prepare(state: AnalysisState) -> dict:
        full_text = state.get("text") or ""
        text = full_text[: settings.max_text_chars]
        profile = await memory.get_user_profile(deps.store, state.get("user_hash"))
        asked = detect_language_request(text)
        if asked:
            profile = await memory.update_user_profile(deps.store, state.get("user_hash"), language=asked)
        source_language = detect_source_language(text)
        language = state.get("requested_language") or asked or profile.get("language") or reply_language_for(source_language)
        if state.get("pre_redacted"):
            # Already redacted by the API layer; the raw text never entered the graph.
            red = RedactionResult(text=text, counts=dict(state.get("redactions") or {}),
                                  phone_fingerprints=list(state.get("phone_fingerprints") or []),
                                  account_fingerprints=list(state.get("account_fingerprints") or []))
        else:
            red = redact(text, settings.fingerprint_secret)
        signals = detect_signals(red.text)
        for item in state.get("extra_signals") or []:
            signals.add(item["name"], item.get("evidence", ""), "file-check")
        urls = extract_urls(full_text)
        return {
            "analysis_id": state.get("analysis_id_hint") or str(uuid.uuid4()),
            "started_at": time.time(),
            "text": text,
            "language": language if language in ("en", "ur", "roman") else "en",
            "source_language": source_language,
            "redacted_text": red.text,
            "redactions": red.counts,
            "phone_fingerprints": red.phone_fingerprints,
            "account_fingerprints": red.account_fingerprints,
            "urls": urls,
            "signals": signals_to_dict(signals),
            "ai_summary": None,
            "plan": [],
            "link_agent_out": {},
            "memory_agent_out": {},
            "link_reports": [],
            "memory_matches": [],
            "reported_number_count": 0,
            "reported_account_count": 0,
            "watchlist": [],
            "tool_trace": [{"step": "prepare", "by": "rules", "detail": {
                "redacted": red.counts, "links": len(urls), "pattern_signals": sorted(signals.signals),
                "source_language": source_language}}],
            "degraded": [],
            "model": model_label(settings),
            "followups": [],
            "answer": None,
            "report_status": None,
        }

    async def read_with_ai(state: AnalysisState) -> dict:
        if not deps.models:
            return {"degraded": state.get("degraded", []) + ["ai_off"]}
        errors: list[str] = []
        ai, used, cached = None, None, False
        key = ai_cache.cache_key("signals", model_label(settings), state["redacted_text"])
        if settings.ai_cache:
            try:
                hit = await ai_cache.get(deps.sessionmaker, key, settings.ai_cache_days)
                if hit:
                    ai, used, cached = AISignals.model_validate(hit["signals"]), hit.get("model"), True
            except Exception as exc:
                log.info("AI cache read failed: %s", type(exc).__name__)
        if ai is None:
            candidates = usable(deps.models)
            if not candidates:
                errors.append("every model is resting after errors or rate limits")
            for model in candidates:
                try:
                    ai = await extract_ai_signals(model, state["redacted_text"], settings.llm_timeout_seconds)
                    note_success(model)
                    used = model_name(model)
                    break
                except Exception as exc:
                    note_failure(model, exc)
                    errors.append(f"{model_name(model)}: {short_error(exc)}")
                    log.warning("AI signals failed on %s", errors[-1])
            if ai is not None and settings.ai_cache:
                try:
                    await ai_cache.put(deps.sessionmaker, key, "signals", used or "", {"signals": ai.model_dump(), "model": used})
                except Exception as exc:
                    log.info("AI cache write failed: %s", type(exc).__name__)
        if ai is None:
            trace = state.get("tool_trace", []) + [{"step": "read_with_ai", "by": "ai", "detail": {"errors": errors}}]
            return {"degraded": state.get("degraded", []) + ["ai_signals_failed"], "tool_trace": trace, "model": "none"}
        signals = signals_from_dict(state["signals"])
        before = set(signals.signals)
        merge_ai_signals(signals, ai)
        trace = state.get("tool_trace", []) + [{"step": "read_with_ai", "by": "ai", "detail": {
            "summary": ai.summary, "claimed_identity": ai.claimed_identity, "model": used, "cached": cached,
            "errors": errors, "new_signals": sorted(set(signals.signals) - before)}}]
        # The model that actually read this message (the chain label is longer and says less).
        return {"signals": signals_to_dict(signals), "ai_summary": ai.summary, "tool_trace": trace,
                "model": (used or model_label(settings))[:64]}

    async def plan(state: AnalysisState) -> dict:
        """Rules-based planner. The specialists only run when a model is available and working."""
        chosen: list[str] = []
        why = "rules only"
        if not deps.models:
            why = "no AI model configured"
        elif not settings.agent_investigator:
            why = "agents switched off"
        elif "ai_signals_failed" in state.get("degraded", []):
            why = "AI unavailable, the guard covers everything"
        elif not usable(deps.agent_models):
            why = "every model is resting, the guard covers everything"
        else:
            if state.get("urls"):
                chosen.append("link_agent")
            chosen.append("memory_agent")
            why = f"{len(state.get('urls', []))} link(s) to inspect" if state.get("urls") else "no links; search memory"
        trace = state.get("tool_trace", []) + [{"step": "plan", "by": "rules", "detail": {"specialists": chosen, "why": why}}]
        return {"plan": chosen, "tool_trace": trace}

    def route_plan(state: AnalysisState) -> list[str]:
        return state.get("plan") or ["gather"]

    def _brief(state: AnalysisState) -> str:
        sig = signals_from_dict(state["signals"])
        return (
            f"Message (personal details removed):\n\"\"\"\n{state['redacted_text'][:2000]}\n\"\"\"\n\n"
            f"Links in the message: {json.dumps(state.get('urls', []))}\n"
            f"Signals found by rules: {', '.join(sorted(sig.signals)) or 'none'}\n"
            f"Claimed organisations: {', '.join(b.name for b in sig.brands) or 'none'}"
        )

    async def link_agent(state: AnalysisState) -> dict:
        return {"link_agent_out": await specialist("link_agent", LINK_AGENT_SYSTEM, _brief(state), check_link, run_check_link, state)}

    async def memory_agent(state: AnalysisState) -> dict:
        return {"memory_agent_out": await specialist(
            "memory_agent", MEMORY_AGENT_SYSTEM, _brief(state), search_similar_reports, run_search, state,
            rounds=min(2, settings.agent_max_tool_rounds))}

    async def gather(state: AnalysisState) -> dict:
        reports: dict[str, dict] = {}
        matches: dict[str, dict] = {}
        trace = list(state.get("tool_trace", []))
        degraded = list(state.get("degraded", []))
        searched = False
        for key in ("link_agent_out", "memory_agent_out"):
            out = state.get(key) or {}
            trace += out.get("trace", [])
            if out.get("failed"):
                degraded.append(f"{key.removesuffix('_out')}_failed")
            if out.get("summary") or out.get("errors"):
                trace.append({"step": key.removesuffix("_out"), "by": "agent", "detail": {
                    "summary": out.get("summary"), "model": out.get("model"), "errors": out.get("errors", [])}})
            for result in out.get("results", []):
                if "link_report" in result:
                    reports[result["link_report"]["url"]] = result["link_report"]
                if "matches" in result:
                    searched = True
                    for m in result["matches"]:
                        matches[m["key"]] = m

        missing = [u for u in state.get("urls", []) if u not in reports]
        if missing:
            for rep in await check_links(missing, settings, deps.http):
                reports[rep["url"]] = rep
            trace.append({"step": "check_link", "by": "guard", "detail": {"urls": missing}})
        if not searched:
            for m in await memory.search_similar(deps.store, deps.embed_provider, state["redacted_text"], settings.similarity_threshold):
                matches[m["key"]] = m
            trace.append({"step": "search_similar_reports", "by": "guard", "detail": {"found": len(matches)}})

        ordered = [reports[u] for u in state.get("urls", []) if u in reports]
        domains = sorted({(r.get("final_registered_domain") or r.get("registered_domain") or "").lower() for r in ordered} - {""})
        numbers = accounts = 0
        watch: list[dict] = []
        try:
            async with deps.sessionmaker() as session:
                numbers = await reported_count(session, "phone_fp", state.get("phone_fingerprints", []), settings.min_independent_reporters)
                accounts = await reported_count(session, "account_fp", state.get("account_fingerprints", []), settings.min_independent_reporters)
                watch = await watchlist_hits(session, domains, state.get("phone_fingerprints", []), state.get("account_fingerprints", []))
        except Exception as exc:
            log.warning("indicator lookup failed: %s", type(exc).__name__)
        if state.get("phone_fingerprints") or state.get("account_fingerprints") or domains:
            trace.append({"step": "lookup_indicators", "by": "guard", "detail": {
                "reported_numbers": numbers, "reported_accounts": accounts, "watchlist": len(watch)}})
        return {
            "link_reports": ordered,
            "memory_matches": sorted(matches.values(), key=lambda m: -m["similarity"])[:5],
            "reported_number_count": numbers,
            "reported_account_count": accounts,
            "watchlist": watch,
            "tool_trace": trace,
            "degraded": degraded,
        }

    async def assess_node(state: AnalysisState) -> dict:
        ctx = EvalContext(
            signals=signals_from_dict(state["signals"]),
            links=state.get("link_reports", []),
            memory_matches=state.get("memory_matches", []),
            sender=state.get("sender"),
            sender_kind=state.get("sender_kind") or sender_kind(state.get("sender")),
            reported_number_count=state.get("reported_number_count", 0),
            reported_account_count=state.get("reported_account_count", 0),
            watchlist_hits=state.get("watchlist", []),
        )
        result = assess(ctx)
        hits = [render_hit(h) for h in result.hits]
        trace = state.get("tool_trace", []) + [{"step": "assess", "by": "rules", "detail": {
            "score": result.score, "verdict": result.verdict, "rules": [h.id for h in result.hits]}}]
        return {"rule_hits": hits, "score": result.score, "verdict": result.verdict, "category": result.category, "tool_trace": trace}

    async def explain(state: AnalysisState) -> dict:
        language = state["language"]
        templates = template_explanation(state["verdict"], state["rule_hits"])
        explanation = {"language": language, "text": templates[language], "source": "template", "templates": templates}
        if deps.models and "ai_signals_failed" not in state.get("degraded", []):
            for model in usable(deps.models):
                text = await ai_explanation(model, dict(state), language, settings.llm_timeout_seconds)
                if text:
                    explanation.update(text=text, source="ai")
                    break
        sig = signals_from_dict(state["signals"])
        flagged = state["verdict"] != "no_red_flags"
        tags: set[str] = set()
        if flagged and sig.has("challan"):
            tags.add("challan")
        if flagged and sig.has("job_offer") and (sig.has("overseas") or sig.has("passport_request")):
            tags.add("overseas_job")
        if flagged and (sig.has("risky_attachment") or sig.has("pdf_active_content")):
            tags.add("risky_file")
        if flagged and state.get("source_kind") == "email":
            tags.add("email")
        steps = next_steps(state["verdict"], state["category"], {b.key for b in sig.brands}, tags)
        return {"explanation": explanation, "next_steps": steps}

    async def persist(state: AnalysisState) -> dict:
        share = bool(state.get("share")) and state["verdict"] != "no_red_flags"
        sig = signals_from_dict(state["signals"])
        domains = sorted({r.get("final_registered_domain") or r.get("registered_domain") or "" for r in state.get("link_reports", [])} - {""})
        report_status = None
        if share:
            try:
                report = await submit_report(deps, dict(state))
                report_status = report.status
            except Exception:
                log.exception("could not store the shared report")
                share = False
        await memory.record_user_check(deps.store, state.get("user_hash"), state["verdict"])
        async with deps.sessionmaker() as session:
            session.add(Analysis(
                id=state["analysis_id"],
                channel=state.get("channel", "web"),
                user_hash=state.get("user_hash"),
                verdict=state["verdict"],
                score=state["score"],
                category=state["category"],
                language=state["language"],
                rule_ids=[h["id"] for h in state["rule_hits"]],
                hard_rule_ids=[h["id"] for h in state["rule_hits"] if h["hard"]],
                brands=[b.key for b in sig.brands],
                link_domains=domains,
                memory_matches=len(state.get("memory_matches", [])),
                llm_model=(state.get("model") or "none")[:64],
                rules_version=RULES_VERSION,
                degraded=state.get("degraded", []),
                tool_calls=[t["step"] for t in state.get("tool_trace", []) if t.get("by") in ("agent", "guard")],
                shared=share,
                excerpt=state["redacted_text"][:280] if share else None,
                latency_ms=int((time.time() - state.get("started_at", time.time())) * 1000),
            ))
            await session.commit()
        if state["verdict"] == "likely_scam" and state.get("user_hash") and settings.telegram_bot_token:
            try:
                await family.alert_guardians(deps.sessionmaker, deps.http, settings.telegram_bot_token,
                                             state.get("user_hash"), state["category"], settings.public_app_url)
            except Exception as exc:
                log.warning("family alert failed: %s", type(exc).__name__)
        return {"share": share, "report_status": report_status}

    async def followup(state: AnalysisState) -> dict:
        question = (state.get("question") or "").strip()[:500]
        asked = detect_language_request(question)
        if asked:
            await memory.update_user_profile(deps.store, state.get("user_hash"), language=asked)
        language = state.get("requested_language") or asked or state.get("language") or reply_language_for(detect_source_language(question))
        language = language if language in ("en", "ur", "roman") else "en"
        answer_text, source = None, "template"
        if deps.models and state.get("verdict"):
            for model in usable(deps.models):
                answer_text = await ai_followup(model, dict(state), question, language, settings.llm_timeout_seconds)
                if answer_text:
                    source = "ai"
                    break
        if not answer_text:
            answer_text = canned_answer(dict(state), question, language)
        answer = {"question": question, "answer": answer_text, "language": language, "source": source}
        return {"answer": answer, "followups": state.get("followups", []) + [answer]}

    def route_start(state: AnalysisState) -> str:
        return "followup" if state.get("mode") == "followup" else "prepare"

    g = StateGraph(AnalysisState)
    for name, fn in (("prepare", prepare), ("read_with_ai", read_with_ai), ("plan", plan), ("link_agent", link_agent),
                     ("memory_agent", memory_agent), ("gather", gather), ("assess", assess_node), ("explain", explain),
                     ("persist", persist), ("followup", followup)):
        g.add_node(name, fn)
    g.add_conditional_edges(START, route_start, {"followup": "followup", "prepare": "prepare"})
    g.add_edge("prepare", "read_with_ai")
    g.add_edge("read_with_ai", "plan")
    g.add_conditional_edges("plan", route_plan, ["link_agent", "memory_agent", "gather"])
    g.add_edge("link_agent", "gather")
    g.add_edge("memory_agent", "gather")
    g.add_edge("gather", "assess")
    g.add_edge("assess", "explain")
    g.add_edge("explain", "persist")
    g.add_edge("persist", END)
    g.add_edge("followup", END)
    compiled = g.compile(checkpointer=checkpointer, store=deps.store)
    compiled.deps = deps  # lets the API layer redact inputs before they enter the graph
    return compiled
