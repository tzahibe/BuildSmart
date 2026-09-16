"""Optional, local, real-model retrieval evaluation — NOT part of the hermetic pytest suite (it
downloads and runs real embedding models). Run manually:

    uv run python -m tests.knowledge.eval.run_eval --provider hash
    uv run python -m tests.knowledge.eval.run_eval --provider huggingface --model intfloat/multilingual-e5-base

Builds a throwaway SQLite index (temp dir, real repo docs, same chunking as production) and
measures Top-1/Recall@3/Recall@5/MRR in three modes — FTS-only, semantic-only, hybrid — against
tests/knowledge/eval/queries.json, whose `expected_docs` are manually grounded via `git grep` on
tracked content, never generated from a model's own output.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import time

from app.knowledge.chunking import chunk_markdown
from app.knowledge.embeddings.base import EmbeddingProvider
from app.knowledge.embeddings.hash_provider import HashEmbeddingProvider
from app.knowledge.indexer import discover_source_files, repo_root_from_here
from app.knowledge.store.base import ChunkRecord
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore

_QUERIES_PATH = os.path.join(os.path.dirname(__file__), "queries.json")
_TOPK_FOR_METRICS = 5


def _rss_mb() -> float:
    # ru_maxrss is KB on Linux, bytes on macOS — normalize via a live sample instead.
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True)
    return float(out.stdout.strip() or 0) / 1024


def build_index(embedder: EmbeddingProvider, db_path: str) -> dict:
    root = repo_root_from_here()
    from app.knowledge.config import DEFAULT_SOURCE_GLOBS

    files = discover_source_files(root, DEFAULT_SOURCE_GLOBS)
    store = SqliteKnowledgeStore(db_path)

    t0 = time.time()
    for rel_path in files:
        with open(os.path.join(root, rel_path), encoding="utf-8") as f:
            text = f.read()
        chunks = chunk_markdown(rel_path, text)
        if not chunks:
            continue
        embeddings = embedder.embed([c.text for c in chunks])
        records = [
            ChunkRecord(chunk_id=c.chunk_id, doc_path=c.doc_path, heading_path=c.heading_path,
                        ordinal=c.ordinal, text=c.text, embedding=emb)
            for c, emb in zip(chunks, embeddings)
        ]
        store.upsert_document(rel_path, checksum=rel_path, chunks=records)
    indexing_s = time.time() - t0
    return {"store": store, "n_files": len(files), "indexing_s": indexing_s}


def _ranked_docs(hits) -> list[str]:
    seen, ordered = set(), []
    for h in hits:
        if h.doc_path not in seen:
            seen.add(h.doc_path)
            ordered.append(h.doc_path)
    return ordered


def evaluate_mode(store, embedder, queries: list[dict], mode: str) -> dict:
    """mode: 'fts' | 'semantic' | 'hybrid'"""
    per_query, latencies = [], []
    for q in queries:
        t0 = time.time()
        if mode == "fts":
            hits = store.search_keyword(q["query"], 50)
        elif mode == "semantic":
            qvec = embedder.embed([q["query"]], is_query=True)[0]
            hits = store.search_vector(qvec, 50)
        else:
            from app.knowledge.retrieval import search

            hits = search(store, embedder, q["query"], top_k=50)
        latencies.append((time.time() - t0) * 1000)

        ranked = _ranked_docs(hits)
        expected = q["expected_docs"]
        top1 = ranked[0] in expected if ranked else False
        recall3 = any(d in expected for d in ranked[:3])
        recall5 = any(d in expected for d in ranked[:5])
        rr = 0.0
        for i, d in enumerate(ranked[:10], start=1):
            if d in expected:
                rr = 1.0 / i
                break
        per_query.append({"id": q["id"], "lang": q["lang"], "top1": top1, "recall3": recall3,
                            "recall5": recall5, "rr": rr})

    def _agg(rows):
        n = len(rows) or 1
        return {
            "n": len(rows),
            "top1": sum(r["top1"] for r in rows) / n,
            "recall3": sum(r["recall3"] for r in rows) / n,
            "recall5": sum(r["recall5"] for r in rows) / n,
            "mrr": sum(r["rr"] for r in rows) / n,
        }

    return {
        "overall": _agg(per_query),
        "hebrew": _agg([r for r in per_query if r["lang"] == "he"]),
        "english": _agg([r for r in per_query if r["lang"] == "en"]),
        "avg_query_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "per_query": per_query,
    }


def run(provider_name: str, model: str | None, device: str = "cpu") -> dict:
    import tempfile

    if provider_name == "hash":
        embedder = HashEmbeddingProvider()
    elif provider_name == "huggingface":
        from app.knowledge.embeddings.huggingface_provider import HuggingFaceEmbeddingProvider

        embedder = HuggingFaceEmbeddingProvider(model, device=device)
    else:
        raise ValueError(f"unsupported provider for eval: {provider_name!r}")

    with open(_QUERIES_PATH, encoding="utf-8") as f:
        queries = json.load(f)["queries"]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "eval.db")
        rss_before = _rss_mb()
        index_info = build_index(embedder, db_path)
        rss_after_index = _rss_mb()
        store = index_info["store"]

        results = {
            mode: evaluate_mode(store, embedder, queries, mode)
            for mode in ("fts", "semantic", "hybrid")
        }

        return {
            "provider": provider_name,
            "model": model or "hashed-ngram-v1",
            "dim": embedder.dim,
            "n_files_indexed": index_info["n_files"],
            "n_queries": len(queries),
            "indexing_s": index_info["indexing_s"],
            "rss_mb_before": rss_before,
            "rss_mb_after_index": rss_after_index,
            "results": results,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=["hash", "huggingface"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    report = run(args.provider, args.model, args.device)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    for mode, r in report["results"].items():
        print(f"\n-- {mode} --")
        print(f"  overall: {r['overall']}")
        print(f"  hebrew:  {r['hebrew']}")
        print(f"  english: {r['english']}")
        print(f"  avg_query_latency_ms: {r['avg_query_latency_ms']:.2f}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
