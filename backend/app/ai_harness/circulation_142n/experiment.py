"""#142N driver — every measurement the investigation reports, over both valid plan sets.

    PYTHONPATH=backend python -m app.ai_harness.circulation_142n.experiment <pool.json> <out.json>

`pool.json` comes from `circulation_142n.pool`. Nothing here modifies production: production's
`circulation_prefers`, `classify_extreme` and `measure` are imported and called as they are.
"""
from __future__ import annotations

import itertools
import json
import os
import sys

from . import formulations as F
from . import privacy as PV
from . import relation as R

#: Which `CirculationMetrics` field reaches a DECISION in production, and where. Audited by
#: reading every consumer of the dataclass (see the report's §3); the reporting DTO
#: (`demo.contract._metrics_out`) serialises all nine, which is not a decision.
DECISION_CONSUMERS = {
    "area_m2": [],
    "ratio": ["validation.C26 classify_extreme (upper bound 0.24)", "circulation_prefers (lower better)"],
    "longest_segment_m": ["validation.C26 classify_extreme (upper bound 20.0 m)",
                          "circulation_prefers (lower better)"],
    "total_length_m": [],
    "narrowest_width_m": [],
    "dead_end_count": ["validation.C26 classify_extreme (upper bound 2)",
                       "circulation_prefers (lower better)",
                       "concept_compilers imports EXTREME_DEAD_END_COUNT"],
    "turn_count": [],
    "duplicated_segment_count": [],
    "duplicated_area_m2": [],
}


def smallest_cycle(by_brief: dict[str, list[R.Plan]]) -> dict | None:
    """The simplest concrete A>-B>-C>-A to put in the report: fewest distinct measures across its
    three edges, then the smallest total spread in the values that carry them.

    Cycles are searched WITHIN a brief only — two plans of different briefs have different
    footprints and are never candidates for the same selection.
    """
    cycles = []
    for plans in by_brief.values():
        by = {p.key: p for p in plans}
        cycles += [R.classify_cycle(c, by) for c in R.distinct_three_cycles(plans)]
    if not cycles:
        return None

    def spread(c: dict) -> float:
        v = c["values"]
        return (max(x["ratio"] for x in v.values()) - min(x["ratio"] for x in v.values())
                + max(x["area_m2"] for x in v.values()) - min(x["area_m2"] for x in v.values()))
    return min(cycles, key=lambda c: (len(c["measures_involved"]), round(spread(c), 4), c["cycle"]))


