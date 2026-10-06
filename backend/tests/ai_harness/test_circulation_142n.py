"""#142N — the investigation's claims about `circulation_prefers`, pinned as tests.

These are claims about PRODUCTION's comparator, so they are written against
`app.vertical_slice.circulation_metrics` directly with hand-built metric values: a test here fails
if someone changes the comparator's shape, which is exactly the signal a follow-up task wants.
Nothing here asserts on the measured pools (those live in the report's data file).
"""
from __future__ import annotations

import itertools

import pytest

from app.ai_harness.circulation_142n import formulations as F
from app.ai_harness.circulation_142n import relation as R
from app.vertical_slice.circulation_metrics import (AREA_KEEP_RATIO, CirculationMetrics,
                                                    circulation_prefers)


def metrics(ratio: float, longest: float | None, dead_ends: int, *, duplicated: int = 0,
            area: float = 10.0) -> CirculationMetrics:
    return CirculationMetrics(area_m2=area, ratio=ratio, longest_segment_m=longest,
                              total_length_m=longest or 0.0, narrowest_width_m=1.4,
                              dead_end_count=dead_ends, turn_count=0,
                              duplicated_segment_count=duplicated, duplicated_area_m2=0.0)


def plan(key: str, ratio: float, longest: float | None, dead_ends: int, plan_area: float,
         *, duplicated: int = 0) -> R.Plan:
    return R.Plan(dataset="synthetic", brief="BXX", candidate=int(key), area_m2=plan_area,
                  metrics=metrics(ratio, longest, dead_ends, duplicated=duplicated), record={})


# --------------------------------------------------------------- the relation's shape

def test_the_comparator_is_a_disjunction_so_two_plans_can_each_beat_the_other():
    """Not antisymmetric. A beats B on dead ends while B beats A on ratio, so whichever is passed
    as `current` loses — the outcome of production's own pairwise call depends on argument order."""
    a = plan("1", ratio=0.10, longest=6.0, dead_ends=2, plan_area=100.0)
    b = plan("2", ratio=0.16, longest=6.0, dead_ends=0, plan_area=100.0)
    assert R.beats(a, b) and R.beats(b, a)
    assert circulation_prefers(a.metrics, a.area_m2, b.metrics, b.area_m2) is None
    assert circulation_prefers(b.metrics, b.area_m2, a.metrics, a.area_m2) is None


def test_three_plans_cycle_on_the_circulation_measures_alone():
    """The minimal cycle: equal areas, and each plan beats its predecessor on exactly ONE of the
    three measures the docstring names — a different one each time. No tolerance effect and no
    area term is involved, so neither can be the cause."""
    a = plan("1", ratio=0.18, longest=7.0, dead_ends=0, plan_area=100.0)
    b = plan("2", ratio=0.14, longest=9.0, dead_ends=0, plan_area=100.0)
    c = plan("3", ratio=0.16, longest=6.0, dead_ends=1, plan_area=100.0)
    assert R.better_on(a, b) == ("ratio",)
    assert R.better_on(b, c) == ("longest_segment",)
    assert R.better_on(c, a) == ("dead_end_count",)
    assert R.beats(a, b) and R.beats(b, c) and R.beats(c, a)


def test_a_single_measure_can_never_cycle():
    """Why a tolerance is not the cause: a strict comparison on ONE scalar is transitive, so no
    arrangement of values cycles while every edge is carried by the same measure."""
    for ratios in itertools.permutations((0.10, 0.14, 0.18)):
        ps = [plan(str(i), r, 6.0, 0, 100.0) for i, r in enumerate(ratios)]
        assert not R.ordered_three_cycles(ps)


def test_the_code_counts_a_bigger_house_as_better_circulation():
    """The implementation's fourth disjunct, which its own docstring does not mention: a plan with
    strictly WORSE circulation on all three measures still wins for being larger."""
    small = plan("1", ratio=0.10, longest=5.0, dead_ends=0, plan_area=100.0)
    large = plan("2", ratio=0.20, longest=9.0, dead_ends=2, plan_area=101.0)
    assert R.better_on(small, large) == ("area",)
    assert R.beats(small, large)
    assert not F.beats_without_area(small, large)


def test_the_area_floor_is_relative_to_whichever_plan_is_current():
    """Rule 2's threshold is `0.85 * current`, so the same candidate clears it against one
    reference and not another — the comparison is pair-relative, not a property of the plan."""
    big = plan("1", ratio=0.20, longest=9.0, dead_ends=1, plan_area=200.0)
    mid = plan("2", ratio=0.20, longest=9.0, dead_ends=1, plan_area=160.0)
    small = plan("3", ratio=0.10, longest=5.0, dead_ends=0, plan_area=100.0)
    assert R.floor_ok(mid, small) is (100.0 >= AREA_KEEP_RATIO * 160.0)
    assert not R.floor_ok(big, small)
    assert R.floor_ok(mid, plan("4", 0.1, 5.0, 0, 140.0))


