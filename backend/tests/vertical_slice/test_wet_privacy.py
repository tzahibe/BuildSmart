"""Wet-room privacy and access quality — Issue #37.

`app.vertical_slice.wet_privacy.compute_wet_privacy` is exercised directly, off hand-built
`Fixture`s solved through the real geometry-core engine (`solve_fixture`) and the real door
generator (`generate_interior_doors`) — the same pattern `test_c17_bathroom_access.py` uses, so a
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
from app.vertical_slice.wet_privacy import (
    ZoneClass,
    better_candidate,
    candidate_privacy_key,
    compute_wet_privacy,
)
from app.vertical_slice.wet_rooms import ResolvedWetRoom

_WET_SPEC = ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0)
_TOILET_SPEC = ZoneSpec("BATH_1", (ProgramRole.TOILET,), 2, 3, 12, 0.9, 3.0)
_HALL_SPEC = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 10, 20, 1.2, 8.0)
_MASTER_SPEC = ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 25, 2.5)


def _row_fixture(entered_from: str, wet_spec: ZoneSpec) -> Fixture:
    """Two rooms beside `BATH_1`, mirroring `test_c17_bathroom_access.py`'s `_fixture`: whichever
    zone enters `BATH_1` sits beside it, so the declared door is physically real."""
    first, second = ("HALL", "MASTER") if entered_from == "MASTER" else ("MASTER", "HALL")
    tree = Split(Cut.V, Leaf(first), Split(Cut.V, Leaf(second), Leaf("BATH_1"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge(entered_from, "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (_HALL_SPEC, _MASTER_SPEC, wet_spec)
    return Fixture("ROW", (wing,), zones, access)


def _facing_fixture(east_zone_id: str, east_spec: ZoneSpec) -> Fixture:
    """`BATH_1` | `HALL` | `east_zone_id`, ALL leaves of one `Cut.V` chain — every leaf spans the
    wing's full height, so `BATH_1`'s door onto `HALL` and `east_zone_id`'s door onto `HALL` land
    at the SAME midpoint: a real, geometrically-forced facing pair, not an assumed one."""
    tree = Split(Cut.V, Leaf("BATH_1"), Split(Cut.V, Leaf("HALL"), Leaf(east_zone_id), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("BATH_1", "HALL", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", east_zone_id, ConnectionKind.DOOR),
    ))
    zones = (_TOILET_SPEC, _HALL_SPEC, east_spec)
    return Fixture("FACING", (wing,), zones, access)


def _rects_and_doors(fixture: Fixture):
    solve = solve_fixture(fixture)
    doors = generate_interior_doors(fixture, solve.rects)
    return solve.rects, solve.walls, doors


def _req(kind: WetRoomKind, host: str | None) -> ResolvedWetRoom:
    return ResolvedWetRoom("BATH_1", kind, host, WetRoomStrength.REQUIRED, True)


def _validate(fixture: Fixture, rects, walls, doors, wet_rooms):
    wing = fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    parking = site_stage.build_parking(spec)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance,
                    site_stage.classify_garden(spec, plot, footprint, parking))
    entrance_door = build_entrance_door(entrance, footprint, "HALL")
    return validate(fixture, rects, walls, doors, entrance_door, [], [], site, wet_rooms=wet_rooms)


# --------------------------------------------------------------------------- AC-1


def test_records_for_canonical_and_guest_wc_fixtures():
    # Ensuite, entered only from its host bedroom.
    fixture = _row_fixture("MASTER", _WET_SPEC)
    rects, walls, doors = _rects_and_doors(fixture)
    records = compute_wet_privacy(fixture, rects, walls, doors, (_req(WetRoomKind.ENSUITE, "MASTER"),))
    assert len(records) == 1
    record = records[0]
    assert record.zone_id == "BATH_1"
    assert record.entered_from == "MASTER"
    assert record.entered_from_class is ZoneClass.PRIVATE
    assert record.public_exposure_score == 0.0
    assert record.direct_sight_line is False

    # A shared bathroom, entered from circulation.
    fixture = _row_fixture("HALL", _WET_SPEC)
    rects, walls, doors = _rects_and_doors(fixture)
    records = compute_wet_privacy(fixture, rects, walls, doors, (_req(WetRoomKind.SHARED_BATHROOM, None),))
    assert len(records) == 1
    record = records[0]
    assert record.entered_from == "HALL"
    assert record.entered_from_class is ZoneClass.CIRCULATION

    # A guest WC, entered from circulation — its own fixture, its own kind.
    fixture = _row_fixture("HALL", _TOILET_SPEC)
    rects, walls, doors = _rects_and_doors(fixture)
    records = compute_wet_privacy(fixture, rects, walls, doors, (_req(WetRoomKind.GUEST_WC, None),))
    assert len(records) == 1
    record = records[0]
    assert record.entered_from == "HALL"
    assert record.entered_from_class is ZoneClass.CIRCULATION
    assert 0.0 <= record.public_exposure_score <= 1.0
    assert isinstance(record.adjacency_quality, bool)
    assert isinstance(record.circulation_obstruction, bool)


# --------------------------------------------------------------------------- AC-2


def test_c29_fails_dining_facing_wc_and_passes_corridor_access():
    dining_spec = ZoneSpec("DINING", (ProgramRole.DINING,), 8, 10, 16, 2.0)
    tree = Split(Cut.V, Leaf("BATH_1"), Split(Cut.V, Leaf("DINING"), Leaf("MASTER"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("DINING", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("DINING", "BATH_1", ConnectionKind.DOOR),
    ))
    fixture = Fixture("DINING_WC", (wing,), (dining_spec, _MASTER_SPEC, _TOILET_SPEC), access)
    rects, walls, doors = _rects_and_doors(fixture)
    report = _validate(fixture, rects, walls, doors, (_req(WetRoomKind.GUEST_WC, None),))
    c29 = next(c for c in report.checks if c.check_id == "C29")
    assert not c29.passed
    assert "BATH_1" in c29.detail and "DINING" in c29.detail

    # The canonical corridor-access bathroom (the same geometry C17's own tests hold up as
    # correct) clears C29 — corridor access is never refused here.
    fixture = _row_fixture("HALL", _WET_SPEC)
    rects, walls, doors = _rects_and_doors(fixture)
    report = _validate(fixture, rects, walls, doors, (_req(WetRoomKind.SHARED_BATHROOM, None),))
    c29 = next(c for c in report.checks if c.check_id == "C29")
    assert c29.passed, c29.detail

    # The ensuite canonical fixture clears C29 too.
    fixture = _row_fixture("MASTER", _WET_SPEC)
    rects, walls, doors = _rects_and_doors(fixture)
    report = _validate(fixture, rects, walls, doors, (_req(WetRoomKind.ENSUITE, "MASTER"),))
    c29 = next(c for c in report.checks if c.check_id == "C29")
    assert c29.passed, c29.detail


def test_living_entered_wc_scores_public_soft_exposure():
    """Pin: C24 (Issue #69) now allows LIVING as a wet room's entered-from role, but this module's
    own scoring is unchanged — LIVING reads PUBLIC and scores the soft band, never the C29 hard-fail
    band reserved for KITCHEN/DINING (specs/009-guest-wc-placement decision C)."""
    living_spec = ZoneSpec("LIVING", (ProgramRole.LIVING,), 16, 20, 26, 3.0)
    tree = Split(Cut.V, Leaf("LIVING"), Leaf("BATH_1"), None)
    wing = Wing("W", 0, 0, m_to_u(10.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((DesiredAccessEdge("LIVING", "BATH_1", ConnectionKind.DOOR),))
    fixture = Fixture("LIVING_WC", (wing,), (living_spec, _TOILET_SPEC), access)
    rects, walls, doors = _rects_and_doors(fixture)
    records = compute_wet_privacy(fixture, rects, walls, doors, (_req(WetRoomKind.GUEST_WC, None),))
    assert len(records) == 1
    record = records[0]
    assert record.entered_from == "LIVING"
    assert record.entered_from_class is ZoneClass.PUBLIC
    assert record.public_exposure_score == 0.7

    report = _validate(fixture, rects, walls, doors, (_req(WetRoomKind.GUEST_WC, None),))
    c29 = next(c for c in report.checks if c.check_id == "C29")
    assert c29.passed, c29.detail


# --------------------------------------------------------------------------- AC-3


def test_ranking_prefers_better_privacy():
    """Two siblings of the SAME programme (a WC off a hall), differing only in what the hall's
    OTHER door faces: one candidate's hall opens onto a bedroom, the other's onto the living room.
    The geometry forces the two doors to line up exactly (`_facing_fixture`), so the only thing
    that differs between the two candidates is the privacy of that facing room."""
    bedroom_spec = ZoneSpec("BEDROOM_1", (ProgramRole.BEDROOM,), 8, 10, 14, 2.5)
    living_spec = ZoneSpec("LIVING", (ProgramRole.LIVING,), 12, 16, 24, 2.8)

    private_fixture = _facing_fixture("BEDROOM_1", bedroom_spec)
    rects, walls, doors = _rects_and_doors(private_fixture)
    private_records = compute_wet_privacy(private_fixture, rects, walls, doors,
                                          (_req(WetRoomKind.GUEST_WC, None),))

    public_fixture = _facing_fixture("LIVING", living_spec)
    rects, walls, doors = _rects_and_doors(public_fixture)
    public_records = compute_wet_privacy(public_fixture, rects, walls, doors,
                                         (_req(WetRoomKind.GUEST_WC, None),))

    assert public_records[0].direct_sight_line is True
    assert public_records[0].door_facing == "LIVING"
    assert private_records[0].direct_sight_line is False

    assert candidate_privacy_key(private_records) < candidate_privacy_key(public_records)
    assert better_candidate(private_records, public_records) is private_records
