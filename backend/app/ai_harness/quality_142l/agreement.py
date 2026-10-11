"""#142L step 8 — do deterministic metrics predict the independent judge's verdict?

The central experiment. Order of operations matters and is deliberate:

  1. Measure the judge's SELF-CONSISTENCY first (order swap, exact repeat, framing change, second
     model). That consistency is the ceiling on any agreement number: a metric cannot agree with a
     verdict more reliably than the verdict agrees with itself.
  2. Keep only pairs where the judge is both DECIDED and ORDER-CONSISTENT (it named the same physical
     plan with A and B swapped). Everything else is reported, never silently dropped.
  3. On that subset, measure how often each metric, each dimension, each weighting scenario, the
     dominance rules and the production heuristic pick the judge's plan.

No metric is tuned to agree with the judge (task stop rule); this only measures.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter

from app.ai_harness.quality_142l.metrics import DIMENSIONS, METRICS

#: judge category -> the dimensions of this evaluator that speak to it
CATEGORY_TO_DIMENSIONS = {
    "circulation": ("circulation_efficiency",),
    "zoning_and_privacy": ("public_private_separation", "privacy"),
    "entrance": ("entrance_quality",),
    "public_space": ("public_zone_quality",),
    "bedrooms": ("bedroom_quality",),
    "wet_rooms": ("wet_core_quality",),
    "daylight_and_exposure": ("exposure_quality",),
    "room_proportion": ("proportion_quality",),
}
DECIDED = ("A", "B")


def _plan_choice(rec: dict) -> str | None:
    """The judge's choice expressed as the CANDIDATE INDEX, undoing the A/B presentation order.
    Returns None for EQUIVALENT / CANNOT_DETERMINE / errors."""
    c = (rec["verdict"] or {}).get("choice")
    if c not in DECIDED:
        return None
    if rec["order"] == "AB":
        return rec["a"] if c == "A" else rec["b"]
    return rec["b"] if c == "A" else rec["a"]


def run(judge_path: str, comparison_path: str, out_path: str) -> dict:
    J = json.load(open(judge_path))
    C = json.load(open(comparison_path))
    pairs = {(p["brief"], p["a"], p["b"]): p for p in C["pairs"]}
    byp: dict = {}
    for r in J["judgements"]:
        byp.setdefault((r["brief"], r["a"], r["b"]), []).append(r)

    # ---- 1. self-consistency -------------------------------------------------
    cons = {"order": {"n": 0, "same_plan": 0, "both_decided": 0, "position_bias_A": 0},
            "repeat": {"n": 0, "same": 0}, "config": {"n": 0, "same": 0}, "model": {"n": 0, "same": 0},
            "choice_distribution": Counter(), "confidence": []}
    per_pair = {}
    for key, recs in byp.items():
        prim = {r["order"]: r for r in recs if r["run"] == "primary"}
        rep = next((r for r in recs if r["run"] == "repeat"), None)
        cfg = next((r for r in recs if r["run"] == "config2"), None)
        mdl = next((r for r in recs if r["run"] == "model2"), None)
        for r in recs:
            cons["choice_distribution"][(r["verdict"] or {}).get("choice", "MISSING")] += 1
            if isinstance((r["verdict"] or {}).get("confidence"), (int, float)):
                cons["confidence"].append(r["verdict"]["confidence"])
        ab, ba = prim.get("AB"), prim.get("BA")
        order_ok, consensus = None, None
        if ab and ba:
            cons["order"]["n"] += 1
            ca, cb = _plan_choice(ab), _plan_choice(ba)
            if ca is not None and cb is not None:
                cons["order"]["both_decided"] += 1
                if ca == cb:
                    cons["order"]["same_plan"] += 1
                    order_ok, consensus = True, ca
                else:
                    order_ok = False
                    if (ab["verdict"].get("choice") == "A") and (ba["verdict"].get("choice") == "A"):
                        cons["order"]["position_bias_A"] += 1
            else:
                order_ok = None
        if ab and rep:
            cons["repeat"]["n"] += 1
            cons["repeat"]["same"] += int((ab["verdict"] or {}).get("choice") == (rep["verdict"] or {}).get("choice"))
        if ab and cfg:
            cons["config"]["n"] += 1
            cons["config"]["same"] += int(_plan_choice(ab) == _plan_choice(cfg))
        if ab and mdl:
            cons["model"]["n"] += 1
            cons["model"]["same"] += int(_plan_choice(ab) == _plan_choice(mdl))
        per_pair[key] = {"order_consistent": order_ok, "consensus_plan": consensus,
                         "ab_choice": (ab["verdict"] or {}).get("choice") if ab else None,
                         "ba_choice": (ba["verdict"] or {}).get("choice") if ba else None,
                         "config_plan": _plan_choice(cfg) if cfg else None,
                         "model2_plan": _plan_choice(mdl) if mdl else None,
                         "categories": (ab["verdict"] or {}).get("categories") if ab else None,
                         "decisive_reason": (ab["verdict"] or {}).get("decisive_reason") if ab else None}
    for k in ("order", "repeat", "config", "model"):
        d = cons[k]
        if k == "order":
            d["rate_same_plan"] = round(d["same_plan"] / d["both_decided"], 4) if d["both_decided"] else None
        else:
            d["rate_same"] = round(d["same"] / d["n"], 4) if d["n"] else None
    cons["choice_distribution"] = dict(cons["choice_distribution"])
    cons["mean_confidence"] = round(statistics.mean(cons["confidence"]), 3) if cons["confidence"] else None
    cons.pop("confidence")

    # ---- 2. the usable subset ------------------------------------------------
    usable = [(k, v) for k, v in per_pair.items() if v["order_consistent"] and v["consensus_plan"] is not None]

    # ---- 3. what predicts it -------------------------------------------------
    def rate(hit, n):
        return round(hit / n, 4) if n else None

    metric_agree = {}
    for name, d in METRICS.items():
        if d.direction == "info":
            continue
        hit = n = 0
        for (bid, a, b), v in usable:
            vec = C["briefs"][bid]["vectors"]
            va, vb = vec[str(a)][name], vec[str(b)][name]
            if abs(va - vb) <= 1e-9:
                continue
            pick = a if ((va > vb) == (d.direction == "up")) else b
            n += 1
            hit += int(pick == v["consensus_plan"])
        if n >= 8:
            metric_agree[name] = {"n": n, "agreement": rate(hit, n), "dimension": d.dimension,
                                  "availability": d.availability}

    dim_agree = {}
    for dim in DIMENSIONS:
        hit = n = 0
        for (bid, a, b), v in usable:
            ds = C["briefs"][bid]["dimension_scores"]
            sa, sb = ds[str(a)].get(dim), ds[str(b)].get(dim)
            if sa is None or sb is None or abs(sa - sb) <= 1e-9:
                continue
            n += 1
            hit += int((a if sa > sb else b) == v["consensus_plan"])
        dim_agree[dim] = {"n": n, "agreement": rate(hit, n)}

    scen_agree = {}
    for s in C["scenarios"]:
        hit = n = 0
        for (bid, a, b), v in usable:
            ss = C["briefs"][bid]["scenario_scores"]
            sa, sb = ss[str(a)].get(s), ss[str(b)].get(s)
            if sa is None or sb is None or abs(sa - sb) <= 1e-9:
                continue
            n += 1
            hit += int((a if sa > sb else b) == v["consensus_plan"])
        scen_agree[s] = {"n": n, "agreement": rate(hit, n)}

    heur_hit = heur_n = 0
    dom_hit = dom_n = 0
    for (bid, a, b), v in usable:
        p = pairs[(bid, a, b)]
        if p["heuristic_pref"] in DECIDED:
            heur_n += 1
            heur_hit += int((a if p["heuristic_pref"] == "A" else b) == v["consensus_plan"])
        if p["pareto_dimension"] in DECIDED:
            dom_n += 1
            dom_hit += int((a if p["pareto_dimension"] == "A" else b) == v["consensus_plan"])

    cat_agree = {}
    for cat, dims in CATEGORY_TO_DIMENSIONS.items():
        hit = n = 0
        for (bid, a, b), v in usable:
            cats = v["categories"] or {}
            jc = (cats.get(cat) or {}).get("better")
            if jc not in DECIDED:
                continue
            jplan = a if jc == "A" else b           # category verdicts come from the AB-ordered run
            ds = C["briefs"][bid]["dimension_scores"]
            vals = [(ds[str(a)].get(d), ds[str(b)].get(d)) for d in dims]
            vals = [(x, y) for x, y in vals if x is not None and y is not None and abs(x - y) > 1e-9]
            if not vals:
                continue
            mine = a if statistics.mean(x for x, _ in vals) > statistics.mean(y for _, y in vals) else b
            n += 1
            hit += int(mine == jplan)
        cat_agree[cat] = {"n": n, "agreement": rate(hit, n)}

    reasons = Counter()
    for _k, v in per_pair.items():
        for cat, c in (v["categories"] or {}).items():
            if isinstance(c, dict) and c.get("better") in DECIDED:
                reasons[cat] += 1

    top = sorted(metric_agree.items(), key=lambda kv: -kv[1]["agreement"])
    out = {
        "judge_self_consistency": cons,
        "pairs_judged": len(per_pair),
        "pairs_order_consistent_and_decided": len(usable),
        "metric_agreement": metric_agree,
        "dimension_agreement": dim_agree,
        "scenario_agreement": scen_agree,
        "category_agreement": cat_agree,
        "heuristic_agreement": {"n": heur_n, "agreement": rate(heur_hit, heur_n)},
        "dimension_dominance_agreement": {"n": dom_n, "agreement": rate(dom_hit, dom_n)},
        "strongest_metrics": [{"metric": k, **v} for k, v in top[:12]],
        "weakest_metrics": [{"metric": k, **v} for k, v in top[-12:]],
        "judge_category_usage": dict(reasons),
        "per_pair": {f"{b}:{a}v{c}": v for (b, a, c), v in per_pair.items()},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print(json.dumps({k: out[k] for k in ("judge_self_consistency", "pairs_judged",
                                          "pairs_order_consistent_and_decided", "heuristic_agreement",
                                          "dimension_dominance_agreement", "dimension_agreement",
                                          "scenario_agreement", "category_agreement")}, indent=1))
    print("\nstrongest metrics:", [(d["metric"], d["agreement"], d["n"]) for d in out["strongest_metrics"]])
    print("weakest metrics:", [(d["metric"], d["agreement"], d["n"]) for d in out["weakest_metrics"]])
    return out


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3])
