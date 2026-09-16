"""Dependency-free deterministic embedding: a hashed bag of words + character n-grams, L2-normalized.

This is the safe default when no installed Ollama model declares embedding capability (the actual
state of this dev machine today — see `factory.py`). It is not semantic search in the sense a real
embedding model provides; the hybrid retrieval layer's keyword/FTS5 channel is what makes exact
technical terms (`C22`, `VerticalCore`, ...) retrieve reliably regardless of this provider's
quality — see docs/PROJECT_KNOWLEDGE_RAG.md for the tradeoff and the upgrade path.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.knowledge.embeddings.base import EmbeddingProvider

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_NGRAM_SIZES = (3, 4)


def _stable_bucket(token: str, dim: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % dim


def _features(text: str) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    features = list(words)
    for word in words:
        for n in _NGRAM_SIZES:
            features.extend(word[i:i + n] for i in range(len(word) - n + 1))
    return features


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = 512):
        self.provider_name = "hash"
        self.model_name = "hashed-ngram-v1"
        self.dim = dim

    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        # A bag-of-words/n-gram hash has no query/document asymmetry to exploit — ignored.
        del is_query
        vectors = []
        for text in texts:
            vector = [0.0] * self.dim
            for feature in _features(text):
                vector[_stable_bucket(feature, self.dim)] += 1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        return vectors
