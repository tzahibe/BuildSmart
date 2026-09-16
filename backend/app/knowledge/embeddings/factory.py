"""Embedding-provider selection.

Resolution order:
1. Explicit `KNOWLEDGE_EMBEDDING_PROVIDER` env override, if set.
2. Auto-detect: ask Ollama discovery for an installed model with *verified* embedding capability
   (checked via `/api/tags`/`/api/show`, never assumed from a model's name).
3. Fall back to the deterministic hash embedder and log that semantic embeddings are not enabled —
   this is today's actual state (`llama3.2` and `gemma4:26b` both lack embedding capability).

`LocalArchitectModelGateway`-style lazy imports: the openai/ollama modules are only imported once
a branch that needs them is actually taken.
"""

from __future__ import annotations

import logging

from app.knowledge.config import KnowledgeConfig
from app.knowledge.embeddings.base import EmbeddingProvider
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider

logger = logging.getLogger(__name__)


def get_embedding_provider(cfg: KnowledgeConfig) -> EmbeddingProvider:
    override = cfg.embedding_provider_override
    if override == "hash":
        return HashEmbeddingProvider()
    if override == "openai":
        from app.knowledge.embeddings.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider()
    if override == "ollama":
        from app.knowledge.embeddings.ollama_provider import OllamaEmbeddingProvider

        if not cfg.embedding_model:
            raise RuntimeError("KNOWLEDGE_EMBEDDING_PROVIDER=ollama requires KNOWLEDGE_EMBEDDING_MODEL")
        return OllamaEmbeddingProvider(cfg.embedding_model, cfg.ollama_base_url)
    if override is not None:
        raise RuntimeError(f"Unknown KNOWLEDGE_EMBEDDING_PROVIDER: {override!r} (expected 'ollama', 'hash', or 'openai')")

    from app.local_models.discovery import discover_ollama

    status = discover_ollama(cfg.ollama_base_url)
    if status.available and status.embedding_capable_models:
        from app.knowledge.embeddings.ollama_provider import OllamaEmbeddingProvider

        chosen = status.embedding_capable_models[0]
        logger.info("knowledge: auto-selected Ollama embedding model %r", chosen.name)
        return OllamaEmbeddingProvider(chosen.name, cfg.ollama_base_url)

    logger.warning(
        "knowledge: semantic embeddings NOT ENABLED — no installed Ollama model declares "
        "'embedding' capability; falling back to the deterministic hash embedder. Hybrid keyword "
        "search still retrieves exact technical terms reliably. Recommend `ollama pull "
        "nomic-embed-text` (not done automatically) to enable real semantic embeddings."
    )
    return HashEmbeddingProvider()
