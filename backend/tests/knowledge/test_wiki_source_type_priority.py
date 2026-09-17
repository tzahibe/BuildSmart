"""Wiki-first retrieval invariants (source_type reranking) — the same bounded-multiplier
discipline as doc_status, applied to source_type: WIKI_CANONICAL/PROJECT_STATE get a guaranteed
floor weight so a semantically-similar old investigation can't simply outrank the canonical
current-truth source on status alone, but the floor still never overrides a real relevance gap.
"""

from app.knowledge import doc_status
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider
from app.knowledge.retrieval import search
from app.knowledge.store.base import ChunkRecord
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore

_STATUS_TABLE = {
    "docs/wiki/features/example.md": {"topic": "t", "source_type": "WIKI_CANONICAL", "doc_status": "IMPLEMENTED", "capability_status": "IMPLEMENTED_MERGED", "confidence": "high"},
    "docs/EXAMPLE_INVESTIGATION_REPORT.md": {"topic": "t", "source_type": "INVESTIGATION", "doc_status": "ACTIVE_RESEARCH", "capability_status": "UNKNOWN", "confidence": "high"},
    "docs/IRRELEVANT_WIKI.md": {"topic": "other", "source_type": "WIKI_CANONICAL", "doc_status": "IMPLEMENTED", "capability_status": "IMPLEMENTED_MERGED", "confidence": "high"},
    "docs/HIGHLY_RELEVANT_HISTORICAL.md": {"topic": "t", "source_type": "HISTORICAL", "doc_status": "SUPERSEDED", "confidence": "high"},
}


def _seed_store(tmp_path, chunks_by_doc: dict[str, list[str]]):
    doc_status.set_table_for_testing(_STATUS_TABLE)
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    embedder = HashEmbeddingProvider()
    for doc_path, texts in chunks_by_doc.items():
        embeddings = embedder.embed(texts)
        records = [
            ChunkRecord(chunk_id=f"{doc_path}::h::{i}", doc_path=doc_path, heading_path="h",
                        ordinal=i, text=t, embedding=emb)
            for i, (t, emb) in enumerate(zip(texts, embeddings))
        ]
        store.upsert_document(doc_path, checksum=doc_path, chunks=records)
    return store, embedder


def test_wiki_canonical_wins_a_near_tie_against_an_old_investigation(tmp_path):
    identical_text = "Multi-Level Phase 1 core-band coordinator status."
    store, embedder = _seed_store(tmp_path, {
        "docs/wiki/features/example.md": [identical_text],
        "docs/EXAMPLE_INVESTIGATION_REPORT.md": [identical_text],
    })
    hits = search(store, embedder, "Multi-Level Phase 1 status", top_k=5)
    by_doc = {h.doc_path: h for h in hits}
    assert by_doc["docs/wiki/features/example.md"].combined_relevance == by_doc["docs/EXAMPLE_INVESTIGATION_REPORT.md"].combined_relevance
    assert by_doc["docs/wiki/features/example.md"].final_score > by_doc["docs/EXAMPLE_INVESTIGATION_REPORT.md"].final_score
    assert hits[0].doc_path == "docs/wiki/features/example.md"


def test_wiki_source_type_floor_cannot_flip_a_real_relevance_gap(tmp_path):
    store, embedder = _seed_store(tmp_path, {
        "docs/IRRELEVANT_WIKI.md": ["Recipe instructions for baking sourdough bread at home."],
        "docs/HIGHLY_RELEVANT_HISTORICAL.md": ["Multi-Level Phase 1 core-band coordinator allocations A and C."],
    })
    hits = search(store, embedder, "Multi-Level Phase 1 core-band coordinator allocations", top_k=5)
    by_doc = {h.doc_path: h for h in hits}
    assert by_doc["docs/HIGHLY_RELEVANT_HISTORICAL.md"].combined_relevance > by_doc["docs/IRRELEVANT_WIKI.md"].combined_relevance
    assert hits[0].doc_path == "docs/HIGHLY_RELEVANT_HISTORICAL.md", \
        "a WIKI_CANONICAL floor must never override a real relevance gap"


def test_default_source_type_derivation_for_entries_without_an_explicit_value():
    from app.knowledge.doc_status import _default_source_type

    assert _default_source_type("docs/wiki/anything.md", "ACTIVE_RESEARCH") == "WIKI_CANONICAL"
    assert _default_source_type("docs/PROJECT_STATE.md", "IMPLEMENTED") == "PROJECT_STATE"
    assert _default_source_type("specs/007-x/spec.md", "IMPLEMENTED") == "SPEC"
    assert _default_source_type("docs/SOME_REPORT.md", "SUPERSEDED") == "HISTORICAL"
    assert _default_source_type("docs/SOME_REPORT.md", "ACTIVE_RESEARCH") == "INVESTIGATION"
    assert _default_source_type("docs/SOME_REPORT.md", "IMPLEMENTED") == "IMPLEMENTATION_REPORT"
