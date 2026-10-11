"""#142N step 0 — the plan pool, taken from #142L/#142M rather than regenerated.

Two valid-plan sets, both produced by the UNCHANGED production pipeline:

  corrected   the 81 validator-PASS plans of #142L's own baseline pool, read straight off
              `docs/reports/142l-quality-ranking/data/baseline_pool.json`. Not re-realized, so
              #142N provably reasons about the same plans #142L and #142M measured.
  historical  the #151 proposal dataset, realized here through the same `quality_142l.baseline`
              code path (that module only ever reads the #142K dataset, so the historical set has
              to be built; it is built with production's own functions and nothing else).

A "plan" is `quality_142l.baseline.plan_record`'s dict, so every circulation quantity this
investigation reads is production's own `circulation_metrics.measure` output, recorded under
`production_quality.circulation`, plus the plan's `gross_area_m2` — exactly the two arguments
`general_pipeline` passes to `circulation_prefers`.

Usage (dev venv): PYTHONPATH=backend python -m app.ai_harness.circulation_142n.pool <out.json>
"""
from __future__ import annotations

import json
import os
import sys
import time

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO = os.path.dirname(_BACKEND)

#: #142L's own saved pool — the corrected (#142K) dataset's PASS plans, reused verbatim.
POOL_142L = os.path.join(_REPO, "docs", "reports", "142l-quality-ranking", "data", "baseline_pool.json")
#: The #151 historical proposal dataset, realized here.
DATASET_HISTORICAL = os.path.join(_REPO, "docs", "reports", "llm-topology-poc", "generation-dataset.json")


def _brief_of(record: dict):
    """A `Brief` for either dataset's record shape (the historical records carry a partial dict)."""
    from app.ai_harness.topology_poc import briefs as briefs_mod
    b = record["brief"]
    if "source_key" in b and "size_tier" in b:
        return briefs_mod.Brief(**b)
    return {x.brief_id: x for x in briefs_mod.select_briefs()}[record["brief_id"]]


def corrected_from_142l(path: str = POOL_142L) -> dict[str, list[dict]]:
    """{brief_id: [plan, ...]} — #142L's PASS plans, untouched."""
    data = json.load(open(path))
    return {bid: list(b["plans"]) for bid, b in sorted(data["briefs"].items())}


def realize_historical(path: str = DATASET_HISTORICAL) -> dict[str, list[dict]]:
    """{brief_id: [plan, ...]} for the historical dataset, through production's own pipeline."""
    from app.ai_harness.quality_142l.baseline import plan_record
    from app.ai_harness.topology_poc import briefs as briefs_mod
    from app.ai_harness.topology_poc import critic as poc_critic
    from app.ai_harness.topology_poc import gap_closure_142a as gc
    from app.ai_harness.topology_poc import priors as priors_mod
    from app.ai_harness.topology_poc import schema
    from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
    from app.ai_harness.topology_poc.regen_142k import proposals_of
    from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
    from app.vertical_slice.proposal_critic import criticize
    from app.vertical_slice.proposal_selection import pipeline_input

    pri = priors_mod.load_priors()
    out: dict[str, list[dict]] = {}
    for rec in sorted(json.load(open(path))["records"], key=lambda r: r["brief_id"]):
        bid = rec["brief_id"]
        brief = _brief_of(rec)
        kinds = briefs_mod.brief_wet_room_kinds(brief)
        fp = (brief.footprint_width_m, brief.footprint_depth_m)
        plans: list[dict] = []
        tps = []
        for raw in proposals_of(rec["attempts"][0]["parsed_json"]):
            try:
                tp = schema.proposal_from_dict(raw)
            except schema.SchemaViolationError:
                continue
            tps.append(tp)
            i = len(tps) - 1
            zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
            p = from_topology_proposal(f"{bid}#{i}", tp, zones, kinds)
            report = criticize(p)
            if not report.clean:
                continue
            res = run_band_pipeline(pipeline_input(p, report, fp))
            if isinstance(res, PipelineSuccess):
                plans.append(plan_record(res, p, brief, poc_critic.score_topology(tp, pri).total_score,
                                         i, report))
        out[bid] = plans
        print(f"historical {bid}: PASS {len(plans)} {[p['candidate'] for p in plans]}", flush=True)
    return out


def build(out_path: str) -> dict:
    t0 = time.time()
    pools = {"corrected": corrected_from_142l(), "historical": realize_historical()}
    out = {
        "note": "corrected = #142L's saved baseline pool, reused verbatim; historical = the #151 "
                "dataset realized through the same production path. Circulation values are "
                "production's own circulation_metrics.measure output.",
        "sources": {"corrected": os.path.relpath(POOL_142L, _REPO),
                    "historical": os.path.relpath(DATASET_HISTORICAL, _REPO)},
        "seconds": round(time.time() - t0, 1),
        "totals": {name: {"briefs_with_a_pass": sum(1 for v in p.values() if v),
                          "plans": sum(len(v) for v in p.values()),
                          "briefs_with_multiple_pass": sum(1 for v in p.values() if len(v) > 1)}
                   for name, p in pools.items()},
        "pools": pools,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print(json.dumps(out["totals"], indent=1))
    return out


if __name__ == "__main__":
    build(sys.argv[1])
