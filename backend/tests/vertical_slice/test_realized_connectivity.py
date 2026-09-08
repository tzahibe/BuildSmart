"""The realized-connectivity invariant.

    A declared access edge is NEVER treated as realized because the graph contains it.
    The realized plan — walls, openings and generated doors — is the source of truth for
    physical accessibility.

These tests construct the two failure modes directly against the engine rather than relying on
a scenario that happens to exhibit them, so they pin the invariant itself.
"""
from __future__ import annotations

import pytest

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
    Side,
    Split,
    WallType,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.site import EntranceWalk, SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import realized_connections, validate
from app.vertical_slice import site as site_stage


def _zone(zone_id: str) -> ZoneSpec:
    return ZoneSpec(zone_id, (ProgramRole.BEDROOM,), 8, 12, 25, 2.0)


def _validate(fixture: Fixture, entrance_zone: str):
    """Solve a fixture and run the full validation over it."""
    solve = solve_fixture(fixture)
    wing = fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y),
                    site_stage.build_parking(spec), entrance,
                    site_stage.classify_garden(spec, plot, footprint, site_stage.build_parking(spec)))
    doors = generate_interior_doors(fixture, solve.rects)
    entrance_door = build_entrance_door(entrance, footprint, entrance_zone)
    report = validate(fixture, solve.rects, solve.walls, doors, entrance_door, [], [], site)
    return solve, doors, report


# ------------------------------------------------------------------ the A-B-C door case

def _abc_fixture() -> Fixture:
    """A | B | C in a row. A is adjacent to B, B to C, and A is NOT adjacent to C —
    yet a DOOR is declared between A and C."""
    tree = Split(Cut.V, Leaf("A"), Split(Cut.V, Leaf("B"), Leaf("C"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("A", "B", ConnectionKind.DOOR),
        DesiredAccessEdge("A", "C", ConnectionKind.DOOR),  # no physical interface exists
    ))
    return Fixture("ABC", (wing,), (_zone("A"), _zone("B"), _zone("C")), access)


def test_declared_door_between_non_adjacent_zones_fails_validation():
    fixture = _abc_fixture()
    solve, doors, report = _validate(fixture, "A")

    assert solve.rects["A"].shared_edge_len_u(solve.rects["C"]) == 0
    assert not any({d.a, d.b} == {"A", "C"} for d in doors), "no door can exist there"

    c13 = next(c for c in report.checks if c.check_id == "C13")
    assert not c13.passed
    assert "A-C" in c13.detail
    assert "share no physical interface" in c13.detail


def test_c5_no_longer_reports_a_sealed_room_as_reachable():
    """The exact hole this invariant closes: C5 used to walk the declared graph, so C was
    'reachable' through a door that was never built."""
    _, _, report = _validate(_abc_fixture(), "A")
    c5 = next(c for c in report.checks if c.check_id == "C5")
    assert not c5.passed
    assert "C" in c5.detail


def test_the_same_plan_passes_once_the_declared_edge_matches_the_geometry():
    """Control: declare B-C instead of A-C — the rooms do touch, the door is built, and both
    checks pass. The invariant rejects false claims, not valid plans."""
    tree = Split(Cut.V, Leaf("A"), Split(Cut.V, Leaf("B"), Leaf("C"), None), None)
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("A", "B", ConnectionKind.DOOR),
        DesiredAccessEdge("B", "C", ConnectionKind.DOOR),
    ))
    fixture = Fixture("ABC_OK", (wing,), (_zone("A"), _zone("B"), _zone("C")), access)
    _, _, report = _validate(fixture, "A")
    assert next(c for c in report.checks if c.check_id == "C13").passed
    assert next(c for c in report.checks if c.check_id == "C5").passed


# ------------------------------------------------------------------ the blocked OPEN case

