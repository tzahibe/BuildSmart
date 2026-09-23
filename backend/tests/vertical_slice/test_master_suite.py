"""Master-suite access and privacy — Issue #42.

`app.vertical_slice.master_suite.compute_master_suites` is exercised directly, off hand-built
`Fixture`s solved through the real geometry-core engine (`solve_fixture`) and the real door
generator (`generate_interior_doors`) — the same pattern `test_wet_privacy.py` uses, so a record is
only ever read off REALIZED geometry, never off the requirement that produced it.
"""
from __future__ import annotations

from app.vertical_slice.doors import generate_interior_doors
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
from app.vertical_slice.master_suite import (
    EnsuiteAccess,
    WardrobeRelationship,
    better_candidate,
    candidate_suite_key,
    compute_master_suites,
)
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.wet_rooms import ResolvedWetRoom

_HALL_SPEC = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 10, 20, 1.2, 8.0)
_MASTER_SPEC = ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 25, 2.5)
_BATH_SPEC = ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0)
_DRESSING_SPEC = ZoneSpec("DRESSING", (ProgramRole.DRESSING_ROOM,), 3, 4, 6, 1.4, 5.0)
_FILL_SPEC = ZoneSpec("FILL", (ProgramRole.STORAGE,), 6, 10, 16, 1.5, 6.0)


def _ensuite(host: str = "MASTER") -> ResolvedWetRoom:
    return ResolvedWetRoom("BATH_1", WetRoomKind.ENSUITE, host, WetRoomStrength.REQUIRED, True)


def _rects_walls_doors(fixture: Fixture):
    solve = solve_fixture(fixture)
    doors = generate_interior_doors(fixture, solve.rects)
    return solve.rects, solve.walls, doors


# --------------------------------------------------------------------------- AC-1


def _row_fixture() -> Fixture:
    """Canonical master suite: HALL | MASTER | BATH_1, a simple three-way row (mirrors
    `test_wet_privacy._row_fixture`) — the ensuite entered only from the bedroom, no dressing
    room."""
    tree = Split(Cut.V, Leaf("HALL"), Split(Cut.V, Leaf("MASTER"), Leaf("BATH_1"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
    ))
    return Fixture("ROW", (wing,), (_HALL_SPEC, _MASTER_SPEC, _BATH_SPEC), access)


def _dressing_fixture() -> Fixture:
    """The same canonical suite, plus a `DRESSING_ROOM` linked directly from `MASTER`: HALL west of
    MASTER, and an east column split into BATH_1 (north) over DRESSING (south) so BOTH are
    physically adjacent to MASTER's own east wall (a simple linear chain would only touch the
    first of the two)."""
    east_col = Split(Cut.H, Leaf("BATH_1"), Leaf("DRESSING"), None)
    row = Split(Cut.V, Leaf("MASTER"), east_col, None)
    tree = Split(Cut.H, Leaf("HALL"), row, None)
    wing = Wing("W", 0, 0, m_to_u(7.5), m_to_u(9.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "DRESSING", ConnectionKind.DOOR),
    ))
    zones = (_HALL_SPEC, _MASTER_SPEC, _BATH_SPEC, _DRESSING_SPEC)
    return Fixture("DRESSING", (wing,), zones, access)


def test_records_for_canonical_and_dressing_room_fixtures():
    fixture = _row_fixture()
    rects, walls, doors = _rects_walls_doors(fixture)
    records = compute_master_suites(fixture, rects, walls, doors, (_ensuite(),))
    assert len(records) == 1
    record = records[0]
    assert record.bedroom_zone_id == "MASTER"
    assert record.ensuite_zone_id == "BATH_1"
    assert record.ensuite_access is EnsuiteAccess.DIRECT
    assert record.wardrobe_zone_id is None
    assert record.wardrobe_relationship is WardrobeRelationship.IN_ROOM
    assert isinstance(record.hall_sight_line_to_bed, bool)
    assert isinstance(record.ensuite_route_crosses_bed, bool)
    assert record.wardrobe_route_crosses_bed is False
    assert record.suite_score >= 0.0

    fixture = _dressing_fixture()
    rects, walls, doors = _rects_walls_doors(fixture)
    records = compute_master_suites(fixture, rects, walls, doors, (_ensuite(),))
    assert len(records) == 1
    record = records[0]
    assert record.bedroom_zone_id == "MASTER"
    assert record.wardrobe_zone_id == "DRESSING"
    assert record.wardrobe_relationship is WardrobeRelationship.DRESSING_ROOM


