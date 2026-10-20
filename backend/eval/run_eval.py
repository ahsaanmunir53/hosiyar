"""Evaluate the checker on labelled messages and write eval/results.md and eval/results.json.

    python -m eval.run_eval                       # rules only + rules with memory (no API calls)
    python -m eval.run_eval --with-ai --limit 20  # also the full AI pipeline on 20 test messages

The evaluation is isolated: it always uses a temporary SQLite file and in-memory agent memory,
never your DATABASE_URL, and network link checks are off so results are reproducible.

The AI run uses your free-tier quota (each message makes about 4-6 model calls, spread over the
models in the chain), so it only covers the held-out test set, waits between messages, waits for a
rate-limited model to recover, and reports which model answered and how many messages fell back to
rules because no model could answer.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import RULES_VERSION  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.state import Deps  # noqa: E402
from app.ai.llm import build_model_chains, check_models, model_label  # noqa: E402
from app.ai.model_status import describe, seconds_until_free  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core.aio import run  # noqa: E402
from app.db.session import init_db, make_engine, make_sessionmaker  # noqa: E402
from app.memory.embeddings import build_embeddings  # noqa: E402
from app.memory.store import seed_pattern_library  # noqa: E402

HERE = Path(__file__).resolve().parent
AI_FAILURES = {"ai_signals_failed", "investigator_failed"}
ISOLATED = {
    "database_url": None,
    "telegram_bot_token": None,
    "enable_network_checks": False,
    "seed_demo_data": False,
    "rate_limit_per_minute": 100_000,
}


async def run_setup(name: str, settings: Settings, rows: list[dict], with_memory: bool, pace: float = 0.0) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings.model_copy(update={**ISOLATED, "sqlite_path": os.path.join(tmp, "eval.db")})
        engine = make_engine(settings)
        await init_db(engine)
        embeddings, provider = build_embeddings(settings)
        store = InMemoryStore(index={"dims": settings.embedding_dims, "embed": embeddings, "fields": ["text"]})
        if with_memory:
            await seed_pattern_library(store, provider)
        models, agent_models = build_model_chains(settings)
        llm = models[0] if models else None
        deps = Deps(settings=settings, llm=llm, fallbacks=models[1:], agent_order=agent_models, store=store,
                    embed_provider=provider, sessionmaker=make_sessionmaker(engine), http=None)
        graph = build_graph(deps, InMemorySaver())
        results = []
        answered: Counter = Counter()
        for i, row in enumerate(rows):
            if pace and i:
                await asyncio.sleep(pace)
            wait = seconds_until_free(models)
            if wait:
                # Every model is resting after a rate limit; wait (up to 2 minutes) so the AI row is fair.
                print(f"  every model is rate-limited, waiting {min(wait, 120):.0f}s…", flush=True)
                await asyncio.sleep(min(wait, 120) + 1)
            state = await graph.ainvoke(
                {"mode": "analyze", "text": row["text"], "sender": row.get("sender"), "share": False, "channel": "eval",
                 "extra_signals": [], "file_info": None, "source_kind": "text"},
                {"configurable": {"thread_id": f"{name}-{i}"}},
            )
            results.append({
                "id": row["id"], "label": row["label"], "verdict": state["verdict"], "score": state["score"],
                "category": row.get("category"), "language": row.get("language"),
                "rules": [h["id"] for h in state["rule_hits"]],
                "ai_failed": bool(AI_FAILURES & set(state.get("degraded", []))),
            })
            if llm is not None:
                reader = next((t["detail"].get("model") for t in state.get("tool_trace", [])
                               if t.get("step") == "read_with_ai"), None) or "rules only"
                answered[reader] += 1
                print(f"  {name}: {i + 1}/{len(rows)} ({row['id']}: {state['verdict']}, read by {reader})", flush=True)
        await engine.dispose()
    label = model_label(settings) if llm else "none"
    if llm:
        label += f" · {provider} embeddings"
        print("  messages read by: " + ", ".join(f"{k} {v}" for k, v in answered.most_common()), flush=True)
        for m in models:
            d = describe(m)
            note = f" (resting: {d['status']})" if d["status"] != "ok" else ""
            print(f"  {d['model']}: {d['calls']} calls, {d['failures']} failed{note}", flush=True)
    return {"name": name, "model": label, "results": results, "read_by": dict(answered)}


def metrics(results: list[dict]) -> dict:
    def confusion(flag) -> dict:
        tp = sum(1 for r in results if r["label"] == "scam" and flag(r["verdict"]))
        fn = sum(1 for r in results if r["label"] == "scam" and not flag(r["verdict"]))
        fp = sum(1 for r in results if r["label"] == "legit" and flag(r["verdict"]))
        tn = sum(1 for r in results if r["label"] == "legit" and not flag(r["verdict"]))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        fpr = fp / (fp + tn) if fp + tn else 0.0
        return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "precision": precision, "recall": recall, "f1": f1, "fpr": fpr}

    return {
        "strict": confusion(lambda v: v == "likely_scam"),
        "flagged": confusion(lambda v: v in ("likely_scam", "suspicious")),
        "verdicts": {
            label: dict(Counter(r["verdict"] for r in results if r["label"] == label)) for label in ("scam", "legit")
        },
    }


def breakdown(results: list[dict], key: str) -> dict:
    """Share of scams caught (strict and flagged) per category or language."""
    out: dict[str, dict] = {}
    for r in results:
        if r["label"] != "scam":
            continue
        group = out.setdefault(r.get(key) or "unknown", {"n": 0, "caught": 0, "flagged": 0})
        group["n"] += 1
        group["caught"] += r["verdict"] == "likely_scam"
        group["flagged"] += r["verdict"] in ("likely_scam", "suspicious")
    return dict(sorted(out.items()))


def run_json(run_: dict) -> dict:
    res = run_["results"]
    m = metrics(res)
    return {
        "name": run_["name"],
        "model": run_["model"],
        **({"read_by": run_["read_by"]} if run_.get("read_by") else {}),
        "messages": len(res),
        "strict": {k: round(v, 4) if isinstance(v, float) else v for k, v in m["strict"].items()},
        "flagged": {k: round(v, 4) if isinstance(v, float) else v for k, v in m["flagged"].items()},
        "ai_failed": sum(r["ai_failed"] for r in res),
        "missed": [r["id"] for r in res if r["label"] == "scam" and r["verdict"] != "likely_scam"],
        "false_alarms": [r["id"] for r in res if r["label"] == "legit" and r["verdict"] != "no_red_flags"],
        "by_category": breakdown(res, "category"),
        "by_language": breakdown(res, "language"),
    }


def fmt(x: float) -> str:
    return f"{x * 100:.1f}%"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def balanced_sample(rows: list[dict], limit: int | None) -> list[dict]:
    """Take up to `limit` rows, alternating scam and legitimate messages, in file order."""
    if not limit or limit >= len(rows):
        return rows
    scams = [r for r in rows if r["label"] == "scam"]
    legit = [r for r in rows if r["label"] == "legit"]
    out: list[dict] = []
    while len(out) < limit and (scams or legit):
        if scams:
            out.append(scams.pop(0))
        if legit and len(out) < limit:
            out.append(legit.pop(0))
    return out


def table(title: str, rows: list[dict], runs: list[dict]) -> list[str]:
    n_scam = sum(r["label"] == "scam" for r in rows)
    n_legit = len(rows) - n_scam
    lines = [
        f"## {title}",
        "",
        f"{len(rows)} messages: {n_scam} scam, {n_legit} legitimate.",
        "",
        "| Set-up | Model | Messages | Strict precision | Strict recall | Strict F1 | Flagged recall | False alarms on legit |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run_ in runs:
        res = run_["results"]
        m = metrics(res)
        s, f = m["strict"], m["flagged"]
        legit_n = sum(r["label"] == "legit" for r in res)
        lines.append(
            f"| {run_['name']} | {run_['model']} | {len(res)} | {fmt(s['precision'])} | {fmt(s['recall'])} | "
            f"{fmt(s['f1'])} | {fmt(f['recall'])} | {f['fp']} of {legit_n} ({fmt(f['fpr'])}) |"
        )
    for run_ in runs:
        if run_.get("read_by"):
            lines += ["", f"Messages read by ({run_['name']}): "
                      + ", ".join(f"`{k}` {v}" for k, v in sorted(run_["read_by"].items(), key=lambda kv: -kv[1])) + "."]
    for run_ in runs:
        failed = sum(r["ai_failed"] for r in run_["results"])
        if failed:
            lines += ["", f"In **{run_['name']}**, a model call failed for {failed} message(s) (usually a free-tier "
                      "rate limit). Those messages were scored by the rules alone, so the AI row understates the "
                      "pipeline. Re-run later or with a larger `--pace`."]
    for run_ in runs:
        lines += ["", f"Misses and false alarms ({run_['name']}):", ""]
        issues = []
        for r in run_["results"]:
            if r["label"] == "scam" and r["verdict"] != "likely_scam":
                issues.append(f"- missed `{r['id']}` → {r['verdict']} ({r['score']}): {', '.join(r['rules']) or 'no rules'}")
            if r["label"] == "legit" and r["verdict"] != "no_red_flags":
                issues.append(f"- false alarm `{r['id']}` → {r['verdict']} ({r['score']}): {', '.join(r['rules'])}")
        lines += issues or ["- none"]
    return lines + [""]


async def main(args: argparse.Namespace) -> None:
    base = Settings(_env_file=None, llm_provider="none", embeddings_provider="local")
    rules_setups = [("rules only", base, False), ("rules + pattern memory", base, True)]

    test_rows, dev_rows = load("test.jsonl"), load("dev.jsonl")
    test_runs = [await run_setup(name, s, test_rows, mem) for name, s, mem in rules_setups]
    dev_runs = [await run_setup(name, s, dev_rows, mem) for name, s, mem in rules_setups]

    ai_runs: list[dict] = []
    ai_rows: list[dict] = []
    if args.with_ai:
        keyed = Settings()
        if keyed.resolved_llm_provider == "none":
            sys.exit("--with-ai needs GROQ_API_KEY or GOOGLE_API_KEY in .env")
        keyed = keyed.model_copy(update={"embeddings_provider": "gemini" if args.gemini_embeddings else "local"})
        for change in await check_models(keyed):
            print(f"Model check: {change}.", flush=True)
        ai_rows = balanced_sample(test_rows, args.limit)
        print(f"Running the AI pipeline on {len(ai_rows)} test messages, {args.pace:g}s apart…", flush=True)
        ai_runs.append(await run_setup("full (AI + memory)", keyed, ai_rows, True, pace=args.pace))

    lines = [
        "# Evaluation results",
        "",
        "Messages are in English, Urdu and Roman Urdu and reflect common Pakistani SMS and WhatsApp scams. "
        "Both sets were written by the project author, so treat the numbers as a sanity check, not a benchmark. "
        "Network link checks (domain age, short-link expansion, Safe Browsing) were off.",
        "",
        "- **Dev set** (`eval/dev.jsonl`) was used while writing and tuning the rules.",
        "- **Test set** (`eval/test.jsonl`) was written after the rules were frozen and was not used for tuning. "
        "Two changes were made after it was written: a bug fix (Urdu letters in patterns were not normalised the "
        "same way as the message text) and challan/PSID vocabulary added after a real user report. Later additions "
        "(red-team defences, file and email checks, overseas-job and cross-border names) left the test-set numbers "
        "unchanged. No weights were tuned to the test set, and its misses are listed below.",
        "",
        "*Strict* counts only `likely_scam` as a positive. *Flagged* also counts `suspicious`.",
        "",
    ]
    lines += table("Test set (held out)", test_rows, test_runs)
    if ai_runs:
        lines += table("Test set with the AI pipeline", ai_rows, ai_runs)
    lines += table("Dev set (used for tuning)", dev_rows, dev_runs)
    out = "\n".join(lines) + "\n"
    (HERE / "results.md").write_text(out, encoding="utf-8")

    def dataset(rows: list[dict], runs: list[dict]) -> dict:
        return {"messages": len(rows), "scam": sum(r["label"] == "scam" for r in rows),
                "legit": sum(r["label"] == "legit" for r in rows), "runs": [run_json(r) for r in runs]}

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rules_version": RULES_VERSION,
        "network_checks": False,
        "test": dataset(test_rows, test_runs),
        "dev": dataset(dev_rows, dev_runs),
    }
    if ai_runs:
        summary["test_ai"] = dataset(ai_rows, ai_runs)
    elif (HERE / "results.json").exists():
        # Keep the last AI run (it costs API quota) when re-running rules only.
        previous = json.loads((HERE / "results.json").read_text(encoding="utf-8")).get("test_ai")
        if previous:
            summary["test_ai"] = previous
    (HERE / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Hoshiyar on labelled messages")
    parser.add_argument("--with-ai", action="store_true", help="also run the full AI pipeline (uses API quota)")
    parser.add_argument("--limit", type=int, default=None, help="number of test messages for the AI run (balanced)")
    parser.add_argument("--pace", type=float, default=20.0, help="seconds to wait between messages in the AI run")
    parser.add_argument("--gemini-embeddings", action="store_true",
                        help="use Gemini embeddings in the AI run (default: local, to save quota)")
    run(main(parser.parse_args()))
