"""C24 — access topology obeys the door rules (`app/vertical_slice/access_rules.py`, Issue #18).

Each negative fixture is a row of zones sharing full walls (so every declared DOOR edge is
physically realizable), differing only in which edges are declared — the same "only the
requirement changes" discipline `test_c17_bathroom_access.py` uses, since C24 is meant to judge
the TOPOLOGY, not the geometry.
"""
from __future__ import annotations

from app.vertical_slice import site as site_stage
from app.vertical_slice.access_rules import DOOR_WIDTH_M, DoorKind
from app.vertical_slice.doors import build_entrance_door, generate_interior_doors
from app.vertical_slice.geometry_core.engine import derive_wall_types, leaf_shapes, solve_fixture
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
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import validate

_ROW_DEPTH_M = 4.0


def _row_tree(zone_ids: list[str]):
    n = len(zone_ids)

    def build(i: int):
        return Leaf(zone_ids[i]) if i == n - 1 else Split(Cut.V, Leaf(zone_ids[i]), build(i + 1), None)

    return build(0)


def _row_fixture(name: str, zones: list[tuple[str, tuple[ProgramRole, ...], float, float, float, float]],
                 edges: tuple[DesiredAccessEdge, ...]) -> Fixture:
    """`zones`, left to right in one row on a shared depth (so every pair of neighbours shares a
    full wall): `(zone_id, roles, area_min, area_target, area_max, min_short_side)`. The row's
    total width is AUTOSIZED — the midpoint of the width range every zone's own shape curve
    (queried against a generous tentative width) can jointly satisfy at the shared depth — since
    the geometry solver needs an EXACT width match across the row and a fixed guess routinely
    misses that range as roles/areas change per test."""
    specs = tuple(ZoneSpec(zid, roles, lo, target, hi, short)
                 for zid, roles, lo, target, hi, short in zones)
    tree = _row_tree([z[0] for z in zones])
    bh = m_to_u(_ROW_DEPTH_M)
    tentative = Wing(name, 0, 0, m_to_u(50.0), bh, tree)
    tentative_fixture = Fixture(name, (tentative,), specs, DesiredAccessTopology(()))
    walls = derive_wall_types(tentative_fixture, tentative, {}, {})
    min_sum = max_sum = 0
    for spec in specs:
        row = leaf_shapes(spec, walls, tentative.w_u, bh).get(bh)
        if not row:
            raise ValueError(f"{spec.zone_id}: no feasible width at depth {_ROW_DEPTH_M} m")
        min_sum += min(row)
        max_sum += max(row)
    wing = Wing(name, 0, 0, (min_sum + max_sum) // 2, bh, tree)
    return Fixture(name, (wing,), specs, DesiredAccessTopology(edges))


def _c24(fixture: Fixture):
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
    entrance_door = build_entrance_door(entrance, footprint, fixture.zones[0].zone_id)
    report = validate(fixture, solve.rects, solve.walls, doors, entrance_door, [], [], site)
    return next(c for c in report.checks if c.check_id == "C24")


_HALL = ("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 8, 15, 1.5)


def test_c24_rejects_bedroom_to_bedroom_door():
    fixture = _row_fixture("BED2BED", [
        _HALL,
        ("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
        ("BEDROOM_2", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
    ], (
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("BEDROOM_1", "BEDROOM_2", ConnectionKind.DOOR),
    ))
    check = _c24(fixture)
    assert not check.passed
    assert "BEDROOM_1-BEDROOM_2" in check.detail


def test_c24_rejects_a_room_reachable_only_through_a_bedroom():
    fixture = _row_fixture("THROUGH_BEDROOM", [
        _HALL,
        ("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
        ("STORAGE_1", (ProgramRole.STORAGE,), 2, 4, 8, 0.9),
    ], (
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("BEDROOM_1", "STORAGE_1", ConnectionKind.DOOR),
    ))
    check = _c24(fixture)
    assert not check.passed
    assert "STORAGE_1" in check.detail


def test_c24_passes_on_canonical_fixtures(tmp_path):
    result = run_demo(str(tmp_path / "canonical.svg"))
    check = next(c for c in result.validation.checks if c.check_id == "C24")
    assert check.passed, check.detail

    # The one sanctioned PRIVATE-to-(wet) exception: an ensuite entered only from its own
    # bedroom, with nothing else attached to it.
    fixture = _row_fixture("ENSUITE_OK", [
        _HALL,
        ("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 20, 3.0),
        ("BATH_1", (ProgramRole.BATHROOM,), 4.5, 6.5, 12, 1.6),
    ], (
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
    ))
    check2 = _c24(fixture)
    assert check2.passed, check2.detail


def test_c24_allows_wet_room_from_living_but_not_kitchen_or_dining():
    """spec 009 decision C: LIVING is the guest WC's last public-access fallback (after HALL/
    circulation and the hosting bedroom); KITCHEN and DINING stay disallowed."""
    living_ok = _row_fixture("LIVING_WC", [
        ("LIVING", (ProgramRole.LIVING,), 16, 20, 26, 3.0),
        ("TOILET_1", (ProgramRole.TOILET,), 2.2, 4.0, 6.0, 1.1),
    ], (
        DesiredAccessEdge("LIVING", "TOILET_1", ConnectionKind.DOOR),
    ))
    check = _c24(living_ok)
    assert check.passed, check.detail

    kitchen_bad = _row_fixture("KITCHEN_WC", [
        ("KITCHEN", (ProgramRole.KITCHEN,), 10, 13, 18, 2.4),
        ("TOILET_1", (ProgramRole.TOILET,), 2.2, 4.0, 6.0, 1.1),
    ], (
        DesiredAccessEdge("KITCHEN", "TOILET_1", ConnectionKind.DOOR),
    ))
    check = _c24(kitchen_bad)
    assert not check.passed
    assert "KITCHEN-TOILET_1" in check.detail

    dining_bad = _row_fixture("DINING_WC", [
        ("DINING", (ProgramRole.DINING,), 9, 11, 15, 2.4),
        ("TOILET_1", (ProgramRole.TOILET,), 2.2, 4.0, 6.0, 1.1),
    ], (
        DesiredAccessEdge("DINING", "TOILET_1", ConnectionKind.DOOR),
    ))
    check = _c24(dining_bad)
    assert not check.passed
    assert "DINING-TOILET_1" in check.detail


def _door_width_for(role: ProgramRole, band: tuple[float, float, float, float]) -> float:
    lo, target, hi, short = band
    fixture = _row_fixture(f"WIDTH_{role.value}", [
        _HALL,
        ("ROOM", (role,), lo, target, hi, short),
    ], (
        DesiredAccessEdge("HALL", "ROOM", ConnectionKind.DOOR),
    ))
    solve = solve_fixture(fixture)
    doors = generate_interior_doors(fixture, solve.rects)
    door = next(d for d in doors if {"HALL", "ROOM"} == {d.a, d.b})
    return door.width_m


def test_service_doors_are_narrower_and_room_doors_unchanged():
    assert DOOR_WIDTH_M[DoorKind.SERVICE_DOOR] == 0.8
    assert DOOR_WIDTH_M[DoorKind.ROOM_DOOR] == 0.9
    assert DOOR_WIDTH_M[DoorKind.ENTRANCE_DOOR] == 1.0

    narrow = {
        ProgramRole.TOILET: (2.2, 4.0, 6.0, 1.1),
        ProgramRole.LAUNDRY: (2.5, 4.0, 8.0, 1.5),
        ProgramRole.STORAGE: (1.5, 3.0, 6.0, 1.0),
    }
    for role, band in narrow.items():
        assert _door_width_for(role, band) == 0.8, role

    unchanged = {
        ProgramRole.BATHROOM: (4.5, 6.5, 12.0, 1.6),
        ProgramRole.BEDROOM: (9.0, 10.5, 14.0, 2.6),
    }
    for role, band in unchanged.items():
        assert _door_width_for(role, band) == 0.9, role

    footprint = Rect(0, 0, m_to_u(12.0), m_to_u(4.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    entrance_door = build_entrance_door(entrance, footprint, "HALL")
    assert entrance_door.width_m == 1.0
