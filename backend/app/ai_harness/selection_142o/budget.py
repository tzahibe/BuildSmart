"""#142O step 0 — the gating measurement: does the EXISTING budget mechanism reproduce #142M?

The owner's constraint is that `max_realizations` must not be raised arbitrarily, so before any
production change this module measures what the current default actually does, and what every
smaller budget would cost.

TWO NESTED BUDGETS SHARE THE NAME. They are different things and only the outer one is at issue:

  outer  `proposal_selection.select_proposal(max_realizations=None)` — how many critic-clean
         PROPOSALS are pushed through the pipeline. Default `None`, and the slice is
         `ordered[: max_realizations or len(ordered)]`, so the production default is UNBOUNDED.
         Today the loop still stops early because it RETURNS at the first proposal that passes.
  inner  `band_pipeline.run_band_pipeline(max_realizations=150)` — how many BAND LAYOUTS of one
         proposal are realized before giving up. Untouched here: one proposal still yields at most
         one plan, exactly as #142L documented.

So "realize every clean candidate" is not a budget increase. It is the removal of the early return
inside a budget that is already unbounded by default — which is why the cost has to be measured
rather than assumed.

    old      order clean candidates by score, return the FIRST that realizes and validates.
    proposed order the same way, realize every one inside the SAME budget, keep every PASS plan,
             pick by entrance rank, then the same score, then the stable candidate index.

Nothing in production is modified: `criticize`, `run_band_pipeline`, `pipeline_input` and
`_entrance_rank` are imported and called.

    PYTHONPATH=backend python -m app.ai_harness.selection_142o.budget <out.json>
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.ai_harness.topology_poc.regen_142k import proposals_of
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from app.vertical_slice.general_pipeline import _entrance_rank
from app.vertical_slice.proposal_critic import criticize
from app.vertical_slice.proposal_selection import pipeline_input

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO = os.path.dirname(_BACKEND)
DATASETS = {
    "historical": os.path.join(_REPO, "docs", "reports", "llm-topology-poc", "generation-dataset.json"),
    "corrected": os.path.join(_REPO, "docs", "reports", "142k-corrected-proposer", "data",
                              "generation-dataset-142k.json"),
}
#: Budgets to measure. `None` is production's own default (unbounded); the integers say what a cap
#: would cost if one were ever introduced.
BUDGETS = (1, 2, 3, 4, 5, 6, 8, 12, None)


def _brief_of(record: dict):
    b = record["brief"]
    if "source_key" in b and "size_tier" in b:
        return briefs_mod.Brief(**b)
    return {x.brief_id: x for x in briefs_mod.select_briefs()}[record["brief_id"]]


def clean_candidates(record: dict, pri) -> tuple[list, object]:
    """Production's own first two steps: schema, critic, score — in production's order.

    Returns the clean candidates as (index, proposal, report, score), ordered exactly as
    `select_proposal` orders them: by score descending, ties by candidate index.
    """
    brief = _brief_of(record)
    kinds = briefs_mod.brief_wet_room_kinds(brief)
    out, n = [], 0
    for raw in proposals_of(record["attempts"][0]["parsed_json"]):
        try:
            tp = schema.proposal_from_dict(raw)
        except schema.SchemaViolationError:
            continue
        i = n
        n += 1
        zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
        p = from_topology_proposal(f"{record['brief_id']}#{i}", tp, zones, kinds)
        report = criticize(p)
        if report.clean:
            out.append((i, p, report, float(poc_critic.score_topology(tp, pri).total_score)))
    out.sort(key=lambda t: (-t[3], t[0]))
    return out, brief


def realize_clean(clean: list, footprint_m) -> tuple[dict, list[float]]:
    """Run the unchanged pipeline over every clean candidate once, in score order, and keep the
    result. Both selections are then read off this ONE set, so neither pays for the other and the
    comparison is exact rather than two separate runs."""
    results, times = {}, []
    for i, p, report, score in clean:
        t0 = time.perf_counter()
        res = run_band_pipeline(pipeline_input(p, report, footprint_m))
        dt = time.perf_counter() - t0
        times.append(dt)
        results[i] = (res, dt, score)
    return results, times


def selections_at_budget(clean: list, results: dict, budget: int | None) -> dict:
    """Both selections restricted to the first `budget` clean candidates in score order."""
    window = clean[: budget or len(clean)]
    passes = [(i, score, results[i][0]) for i, _p, _r, score in window
              if isinstance(results[i][0], PipelineSuccess)]
    truncated = len(clean) - len(window)
    if not passes:
        return {"budget": budget, "clean": len(clean), "attempted": len(window),
                "truncated_clean": truncated, "pass_plans": 0, "old_winner": None,
                "new_winner": None, "winner_changed": None, "alternatives": 0,
                "entrance_rank": {}, "seconds": round(sum(results[i][1] for i, *_ in window), 3)}
    ranks = {i: _entrance_rank(res.realized) for i, _s, res in passes}
    old = passes[0][0]                                   # today: the FIRST PASS in score order
    new = min(passes, key=lambda t: (ranks[t[0]], -t[1], t[0]))[0]
    # today's cost stops at the first PASS; the proposed cost runs the whole window
    stop = next(k for k, w in enumerate(window) if w[0] == old)
    old_seconds = sum(results[w[0]][1] for w in window[: stop + 1])
    return {
        "budget": budget, "clean": len(clean), "attempted": len(window), "truncated_clean": truncated,
        "pass_plans": len(passes), "pass_candidates": [i for i, *_ in passes],
        "old_winner": old, "new_winner": new, "winner_changed": old != new,
        "entrance_rank": ranks,
        "entrance_rank_old": ranks[old], "entrance_rank_new": ranks[new],
        "entrance_improved": ranks[new] < ranks[old], "entrance_degraded": ranks[new] > ranks[old],
        "alternatives": len(passes) - 1,
        "seconds": round(sum(results[i][1] for i, _p, _r, _s in window), 3),
        "seconds_old_early_return": round(old_seconds, 3),
    }


def run_dataset(name: str, path: str, pri) -> dict:
    per_brief: dict[str, dict] = {}
    realize_times: list[float] = []
    for rec in sorted(json.load(open(path))["records"], key=lambda r: r["brief_id"]):
        bid = rec["brief_id"]
        clean, brief = clean_candidates(rec, pri)
        fp = (brief.footprint_width_m, brief.footprint_depth_m)
        results, times = realize_clean(clean, fp)
        realize_times += times
        per_brief[bid] = {str(b): selections_at_budget(clean, results, b) for b in BUDGETS}
        full = per_brief[bid]["None"]
        print(f"{name} {bid}: clean {full['clean']} PASS {full['pass_plans']} "
              f"old #{full['old_winner']} -> new #{full['new_winner']}"
              f"{' CHANGED' if full.get('winner_changed') else ''} "
              f"rank {full.get('entrance_rank_old')}->{full.get('entrance_rank_new')} "
              f"alts {full['alternatives']} | {full['seconds']}s", flush=True)

    def agg(b) -> dict:
        v = [per_brief[x][str(b)] for x in per_brief]
        with_pass = [x for x in v if x["pass_plans"]]
        secs = [x["seconds"] for x in v]
        return {
            "budget": b,
            "briefs_with_a_pass": len(with_pass),
            "pass_plans_total": sum(x["pass_plans"] for x in v),
            "alternatives_total": sum(x["alternatives"] for x in with_pass),
            "briefs_with_an_alternative": sum(1 for x in with_pass if x["alternatives"]),
            "winner_changed": sum(1 for x in with_pass if x["winner_changed"]),
            "entrance_improved": sum(1 for x in with_pass if x["entrance_improved"]),
            "entrance_degraded": sum(1 for x in with_pass if x["entrance_degraded"]),
            "briefs_truncating_clean": sum(1 for x in v if x["truncated_clean"]),
            "clean_truncated_total": sum(x["truncated_clean"] for x in v),
            "seconds_total": round(sum(secs), 1),
            "seconds_per_brief_p50": round(statistics.median(secs), 3),
            "seconds_per_brief_worst": round(max(secs), 3),
            "seconds_old_early_return_total": round(
                sum(x.get("seconds_old_early_return", x["seconds"]) for x in v), 1),
        }

    return {
        "dataset": name, "path": os.path.relpath(path, _REPO), "briefs": len(per_brief),
        "per_realization_s": {"n": len(realize_times),
                              "p50": round(statistics.median(realize_times), 3),
                              "p95": round(sorted(realize_times)[int(0.95 * (len(realize_times) - 1))], 3),
                              "worst": round(max(realize_times), 3)},
        "by_budget": {str(b): agg(b) for b in BUDGETS},
        "per_brief": per_brief,
    }


def main(out_path: str) -> dict:
    pri = priors_mod.load_priors()
    out = {"note": "#142O gating measurement — what production's EXISTING select_proposal budget "
                   "(max_realizations, default None = unbounded) does under the proposed selection. "
                   "No production file is modified.",
           "budgets": [str(b) for b in BUDGETS], "datasets": {}}
    for name, path in DATASETS.items():
        if not os.path.exists(path):
            continue
        out["datasets"][name] = run_dataset(name, path, pri)
        print(f"\n--- {name} by budget ---")
        for b, a in out["datasets"][name]["by_budget"].items():
            print(f"  budget {b:>4}: briefs {a['briefs_with_a_pass']:>2} PASS {a['pass_plans_total']:>3} "
                  f"alts {a['alternatives_total']:>3} changed {a['winner_changed']:>2} "
                  f"(+{a['entrance_improved']}/-{a['entrance_degraded']}) "
                  f"truncated {a['clean_truncated_total']:>3} in {a['briefs_truncating_clean']:>2} briefs "
                  f"| {a['seconds_total']}s total, worst brief {a['seconds_per_brief_worst']}s "
                  f"(old early-return {a['seconds_old_early_return_total']}s)", flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1])
