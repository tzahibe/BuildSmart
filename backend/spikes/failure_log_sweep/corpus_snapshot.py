"""Cross-commit primary-signature gate over the frozen, committed regression corpus.

`snapshot.py` does the same job over the gitignored production log (`app/data/failures.json`);
this sibling reads `tests/regression_corpus/corpus.json` (the same 432 contexts, frozen in git)
so the gate can run in CI and in a fresh validation worktree. It reuses `project_from_context`,
`signature` and `generate_demo_design` unchanged — same replay, same signature, machine-readable
output on top.

    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --save before.json [--workers 4]
    ...change the code...
    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --save after.json
    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --compare before.json after.json \\
        --report regression_report.json

The report is what `scripts/agent_team/regression_budget.py` evaluates:

    before/after planned, refused, crashes · LOST · GAINED · new crashes · status changes
    (REFUSED<->CRASH) · refusal-code changes · primary-signature changes, each with the context.

**Sharding (Issue #67, O3)**: `--shard I/N` replays only the I-th of N deterministic partitions of
the corpus (by sorted context key, `index % N == I`), so gate-4's ~23-minute single-node snapshot
can be computed by N parallel runner jobs instead. `--merge OUT.json IN1.json IN2.json ...` takes
each shard's `--save` output and writes one document in the same shape `--save` would have produced
for the whole corpus — refusing to merge (raising `ShardMergeError`, never silently) a shard set
that is missing a context, duplicates one, or disagrees on `head_sha`/`corpus_hash`:

    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --shard 0/4 --save shard-0.json
    ...one such run per shard 0..N-1, typically in parallel CI jobs...
    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --merge head_snapshot.json shard-0.json shard-1.json shard-2.json shard-3.json

Shipped additively in shadow mode: the single-node path still runs, and a workflow-level
`--assert-equal` step reports (never fails the job on its own — `continue-on-error`, see
docs/wiki/architecture/agent-team-workflow.md, gate-4 section) whether the merged and single-node
snapshots agree; the single-node/replay path alone still decides gate-4. `--assert-equal` compares
case content and `sha`; soft metadata that may legitimately differ between an equivalent pair —
`corpus_hash`, `workers` (e.g. a single-node snapshot written by an older, pre-sharding script has
no `corpus_hash` at all) — is reported as a note, never a difference. The single-node path is
removed only once several real PRs show them identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CORPUS = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"


def corpus_contexts(path: Path = CORPUS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [case["context"] for case in data["cases"]]


class ShardMergeError(Exception):
    """A shard set cannot be safely merged — `--merge` must never merge silently."""


def parse_shard_spec(spec: str) -> tuple[int, int]:
    try:
        i_str, n_str = spec.split("/")
        i, n = int(i_str), int(n_str)
    except ValueError as exc:
        raise ValueError(f"invalid --shard {spec!r}: expected format I/N") from exc
    if n <= 0 or not (0 <= i < n):
        raise ValueError(f"invalid --shard {spec!r}: need 0 <= I < N and N > 0")
    return i, n


def sorted_context_keys(corpus: Path = CORPUS) -> list[str]:
    from spikes.failure_log_sweep.sweep import key_of  # noqa: WPS433 — see _run_one

    return sorted(key_of(c) for c in corpus_contexts(corpus))


def shard_contexts(spec: str, corpus: Path = CORPUS) -> list[dict]:
    """The I-th of N deterministic partitions of the corpus: sort all contexts by their context
    key, then take every context whose position in that order satisfies `index % N == I`. Depends
    only on the corpus content, never on file order, so a shard's contents are stable across runs
    and every context key lands in exactly one shard."""
    from spikes.failure_log_sweep.sweep import key_of  # noqa: WPS433 — see _run_one

    i, n = parse_shard_spec(spec)
    ordered = sorted(corpus_contexts(corpus), key=key_of)
    return [c for idx, c in enumerate(ordered) if idx % n == i]


def _corpus_hash(corpus: Path = CORPUS) -> str:
    return hashlib.sha256(corpus.read_bytes()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def merge_shards(shard_docs: list[dict], corpus: Path = CORPUS) -> dict:
    """Union of N `--shard`/`--save` documents into one document in the same shape `--save` would
    have produced for the whole corpus. Raises `ShardMergeError`, naming the problem, rather than
    ever merging an unsafe shard set: a `head_sha` disagreement, a `corpus_hash` disagreement, a
    context key produced by more than one shard, or a context key produced by none."""
    if not shard_docs:
        raise ShardMergeError("no shard documents given to merge")

    shas = {d.get("sha") for d in shard_docs}
    if len(shas) > 1:
        raise ShardMergeError(f"shard head_sha mismatch across shards: {sorted(s for s in shas if s)}")

    hashes = {d.get("corpus_hash") for d in shard_docs}
    if len(hashes) > 1:
        raise ShardMergeError(f"shard corpus_hash mismatch across shards: {sorted(h for h in hashes if h)}")

    merged: dict[str, dict] = {}
    for doc in shard_docs:
        for key, value in doc.get("results", {}).items():
            if key in merged:
                raise ShardMergeError(f"duplicate context key across shards: {key}")
            merged[key] = value

    expected = set(sorted_context_keys(corpus))
    missing = expected - merged.keys()
    if missing:
        raise ShardMergeError(
            f"missing shard(s): {len(missing)} context key(s) never produced by any shard, "
            f"e.g. {sorted(missing)[:3]}"
        )
    unexpected = merged.keys() - expected
    if unexpected:
        raise ShardMergeError(f"{len(unexpected)} context key(s) not present in the corpus, e.g. {sorted(unexpected)[:3]}")

    # The shards ran in parallel (typically as matrix CI jobs), so the wall-clock cost of the
    # sharded path is the slowest shard, not the sum of them — preserving that per-shard timing
    # information rather than discarding it.
    slowest_shard = round(max(float(d.get("seconds") or 0) for d in shard_docs), 1)
    return {
        "version": 1,
        "sha": next(iter(shas)),
        "corpus": shard_docs[0].get("corpus", str(corpus)),
        "corpus_hash": next(iter(hashes)),
        "workers": shard_docs[0].get("workers"),
        "seconds": slowest_shard,
        "written_at": _now_iso(),
        "results": dict(sorted(merged.items())),
    }


def normalize_for_compare(doc: dict) -> dict:
    """Strip the fields two equivalent snapshot runs may legitimately differ on — per-run timings
    (top-level `seconds`, per-context `ms`) and the writer timestamp — so the rest (`sha`, `corpus`,
    `corpus_hash`, `workers`, and each context's `status`/`code`/`sig`/`area`/`metrics`) can be
    compared for exact equality."""
    doc = dict(doc)
    doc.pop("seconds", None)
    doc.pop("written_at", None)
    doc.pop("shard", None)
    doc["results"] = {k: {kk: vv for kk, vv in v.items() if kk != "ms"} for k, v in doc.get("results", {}).items()}
    return doc


def snapshots_equal(a: dict, b: dict) -> bool:
    return not describe_snapshot_diff(a, b)


# Metadata that may legitimately differ between two equivalent snapshots — e.g. a single-node
# snapshot written by an older, pre-sharding script never recorded `corpus_hash` at all — so
# `describe_snapshot_diff` never treats a difference here as the snapshots being unequal; it is
# only ever a `describe_snapshot_notes` note. `sha` (the git commit the snapshot was computed at)
# stays a hard-compared field: a mismatch there means one side replayed the wrong commit.
_SOFT_METADATA_FIELDS = ("corpus_hash", "workers")


def describe_snapshot_diff(a: dict, b: dict) -> list[str]:
    """Human-readable mismatch descriptions between two snapshots (after normalizing volatile
    fields) — empty means they are equivalent. Compares case content (`status`/`code`/`sig`/`area`/
    `metrics` per context) and `sha`; see `describe_snapshot_notes` for the soft metadata fields."""
    na, nb = normalize_for_compare(a), normalize_for_compare(b)
    diffs = []
    if na.get("sha") != nb.get("sha"):
        diffs.append(f"sha: {na.get('sha')!r} != {nb.get('sha')!r}")
    keys_a, keys_b = set(na["results"]), set(nb["results"])
    if keys_a != keys_b:
        diffs.append(f"context keys differ: only in A={sorted(keys_a - keys_b)[:5]} only in B={sorted(keys_b - keys_a)[:5]}")
    for key in sorted(keys_a & keys_b):
        if na["results"][key] != nb["results"][key]:
            diffs.append(f"{key}: {na['results'][key]} != {nb['results'][key]}")
    return diffs


def describe_snapshot_notes(a: dict, b: dict) -> list[str]:
    """Soft-metadata mismatches between two snapshots (`corpus_hash`, `workers`) — reported for
    visibility but never counted as a difference by `describe_snapshot_diff`/`snapshots_equal`."""
    na, nb = normalize_for_compare(a), normalize_for_compare(b)
    return [f"{field}: {na.get(field)!r} != {nb.get(field)!r}" for field in _SOFT_METADATA_FIELDS
            if na.get(field) != nb.get(field)]


def _run_one(ctx: dict) -> tuple[str, dict]:
    # Imported inside the worker so `--workers N` forks cleanly and the import cost is per process.
    import dataclasses

    from app.demo import service as svc  # noqa: WPS433
    from app.vertical_slice.quality_metrics import measure_design, wet_adjacency_counts  # noqa: WPS433
    from spikes.failure_log_sweep.sweep import key_of, project_from_context, signature  # noqa: WPS433

    key = key_of(ctx)
    t0 = time.perf_counter()
    try:
        res = svc.generate_demo_design(project_from_context(ctx))
        # Issue #17 (repair): the architectural-quality REGRESSION test reads `metrics` instead of
        # replaying the corpus a third time in CI — see quality_metrics.py. `m5_wet_adjacent_count`
        # / `m5_wet_total_count` are folded in alongside `measure_design`'s own fields (not part of
        # `QualityMetrics`/`QualityOut`, only this snapshot's copy) so the corpus-level M5 share can
        # be pooled exactly — a plan's own ratio alone loses the denominator a corpus pool needs.
        metrics = dataclasses.asdict(measure_design(res.design))
        metrics["m5_wet_adjacent_count"], metrics["m5_wet_total_count"] = wet_adjacency_counts(res.design)
        out = {"status": "PLANNED", "sig": [list(s) for s in signature(res.design)], "area": res.design.gross_area_m2,
               "metrics": metrics}
    except svc.DemoGenerationError as exc:
        out = {"status": "REFUSED", "code": exc.code + ("+outline" if "כן מתאפשר" in exc.message else "")}
    except Exception as exc:  # noqa: BLE001 — a crash is a result, not an abort
        out = {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}"}
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["context"] = {k: ctx[k] for k in ("plot_width_m", "plot_depth_m", "street_facing_side", "built_area_m2",
                                          "footprint_width_m", "footprint_depth_m", "bedrooms", "wet_rooms",
                                          "safe_room", "open_plan")}
    return key, out


def run_all(workers: int = 1, corpus: Path = CORPUS, shard: str | None = None) -> dict:
    contexts = shard_contexts(shard, corpus) if shard else corpus_contexts(corpus)
    if workers <= 1:
        results = [_run_one(c) for c in contexts]
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            results = pool.map(_run_one, contexts, chunksize=4)
    return dict(sorted(results))


def _git_sha() -> str | None:
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=str(Path(__file__).resolve().parents[2])).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def save(path: Path, workers: int, corpus: Path = CORPUS, shard: str | None = None) -> dict:
    t0 = time.time()
    results = run_all(workers, corpus, shard=shard)
    doc = {"version": 1, "sha": _git_sha(), "corpus": str(corpus), "corpus_hash": _corpus_hash(corpus),
           "workers": workers, "seconds": round(time.time() - t0, 1), "written_at": _now_iso(),
           "results": results}
    if shard:
        doc["shard"] = shard
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return doc


def _status_counts(results: dict) -> dict:
    c = Counter(v["status"] for v in results.values())
    return {"planned": c.get("PLANNED", 0), "refused": c.get("REFUSED", 0), "crashes": c.get("CRASH", 0), "total": len(results)}


def compare(before_doc: dict, after_doc: dict) -> dict:
    before, after = before_doc["results"], after_doc["results"]
    keys = sorted(set(before) | set(after))
    lost, gained, new_crashes, status_changes, code_changes, sig_changes = [], [], [], [], [], []
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b is None or a is None:
            status_changes.append({"key": k, "context": (a or b)["context"], "before": b and b["status"], "after": a and a["status"],
                                   "note": "context present on one side only"})
            continue
        row = {"key": k, "context": a["context"], "before": b["status"], "after": a["status"]}
        if b["status"] == "PLANNED" and a["status"] != "PLANNED":
            lost.append({**row, "after_code": a.get("code")})
        elif b["status"] != "PLANNED" and a["status"] == "PLANNED":
            gained.append({**row, "area": a.get("area"), "asked": a["context"]["built_area_m2"]})
        elif b["status"] != a["status"]:
            status_changes.append(row)
        elif b["status"] == "REFUSED" and b.get("code") != a.get("code"):
            code_changes.append({**row, "before_code": b.get("code"), "after_code": a.get("code")})
        elif b["status"] == "PLANNED" and b["sig"] != a["sig"]:
            sig_changes.append({**row, "before_area": b.get("area"), "after_area": a.get("area")})
        if a["status"] == "CRASH" and b["status"] != "CRASH":
            new_crashes.append({**row, "error": a.get("code")})
    return {
        "version": 1,
        "base_sha": before_doc.get("sha"), "head_sha": after_doc.get("sha"),
        "before": _status_counts(before), "after": _status_counts(after),
        "lost": lost, "gained": gained, "crashes": new_crashes, "status_changes": status_changes,
        "refusal_code_changes": code_changes, "primary_signature_changes": sig_changes,
        "byte_identical_primaries": sum(1 for k in keys if k in before and k in after and before[k]["status"] == "PLANNED"
                                        and after[k]["status"] == "PLANNED" and before[k]["sig"] == after[k]["sig"]),
        "refusal_codes": {
            "before": dict(Counter(v.get("code") for v in before.values() if v["status"] == "REFUSED")),
            "after": dict(Counter(v.get("code") for v in after.values() if v["status"] == "REFUSED")),
        },
        "timing": {"before_seconds": before_doc.get("seconds"), "after_seconds": after_doc.get("seconds"),
                   "median_ms_before": _median([v["ms"] for v in before.values() if "ms" in v]),
                   "median_ms_after": _median([v["ms"] for v in after.values() if "ms" in v])},
    }


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def summarize(report: dict) -> str:
    b, a = report["before"], report["after"]
    lines = [
        f"planned before={b['planned']} after={a['planned']}   refused before={b['refused']} after={a['refused']}"
        f"   crashes before={b['crashes']} after={a['crashes']}",
        f"LOST={len(report['lost'])}  GAINED={len(report['gained'])}  new crashes={len(report['crashes'])}"
        f"  status changes={len(report['status_changes'])}  refusal-code changes={len(report['refusal_code_changes'])}"
        f"  primary-signature changes={len(report['primary_signature_changes'])}"
        f"  byte-identical primaries={report['byte_identical_primaries']}",
    ]
    for row in report["lost"]:
        lines.append(f"  LOST {row['context']} -> {row['after']} {row.get('after_code')}")
    for row in report["gained"]:
        pct = 100 * row["area"] / row["asked"] if row.get("area") and row.get("asked") else 0
        lines.append(f"  GAINED {row['context']} built {row.get('area')} ({pct:.0f}% of asked)")
    for row in report["crashes"]:
        lines.append(f"  CRASH {row['context']} {row.get('error')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", metavar="OUT.json")
    g.add_argument("--compare", nargs=2, metavar=("BEFORE.json", "AFTER.json"))
    g.add_argument("--merge", nargs="+", metavar="FILE",
                   help="--merge OUT.json IN1.json IN2.json ... : union of N --shard/--save documents")
    g.add_argument("--assert-equal", nargs=2, metavar=("A.json", "B.json"),
                   help="fail (exit 1) unless the two snapshots are equal after normalising volatile fields")
    ap.add_argument("--shard", metavar="I/N", help="with --save: replay only the I-th of N corpus shards")
    ap.add_argument("--report", metavar="REPORT.json", help="with --compare: write the machine-readable report here")
    ap.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    args = ap.parse_args()
    if args.shard and not args.save:
        ap.error("--shard is only meaningful together with --save")
    if args.save:
        doc = save(Path(args.save), args.workers, args.corpus, shard=args.shard)
        counts = _status_counts(doc["results"])
        shard_note = f" (shard {args.shard})" if args.shard else ""
        print(f"saved {counts['total']} scenarios{shard_note}: planned {counts['planned']} refused {counts['refused']} "
              f"crashes {counts['crashes']} in {doc['seconds']}s ({args.workers} workers)")
        return 0
    if args.merge:
        if len(args.merge) < 2:
            ap.error("--merge needs an output file and at least one shard file")
        out_path, *in_paths = args.merge
        shard_docs = [json.load(open(p, encoding="utf-8")) for p in in_paths]
        try:
            doc = merge_shards(shard_docs, args.corpus)
        except ShardMergeError as exc:
            print(f"merge refused: {exc}", file=sys.stderr)
            return 2
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        counts = _status_counts(doc["results"])
        print(f"merged {len(in_paths)} shard(s) into {counts['total']} scenarios: planned {counts['planned']} "
              f"refused {counts['refused']} crashes {counts['crashes']}")
        return 0
    if args.assert_equal:
        a = json.load(open(args.assert_equal[0], encoding="utf-8"))
        b = json.load(open(args.assert_equal[1], encoding="utf-8"))
        notes = describe_snapshot_notes(a, b)
        if notes:
            print(f"{len(notes)} metadata note(s) (not compared, never fail the assertion):")
            for n in notes:
                print(f"  {n}")
        diffs = describe_snapshot_diff(a, b)
        if diffs:
            print(f"snapshots differ ({len(diffs)} difference(s)):")
            for d in diffs[:20]:
                print(f"  {d}")
            return 1
        print(f"snapshots match: {len(normalize_for_compare(a)['results'])} context(s) identical")
        return 0
    before = json.load(open(args.compare[0], encoding="utf-8"))
    after = json.load(open(args.compare[1], encoding="utf-8"))
    report = compare(before, after)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
    print(summarize(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
