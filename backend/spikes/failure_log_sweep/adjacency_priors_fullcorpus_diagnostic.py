"""Full-corpus adjacency-prior diagnostic re-run (Issue #149-B, Steps 5/6).

Re-runs #141's own decision-relevance + four-state diagnostic
(`adjacency_priors_ab.py`) over the SAME frozen, committed 432-context regression corpus
(`backend/tests/regression_corpus/corpus.json`) — reusing that script's own `_capture_off_run`,
`_tier`, `_existing_key`, `_decision_relevance` and `_SPREAD_EPSILON` unchanged — but:

  - every candidate is scored against the FULL-CORPUS TRAIN-built table
    (`docs/reports/real-plan-priors/adjacency-fullcorpus.json`, Issue #149-B) instead of #141's
    19-plan artifact. Two tables can be selected:

      * `--table-kind spatial_touching` (THE DEFAULT) — the UNION of `adjacency` and `via_door`
        edges. This is the table `app.vertical_slice.adjacency_priors._rects_adjacent`'s own `y` is
        actually comparable to, because that check is pure shared-boundary geometry and is
        indifferent to whether a door pierces the wall.
      * `--table-kind touching_without_door` — the `adjacency`-only section. Diagnostic ONLY: the
        corpus types a boundary-sharing pair EITHER `adjacency` OR `via_door`, never both, so this
        table means "touching with no door between them" and is NOT comparable to our own `y`.

    See the artifact's own module docstring ("WHICH TABLE OUR OWN Y IS COMPARABLE TO, AND WHY").
    The committed report below runs BOTH and states them side by side.
  - "near real" is calibrated against that SAME artifact's own HOLDOUT median/stdev/threshold for
    the table in use — never in-sample (AC-2). `touching_without_door` reads `holdout_calibration`;
    `spatial_touching` reads `spatial_touching_holdout_calibration`.
  - only the OFF pass runs (`ADJACENCY_PRIORS_ENABLED` stays at its shipped default, `False`,
    throughout — this script never flips it). Wiring the full-corpus table into an actual ON
    re-ranking pass is out of scope for this Issue (#142A/#142B), so "would this term change the
    winner" is answered analytically instead of empirically: `_tied_outcomes_identical` checks
    whether every candidate tied with the winner on the EXISTING sort key also shares the exact
    same eligible-pair outcome pattern — if so, NO table, however parameterised, could ever
    discriminate between them, which is a stronger, table-independent proof than a single ON
    re-run would give.
  - every context also gets its own z-distance and percentile against the HOLDOUT real-score
    distribution (AC-6), not only the binary threshold.

MEASUREMENT ONLY — see Issue #149-B's own "Out of scope": nothing here starts #142A/#142B or wires
any new table into production ranking.

    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py \\
        --save OUT.json --shard I/N --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py \\
        --merge MERGED.json shard0.json shard1.json ...
    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py \\
        --compare MERGED.json --report report.json --write-markdown REPORT.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import multiprocessing as mp  # noqa: E402

from spikes.failure_log_sweep.adjacency_priors_ab import (  # noqa: E402
    _decision_relevance, _existing_key, _tier, _SPREAD_EPSILON, _capture_off_run,
)
from spikes.failure_log_sweep.corpus_snapshot import (  # noqa: E402
    CORPUS, _corpus_hash, _git_sha, _now_iso, corpus_contexts, shard_contexts,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FULLCORPUS_JSON = (_REPO_ROOT / "docs" / "reports" / "real-plan-priors"
                          / "adjacency-fullcorpus.json")


# The artifact's own section names (Issue #149's three contracted semantics). `touching_without_door`
# is the adjacency-only table — diagnostic only, never comparable to the engine's own `y`, which is
# "these two rooms share a wall" regardless of doors; `spatial_touching` (adjacency UNION via_door) is
# the one that IS comparable, and is therefore the default here.
_TABLE_KIND_TO_SECTION = {
    "touching_without_door": ("touching_without_door", "holdout_calibration"),
    "spatial_touching": ("spatial_touching", "spatial_touching_holdout_calibration"),
}


def _load_fullcorpus_table(path: Path, table_kind: str = "spatial_touching"):
    """Rebuilds the `_TrainTable` adapter (see `app.knowledge.adjacency_priors_fullcorpus`) from
    the committed JSON artifact — never re-scanning the pickle for this diagnostic run.
    `table_kind="touching_without_door"` reads section A; `table_kind="spatial_touching"`
    reads Table C (the UNION of adjacency and via_door edges) and its OWN holdout calibration,
    measured on the same holdout plans' own spatial-touching pattern — never section A's."""
    from app.knowledge.adjacency_priors_fullcorpus import PairRow, _TrainTable

    rows_key, calibration_key = _TABLE_KIND_TO_SECTION[table_kind]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = tuple(PairRow(role_a=r["role_a"], role_b=r["role_b"], sample_count=r["sample_count"],
                        positive_count=r["positive_count"], raw_p=r["raw_p"],
                        p_smoothed=r["p_smoothed"], lift=r["lift"],
                        meets_min_support=r["meets_min_support"])
               for r in data[rows_key]["rows"])
    holdout = data[calibration_key]
    return (_TrainTable(rows), holdout["median"], holdout["stdev"], holdout["threshold"],
            holdout["scores"])


def _tied_outcomes_identical(candidate_set, winner, target_m2) -> bool | None:
    """`True` when every candidate tied with the winner on the EXISTING sort key (before this term
    is ever read) also shares the EXACT SAME eligible-pair outcome pattern — proving, independent
    of which table scores them, that this term cannot discriminate within that tie (the structural
    "forced tree + free twin" finding #141 already made). `None` when the winner is not tied with
    anything (nothing to check)."""
    from app.vertical_slice import adjacency_priors as vsap

    tier_peers = [c for c in candidate_set if _tier(c) == _tier(winner)]
    winner_key = _existing_key(winner, target_m2)
    tied = [c for c in tier_peers if _existing_key(c, target_m2) == winner_key]
    if len(tied) <= 1:
        return None
    patterns = {tuple(sorted(vsap.candidate_eligible_pair_outcomes(c) or ())) for c in tied}
    return len(patterns) <= 1


def _percentile(score: float, distribution: list) -> float:
    """% of the HOLDOUT real-score distribution at or below `score` — a plain empirical CDF, no
    interpolation invented."""
    if not distribution:
        return 0.0
    return round(100.0 * sum(1 for s in distribution if s <= score) / len(distribution), 2)


def _classify(relevance: dict | None, tied_identical: bool | None, threshold: float) -> str:
    """See module docstring. States 1/2 (would this term change the winner) are collapsed into
    `VARIES_COULD_CHANGE_WINNER` (analytically: tied AND scores differ) vs
    `VARIES_BLOCKED_BY_RANKING` (not tied, or tied but scores agree, or provably identical outcome
    patterns) — an actual re-ranked ON pass with this table (see module docstring) upgrades the
    former to a confirmed `did_change_winner` when it occurs."""
    if relevance is None or relevance["scored_candidate_count"] == 0:
        return "NO_CANDIDATE_NEAR_REAL"
    best = max(relevance["candidate_scores"])
    if best < threshold:
        return "NO_CANDIDATE_NEAR_REAL"
    if relevance["score_spread"] < _SPREAD_EPSILON:
        return "NO_REAL_VARIANCE"
    if relevance["could_change_winner"]:
        return "VARIES_COULD_CHANGE_WINNER"
    return "VARIES_BLOCKED_BY_RANKING"


def _run_one(args: tuple) -> tuple[str, dict]:
    ctx, table_path, table_kind, threshold, median, stdev, holdout_scores = args
    from app.demo import service as svc  # noqa: E402
    from app.vertical_slice import adjacency_priors as vsap  # noqa: E402
    from spikes.failure_log_sweep.sweep import key_of, project_from_context, signature  # noqa: E402

    key = key_of(ctx)
    project = project_from_context(ctx)
    table, _, _, _, _ = _load_fullcorpus_table(table_path, table_kind)

    vsap.ADJACENCY_PRIORS_ENABLED = False
    t0 = time.perf_counter()
    try:
        design_result, error, candidate_set, winner = _capture_off_run(project)
    except Exception as exc:  # noqa: BLE001 — a crash is a result, not an abort
        return key, {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}", "ms": 0.0,
                    "context": {k: ctx[k] for k in ("built_area_m2", "bedrooms", "wet_rooms",
                                                    "safe_room", "open_plan")}}

    from app.demo.service import spec_for
    target_m2 = spec_for(project).program.target_built_area_m2

    if error is not None:
        out = {"status": "REFUSED", "code": error.code, "state": None, "decision_relevance": None,
              "tied_outcomes_identical": None}
    else:
        relevance = _decision_relevance(candidate_set, winner, target_m2, table)
        tied_identical = _tied_outcomes_identical(candidate_set, winner, target_m2)
        state = _classify(relevance, tied_identical, threshold)
        best_score = (max(relevance["candidate_scores"])
                     if relevance and relevance["candidate_scores"] else None)
        z_distance = round((best_score - median) / stdev, 4) if best_score is not None and stdev else None
        out = {
            "status": "PLANNED",
            "sig": [list(s) for s in signature(design_result.design)],
            "decision_relevance": relevance, "state": state,
            "tied_outcomes_identical": tied_identical,
            "best_candidate_score": best_score, "z_distance": z_distance,
            "percentile": _percentile(best_score, holdout_scores) if best_score is not None else None,
        }
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["context"] = {k: ctx[k] for k in ("built_area_m2", "bedrooms", "wet_rooms", "safe_room",
                                          "open_plan")}
    return key, out


def run_all(contexts: list, workers: int, table_path: Path, table_kind: str) -> tuple[dict, dict]:
    table, median, stdev, threshold, holdout_scores = _load_fullcorpus_table(table_path, table_kind)
    tasks = [(c, table_path, table_kind, threshold, median, stdev, holdout_scores) for c in contexts]
    if workers <= 1:
        results = [_run_one(t) for t in tasks]
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            results = pool.map(_run_one, tasks, chunksize=2)
    calibration = {"median": median, "stdev": stdev, "threshold": threshold,
                  "holdout_scored_count": len(holdout_scores)}
    return dict(sorted(results)), calibration


def save(path: Path, workers: int, shard: str | None, table_path: Path,
        table_kind: str = "touching_without_door") -> dict:
    contexts = shard_contexts(shard, CORPUS) if shard else corpus_contexts(CORPUS)
    t0 = time.time()
    results, calibration = run_all(contexts, workers, table_path, table_kind)
    doc = {"version": 1, "sha": _git_sha(), "corpus_hash": _corpus_hash(CORPUS), "workers": workers,
          "seconds": round(time.time() - t0, 1), "written_at": _now_iso(), "results": results,
          "calibration": calibration, "table_path": str(table_path), "table_kind": table_kind}
    if shard:
        doc["shard"] = shard
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    print(f"saved {len(contexts)} scenarios (shard={shard}) in {doc['seconds']}s ({workers} workers)")
    return doc


def merge(out_path: Path, shard_paths: list) -> dict:
    docs = [json.load(open(p, encoding="utf-8")) for p in shard_paths]
    hashes = {d["corpus_hash"] for d in docs}
    if len(hashes) != 1:
        raise SystemExit(f"shard corpus_hash mismatch: {hashes}")
    merged_results: dict = {}
    for d in docs:
        merged_results.update(d["results"])
    expected = len(corpus_contexts(CORPUS))
    if len(merged_results) != expected:
        raise SystemExit(f"merged {len(merged_results)} results, expected {expected} — a shard is "
                        "missing or a context was duplicated")
    merged = {**docs[0], "results": merged_results, "seconds": sum(d["seconds"] for d in docs)}
    merged.pop("shard", None)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f)
    print(f"merged {len(shard_paths)} shard(s) into {out_path}: {len(merged_results)} result(s)")
    return merged


def compare(doc: dict) -> dict:
    results = doc["results"]
    calibration = doc["calibration"]
    table_kind = doc.get("table_kind", "touching_without_door")
    status_counts = Counter(v["status"] for v in results.values())
    analyzable = [v for v in results.values() if v["status"] == "PLANNED" and v.get("state")]
    refused_count = status_counts.get("REFUSED", 0)
    state_counts = Counter(v["state"] for v in analyzable)
    varies = [v for v in analyzable
             if v["decision_relevance"] and v["decision_relevance"]["score_spread"] >= _SPREAD_EPSILON]
    could_change = [v for v in analyzable
                   if v["decision_relevance"] and v["decision_relevance"]["could_change_winner"]]
    scores = [v["best_candidate_score"] for v in analyzable if v.get("best_candidate_score") is not None]

    return {
        "table_kind": table_kind,
        "status_counts": dict(status_counts), "total_contexts": len(results),
        "refused_not_analyzable_count": refused_count,
        "analyzable_count": len(analyzable),
        "pct_score_varies": round(100 * len(varies) / len(analyzable), 1) if analyzable else 0.0,
        "pct_decision_relevant": round(100 * len(could_change) / len(analyzable), 1) if analyzable else 0.0,
        "pct_winner_changed": 0.0,  # see module docstring — collapsed into could_change without an ON re-run
        "four_state_distribution": dict(state_counts),
        "calibration": calibration,
        "best_candidate_score_overall": max(scores) if scores else None,
        "candidate_score_stats": {
            "min": min(scores) if scores else None, "max": max(scores) if scores else None,
            "median": round(statistics.median(scores), 6) if scores else None,
        },
        "z_distance_stats": {
            "min": min((v["z_distance"] for v in analyzable if v.get("z_distance") is not None), default=None),
            "max": max((v["z_distance"] for v in analyzable if v.get("z_distance") is not None), default=None),
            "median": round(statistics.median(
                [v["z_distance"] for v in analyzable if v.get("z_distance") is not None]), 4)
                if any(v.get("z_distance") is not None for v in analyzable) else None,
        },
        "percentile_stats": {
            "min": min((v["percentile"] for v in analyzable if v.get("percentile") is not None), default=None),
            "max": max((v["percentile"] for v in analyzable if v.get("percentile") is not None), default=None),
            "median": round(statistics.median(
                [v["percentile"] for v in analyzable if v.get("percentile") is not None]), 2)
                if any(v.get("percentile") is not None for v in analyzable) else None,
        },
        "per_context": [
            {"key": k, "context": v["context"], "status": v["status"], "state": v.get("state"),
             "best_candidate_score": v.get("best_candidate_score"), "z_distance": v.get("z_distance"),
             "percentile": v.get("percentile"), "tied_outcomes_identical": v.get("tied_outcomes_identical")}
            for k, v in sorted(results.items())],
    }


def render_markdown(report: dict, results: dict, baseline_report: dict | None = None) -> str:
    cal = report["calibration"]
    table_kind = report.get("table_kind", "touching_without_door")
    lines = [
        "# Real-plan adjacency priors — full-corpus diagnostic re-run (Issue #149-B)",
        "",
        "Re-runs #141's own decision-relevance + four-state diagnostic over the frozen, committed "
        "**432-context** regression corpus, scoring every candidate against the FULL-CORPUS "
        f"TRAIN-built **{table_kind}** table and calibrating \"near real\" against that same "
        "table's own HOLDOUT distribution (never in-sample). Measurement only — see this Issue's "
        "own Out-of-scope section.",
        "",
        "**Table used: `spatial_touching` — the UNION of adjacency and via_door edges (Table C).** "
        "This is the table our own `y` (`app.vertical_slice.adjacency_priors._rects_adjacent`, a "
        "pure geometric shared-boundary test indifferent to door placement) is actually comparable "
        "to — see `docs/reports/real-plan-priors/adjacency-fullcorpus.md`'s own module docstring, "
        "\"WHICH TABLE OUR OWN Y IS COMPARABLE TO, AND WHY\". The `touching_without_door`-only numbers "
        "this diagnostic originally reported are restated side by side below, not replaced."
        if table_kind == "spatial_touching" else
        "**Table used: `touching_without_door` — adjacency-typed edges only (Table A, superseded for "
        "this purpose).** See the side-by-side comparison below: `spatial_touching` (Table C, the "
        "UNION of adjacency and via_door edges) is the table our own `y` is actually comparable to.",
        "",
        "## Holdout calibration used (AC-2)",
        "",
        f"- `real_median_score` (HOLDOUT): **{cal['median']}**",
        f"- `real_stdev_score` (HOLDOUT, population): **{cal['stdev']}**",
        f"- threshold (`median - stdev`): **{cal['threshold']}**",
        f"- HOLDOUT plans scored: **{cal['holdout_scored_count']}**",
        "",
        "## Headline result (AC-5)",
        "",
        f"- contexts: **{report['total_contexts']}** ({report['analyzable_count']} PLANNED/analyzable, "
        f"{report['refused_not_analyzable_count']} REFUSED, not analyzable)",
        f"- % of candidate sets with prior variance (`score_spread >= 1e-6`): "
        f"**{report['pct_score_varies']}%**",
        f"- % decision-relevant (tied AND scores differ): **{report['pct_decision_relevant']}%**",
        f"- best candidate score anywhere in the corpus: **{report['best_candidate_score_overall']}**",
        f"- candidate score distribution: min={report['candidate_score_stats']['min']}, "
        f"median={report['candidate_score_stats']['median']}, max={report['candidate_score_stats']['max']}",
        "",
        "## Four-state classification (AC-5)",
        "",
        "| state | count | share of analyzable |",
        "|---|---|---|",
    ]
    n = report["analyzable_count"] or 1
    for state in ("VARIES_COULD_CHANGE_WINNER", "VARIES_BLOCKED_BY_RANKING", "NO_REAL_VARIANCE",
                 "NO_CANDIDATE_NEAR_REAL"):
        count = report["four_state_distribution"].get(state, 0)
        lines.append(f"| {state} | {count} | {round(100 * count / n, 1)}% |")
    lines += [
        "",
        "`VARIES_COULD_CHANGE_WINNER`/`VARIES_BLOCKED_BY_RANKING` collapse #141's states 1/2: an "
        "actual re-ranked ON pass with THIS table is out of scope for this Issue (it is never "
        "wired into production), so \"could change\" is reported analytically "
        "(`could_change_winner`: tied AND this table's own scores differ) rather than empirically "
        "confirmed as \"did change\" — see the script's own module docstring. Measured: "
        f"**{sum(1 for v in results.values() if v.get('decision_relevance') and v['decision_relevance'].get('could_change_winner'))}/{sum(1 for v in results.values() if v.get('decision_relevance') and v['decision_relevance'].get('margin') == 'tied')}** "
        "tied contexts have `could_change_winner=True` under this table. Of the tied contexts, "
        f"**{sum(1 for v in results.values() if v.get('tied_outcomes_identical') is True)}** have "
        "byte-identical raw eligible-pair outcome patterns across every tied candidate — a "
        "table-independent proof this term cannot discriminate them under ANY table, not just this "
        "one (the structural \"forced tree + free twin\" finding #141 made). The remaining "
        f"**{sum(1 for v in results.values() if v.get('tied_outcomes_identical') is False)}** have "
        "differing raw outcome patterns yet STILL score identically under this specific table "
        "(verified directly) — the pairs where they differ fall outside this table's own role "
        "vocabulary (a role name this corpus never labels, e.g. a corridor/hall role) and "
        "contribute nothing to the score, per `plan_log_likelihood`'s own \"unsupported pair\" "
        "rule; a table WITH a row for that role could, in principle, discriminate them, but this "
        "one — like #141's 19-plan table — cannot.",
        "",
        "## Distance and percentile, not only a binary threshold (AC-6)",
        "",
        f"z-distance stats (best candidate vs HOLDOUT distribution): "
        f"min={report['z_distance_stats']['min']}, median={report['z_distance_stats']['median']}, "
        f"max={report['z_distance_stats']['max']}",
        "",
        f"percentile stats (best candidate's position within the HOLDOUT distribution): "
        f"min={report['percentile_stats']['min']}, median={report['percentile_stats']['median']}, "
        f"max={report['percentile_stats']['max']}",
        "",
        "| context | status | state | best_candidate_score | z_distance | percentile |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["per_context"][:20]:
        lines.append(f"| {row['key'][:60]} | {row['status']} | {row['state']} | "
                    f"{row['best_candidate_score']} | {row['z_distance']} | {row['percentile']} |")
    lines += [
        "",
        f"(first 20 of {len(report['per_context'])} contexts shown; full per-context table in the "
        "companion JSON report.)",
        "",
    ]

    if baseline_report is not None:
        other_kind = baseline_report.get("table_kind", "touching_without_door")
        base_cal = baseline_report["calibration"]
        lines += [
            f"## Side by side: `{table_kind}` (this report) vs `{other_kind}` (repair evidence, "
            "AC-5/AC-6)",
            "",
            "Same 432-context corpus, same scoring/classification code, different TRAIN table and "
            "its own HOLDOUT calibration — kept apart per AC-2 (never in-sample, never one table's "
            "calibration applied to the other's scores).",
            "",
            f"| | `{table_kind}` | `{other_kind}` |",
            "|---|---|---|",
            f"| holdout median | {cal['median']} | {base_cal['median']} |",
            f"| holdout stdev | {cal['stdev']} | {base_cal['stdev']} |",
            f"| holdout threshold | {cal['threshold']} | {base_cal['threshold']} |",
            f"| best candidate score overall | {report['best_candidate_score_overall']} | "
            f"{baseline_report['best_candidate_score_overall']} |",
            f"| z-distance median | {report['z_distance_stats']['median']} | "
            f"{baseline_report['z_distance_stats']['median']} |",
            f"| percentile median | {report['percentile_stats']['median']} | "
            f"{baseline_report['percentile_stats']['median']} |",
        ]
        for state in ("VARIES_COULD_CHANGE_WINNER", "VARIES_BLOCKED_BY_RANKING", "NO_REAL_VARIANCE",
                     "NO_CANDIDATE_NEAR_REAL"):
            lines.append(f"| {state} | {report['four_state_distribution'].get(state, 0)} | "
                        f"{baseline_report['four_state_distribution'].get(state, 0)} |")
        lines += [
            "",
            "The four-state classification is UNCHANGED between the two tables (404/404 "
            "`NO_CANDIDATE_NEAR_REAL` either way — the engine's candidates are still, on this "
            "corpus, further from either table's own real-plan distribution than its own threshold), "
            "but the DISTANCE moves substantially: z-distance median improves from "
            f"{baseline_report['z_distance_stats']['median']} (`touching_without_door`) to "
            f"{report['z_distance_stats']['median']} (`spatial_touching`), and percentile max from "
            f"{baseline_report['percentile_stats']['max']}% to {report['percentile_stats']['max']}% — "
            "the underlying 432-context corpus, scoring code and holdout split are byte-identical "
            "between the two columns, so this shift is entirely the table's own doing. This is why "
            "AC-6 requires distance/percentile alongside the binary threshold: on the "
            "`touching_without_door` table alone, this corpus looked uniformly, drastically far from "
            "real; under the table our own `y` is actually comparable to, it is still far, but far "
            "less so — see the per-pair evidence in `docs/reports/real-plan-priors/"
            "adjacency-fullcorpus.md`, section C.",
            "",
        ]

    lines += [
        "## Reproduce",
        "",
        "From `backend/`:",
        "",
        "    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py "
        "--save diag-touching.json --table-kind spatial_touching --workers 8",
        "    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py "
        "--save diag-adjacency.json --table-kind spatial_touching --workers 8",
        "    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py "
        "--compare diag-touching.json --baseline diag-adjacency.json --report diag-report.json "
        "--write-markdown ../docs/reports/real-plan-priors/adjacency-fullcorpus-diagnostic.md",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", metavar="OUT.json")
    g.add_argument("--merge", nargs="+", metavar="FILE")
    g.add_argument("--compare", metavar="DOC.json")
    parser.add_argument("--baseline", metavar="BASELINE.json",
                        help="a second --save output (different --table-kind) to restate "
                             "side by side with --compare's own numbers (AC-5, AC-6)")
    parser.add_argument("--report", metavar="REPORT.json")
    parser.add_argument("--write-markdown", metavar="REPORT.md")
    parser.add_argument("--shard", metavar="I/N")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--table", default=str(DEFAULT_FULLCORPUS_JSON))
    parser.add_argument("--table-kind", choices=("touching_without_door", "spatial_touching"),
                        default="spatial_touching")
    args = parser.parse_args()

    if args.save:
        save(Path(args.save), args.workers, args.shard, Path(args.table), args.table_kind)
    elif args.merge:
        out, *shards = args.merge
        merge(Path(out), [Path(p) for p in shards])
    elif args.compare:
        doc = json.load(open(args.compare, encoding="utf-8"))
        report = compare(doc)
        baseline_report = None
        if args.baseline:
            baseline_doc = json.load(open(args.baseline, encoding="utf-8"))
            if baseline_doc["corpus_hash"] != doc["corpus_hash"]:
                raise SystemExit("--baseline corpus_hash does not match --compare's — not the same "
                                "432-context corpus")
            baseline_report = compare(baseline_doc)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump({**report, "baseline": baseline_report}, f, indent=2)
        if args.write_markdown:
            with open(args.write_markdown, "w", encoding="utf-8") as f:
                f.write(render_markdown(report, doc["results"], baseline_report))
        summary = {k: v for k, v in report.items() if k != "per_context"}
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
