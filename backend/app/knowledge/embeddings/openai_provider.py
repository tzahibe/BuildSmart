"""OpenAI-backed embeddings — the configured remote provider. Gated by OPENAI_API_KEY; never
hardcoded, never logged."""

from __future__ import annotations

import os

from app.knowledge.embeddings.base import EmbeddingProvider

_DIM_BY_MODEL = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("KNOWLEDGE_EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self.provider_name = "openai"
        self.model_name = model
        self.dim = _DIM_BY_MODEL.get(model, 1536)

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.model_name, input=texts)
        return [d.embedding for d in resp.data]
