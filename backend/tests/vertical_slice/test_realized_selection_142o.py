"""Issue #142O — the selection rule itself: realize every clean candidate inside the EXISTING budget,
keep every PASS plan, and order them by arrival rank, then the existing score, then the candidate
index.

Fast unit tests on the rule and its single source. The end-to-end behaviour on the frozen dataset
(which brief's winner moves, and that it only ever moves toward a hall arrival) is asserted in
`tests/ai_harness/test_proposal_quality_gate_142j.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.vertical_slice import general_pipeline
from app.vertical_slice.circulation_metrics import CirculationMetrics
from app.vertical_slice.arrival_policy import (ARRIVAL_RANK_CIRCULATION, ARRIVAL_RANK_LIVING,
                                               ARRIVAL_RANK_OTHER, arrival_rank)
from app.vertical_slice.proposal_selection import PlanOption


def design(arrival_roles: tuple[str, ...], zone: str = "Z1"):
    return SimpleNamespace(entrance_door=SimpleNamespace(b=zone),
                           rooms=[SimpleNamespace(zone_id=zone, roles=arrival_roles),
                                  SimpleNamespace(zone_id="OTHER", roles=("BEDROOM",))])


def circ(ratio: float = 0.12, dead_ends: int = 0) -> CirculationMetrics:
    return CirculationMetrics(area_m2=10.0, ratio=ratio, longest_segment_m=5.0, total_length_m=5.0,
                              narrowest_width_m=1.4, dead_end_count=dead_ends, turn_count=0,
                              duplicated_segment_count=0, duplicated_area_m2=0.0)


def option(index: int, score: float, entrance: int, *, ratio: float = 0.12, dead_ends: int = 0):
    return PlanOption(proposal=SimpleNamespace(name=f"P{index}"), index=index, score=score,
                      clean_rank=index, pipeline=SimpleNamespace(), entrance_rank=entrance,
                      circulation=circ(ratio, dead_ends))


# ------------------------------------------------------------------ one source for the arrival rank

@pytest.mark.parametrize("roles, expected", [
    (("HALL",), ARRIVAL_RANK_CIRCULATION),
    (("CIRCULATION",), ARRIVAL_RANK_CIRCULATION),
    (("HALL", "LIVING"), ARRIVAL_RANK_CIRCULATION),      # circulation wins when a room carries both
    (("LIVING",), ARRIVAL_RANK_LIVING),
    (("KITCHEN",), ARRIVAL_RANK_OTHER),
    ((), ARRIVAL_RANK_OTHER),
])
def test_arrival_rank_reads_the_realized_arrival_room(roles, expected):
    assert arrival_rank(design(roles)) == expected


def test_arrival_rank_is_other_when_the_entrance_targets_no_known_room():
    d = SimpleNamespace(entrance_door=SimpleNamespace(b="MISSING"), rooms=[])
    assert arrival_rank(d) == ARRIVAL_RANK_OTHER


@pytest.mark.parametrize("roles", [("HALL",), ("LIVING",), ("KITCHEN",)])
def test_the_general_pipeline_ranks_an_arrival_by_the_same_one_rule(roles):
    """`_entrance_rank` must stay a delegation, so the two selection paths can never drift apart."""
    plan = SimpleNamespace(design=design(roles))
    assert general_pipeline._entrance_rank(plan) == arrival_rank(plan.design)


# ------------------------------------------------------------------------------ the ordering rule

def test_a_better_arrival_outranks_a_better_score():
    """The one new term, and the whole justification for #142O: a hall arrival beats a living-room
    arrival even when the living-room plan scores higher."""
    hall = option(5, score=-2.0, entrance=ARRIVAL_RANK_CIRCULATION)
    living = option(0, score=0.5, entrance=ARRIVAL_RANK_LIVING)
    assert min([living, hall], key=lambda o: o.sort_key) is hall


def test_the_existing_score_decides_between_equal_arrivals():
    low = option(1, score=-1.0, entrance=ARRIVAL_RANK_LIVING)
    high = option(4, score=-0.2, entrance=ARRIVAL_RANK_LIVING)
    assert min([low, high], key=lambda o: o.sort_key) is high


def test_the_candidate_index_breaks_an_exact_tie_so_selection_is_stable():
    first = option(1, score=-0.642711, entrance=ARRIVAL_RANK_LIVING)
    second = option(2, score=-0.642711, entrance=ARRIVAL_RANK_LIVING)
    assert min([second, first], key=lambda o: o.sort_key) is first
    assert sorted([second, first], key=lambda o: o.sort_key)[0].index == 1


def test_the_order_does_not_depend_on_the_order_the_plans_arrive_in():
    import itertools
    opts = [option(0, -0.1, ARRIVAL_RANK_LIVING), option(3, -2.0, ARRIVAL_RANK_CIRCULATION),
            option(7, -2.0, ARRIVAL_RANK_CIRCULATION), option(2, -0.1, ARRIVAL_RANK_OTHER)]
    orders = {tuple(o.index for o in sorted(p, key=lambda o: o.sort_key))
              for p in itertools.permutations(opts)}
    assert orders == {(3, 7, 0, 2)}


def test_circulation_is_carried_but_never_ranks():
    """#142N measured `circulation_prefers` to be non-transitive and not even antisymmetric, so it
    is deliberately absent from the key: a plan with worse circulation on every measure still wins
    on a better arrival, and circulation never reorders two plans by itself."""
    good_circulation = option(0, score=-1.0, entrance=ARRIVAL_RANK_LIVING, ratio=0.05, dead_ends=0)
    bad_circulation = option(1, score=-1.0, entrance=ARRIVAL_RANK_CIRCULATION, ratio=0.23, dead_ends=2)
    assert min([good_circulation, bad_circulation], key=lambda o: o.sort_key) is bad_circulation
    a = option(0, score=-1.0, entrance=ARRIVAL_RANK_LIVING, ratio=0.05)
    b = option(1, score=-1.0, entrance=ARRIVAL_RANK_LIVING, ratio=0.23)
    assert a.sort_key[:2] == b.sort_key[:2]            # circulation contributes nothing to the key
    assert a.circulation.ratio != b.circulation.ratio   # but it is still carried, for explanation


# ------------------------------------------------------------- the budget, unchanged and respected

def test_the_existing_budget_still_bounds_how_many_proposals_are_tried():
    """`max_realizations` keeps its meaning and its `None` default. It is the OUTER budget — how
    many critic-clean PROPOSALS are pushed through the pipeline — and capping it at 1 restores
    exactly the old behaviour: one attempt, one plan, no alternatives to choose between.

    Measured on the frozen dataset: B05's winner moves at the default budget because a later clean
    candidate arrives through a hall. At a budget of 1 that candidate is never realized, so the
    old winner stands — which is what makes this a budget test and not a ranking test.
    """
    import json
    import os

    from app.ai_harness.topology_poc import critic as poc_critic
    from app.ai_harness.topology_poc import priors as priors_mod
    from app.ai_harness.topology_poc.selection_142j import DATASET, brief_of, candidates_of
    from app.vertical_slice.proposal_selection import ProposalSelection, select_proposal

    if not os.path.exists(DATASET):
        pytest.skip("frozen LLM dataset not present")
    pri = priors_mod.load_priors()
    rec = next(r for r in json.load(open(DATASET))["records"] if r["brief_id"] == "B05")
    tps, props = candidates_of(rec, pri)
    brief = brief_of(rec)
    fp = (brief.footprint_width_m, brief.footprint_depth_m)

    def scorer(p):
        return poc_critic.score_topology(tps[int(p.name.split("#")[1])], pri).total_score

    full = select_proposal(props, score=scorer, footprint_m=fp)
    capped = select_proposal(props, score=scorer, footprint_m=fp, max_realizations=1)
    assert isinstance(full, ProposalSelection) and isinstance(capped, ProposalSelection)

    assert full.alternatives, "the default budget must reach more than one PASS plan for B05"
    assert full.entrance_rank == ARRIVAL_RANK_CIRCULATION
    assert capped.alternatives == []
    # one attempt total: it passed, so nothing is recorded as tried-and-failed
    assert capped.tried == []
    assert capped.clean_rank == 0, "a budget of 1 can only ever return the top-scored clean candidate"
    assert capped.index != full.index, "the capped budget cannot see the better arrival"
    assert capped.entrance_rank >= full.entrance_rank                  # and so cannot beat it
