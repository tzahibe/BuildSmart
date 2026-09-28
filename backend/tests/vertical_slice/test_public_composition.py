"""Public-zone composition: kitchen, dining and living as a coherent composition (Issue #41).

AC-1's canonical fixtures + an open-plan fixture: the canonical single-level pipeline
(`pipeline.run_demo`) for "canonical", and a real generated open-plan design
(`ProgramSpec(open_plan_living=True)`, the same pattern `test_demo_corridor_opening.py::spine_plan`
uses) compared against its own closed-plan sibling for "not penalized for openness".

AC-2's blocking fixture is hand-built (`design_output.RoomOut`/`DoorOut`, the same pattern
`test_circulation_metrics.py`/`test_entrance_circulation.py` use for their own hand-built extreme
cases): a DINING room just wide enough to fit a placed dining table and nothing more, sitting on
the only path from the entrance to LIVING — the table's own clearance rectangle spans the room, so
no straight route exists around it.
"""
from __future__ import annotations

import pytest

from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import public_composition as pc
from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut
from app.vertical_slice.general_pipeline import run_general_from_site
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.spec import ProgramSpec

pytestmark = pytest.mark.filterwarnings("ignore")

_INTERIOR_PARTITION = WallFacts(BoundaryContext.INTERIOR, Construction.STANDARD_PARTITION)


def _room(zone_id, roles, rect_m, area=None):
    x, y, w, h = rect_m
    return RoomOut(
        zone_id=zone_id, roles=roles, rect_m=rect_m, net_w_m=w, net_h_m=h,
        net_area_m2=area if area is not None else round(w * h, 4),
        walls={s: "PARTITION" for s in ("N", "S", "E", "W")},
        wall_facts={s: _INTERIOR_PARTITION for s in ("N", "S", "E", "W")},
    )


def _door(a, b, orientation, center_m):
    return DoorOut(a=a, b=b, kind="ROOM_DOOR", width_m=0.9, center_m=center_m,
                  orientation=orientation, placeable=True, shared_length_m=1.0)


# --------------------------------------------------------------------------- real fixtures


@pytest.fixture(scope="module")
def canonical_design(tmp_path_factory):
    out = tmp_path_factory.mktemp("pubcomp") / "canonical.png"
    return run_demo(str(out)).design


def _brief(*, open_plan: bool):
    program = ProgramSpec(bedrooms=4, safe_room=True, open_plan_living=open_plan, wet_rooms=2,
                          parking_spaces=2, target_built_area_m2=200)
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program)
    assert result.design is not None, result.notes
    return result.design


@pytest.fixture(scope="module")
def open_plan_design():
    return _brief(open_plan=True)


@pytest.fixture(scope="module")
def closed_plan_design():
    return _brief(open_plan=False)


# --------------------------------------------------------------------------- AC-1


def test_composition_computed_on_the_canonical_fixture(canonical_design):
    composition = pc.measure(canonical_design)
    assert composition.blocked_public_rooms == ()
    assert not pc.hard_violations(composition)
    # The canonical fixture has all three of LIVING/DINING/KITCHEN — every relationship fact is a
    # real bool, never "not applicable".
    assert composition.kitchen_dining_related is not None
    assert composition.dining_living_related is not None


def test_open_plan_is_not_penalized(open_plan_design, closed_plan_design):
    open_composition = pc.measure(open_plan_design)
    closed_composition = pc.measure(closed_plan_design)

    # The open-plan fixture's own LDK rooms read as one connected open-plan group.
    assert open_composition.public_zone_coherent is True
    # Being open never fails C31, and never scores worse than the same brief closed — openness
    # itself carries no penalty term at all (see `measure`'s own scoring, which never reads
    # `public_zone_coherent`).
    assert open_composition.blocked_public_rooms == ()
    assert open_composition.composition_score <= closed_composition.composition_score + 1e-9
    # Open-plan rooms are, by construction, linked to each other — never scored as "not related".
    assert open_composition.kitchen_dining_related is not False
    assert open_composition.dining_living_related is not False


# --------------------------------------------------------------------------- AC-2


def _blocked_dining_design() -> GeometricDesign:
    """HALL -> DINING -> LIVING, the only path to LIVING. DINING is 2.5 x 3.0 m net — just enough
    to fit ONE placed dining table (2.4 x 2.0 m footprint+clearance,
    `interior_layout._DINING_TABLE`) centred, with only ~0.05 m either side: the table's own
    clearance rectangle spans nearly the full width, so the straight route from the west door
    (HALL) to the east opening (LIVING) is blocked, with no way around it."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 3.0, 3.0))
    dining = _room("DINING", ("DINING",), (3.0, 0.0, 2.5, 3.0))
    living = _room("LIVING", ("LIVING",), (5.5, 0.0, 6.0, 5.0), area=30.0)
    doors = [
        _door("HALL", "DINING", "vertical", (3.0, 1.5)),
        _door("DINING", "LIVING", "vertical", (5.5, 1.5)),
    ]
    entrance = DoorOut(a="OUTSIDE", b="HALL", kind="ENTRANCE_DOOR", width_m=1.0,
                       center_m=(1.5, 0.0), orientation="horizontal", placeable=True,
                       shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(-5.0, -5.0, 25.0, 20.0), footprint_m=(0.0, 0.0, 11.5, 5.0),
        rooms=(hall, dining, living), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=99.0, net_area_m2=99.0, wall_iterations=0,
    )


def _clear_dining_design() -> GeometricDesign:
    """The SAME topology, a DINING room wide enough (4.0 m) that the centred table leaves a real
    berth on both sides — the positive control: furniture existing in the pass-through room is not
    itself a defect, only a route with no way around it."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 3.0, 3.0))
    dining = _room("DINING", ("DINING",), (3.0, 0.0, 4.0, 3.0))
    living = _room("LIVING", ("LIVING",), (7.0, 0.0, 6.0, 5.0), area=30.0)
    doors = [
        _door("HALL", "DINING", "vertical", (3.0, 1.5)),
        _door("DINING", "LIVING", "vertical", (7.0, 1.5)),
    ]
    entrance = DoorOut(a="OUTSIDE", b="HALL", kind="ENTRANCE_DOOR", width_m=1.0,
                       center_m=(1.5, 0.0), orientation="horizontal", placeable=True,
                       shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(-5.0, -5.0, 25.0, 20.0), footprint_m=(0.0, 0.0, 13.0, 5.0),
        rooms=(hall, dining, living), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=99.0, net_area_m2=99.0, wall_iterations=0,
    )


