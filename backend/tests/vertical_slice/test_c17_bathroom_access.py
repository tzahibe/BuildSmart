"""C17 — realized bathroom access matches the AUTHORITATIVE requirements (specs/007 FR-9).

Three rooms in a row with the bathroom at the end and ONE declared door into it, from the master
or from the hall. For each geometry only the REQUIREMENT handed to validation changes, which is
the point: C17 compares the drawing to what the person was told, and never reads intent off the
drawing.
"""
from __future__ import annotations

from app.vertical_slice import site as site_stage
from app.vertical_slice.doors import build_entrance_door, generate_interior_doors
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Rect,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec, WetRoomKind, WetRoomStrength
from app.vertical_slice.validation import validate
from app.vertical_slice.wet_rooms import ResolvedWetRoom


def _fixture(bath_entered_from: str) -> Fixture:
    # Whichever room enters the bathroom sits beside it, so the declared door is physically real.
    first, second = ("HALL", "MASTER") if bath_entered_from == "MASTER" else ("MASTER", "HALL")
    tree = Split(Cut.V, Leaf(first), Split(Cut.V, Leaf(second), Leaf("BATH_1"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge(bath_entered_from, "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (
        ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 10, 20, 1.2, 8.0),
        ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 25, 2.5),
        ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0),
    )
    return Fixture("C17", (wing,), zones, access)


def _c17(fixture: Fixture, wet_rooms: tuple[ResolvedWetRoom, ...]):
    solve = solve_fixture(fixture)
    wing = fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    parking = site_stage.build_parking(spec)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance,
                    site_stage.classify_garden(spec, plot, footprint, parking))
    doors = generate_interior_doors(fixture, solve.rects)
    entrance_door = build_entrance_door(entrance, footprint, "HALL")
    report = validate(fixture, solve.rects, solve.walls, doors, entrance_door, [], [], site,
                      wet_rooms=wet_rooms)
    return next(c for c in report.checks if c.check_id == "C17")


def _req(kind: WetRoomKind, host: str | None) -> ResolvedWetRoom:
    return ResolvedWetRoom("BATH_1", kind, host, WetRoomStrength.REQUIRED, True)


def test_an_ensuite_entered_from_its_host_passes():
    check = _c17(_fixture("MASTER"), (_req(WetRoomKind.ENSUITE, "MASTER"),))
    assert check.passed, check.detail


def test_a_shared_bathroom_entered_from_the_hall_passes():
    check = _c17(_fixture("HALL"), (_req(WetRoomKind.SHARED_BATHROOM, None),))
    assert check.passed, check.detail


def test_a_bathroom_entered_from_a_bedroom_fails_a_shared_requirement():
    """The same geometry that passes as an ensuite is a FAILURE against a shared requirement:
    C17 does not conclude "so it must be an ensuite" — that would be reading intent off the plan."""
    check = _c17(_fixture("MASTER"), (_req(WetRoomKind.SHARED_BATHROOM, None),))
    assert not check.passed
    assert "BATH_1 (shared_bathroom): entered from MASTER, required only from circulation" in check.detail


def test_an_ensuite_entered_from_the_hall_fails():
    check = _c17(_fixture("HALL"), (_req(WetRoomKind.ENSUITE, "MASTER"),))
    assert not check.passed
    assert "required only from MASTER" in check.detail


def test_a_guest_wc_is_held_to_circulation_like_a_shared_bathroom():
    check = _c17(_fixture("MASTER"), (_req(WetRoomKind.GUEST_WC, None),))
    assert not check.passed and "guest_wc" in check.detail


def test_no_requirement_for_a_wet_zone_fails_closed():
    """Absence is never a pass: a plan with a bathroom and no requirement covering it is refused."""
    check = _c17(_fixture("HALL"), ())
    assert not check.passed
    assert "BATH_1: kind unknown" in check.detail


def test_a_requirement_for_a_zone_the_plan_lacks_fails_closed():
    missing = ResolvedWetRoom("BATH_2", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, True)
    check = _c17(_fixture("HALL"), (_req(WetRoomKind.SHARED_BATHROOM, None), missing))
    assert not check.passed
    assert "BATH_2: required but not in the plan" in check.detail