def test_the_decomposition_matches_production_on_every_synthetic_pair():
    """Everything the report attributes to a cause is checked against production's own verdict."""
    ps = [plan(str(i), r, l, d, a)
          for i, (r, l, d, a) in enumerate(itertools.product((0.10, 0.18), (5.0, 9.0), (0, 2),
                                                             (100.0, 130.0)))]
    assert all(R.verdict_agrees(x, y) for x, y in itertools.permutations(ps, 2))


# --------------------------------------------------------------- the candidate formulations

def test_pareto_repair_is_transitive_and_antisymmetric_on_the_cycling_set():
    """F1 is the minimal repair: the same three measures, 'no worse on any and better on one'."""
    a = plan("1", ratio=0.10, longest=9.0, dead_ends=2, plan_area=100.0)
    b = plan("2", ratio=0.20, longest=6.0, dead_ends=1, plan_area=100.0)
    c = plan("3", ratio=0.15, longest=12.0, dead_ends=0, plan_area=100.0)
    props = F.properties([a, b, c], F.FORMULATIONS["F1_PARETO_3"])
    assert props["transitive"] and props["antisymmetric"]
    assert props["ordered_3_cycles"] == 0


def test_pareto_dominance_still_leaves_plans_incomparable():
    """And is honest about it: a partial order refuses to rank a genuine trade-off rather than
    inventing a weight for it."""
    a = plan("1", ratio=0.10, longest=9.0, dead_ends=2, plan_area=100.0)
    b = plan("2", ratio=0.20, longest=6.0, dead_ends=1, plan_area=100.0)
    assert not F.pareto_prefers(a, b, F.THREE)
    assert not F.pareto_prefers(b, a, F.THREE)


def test_pareto_dominance_fires_when_one_plan_is_better_on_everything():
    worse = plan("1", ratio=0.20, longest=9.0, dead_ends=2, plan_area=100.0)
    better = plan("2", ratio=0.10, longest=6.0, dead_ends=0, plan_area=100.0)
    assert F.pareto_prefers(worse, better, F.THREE)
    assert not F.pareto_prefers(better, worse, F.THREE)


def test_waste_only_pareto_ignores_ratio_and_segment_length():
    """F2 compares only the measures whose direction is defensible on its own. A plan with a much
    lower ratio does not beat one with fewer dead ends."""
    lean = plan("1", ratio=0.08, longest=4.0, dead_ends=2, plan_area=100.0)
    generous = plan("2", ratio=0.19, longest=9.0, dead_ends=0, plan_area=100.0)
    assert F.pareto_prefers(lean, generous, F.MONOTONE_WASTE)
    assert not F.pareto_prefers(generous, lean, F.MONOTONE_WASTE)


@pytest.mark.parametrize("name", ["F1_PARETO_3", "F2_PARETO_WASTE", "F3_LEX_WASTE",
                                  "F4_BOUNDS_WASTE"])
def test_every_proposed_formulation_is_antisymmetric_where_the_current_one_is_not(name):
    a = plan("1", ratio=0.10, longest=6.0, dead_ends=2, plan_area=100.0)
    b = plan("2", ratio=0.16, longest=6.0, dead_ends=0, plan_area=100.0)
    prefers = F.FORMULATIONS[name]
    assert not (prefers(a, b) and prefers(b, a))


def test_removing_the_area_disjunct_is_not_enough_on_its_own():
    """F0b repairs the term that carries most of the MEASURED cycles, but the rule that remains is
    still 'better on at least one', so two plans can still each beat the other. The implementation
    defect and the structural defect are separate problems."""
    a = plan("1", ratio=0.10, longest=6.0, dead_ends=2, plan_area=100.0)
    b = plan("2", ratio=0.16, longest=6.0, dead_ends=0, plan_area=100.0)
    assert F.beats_without_area(a, b) and F.beats_without_area(b, a)


def test_the_greedy_fold_lands_on_different_plans_for_different_arrival_orders():
    """What a cycle costs in production's own ranking pattern: keep `current`, replace it when the
    next candidate is preferred. On a cyclic set the winner is an artefact of iteration order."""
    a = plan("1", ratio=0.10, longest=9.0, dead_ends=2, plan_area=100.0)
    b = plan("2", ratio=0.20, longest=6.0, dead_ends=1, plan_area=100.0)
    c = plan("3", ratio=0.15, longest=12.0, dead_ends=0, plan_area=100.0)
    assert R.fold_winners([a, b, c])["distinct_winners"] == 3


def test_production_is_not_modified_by_this_investigation():
    """`circulation_prefers` still has exactly the shape the report describes — four disjuncts and
    an area floor. A follow-up that changes it should fail this test and update the report."""
    assert circulation_prefers(metrics(0.10, 5.0, 0), 100.0, metrics(0.10, 5.0, 0), 100.0) is not None
    assert circulation_prefers(metrics(0.10, 5.0, 0), 100.0, metrics(0.05, 5.0, 0), 100.0) is None
    assert circulation_prefers(metrics(0.10, 5.0, 0), 100.0, metrics(0.05, 5.0, 0), 80.0) is not None
