"""Wet-core / plumbing efficiency — Issue #44.

`app.vertical_slice.wet_core` is exercised directly, off hand-built `Fixture`s solved through the
real geometry-core engine (`solve_fixture`) — the same pattern `test_wet_privacy.py` uses, so a
record is only ever read off REALIZED geometry, never off the requirement that produced it.
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
from app.vertical_slice.wet_core import (
    better_candidate,
    candidate_wet_core_key,
    compute_wet_core,
    wet_core_alignment,
)
from app.vertical_slice.wet_rooms import ResolvedWetRoom

_HALL_SPEC = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 10, 20, 1.2, 8.0)
_MASTER_SPEC = ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 25, 2.5)
_WET_SPEC_1 = ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0)
_WET_SPEC_2 = ZoneSpec("BATH_2", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0)
_KITCHEN_SPEC = ZoneSpec("KITCHEN", (ProgramRole.KITCHEN,), 10, 13, 20, 2.4, 3.0)


def _solve(fixture: Fixture):
    solve = solve_fixture(fixture)
    return solve.rects, solve.walls


def _req(zone_id: str, kind: WetRoomKind) -> ResolvedWetRoom:
    return ResolvedWetRoom(zone_id, kind, None, WetRoomStrength.REQUIRED, True)


def _validate(fixture: Fixture, rects, walls, wet_rooms):
    solve_rects, solve_walls = rects, walls
    doors = generate_interior_doors(fixture, solve_rects)
    wing = fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    parking = site_stage.build_parking(spec)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance,
                    site_stage.classify_garden(spec, plot, footprint, parking))
    entrance_door = build_entrance_door(entrance, footprint, "HALL")
    return validate(fixture, solve_rects, solve_walls, doors, entrance_door, [], [], site,
                    wet_rooms=wet_rooms)


def _kitchen_adjacent_row() -> Fixture:
    """KITCHEN | BATH_1 | BATH_2 | HALL, one `Cut.V` chain — every leaf spans the wing's full
    height, so each neighbour pair shares a full wall: the kitchen touches BATH_1, and the two
    bathrooms touch each other."""
    tree = Split(Cut.V, Leaf("KITCHEN"),
                Split(Cut.V, Leaf("BATH_1"), Split(Cut.V, Leaf("BATH_2"), Leaf("HALL"), None), None),
                None)
    wing = Wing("W", 0, 0, m_to_u(9.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "BATH_2", ConnectionKind.DOOR),
        DesiredAccessEdge("BATH_2", "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (_KITCHEN_SPEC, _WET_SPEC_1, _WET_SPEC_2, _HALL_SPEC)
    return Fixture("KITCHEN_ROW", (wing,), zones, access)


def _clustered_bathrooms_fixture() -> Fixture:
    """HALL beside a column split into BATH_1 (top) / BATH_2 (bottom): HALL is adjacent to BOTH
    (a real door to each), and the two bathrooms are also adjacent to EACH OTHER — the clustered
    candidate."""
    tree = Split(Cut.V, Leaf("HALL"), Split(Cut.H, Leaf("BATH_1"), Leaf("BATH_2"), None), None)
    wing = Wing("W", 0, 0, m_to_u(6.0), m_to_u(6.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "BATH_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH_2", ConnectionKind.DOOR),
    ))
    zones = (_HALL_SPEC, _WET_SPEC_1, _WET_SPEC_2)
    return Fixture("CLUSTERED", (wing,), zones, access)


def _spread_bathrooms_fixture() -> Fixture:
    """BATH_1 | HALL | BATH_2 — both bathrooms entered from the SAME hall (identical requirement
    to the clustered candidate) but never adjacent to each other: the spread-out sibling."""
    tree = Split(Cut.V, Leaf("BATH_1"), Split(Cut.V, Leaf("HALL"), Leaf("BATH_2"), None), None)
    wing = Wing("W", 0, 0, m_to_u(8.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("BATH_1", "HALL", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH_2", ConnectionKind.DOOR),
    ))
    zones = (_WET_SPEC_1, _HALL_SPEC, _WET_SPEC_2)
    return Fixture("SPREAD", (wing,), zones, access)


def _row_fixture(entered_from: str) -> Fixture:
    """A single wet room beside `HALL`/`MASTER` — the level building-block for the two-level test,
    mirroring `test_wet_privacy._row_fixture`."""
    first, second = ("HALL", "MASTER") if entered_from == "MASTER" else ("MASTER", "HALL")
    tree = Split(Cut.V, Leaf(first), Split(Cut.V, Leaf(second), Leaf("BATH_1"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge(entered_from, "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (_HALL_SPEC, _MASTER_SPEC, ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0))
    return Fixture("ROW", (wing,), zones, access)


def _mirrored_row_fixture() -> Fixture:
    """The same three rooms as `_row_fixture`, but MASTER and BATH_1 swap ends — BATH_1 lands at a
    different x-range, so its footprint does not overlap `_row_fixture`'s BATH_1 at all."""
    tree = Split(Cut.V, Leaf("BATH_1"), Split(Cut.V, Leaf("MASTER"), Leaf("HALL"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("MASTER", "HALL", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (_HALL_SPEC, _MASTER_SPEC, ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0))
    return Fixture("ROW_MIRRORED", (wing,), zones, access)


# --------------------------------------------------------------------------- AC-1


def test_records_for_canonical_and_two_level_fixtures():
    # A shared-wall, kitchen-adjacent cluster: BATH_1/BATH_2 touch each other AND the kitchen.
    fixture = _kitchen_adjacent_row()
    rects, walls = _solve(fixture)
    core = compute_wet_core(fixture, rects, walls)
    assert core.shared_wall_length_m > 0.0
    assert core.cluster_count == 1
    assert core.clusters == (("BATH_1", "BATH_2"),)
    assert core.kitchen_adjacent_count == 1
    assert core.plumbing_complexity_index == 1

    # A single isolated wet room, no kitchen at all: its own one-element cluster, one stack.
    fixture = _row_fixture("MASTER")
    rects, walls = _solve(fixture)
    core = compute_wet_core(fixture, rects, walls)
    assert core.shared_wall_length_m == 0.0
    assert core.clusters == (("BATH_1",),)
    assert core.kitchen_adjacent_count == 0
    assert core.plumbing_complexity_index == 1

    # A plan with no wet room at all is a real, valid input — nothing to divide by zero on.
    hall_only = Fixture("EMPTY", fixture.wings, (_HALL_SPEC, _MASTER_SPEC),
                        DesiredAccessTopology((DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),)))
    rects2, walls2 = _solve(_row_fixture("MASTER"))
    empty_core = compute_wet_core(hall_only, rects2, walls2)
    assert empty_core.clusters == ()
    assert empty_core.plumbing_complexity_index == 0

    # A two-level fixture: the SAME row layout on both levels stacks its wet room exactly —
    # `wet_core_alignment` reports it aligned.
    lower_rects, lower_walls = _solve(_row_fixture("MASTER"))
    upper_rects, upper_walls = _solve(_row_fixture("MASTER"))
    alignment = wet_core_alignment(_row_fixture("MASTER"), lower_rects,
                                   _row_fixture("MASTER"), upper_rects)
    assert alignment.upper_wet_count == 1
    assert alignment.aligned_count == 1
    assert alignment.alignment_ratio == 1.0

    # A mirrored upper level puts BATH_1 at a different footprint — not aligned.
    mirrored_rects, mirrored_walls = _solve(_mirrored_row_fixture())
    misaligned = wet_core_alignment(_row_fixture("MASTER"), lower_rects,
                                    _mirrored_row_fixture(), mirrored_rects)
    assert misaligned.upper_wet_count == 1
    assert misaligned.aligned_count == 0
    assert misaligned.alignment_ratio == 0.0


# --------------------------------------------------------------------------- AC-2


def test_ranking_prefers_clustered_and_never_refuses():
    clustered = _clustered_bathrooms_fixture()
    c_rects, c_walls = _solve(clustered)
    clustered_core = compute_wet_core(clustered, c_rects, c_walls)

    spread = _spread_bathrooms_fixture()
    s_rects, s_walls = _solve(spread)
    spread_core = compute_wet_core(spread, s_rects, s_walls)

    assert clustered_core.plumbing_complexity_index < spread_core.plumbing_complexity_index
    assert clustered_core.shared_wall_length_m > spread_core.shared_wall_length_m == 0.0
    assert candidate_wet_core_key(clustered_core) < candidate_wet_core_key(spread_core)
    assert better_candidate(clustered_core, spread_core) is clustered_core
    assert better_candidate(spread_core, clustered_core) is clustered_core

    # Neither candidate is refused for a WET-CORE reason — both are the SAME programme (two
    # SHARED_BATHROOMs off one hall), entered only from circulation, which is all C17/C29 (the
    # only checks that judge wet-room access) require; wet-core adds no check of its own, so no
    # `check_id` for it can even appear in the report. (Entrance/parking placement is a separate,
    # unrelated site concern this hand-built micro-fixture was never built to satisfy — C17/C29
    # are the checks this Issue could possibly interact with.)
    wet_rooms = (_req("BATH_1", WetRoomKind.SHARED_BATHROOM), _req("BATH_2", WetRoomKind.SHARED_BATHROOM))
    for fixture_, rects_, walls_ in ((clustered, c_rects, c_walls), (spread, s_rects, s_walls)):
        report = _validate(fixture_, rects_, walls_, wet_rooms)
        checks = {c.check_id: c for c in report.checks}
        assert "WET_CORE" not in checks
        assert checks["C17"].passed, checks["C17"].detail
        assert checks["C29"].passed, checks["C29"].detail
