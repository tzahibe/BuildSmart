"""Concept Engine v2 (4/5) — Issue #78: the flag-on stage wired into `run_general`.

AC-3 and AC-6 are proved against a REAL, frozen regression-corpus context (not a synthetic
fixture): a request whose shown plan set, flag ON, genuinely contains two circulation classes —
found via `spikes/failure_log_sweep/concept_diversity_v2.py` (context index 1 of `tests/
regression_corpus/corpus.json`'s PLANNED cases, `project_id` below). Hard-coded here rather than
read back from the corpus file, so this test does not depend on the corpus's own ordering.

A `_ClassRecorder` (the same instrumentation `spikes/failure_log_sweep/concept_diversity.py`'s own
`_ClassRecorder` uses for the Issue #75 baseline) matches every `DemoDesign` the demo service hands
back to the `RealizedPlan` `general_pipeline._realize` built it from, by room-rectangle signature —
so "the label matches the realized class" and "shown plans are pairwise distinct" are checked
against the SAME realized geometry the pipeline itself classified, never against the label's own
claim.
"""
from __future__ import annotations

import pytest

from app.demo import service as svc
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice.concept_spec import CirculationClass, concept_spec_of, topologically_distinct
from spikes.failure_log_sweep.sweep import project_from_context

#: A single-bedroom, 2-wet-room, safe-room brief on an 11x12 footprint within an 18x22.5 plot —
#: `project_id` "47f81017-..." in the frozen corpus. Flag ON, its shown set contains a SPINE
#: primary and a FRONT_BAND alternative.
_MULTI_CLASS_CONTEXT = {
    "project_id": "47f81017-3d75-4783-8958-6790a5791ffc",
    "plot_width_m": 18.0, "plot_depth_m": 22.5, "street_facing_side": "NORTH",
    "built_area_m2": 132.0, "footprint_width_m": 11.0, "footprint_depth_m": 12.0,
    "bedrooms": 1, "wet_rooms": 2, "safe_room": True, "open_plan": False,
}


def _layout_signature_of_rooms(rooms) -> tuple:
    return tuple(sorted((zid, round(x, 3), round(y, 3), round(w, 3), round(h, 3))
                        for zid, x, y, w, h in rooms))


def _demo_design_rooms(design) -> tuple:
    return tuple((r.id, r.x, r.y, r.width_m, r.depth_m) for r in design.rooms)


def _realized_plan_rooms(design) -> tuple:
    # `r.rect_m` is the GROSS (centerline) rect; `DemoDesign.rooms` pairs that same GROSS corner
    # with the NET width/depth (`app.demo.contract.RoomOut`'s own documented convention) — using
    # `net_w_m`/`net_h_m` here, not `rect_m`'s own width/height, is what makes the two signatures
    # comparable at all once a room's walls have real thickness.
    return tuple((r.zone_id, r.rect_m[0], r.rect_m[1], r.net_w_m, r.net_h_m) for r in design.rooms)


