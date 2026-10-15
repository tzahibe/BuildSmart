"""The architectural brain (#197): distinct concepts -> exact geometry, through unchanged rules.

The bar these tests hold is deliberately higher than "a validator passed":
critic-clean BEFORE placement · realizes · preserves the requested graph n/n · bands >= 2.
"""
from __future__ import annotations

import pytest

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice.band_embedding import find_k4, find_triple_lens
from app.vertical_slice.brain.proposer import DeterministicProposer, programme_from_spec
from app.vertical_slice.brain.runner import run_brain
from app.vertical_slice.proposal_critic import Proposal, criticize


def _brief(bid):
    return {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]


def _spec_and_footprint(bid):
    from tests.vertical_slice.test_hub_guard import _project
    b = _brief(bid)
    project = _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                            open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                            footprint_width_m=b.footprint_width_m,
                            footprint_depth_m=b.footprint_depth_m,
                            plot_width_m=b.footprint_width_m + 8,
                            plot_depth_m=b.footprint_depth_m + 8))
    return svc.spec_for(project), (b.footprint_width_m, b.footprint_depth_m)


SMALL, MEDIUM, LARGE = "B08", "B06", "B16"


# ------------------------------------------------------------- the proposals are representable

@pytest.mark.parametrize("bid", [SMALL, MEDIUM, LARGE])
def test_every_proposal_is_free_of_the_two_obstructions_that_kill_rectangle_layouts(bid):
    """#194 measured 7 of 20 LLM proposals failing on K4 or triple-lens. These cannot: every parti
    is a tree plus at most one path, by construction."""
    spec, fp = _spec_and_footprint(bid)
    programme = programme_from_spec(spec, fp)
    for prop in DeterministicProposer().propose(programme):
        adj: dict[str, set] = {}
        for a, b in prop.spatial:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        assert find_k4(adj) is None, f"{prop.name} contains a K4"
        assert find_triple_lens(adj) is None, f"{prop.name} contains a triple-lens"


@pytest.mark.parametrize("bid", [SMALL, MEDIUM, LARGE])
def test_every_proposal_passes_the_critic_before_any_placement(bid):
    spec, fp = _spec_and_footprint(bid)
    programme = programme_from_spec(spec, fp)
    for prop in DeterministicProposer().propose(programme):
        zones = {z: programme.zones[z] for z in prop.rooms if z in programme.zones}
        from app.vertical_slice.brain.proposer import _hall_intent
        for z in prop.rooms:
            zones.setdefault(z, _hall_intent(z, 7.0))
        report = criticize(Proposal(
            name=prop.name, roles={z: zones[z].role for z in zones},
            spatial=frozenset(frozenset(e) for e in prop.spatial), access=tuple(prop.access),
            zones=zones, wet_rooms=programme.wet_rooms))
        hard = [f for f in report.findings if getattr(f, "severity", "") == "HARD"]
        assert not hard, f"{prop.name}: {[f.code for f in hard]}"


def test_a_door_is_never_declared_without_a_contact_to_carry_it():
    spec, fp = _spec_and_footprint(MEDIUM)
    programme = programme_from_spec(spec, fp)
    for prop in DeterministicProposer().propose(programme):
        contacts = {frozenset(e) for e in prop.spatial}
        for a, b in prop.access:
            if a == "ENTRANCE":
                continue
            assert frozenset((a, b)) in contacts, f"{prop.name}: door {a}->{b} has no shared wall"


# ------------------------------------------------------------- the delivered plans count

@pytest.mark.parametrize("bid", [SMALL, MEDIUM, LARGE])
def test_the_brain_delivers_at_least_two_genuinely_distinct_plans(bid):
    res = run_brain(*_spec_and_footprint(bid), brief=bid)
    assert len(res.distinct) >= 2, [f"{p.parti}:{p.stage}:{p.reason[:60]}" for p in res.plans]


