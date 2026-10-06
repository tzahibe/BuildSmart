"""#142L steps 5/6/9/11 — per-plan quality vectors, pairwise comparison WITHOUT arbitrary weights,
diversity, and the current heuristic's behaviour on the same pool. Experiment code only.

Ranking rules, in the order the task asks for them (§5):
  1. PARETO DOMINANCE on the raw ranked metrics. A dominates B when it is no worse on every ranked
     metric and strictly better on at least one. This needs no weights at all.
  2. DIMENSION-LEVEL dominance. Each of the ten dimensions is reduced to one number by min-max
     normalising its ranked metrics WITHIN the brief's own comparison set and averaging them. The
     equal weight inside a dimension is itself a choice and is labelled as such; it is never applied
     ACROSS dimensions.
  3. DOMINANCE COUNT / Copeland score: how many of the brief's other plans a plan Pareto-dominates at
     the dimension level, used only to report how often a clear winner exists.
  4. Documented alternative weighting SCENARIOS (§5) — equal, privacy-led, openness-led, efficiency-led
     — reported side by side so the reader can see how much the answer depends on taste.

A metric with no variation inside a brief cannot separate that brief's plans; `metric_signal` reports
exactly how often each metric discriminates, which is the §8/§13-Q3 question.
"""
from __future__ import annotations

import itertools
import json
import os
import statistics
import sys

from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.quality_142l.metrics import DIMENSIONS, METRICS, contacts, door_graph, evaluate

TOL = 1e-9
RANKED = tuple(n for n, d in METRICS.items() if d.direction in ("up", "down"))
#: Documented alternative weighting scenarios (§5). NONE of these is a recommendation: they exist to
#: show how much the ordering depends on taste that the brief does not state.
SCENARIOS: dict[str, dict] = {
    "equal": {d: 1.0 for d in DIMENSIONS},
    "privacy_led": {**{d: 1.0 for d in DIMENSIONS}, "privacy": 3.0, "public_private_separation": 3.0},
    "openness_led": {**{d: 1.0 for d in DIMENSIONS}, "public_zone_quality": 3.0, "circulation_efficiency": 2.0},
    "efficiency_led": {**{d: 1.0 for d in DIMENSIONS}, "circulation_efficiency": 3.0, "proportion_quality": 2.0},
    "bedroom_led": {**{d: 1.0 for d in DIMENSIONS}, "bedroom_quality": 3.0, "exposure_quality": 2.0},
}


def better(metric: str, a: float, b: float) -> int:
    """+1 when a is better than b for this metric, -1 when worse, 0 when equal."""
    d = METRICS[metric].direction
    if abs(a - b) <= TOL:
        return 0
    if d == "up":
        return 1 if a > b else -1
    if d == "down":
        return 1 if a < b else -1
    return 0


def pareto(va: dict, vb: dict, keys=RANKED) -> str:
    """'A', 'B' or 'NONE' — strict Pareto dominance over `keys`."""
    s = [better(k, va[k], vb[k]) for k in keys]
    if all(x >= 0 for x in s) and any(x > 0 for x in s):
        return "A"
    if all(x <= 0 for x in s) and any(x < 0 for x in s):
        return "B"
    return "NONE"


def normalise(vectors: list[dict]) -> list[dict]:
    """Min-max normalise every RANKED metric to [0, 1] with 1 = better, WITHIN this comparison set.
    A metric that does not vary in the set is dropped (it cannot separate these plans)."""
    out = [dict() for _ in vectors]
    for k in RANKED:
        vals = [v[k] for v in vectors]
        lo, hi = min(vals), max(vals)
        if hi - lo <= TOL:
            continue
        for i, v in enumerate(vectors):
            x = (v[k] - lo) / (hi - lo)
            out[i][k] = x if METRICS[k].direction == "up" else 1.0 - x
    return out


def dimension_scores(normalised: dict) -> dict:
    """Equal-weight mean of a dimension's normalised metrics (documented choice; `None` when none of
    the dimension's metrics varied in this comparison set)."""
    out = {}
    for d in DIMENSIONS:
        vals = [v for k, v in normalised.items() if METRICS[k].dimension == d]
        out[d] = round(statistics.mean(vals), 4) if vals else None
    return out


def scenario_scores(dims: dict) -> dict:
    out = {}
    for name, w in SCENARIOS.items():
        pairs = [(w[d], v) for d, v in dims.items() if v is not None]
        tw = sum(x for x, _ in pairs)
        out[name] = round(sum(x * v for x, v in pairs) / tw, 4) if tw else None
    return out


# ----------------------------------------------------------------------------- diversity (§11)

def _band_index(plan: dict) -> dict:
    return {z: i for i, row in enumerate(plan["band_rows"]) for z, _span in row}