class _ClassRecorder:
    """Records every `RealizedPlan` `_realize` builds, keyed by its own layout signature, so a
    `DemoDesign` the demo service later hands back can be matched to the `RealizedPlan` it was
    realized from — mirrors `concept_diversity.py`'s `_ClassRecorder` (Issue #75)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch):
        self._orig = gp._realize
        self.by_signature: dict[tuple, object] = {}
        monkeypatch.setattr(gp, "_realize", self._realize)

    def _realize(self, *args, **kwargs):
        plan = self._orig(*args, **kwargs)
        sig = _layout_signature_of_rooms(_realized_plan_rooms(plan.design))
        self.by_signature[sig] = plan
        return plan

    def plan_for(self, design) -> object | None:
        sig = _layout_signature_of_rooms(_demo_design_rooms(design))
        return self.by_signature.get(sig)


@pytest.fixture
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gp, "CONCEPT_ENGINE_V2_ENABLED", True)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _ClassRecorder:
    return _ClassRecorder(monkeypatch)


def _shown_designs(flag_on, recorder):
    project = project_from_context(_MULTI_CLASS_CONTEXT)
    result = svc.generate_demo_design(project)
    return [result.design, *result.alternatives]


def test_flag_off_never_calls_plans_per_class(monkeypatch: pytest.MonkeyPatch):
    """The gate mechanism itself (the `LAUNDRY_ROOM_ENABLED` pattern): with the flag at its default
    (off), `run_general` never reaches `concept_engine_v2.plans_per_class` at all — the alternatives
    come from `_alternative_plans` alone, whatever this module does or does not implement."""
    assert gp.CONCEPT_ENGINE_V2_ENABLED is False

    def _fail(*args, **kwargs):
        raise AssertionError("plans_per_class must not be called while the flag is off")

    monkeypatch.setattr(gp.concept_engine_v2, "plans_per_class", _fail)
    project = project_from_context(_MULTI_CLASS_CONTEXT)
    result = svc.generate_demo_design(project)
    assert result.design is not None


def test_multi_class_context_actually_shows_two_classes(flag_on, recorder):
    """Guards the fixture context itself: if the corpus/pipeline ever changes so this context no
    longer demonstrates diversity, the two tests below would otherwise pass vacuously."""
    shown = _shown_designs(flag_on, recorder)
    classes = {recorder.plan_for(d).circulation_class for d in shown if recorder.plan_for(d)}
    assert len(classes) >= 2, f"expected >=2 circulation classes, got {classes}"


def test_every_shown_plan_label_matches_its_realized_class(flag_on, recorder):
    """AC-3: every shown plan's `concept` label names the SAME class `general_pipeline._realize`
    computed for it (`concept_spec.realized_circulation_class`, read off the realized geometry)."""
    shown = _shown_designs(flag_on, recorder)
    labelled = [d for d in shown if d.concept is not None]
    assert labelled, "expected at least one shown plan to carry a concept label"
    for design in labelled:
        plan = recorder.plan_for(design)
        assert plan is not None, "labelled plan not found in the realized-plan recorder"
        assert plan.circulation_class is not None
        assert design.concept.circulation_class == plan.circulation_class.value


def test_shown_plans_are_pairwise_topologically_distinct(flag_on, recorder):
    """AC-6: no two shown plans are mirror images or re-proportionings of the same concept family
    — `concept_spec.topologically_distinct` holds for every pair of shown plans."""
    shown = _shown_designs(flag_on, recorder)
    specs = []
    for design in shown:
        plan = recorder.plan_for(design)
        assert plan is not None
        specs.append(concept_spec_of(plan.concept))
    assert len(specs) >= 2
    for i in range(len(specs)):
        for j in range(i + 1, len(specs)):
            assert topologically_distinct(specs[i], specs[j]), (
                f"shown plans {i} and {j} are not topologically distinct: {specs[i]} vs {specs[j]}")


def test_concept_label_covers_every_circulation_class():
    """`concept_engine_v2.concept_label` never raises for a class `realized_circulation_class` can
    return — every `CirculationClass` value has a Hebrew label and rationale."""
    from app.vertical_slice.concept_engine_v2 import concept_label

    for circulation_class in CirculationClass:
        label = concept_label(circulation_class)
        assert label.label
        assert label.rationale


# ------------------------------------------------------------------ AC-5: cross-outline search

def _rect_buildable(width_m: float, depth_m: float):
    """A plain rectangle, set back 6 m from y=0 — the same front-parking-band clearance
    `demo.service._buildable_from` reserves before handing a region to the adapter, so a
    realized plan's own entrance/parking checks (C16/C18) pass without going through the demo
    service's own placement machinery."""
    from app.geometry_domain.constraints import BuildableRegion
    from app.geometry_domain.primitives import MultiRegion, Region, Ring
    from app.geometry_domain.provenance import Authority, Provenance, Source

    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(0.0, 6.0, width_m, depth_m))),
        Provenance(Source.USER, Authority.AUTHORITATIVE, ref="test_cross_outline"))


