"""The stated budget bounds the WHOLE request, not one stage of it (#247).

THE DEFECT THESE TESTS PIN. `REQUEST_BUDGET_S` was handed to `_improve_exactly` and to nothing
else. #226 measured the consequence with `budget_s=0.2`: 23.0 s on B11 and 34.8 s on B16, and on
B16 the exact pipeline was never entered at all — the time went to the production sizer inside
`run_brain`'s own first stage, which read no deadline. So the 30 s the owner was asked to approve
was a time limit on one stage and the rest of the request was open-ended.

What is asserted here is the SHAPE of the bound, never a duration: a wall-clock assertion would
measure this machine's load rather than the code, and #226 showed the same brief swinging 27 % on
load alone. So each test counts the units of work the budget refused to START, which is
deterministic, and the durations live in the report instead.

The floor is asserted as carefully as the bound. A budget may not empty a result — cancelling work
to make a number look right would trade a slow plan for no plan — so the first plan is produced
with no deadline at all, and `test_an_impossible_budget_still_returns_the_first_plan` is the test
that would fail if anyone ever made the bound absolute.
"""
from __future__ import annotations

import time

import pytest

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice.band_pipeline import PipelineInput, PipelineSuccess, run_band_pipeline
from app.vertical_slice.brain.budget import RequestBudget
from app.vertical_slice.brain.proposer import programme_from_spec
from app.vertical_slice.brain.runner import run_brain

SMALL, LARGE = "B08", "B16"


def _brief(bid):
    return {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]


def _project(bid):
    from tests.vertical_slice.test_hub_guard import _project as mk
    b = _brief(bid)
    return mk(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                   open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                   footprint_width_m=b.footprint_width_m,
                   footprint_depth_m=b.footprint_depth_m,
                   plot_width_m=b.footprint_width_m + 8,
                   plot_depth_m=b.footprint_depth_m + 8))


def _spec_and_footprint(bid):
    b = _brief(bid)
    return svc.spec_for(_project(bid)), (b.footprint_width_m, b.footprint_depth_m)


# ----------------------------------------------------------------- the budget object itself

def test_the_budget_is_an_instant_not_a_duration_so_every_stage_reads_the_same_deadline():
    # The whole defect was a duration measured again inside each stage. `started` is taken once.
    b = RequestBudget(budget_s=10.0, started=time.monotonic() - 4.0)
    assert 5.5 < b.left() < 6.5 and not b.expired()
    assert 3.5 < b.spent() < 4.5
    assert b.deadline == b.started + 10.0


def test_an_expired_budget_names_what_it_refused_and_a_live_one_says_nothing():
    live = RequestBudget(budget_s=30.0, started=time.monotonic())
    assert live.notes() == () and live.given_up == ()
    spent = RequestBudget(budget_s=0.1, started=time.monotonic() - 9.0)
    assert spent.expired()
    spent.gave_up("4 of 8 partis were not sized")
    spent.gave_up("4 of 8 partis were not sized")          # a repeat collapses
    assert spent.given_up == ("4 of 8 partis were not sized",)
    note, = spent.notes()
    assert "0.1 s ran out" in note and "4 of 8 partis" in note


# ----------------------------------------------------- AC-3: the production path reads the budget

