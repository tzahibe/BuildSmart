"""Concept-level scoring and the bounded adaptation ladder (`concept_score.py`, Issue #76)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from app.vertical_slice.concept_score import (
    ADAPT_LIMIT,
    ConceptScore,
    adapt,
    concept_score,
)
from app.vertical_slice.concept_spec import CirculationClass, ConceptSpec, ZoningSplit
from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut
from app.vertical_slice.general_pipeline import RealizedPlan, SafetyReport
from app.vertical_slice.validation import Check, ValidationReport
from app.vertical_slice.wet_core import WetCore

OK = SafetyReport(rooms_inside_buildable=True, rooms_clear_of_exclusions=True)
PASSING = ValidationReport()


def _room(zone_id, roles, rect) -> RoomOut:
    x, y, w, h = rect
    return RoomOut(zone_id=zone_id, roles=roles, rect_m=rect, net_w_m=w, net_h_m=h,
                  net_area_m2=round(w * h, 2), walls={}, wall_facts={})


def _door(a, b) -> DoorOut:
    return DoorOut(a=a, b=b, kind="DOOR", width_m=0.9, center_m=(0.0, 0.0),
                  orientation="horizontal", placeable=True, shared_length_m=0.9)


def _wet_core(clusters, kitchen_adjacent=0) -> WetCore:
    complexity = len(clusters) if clusters else 0
    shared = 2.0 if any(len(c) > 1 for c in clusters) else 0.0
    return WetCore(shared_wall_length_m=shared, clusters=clusters, cluster_count=len(clusters),
                  kitchen_adjacent_count=kitchen_adjacent, plumbing_complexity_index=complexity)


def _plan(*, index, circulation_class, hall_rect, hall_door_targets, bath_rects, wet_core) -> RealizedPlan:
    """A hand-built `RealizedPlan` of one small programme (2 bedrooms, 2 bathrooms, a kitchen and
    a hall) — real enough for `hub_guard.proportions_of`/`concept_score`'s own arithmetic to run
    on, with the hall shape/doors and wet-room adjacency the only things that vary between the two
    plans this module's AC-1 test compares."""
    rooms = [
        _room("BED1", ("BEDROOM",), (0.0, 0.0, 4.0, 3.0)),           # aspect 1.333, same both plans
        _room("MASTER", ("MASTER_BEDROOM",), (4.0, 0.0, 4.0, 3.0)),  # aspect 1.333, same both plans
        _room("KITCHEN", ("KITCHEN",), (20.0, 20.0, 4.0, 3.0)),      # far from every bathroom
        _room("HALL", ("HALL", "CIRCULATION"), hall_rect),
        _room("BATH1", ("BATHROOM",), bath_rects[0]),
        _room("BATH2", ("BATHROOM",), bath_rects[1]),
    ]
    doors = [_door("HALL", target) for target in hall_door_targets]
    entrance_door = _door("OUTSIDE", "HALL")
    design = GeometricDesign(
        plot_m=(0.0, 0.0, 30.0, 30.0), footprint_m=(0.0, 0.0, 12.0, 12.0),
        rooms=tuple(rooms), interior_doors=tuple(doors), entrance_door=entrance_door,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.2, 1.2),
        gross_area_m2=60.0, net_area_m2=54.0, wall_iterations=1, wet_core=wet_core,
    )
    return RealizedPlan(
        index=index, concept=SimpleNamespace(circulation_class=circulation_class),
        design=design, validation=PASSING, safety=OK, circulation_class=circulation_class,
    )


HUB_PLAN = _plan(
    index=0, circulation_class=CirculationClass.HUB_LOBBY,
    hall_rect=(0.0, 10.0, 3.0, 2.0),                     # aspect 1.5 — compact lobby
    hall_door_targets=("BED1", "MASTER", "KITCHEN", "BATH1"),   # 4 doors
    bath_rects=((0.0, 3.0, 2.0, 2.0), (2.0, 3.0, 2.0, 2.0)),    # touching along x=2 -> adjacent
    wet_core=_wet_core((("BATH1", "BATH2"),)),
)
SPINE_PLAN = _plan(
    index=1, circulation_class=CirculationClass.SPINE,
    hall_rect=(0.0, 10.0, 6.0, 1.0),                     # aspect 6.0 — a spine, not a lobby
    hall_door_targets=("BED1", "MASTER"),                       # 2 doors
    bath_rects=((0.0, 3.0, 2.0, 2.0), (10.0, 3.0, 2.0, 2.0)),   # far apart -> not adjacent
    wet_core=_wet_core((("BATH1",), ("BATH2",))),
)


