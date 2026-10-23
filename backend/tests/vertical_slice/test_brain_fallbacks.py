"""Expiry is not an error: a brain request that runs out of time is a 200 that says so (#247 AC-4).

The distinction these tests defend is the whole reason #247 was not allowed to "fix" the latency by
refusing. There are two outcomes and they must not be confused:

  the budget ran out   -> HTTP 200, a production-sized plan set, and a note naming what did not run
  the brain has no plan -> `BRAIN_NO_PLAN`, HTTP 422, the one genuine refusal

Before #247 the first outcome existed but was SILENT: #226 measured a request with `budget_s=0.2`
returning eight plans, every one production-sized, with nothing in the response saying the exact
sizer had never run — and still costing 23-35 s. The response is now honest in both directions,
and no status changed.
"""
from __future__ import annotations

import time

import pytest

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice.brain.runner import run_brain

SMALL = "B08"


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


# ------------------------------------------------- expiry through the product boundary: a 200

def test_an_expired_budget_returns_a_plan_set_through_the_service_not_an_error(monkeypatch):
    """AC-4. The request is asked for a budget it cannot possibly meet and must still answer with
    a drawn plan — the same `DemoResult` shape, no exception."""
    monkeypatch.setattr(svc, "BRAIN_BUDGET_S", 0.0)
    res = svc.generate_demo_design(_project(SMALL), brain=True)
    assert res.design is not None and res.design.rooms, "expiry must not empty the plan"
    assert res.design.validation is not None


def test_the_expired_response_says_what_did_not_run_on_every_plan(monkeypatch):
    """AC-4. #226's finding was that the response was silent about a stage that never ran."""
    monkeypatch.setattr(svc, "BRAIN_BUDGET_S", 0.0)
    res = svc.generate_demo_design(_project(SMALL), brain=True)
    plans = [res.design, *res.alternatives]
    for plan in plans:
        notes = list(plan.validation.warnings or ())
        assert any("request budget" in n for n in notes), notes
        assert any("were not sized" in n or "did not run" in n for n in notes), notes


def test_the_expired_plan_set_is_production_sized_and_names_its_sizer(monkeypatch):
    """Expiry falls back to production's geometry, which is what it has always done; what is new
    is that the plan says so in the same breath as saying the budget ran out."""
    monkeypatch.setattr(svc, "BRAIN_BUDGET_S", 0.0)
    res = svc.generate_demo_design(_project(SMALL), brain=True)
    notes = list(res.design.validation.warnings or ())
    assert any("sized by the production sizer" in n for n in notes), notes


def test_an_unexpired_request_says_nothing_about_a_budget(monkeypatch):
    """The note is not a permanent fixture of every brain response.

    The phrase matters and this test is why it was changed. The EXACT SIZER's own share runs out on
    a perfectly healthy request, and it used to report that as "request budget reached" — so a
    request with 9,970 s of budget left carried a sentence saying its budget had run out. The two
    are now distinguishable, and this asserts the request-level sentence specifically.
    """
    monkeypatch.setattr(svc, "BRAIN_BUDGET_S", 10_000.0)
    res = svc.generate_demo_design(_project(SMALL), brain=True)
    for plan in (res.design, *res.alternatives):
        notes = list(plan.validation.warnings or ())
        assert not any("request budget of" in n for n in notes), notes
        assert not any("request budget reached" in n for n in notes), notes


# --------------------------------------------- the one genuine refusal is still the only refusal

def test_a_brief_with_no_plan_at_all_is_still_the_422_and_not_a_budget_note(monkeypatch):
    """`BRAIN_NO_PLAN` must stay reachable and must stay distinguishable from expiry: a budget
    that ran out is a 200, and only an empty result is an error."""
    monkeypatch.setattr(svc, "BRAIN_BUDGET_S", 0.0)

    class _NoParti:
        def propose(self, programme):
            return ()

    import app.vertical_slice.brain.runner as rn
    real = rn.run_brain
    monkeypatch.setattr(svc, "run_brain",
                        lambda *a, **k: real(*a, **{**k, "proposer": _NoParti()}))
    with pytest.raises(svc.DemoGenerationError) as exc:
        svc.generate_demo_design(_project(SMALL), brain=True)
    assert exc.value.code == "BRAIN_NO_PLAN"


def test_expiry_and_no_plan_are_different_outcomes_of_the_same_runner():
    """The same `run_brain` call, one budget, two results — told apart by whether a plan exists
    and never by the clock."""
    spec, fp = _spec_and_footprint(SMALL)
    expired = run_brain(spec, fp, brief=SMALL, budget_s=0.0,
                        request_started=time.monotonic() - 3600.0)
    assert expired.budget_expired and expired.distinct      # 200: a plan, with a note

    class _NoParti:
        def propose(self, programme):
            return ()

    empty = run_brain(spec, fp, brief=SMALL, proposer=_NoParti())
    assert not empty.distinct and not empty.budget_expired   # 422: no plan, no budget excuse
