"""#142N step 1 — the relation `circulation_prefers` actually defines, and its failure modes.

`circulation_metrics.circulation_prefers(current, current_area, candidate, candidate_area)` returns
`None` when the candidate "earns the primary". Read as a relation on plans,

    y >- x   iff   better_on(x, y) is non-empty   AND   area(y) >= 0.85 * area(x)

where `better_on` is production's own `better` list, which fires when the candidate is better on
ANY ONE of four things (the docstring names three; the code also appends `area`):

    ratio            candidate.ratio            < current.ratio            - 0.02
    longest_segment  candidate.longest_segment  < current.longest_segment  - 0.02   (both not None)
    dead_end_count   candidate.dead_end_count   < current.dead_end_count
    area             candidate_area             > current_area             + 0.05

This module reproduces that decomposition and CHECKS it against production's own return value on
every pair, so the cause attribution below is production's behaviour and not a paraphrase of it.

Everything here is measurement. `circulation_metrics` is imported and called; it is never modified.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from app.vertical_slice.circulation_metrics import (AREA_KEEP_RATIO, _EPS, CirculationMetrics,
                                                    circulation_prefers, classify_extreme)

#: The four things the code compares. `area` is NOT a circulation measure; it is listed because
#: the implementation puts it in the same disjunction (see §"AREA_SUBSTITUTION" below).
MEASURES = ("ratio", "longest_segment", "dead_end_count", "area")
#: The three the docstring names — the ones that are actually about circulation.
CIRCULATION_MEASURES = ("ratio", "longest_segment", "dead_end_count")
#: The absolute area margin the code uses for the `area` disjunct, in m2.
AREA_BETTER_MARGIN_M2 = 0.05


@dataclass(frozen=True)
class Plan:
    """One validator-PASS plan, carrying exactly the two arguments production passes to
    `circulation_prefers` plus the circulation quantities it does NOT compare."""

    dataset: str
    brief: str
    candidate: int
    #: `design.gross_area_m2` — what `general_pipeline` passes as `*_area_m2`.
    area_m2: float
    metrics: CirculationMetrics
    #: The plan record, for the privacy/zoning and rendering steps.
    record: dict

    @property
    def key(self) -> str:
        return f"{self.brief}#{self.candidate}"


def plan_from_record(dataset: str, record: dict) -> Plan:
    c = record["production_quality"]["circulation"]
    return Plan(
        dataset=dataset, brief=record["brief"], candidate=record["candidate"],
        area_m2=record["gross_area_m2"],
        metrics=CirculationMetrics(
            area_m2=c["area_m2"], ratio=c["ratio"], longest_segment_m=c["longest_segment_m"],
            total_length_m=c["total_length_m"], narrowest_width_m=c["narrowest_width_m"],
            dead_end_count=c["dead_end_count"], turn_count=c["turn_count"],
            duplicated_segment_count=c["duplicated_segment_count"],
            duplicated_area_m2=c["duplicated_area_m2"]),
        record=record)


def plans_of(pool: dict, dataset: str) -> dict[str, list[Plan]]:
    return {bid: [plan_from_record(dataset, r) for r in recs]
            for bid, recs in sorted(pool["pools"][dataset].items())}


# --------------------------------------------------------------------- the relation, decomposed

def better_on(x: Plan, y: Plan) -> tuple[str, ...]:
    """Production's own `better` list for `circulation_prefers(current=x, candidate=y)`."""
    out = []
    if y.metrics.ratio < x.metrics.ratio - _EPS:
        out.append("ratio")
    if (y.metrics.longest_segment_m is not None and x.metrics.longest_segment_m is not None
            and y.metrics.longest_segment_m < x.metrics.longest_segment_m - _EPS):
        out.append("longest_segment")
    if y.metrics.dead_end_count < x.metrics.dead_end_count:
        out.append("dead_end_count")
    if y.area_m2 > x.area_m2 + AREA_BETTER_MARGIN_M2:
        out.append("area")
    return tuple(out)


def floor_ok(x: Plan, y: Plan) -> bool:
    """Rule 2 — the candidate still delivers `AREA_KEEP_RATIO` of the CURRENT plan's area. The
    threshold is relative to `x`, so the same `y` clears it against one reference and not another."""
    return y.area_m2 >= AREA_KEEP_RATIO * x.area_m2


def beats(x: Plan, y: Plan) -> bool:
    """`True` when production says `y` takes the primary from `x`."""
    return bool(better_on(x, y)) and floor_ok(x, y)