def _blocked_open_fixture() -> Fixture:
    """V( H(A,B), C ): A and C touch but are non-siblings, so declaring them one open group
    leaves a real PARTITION wall between them."""
    tree = Split(Cut.V, Split(Cut.H, Leaf("A"), Leaf("B"), None), Leaf("C"), None)
    wing = Wing("W", 0, 0, m_to_u(9.0), m_to_u(6.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("A", "B", ConnectionKind.DOOR),
        DesiredAccessEdge("A", "C", ConnectionKind.OPEN_CONNECTION),
    ))
    return Fixture("BLOCKED", (wing,), (_zone("A"), _zone("B"), _zone("C")), access,
                   open_groups=(("A", "C"),))


def test_declared_open_connection_blocked_by_a_partition_fails_validation():
    fixture = _blocked_open_fixture()
    solve, _, report = _validate(fixture, "A")

    assert solve.rects["A"].shared_edge_len_u(solve.rects["C"]) > 0, "they do touch"
    assert solve.walls[("A", Side.E)] is WallType.PARTITION, "but the wall is still there"

    c13 = next(c for c in report.checks if c.check_id == "C13")
    assert not c13.passed
    assert "A-C (OPEN_CONNECTION)" in c13.detail
    assert "physically walled" in c13.detail


def test_a_genuine_open_group_is_accepted():
    """Control: {A, B} IS a whole subtree, so the engine marks it OPEN and the invariant is
    satisfied without any door."""
    tree = Split(Cut.V, Split(Cut.H, Leaf("A"), Leaf("B"), None), Leaf("C"), None)
    wing = Wing("W", 0, 0, m_to_u(9.0), m_to_u(6.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("A", "B", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("B", "C", ConnectionKind.DOOR),
    ))
    fixture = Fixture("OPEN_OK", (wing,), (_zone("A"), _zone("B"), _zone("C")), access,
                      open_groups=(("A", "B"),))
    solve, _, report = _validate(fixture, "A")
    assert solve.walls[("A", Side.S)] is WallType.OPEN
    assert next(c for c in report.checks if c.check_id == "C13").passed
    assert next(c for c in report.checks if c.check_id == "C5").passed


# ------------------------------------------------------------------ the evidence rules

def test_realized_connections_accept_only_physical_evidence():
    fixture = _blocked_open_fixture()
    solve, doors, _ = _validate(fixture, "A")
    connections = realized_connections(solve.rects, solve.walls, doors)
    pairs = {frozenset((c.a, c.b)) for c in connections}
    assert frozenset(("A", "B")) in pairs           # a real door was built
    assert frozenset(("A", "C")) not in pairs       # declared open, but walled
    for connection in connections:
        assert connection.kind in ("DOOR", "OPEN")
        assert connection.evidence


def test_an_unplaceable_door_is_not_a_realized_connection():
    """A hole that does not fit carries no traffic, so it is not evidence of passage."""
    from app.vertical_slice.doors import Door

    rects = {"A": Rect(0, 0, 100, 100), "B": Rect(100, 0, 100, 100)}
    walls = {(z, s): WallType.PARTITION for z in rects for s in Side}
    unplaceable = Door("A", "B", ConnectionKind.DOOR, 0.9, (100, 50), "vertical",
                       placeable=False, shared_length_m=0.4)
    assert realized_connections(rects, walls, [unplaceable]) == []


def test_declared_topology_is_preserved_as_intent():
    """DesiredAccessTopology is not removed or rewritten — C13 is a COMPARISON against it."""
    fixture = _abc_fixture()
    assert len(fixture.access.edges) == 2
    _validate(fixture, "A")
    assert len(fixture.access.edges) == 2
    assert any({e.a, e.b} == {"A", "C"} for e in fixture.access.edges)


def test_validation_reports_the_failure_and_does_not_repair_it():
    """The invariant fails loudly; it never edits walls, doors or the topology to make itself
    pass."""
    fixture = _abc_fixture()
    solve, doors, report = _validate(fixture, "A")
    assert not report.ok
    assert solve.rects["A"].shared_edge_len_u(solve.rects["C"]) == 0  # geometry untouched
    assert not any({d.a, d.b} == {"A", "C"} for d in doors)           # no door invented