def test_no_ensuite_reports_none_access():
    """A `MASTER_BEDROOM` with no ensuite hosted at all — `wet_rooms` carries nothing for it."""
    tree = Split(Cut.V, Leaf("HALL"), Leaf("MASTER"), None)
    wing = Wing("W", 0, 0, m_to_u(8.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),))
    fixture = Fixture("NO_ENSUITE", (wing,), (_HALL_SPEC, _MASTER_SPEC), access)
    rects, walls, doors = _rects_walls_doors(fixture)
    records = compute_master_suites(fixture, rects, walls, doors, ())
    assert len(records) == 1
    record = records[0]
    assert record.ensuite_zone_id is None
    assert record.ensuite_access is EnsuiteAccess.NONE
    assert record.ensuite_route_crosses_bed is False


# --------------------------------------------------------------------------- AC-2


def _shotgun_fixture() -> Fixture:
    """The WORSE sibling: HALL / MASTER / BATH_1 stacked vertically, each spanning the full wing
    width — the entry door (HALL-MASTER) and the ensuite door (MASTER-BATH_1) land on OPPOSITE
    walls at the SAME x, forced there by the geometry (both shared edges span the full width), so
    the straight route between them runs directly across the room — straight into the bed zone,
    which is anchored on the far side from the entry door."""
    tree = Split(Cut.H, Leaf("HALL"), Split(Cut.H, Leaf("MASTER"), Leaf("BATH_1"), None), None)
    wing = Wing("W", 0, 0, m_to_u(4.0), m_to_u(11.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
    ))
    return Fixture("SHOTGUN", (wing,), (_HALL_SPEC, _MASTER_SPEC, _BATH_SPEC), access)


def _clustered_fixture() -> Fixture:
    """The BETTER sibling: HALL north of a row split into MASTER (west) and an east column split
    into BATH_1 (north, a small slice) over FILL (south, the rest). The ensuite door
    (MASTER-BATH_1) only shares BATH_1's own (small, north) y-range with MASTER's east wall, so it
    lands close to the entry door (also on MASTER's north wall) — both doors cluster near the
    entry, well clear of the bed zone anchored on the far (south) side of the room."""
    east_col = Split(Cut.H, Leaf("BATH_1"), Leaf("FILL"), None)
    row = Split(Cut.V, Leaf("MASTER"), east_col, None)
    tree = Split(Cut.H, Leaf("HALL"), row, None)
    wing = Wing("W", 0, 0, m_to_u(8.75), m_to_u(9.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (_HALL_SPEC, _MASTER_SPEC, _BATH_SPEC, _FILL_SPEC)
    return Fixture("CLUSTERED", (wing,), zones, access)


def test_ranking_prefers_the_better_route():
    worse_fixture = _shotgun_fixture()
    rects, walls, doors = _rects_walls_doors(worse_fixture)
    worse_records = compute_master_suites(worse_fixture, rects, walls, doors, (_ensuite(),))
    assert len(worse_records) == 1
    assert worse_records[0].ensuite_route_crosses_bed is True

    better_fixture = _clustered_fixture()
    rects, walls, doors = _rects_walls_doors(better_fixture)
    better_records = compute_master_suites(better_fixture, rects, walls, doors, (_ensuite(),))
    assert len(better_records) == 1
    assert better_records[0].ensuite_route_crosses_bed is False

    assert candidate_suite_key(better_records) < candidate_suite_key(worse_records)
    assert better_candidate(better_records, worse_records) is better_records