def test_c31_fails_path_only_through_furniture():
    blocked = pc.measure(_blocked_dining_design())
    assert blocked.blocked_public_rooms == ("LIVING",)
    violations = pc.hard_violations(blocked)
    assert violations and "LIVING" in violations[0]


def test_c31_passes_when_a_berth_exists_around_the_furniture():
    clear = pc.measure(_clear_dining_design())
    assert clear.blocked_public_rooms == ()
    assert not pc.hard_violations(clear)


def test_c31_appears_in_the_check_list(canonical_design):
    del canonical_design
    import tempfile

    from app.vertical_slice.pipeline import run_demo as _run_demo
    result = _run_demo(tempfile.mktemp(suffix=".png"))
    assert "C31" in [c.check_id for c in result.validation.checks]


def test_c31_gate_actually_blocks_a_candidate(monkeypatch):
    """`validate()`'s own C31 wiring, not `measure`/`hard_violations` again: force `measure` to
    report a blocked room for one real, already-solved candidate and confirm `validate()` fails
    C31 and refuses the plan — the same "prove the gate itself, not just the pure function" pattern
    `test_circulation_metrics.py::test_c26_gate_actually_blocks_the_plan_...` uses."""
    from app.vertical_slice import concept as concept_stage
    from app.vertical_slice import doors as doors_stage
    from app.vertical_slice import furniture as furniture_stage
    from app.vertical_slice import public_composition as pc_module
    from app.vertical_slice import site as site_stage
    from app.vertical_slice import validation as validation_stage
    from app.vertical_slice import windows as windows_stage
    from app.vertical_slice.geometry_core.engine import solve_fixture
    from app.vertical_slice.spec import demo_spec
    from app.vertical_slice.wet_rooms import resolve_wet_rooms

    spec = demo_spec()
    concept = concept_stage.build_concept(spec)
    solve = solve_fixture(concept.fixture)
    entrance_local_x = (solve.rects[concept.entrance_zone_id].x
                        + solve.rects[concept.entrance_zone_id].w // 2)
    site = site_stage.build_site_plan(spec, concept.footprint_width_m, concept.footprint_depth_m,
                                      entrance_local_x)
    rects = site_stage.translate_rects(solve.rects, site.footprint_offset_u)
    interior_doors = doors_stage.generate_interior_doors(concept.fixture, rects)
    entrance_door = doors_stage.build_entrance_door(site.entrance, site.footprint)
    windows = windows_stage.generate_windows(concept.fixture, rects, site.footprint)
    furniture = furniture_stage.check_furniture_feasibility(concept.fixture, rects, solve.walls)

    before = validation_stage.validate(concept.fixture, rects, solve.walls, interior_doors,
                                       entrance_door, windows, furniture, site,
                                       wet_rooms=resolve_wet_rooms(spec.program))
    c31_before = next(c for c in before.checks if c.check_id == "C31")
    assert c31_before.passed

    forced = pc_module.PublicComposition(
        kitchen_dining_related=True, dining_living_related=True, public_zone_coherent=True,
        entrance_reaches_public=True, living_exterior_exposed=True, living_has_window=True,
        blocked_public_rooms=("LIVING",), composition_score=2.0,
    )
    monkeypatch.setattr(validation_stage.public_composition, "measure", lambda design: forced)
    after = validation_stage.validate(concept.fixture, rects, solve.walls, interior_doors,
                                      entrance_door, windows, furniture, site,
                                      wet_rooms=resolve_wet_rooms(spec.program))
    c31_after = next(c for c in after.checks if c.check_id == "C31")
    assert not c31_after.passed
    assert not after.ok


# --------------------------------------------------------------------------- AC-3


def test_ranking_prefers_the_better_composition():
    better = pc.PublicComposition(
        kitchen_dining_related=True, dining_living_related=True, public_zone_coherent=True,
        entrance_reaches_public=True, living_exterior_exposed=True, living_has_window=True,
        blocked_public_rooms=(), composition_score=0.0,
    )
    worse = pc.PublicComposition(
        kitchen_dining_related=False, dining_living_related=True, public_zone_coherent=None,
        entrance_reaches_public=True, living_exterior_exposed=True, living_has_window=True,
        blocked_public_rooms=(), composition_score=1.0,
    )
    assert pc.composition_prefers(worse, better) is None
    assert pc.composition_prefers(better, worse) is not None


def test_equal_composition_is_not_a_preference():
    a = pc.PublicComposition(True, True, True, True, True, True, (), 0.0)
    b = pc.PublicComposition(True, True, True, True, True, True, (), 0.0)
    assert pc.composition_prefers(a, b) is not None
