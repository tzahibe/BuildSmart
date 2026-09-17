"""Concurrency-safety tests for the single-writer index lock. Multiple agents may run against the
same shared SQLite-backed index; only one may write (index/clear) at a time, and readers must
stay usable throughout — see app/knowledge/lock.py and sqlite_store.py's WAL mode.
"""

from __future__ import annotations

import time

from app.knowledge.config import KnowledgeConfig
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.lock import IndexLock, IndexLockTimeout, acquire_index_lock
from app.knowledge.store.base import ChunkRecord
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore


def _make_indexer(tmp_path, docs: dict[str, str]):
    (tmp_path / "docs").mkdir(exist_ok=True)
    for name, text in docs.items():
        (tmp_path / "docs" / name).write_text(text)
    cfg = KnowledgeConfig(embedding_provider_override="hash", embedding_model=None,
                           sqlite_path=str(tmp_path / "index.db"), source_globs=("docs/**/*.md",))
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    return KnowledgeIndexer(cfg, store, HashEmbeddingProvider(), repo_root=str(tmp_path))


def test_lock_acquire_and_release(tmp_path):
    db_path = str(tmp_path / "index.db")
    lock_a = IndexLock(db_path)
    assert lock_a.acquire(timeout_s=1.0) is True

    lock_b = IndexLock(db_path)
    assert lock_b.acquire(timeout_s=0.3) is False, "a second holder must not acquire while the first holds it"

    lock_a.release()
    assert lock_b.acquire(timeout_s=1.0) is True, "released promptly, a waiting acquirer succeeds"
    lock_b.release()


def test_acquire_index_lock_context_manager_reports_success_and_failure(tmp_path):
    db_path = str(tmp_path / "index.db")
    with acquire_index_lock(db_path, timeout_s=1.0) as first:
        assert first is True
        with acquire_index_lock(db_path, timeout_s=0.3) as second:
            assert second is False, "a concurrent acquire attempt must not also succeed"
    with acquire_index_lock(db_path, timeout_s=1.0) as third:
        assert third is True, "the lock is released when the first `with` block exits"


def test_second_writer_defers_instead_of_running_concurrently(tmp_path):
    idx = _make_indexer(tmp_path, {"a.md": "# A\n\ncontent\n"})

    # Simulate Agent A's in-progress refresh by holding the write lock externally.
    holder = IndexLock(idx.cfg.sqlite_path)
    assert holder.acquire(timeout_s=1.0)
    try:
        report = idx.index_changed(lock_timeout_s=0.3)
        assert report.deferred is True, "Agent B must defer, never start a second concurrent writer"
        assert report.indexed == [] and report.removed == []
    finally:
        holder.release()

    # Once the lock is free, a normal refresh proceeds and actually indexes.
    report = idx.index_changed(lock_timeout_s=1.0)
    assert report.deferred is False
    assert report.indexed == ["docs/a.md"]


def test_clear_refuses_rather_than_forcing_through_a_held_lock(tmp_path):
    idx = _make_indexer(tmp_path, {"a.md": "# A\n\ncontent\n"})
    idx.index_all()

    holder = IndexLock(idx.cfg.sqlite_path)
    assert holder.acquire(timeout_s=1.0)
    try:
        try:
            idx.clear(lock_timeout_s=0.3)
            assert False, "clear() must raise, never silently no-op or force through"
        except IndexLockTimeout:
            pass
    finally:
        holder.release()

    # The index was NOT destroyed by the refused clear attempt.
    assert idx.store.all_document_checksums() == {"docs/a.md": idx.store.all_document_checksums()["docs/a.md"]}
    idx.clear(lock_timeout_s=1.0)  # now succeeds
    assert idx.store.all_document_checksums() == {}


def test_stale_lock_file_does_not_block_a_new_holder(tmp_path):
    """flock is tied to a live file descriptor, not the lock file's mere existence — a leftover
    lock file from a process that already exited (crashed or not) is not "stale" in any way that
    needs manual recovery; a new acquirer succeeds immediately."""
    db_path = str(tmp_path / "index.db")
    crashed = IndexLock(db_path)
    assert crashed.acquire(timeout_s=1.0)
    # Simulate the holding process exiting without calling release() (e.g. a crash) — the OS
    # reclaims the flock the moment the fd closes, which os.close() alone (skipping release()'s
    # explicit LOCK_UN) already demonstrates.
    import os

    os.close(crashed._fd)
    crashed._fd = None

    assert os.path.exists(db_path + ".lock"), "the lock file itself is still there, unlike the lock"
    new_holder = IndexLock(db_path)
    start = time.monotonic()
    assert new_holder.acquire(timeout_s=2.0) is True
    assert time.monotonic() - start < 0.5, "must acquire immediately, not wait out the timeout"
    new_holder.release()


def test_index_remains_readable_after_an_interrupted_refresh(tmp_path):
    """Each document is committed individually during indexing (sqlite_store.py's
    upsert_document), so a refresh that stops partway (crash, kill, or a deferred second writer)
    never leaves the store in a state where reads fail — whatever was committed so far stays
    queryable."""
    idx = _make_indexer(tmp_path, {"a.md": "# A\n\nfirst content\n", "b.md": "# B\n\nsecond content\n"})

    # Simulate "interrupted after the first document" by indexing only one file directly, as a
    # real crash mid-loop would leave things — docs/b.md is never reached.
    idx._index_file("docs/a.md")

    assert set(idx.store.all_document_checksums()) == {"docs/a.md"}, "each document commits individually"
    assert idx.store.get_index_meta() is None, "the overall index_meta only finalizes at the end of a full pass"
    hits = idx.store.search_keyword("first content", 5)
    assert any(h.doc_path == "docs/a.md" for h in hits), "the committed document is still queryable"
    assert not any(h.doc_path == "docs/b.md" for h in idx.store.search_keyword("anything", 5)), \
        "the never-reached document correctly absent from the store"
    stats = idx.store.stats()
    assert stats["documents"] == 1  # never raises, store stays usable and reports truthfully
