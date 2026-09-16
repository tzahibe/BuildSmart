"""Store selection. Only `sqlite` is implemented this round — see
docs/PROJECT_KNOWLEDGE_RAG.md's Storage section for the documented (not implemented) Postgres+
pgvector future adapter plan, which would live at `app/knowledge/store/postgres_store.py`
implementing the same `KnowledgeStore` ABC.
"""

from __future__ import annotations

from app.knowledge.config import KnowledgeConfig
from app.knowledge.store.base import KnowledgeStore
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore


def get_store(cfg: KnowledgeConfig) -> KnowledgeStore:
    return SqliteKnowledgeStore(cfg.sqlite_path)
