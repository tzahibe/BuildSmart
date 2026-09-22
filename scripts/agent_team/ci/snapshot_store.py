"""O2 (Issue #68) — the trusted corpus-snapshot store.

Two things gate-4 (and the `push`-triggered `agent-snapshot.yml`) both need, factored out so they
are unit-testable without a real GitHub Actions run:

- `validate_snapshot`: is a snapshot document trustworthy? It must claim the exact SHA it is
  supposed to be a snapshot of, cover the whole corpus (432 contexts, not a partial/stale shard
  set) and be built from the corpus content currently on disk (`corpus_hash`). Used both by
  `agent-snapshot.yml` before it saves/uploads a snapshot, and by gate-4 before it trusts one it
  restored or downloaded.
- `select_base_snapshot`: gate-4's lookup order for the *base* (merge-base) snapshot — the v2
  Actions cache, then the `push` run's artifact, then "compute it locally" — validating each
  candidate in turn and recording why a candidate was rejected instead of silently discarding it.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXPECTED_CONTEXT_COUNT = 432


@dataclass
class ValidationResult:
    ok: bool
    reason: str


def validate_snapshot(doc: dict | None, expected_head_sha: str, expected_corpus_hash: str,
                       expected_count: int = EXPECTED_CONTEXT_COUNT) -> ValidationResult:
    """A snapshot is trusted only if it is a complete, current replay of the exact SHA it claims
    to be — never on relevance/recency alone. Checked in a fixed order so the reason names the
    first thing that is wrong, not every thing that might be."""
    if doc is None:
        return ValidationResult(False, "no snapshot document")
    head_sha = doc.get("sha")
    if head_sha != expected_head_sha:
        return ValidationResult(False, f"head_sha mismatch: snapshot has {head_sha!r}, expected {expected_head_sha!r}")
    count = len(doc.get("results") or {})
    if count != expected_count:
        return ValidationResult(False, f"context count mismatch: snapshot has {count}, expected {expected_count}")
    corpus_hash = doc.get("corpus_hash")
    if corpus_hash != expected_corpus_hash:
        return ValidationResult(False, f"corpus_hash mismatch: snapshot has {corpus_hash!r}, expected {expected_corpus_hash!r}")
    return ValidationResult(True, "head_sha, context count and corpus_hash all match")


@dataclass
class SourceSelection:
    source: str  # "v2_cache" | "push_artifact" | "computed"
    reason: str
    rejected: list[tuple[str, str]] = field(default_factory=list)


def select_base_snapshot(expected_head_sha: str, expected_corpus_hash: str,
                          v2_cache_doc: dict | None, push_artifact_doc: dict | None,
                          expected_count: int = EXPECTED_CONTEXT_COUNT) -> SourceSelection:
    """Lookup order required by Issue #68: (a) the v2 Actions cache, (b) on a miss, the `push`
    run's artifact, (c) on a miss, compute locally. A candidate that fails validation is rejected
    with a named reason and the next one in order is tried — it is never used anyway."""
    rejected: list[tuple[str, str]] = []
    for source, doc in (("v2_cache", v2_cache_doc), ("push_artifact", push_artifact_doc)):
        if doc is None:
            rejected.append((source, "not available (cache/artifact miss)"))
            continue
        result = validate_snapshot(doc, expected_head_sha, expected_corpus_hash, expected_count)
        if result.ok:
            return SourceSelection(source, result.reason, rejected)
        rejected.append((source, result.reason))
    return SourceSelection("computed", "no trusted candidate available or valid; computing locally", rejected)


def _load(path: str | None) -> dict | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _write_lines(lines: list[str], step_summary: str | None) -> None:
    text = "\n".join(lines)
    print(text)
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="check one snapshot document before trusting it")
    p_validate.add_argument("--snapshot", required=True)
    p_validate.add_argument("--expected-head-sha", required=True)
    p_validate.add_argument("--expected-corpus-hash", required=True)
    p_validate.add_argument("--expected-count", type=int, default=EXPECTED_CONTEXT_COUNT)
    p_validate.add_argument("--step-summary")

    p_select = sub.add_parser("select", help="pick the base-snapshot source: v2 cache -> push artifact -> computed")
    p_select.add_argument("--expected-head-sha", required=True)
    p_select.add_argument("--expected-corpus-hash", required=True)
    p_select.add_argument("--expected-count", type=int, default=EXPECTED_CONTEXT_COUNT)
    p_select.add_argument("--v2-cache", help="path to the v2-cache-restored snapshot file, if the cache step hit")
    p_select.add_argument("--push-artifact", help="path to the downloaded push-artifact snapshot file, if found")
    p_select.add_argument("--github-output")
    p_select.add_argument("--step-summary")

    args = ap.parse_args()

    if args.cmd == "validate":
        doc = _load(args.snapshot)
        result = validate_snapshot(doc, args.expected_head_sha, args.expected_corpus_hash, args.expected_count)
        _write_lines([f"snapshot validation: {'PASS' if result.ok else 'FAIL'} — {result.reason}"], args.step_summary)
        return 0 if result.ok else 1

    selection = select_base_snapshot(
        args.expected_head_sha, args.expected_corpus_hash,
        _load(args.v2_cache), _load(args.push_artifact), args.expected_count,
    )
    lines = [f"base snapshot source: {selection.source} — {selection.reason}"]
    lines += [f"  rejected {src}: {reason}" for src, reason in selection.rejected]
    _write_lines(lines, args.step_summary)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"source={selection.source}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
