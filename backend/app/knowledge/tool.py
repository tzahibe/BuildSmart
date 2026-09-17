"""The plain-function "agent retrieval tool" — see docs/PROJECT_KNOWLEDGE_RAG.md for why this repo
exposes it as an importable function plus `knowledge search --json` rather than a new MCP server.
"""

from __future__ import annotations

from app.knowledge.config import config_from_env
from app.knowledge.embeddings.factory import get_embedding_provider
from app.knowledge.indexer import repo_root_from_here
from app.knowledge.retrieval import search
from app.knowledge.store.factory import get_store


def retrieve(
    query: str,
    *,
    topics: tuple[str, ...] | None = None,
    status: tuple[str, ...] | None = None,
    top_k: int = 5,
) -> list[dict]:
    """query -> list of {text, document, section, status, capability_status, commit, score},
    ranked highest-first. `status`, when given, filters to those doc_status values (e.g. ask for
    ("HISTORICAL",) explicitly) rather than hiding them by default."""
    cfg = config_from_env(repo_root_from_here())
    store = get_store(cfg)
    embedder = get_embedding_provider(cfg)
    hits = search(store, embedder, query, top_k=top_k, topics=topics, status=status)
    return [
        {
            "text": h.text,
            "document": h.doc_path,
            "section": h.heading_path,
            "status": h.status.doc_status,
            "capability_status": h.status.capability_status,
            "source_type": h.status.source_type,
            "commit": h.status.commit,
            "score": round(h.final_score, 4),
        }
        for h in hits
    ]
