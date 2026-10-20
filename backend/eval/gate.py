"""Quality gate for CI: compare eval/results.json and eval/redteam_results.json with
eval/thresholds.json and exit with an error if any number got worse.

    python -m eval.run_eval && python -m eval.redteam && python -m eval.gate
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check() -> list[str]:
    limits = json.loads((HERE / "thresholds.json").read_text(encoding="utf-8"))
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    for name in ("test", "dev"):
        lim = limits[name]
        run = next((r for r in results[name]["runs"] if r["name"] == lim["run"]), None)
        if run is None:
            problems.append(f"{name}: run '{lim['run']}' is missing")
            continue
        checks = [
            ("strict precision", run["strict"]["precision"], lim["min_strict_precision"], ">="),
            ("strict recall", run["strict"]["recall"], lim["min_strict_recall"], ">="),
            ("flagged recall", run["flagged"]["recall"], lim["min_flagged_recall"], ">="),
            ("false alarms", run["flagged"]["fp"], lim["max_false_alarms"], "<="),
        ]
        for label, value, bound, op in checks:
            ok = value >= bound if op == ">=" else value <= bound
            print(f"{'ok  ' if ok else 'FAIL'} {name} {label}: {value} (needs {op} {bound})")
            if not ok:
                problems.append(f"{name} {label} is {value}, needs {op} {bound}")
    red_path = HERE / "redteam_results.json"
    if red_path.exists():
        red = json.loads(red_path.read_text(encoding="utf-8"))
        lim = limits["redteam"]
        run = next((r for r in red["runs"] if r["name"] == lim["run"]), None)
        if run:
            rate = run["passed"] / run["total"] if run["total"] else 0
            ok = rate >= lim["min_pass_rate"]
            print(f"{'ok  ' if ok else 'FAIL'} red team pass rate: {run['passed']}/{run['total']} (needs >= {lim['min_pass_rate']:.0%})")
            if not ok:
                failed = [c["id"] for c in run["cases"] if not c["passed"]]
                problems.append(f"red team failed: {', '.join(failed)}")
    else:
        problems.append("eval/redteam_results.json is missing; run python -m eval.redteam")
    return problems


if __name__ == "__main__":
    issues = check()
    if issues:
        print("\nQuality gate failed:\n- " + "\n- ".join(issues))
        sys.exit(1)
    print("\nQuality gate passed.")