def verdict_agrees(x: Plan, y: Plan) -> bool:
    """The decomposition above must agree with production's own return value on every pair."""
    return (circulation_prefers(x.metrics, x.area_m2, y.metrics, y.area_m2) is None) == beats(x, y)


def edges(plans: list[Plan]) -> dict[tuple[str, str], tuple[str, ...]]:
    """{(x, y): causes} for every ordered pair where `y` beats `x`, with the causes that carried it."""
    out = {}
    for x, y in itertools.permutations(plans, 2):
        causes = better_on(x, y)
        if causes and floor_ok(x, y):
            out[(x.key, y.key)] = causes
    return out


# ------------------------------------------------------------------------------ failure modes

def mutual_pairs(plans: list[Plan]) -> list[dict]:
    """Unordered pairs where EACH beats the other — the relation is not antisymmetric, so it is not
    a strict partial order at all, independently of any cycle of length 3. In a pairwise call like
    `_guard_demoted_hub`'s, such a pair's outcome is decided purely by which plan is passed as
    `current`."""
    out = []
    for x, y in itertools.combinations(plans, 2):
        if beats(x, y) and beats(y, x):
            out.append({"a": x.key, "b": y.key,
                        "b_beats_a_by": list(better_on(x, y)), "a_beats_b_by": list(better_on(y, x)),
                        "area_m2": [x.area_m2, y.area_m2]})
    return out


def ordered_three_cycles(plans: list[Plan]) -> list[tuple[str, str, str]]:
    """Every ordered triple i>-j>-k>-i, the same count #142M reported (3 orderings per cycle)."""
    beat = {(x.key, y.key): beats(x, y) for x, y in itertools.permutations(plans, 2)}
    ids = [p.key for p in plans]
    return [(i, j, k) for i in ids for j in ids for k in ids
            if len({i, j, k}) == 3 and beat.get((i, j)) and beat.get((j, k)) and beat.get((k, i))]


def distinct_three_cycles(plans: list[Plan]) -> list[tuple[str, str, str]]:
    """One canonical representative per 3-cycle (rotation-normalised, smallest id first)."""
    seen, out = set(), []
    for cyc in ordered_three_cycles(plans):
        i = cyc.index(min(cyc))
        canon = cyc[i:] + cyc[:i]
        if canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def classify_cycle(cycle: tuple[str, str, str], by_key: dict[str, Plan]) -> dict:
    """The root cause of ONE cycle, from the causes that carried its three edges.

    `single_measure` is the question that decides between the two candidate explanations the task
    lists. A strict comparison on ONE scalar cannot cycle (summing i<j-e, j<k-e, k<i-e gives
    0 < -3e), so a cycle whose every edge is carried by the same single measure is impossible and
    a tolerance can therefore not be the cause. What a cycle needs is TWO measures that order the
    plans differently — the disjunction.
    """
    a, b, c = cycle
    per_edge = {f"{x}->{y}": list(better_on(by_key[x], by_key[y]))
                for x, y in ((a, b), (b, c), (c, a))}
    union = sorted({m for v in per_edge.values() for m in v}, key=MEASURES.index)
    # the measures that are, on their own, enough to carry every edge of the cycle
    sufficient = [m for m in MEASURES if all(m in v for v in per_edge.values())]
    area_only_edges = [k for k, v in per_edge.items() if v == ["area"]]
    if area_only_edges:
        cause = "AREA_SUBSTITUTION"
    elif len(union) >= 2:
        cause = "DISJUNCTION"
    else:
        cause = "SINGLE_MEASURE_IMPOSSIBLE"
    return {"cycle": list(cycle), "causes_per_edge": per_edge, "measures_involved": union,
            "single_measure_sufficient": sufficient, "area_only_edges": area_only_edges,
            "root_cause": cause,
            "values": {k: {"ratio": by_key[k].metrics.ratio,
                           "longest_segment_m": by_key[k].metrics.longest_segment_m,
                           "dead_end_count": by_key[k].metrics.dead_end_count,
                           "area_m2": by_key[k].area_m2} for k in cycle}}


# ----------------------------------------------------------------- what the cycles actually cost