def diversity(pa: dict, pb: dict) -> dict:
    """How different two plans of the same brief really are — concept difference, not noise."""
    ca, cb = set(contacts(pa)), set(contacts(pb))
    union = ca | cb
    topo = round(1.0 - len(ca & cb) / len(union), 4) if union else 0.0
    ba, bb = _band_index(pa), _band_index(pb)
    common = sorted(set(ba) & set(bb))
    band_moves = sum(1 for z in common if ba[z] != bb[z])
    ra, rb = pa["rooms"], pb["rooms"]
    fw = max(pa["footprint_m"][2], pb["footprint_m"][2]) or 1.0
    fh = max(pa["footprint_m"][3], pb["footprint_m"][3]) or 1.0
    shift = [abs((ra[z]["rect_m"][0] + ra[z]["rect_m"][2] / 2) - (rb[z]["rect_m"][0] + rb[z]["rect_m"][2] / 2)) / fw
             + abs((ra[z]["rect_m"][1] + ra[z]["rect_m"][3] / 2) - (rb[z]["rect_m"][1] + rb[z]["rect_m"][3] / 2)) / fh
             for z in common]
    da, db = door_graph(pa), door_graph(pb)
    ea = {frozenset((x, y)) for x in da for y in da[x]}
    eb = {frozenset((x, y)) for x in db for y in db[x]}
    door_j = round(1.0 - len(ea & eb) / len(ea | eb), 4) if (ea | eb) else 0.0
    return {
        "contact_jaccard_distance": topo,
        "door_graph_jaccard_distance": door_j,
        "rooms_changing_band": band_moves,
        "rooms_changing_band_share": round(band_moves / len(common), 4) if common else 0.0,
        "mean_room_shift": round(statistics.mean(shift), 4) if shift else 0.0,
        "same_arrival_room": pa["entrance_door"]["b"] == pb["entrance_door"]["b"],
        "same_band_count": pa["n_bands"] == pb["n_bands"],
    }


def concept_label(d: dict) -> str:
    """A coarse, documented reading of the diversity numbers: are these two different ideas?"""
    if d["contact_jaccard_distance"] >= 0.5 or d["rooms_changing_band_share"] >= 0.5:
        return "DIFFERENT_CONCEPT"
    if d["contact_jaccard_distance"] >= 0.25 or d["rooms_changing_band_share"] >= 0.25 or not d["same_arrival_room"]:
        return "VARIANT"
    return "MINOR_PERMUTATION"


# ----------------------------------------------------------------------------- the run