def test_score_is_deterministic_and_prefers_verified_lobby_over_spine():
    hub_score = concept_score(HUB_PLAN)
    spine_score = concept_score(SPINE_PLAN)

    # Determinism: the same plan scores byte-identically on repeat calls (no hidden state, no
    # hash-order dependency) — the property AC-1 calls "across runs and process restarts".
    assert concept_score(HUB_PLAN) == hub_score
    assert concept_score(SPINE_PLAN) == spine_score

    # Both declared classes survive realization in this fixture (set directly, no mismatch).
    assert hub_score.class_verified and spine_score.class_verified

    # M1 (bedroom/master aspect) is IDENTICAL between the two plans by construction.
    assert hub_score.bedroom_aspect == pytest.approx(spine_score.bedroom_aspect)
    assert hub_score.master_aspect == pytest.approx(spine_score.master_aspect)

    # M4 and M5 are strictly better for the hub-lobby plan.
    assert hub_score.hall_aspect_median < spine_score.hall_aspect_median
    assert hub_score.hall_door_count > spine_score.hall_door_count
    assert hub_score.wet_adjacency_share > (spine_score.wet_adjacency_share or 0.0)

    # M4/M5 better, M1 not worse -> the verified hub-lobby plan orders above the spine plan.
    assert hub_score.total > spine_score.total
    assert hub_score.key() < spine_score.key()


def test_a_rejected_plan_always_sorts_last_regardless_of_total():
    failing_validation = ValidationReport(checks=[Check("C24", "access topology", False, "defect")])
    broken = replace(HUB_PLAN, validation=failing_validation)
    broken_score = concept_score(broken)
    assert broken_score.rejected
    assert broken_score.total > concept_score(SPINE_PLAN).total  # a higher raw total…
    assert broken_score.key() > concept_score(SPINE_PLAN).key()  # …still sorts worse


BASE_SPEC = ConceptSpec(
    circulation_class=CirculationClass.SPINE,
    zoning=ZoningSplit.SIDE_BY_SIDE,
    wet_core_groups=(("BATH1",), ("BATH2",)),
    programme_reference=("BATH1", "BATH2", "BED1", "HALL", "KITCHEN", "MASTER"),
    outline_reference=(0,),
)


def _score(**overrides) -> ConceptScore:
    base = dict(index=0, rejected=False, class_verified=True, circulation_class=CirculationClass.SPINE,
               bedroom_aspect=1.2, master_aspect=1.1, circulation_share=0.1, hall_door_count=2,
               hall_aspect_median=3.0, wet_adjacency_share=0.5, plumbing_complexity_index=2,
               entrance_rank=0, total=0.0)
    base.update(overrides)
    return ConceptScore(**base)


def test_adapt_keeps_class_and_respects_limit():
    poor_wet_score = _score(wet_adjacency_share=0.5, plumbing_complexity_index=2)
    good_wet_score = _score(wet_adjacency_share=1.0, plumbing_complexity_index=1)

    # Rung 1: cluster the wet rooms — the concept-level "SPINE_SERVICE_CLUSTER" move.
    step1 = adapt(BASE_SPEC, SPINE_PLAN, poor_wet_score, attempt=0)
    assert step1 is not None
    assert step1.circulation_class == BASE_SPEC.circulation_class
    assert step1.wet_core_groups == (("BATH1", "BATH2"),)

    # Rung 2: clustering already happened and the wet standing is now good -> flip the zoning.
    step2 = adapt(step1, SPINE_PLAN, good_wet_score, attempt=1)
    assert step2 is not None
    assert step2.circulation_class == BASE_SPEC.circulation_class
    assert step2.zoning == ZoningSplit.FRONT_REAR

    # ADAPT_LIMIT: no further move, however good an application would otherwise be.
    assert adapt(step2, SPINE_PLAN, good_wet_score, attempt=ADAPT_LIMIT) is None
    assert adapt(step2, SPINE_PLAN, good_wet_score, attempt=ADAPT_LIMIT + 5) is None


def test_adapt_gives_up_on_a_structural_defect_regardless_of_attempt():
    failing_validation = ValidationReport(checks=[Check("C19", "exterior exposure", False, "defect")])
    broken = replace(SPINE_PLAN, validation=failing_validation)
    assert adapt(BASE_SPEC, broken, _score(wet_adjacency_share=0.0, plumbing_complexity_index=2),
                attempt=0) is None


def test_adapt_gives_up_when_no_rung_applies():
    already_clustered = replace(BASE_SPEC, wet_core_groups=(("BATH1", "BATH2"),),
                                zoning=ZoningSplit.WRAPPED)
    assert adapt(already_clustered, SPINE_PLAN, _score(wet_adjacency_share=1.0,
                                                       plumbing_complexity_index=1),
                attempt=0) is None


@pytest.mark.parametrize("cls", list(CirculationClass))
def test_adapt_never_changes_the_declared_class(cls):
    spec = replace(BASE_SPEC, circulation_class=cls)
    result = adapt(spec, SPINE_PLAN, _score(wet_adjacency_share=0.0, plumbing_complexity_index=2),
                   attempt=0)
    assert result is None or result.circulation_class == cls
