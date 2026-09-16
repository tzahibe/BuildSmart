import pytest

from app.knowledge.config import KnowledgeConfig
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider
from app.knowledge.indexer import EmbeddingConfigMismatch, KnowledgeIndexer
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore


def _cfg(tmp_path):
    return KnowledgeConfig(
        embedding_provider_override="hash", embedding_model=None,
        sqlite_path=str(tmp_path / "index.db"),
        source_globs=("docs/**/*.md",),
    )


def _make_indexer(tmp_path):
    cfg = _cfg(tmp_path)
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    return KnowledgeIndexer(cfg, store, HashEmbeddingProvider(), repo_root=str(tmp_path))


def test_index_changed_skips_unchanged_files(tmp_docs):
    idx = _make_indexer(tmp_docs)
    first = idx.index_all()
    assert set(first.indexed) == {"docs/CURRENT_APPROACH.md", "docs/OLD_APPROACH.md", "docs/UNRELATED.md"}

    second = idx.index_changed()
    assert second.indexed == []
    assert set(second.skipped_unchanged) == set(first.indexed)


def test_index_changed_reindexes_edited_file(tmp_docs):
    idx = _make_indexer(tmp_docs)
    idx.index_all()

    (tmp_docs / "docs" / "CURRENT_APPROACH.md").write_text("# Current Approach\n\nEdited body.\n")
    report = idx.index_changed()
    assert report.indexed == ["docs/CURRENT_APPROACH.md"]
    assert "docs/OLD_APPROACH.md" in report.skipped_unchanged


def test_index_changed_removes_deleted_file(tmp_docs):
    idx = _make_indexer(tmp_docs)
    idx.index_all()

    (tmp_docs / "docs" / "OLD_APPROACH.md").unlink()
    report = idx.index_changed()
    assert report.removed == ["docs/OLD_APPROACH.md"]
    assert "docs/OLD_APPROACH.md" not in idx.store.all_document_checksums()


def test_embedding_config_change_forces_rebuild_error(tmp_docs):
    idx = _make_indexer(tmp_docs)
    idx.index_all()

    # Simulate a different embedding provider/model having been configured — e.g. after pulling a
    # dedicated embedding model and switching KNOWLEDGE_EMBEDDING_PROVIDER=ollama.
    class _OtherEmbedder(HashEmbeddingProvider):
        def __init__(self):
            super().__init__()
            self.provider_name = "ollama"
            self.model_name = "nomic-embed-text"

    idx2 = KnowledgeIndexer(idx.cfg, idx.store, _OtherEmbedder(), repo_root=idx.repo_root)
    with pytest.raises(EmbeddingConfigMismatch):
        idx2.index_changed()

    # index_all is not gated the same way (it's an explicit full rebuild), but clear+index_all is
    # the documented recovery path — confirm it succeeds cleanly.
    idx2.store.clear()
    idx2.index_all()
    meta = idx2.store.get_index_meta()
    assert meta.embedding_provider == "ollama"
