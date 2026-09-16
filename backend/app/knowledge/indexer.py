"""Indexing pipeline: discover source docs, chunk them, embed, upsert into the store —
incrementally where possible (checksum diff), never mixing vectors from two different embedding
configs.
"""

from __future__ import annotations

import fnmatch
import glob as glob_module
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app.knowledge.chunking import chunk_markdown
from app.knowledge.config import EXCLUDED_GLOBS, KnowledgeConfig
from app.knowledge.embeddings.base import EmbeddingProvider
from app.knowledge.store.base import ChunkRecord, IndexMeta, KnowledgeStore


def repo_root_from_here() -> str:
    # app/knowledge/indexer.py -> app/knowledge -> app -> backend -> repo root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _is_excluded(rel_path: str) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in EXCLUDED_GLOBS)


def discover_source_files(repo_root: str, source_globs: tuple[str, ...]) -> list[str]:
    """Repo-relative paths (posix-style) of every file matching the config's globs, minus
    excluded globs. Sorted for stable, deterministic ordering."""
    found: set[str] = set()
    for pattern in source_globs:
        for abs_path in glob_module.glob(os.path.join(repo_root, pattern), recursive=True):
            if os.path.isfile(abs_path):
                rel = os.path.relpath(abs_path, repo_root).replace(os.sep, "/")
                if not _is_excluded(rel):
                    found.add(rel)
    return sorted(found)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class IndexReport:
    indexed: list[str]
    skipped_unchanged: list[str]
    removed: list[str]


class EmbeddingConfigMismatch(RuntimeError):
    pass


class KnowledgeIndexer:
    def __init__(self, cfg: KnowledgeConfig, store: KnowledgeStore, embedder: EmbeddingProvider,
                 *, repo_root: str | None = None):
        self.cfg = cfg
        self.store = store
        self.embedder = embedder
        self.repo_root = repo_root or repo_root_from_here()

    def _assert_embedding_config_compatible(self) -> None:
        meta = self.store.get_index_meta()
        if meta is None:
            return
        if (meta.embedding_provider, meta.embedding_model) != (self.embedder.provider_name, self.embedder.model_name):
            raise EmbeddingConfigMismatch(
                f"The index was built with provider={meta.embedding_provider!r} "
                f"model={meta.embedding_model!r}, but the active config resolves to "
                f"provider={self.embedder.provider_name!r} model={self.embedder.model_name!r}. "
                f"Mixing embeddings from different models would silently corrupt vector search. "
                f"Run `knowledge clear && knowledge index` to rebuild with the new config."
            )

    def _index_file(self, rel_path: str) -> None:
        with open(os.path.join(self.repo_root, rel_path), encoding="utf-8") as f:
            text = f.read()
        checksum = _checksum(text)
        chunks = chunk_markdown(rel_path, text)
        embeddings = self.embedder.embed([c.text for c in chunks]) if chunks else []
        records = [
            ChunkRecord(chunk_id=c.chunk_id, doc_path=c.doc_path, heading_path=c.heading_path,
                        ordinal=c.ordinal, text=c.text, embedding=emb)
            for c, emb in zip(chunks, embeddings)
        ]
        self.store.upsert_document(rel_path, checksum, records)

    def _finalize_meta(self) -> None:
        self.store.set_index_meta(IndexMeta(
            embedding_provider=self.embedder.provider_name,
            embedding_model=self.embedder.model_name,
            embedding_dim=self.embedder.dim,
            updated_at=datetime.now(timezone.utc).isoformat(),
        ))

    def index_all(self) -> IndexReport:
        current_files = discover_source_files(self.repo_root, self.cfg.source_globs)
        known_paths = set(self.store.all_document_checksums())
        for rel_path in current_files:
            self._index_file(rel_path)
        removed = known_paths - set(current_files)
        for rel_path in removed:
            self.store.delete_document(rel_path)
        self._finalize_meta()
        return IndexReport(indexed=current_files, skipped_unchanged=[], removed=sorted(removed))

    def index_changed(self) -> IndexReport:
        self._assert_embedding_config_compatible()
        current_files = discover_source_files(self.repo_root, self.cfg.source_globs)
        known_checksums = self.store.all_document_checksums()

        indexed, skipped = [], []
        for rel_path in current_files:
            with open(os.path.join(self.repo_root, rel_path), encoding="utf-8") as f:
                text = f.read()
            checksum = _checksum(text)
            if known_checksums.get(rel_path) == checksum:
                skipped.append(rel_path)
                continue
            self._index_file(rel_path)
            indexed.append(rel_path)

        removed = set(known_checksums) - set(current_files)
        for rel_path in removed:
            self.store.delete_document(rel_path)

        if indexed or removed or self.store.get_index_meta() is None:
            self._finalize_meta()
        return IndexReport(indexed=indexed, skipped_unchanged=skipped, removed=sorted(removed))

    def clear(self) -> None:
        self.store.clear()
