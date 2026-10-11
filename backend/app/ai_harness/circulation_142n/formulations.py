"""#142N step 2 — candidate formulations of circulation quality, compared experimentally.

Each formulation is a relation `prefers(x, y) -> bool` meaning "y is better than x". None of them
introduces a weighted sum, and every quantity any of them reads is already measured by
`circulation_metrics.measure`.

    F0 CURRENT      production's own `circulation_prefers`: better on AT LEAST ONE of ratio,
                    longest segment, dead ends or area, plus the 85% area floor.
    F0b NO_AREA     F0 with the `area` disjunct removed, i.e. the function its own docstring
                    describes. Isolates how much of F0's damage comes from letting a bigger house
                    win a CIRCULATION comparison outright.
    F1 PARETO_3     the MINIMAL repair of F0: the same three circulation measures, but "no worse
                    on any and strictly better on at least one". Pareto dominance is a strict
                    partial order, so this is transitive and antisymmetric by construction.
    F2 PARETO_WASTE Pareto on the subset of measures whose direction is architecturally monotone:
                    dead ends and duplicated segments. Ratio and longest segment are dropped
                    because lower is NOT better for them (see `privacy.py` and the report's §4).
    F3 LEX_WASTE    a total order: dead ends, then duplicated segments, then ratio. Included to be
                    measured and then rejected — a lexicographic order is not weight-free, it puts
                    an infinite weight on its first term.
    F4 BOUNDS_WASTE `classify_extreme` as a screen (production's own calibrated upper bounds),
                    then F2 among the survivors.

For each formulation this module measures what the task asks for: transitivity, ties, comparable
pairs, maximal elements, and how often the fold over arrival orders lands on different plans.
"""
from __future__ import annotations

import itertools

from app.vertical_slice.circulation_metrics import _EPS, classify_extreme

from .relation import Plan, beats, better_on, floor_ok

#: Lower is better and the direction is defensible on its own: an unserved corridor end and a
#: second corridor duplicating the first are waste with no compensating architectural benefit.
MONOTONE_WASTE = ("dead_end_count", "duplicated_segment_count")
#: The three measures F0 names. Lower is better only INSIDE production's calibrated bounds; see §4.
THREE = ("ratio", "longest_segment_m", "dead_end_count")


def _value(p: Plan, measure: str):
    return getattr(p.metrics, measure)


def _cmp(p: Plan, q: Plan, measure: str) -> int:
    """-1 when p is strictly better (lower) than q on `measure`, +1 when worse, 0 when the same
    within the measure's own tolerance. `None` (no circulation room) compares as 0, which is how
    `circulation_prefers` treats it."""
    a, b = _value(p, measure), _value(q, measure)
    if a is None or b is None:
        return 0
    eps = _EPS if isinstance(a, float) else 0
    if a < b - eps:
        return -1
    if b < a - eps:
        return 1
    return 0


def pareto_prefers(x: Plan, y: Plan, measures) -> bool:
    """`y` Pareto-dominates `x` on `measures`: no measure where `x` is strictly better, at least
    one where `y` is."""
    signs = [_cmp(y, x, m) for m in measures]
    return all(s <= 0 for s in signs) and any(s < 0 for s in signs)


def lex_key(p: Plan) -> tuple:
    return (p.metrics.dead_end_count, p.metrics.duplicated_segment_count, round(p.metrics.ratio, 4),
            p.brief, p.candidate)


def beats_without_area(x: Plan, y: Plan) -> bool:
    """F0 as its own docstring describes it: the three circulation measures and the area floor,
    with `area` NOT counted as a reason to win."""
    return bool([c for c in better_on(x, y) if c != "area"]) and floor_ok(x, y)


FORMULATIONS = {
    "F0_CURRENT": lambda x, y: beats(x, y),
    "F0b_NO_AREA": beats_without_area,
    "F1_PARETO_3": lambda x, y: pareto_prefers(x, y, THREE),
    "F2_PARETO_WASTE": lambda x, y: pareto_prefers(x, y, MONOTONE_WASTE),
    "F3_LEX_WASTE": lambda x, y: lex_key(y) < lex_key(x),
    "F4_BOUNDS_WASTE": lambda x, y: (classify_extreme(x.metrics) is not None
                                     and classify_extreme(y.metrics) is None)
                                    or (classify_extreme(x.metrics) is None
                                        and classify_extreme(y.metrics) is None
                                        and pareto_prefers(x, y, MONOTONE_WASTE)),
}


