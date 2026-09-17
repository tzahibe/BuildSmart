"""`knowledge` CLI — see docs/PROJECT_KNOWLEDGE_RAG.md.

    knowledge index [--changed]
    knowledge search "<query>" [--topic T ...] [--status S ...] [--top-k N] [--json]
    knowledge context "<task>" [--max-tokens N] [--topic T ...] [--historical]
    knowledge stats
    knowledge clear
    knowledge local-models
    knowledge doctor
"""

from __future__ import annotations

import argparse
import json
import sys

from app.knowledge.config import config_from_env
from app.knowledge.context_pack import build_context_pack
from app.knowledge.doc_status import stale_entries
from app.knowledge.embeddings.factory import get_embedding_provider
from app.knowledge.indexer import EmbeddingConfigMismatch, KnowledgeIndexer, repo_root_from_here
from app.knowledge.lock import IndexLockTimeout
from app.knowledge.retrieval import search
from app.knowledge.store.factory import get_store
from app.local_models.discovery import discover_ollama, recommend_candidates


def _indexer() -> KnowledgeIndexer:
    cfg = config_from_env(repo_root_from_here())
    return KnowledgeIndexer(cfg, get_store(cfg), get_embedding_provider(cfg))


def cmd_index(args: argparse.Namespace) -> int:
    idx = _indexer()
    try:
        report = idx.index_changed() if args.changed else idx.index_all()
    except EmbeddingConfigMismatch as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if report.deferred:
        print("refresh deferred — another process is currently indexing this shared index; "
              "using the last known-good index. Retrieval is unaffected; re-run later to pick up "
              "any changes.")
        return 0
    print(f"indexed: {len(report.indexed)}  skipped (unchanged): {len(report.skipped_unchanged)}  "
          f"removed: {len(report.removed)}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    cfg = config_from_env(repo_root_from_here())
    store, embedder = get_store(cfg), get_embedding_provider(cfg)
    hits = search(store, embedder, args.query, top_k=args.top_k,
                  topics=tuple(args.topic) if args.topic else None,
                  status=tuple(args.status) if args.status else None)
    if args.json:
        print(json.dumps([{
            "document": h.doc_path, "section": h.heading_path, "status": h.status.doc_status,
            "capability_status": h.status.capability_status, "commit": h.status.commit,
            "score": round(h.final_score, 4), "text": h.text,
        } for h in hits], indent=2, ensure_ascii=False))
    else:
        for h in hits:
            print(f"[{h.final_score:.3f}] {h.doc_path} > {h.heading_path}  "
                  f"({h.status.doc_status}/{h.status.capability_status})")
            print(f"    {h.text[:200].replace(chr(10), ' ')}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    cfg = config_from_env(repo_root_from_here())
    store, embedder = get_store(cfg), get_embedding_provider(cfg)
    pack = build_context_pack(store, embedder, args.task, max_tokens=args.max_tokens,
                               topics=tuple(args.topic) if args.topic else None,
                               include_historical=args.historical)
    print(f"# Context pack for: {args.task}")
    print(f"# approx tokens used: {pack.total_tokens} / budget {args.max_tokens}")
    print("\n## PROJECT_STATE.md\n")
    print(pack.project_state_text)
    for c in pack.chunks:
        print(f"\n## {c.doc_path} > {c.heading_path}  [{c.status.doc_status}]\n")
        print(c.text)
    if pack.historical_chunks:
        print("\n## Historical evidence\n")
        for c in pack.historical_chunks:
            print(f"\n### {c.doc_path} > {c.heading_path}  [{c.status.doc_status}]\n")
            print(c.text)
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    cfg = config_from_env(repo_root_from_here())
    print(json.dumps(get_store(cfg).stats(), indent=2))
    return 0


def cmd_clear(_args: argparse.Namespace) -> int:
    try:
        _indexer().clear()
    except IndexLockTimeout as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print("index cleared")
    return 0


def cmd_local_models(_args: argparse.Namespace) -> int:
    cfg = config_from_env(repo_root_from_here())
    status = discover_ollama(cfg.ollama_base_url)
    if not status.available:
        print(f"Ollama unreachable at {status.base_url}: {status.error}")
        return 0
    print(f"Ollama at {status.base_url} — {len(status.models)} model(s) installed:")
    for m in status.models:
        caution = "  [32GB RAM caution]" if m.ram_caution else ""
        print(f"  {m.name}  ({m.parameter_size}, {m.quantization})  capabilities={list(m.capabilities)}{caution}")
    print(json.dumps(recommend_candidates(status), indent=2))
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    stale = stale_entries()
    print(f"{len(stale)} doc_status.json entries below 'high' confidence — worth a manual git recheck:")
    for path in stale:
        print(f"  {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knowledge")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index")
    p_index.add_argument("--changed", action="store_true")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--topic", action="append")
    p_search.add_argument("--status", action="append")
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_context = sub.add_parser("context")
    p_context.add_argument("task")
    p_context.add_argument("--max-tokens", type=int, default=4000)
    p_context.add_argument("--topic", action="append")
    p_context.add_argument("--historical", action="store_true")
    p_context.set_defaults(func=cmd_context)

    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("clear").set_defaults(func=cmd_clear)
    sub.add_parser("local-models").set_defaults(func=cmd_local_models)
    sub.add_parser("doctor").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