def fold_winners(plans: list[Plan], *, max_exact: int = 8, samples: int = 20000,
                 seed: int = 142) -> dict:
    """Production's own ranking pattern — keep `current`, replace it whenever the next candidate is
    preferred — run over every arrival order of the same plan set.

    This is what "cannot define an ordering" costs in practice: the number of DISTINCT plans this
    fold can end on when nothing changes but the order the plans arrive in. 1 means the relation
    happens to pick a stable winner on this set; more than 1 means the selected plan is an artefact
    of iteration order.
    """
    n = len(plans)
    if n < 2:
        return {"n": n, "orders": 1, "distinct_winners": 1, "winners": {plans[0].key: 1} if n else {},
                "exhaustive": True}
    if n <= max_exact:
        orders = list(itertools.permutations(plans))
        exhaustive = True
    else:
        rng = random.Random(seed)
        orders = []
        for _ in range(samples):
            o = list(plans)
            rng.shuffle(o)
            orders.append(tuple(o))
        exhaustive = False
    counts: dict[str, int] = {}
    for order in orders:
        current = order[0]
        for cand in order[1:]:
            if beats(current, cand):
                current = cand
        counts[current.key] = counts.get(current.key, 0) + 1
    return {"n": n, "orders": len(orders), "distinct_winners": len(counts),
            "winners": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "exhaustive": exhaustive}


def tolerance_sensitivity(plans: list[Plan]) -> dict:
    """The SAME 0.02 constant is applied to a dimensionless ratio and to a length in metres.

    On this pool the circulation ratio spans a few hundredths, so 0.02 is a large share of the
    whole observed range, while 0.02 m on a corridor of ~10 m is below the grid's own noise. The
    numbers here say how much of each measure's range the one tolerance covers.
    """
    ratios = [p.metrics.ratio for p in plans]
    longs = [p.metrics.longest_segment_m for p in plans if p.metrics.longest_segment_m is not None]
    def span(v):
        return round(max(v) - min(v), 4) if v else None
    return {"eps": _EPS,
            "ratio": {"min": round(min(ratios), 4), "max": round(max(ratios), 4), "span": span(ratios),
                      "eps_share_of_span": round(_EPS / span(ratios), 3) if span(ratios) else None},
            "longest_segment_m": {"min": round(min(longs), 3) if longs else None,
                                  "max": round(max(longs), 3) if longs else None,
                                  "span": span(longs),
                                  "eps_share_of_span": round(_EPS / span(longs), 4) if span(longs) else None}}


def bounds_screen(plans: list[Plan]) -> dict:
    """Whether `classify_extreme` — the calibrated UPPER bounds C26 already enforces — still
    separates anything inside a pool of plans that have all passed the validators."""
    extreme = [p.key for p in plans if classify_extreme(p.metrics) is not None]
    return {"plans": len(plans), "extreme": len(extreme), "extreme_keys": extreme}


__all__ = ["MEASURES", "CIRCULATION_MEASURES", "AREA_BETTER_MARGIN_M2", "Plan", "plan_from_record",
           "plans_of", "better_on", "floor_ok", "beats", "verdict_agrees", "edges", "mutual_pairs",
           "ordered_three_cycles", "distinct_three_cycles", "classify_cycle", "fold_winners",
           "tolerance_sensitivity", "bounds_screen"]


def measure_conflicts(plans: list[Plan]) -> dict:
    """How often two of F0's own measures rank the SAME pair in opposite directions.

    This is the structural reason a disjunction cycles, measured rather than argued: if the three
    measures always agreed, "better on at least one" would coincide with "better on all" and the
    relation would be a total order. Every conflicting pair is a pair where the comparator has to
    choose between two circulation objectives and instead declares both plans the winner.
    """
    def sign(a, b):
        if a is None or b is None:
            return 0
        eps = _EPS if isinstance(a, float) else 0
        if a < b - eps:
            return -1
        if b < a - eps:
            return 1
        return 0

    fields = {"ratio": lambda p: p.metrics.ratio,
              "longest_segment": lambda p: p.metrics.longest_segment_m,
              "dead_end_count": lambda p: p.metrics.dead_end_count,
              "area": lambda p: p.area_m2}
    out: dict[str, dict] = {}
    for m1, m2 in itertools.combinations(fields, 2):
        conflict = agree = silent = 0
        for x, y in itertools.combinations(plans, 2):
            s1 = sign(fields[m1](x), fields[m1](y))
            s2 = sign(fields[m2](x), fields[m2](y))
            if s1 == 0 or s2 == 0:
                silent += 1
            elif s1 == s2:
                agree += 1
            else:
                conflict += 1
        decided = conflict + agree
        out[f"{m1} vs {m2}"] = {"conflict": conflict, "agree": agree, "one_is_tied": silent,
                                "conflict_share_of_decided": round(conflict / decided, 3) if decided else None}
    return out


__all__ += ["measure_conflicts"]
