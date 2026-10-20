"""The red-team set runs on every test run (rules only, no network)."""

from app.config import Settings
from eval.redteam import passed
from eval.run_eval import load, run_setup


async def test_red_team_set_passes():
    rows = load("redteam.jsonl")
    for r in rows:
        r["label"] = "legit" if r["expect"] == "no_red_flags" else "scam"
    result = await run_setup("rules", Settings(_env_file=None, llm_provider="none", embeddings_provider="local"), rows, True)
    expected = {r["id"]: r["expect"] for r in rows}
    failures = [(r["id"], r["verdict"]) for r in result["results"] if not passed(expected[r["id"]], r["verdict"])]
    assert failures == []
