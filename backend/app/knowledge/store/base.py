from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    doc_path: str
    heading_path: str
    ordinal: int
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    doc_path: str
    heading_path: str
    text: str
    raw_score: float


@dataclass(frozen=True)
class IndexMeta:
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    updated_at: str


class KnowledgeStore(ABC):
    @abstractmethod
    def upsert_document(self, path: str, checksum: str, chunks: list[ChunkRecord]) -> None: ...

    @abstractmethod
    def delete_document(self, path: str) -> None: ...

    @abstractmethod
    def all_document_checksums(self) -> dict[str, str]: ...

    @abstractmethod
    def search_vector(self, query_vector: list[float], top_k: int) -> list[SearchHit]:
        """Higher raw_score = more similar (cosine, roughly [-1, 1])."""

    @abstractmethod
    def search_keyword(self, query_text: str, top_k: int) -> list[SearchHit]:
        """Higher raw_score = more relevant (already sign-flipped from FTS5's bm25(), where lower
        is better)."""

    @abstractmethod
    def get_index_meta(self) -> IndexMeta | None: ...

    @abstractmethod
    def set_index_meta(self, meta: IndexMeta) -> None: ...

    @abstractmethod
    def stats(self) -> dict: ...

    @abstractmethod
    def clear(self) -> None: ...
