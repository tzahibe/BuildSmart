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
from app.knowledge.lock import IndexLockTimeout, acquire_index_lock
from app.knowledge.store.base import ChunkRecord, IndexMeta, KnowledgeStore

#: How long a write (index/clear) waits for another agent's in-progress refresh before giving up.
#: Deliberately short relative to a full reindex — the point is to let a second agent notice
#: quickly and either wait briefly or fall back to reading the last known-good index, not to make
#: every agent queue behind a slow first indexer.
DEFAULT_LOCK_TIMEOUT_S = 30.0


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
    #: True when another process held the write lock past the bounded timeout — no write was
    #: attempted, and `indexed`/`skipped_unchanged`/`removed` are meaningless (empty) here.
    #: Retrieval against the existing (last known-good) index remains valid and unaffected.
    deferred: bool = False


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
        recorded = (meta.embedding_provider, meta.embedding_model, meta.embedding_dim)
        active = (self.embedder.provider_name, self.embedder.model_name, self.embedder.dim)
        if recorded != active:
            raise EmbeddingConfigMismatch(
                f"The index was built with provider={meta.embedding_provider!r} "
                f"model={meta.embedding_model!r} dim={meta.embedding_dim}, but the active config "
                f"resolves to provider={self.embedder.provider_name!r} "
                f"model={self.embedder.model_name!r} dim={self.embedder.dim}. "
                f"Mixing embeddings from different models (or model versions that changed "
                f"dimensionality) would silently corrupt vector search. "
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

    def index_all(self, *, lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S) -> IndexReport:
        with acquire_index_lock(self.cfg.sqlite_path, timeout_s=lock_timeout_s) as acquired:
            if not acquired:
                return IndexReport(indexed=[], skipped_unchanged=[], removed=[], deferred=True)
            return self._index_all_locked()

    def _index_all_locked(self) -> IndexReport:
        current_files = discover_source_files(self.repo_root, self.cfg.source_globs)
        known_paths = set(self.store.all_document_checksums())
        for rel_path in current_files:
            self._index_file(rel_path)
        removed = known_paths - set(current_files)
        for rel_path in removed:
            self.store.delete_document(rel_path)
        self._finalize_meta()
        return IndexReport(indexed=current_files, skipped_unchanged=[], removed=sorted(removed))

    def index_changed(self, *, lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S) -> IndexReport:
        """Single-writer safe: if another agent is already refreshing this shared index, this
        waits up to `lock_timeout_s` and, failing that, returns `deferred=True` rather than
        starting a second concurrent writer — the existing index is left exactly as it was and
        remains fully readable in the meantime (see sqlite_store.py's WAL mode)."""
        with acquire_index_lock(self.cfg.sqlite_path, timeout_s=lock_timeout_s) as acquired:
            if not acquired:
                return IndexReport(indexed=[], skipped_unchanged=[], removed=[], deferred=True)
            return self._index_changed_locked()

    def _index_changed_locked(self) -> IndexReport:
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

    def clear(self, *, lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S) -> None:
        """Destructive and rare — refuses outright (raises) rather than silently no-op'ing or
        forcing through another process's in-progress write if the lock can't be acquired.
        Never deletes/rebuilds the shared index merely because a lock is held."""
        with acquire_index_lock(self.cfg.sqlite_path, timeout_s=lock_timeout_s) as acquired:
            if not acquired:
                raise IndexLockTimeout(
                    f"could not acquire the index lock within {lock_timeout_s}s — another "
                    f"process appears to be indexing. Refusing to clear the shared index "
                    f"concurrently; try again shortly."
                )
            self.store.clear()
