"""#142L step 9 — WHY the current heuristic prefers weaker plans.

The heuristic is `ai_harness.topology_poc.critic.score_topology`, the score #142J's gate ranks
critic-clean candidates by. It is a geometry-free score over the PROPOSAL graph:

    total = adjacency_similarity + access_similarity + wet_core_similarity + entrance_relation_score
            - 10.0 * len(hard_violations)

This module recomputes that breakdown for every plan in the pool and measures, pair by pair, which
realized quality property each COMPONENT pulls toward. No production code is modified.

Failure modes the task lists (§9) are tested, not assumed:
  SCORED_BEFORE_REALIZATION   the score sees no geometry, so anything decided by the realizer
                              (room shapes, corridor length, facade allocation) is invisible to it.
  TOPOLOGY_PROXY_NOT_SURVIVING  a graph property the score rewards that does not survive into a
                              better realized plan.
  CORPUS_MISMATCH             the priors are measured on ResPlan APARTMENTS; these briefs are
                              detached houses, where the same adjacency can mean the opposite thing.
  MISSING_PRIVACY / MISSING_CIRCULATION  properties with no term in the score at all.
  DOUBLE_COUNTING             two terms rewarding the same underlying property.
"""
from __future__ import annotations

import json
import os
import statistics
import sys

from app.ai_harness.quality_142l.metrics import METRICS, evaluate
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc.regen_142k import _candidates
from app.ai_harness.topology_poc.briefs import Brief

COMPONENTS = ("adjacency_similarity", "access_similarity", "wet_core_similarity",
              "entrance_relation_score", "total_score")
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATASET_142K = os.path.join(os.path.dirname(_BACKEND), "docs", "reports", "142k-corrected-proposer",
                            "data", "generation-dataset-142k.json")
TOL = 1e-9


def breakdowns(pool: dict, pri) -> dict:
    """{(brief, candidate): ScoreBreakdown as a dict} for every plan in the pool."""
    data = json.load(open(DATASET_142K))
    out = {}
    for rec in data["records"]:
        bid = rec["brief_id"]
        if bid not in pool["briefs"]:
            continue
        keep = {p["candidate"] for p in pool["briefs"][bid]["plans"]}
        tps, props, _rej = _candidates(rec, pri, 0)
        for i, tp in enumerate(tps):
            if i in keep:
                sb = poc_critic.score_topology(tp, pri)
                out[(bid, i)] = {c: getattr(sb, c) for c in COMPONENTS}
                out[(bid, i)]["hard_violations"] = list(sb.hard_violations)
                out[(bid, i)]["n_rooms"] = len(tp.rooms)
                out[(bid, i)]["entrance_targets"] = sorted(b for a, b in tp.access_graph if a == "ENTRANCE")
    return out


def _pref(x, y) -> str:
    """A component can be `None` ('no evidence'); the critic then substitutes its own fallback, so a
    None-vs-number comparison is not a preference this component expressed."""
    if x is None or y is None:
        return "NONE" if x is None and y is None else "UNDEFINED"
    return "A" if x > y + TOL else ("B" if x < y - TOL else "TIE")