def test_the_production_sizer_reads_the_budget_and_names_what_it_did_not_size():
    """AC-3. `run_band_pipeline` is the stage #226 measured at 26.4 s with the budget unread."""
    spec, fp = _spec_and_footprint(SMALL)
    p = programme_from_spec(spec, fp)
    from app.vertical_slice.brain.proposer import DeterministicProposer
    prop = next(x for x in DeterministicProposer().propose(p))
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    inp = PipelineInput(name=prop.name, zones=zones, required_edges=tuple(prop.spatial),
                        footprint_m=p.footprint_m, wet_rooms=p.resolved_wet,
                        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE"))
    spent = RequestBudget(budget_s=0.0, started=time.monotonic() - 60.0)
    out = run_band_pipeline(inp, max_candidates=80, max_realizations=12,
                            prefer=lambda *a: (0,), budget=spent)
    # the floor held: an expired budget still produced this parti's plan
    assert isinstance(out, PipelineSuccess), getattr(out, "code", out)
    # ...and the pipeline said what it stopped doing rather than quietly doing less
    assert any("request budget reached" in w for w in out.warnings), out.warnings
    assert spent.given_up, "the budget must record what the pipeline refused to start"


def test_without_a_budget_the_production_sizer_reads_no_clock_and_is_byte_identical():
    """The parameter is additive: production passes nothing and must be unchanged (AC-6)."""
    spec, fp = _spec_and_footprint(SMALL)
    p = programme_from_spec(spec, fp)
    from app.vertical_slice.brain.proposer import DeterministicProposer
    prop = next(x for x in DeterministicProposer().propose(p))
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    inp = PipelineInput(name=prop.name, zones=zones, required_edges=tuple(prop.spatial),
                        footprint_m=p.footprint_m, wet_rooms=p.resolved_wet,
                        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE"))
    a = run_band_pipeline(inp, max_candidates=80, max_realizations=12, prefer=lambda *x: (0,))
    b = run_band_pipeline(inp, max_candidates=80, max_realizations=12, prefer=lambda *x: (0,),
                          budget=None)
    assert isinstance(a, PipelineSuccess) and isinstance(b, PipelineSuccess)
    assert a.realized.rects == b.realized.rects
    assert not any("request budget" in w for w in a.warnings + b.warnings)


# --------------------------------------------- AC-2: a small budget binds, and names what it cost

def test_a_tiny_budget_stops_sizing_partis_and_says_how_many_it_skipped():
    """AC-2. The bound is counted, not timed: with the budget already spent, `run_brain` sizes
    partis until one plan counts and then stops, and the result says how many it did not size."""
    spec, fp = _spec_and_footprint(SMALL)
    res = run_brain(spec, fp, brief=SMALL, request_started=time.monotonic() - 600.0, budget_s=1.0)
    assert res.accepted, "the floor must still deliver the first plan"
    assert res.budget_expired
    note, = res.notes
    assert "partis were not sized" in note and "fewer alternatives" in note
    # exactly the floor: sizing stopped at the first parti that counted
    assert sum(1 for p in res.plans if p.counts) == 1, [p.parti for p in res.plans]


def test_a_full_budget_binds_nothing_and_the_result_carries_no_note():
    """The same call with the budget intact must be the unbounded behaviour, note-free."""
    spec, fp = _spec_and_footprint(SMALL)
    res = run_brain(spec, fp, brief=SMALL, budget_s=600.0)
    assert res.accepted and not res.budget_expired and res.notes == ()


def test_the_request_start_is_what_the_budget_measures_from_not_the_brains_own_start():
    """AC-3's seam: the production prefix a brain request pays is INSIDE the budget. The same
    budget expires or not purely according to the instant the request began."""
    spec, fp = _spec_and_footprint(SMALL)
    late = run_brain(spec, fp, brief=SMALL, budget_s=5.0,
                     request_started=time.monotonic() - 600.0)
    fresh = run_brain(spec, fp, brief=SMALL, budget_s=5.0, request_started=time.monotonic())
    assert late.budget_expired and late.notes
    assert not fresh.budget_expired and fresh.notes == ()
    assert late.accepted and fresh.accepted


def test_an_impossible_budget_still_returns_the_first_plan():
    """The one fix this Issue was told NOT to reach for. A budget of zero must not empty the
    result: the first plan is produced with no deadline, so the overshoot is the floor's cost and
    a plan is never traded for a number."""
    spec, fp = _spec_and_footprint(SMALL)
    res = run_brain(spec, fp, brief=SMALL, budget_s=0.0,
                    request_started=time.monotonic() - 3600.0)
    assert res.accepted and res.distinct, "a zero budget must still deliver a plan"
    assert res.budget_expired and res.notes


def test_the_exact_sizer_says_so_when_the_budget_left_it_no_time():
    """#226 measured this as silent: the exact sizer never ran and nothing in the response said
    so, while the request still cost 23-35 s."""
    pytest.importorskip("scipy")
    spec, fp = _spec_and_footprint(SMALL)
    res = run_brain(spec, fp, brief=SMALL, sizer="exact", budget_s=0.0,
                    request_started=time.monotonic() - 3600.0)
    assert res.accepted and all(p.sizer == "production" for p in res.accepted)
    assert any("exact sizer did not run" in n for n in res.notes), res.notes


@pytest.mark.parametrize("bid", [SMALL, LARGE])
def test_the_brains_own_default_leaves_every_plan_exactly_where_it_was(bid):
    """AC-6, the shape of it: at a budget nothing can exhaust, the plans are the unbounded ones.
    The corpus regression is the other half and lives in the report."""
    spec, fp = _spec_and_footprint(bid)
    bounded = run_brain(spec, fp, brief=bid, budget_s=10_000.0)
    assert not bounded.budget_expired and bounded.notes == ()
    assert bounded.accepted