def properties(plans: list[Plan], prefers) -> dict:
    """Every structural property the task asks us to measure, for one formulation on one plan set."""
    keys = [p.key for p in plans]
    by = {p.key: p for p in plans}
    pref = {(a, b): prefers(by[a], by[b]) for a, b in itertools.permutations(keys, 2)}
    pairs = list(itertools.combinations(keys, 2))
    mutual = [(a, b) for a, b in pairs if pref[(a, b)] and pref[(b, a)]]
    comparable = [(a, b) for a, b in pairs if pref[(a, b)] or pref[(b, a)]]
    incomparable = [(a, b) for a, b in pairs if not pref[(a, b)] and not pref[(b, a)]]
    # transitivity: x>-y and y>-z must imply x>-z  (reading pref[(x, y)] as "y beats x")
    violations = [(a, b, c) for a, b, c in itertools.permutations(keys, 3)
                  if pref[(a, b)] and pref[(b, c)] and not pref[(a, c)]]
    cycles3 = [(a, b, c) for a, b, c in itertools.permutations(keys, 3)
               if pref[(a, b)] and pref[(b, c)] and pref[(c, a)]]
    maximal = [k for k in keys if not any(pref[(k, o)] for o in keys if o != k)]
    # the fold over arrival orders, as production ranks
    folds: dict[str, int] = {}
    orders = itertools.permutations(plans) if len(plans) <= 8 else None
    if orders is not None and len(plans) >= 2:
        for order in orders:
            cur = order[0]
            for cand in order[1:]:
                if prefers(cur, cand):
                    cur = cand
            folds[cur.key] = folds.get(cur.key, 0) + 1
    elif plans:
        folds = {plans[0].key: 1}
    return {
        "plans": len(plans), "pairs": len(pairs),
        "comparable_pairs": len(comparable), "incomparable_pairs": len(incomparable),
        "mutual_pairs": len(mutual), "mutual_examples": [list(m) for m in mutual[:3]],
        "transitivity_violations": len(violations), "transitive": not violations,
        "antisymmetric": not mutual,
        "ordered_3_cycles": len(cycles3),
        "maximal_elements": maximal, "unique_maximum": len(maximal) == 1,
        "fold_distinct_winners": len(folds),
        "fold_winners": dict(sorted(folds.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def reference_winners(plans: list[Plan]) -> dict:
    """The two selections #142N has to compare a corrected formulation against.

    `prod_today` is the #142J gate's own pick: the highest-scoring critic-clean candidate that
    passes. `m142_step` is #142M's recommended step: entrance rank first, then the same score.
    """
    def entrance_rank(p: Plan) -> int:
        roles = set(p.record["production_quality"]["entrance"]["arrival_roles"])
        if {"HALL", "CIRCULATION"} & roles:
            return 0
        return 1 if "LIVING" in roles else 2
    prod = min(plans, key=lambda p: (-p.record["heuristic_score"], p.candidate))
    m142 = min(plans, key=lambda p: (entrance_rank(p), -p.record["heuristic_score"], p.candidate))
    return {"prod_today": prod.key, "m142_step": m142.key,
            "entrance_rank": {p.key: entrance_rank(p) for p in plans}}


def selection_impact(plans: list[Plan], prefers, refs: dict) -> dict:
    """How often a formulation would change the selection, stated the only weight-free way there
    is: the reference winner is overridden exactly when another plan STRICTLY beats it under the
    formulation. Anything else would need a precedence or a weight to settle."""
    by = {p.key: p for p in plans}
    out = {}
    for name in ("prod_today", "m142_step"):
        ref = refs[name]
        dominators = sorted(k for k in by if k != ref and prefers(by[ref], by[k]))
        out[name] = {"winner": ref, "dominated": bool(dominators), "dominators": dominators}
    return out


__all__ = ["MONOTONE_WASTE", "THREE", "FORMULATIONS", "beats_without_area", "pareto_prefers", "lex_key", "properties",
           "reference_winners", "selection_impact"]


def three_cycles_under(plans: list[Plan], prefers) -> list[tuple[str, str, str]]:
    """One canonical representative per 3-cycle of an arbitrary formulation."""
    keys = [p.key for p in plans]
    by = {p.key: p for p in plans}
    pref = {(a, b): prefers(by[a], by[b]) for a, b in itertools.permutations(keys, 2)}
    seen, out = set(), []
    for a, b, c in itertools.permutations(keys, 3):
        if pref[(a, b)] and pref[(b, c)] and pref[(c, a)]:
            i = min(range(3), key=lambda j: (a, b, c)[j])
            canon = ((a, b, c)[i:] + (a, b, c)[:i])
            if canon not in seen:
                seen.add(canon)
                out.append(canon)
    return out


def describe_cycle(cycle, by: dict[str, Plan], measures=THREE) -> dict:
    """A cycle's three edges with the values behind them, for an arbitrary measure list."""
    a, b, c = cycle
    return {
        "cycle": list(cycle),
        "better_on": {f"{x}->{y}": [m for m in measures if _cmp(by[y], by[x], m) < 0]
                      for x, y in ((a, b), (b, c), (c, a))},
        "values": {k: {m: getattr(by[k].metrics, m) for m in measures} | {"area_m2": by[k].area_m2}
                   for k in cycle},
    }


__all__ += ["three_cycles_under", "describe_cycle"]
