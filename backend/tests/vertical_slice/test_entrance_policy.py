"""Issue #20 — entrance policy: the front door opens into a hall, foyer or living room, never a
kitchen, dining, private or wet room.

Three witnesses, each a small hand-built fixture so the behaviour is deterministic and does not
depend on which candidate the generator happens to produce for a given brief:

  * `ENTRANCE_ZONE_PRIORITY` is exactly HALL/CIRCULATION/LIVING, and `resolve_entrance` refuses
    (returns `None`) when only a disallowed role fronts the street (AC-1).
  * C23 fails closed on a realized plan whose entrance door names a disallowed room, independent
    of how that name was chosen (AC-2).
  * candidate selection's entrance rank orders a HALL/CIRCULATION entrance ahead of a LIVING one
    (AC-3) — `general_pipeline._entrance_rank`, the function `run_general`'s main loop uses.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.vertical_slice import doors as doors_stage
from app.vertical_slice import footprint as footprint_module
from app.vertical_slice import furniture as furniture_stage
from app.vertical_slice import general_pipeline
from app.vertical_slice import validation as validation_stage
from app.vertical_slice import windows as windows_stage
from app.vertical_slice.general_pipeline import _site_plan_for
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec


def _z(zid: str, role: ProgramRole) -> ZoneSpec:
    roles = (role, ProgramRole.CIRCULATION) if role is ProgramRole.HALL else (role,)
    return ZoneSpec(zid, roles, 5.0, 20.0, 35.0, 2.0, 4.0)


def test_priority_and_none_when_only_kitchen_or_dining_front_the_street():
    assert doors_stage.ENTRANCE_ZONE_PRIORITY == (
        ProgramRole.HALL, ProgramRole.CIRCULATION, ProgramRole.LIVING)
    assert ProgramRole.DINING not in doors_stage.ENTRANCE_ZONE_PRIORITY
    assert ProgramRole.KITCHEN not in doors_stage.ENTRANCE_ZONE_PRIORITY

    # One row, the wing's full depth: KITCHEN and DINING side by side, BOTH on the street wall
    # (rect.y == footprint.y) and nothing else in the fixture at all.
    zones = (_z("KITCHEN", ProgramRole.KITCHEN), _z("DINING", ProgramRole.DINING))
    tree = Split(Cut.V, Leaf("KITCHEN"), Leaf("DINING"))
    wing = Wing("A", 0, 0, m_to_u(8.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology(
        (DesiredAccessEdge("KITCHEN", "DINING", ConnectionKind.CASED_OPENING),))
    fixture = Fixture("ONLY_KITCHEN_DINING", (wing,), zones, access)

    solve = solve_fixture(fixture)
    footprint = footprint_module.bounding_box((wing.rect(),))
    resolved = doors_stage.resolve_entrance(fixture, solve.rects, footprint)
    assert resolved is None

    # The refusal message helper names what WAS there, even though it was disallowed.
    fronting = doors_stage.street_fronting_roles(fixture, solve.rects, footprint)
    assert set(fronting) == {"KITCHEN", "DINING"}


def _hall_bedroom_fixture() -> Fixture:
    zones = (_z("HALL", ProgramRole.HALL), _z("BEDROOM", ProgramRole.BEDROOM))
    tree = Split(Cut.H, Leaf("HALL"), Leaf("BEDROOM"), fixed_at_u=m_to_u(3.0))
    wing = Wing("A", 0, 0, m_to_u(6.0), m_to_u(8.0), tree)
    access = DesiredAccessTopology((DesiredAccessEdge("HALL", "BEDROOM", ConnectionKind.DOOR),))
    return Fixture("HALL_BEDROOM", (wing,), zones, access)


def test_c23_fails_closed_on_disallowed_entrance_room():
    fixture = _hall_bedroom_fixture()
    solve = solve_fixture(fixture)
    footprint = footprint_module.bounding_box((fixture.wings[0].rect(),))
    spec = ArchitecturalSpec(plot=PlotSpec(width_m=16.0, depth_m=16.0),
                             program=ProgramSpec(bedrooms=1, safe_room=False, wet_rooms=0,
                                                 parking_spaces=0))
    site = _site_plan_for(spec, footprint)
    interior = doors_stage.generate_interior_doors(fixture, solve.rects)
    # A caller that hardcodes (or otherwise mis-resolves) the entrance zone to a disallowed room —
    # here BEDROOM — regardless of what actually fronts the street. C23 is the check that this
    # cannot silently pass validation, independent of C16's own geometric wall check.
    entrance = doors_stage.build_entrance_door(site.entrance, footprint, "BEDROOM")
    windows = windows_stage.generate_windows(fixture, solve.rects, footprint)
    furniture = furniture_stage.check_furniture_feasibility(fixture, solve.rects, solve.walls)
    report = validation_stage.validate(fixture, solve.rects, solve.walls, interior, entrance,
                                       windows, furniture, site)
    c23 = next(c for c in report.checks if c.check_id == "C23")
    assert not c23.passed
    assert "BEDROOM" in c23.detail


def test_c23_passes_on_the_frozen_baseline(tmp_path):
    """Every plan on the frozen corpus that still plans passes C23 (AC-2's regression half): the
    canonical single-level baseline is the cheapest witness available in a unit test."""
    result = run_demo(str(tmp_path / "house.png"))
    c23 = next(c for c in result.validation.checks if c.check_id == "C23")
    assert c23.passed, c23.detail


def _rank_fixture(front_role: ProgramRole) -> tuple[Fixture, str]:
    back_role = ProgramRole.LIVING if front_role is ProgramRole.HALL else ProgramRole.HALL
    front_id, back_id = f"FRONT_{front_role.value}", f"BACK_{back_role.value}"
    zones = (_z(front_id, front_role), _z(back_id, back_role))
    tree = Split(Cut.H, Leaf(front_id), Leaf(back_id), fixed_at_u=m_to_u(3.0))
    wing = Wing("A", 0, 0, m_to_u(6.0), m_to_u(8.0), tree)
    access = DesiredAccessTopology((DesiredAccessEdge(front_id, back_id, ConnectionKind.DOOR),))
    return Fixture(f"RANK_{front_role.value}", (wing,), zones, access), front_id


def _stub_plan(front_role: ProgramRole):
    """A minimal object with the two attributes `_entrance_rank` reads (`.design.entrance_door.b`
    and `.design.rooms`), built off a REAL `resolve_entrance` call on a REAL small fixture — no
    need for the full doors/windows/furniture/assemble pipeline just to rank an entrance."""
    fixture, front_id = _rank_fixture(front_role)
    solve = solve_fixture(fixture)
    footprint = footprint_module.bounding_box((fixture.wings[0].rect(),))
    resolved = doors_stage.resolve_entrance(fixture, solve.rects, footprint)
    assert resolved is not None and resolved[0] == front_id
    zone_id, low, high = resolved
    door = doors_stage.Door("OUTSIDE", zone_id, ConnectionKind.DOOR,
                            doors_stage.ENTRANCE_DOOR_WIDTH_M, ((low + high) // 2, footprint.y),
                            "horizontal", True, 1.0)
    rooms = [SimpleNamespace(zone_id=z.zone_id, roles=tuple(r.value for r in z.roles))
             for z in fixture.zones]
    return SimpleNamespace(design=SimpleNamespace(entrance_door=door, rooms=rooms))


def test_hall_entrance_outranks_living_entrance():
    hall_plan = _stub_plan(ProgramRole.HALL)
    living_plan = _stub_plan(ProgramRole.LIVING)
    assert general_pipeline._entrance_rank(hall_plan) == 0
    assert general_pipeline._entrance_rank(living_plan) == 1
    assert general_pipeline._entrance_rank(hall_plan) < general_pipeline._entrance_rank(living_plan)