@pytest.mark.parametrize("bid", [SMALL, MEDIUM, LARGE])
def test_every_accepted_plan_preserves_the_requested_graph_and_is_not_row_collapsed(bid):
    res = run_brain(*_spec_and_footprint(bid), brief=bid)
    assert res.accepted
    for p in res.accepted:
        got, want = p.spatial_preserved.split("/")
        assert got == want, f"{p.parti} lost contacts: {p.spatial_preserved}"
        got, want = p.access_preserved.split("/")
        assert got == want, f"{p.parti} lost doors: {p.access_preserved}"
        assert p.bands >= 2, f"{p.parti} collapsed to {p.bands} band(s) — a row is not a plan"


def test_distinctness_is_decided_on_geometry_not_on_the_parti_name():
    """Two partis that converge must not both be offered."""
    res = run_brain(*_spec_and_footprint(MEDIUM), brief=MEDIUM)
    sigs = [p.geometry_signature for p in res.distinct]
    assert len(sigs) == len(set(sigs))
    assert len(res.distinct) <= len(res.accepted)


def test_a_failing_parti_is_reported_not_silently_dropped():
    res = run_brain(*_spec_and_footprint(LARGE), brief=LARGE)
    for p in res.plans:
        assert p.stage, f"{p.parti} has no recorded stage"
        if not p.ok:
            assert p.reason, f"{p.parti} failed with no reason"


def test_the_brain_is_deterministic():
    a = run_brain(*_spec_and_footprint(MEDIUM), brief=MEDIUM)
    b = run_brain(*_spec_and_footprint(MEDIUM), brief=MEDIUM)
    assert [p.geometry_signature for p in a.distinct] == [p.geometry_signature for p in b.distinct]


def test_it_costs_nothing_and_calls_no_model(monkeypatch):
    """The whole point of the deterministic proposer: no network, no key, no spend."""
    import urllib.request
    def forbidden(*a, **k):
        raise AssertionError("the brain must not open a network connection")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    res = run_brain(*_spec_and_footprint(SMALL), brief=SMALL)
    assert res.distinct


# ----------------------------------------------------------------- the exact sizer seam (#197 item 4)

def test_the_exact_sizer_plans_the_small_brief_within_the_request_budget():
    pytest.importorskip("scipy")
    import time
    spec, fp = _spec_and_footprint(SMALL)
    t = time.monotonic()
    res = run_brain(spec, fp, brief=SMALL, sizer="exact", families=("band",), budget_s=30.0)
    assert time.monotonic() - t < 45.0                      # the budget plus the last solve in flight
    assert len(res.accepted) >= 5
    exact = [p for p in res.accepted if p.sizer == "exact"]
    assert exact and all(p.family == "band" for p in exact)
    for p in res.accepted:
        assert p.spatial_preserved.split("/")[0] == p.spatial_preserved.split("/")[1]


def test_the_families_flag_can_produce_a_cross_band_plan_and_every_plan_names_its_maker():
    pytest.importorskip("scipy")
    spec, fp = _spec_and_footprint(SMALL)
    res = run_brain(spec, fp, brief=SMALL, sizer="exact", families=("band", "spine", "stack", "cells"))
    assert res.accepted
    assert {p.sizer for p in res.accepted} <= {"exact", "production"}
    assert all(p.family in ("band", "spine", "stack", "cells") for p in res.accepted)


def test_without_a_solver_the_exact_sizer_falls_back_to_production_and_says_so(monkeypatch):
    from app.vertical_slice.band_pipeline import PipelineDiagnosis
    from app.vertical_slice.brain import exact_pipeline
    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline",
                        lambda *a, **k: PipelineDiagnosis("EXACT_SIZER_UNAVAILABLE", "SIZING", "scipy missing"))
    spec, fp = _spec_and_footprint(SMALL)
    res = run_brain(spec, fp, brief=SMALL, sizer="exact")
    assert res.accepted and all(p.sizer == "production" for p in res.accepted)
    assert all(any("fell back to production" in n for n in p.notes) for p in res.accepted)


def test_the_production_sizer_is_untouched_by_the_seam():
    spec, fp = _spec_and_footprint(SMALL)
    a = run_brain(spec, fp, brief=SMALL)
    b = run_brain(spec, fp, brief=SMALL, sizer="production")
    assert [p.geometry_signature for p in a.accepted] == [p.geometry_signature for p in b.accepted]
    assert all(p.sizer == "production" and p.family == "band" and p.notes == () for p in a.accepted)
