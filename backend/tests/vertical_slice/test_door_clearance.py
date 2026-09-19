"""Door usability (`app/vertical_slice/door_clearance.py`, Issue #38): swing-envelope conflicts
(door-door, door-wall, door-fixture) and the access-rules width, wired into validation as C28.

Fixtures here construct `Door`/`Rect`/`WallMap` BY HAND rather than through the geometry solver —
door_clearance reasons purely about swing geometry (hinge, swing direction, width) over already-
solved rects, so a hand-built rect is exactly as authoritative an input as a solved one, and gives
full control over the corner geometry each defect class needs. Every zone here uses `WallType.OPEN`
walls (net == gross) since this module's checks are about swing geometry, not wall thickness.
"""
from __future__ import annotations

from app.vertical_slice.door_clearance import (
    check_doors_usable,
    resolve_swings,
    swing_envelope_m,
)
from app.vertical_slice.doors import Door, build_entrance_door, generate_interior_doors
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    ProgramRole,
    Rect,
    Side,
    WallType,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice import site as site_stage
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import validate


def _open_walls(zone_ids: list[str]) -> dict[tuple[str, Side], WallType]:
    return {(zone_id, side): WallType.OPEN for zone_id in zone_ids for side in Side}


def _fixture(zones: list[ZoneSpec]) -> Fixture:
    return Fixture("HAND_BUILT", (), tuple(zones), DesiredAccessTopology(()))


# ------------------------------------------------------------------ AC-1: one fixture per defect class

