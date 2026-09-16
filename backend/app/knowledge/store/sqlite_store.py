"""SQLite-backed `KnowledgeStore` — the only storage backend built and tested this round (see
docs/PROJECT_KNOWLEDGE_RAG.md's Storage section for why Postgres+pgvector is documented as a
future adapter rather than shipped untested here). Uses stdlib `sqlite3` plus an FTS5 virtual
table for keyword search; vector search is brute-force cosine in Python, which is more than fast
enough for a corpus this size (a few hundred chunks).
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3

from app.knowledge.store.base import ChunkRecord, IndexMeta, KnowledgeStore, SearchHit

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    path TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    last_indexed TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_path TEXT NOT NULL,
    heading_path TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED, text, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS index_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    embedding_provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _fts_query(text: str) -> str:
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class SqliteKnowledgeStore(KnowledgeStore):
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_document(self, path: str, checksum: str, chunks: list[ChunkRecord]) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM chunks WHERE doc_path = ?", (path,))
        cur.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_path = ?)", (path,))
        for c in chunks:
            cur.execute(
                "INSERT OR REPLACE INTO chunks (chunk_id, doc_path, heading_path, ordinal, text, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (c.chunk_id, c.doc_path, c.heading_path, c.ordinal, c.text, json.dumps(c.embedding)),
            )
            cur.execute("INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)", (c.chunk_id, c.text))
        cur.execute(
            "INSERT INTO documents (path, checksum, last_indexed) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(path) DO UPDATE SET checksum = excluded.checksum, last_indexed = excluded.last_indexed",
            (path, checksum),
        )
        self._conn.commit()

    def delete_document(self, path: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_path = ?)", (path,))
        cur.execute("DELETE FROM chunks WHERE doc_path = ?", (path,))
        cur.execute("DELETE FROM documents WHERE path = ?", (path,))
        self._conn.commit()

    def all_document_checksums(self) -> dict[str, str]:
        return dict(self._conn.execute("SELECT path, checksum FROM documents").fetchall())

    def search_vector(self, query_vector: list[float], top_k: int) -> list[SearchHit]:
        rows = self._conn.execute("SELECT chunk_id, doc_path, heading_path, text, embedding FROM chunks").fetchall()
        scored = [
            (_cosine(query_vector, json.loads(embedding)), chunk_id, doc_path, heading_path, text)
            for chunk_id, doc_path, heading_path, text, embedding in rows
        ]
        scored.sort(key=lambda r: r[0], reverse=True)
        return [
            SearchHit(chunk_id=cid, doc_path=dp, heading_path=hp, text=t, raw_score=s)
            for s, cid, dp, hp, t in scored[:top_k]
        ]

    def search_keyword(self, query_text: str, top_k: int) -> list[SearchHit]:
        fts_query = _fts_query(query_text)
        rows = self._conn.execute(
            "SELECT c.chunk_id, c.doc_path, c.heading_path, c.text, bm25(chunks_fts) AS rank "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_query, top_k),
        ).fetchall()
        # bm25(): lower (more negative) is more relevant — flip sign so higher raw_score is better,
        # consistent with search_vector's convention.
        return [
            SearchHit(chunk_id=cid, doc_path=dp, heading_path=hp, text=t, raw_score=-rank)
            for cid, dp, hp, t, rank in rows
        ]

    def get_index_meta(self) -> IndexMeta | None:
        row = self._conn.execute(
            "SELECT embedding_provider, embedding_model, embedding_dim, updated_at FROM index_meta WHERE id = 1"
        ).fetchone()
        return IndexMeta(*row) if row else None

    def set_index_meta(self, meta: IndexMeta) -> None:
        self._conn.execute(
            "INSERT INTO index_meta (id, embedding_provider, embedding_model, embedding_dim, updated_at) "
            "VALUES (1, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "embedding_provider = excluded.embedding_provider, embedding_model = excluded.embedding_model, "
            "embedding_dim = excluded.embedding_dim, updated_at = excluded.updated_at",
            (meta.embedding_provider, meta.embedding_model, meta.embedding_dim, meta.updated_at),
        )
        self._conn.commit()

    def stats(self) -> dict:
        n_docs = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_chunks = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        meta = self.get_index_meta()
        return {
            "documents": n_docs,
            "chunks": n_chunks,
            "embedding_provider": meta.embedding_provider if meta else None,
            "embedding_model": meta.embedding_model if meta else None,
            "embedding_dim": meta.embedding_dim if meta else None,
            "updated_at": meta.updated_at if meta else None,
        }

    def clear(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("DELETE FROM chunks; DELETE FROM chunks_fts; DELETE FROM documents; DELETE FROM index_meta;")
        self._conn.commit()
