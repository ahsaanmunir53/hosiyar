"""Red-team set: messages written to fool the checker (prompt injection, disguised links,
look-alike letters, spaced-out keywords) plus controls that must stay clean.

    python -m eval.redteam            # rules only, no API calls; writes eval/redteam_results.json
    python -m eval.redteam --with-ai  # also through the AI pipeline (uses quota)
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import RULES_VERSION  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core.aio import run  # noqa: E402
from eval.run_eval import load, run_setup  # noqa: E402

HERE = Path(__file__).resolve().parent


def passed(expect: str, verdict: str) -> bool:
    if expect == "likely_scam":
        return verdict == "likely_scam"
    if expect == "flagged":
        return verdict in ("likely_scam", "suspicious")
    return verdict == "no_red_flags"


async def main(args: argparse.Namespace) -> None:
    rows = load("redteam.jsonl")
    for r in rows:
        r["label"] = "legit" if r["expect"] == "no_red_flags" else "scam"
    settings = Settings(_env_file=None, llm_provider="none", embeddings_provider="local")
    runs = [await run_setup("rules + pattern memory", settings, rows, True)]
    if args.with_ai:
        keyed = Settings().model_copy(update={"embeddings_provider": "local"})
        if keyed.resolved_llm_provider == "none":
            sys.exit("--with-ai needs GROQ_API_KEY or GOOGLE_API_KEY in .env")
        runs.append(await run_setup("full (AI + memory)", keyed, rows, True, pace=args.pace))
    by_id = {r["id"]: r for r in rows}
    report = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "rules_version": RULES_VERSION, "runs": []}
    for run_ in runs:
        cases = []
        for res in run_["results"]:
            row = by_id[res["id"]]
            cases.append({"id": res["id"], "attack": row["attack"], "expect": row["expect"], "verdict": res["verdict"],
                          "score": res["score"], "rules": res["rules"], "passed": passed(row["expect"], res["verdict"])})
        report["runs"].append({"name": run_["name"], "model": run_["model"], "passed": sum(c["passed"] for c in cases),
                               "total": len(cases), "cases": cases})
    (HERE / "redteam_results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for run_ in report["runs"]:
        print(f"{run_['name']}: {run_['passed']}/{run_['total']} passed")
        for c in run_["cases"]:
            mark = "ok  " if c["passed"] else "FAIL"
            print(f"  {mark} {c['id']} {c['attack']}: expected {c['expect']}, got {c['verdict']} ({c['score']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the red-team set")
    parser.add_argument("--with-ai", action="store_true")
    parser.add_argument("--pace", type=float, default=20.0)
    run(main(parser.parse_args()))