def test_cross_outline_search_adds_a_second_class():
    """AC-5: a brief whose PRIMARY outline offers a single circulation class among its own
    candidates receives a second, VERIFIED class from another outline the service surveyed —
    real geometry both sides, never a mock: a 10x16 m rectangle's own candidates for this
    programme are SPINE only (measured), while a 15x11 m rectangle for the SAME programme also
    offers FRONT_BAND."""
    from app.vertical_slice import concept_generator as cg
    from app.vertical_slice import concept_engine_v2 as ce2
    from app.vertical_slice.concept_spec import CirculationClass as CC
    from app.vertical_slice.geometry_core.engine import solve_fixture
    from app.vertical_slice.safe_adapter import adapt
    from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

    program = ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, parking_spaces=0)

    primary_buildable = _rect_buildable(10.0, 16.0)
    primary_adapted = adapt(primary_buildable)
    primary_spec = ArchitecturalSpec(PlotSpec(16.0, 22.0), program)
    primary_generated = cg.generate_concepts(primary_spec, list(primary_adapted.candidates))
    assert {c.circulation_class for c in primary_generated.candidates} == {CC.SPINE}, (
        "fixture guard: the primary outline must offer exactly one class")

    def primary_realize(index: int, candidate):
        solve = solve_fixture(candidate.concept.fixture)
        return gp._realize(primary_spec, primary_buildable, None, candidate, index, solve, ())

    chosen_index, chosen_plan = next(
        (i, plan) for i, c in enumerate(primary_generated.candidates)
        if (plan := primary_realize(i, c)).ok)
    assert chosen_plan.circulation_class is CC.SPINE

    already_found = ce2.plans_per_class(
        primary_spec, primary_realize, primary_generated.candidates, chosen_index, chosen_plan)
    assert already_found == (), "fixture guard: nothing else to find on the primary's own outline"

    other_buildable = _rect_buildable(15.0, 11.0)
    other_adapted = adapt(other_buildable)
    other_spec = ArchitecturalSpec(PlotSpec(21.0, 17.0), program)
    other_generated = cg.generate_concepts(other_spec, list(other_adapted.candidates))
    assert CC.FRONT_BAND in {c.circulation_class for c in other_generated.candidates}

    def other_realize(index: int, candidate):
        solve = solve_fixture(candidate.concept.fixture)
        return gp._realize(other_spec, other_buildable, None, candidate, index, solve, ())

    outline_key = object()
    found = ce2.plans_per_class_cross_outline(
        primary_spec, chosen_plan, already_found,
        [(outline_key, ce2.OutlineCandidates(other_generated.candidates, other_realize))])

    assert len(found) >= 1
    keys = {key for key, _ in found}
    classes = {plan.circulation_class for _, plan in found}
    assert keys == {outline_key}
    assert CC.FRONT_BAND in classes
    for _, plan in found:
        assert plan.ok


# --------------------------------------------------------------------------- Issue #79 review
# finding (attempt 5): the diversity report's "excluded from both compilers" section was computed
# from hand-written copies of the two compilers' preconditions, and the hub-lobby copy was never
# updated when attempt 4 taught `compile_hub_lobby` a 3-wet-room (GUEST_WC) variant — so the
# committed report reported a population as excluded that the code already served. The copies are
# gone (the helpers now ask the compilers themselves), and this holds the two together whatever the
# implementation becomes: the report's eligibility must equal the compiler's own verdict across the
# programme matrix, because the Issue's lead direction accepts AC-3's shortfall ONLY while the
# residual population is documented accurately.

@pytest.mark.parametrize("bedrooms", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("wet_rooms", [1, 2, 3, 4])
@pytest.mark.parametrize("safe_room", [False, True])
def test_report_eligibility_mirrors_each_compilers_own_precondition(bedrooms, wet_rooms, safe_room):
    from app.vertical_slice.concept_compilers import _branched_unsupported, _hub_lobby_unsupported
    from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
    from spikes.failure_log_sweep.concept_diversity_v2 import (_branched_eligible,
                                                               _hub_lobby_eligible)

    spec = ArchitecturalSpec(plot=PlotSpec(width_m=16.0, depth_m=20.0),
                             program=ProgramSpec(bedrooms=bedrooms, wet_rooms=wet_rooms,
                                                 safe_room=safe_room))
    context = {"bedrooms": bedrooms, "wet_rooms": wet_rooms, "safe_room": safe_room}
    assert _hub_lobby_eligible(context) is (_hub_lobby_unsupported(spec) is None)
    assert _branched_eligible(context) is (_branched_unsupported(spec) is None)
