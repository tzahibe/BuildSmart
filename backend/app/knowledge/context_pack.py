"""Bounded context-pack builder for an agent task: PROJECT_STATE.md first, then top-ranked current
chunks, then (only if asked for and budget remains) historical evidence — always respecting a
strict approximate-token budget.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.knowledge.embeddings.base import EmbeddingProvider
from app.knowledge.indexer import repo_root_from_here
from app.knowledge.retrieval import RetrievedChunk, search
from app.knowledge.store.base import KnowledgeStore
from app.knowledge.tokens import approx_token_count


@dataclass(frozen=True)
class ContextPack:
    task: str
    project_state_text: str
    chunks: list[RetrievedChunk]
    historical_chunks: list[RetrievedChunk] = field(default_factory=list)
    total_tokens: int = 0
    sources: list[str] = field(default_factory=list)


def _project_state_text(project_state_path: str | None) -> str:
    path = project_state_path or os.path.join(repo_root_from_here(), "docs", "PROJECT_STATE.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_context_pack(
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    task: str,
    *,
    max_tokens: int = 4000,
    topics: tuple[str, ...] | None = None,
    include_historical: bool = False,
    project_state_path: str | None = None,
) -> ContextPack:
    project_state_text = _project_state_text(project_state_path)
    used = approx_token_count(project_state_text)
    sources = ["docs/PROJECT_STATE.md"] if project_state_text else []

    chunks: list[RetrievedChunk] = []
    if used < max_tokens:
        for candidate in search(store, embedder, task, top_k=20, topics=topics):
            cost = approx_token_count(candidate.text)
            if used + cost > max_tokens:
                continue
            chunks.append(candidate)
            sources.append(candidate.doc_path)
            used += cost

    historical_chunks: list[RetrievedChunk] = []
    if include_historical and used < max_tokens:
        for candidate in search(store, embedder, task, top_k=10, topics=topics,
                                 status=("HISTORICAL", "SUPERSEDED")):
            cost = approx_token_count(candidate.text)
            if used + cost > max_tokens:
                continue
            historical_chunks.append(candidate)
            sources.append(candidate.doc_path)
            used += cost

    return ContextPack(
        task=task, project_state_text=project_state_text, chunks=chunks,
        historical_chunks=historical_chunks, total_tokens=used, sources=sources,
    )
