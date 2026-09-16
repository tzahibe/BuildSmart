"""Hybrid retrieval with a bounded, explicitly two-stage scoring pipeline.

Raw FTS5 bm25 scores and raw cosine-similarity scores are on incomparable scales, so they are
never combined directly. Each channel is independently normalized to [0, 1] first; only the
resulting `combined` relevance score is reranked by a bounded status multiplier — narrow enough to
break a near-tie between equally-relevant chunks of different status, but never wide enough to
flip a real relevance gap. See `doc_status.py`'s `_STATUS_WEIGHT` for the exact bounds and the
worked-example comment below.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.doc_status import DocStatusEntry, status_for
from app.knowledge.embeddings.base import EmbeddingProvider
from app.knowledge.store.base import KnowledgeStore, SearchHit

#: How many raw candidates each channel considers before normalization/reranking. Generous
#: relative to this corpus's size (a few hundred chunks) so a relevant chunk is never dropped
#: before it gets a chance to be reranked.
_CANDIDATE_POOL = 50


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    doc_path: str
    heading_path: str
    text: str
    combined_relevance: float
    final_score: float
    status: DocStatusEntry


def _normalize(hits: list[SearchHit]) -> dict[str, float]:
    if not hits:
        return {}
    scores = [h.raw_score for h in hits]
    lo, hi = min(scores), max(scores)
    span = hi - lo
    if span == 0:
        # No variance in this pool (a single candidate, or a tie across all of them) — min-max
        # normalization is undefined here, but collapsing to 0 would wrongly read as "irrelevant".
        # These are, by definition, the best matches this channel found, so they normalize to 1.
        return {h.chunk_id: 1.0 for h in hits}
    return {h.chunk_id: (h.raw_score - lo) / span for h in hits}


def search(
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    query: str,
    *,
    top_k: int = 5,
    topics: tuple[str, ...] | None = None,
    status: tuple[str, ...] | None = None,
) -> list[RetrievedChunk]:
    """`status`, when given, FILTERS to those doc_status values (e.g. `("HISTORICAL",
    "SUPERSEDED")` to explicitly ask for historical material) rather than reranking — so
    historical/superseded content is always reachable on request, never hidden outright."""
    query_vector = embedder.embed([query])[0]
    vector_hits = store.search_vector(query_vector, _CANDIDATE_POOL)
    keyword_hits = store.search_keyword(query, _CANDIDATE_POOL)

    norm_vector = _normalize(vector_hits)
    norm_keyword = _normalize(keyword_hits)
    hit_by_id = {h.chunk_id: h for h in (*vector_hits, *keyword_hits)}

    results: list[RetrievedChunk] = []
    for chunk_id, hit in hit_by_id.items():
        entry = status_for(hit.doc_path)
        if status is not None and entry.doc_status not in status:
            continue
        if topics is not None and entry.topic not in topics:
            continue

        combined = 0.5 * norm_vector.get(chunk_id, 0.0) + 0.5 * norm_keyword.get(chunk_id, 0.0)
        # Worked example of the bound this multiplier respects: a highly-relevant HISTORICAL chunk
        # (combined=0.9, weight=0.90 -> final=0.81) still outranks an irrelevant IMPLEMENTED_MERGED
        # chunk (combined=0.05, weight=1.15 -> final=0.0575) — status can break a near-tie, never a
        # real relevance gap.
        final = combined * entry.status_weight
        results.append(RetrievedChunk(
            chunk_id=chunk_id, doc_path=hit.doc_path, heading_path=hit.heading_path, text=hit.text,
            combined_relevance=combined, final_score=final, status=entry,
        ))

    results.sort(key=lambda r: r.final_score, reverse=True)
    return results[:top_k]