def test_conflict_classes_on_fixtures_and_none_on_canonical():
    """AC-1: door_clearance detects each conflict class (door-door, door-fixture, door-wall,
    access-width) on a hand-built fixture isolating that class, and reports none on the demo
    pipeline's own canonical fixture."""

    # --- door-door: two doors hinged at the SAME corner of the room they both swing into — their
    # swing envelopes are identical quarter-discs, so they collide outright, the "two doors in a
    # corner" case. Both doors' `a` is `OUTSIDE`, so `resolve_swings` cannot flip either away,
    # isolating the DETECTION from the resolution AC-2 covers.
    room_c = Rect(0, 0, m_to_u(2.0), m_to_u(2.0))
    zones = [ZoneSpec("ROOM_C", (ProgramRole.LIVING,), 3, 4, 8, 1.5)]
    fixture = _fixture(zones)
    rects = {"ROOM_C": room_c}
    walls = _open_walls(["ROOM_C"])

    width_u = m_to_u(0.9)
    d1 = Door("OUTSIDE", "ROOM_C", ConnectionKind.DOOR, 0.9, (0, width_u // 2), "vertical",
             True, 2.0, "ROOM_C", (0, 0), 0.0)
    d2 = Door("OUTSIDE", "ROOM_C", ConnectionKind.DOOR, 0.9, (width_u // 2, 0), "horizontal",
             True, 2.0, "ROOM_C", (0, 0), 90.0)

    assert swing_envelope_m(d1).intersection(swing_envelope_m(d2)).area > 0.1

    defects = check_doors_usable(fixture, rects, walls, [d1, d2])
    assert any("swing envelopes overlap" in d for d in defects), defects
    # Unresolvable: both hinge on the street ("OUTSIDE"), so there is no other side to flip to.
    assert resolve_swings(fixture, rects, walls, [d1, d2]) == [d1, d2]

    # --- door-fixture: a minimal WC whose only door swings across almost the whole room — the
    # swing envelope reaches the fixture footprint anchored in the far corner. `a="OUTSIDE"` again
    # isolates detection from resolution (a real ensuite/WC's only other side is its host or the
    # hall; using `OUTSIDE` just means "nothing to flip to" without asserting which real role
    # that is).
    room = Rect(0, 0, m_to_u(0.8), m_to_u(1.0))
    zones = [ZoneSpec("TOILET_1", (ProgramRole.TOILET,), 0.8, 1.0, 2.0, 0.8)]
    fixture = _fixture(zones)
    rects = {"TOILET_1": room}
    walls = _open_walls(["TOILET_1"])

    width_u = m_to_u(0.8)
    door = Door("OUTSIDE", "TOILET_1", ConnectionKind.DOOR, 0.8, (0, width_u // 2), "vertical",
               True, 1.0, "TOILET_1", (0, 0), 0.0)

    defects = check_doors_usable(fixture, rects, walls, [door])
    assert any("fixture footprint" in d for d in defects), defects
    assert resolve_swings(fixture, rects, walls, [door]) == [door]

    # --- door-wall: a strip room only 0.8 m deep in the direction the door swings — the leaf
    # cannot reach 90 degrees without hitting the room's own far wall.
    room = Rect(0, 0, m_to_u(3.0), m_to_u(0.8))
    zones = [ZoneSpec("STRIP", (ProgramRole.STORAGE,), 2, 2.4, 5, 0.8)]
    fixture = _fixture(zones)
    rects = {"STRIP": room}
    walls = _open_walls(["STRIP"])

    width_u = m_to_u(0.9)
    door = Door("OUTSIDE", "STRIP", ConnectionKind.DOOR, 0.9, (m_to_u(1.5), 0), "horizontal",
               True, 3.0, "STRIP", (m_to_u(1.5) - width_u // 2, 0), 90.0)

    defects = check_doors_usable(fixture, rects, walls, [door])
    assert any("depth in the swing direction" in d for d in defects), defects

    # --- access-width: a door narrower than the access-rules width for its own role pair (a
    # `ROOM_DOOR` pair realized at 0.7 m) — normally unreachable through
    # `generate_interior_doors`, which is exactly why this check exists: to catch it if some
    # future path ever drifts.
    zones = [
        ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 8, 15, 1.5),
        ZoneSpec("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
    ]
    fixture = _fixture(zones)
    door = Door("HALL", "BEDROOM_1", ConnectionKind.DOOR, 0.7, (0, 0), "vertical",
               True, 1.0, "BEDROOM_1", (0, 0), 0.0)

    defects = check_doors_usable(fixture, {}, {}, [door])
    assert any("access width" in d for d in defects), defects

    # --- none on canonical: the demo pipeline's own canonical fixture (`pipeline.run_demo`) — C28
    # must be clean on it, the same "additive, does not touch what already plans" bar C24 was
    # held to.
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        result = run_demo(os.path.join(d, "canonical.svg"))
    check = next(c for c in result.validation.checks if c.check_id == "C28")
    assert check.passed, check.detail


# ------------------------------------------------------------------ AC-2: C28 + engine swing resolution

def _row_with_two_doors_into_the_corner(room_a_beyond: bool):
    """ROOM_C (2x2 m) is entered by two doors, D1 from ROOM_A (west) and D2 from ROOM_B (north),
    both hinged at ROOM_C's own NW corner — by default BOTH swing into ROOM_C (the "smaller room
    wins" rule, since ROOM_A/ROOM_B are both larger), which collide there exactly like
    `test_door_door_conflict_detected` above. `room_a_beyond` controls whether ROOM_A has real
    space for D1 to flip into (the resolvable case) or is absent entirely (the unresolvable one).
    """
    room_c = Rect(0, 0, m_to_u(2.0), m_to_u(2.0))
    rects = {"ROOM_C": room_c}
    zones = [ZoneSpec("ROOM_C", (ProgramRole.LIVING,), 3, 4, 8, 1.5)]
    if room_a_beyond:
        rects["ROOM_A"] = Rect(-m_to_u(4.0), 0, m_to_u(4.0), m_to_u(4.0))
        zones.append(ZoneSpec("ROOM_A", (ProgramRole.LIVING,), 10, 14, 20, 3.0))
    zones.append(ZoneSpec("ROOM_B", (ProgramRole.LIVING,), 10, 14, 20, 3.0))
    rects["ROOM_B"] = Rect(0, -m_to_u(4.0), m_to_u(4.0), m_to_u(4.0))
    fixture = _fixture(zones)
    walls = _open_walls(list(rects))

    # When there is no room to flip into, BOTH doors must be unflippable ("OUTSIDE") — otherwise
    # the OTHER door (whose alternate room always exists) would resolve the conflict by itself,
    # which is a real resolution, not the unresolvable case this branch is meant to exercise.
    width_u = m_to_u(0.9)
    d1_a = "ROOM_A" if room_a_beyond else "OUTSIDE"
    d2_a = "ROOM_B" if room_a_beyond else "OUTSIDE"
    d1 = Door(d1_a, "ROOM_C", ConnectionKind.DOOR, 0.9, (0, width_u // 2), "vertical",
             True, 2.0, "ROOM_C", (0, 0), 0.0)
    d2 = Door(d2_a, "ROOM_C", ConnectionKind.DOOR, 0.9, (width_u // 2, 0), "horizontal",
             True, 2.0, "ROOM_C", (0, 0), 90.0)
    return fixture, rects, walls, [d1, d2]


def test_c28_fails_door_door_and_door_fixture_and_engine_flips_swing_first():
    # --- the resolvable door-door case: the engine flips D1 into ROOM_A before C28 ever runs.
    fixture, rects, walls, doors = _row_with_two_doors_into_the_corner(room_a_beyond=True)
    assert check_doors_usable(fixture, rects, walls, doors), "fixture must start in conflict"
    resolved = resolve_swings(fixture, rects, walls, doors)
    assert not check_doors_usable(fixture, rects, walls, resolved)
    flipped = next(d for d in resolved if d.b == "ROOM_C" and d.orientation == "vertical")
    assert flipped.swings_into == "ROOM_A"

    # --- the SAME corner conflict, but with no room to flip into: C28 fails closed.
    fixture, rects, walls, doors = _row_with_two_doors_into_the_corner(room_a_beyond=False)
    resolved = resolve_swings(fixture, rects, walls, doors)
    defects = check_doors_usable(fixture, rects, walls, resolved)
    assert any("swing envelopes overlap" in d for d in defects), defects

    # --- door-fixture: a door swinging into a toilet's fixture footprint, no room to flip into.
    room = Rect(0, 0, m_to_u(0.8), m_to_u(1.0))
    zones = [ZoneSpec("TOILET_1", (ProgramRole.TOILET,), 0.8, 1.0, 2.0, 0.8)]
    fx_fixture = _fixture(zones)
    fx_rects = {"TOILET_1": room}
    fx_walls = _open_walls(["TOILET_1"])
    width_u = m_to_u(0.8)
    door = Door("OUTSIDE", "TOILET_1", ConnectionKind.DOOR, 0.8, (0, width_u // 2), "vertical",
               True, 1.0, "TOILET_1", (0, 0), 0.0)
    resolved = resolve_swings(fx_fixture, fx_rects, fx_walls, [door])
    defects = check_doors_usable(fx_fixture, fx_rects, fx_walls, resolved)
    assert any("fixture footprint" in d for d in defects), defects


def test_c28_wired_into_validate_via_a_solved_fixture():
    """C28 is a real check on the report `validate()` returns, not just a standalone function —
    proven over one small solved fixture rather than the full canonical pipeline (already covered
    by `test_canonical_fixtures_report_no_c28_defects`)."""
    from tests.vertical_slice.test_access_rules import _row_fixture, _HALL

    fixture = _row_fixture("C28_WIRING", [
        _HALL,
        ("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 10.5, 14, 2.6),
    ], (
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
    ))
    solve = solve_fixture(fixture)
    wing = fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    parking = site_stage.build_parking(spec)
    site = site_stage.SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance,
                               site_stage.classify_garden(spec, plot, footprint, parking))
    doors = generate_interior_doors(fixture, solve.rects)
    entrance_door = build_entrance_door(entrance, footprint, fixture.zones[0].zone_id)
    report = validate(fixture, solve.rects, solve.walls, doors, entrance_door, [], [], site)
    check = next(c for c in report.checks if c.check_id == "C28")
    assert check.passed, check.detail
