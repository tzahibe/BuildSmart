"""A/B + decision-relevance analysis of the real-plan adjacency prior (Issue #141, Steps 3/4/6)
over the frozen, committed 432-context regression corpus (`tests/regression_corpus/corpus.json`) —
flag OFF (shipped default) vs flag ON (`ADJACENCY_PRIORS_ENABLED = True`).

    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --save-off off.json --shard I/N --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --save-on  on.json  --shard I/N --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --merge-off merged_off.json off-0.json off-1.json ...
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --merge-on  merged_on.json  on-0.json  on-1.json ...
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --compare merged_off.json merged_on.json --report report.json

Sharded the same way `room_proportion_priors_ab.py` (Issue #140) is, for the same reason: this
replays the whole corpus twice, and the OFF side does substantially more work per context (see
"Decision relevance" below).

DECISION RELEVANCE (Step 3/4, the OFF side only — "what candidates existed" does not depend on the
flag): for every context, the OFF run is instrumented to capture (a) the exact candidate list
`concept_generator.generate_concepts` produced for the outline that ended up winning
(`app.demo.service._select_plans`'s own return value identifies the winning `ConceptCandidate` by
object identity; `generate_concepts` is wrapped to record every call it makes during that one
`generate_demo_design`, and the call whose returned candidates literally CONTAIN the winning
object — by `is`, not equality — is the winner's candidate set; robust regardless of how many
outlines/re-runs `service.py`'s own outline search performs, since it depends on identity
containment, never call order or count).

Within that candidate set, restricted to candidates in the SAME TIER as the winner (`accepted` /
`tier2` / `quality` — `generate_concepts` never compares across tiers when ranking), this script
computes each candidate's OWN adjacency log-likelihood (`adjacency_priors.
candidate_eligible_pair_outcomes` + `app.knowledge.adjacency_priors.plan_log_likelihood`, i.e. the
exact function the runtime signal itself uses, called directly and unconditionally — not gated by
`ADJACENCY_PRIORS_ENABLED`, since this is a measurement, not the ranking decision), each candidate's
"existing key" (the sort-key tuple `generate_concepts` ranks that tier by, EXCLUDING the
room-proportion and adjacency terms), and from those: `score_spread` (max-min of every candidate's
own score, among candidates that HAVE one), `margin` (`"tied"` when >=1 OTHER candidate shares the
winner's exact existing key — the only condition under which a lower-precedence term can matter at
all — else `"decisive"`), `could_change_winner` (margin is `"tied"` AND the tied group's own scores
are not all equal), and `did_change_winner` (measured directly: the SAME context run again with the
flag ON, comparing realized-plan signatures — exactly `primary_signature_changes`' own definition).

FOUR-STATE CLASSIFICATION (Step 4): each context lands in exactly one of:
  1. VARIES_AND_CHANGES_WINNER   — ranking + prior work together
  2. VARIES_BUT_WINNER_UNCHANGED — RANKING ARCHITECTURE / precedence is the ceiling
  3. NO_REAL_VARIANCE            — CANDIDATE / TOPOLOGY DIVERSITY is the ceiling
  4. NO_CANDIDATE_NEAR_REAL      — CANDIDATE GENERATION / EXPRESSIVENESS is the ceiling

Priority order when more than one condition could apply: (4) is checked first — a candidate set
where NOTHING is close to how real plans behave dominates any variance question; then (3) — no real
score variance to work with; then whether the ACTUAL A/B run changed the winner, splitting the
remainder into (1)/(2). A context is folded into (4) when it has zero SCORABLE candidates at all
(no eligible pair anywhere has a supported artifact row) — the strongest form of "not near a real
plan": there is no adjacency evidence to compare at all, not merely a low score.

"Near the real distribution" is calibrated against the SAME 19-plan corpus the artifact itself was
measured from: every real plan is scored against its own table (in-sample, an honestly-acknowledged
optimism — the real corpus IS the population `adjacency.json` was built from) via
`_real_corpus_reference_scores`, giving a median and population stdev; a context lands in state (4)
when its BEST scored candidate still falls more than one of that corpus's own stdevs below that
median.
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

from spikes.failure_log_sweep.corpus_snapshot import (  # noqa: E402
    CORPUS, _corpus_hash, _git_sha, _now_iso, corpus_contexts, shard_contexts,
)

#: Degenerate spread floor — below this, candidates are treated as scoring "the same" (state 3),
#: never a manufactured non-zero spread out of floating-point noise.
_SPREAD_EPSILON = 1e-6


def _real_corpus_reference_scores() -> list[float]:
    """Every one of the 19 real corpus plans, scored against the SAME committed artifact table —
    see module docstring, "NEAR THE REAL DISTRIBUTION"."""
    from app.knowledge import adjacency_priors as ap

    table = ap.load_priors_table()
    plans, _, _ = ap.load_plan_role_adjacencies()
    scores = []
    for plan in plans:
        roles = sorted(plan.role_zone_ids)
        outcomes = [(a, b, ap._pair_touches(plan, a, b))
                   for a, b in ap.eligible_pairs_for_roles(roles)]
        score = ap.plan_log_likelihood(outcomes, table)
        if score is not None:
            scores.append(score)
    return scores


def _tier(candidate) -> str:
    if candidate.quality_repartitioned:
        return "quality"
    if candidate.repartitioned:
        return "tier2"
    return "accepted"


def _existing_key(candidate, target_m2: float | None) -> tuple:
    """The sort-key tuple `concept_generator.generate_concepts` ranks a candidate's own tier by,
    EXCLUDING the room-proportion-priors and adjacency-priors terms (both constants under this
    script's own instrumentation — it never enables either flag while capturing candidates)."""
    if target_m2 is None:
        return (candidate.over_preferred or candidate.shrunk, candidate.over_preferred)
    if candidate.repartitioned and not candidate.quality_repartitioned:
        return (round(abs(candidate.used_area_m2 - target_m2), 4),
               round(candidate.used_area_m2, 4), candidate.strategy.value)
    return (round(abs(candidate.used_area_m2 - target_m2), 4),
           candidate.over_preferred or candidate.shrunk, candidate.over_preferred,
           round(candidate.used_area_m2, 4), candidate.strategy.value)


def _capture_off_run(project):
    """Runs `generate_demo_design` once (flag OFF, the shipped default) with `generate_concepts`
    and `_select_plans` instrumented — see module docstring, "DECISION RELEVANCE"."""
    import app.demo.service as svc
    from app.vertical_slice import concept_generator as generator

    captured_generated: list = []
    real_generate_concepts = generator.generate_concepts
    real_select_plans = svc._select_plans
    captured_selection: list = []

    def wrapped_generate_concepts(spec, wing_candidates):
        result = real_generate_concepts(spec, wing_candidates)
        captured_generated.append(result)
        return result

    def wrapped_select_plans(*args, **kwargs):
        result = real_select_plans(*args, **kwargs)
        captured_selection.append(result)
        return result

    generator.generate_concepts = wrapped_generate_concepts
    svc._select_plans = wrapped_select_plans
    try:
        design_result = svc.generate_demo_design(project)
        error = None
    except svc.DemoGenerationError as exc:
        design_result, error = None, exc
    finally:
        generator.generate_concepts = real_generate_concepts
        svc._select_plans = real_select_plans

    selection = captured_selection[0] if captured_selection else None
    winner = selection.primary[1].concept if selection is not None else None
    candidate_set = None
    if winner is not None:
        for generated in captured_generated:
            if any(c is winner for c in generated.candidates):
                candidate_set = generated.candidates
                break
    return design_result, error, candidate_set, winner


def _decision_relevance(candidate_set, winner, target_m2, table):
    """`None` when there is nothing to analyze (a refusal before any candidate set existed);
    otherwise the per-candidate-set measurement Step 3/4 requires."""
    from app.vertical_slice import adjacency_priors as vsap

    if candidate_set is None or winner is None:
        return None
    tier_peers = [c for c in candidate_set if _tier(c) == _tier(winner)]
    scores: dict[int, float] = {}
    for c in tier_peers:
        outcomes = vsap.candidate_eligible_pair_outcomes(c)
        if not outcomes:
            continue
        score = None
        from app.knowledge.adjacency_priors import plan_log_likelihood
        score = plan_log_likelihood(outcomes, table)
        if score is not None:
            scores[id(c)] = score

    winner_key = _existing_key(winner, target_m2)
    tied_ids = [id(c) for c in tier_peers if _existing_key(c, target_m2) == winner_key]
    margin = "tied" if len(tied_ids) > 1 else "decisive"
    tied_scores = {round(scores[i], 6) for i in tied_ids if i in scores}
    could_change_winner = margin == "tied" and len(tied_scores) >= 2

    defined = list(scores.values())
    score_spread = round(max(defined) - min(defined), 6) if len(defined) >= 2 else 0.0
    return {
        "candidate_count": len(tier_peers),
        "scored_candidate_count": len(defined),
        "candidate_scores": [round(v, 6) for v in defined],
        "score_spread": score_spread,
        "margin": margin,
        "tied_count": len(tied_ids),
        "could_change_winner": could_change_winner,
        "winner_score": scores.get(id(winner)),
    }


def _classify(relevance: dict | None, did_change_winner: bool, real_median: float,
             real_stdev: float) -> str:
    if relevance is None or relevance["scored_candidate_count"] == 0:
        return "NO_CANDIDATE_NEAR_REAL"
    best = max(relevance["candidate_scores"])
    if best < real_median - real_stdev:
        return "NO_CANDIDATE_NEAR_REAL"
    if relevance["score_spread"] < _SPREAD_EPSILON:
        return "NO_REAL_VARIANCE"
    return "VARIES_AND_CHANGES_WINNER" if did_change_winner else "VARIES_BUT_WINNER_UNCHANGED"


def _run_one(args: tuple[dict, float, float]) -> tuple[str, dict]:
    ctx, real_median, real_stdev = args
    from app.demo import service as svc  # noqa: E402
    from app.knowledge import adjacency_priors as ap  # noqa: E402
    from app.vertical_slice import adjacency_priors as vsap  # noqa: E402
    from app.vertical_slice.quality_metrics import measure_design  # noqa: E402
    from spikes.failure_log_sweep.sweep import key_of, project_from_context, signature  # noqa: E402

    key = key_of(ctx)
    project = project_from_context(ctx)
    table = ap.load_priors_table()

    vsap.ADJACENCY_PRIORS_ENABLED = False
    t0 = time.perf_counter()
    try:
        design_result, error, candidate_set, winner = _capture_off_run(project)
    except Exception as exc:  # noqa: BLE001 — a crash is a result, not an abort
        out = {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}", "ms": 0.0}
        out["context"] = {k: ctx[k] for k in ("plot_width_m", "plot_depth_m", "street_facing_side",
                                              "built_area_m2", "footprint_width_m",
                                              "footprint_depth_m", "bedrooms", "wet_rooms",
                                              "safe_room", "open_plan")}
        return key, out

    from app.demo.service import spec_for
    spec = spec_for(project)
    target_m2 = spec.program.target_built_area_m2

    if error is not None:
        off = {"status": "REFUSED", "code": error.code}
        relevance = None
    else:
        off = {"status": "PLANNED", "sig": [list(s) for s in signature(design_result.design)],
              "area": design_result.design.gross_area_m2,
              "m5_wet_adjacency_ratio": measure_design(design_result.design).m5_wet_adjacency_ratio,
              "m6_public_zone_contiguous": measure_design(design_result.design).m6_public_zone_contiguous}
        relevance = _decision_relevance(candidate_set, winner, target_m2, table)

    vsap.ADJACENCY_PRIORS_ENABLED = True
    try:
        on_result = svc.generate_demo_design(project)
        on = {"status": "PLANNED", "sig": [list(s) for s in signature(on_result.design)],
             "area": on_result.design.gross_area_m2,
             "m5_wet_adjacency_ratio": measure_design(on_result.design).m5_wet_adjacency_ratio,
             "m6_public_zone_contiguous": measure_design(on_result.design).m6_public_zone_contiguous}
    except svc.DemoGenerationError as exc:
        on = {"status": "REFUSED", "code": exc.code}
    except Exception as exc:  # noqa: BLE001
        on = {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}"}
    finally:
        vsap.ADJACENCY_PRIORS_ENABLED = False

    did_change_winner = (
        (off["status"] == "PLANNED") != (on["status"] == "PLANNED")
        or (off["status"] == "PLANNED" and on["status"] == "PLANNED" and off["sig"] != on["sig"])
        or (off["status"] == "REFUSED" and on["status"] == "REFUSED"
            and off.get("code") != on.get("code")))

    state = _classify(relevance, did_change_winner, real_median, real_stdev)

    out = {**off, "ms": round((time.perf_counter() - t0) * 1000, 1), "on": on,
          "did_change_winner": did_change_winner, "decision_relevance": relevance, "state": state}
    out["context"] = {k: ctx[k] for k in ("plot_width_m", "plot_depth_m", "street_facing_side",
                                          "built_area_m2", "footprint_width_m", "footprint_depth_m",
                                          "bedrooms", "wet_rooms", "safe_room", "open_plan")}
    return key, out


def run_all(contexts: list[dict], workers: int) -> dict:
    real_scores = _real_corpus_reference_scores()
    real_median = statistics.median(real_scores)
    real_stdev = statistics.pstdev(real_scores) if len(real_scores) > 1 else abs(real_median) * 0.5
    tasks = [(c, real_median, real_stdev) for c in contexts]
    if workers <= 1:
        results = [_run_one(t) for t in tasks]
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            results = pool.map(_run_one, tasks, chunksize=2)
    return dict(sorted(results)), real_median, real_stdev


def save(path: Path, workers: int, shard: str | None) -> dict:
    contexts = shard_contexts(shard, CORPUS) if shard else corpus_contexts(CORPUS)
    t0 = time.time()
    results, real_median, real_stdev = run_all(contexts, workers)
    doc = {"version": 1, "sha": _git_sha(), "corpus_hash": _corpus_hash(CORPUS), "workers": workers,
          "seconds": round(time.time() - t0, 1), "written_at": _now_iso(), "results": results,
          "real_median_score": real_median, "real_stdev_score": real_stdev}
    if shard:
        doc["shard"] = shard
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    print(f"saved {len(contexts)} scenarios (shard={shard}) in {doc['seconds']}s ({workers} workers)")
    return doc


def merge(out_path: Path, shard_paths: list[Path]) -> dict:
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


def _status_counts(results: dict) -> dict:
    c = Counter(v["status"] for v in results.values())
    return {"planned": c.get("PLANNED", 0), "refused": c.get("REFUSED", 0),
           "crashes": c.get("CRASH", 0), "total": len(results)}


def _median(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


def compare(doc: dict) -> dict:
    """Everything Steps 3/4/6 require, computed from ONE saved doc (each result already carries
    both its own OFF measurement and an embedded ON re-run — see `_run_one`)."""
    results = doc["results"]
    off = results
    on = {k: {**v.get("on", {"status": v["status"], **({"code": v["code"]} if "code" in v else {})}),
             "context": v["context"]}
         for k, v in results.items() if v["status"] != "CRASH"}

    keys = sorted(results)
    lost, gained, status_changes, code_changes, sig_changes, crashes = [], [], [], [], [], []
    for k in keys:
        b = results[k]
        if b["status"] == "CRASH":
            crashes.append({"key": k, "error": b.get("code")})
            continue
        a = b.get("on", {})
        row = {"key": k, "context": b["context"], "off_status": b["status"],
              "on_status": a.get("status")}
        if b["status"] == "PLANNED" and a.get("status") != "PLANNED":
            lost.append({**row, "on_code": a.get("code")})
        elif b["status"] != "PLANNED" and a.get("status") == "PLANNED":
            gained.append({**row, "on_area": a.get("area")})
        elif b["status"] != a.get("status"):
            status_changes.append(row)
        elif b["status"] == "REFUSED" and b.get("code") != a.get("code"):
            code_changes.append({**row, "off_code": b.get("code"), "on_code": a.get("code")})
        elif b["status"] == "PLANNED" and b.get("sig") != a.get("sig"):
            sig_changes.append({**row, "off_area": b.get("area"), "on_area": a.get("area")})

    #: Four-state classification only ever applies to a context that actually produced a candidate
    #: set — a REFUSED context never reached one, so it is reported separately (`refused_count`
    #: below), never folded into "NO_CANDIDATE_NEAR_REAL" alongside a context that DID plan but
    #: whose candidates are simply far from real adjacency patterns; those are different findings.
    analyzable = [v for v in results.values() if v["status"] == "PLANNED" and v.get("state")]
    refused_count = sum(1 for v in results.values() if v["status"] == "REFUSED")
    state_counts = Counter(v["state"] for v in analyzable)
    varies = [v for v in analyzable
             if v["decision_relevance"] and v["decision_relevance"]["score_spread"] >= _SPREAD_EPSILON]
    could_change = [v for v in analyzable
                   if v["decision_relevance"] and v["decision_relevance"]["could_change_winner"]]
    did_change = [v for v in analyzable if v["did_change_winner"]]
    inert = [v for v in analyzable
            if v["decision_relevance"] and v["decision_relevance"]["score_spread"] < _SPREAD_EPSILON]
    blocked = [v for v in analyzable
              if v["decision_relevance"] and v["decision_relevance"]["score_spread"] >= _SPREAD_EPSILON
              and not v["decision_relevance"]["could_change_winner"]]

    worked_examples = [
        {"key": k, "context": v["context"], "off_sig": v.get("sig"), "on_sig": v["on"].get("sig"),
        "decision_relevance": v["decision_relevance"]}
        for k, v in results.items() if v.get("did_change_winner") and v["status"] != "CRASH"][:10]
    no_good_candidate_examples = [
        {"key": k, "context": v["context"], "decision_relevance": v.get("decision_relevance")}
        for k, v in results.items() if v.get("state") == "NO_CANDIDATE_NEAR_REAL"][:10]

    n = len(analyzable) or 1
    return {
        "off": _status_counts(off), "on": _status_counts(on),
        "lost": lost, "gained": gained, "crashes": crashes, "status_changes": status_changes,
        "refusal_code_changes": code_changes, "primary_signature_changes": sig_changes,
        "byte_identical_primaries": sum(
            1 for k in keys if results[k]["status"] == "PLANNED"
            and results[k].get("on", {}).get("status") == "PLANNED"
            and results[k].get("sig") == results[k]["on"].get("sig")),
        "m5_wet_adjacency_ratio_median": {
            "off": _median([v.get("m5_wet_adjacency_ratio") for v in off.values()
                           if v["status"] == "PLANNED"]),
            "on": _median([v.get("m5_wet_adjacency_ratio") for v in on.values()
                          if v.get("status") == "PLANNED"]),
        },
        "m6_public_zone_contiguous_share": {
            "off": _median([1.0 if v.get("m6_public_zone_contiguous") else 0.0
                           for v in off.values() if v["status"] == "PLANNED"
                           and v.get("m6_public_zone_contiguous") is not None]),
            "on": _median([1.0 if v.get("m6_public_zone_contiguous") else 0.0
                          for v in on.values() if v.get("status") == "PLANNED"
                          and v.get("m6_public_zone_contiguous") is not None]),
        },
        "real_median_score": doc.get("real_median_score"), "real_stdev_score": doc.get("real_stdev_score"),
        #: The delivered PRIMARY's own adjacency log-likelihood (the winning candidate's solved-
        #: geometry score, `decision_relevance.winner_score` — the SAME Rect positions the realized
        #: plan ships with, for a normal, non-repartitioned candidate). ON is not recomputed
        #: separately: with `primary_signature_changes == 0` (proven above) the delivered geometry
        #: is IDENTICAL on both sides, so its own adjacency score cannot differ either.
        "adjacency_similarity_score_median": {
            "off": _median([v["decision_relevance"]["winner_score"] for v in analyzable
                           if v.get("decision_relevance")
                           and v["decision_relevance"].get("winner_score") is not None]),
            "on": _median([v["decision_relevance"]["winner_score"] for v in analyzable
                          if v.get("decision_relevance")
                          and v["decision_relevance"].get("winner_score") is not None])
                 if len(sig_changes) == 0 else None,
        },
        "decision_relevance": {
            "analyzable_count": len(analyzable), "refused_not_analyzable_count": refused_count,
            "pct_score_varies": round(100 * len(varies) / n, 1),
            "pct_could_change_winner": round(100 * len(could_change) / n, 1),
            "pct_did_change_winner": round(100 * len(did_change) / n, 1),
            "inert_count": len(inert),
            "blocked_by_ranking_count": len(blocked),
            "four_state_distribution": dict(state_counts),
        },
        "worked_examples_winner_changed": worked_examples,
        "no_good_candidate_examples": no_good_candidate_examples,
    }


def main() -> int:
    ap_ = argparse.ArgumentParser()
    g = ap_.add_mutually_exclusive_group(required=True)
    g.add_argument("--save-off", metavar="OUT.json")
    g.add_argument("--merge-off", nargs="+", metavar="FILE")
    g.add_argument("--compare", metavar="DOC.json")
    ap_.add_argument("--report", metavar="REPORT.json")
    ap_.add_argument("--shard", metavar="I/N")
    ap_.add_argument("--workers", type=int, default=4)
    args = ap_.parse_args()

    if args.save_off:
        save(Path(args.save_off), args.workers, args.shard)
    elif args.merge_off:
        out, *shards = args.merge_off
        merge(Path(out), [Path(p) for p in shards])
    elif args.compare:
        doc = json.load(open(args.compare, encoding="utf-8"))
        report = compare(doc)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        summary = {k: v for k, v in report.items()
                  if k not in ("lost", "gained", "status_changes", "refusal_code_changes",
                              "primary_signature_changes", "crashes", "worked_examples_winner_changed",
                              "no_good_candidate_examples")}
        print(json.dumps(summary, indent=2))
        print(f"LOST={len(report['lost'])} GAINED={len(report['gained'])} "
             f"primary_signature_changes={len(report['primary_signature_changes'])} "
             f"crashes={len(report['crashes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
