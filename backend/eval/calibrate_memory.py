"""Print similarity scores between the eval messages and the pattern library.

Use it to choose SIMILARITY_THRESHOLD_LOCAL / SIMILARITY_THRESHOLD_GEMINI for the embedder
you run: pick a value that most scam messages reach and legitimate ones do not.

    python -m eval.calibrate_memory            # embedder chosen by .env (Gemini if GOOGLE_API_KEY is set)
    python -m eval.calibrate_memory --local    # free local embedder, no API calls

Gemini's free tier allows about 100 embeddings a minute, so with Gemini this script sends
small batches and waits between them. It takes about four minutes.
"""

import argparse
import json
import math
import time
from pathlib import Path

from app.config import Settings
from app.core.redaction import redact
from app.memory.embeddings import build_embeddings

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "pattern_library.jsonl"
BATCH = 45
WAIT = 62


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def embed_paced(emb, texts: list[str], paced: bool) -> list[list[float]]:
    if not paced:
        return emb.embed_documents(texts)
    out: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        chunk = texts[start:start + BATCH]
        for attempt in range(3):
            try:
                out += emb.embed_documents(chunk)
                break
            except Exception as exc:  # free-tier rate limit: wait and retry
                if "RESOURCE_EXHAUSTED" not in str(exc) and "429" not in str(exc) or attempt == 2:
                    raise
                print(f"  rate limited, waiting {WAIT}s…", flush=True)
                time.sleep(WAIT)
        print(f"  embedded {min(start + BATCH, len(texts))}/{len(texts)}", flush=True)
        if start + BATCH < len(texts):
            time.sleep(WAIT)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="use the free local embedder")
    args = parser.parse_args()

    settings = Settings()
    if args.local:
        settings = settings.model_copy(update={"embeddings_provider": "local"})
    emb, provider = build_embeddings(settings)
    paced = provider.startswith("gemini")
    library = [json.loads(line)["text"] for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [json.loads(line) for name in ("dev.jsonl", "test.jsonl")
            for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [redact(r["text"], "x").text for r in rows]

    print(f"Embedder: {provider} ({len(library) + len(texts)} texts)")
    vectors = embed_paced(emb, library + texts, paced)
    lib_vecs, vecs = vectors[: len(library)], vectors[len(library):]

    best: dict[str, list[float]] = {"scam": [], "legit": []}
    for r, v in zip(rows, vecs, strict=False):
        best[r["label"]].append(max(cosine(v, lv) for lv in lib_vecs))
    current = settings.similarity_threshold
    print(f"\nCurrent threshold for {provider}: {current:.2f}\n")
    for t in [x / 100 for x in range(30, 96, 5)]:
        s = sum(x >= t for x in best["scam"])
        legit = sum(x >= t for x in best["legit"])
        print(f"threshold {t:.2f}: scam matches {s:3d}/{len(best['scam'])}   legit matches {legit:3d}/{len(best['legit'])}")
    print("\nPick the lowest threshold with 0 legit matches, then set it in .env "
          "(SIMILARITY_THRESHOLD_GEMINI or SIMILARITY_THRESHOLD_LOCAL).")


if __name__ == "__main__":
    main()