def run_dataset(name: str, pool: dict) -> dict:
    by_brief = R.plans_of(pool, name)
    allp = [p for v in by_brief.values() for p in v]
    multi = {b: v for b, v in by_brief.items() if len(v) > 1}

    # 0. the decomposition must agree with production on every pair, or nothing below is evidence
    mismatches = [[x.key, y.key] for x, y in itertools.permutations(allp, 2)
                  if not R.verdict_agrees(x, y)]

    # 1. F0's failure modes
    mutual = {b: R.mutual_pairs(v) for b, v in multi.items()}
    cycles = {b: [R.classify_cycle(c, {p.key: p for p in v}) for c in R.distinct_three_cycles(v)]
              for b, v in multi.items()}
    all_cycles = [c for v in cycles.values() for c in v]
    root_causes: dict[str, int] = {}
    measure_sets: dict[str, int] = {}
    for c in all_cycles:
        root_causes[c["root_cause"]] = root_causes.get(c["root_cause"], 0) + 1
        k = "+".join(c["measures_involved"])
        measure_sets[k] = measure_sets.get(k, 0) + 1
    folds = {b: R.fold_winners(v) for b, v in by_brief.items() if v}

    # 1b. does the disjunction still cycle once the undocumented `area` disjunct is removed?
    no_area = []
    for plans in multi.values():
        by = {p.key: p for p in plans}
        no_area += [F.describe_cycle(c, by) for c in F.three_cycles_under(plans, F.beats_without_area)]

    # 2. the formulations
    forms = {}
    for fname, prefers in F.FORMULATIONS.items():
        per_brief = {b: F.properties(v, prefers) for b, v in multi.items()}
        refs = {b: F.reference_winners(v) for b, v in by_brief.items() if v}
        impact = {b: F.selection_impact(v, prefers, refs[b]) for b, v in multi.items()}
        forms[fname] = {
            "totals": {
                "briefs": len(per_brief),
                "pairs": sum(p["pairs"] for p in per_brief.values()),
                "comparable_pairs": sum(p["comparable_pairs"] for p in per_brief.values()),
                "incomparable_pairs": sum(p["incomparable_pairs"] for p in per_brief.values()),
                "mutual_pairs": sum(p["mutual_pairs"] for p in per_brief.values()),
                "transitivity_violations": sum(p["transitivity_violations"] for p in per_brief.values()),
                "ordered_3_cycles": sum(p["ordered_3_cycles"] for p in per_brief.values()),
                "briefs_transitive": sum(1 for p in per_brief.values() if p["transitive"]),
                "briefs_antisymmetric": sum(1 for p in per_brief.values() if p["antisymmetric"]),
                "briefs_with_unique_maximum": sum(1 for p in per_brief.values() if p["unique_maximum"]),
                "max_fold_distinct_winners": max((p["fold_distinct_winners"] for p in per_brief.values()),
                                                 default=0),
                "briefs_where_fold_is_order_dependent": sum(
                    1 for p in per_brief.values() if p["fold_distinct_winners"] > 1),
                "prod_today_dominated": sum(1 for i in impact.values() if i["prod_today"]["dominated"]),
                "m142_step_dominated": sum(1 for i in impact.values() if i["m142_step"]["dominated"]),
            },
            "per_brief": per_brief,
            "selection_impact": impact,
        }

    # 3. architectural direction
    zoning = {p.key: PV.zoning_facts(p) for p in allp}
    lower = {b: PV.lower_ratio_costs_zoning(v) for b, v in multi.items()}
    lower_tot: dict[str, int] = {}
    for v in lower.values():
        for k, n in v["verdicts"].items():
            lower_tot[k] = lower_tot.get(k, 0) + n

    return {
        "dataset": name,
        "plans": len(allp), "briefs_with_a_pass": len(by_brief), "briefs_with_multiple_pass": len(multi),
        "decomposition_mismatches_vs_production": mismatches,
        "f0": {
            "ordered_3_cycles": sum(len(R.ordered_three_cycles(v)) for v in multi.values()),
            "distinct_3_cycles": len(all_cycles),
            "mutual_pairs": sum(len(v) for v in mutual.values()),
            "pairs": sum(len(v) * (len(v) - 1) // 2 for v in multi.values()),
            "root_causes": root_causes,
            "measure_sets": dict(sorted(measure_sets.items(), key=lambda kv: -kv[1])),
            "single_measure_cycles": sum(1 for c in all_cycles if c["single_measure_sufficient"]),
            "smallest_cycle": smallest_cycle(multi),
            "mutual_pair_examples": [m for v in mutual.values() for m in v][:6],
            "max_fold_distinct_winners": max((f["distinct_winners"] for f in folds.values()), default=0),
            "fold_distinct_winners_per_brief": {b: f["distinct_winners"] for b, f in sorted(folds.items())},
            "briefs_order_dependent": sum(1 for f in folds.values() if f["distinct_winners"] > 1),
        },
        "measure_conflicts": {b: R.measure_conflicts(v) for b, v in multi.items()},
        "measure_conflicts_total": {
            k: {"conflict": sum(R.measure_conflicts(v)[k]["conflict"] for v in multi.values()),
                "agree": sum(R.measure_conflicts(v)[k]["agree"] for v in multi.values()),
                "one_is_tied": sum(R.measure_conflicts(v)[k]["one_is_tied"] for v in multi.values())}
            for k in R.measure_conflicts(next(iter(multi.values())))},
        "cycles_without_the_area_disjunct": {
            "distinct_3_cycles": len(no_area),
            "smallest": min(no_area, key=lambda c: (len({m for v in c["better_on"].values() for m in v}),
                                                    c["cycle"])) if no_area else None,
            "all": no_area},
        "tolerance": R.tolerance_sensitivity(allp),
        "bounds_screen": R.bounds_screen(allp),
        "formulations": forms,
        "zoning": {
            "per_plan": zoning,
            "ratio_vs_zoning": PV.ratio_vs_zoning_table(allp),
            "by_circulation_room_count": PV.branching_facts(allp),
            "ratio_vs_width": PV.ratio_vs_width(allp),
            "ratio_vs_dead_ends": PV.ratio_vs_dead_ends(allp),
            "within_brief_ratio_vs_dead_ends": PV.within_brief_ratio_vs_dead_ends(multi),
            "lower_ratio_pairs": lower_tot,
            "lower_ratio_examples": [e for v in lower.values() for e in v["worse_zoning_examples"]][:10],
            "plans_with_a_private_room_not_off_circulation": sum(
                1 for z in zoning.values() if z["private_not_from_circulation"] > 0),
        },
    }


def main(pool_path: str, out_path: str) -> dict:
    pool = json.load(open(pool_path))
    out = {"note": "#142N — why circulation_prefers is non-transitive. Measurement only; production "
                   "is imported, never modified.",
           "pool": pool["sources"], "decision_consumers": DECISION_CONSUMERS,
           "unused_in_any_decision": [k for k, v in DECISION_CONSUMERS.items() if not v],
           "datasets": {}}
    for name in ("historical", "corrected"):
        out["datasets"][name] = run_dataset(name, pool)
        d = out["datasets"][name]
        print(f"\n=== {name}: {d['plans']} plans, {d['briefs_with_multiple_pass']} briefs with >1 ===",
              flush=True)
        print("F0:", json.dumps({k: v for k, v in d["f0"].items()
                                 if k not in ("smallest_cycle", "mutual_pair_examples",
                                              "fold_distinct_winners_per_brief")}, indent=1))
        for fname, f in d["formulations"].items():
            print(fname, json.dumps(f["totals"]))
        print("conflicts:", json.dumps(d["measure_conflicts_total"], indent=1))
        print("zoning:", json.dumps(d["zoning"]["lower_ratio_pairs"]),
              json.dumps(d["zoning"]["ratio_vs_zoning"]))
        print("by circulation rooms:", json.dumps(d["zoning"]["by_circulation_room_count"], indent=1))
        print("ratio vs width:", json.dumps(d["zoning"]["ratio_vs_width"], indent=1))
        print("ratio vs dead ends:", json.dumps(d["zoning"]["ratio_vs_dead_ends"], indent=1))
        print("within-brief lower ratio -> more dead ends:",
              d["zoning"]["within_brief_ratio_vs_dead_ends"]["pairs_where_lower_ratio_means_more_dead_ends"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