def run(pool_path: str, out_path: str) -> dict:
    pool = json.load(open(pool_path))
    pri = priors_mod.load_priors()
    out = {"metrics": {n: {"dimension": d.dimension, "direction": d.direction, "unit": d.unit,
                           "availability": d.availability, "definition": d.definition, "inputs": d.inputs,
                           "rationale": d.rationale, "limitations": d.limitations}
                       for n, d in METRICS.items()},
           "scenarios": SCENARIOS, "briefs": {}, "pairs": []}
    signal = {k: {"briefs_varying": 0, "briefs_present": 0, "pairs_deciding": 0, "pairs": 0} for k in RANKED}

    for bid, b in sorted(pool["briefs"].items()):
        plans = b["plans"]
        if not plans:
            continue
        vecs = [evaluate(p, pri) for p in plans]
        norms = normalise(vecs)
        dims = [dimension_scores(n) for n in norms]
        scen = [scenario_scores(d) for d in dims]
        idx = [p["candidate"] for p in plans]
        heur = [p["heuristic_score"] for p in plans]

        for k in RANKED:
            signal[k]["briefs_present"] += 1
            if len({round(v[k], 9) for v in vecs}) > 1:
                signal[k]["briefs_varying"] += 1

        pairs = []
        for i, j in itertools.combinations(range(len(plans)), 2):
            raw = pareto(vecs[i], vecs[j])
            dkeys = [d for d in DIMENSIONS if dims[i][d] is not None and dims[j][d] is not None]
            ds = [1 if dims[i][d] > dims[j][d] + TOL else (-1 if dims[i][d] < dims[j][d] - TOL else 0) for d in dkeys]
            dim_dom = "A" if (all(x >= 0 for x in ds) and any(x > 0 for x in ds)) else \
                      ("B" if (all(x <= 0 for x in ds) and any(x < 0 for x in ds)) else "NONE")
            wins_a = sum(1 for k in RANKED if better(k, vecs[i][k], vecs[j][k]) > 0)
            wins_b = sum(1 for k in RANKED if better(k, vecs[i][k], vecs[j][k]) < 0)
            decided = wins_a + wins_b
            for k in RANKED:
                signal[k]["pairs"] += 1
                if better(k, vecs[i][k], vecs[j][k]) != 0:
                    signal[k]["pairs_deciding"] += 1
            share = max(wins_a, wins_b) / decided if decided else 0.0
            cls = "CLEAR" if raw != "NONE" else ("NEAR_CLEAR" if share >= 0.75 else "TRADE_OFF")
            div = diversity(plans[i], plans[j])
            pairs.append({
                "brief": bid, "a": idx[i], "b": idx[j], "pareto_raw": raw, "pareto_dimension": dim_dom,
                "metric_wins_a": wins_a, "metric_wins_b": wins_b, "metrics_deciding": decided,
                "win_share": round(share, 4), "class": cls,
                "dim_wins_a": sum(1 for x in ds if x > 0), "dim_wins_b": sum(1 for x in ds if x < 0),
                "scenario_pref": {s: ("A" if (scen[i][s] or 0) > (scen[j][s] or 0) + TOL else
                                      ("B" if (scen[i][s] or 0) < (scen[j][s] or 0) - TOL else "TIE"))
                                  for s in SCENARIOS},
                "heuristic_pref": "A" if heur[i] > heur[j] + TOL else ("B" if heur[i] < heur[j] - TOL else "TIE"),
                "diversity": div, "concept": concept_label(div),
            })
        out["pairs"].extend(pairs)

        order_equal = sorted(range(len(plans)), key=lambda i: (-(scen[i]["equal"] or 0), idx[i]))
        copeland = []
        for i in range(len(plans)):
            w = sum(1 for p in pairs if (p["a"] == idx[i] and p["pareto_dimension"] == "A")
                    or (p["b"] == idx[i] and p["pareto_dimension"] == "B"))
            copeland.append(w)
        out["briefs"][bid] = {
            "plans": idx, "heuristic_scores": heur,
            "heuristic_best": idx[max(range(len(plans)), key=lambda i: (heur[i], -idx[i]))],
            "vectors": {str(idx[i]): vecs[i] for i in range(len(plans))},
            "dimension_scores": {str(idx[i]): dims[i] for i in range(len(plans))},
            "scenario_scores": {str(idx[i]): scen[i] for i in range(len(plans))},
            "dimension_dominance_wins": {str(idx[i]): copeland[i] for i in range(len(plans))},
            "best_equal_weight": idx[order_equal[0]],
            "scenario_best": {s: idx[max(range(len(plans)), key=lambda i: ((scen[i][s] or 0), -idx[i]))] for s in SCENARIOS},
            "varying_metrics": sorted({k for k in RANKED if len({round(v[k], 9) for v in vecs}) > 1}),
            "pairs": pairs,
        }

    tot = len(out["pairs"])
    out["summary"] = {
        "briefs": len(out["briefs"]), "plans": sum(len(b["plans"]) for b in out["briefs"].values()),
        "pairs": tot,
        "pareto_raw_decided": sum(1 for p in out["pairs"] if p["pareto_raw"] != "NONE"),
        "pareto_dimension_decided": sum(1 for p in out["pairs"] if p["pareto_dimension"] != "NONE"),
        "class_counts": {c: sum(1 for p in out["pairs"] if p["class"] == c) for c in ("CLEAR", "NEAR_CLEAR", "TRADE_OFF")},
        "concept_counts": {c: sum(1 for p in out["pairs"] if p["concept"] == c)
                           for c in ("DIFFERENT_CONCEPT", "VARIANT", "MINOR_PERMUTATION")},
        "scenario_agreement": {s: round(sum(1 for p in out["pairs"] if p["scenario_pref"][s] == p["scenario_pref"]["equal"]) / tot, 4)
                               for s in SCENARIOS} if tot else {},
        "heuristic_vs_equal_weight_agreement": round(
            sum(1 for p in out["pairs"] if p["heuristic_pref"] == p["scenario_pref"]["equal"]) / tot, 4) if tot else None,
        "briefs_where_heuristic_best_equals_equal_weight_best": sum(
            1 for b in out["briefs"].values() if b["heuristic_best"] == b["best_equal_weight"]),
        "metric_signal": {k: {**v, "brief_variation_rate": round(v["briefs_varying"] / max(v["briefs_present"], 1), 4),
                              "pair_decision_rate": round(v["pairs_deciding"] / max(v["pairs"], 1), 4)}
                          for k, v in signal.items()},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    s = out["summary"]
    print(json.dumps({k: s[k] for k in ("briefs", "plans", "pairs", "pareto_raw_decided", "pareto_dimension_decided",
                                        "class_counts", "concept_counts", "scenario_agreement",
                                        "heuristic_vs_equal_weight_agreement",
                                        "briefs_where_heuristic_best_equals_equal_weight_best")}, indent=1))
    dead = [k for k, v in s["metric_signal"].items() if v["brief_variation_rate"] == 0]
    weak = sorted(s["metric_signal"].items(), key=lambda kv: kv[1]["pair_decision_rate"])[:8]
    print("metrics that never vary within any brief:", dead)
    print("lowest pair-decision rates:", [(k, v["pair_decision_rate"]) for k, v in weak])
    return out


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
