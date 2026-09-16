"""The four retrieval-scoring invariants specifically required by review: exact-term retrieval
still works regardless of embedding quality, status only breaks near-ties (never flips a real
relevance gap), and explicit historical requests bypass the default down-weighting.
"""

from app.knowledge import doc_status
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider
from app.knowledge.retrieval import search
from app.knowledge.store.base import ChunkRecord
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore

_STATUS_TABLE = {
    "docs/CURRENT.md": {"topic": "wet-rooms", "doc_status": "IMPLEMENTED_MERGED", "capability_status": "IMPLEMENTED_MERGED", "confidence": "high"},
    "docs/OLD.md": {"topic": "wet-rooms", "doc_status": "SUPERSEDED", "capability_status": "N/A", "confidence": "high"},
    "docs/IRRELEVANT_CURRENT.md": {"topic": "other", "doc_status": "IMPLEMENTED_MERGED", "capability_status": "IMPLEMENTED_MERGED", "confidence": "high"},
    "docs/RELEVANT_HISTORICAL.md": {"topic": "wet-rooms", "doc_status": "HISTORICAL", "capability_status": "N/A", "confidence": "high"},
    "docs/EXACT_TERM.md": {"topic": "geometry", "doc_status": "IMPLEMENTED_MERGED", "capability_status": "IMPLEMENTED_MERGED", "confidence": "high"},
    "docs/GENERIC_TOPIC.md": {"topic": "geometry", "doc_status": "IMPLEMENTED_MERGED", "capability_status": "IMPLEMENTED_MERGED", "confidence": "high"},
}


def _seed_store(tmp_path, chunks_by_doc: dict[str, list[str]]) -> tuple[SqliteKnowledgeStore, HashEmbeddingProvider]:
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


def test_exact_technical_term_retrieves_via_keyword_channel(tmp_path):
    store, embedder = _seed_store(tmp_path, {
        "docs/EXACT_TERM.md": ["The C22 seam validation rule checks realized bathroom access."],
        "docs/GENERIC_TOPIC.md": ["This section discusses general room layout quality and shape."],
    })
    hits = search(store, embedder, "C22", top_k=5)
    assert hits, "expected at least one hit for an exact technical term"
    assert hits[0].doc_path == "docs/EXACT_TERM.md"


def test_equally_relevant_implemented_outranks_superseded_on_near_tie(tmp_path):
    identical_text = "The VerticalCore stair seat is the accepted approach for multi-level circulation."
    store, embedder = _seed_store(tmp_path, {
        "docs/CURRENT.md": [identical_text],
        "docs/OLD.md": [identical_text],
    })
    hits = search(store, embedder, "VerticalCore stair seat", top_k=5)
    by_doc = {h.doc_path: h for h in hits}
    assert by_doc["docs/CURRENT.md"].combined_relevance == by_doc["docs/OLD.md"].combined_relevance
    assert by_doc["docs/CURRENT.md"].final_score > by_doc["docs/OLD.md"].final_score
    assert hits[0].doc_path == "docs/CURRENT.md"


def test_status_boost_cannot_flip_a_real_relevance_gap(tmp_path):
    store, embedder = _seed_store(tmp_path, {
        "docs/IRRELEVANT_CURRENT.md": ["Recipe instructions for baking sourdough bread at home."],
        "docs/RELEVANT_HISTORICAL.md": ["Wet-room fixture demand resolves toilets into bathrooms unless a guest WC is explicit."],
    })
    hits = search(store, embedder, "wet-room fixture demand toilets bathrooms", top_k=5)
    by_doc = {h.doc_path: h for h in hits}
    assert by_doc["docs/RELEVANT_HISTORICAL.md"].combined_relevance > by_doc["docs/IRRELEVANT_CURRENT.md"].combined_relevance
    # the bound: status_weight spans [0.75, 1.15] — 1.15x can never overcome a real relevance gap
    # this large, so final ranking must follow relevance, not status.
    assert hits[0].doc_path == "docs/RELEVANT_HISTORICAL.md"
    assert by_doc["docs/RELEVANT_HISTORICAL.md"].final_score > by_doc["docs/IRRELEVANT_CURRENT.md"].final_score


def test_explicit_historical_filter_still_retrieves_superseded_material(tmp_path):
    store, embedder = _seed_store(tmp_path, {
        "docs/CURRENT.md": ["The accepted stair placement is a shared core-band seat."],
        "docs/OLD.md": ["The old stair placement heuristic is no longer used."],
    })
    default_hits = search(store, embedder, "stair placement", top_k=5)
    assert any(h.doc_path == "docs/OLD.md" for h in default_hits), "down-weighted, not hidden, by default"

    historical_only = search(store, embedder, "stair placement", top_k=5, status=("SUPERSEDED",))
    assert historical_only
    assert all(h.status.doc_status == "SUPERSEDED" for h in historical_only)
    assert any(h.doc_path == "docs/OLD.md" for h in historical_only)


def test_topic_filter(tmp_path):
    store, embedder = _seed_store(tmp_path, {
        "docs/EXACT_TERM.md": ["Geometry seam validation content."],
        "docs/CURRENT.md": ["Wet-room fixture demand content."],
    })
    hits = search(store, embedder, "content", top_k=5, topics=("wet-rooms",))
    assert hits
    assert all(h.status.topic == "wet-rooms" for h in hits)
