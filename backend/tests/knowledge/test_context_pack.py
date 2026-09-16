from app.knowledge import doc_status
from app.knowledge.context_pack import build_context_pack
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider
from app.knowledge.store.base import ChunkRecord
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore
from app.knowledge.tokens import approx_token_count


def _store_with_many_chunks(tmp_path, n=20):
    doc_status.set_table_for_testing({
        f"docs/DOC_{i}.md": {"topic": "t", "doc_status": "IMPLEMENTED_MERGED", "confidence": "high"}
        for i in range(n)
    })
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    embedder = HashEmbeddingProvider()
    for i in range(n):
        text = f"Multi-level Phase 1 detail number {i}. " * 20
        record = ChunkRecord(chunk_id=f"doc{i}::h::0", doc_path=f"docs/DOC_{i}.md", heading_path="h",
                              ordinal=0, text=text, embedding=embedder.embed([text])[0])
        store.upsert_document(f"docs/DOC_{i}.md", checksum=str(i), chunks=[record])
    return store, embedder


def test_context_pack_respects_token_budget(tmp_path):
    project_state = tmp_path / "PROJECT_STATE.md"
    project_state.write_text("# Project State\n\nCompact summary.\n")
    store, embedder = _store_with_many_chunks(tmp_path)

    pack = build_context_pack(store, embedder, "implement multi-level Phase 1", max_tokens=300,
                               project_state_path=str(project_state))

    assert pack.total_tokens <= 300
    assert pack.project_state_text.startswith("# Project State")
    # actual text content must not exceed what the reported token count implies (with slack for
    # the approx heuristic's rounding)
    total_chars = len(pack.project_state_text) + sum(len(c.text) for c in pack.chunks)
    assert approx_token_count("x" * total_chars) <= 300 + 10


def test_context_pack_includes_project_state_first(tmp_path):
    project_state = tmp_path / "PROJECT_STATE.md"
    project_state.write_text("# Project State\n\nThe current architecture is X.\n")
    store, embedder = _store_with_many_chunks(tmp_path, n=2)

    pack = build_context_pack(store, embedder, "anything", max_tokens=4000,
                               project_state_path=str(project_state))
    assert "Project State" in pack.project_state_text
    assert pack.sources[0] == "docs/PROJECT_STATE.md"


def test_historical_only_included_when_requested_and_budget_allows(tmp_path):
    project_state = tmp_path / "PROJECT_STATE.md"
    project_state.write_text("# Project State\n")
    doc_status.set_table_for_testing({
        "docs/CURRENT.md": {"topic": "t", "doc_status": "IMPLEMENTED_MERGED", "confidence": "high"},
        "docs/OLD.md": {"topic": "t", "doc_status": "SUPERSEDED", "confidence": "high"},
    })
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    embedder = HashEmbeddingProvider()
    for doc_path, text in [("docs/CURRENT.md", "multi-level phase 1 current approach"),
                            ("docs/OLD.md", "multi-level phase 1 old approach")]:
        record = ChunkRecord(chunk_id=f"{doc_path}::h::0", doc_path=doc_path, heading_path="h",
                              ordinal=0, text=text, embedding=embedder.embed([text])[0])
        store.upsert_document(doc_path, checksum=doc_path, chunks=[record])

    without_historical = build_context_pack(store, embedder, "multi-level phase 1", max_tokens=4000,
                                             project_state_path=str(project_state))
    assert not without_historical.historical_chunks

    with_historical = build_context_pack(store, embedder, "multi-level phase 1", max_tokens=4000,
                                          include_historical=True, project_state_path=str(project_state))
    assert any(c.doc_path == "docs/OLD.md" for c in with_historical.historical_chunks)
