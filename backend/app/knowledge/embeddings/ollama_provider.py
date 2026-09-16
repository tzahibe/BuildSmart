"""Ollama-backed embeddings — only constructible for a model whose capabilities were verified (via
`app.local_models.discovery`) to actually include "embedding". Never repurposes a completion model
silently: constructing this provider for a non-embedding-capable model raises immediately.
"""

from __future__ import annotations

import httpx

from app.knowledge.embeddings.base import EmbeddingProvider
from app.local_models.discovery import discover_ollama


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, base_url: str):
        status = discover_ollama(base_url)
        if not status.available:
            raise RuntimeError(f"Ollama unreachable at {base_url} — cannot use the ollama embedding provider")
        entry = next((m for m in status.models if m.name == model), None)
        if entry is None:
            raise RuntimeError(f"Ollama model {model!r} is not installed (`ollama list` to check)")
        if not entry.has_embedding_capability:
            raise RuntimeError(
                f"Ollama model {model!r} does not declare 'embedding' in its capabilities "
                f"({list(entry.capabilities)}) — refusing to silently use a completion model as "
                f"an embedder. Pull a dedicated embedding model instead (e.g. `ollama pull "
                f"nomic-embed-text`) and set KNOWLEDGE_EMBEDDING_MODEL to it."
            )
        self.provider_name = "ollama"
        self.model_name = model
        self.dim = 0  # discovered on first real call
        self._base_url = base_url

    def embed(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client() as client:
            resp = client.post(
                f"{self._base_url}/api/embed",
                json={"model": self.model_name, "input": texts},
                timeout=60.0,
            )
            resp.raise_for_status()
            embeddings = resp.json()["embeddings"]
        if not self.dim and embeddings:
            self.dim = len(embeddings[0])
        return embeddings
