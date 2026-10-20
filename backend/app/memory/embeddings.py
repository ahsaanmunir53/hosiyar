"""Embeddings for the scam memory.

* Gemini embeddings (free tier) when GOOGLE_API_KEY is set.
* Otherwise a local character n-gram hashing embedder: no network, no cost, and good at
  spotting the near-identical templates that scam campaigns reuse.
"""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

from app.config import Settings
from app.core.text import normalize

_PLACEHOLDER = re.compile(r"\[(phone|code|cnic|card|iban|email)_\d+\]")
_DIGITS = re.compile(r"\d+")


def _features(text: str) -> list[str]:
    t = normalize(text)
    t = _PLACEHOLDER.sub(lambda m: f" {m.group(1)} ", t)
    t = _DIGITS.sub("0", t)
    words = re.findall(r"\w+", t)
    feats = [f"w:{w}" for w in words]
    feats += [f"b:{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
    padded = f" {' '.join(words)} "
    for n in (3, 4, 5):
        feats += [f"c{n}:{padded[i:i + n]}" for i in range(max(0, len(padded) - n + 1))]
    return feats


class HashingEmbeddings(Embeddings):
    """Signed feature hashing into a fixed-size, L2-normalised vector."""

    def __init__(self, dims: int = 768):
        self.dims = dims

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        for feat in _features(text):
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            idx = h % self.dims
            sign = 1.0 if (h >> 63) & 1 else -1.0
            weight = 1.5 if feat.startswith(("w:", "b:")) else 1.0
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embeddings(settings: Settings) -> tuple[Embeddings, str]:
    """Return the embedder and a short provider key used to namespace stored vectors."""
    if settings.resolved_embeddings_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        emb = GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.google_api_key,
            task_type="SEMANTIC_SIMILARITY",
            output_dimensionality=settings.embedding_dims,
        )
        return emb, f"gemini{settings.embedding_dims}"
    return HashingEmbeddings(settings.embedding_dims), f"local{settings.embedding_dims}"