def run(pool_path: str, comparison_path: str, out_path: str) -> dict:
    pool = json.load(open(pool_path))
    comparison = json.load(open(comparison_path))
    pri = priors_mod.load_priors()
    bds = breakdowns(pool, pri)
    vecs = {(b, p["candidate"]): evaluate(p, pri) for b, bb in pool["briefs"].items() for p in bb["plans"]}

    # per pair: which plan each score COMPONENT prefers, and which plan each METRIC prefers
    rows = []
    for p in comparison["pairs"]:
        ka, kb = (p["brief"], p["a"]), (p["brief"], p["b"])
        if ka not in bds or kb not in bds:
            continue
        r = {"brief": p["brief"], "a": p["a"], "b": p["b"], "concept": p["concept"]}
        for c in COMPONENTS:
            r[f"pref_{c}"] = _pref(bds[ka][c], bds[kb][c])
        for k, d in METRICS.items():
            if d.direction == "info":
                continue
            va, vb = vecs[ka][k], vecs[kb][k]
            r[f"metric_{k}"] = "TIE" if abs(va - vb) <= TOL else (
                "A" if ((va > vb) == (d.direction == "up")) else "B")
        rows.append(r)

    # agreement of each component with each metric, over the pairs where BOTH are decided
    agree = {}
    for c in COMPONENTS:
        agree[c] = {}
        for k, d in METRICS.items():
            if d.direction == "info":
                continue
            both = [r for r in rows if r[f"pref_{c}"] in ("A", "B") and r[f"metric_{k}"] in ("A", "B")]
            if len(both) < 8:
                continue
            same = sum(1 for r in both if r[f"pref_{c}"] == r[f"metric_{k}"])
            agree[c][k] = {"n": len(both), "agreement": round(same / len(both), 4)}

    # what the TOTAL score systematically pulls toward / away from
    tot = agree["total_score"]
    pulls_toward = sorted(tot.items(), key=lambda kv: -kv[1]["agreement"])[:10]
    pulls_against = sorted(tot.items(), key=lambda kv: kv[1]["agreement"])[:10]

    # component spread: a component that never varies inside a brief cannot be driving anything
    spread = {}
    for c in COMPONENTS:
        per = []
        for bid, bb in pool["briefs"].items():
            vals = [bds[(bid, p["candidate"])][c] for p in bb["plans"] if (bid, p["candidate"]) in bds
                    and bds[(bid, p["candidate"])][c] is not None]
            if len(vals) > 1:
                per.append(max(vals) - min(vals))
        spread[c] = {"mean_within_brief_range": round(statistics.mean(per), 4) if per else 0.0,
                     "briefs_with_any_variation": sum(1 for v in per if v > TOL), "briefs": len(per)}

    # the entrance term, specifically: the ResPlan front-door prior gives LIVING 0.99 and HALL 0.0
    fd = pri.front_door_direct_access
    ent = {"front_door_direct_access_rates": {k: (v.get("rate") if isinstance(v, dict) else v) for k, v in fd.items()},
           "plans_arriving_in_circulation": 0, "plans_arriving_in_living": 0,
           "mean_entrance_term_circulation_arrival": None, "mean_entrance_term_living_arrival": None}
    circ_terms, living_terms = [], []
    for bid, bb in pool["briefs"].items():
        for p in bb["plans"]:
            key = (bid, p["candidate"])
            if key not in bds:
                continue
            v = vecs[key]
            term = bds[key]["entrance_relation_score"] or 0.0
            if v["arrival_is_circulation"] == 1:
                ent["plans_arriving_in_circulation"] += 1; circ_terms.append(term)
            else:
                ent["plans_arriving_in_living"] += 1; living_terms.append(term)
    ent["mean_entrance_term_circulation_arrival"] = round(statistics.mean(circ_terms), 4) if circ_terms else None
    ent["mean_entrance_term_living_arrival"] = round(statistics.mean(living_terms), 4) if living_terms else None
    both = [r for r in rows if r["pref_entrance_relation_score"] in ("A", "B")
            and r["metric_arrival_is_circulation"] in ("A", "B")]
    ent["pairs_where_entrance_term_decides"] = len(both)
    ent["agreement_with_arrival_is_circulation"] = round(
        sum(1 for r in both if r["pref_entrance_relation_score"] == r["metric_arrival_is_circulation"]) / len(both), 4) if both else None

    # the adjacency term, specifically: BEDROOM-LIVING touching has lift 1.886 in the apartment corpus
    rows_adj = {f"{r.role_a}-{r.role_b}": {"p": r.p_smoothed, "lift": r.lift} for r in pri.adjacency_table.rows}
    adj = {"adjacency_prior_rows": rows_adj,
           "access_prior_bedroom_living": next((r.lift for r in pri.access_table.rows
                                                if {r.role_a, r.role_b} == {"BEDROOM", "LIVING"}), None)}
    b_both = [r for r in rows if r["pref_adjacency_similarity"] in ("A", "B")
              and r["metric_public_private_wall_m"] in ("A", "B")]
    adj["pairs_where_adjacency_term_decides"] = len(b_both)
    adj["agreement_with_less_public_private_wall"] = round(
        sum(1 for r in b_both if r["pref_adjacency_similarity"] == r["metric_public_private_wall_m"]) / len(b_both), 4) if b_both else None

    out = {
        "score_definition": "total = adjacency_similarity + access_similarity + wet_core_similarity + "
                            "entrance_relation_score - 10.0 * len(hard_violations)",
        "component_spread": spread,
        "component_vs_metric_agreement": agree,
        "total_score_pulls_toward": [{"metric": k, **v} for k, v in pulls_toward],
        "total_score_pulls_against": [{"metric": k, **v} for k, v in pulls_against],
        "entrance_term": ent, "adjacency_term": adj,
        "pairs": rows,
        "breakdowns": {f"{b}#{c}": v for (b, c), v in sorted(bds.items())},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print("component spread:", json.dumps(spread, indent=1))
    print("\ntotal score AGREES most with:", [(k, v["agreement"], v["n"]) for k, v in pulls_toward[:6]])
    print("total score DISAGREES most with:", [(k, v["agreement"], v["n"]) for k, v in pulls_against[:6]])
    print("\nentrance term:", json.dumps({k: v for k, v in ent.items() if k != "front_door_direct_access_rates"}, indent=1))
    print("front-door prior rates:", ent["front_door_direct_access_rates"])
    print("\nadjacency term:", json.dumps({k: v for k, v in adj.items() if k != "adjacency_prior_rows"}, indent=1))
    return out


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3])
