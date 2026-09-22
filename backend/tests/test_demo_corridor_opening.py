"""The corridor-opening rule (`contract._open_corridor_to_public`), a segment-level post-process.

The defect: in every spine parti the hall's long side faced the open living/dining/kitchen for
10-12 m with nothing on it but a 0.9 m cased opening, and was drawn as a full-length partition —
~17 m2 of enclosed corridor with the open-plan space directly behind the wall. The engine cannot
express the opening (one wall type per side; an OPEN side needs a full-edge match on both zones),
so the contract decides it on the merged wall SEGMENTS, exactly where a multi-neighbour side is
already re-typed per pair.

Two layers of proof:
  1. the predicate on hand-built segments, one condition at a time — public-facing opens, a
     door-bearing piece stays, EXTERIOR and RC never open, no open group means nothing opens;
  2. the real pipeline on the plan the rule was written for (4BR + safe room, open plan, spine
     parti): the public stretch opens, the private and door-bearing pieces stay, the cased
     opening's symbol goes, and every access/validation check is as green as before.

Nothing here touches Geometry Core, the WallMap, the generator's topology or validation.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.demo.contract import (
    DoorOut,
    OpenInterface,
    WallSegment,
    _open_corridor_to_public,
    _suppress_covered_cased_openings,
    to_demo_design,
)
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.general_pipeline import run_general_from_site
from app.vertical_slice.spec import ProgramSpec


# ------------------------------------------------------------------ 1. the predicate, in isolation

def _room(zone_id: str, *roles: str):
    return SimpleNamespace(zone_id=zone_id, roles=roles)


def _door(a: str, b: str, kind: str, orientation: str, centre: tuple[float, float],
          width_m: float = 0.9):
    return SimpleNamespace(a=a, b=b, kind=kind, orientation=orientation, center_m=centre,
                           width_m=width_m)


def _seg(a: str, b: str, start: float, end: float, construction: str = "STANDARD_PARTITION",
         context: str = "INTERIOR", coord: float = 10.0, orientation: str = "vertical"):
    return WallSegment(orientation=orientation, coord=coord, start=start, end=end,
                       construction=construction, boundary_context=context, room_ids=[a, b])


def _design(*, open_groups=(("LIVING", "DINING", "KITCHEN"),), cased=True, extra_doors=()):
    """A hall at x=10 running y=0..14, public zones on its west, a master bedroom at the foot."""
    rooms = [_room("HALL", "HALL", "CIRCULATION"), _room("LIVING", "LIVING"),
             _room("DINING", "DINING"), _room("KITCHEN", "KITCHEN"),
             _room("MASTER", "MASTER_BEDROOM"), _room("SAFE_ROOM", "SAFE_ROOM")]
    doors = [_door("HALL", "MASTER", "DOOR", "vertical", (10.0, 12.5)),
             _door("HALL", "SAFE_ROOM", "DOOR", "vertical", (11.4, 7.0)),
             *extra_doors]
    if cased:
        doors.insert(0, _door("HALL", "LIVING", "CASED_OPENING", "vertical", (10.0, 2.5)))
    entrance = _door("OUTSIDE", "HALL", "DOOR", "horizontal", (10.7, 0.0), 1.0)
    return SimpleNamespace(rooms=rooms, open_groups=open_groups, interior_doors=doors,
                           entrance_door=entrance)


def _run(design, walls):
    kept, opens = _open_corridor_to_public(design, walls, [])
    return kept, opens


def test_public_facing_corridor_segments_open_and_the_rest_stay():
    walls = [
        _seg("HALL", "LIVING", 0.0, 5.0),
        _seg("HALL", "DINING", 5.0, 8.0),
        _seg("HALL", "KITCHEN", 8.0, 11.0),
        _seg("HALL", "MASTER", 11.0, 14.0),                          # door-bearing, private
        _seg("HALL", "SAFE_ROOM", 5.5, 8.5, "RC_SAFE_ROOM", coord=11.4),
    ]
    kept, opens = _run(_design(), walls)
    assert {tuple(o.room_ids) for o in opens} == {
        ("HALL", "LIVING"), ("HALL", "DINING"), ("HALL", "KITCHEN")}
    assert sum(o.end - o.start for o in opens) == pytest.approx(11.0)
    assert {tuple(s.room_ids) for s in kept} == {("HALL", "MASTER"), ("HALL", "SAFE_ROOM")}


def test_a_door_bearing_public_segment_stays_walled():
    """A public zone the hall enters through a real DOOR keeps that piece of wall."""
    design = _design(extra_doors=[_door("HALL", "KITCHEN", "DOOR", "vertical", (10.0, 9.5))])
    walls = [_seg("HALL", "LIVING", 0.0, 5.0), _seg("HALL", "KITCHEN", 8.0, 11.0)]
    kept, opens = _run(design, walls)
    assert [tuple(o.room_ids) for o in opens] == [("HALL", "LIVING")]
    assert [tuple(s.room_ids) for s in kept] == [("HALL", "KITCHEN")]


def test_a_door_touching_the_segment_edge_only_does_not_hold_it():
    """Overlap must be real: a door spanning 5.0-5.9 sits on the DINING piece and only touches
    the LIVING piece's end, so LIVING still opens and DINING holds its wall."""
    design = _design(extra_doors=[_door("HALL", "DINING", "DOOR", "vertical", (10.0, 5.45))])
    walls = [_seg("HALL", "LIVING", 0.0, 5.0), _seg("HALL", "DINING", 5.0, 8.0)]
    kept, opens = _run(design, walls)
    assert [tuple(o.room_ids) for o in opens] == [("HALL", "LIVING")]
    assert [tuple(s.room_ids) for s in kept] == [("HALL", "DINING")]


@pytest.mark.parametrize("construction, context", [
    ("RC_SAFE_ROOM", "INTERIOR"),
    ("STANDARD_PARTITION", "EXTERIOR"),
    ("STRUCTURAL", "INTERIOR"),
])
def test_exterior_and_rc_segments_never_open(construction, context):
    walls = [_seg("HALL", "LIVING", 0.0, 5.0, construction, context)]
    kept, opens = _run(_design(), walls)
    assert opens == [] and kept == walls


def test_a_closed_plan_has_no_open_group_so_nothing_opens():
    walls = [_seg("HALL", "LIVING", 0.0, 5.0), _seg("HALL", "KITCHEN", 8.0, 11.0)]
    kept, opens = _run(_design(open_groups=()), walls)
    assert opens == [] and kept == walls


def test_without_a_declared_cased_opening_into_the_group_nothing_opens():
    walls = [_seg("HALL", "LIVING", 0.0, 5.0)]
    kept, opens = _run(_design(cased=False), walls)
    assert opens == [] and kept == walls


def test_two_public_zones_facing_each_other_are_not_the_corridor_rule():
    """The rule is hall <-> public only; a walled join between two group members is left alone
    (that is the engine's own OPEN marking, or a real partition it chose not to open)."""
    walls = [_seg("LIVING", "DINING", 0.0, 8.0, orientation="horizontal", coord=5.0)]
    kept, opens = _run(_design(), walls)
    assert opens == [] and kept == walls


def test_cased_opening_symbol_goes_only_when_its_span_is_fully_open():
    cased = DoorOut(a="HALL", b="LIVING", kind="CASED_OPENING", width_m=0.9, x=10.0, y=2.5,
                    orientation="vertical")
    real = DoorOut(a="HALL", b="MASTER", kind="DOOR", width_m=0.9, x=10.0, y=12.5,
                   orientation="vertical")
    fully = [OpenInterface(orientation="vertical", coord=10.0, start=0.0, end=5.0,
                           room_ids=["HALL", "LIVING"])]
    assert _suppress_covered_cased_openings([cased, real], fully) == [real]
    # Covered by two ADJACENT open pieces is still covered.
    split = [OpenInterface(orientation="vertical", coord=10.0, start=0.0, end=2.4, room_ids=[]),
             OpenInterface(orientation="vertical", coord=10.0, start=2.4, end=5.0, room_ids=[])]
    assert _suppress_covered_cased_openings([cased, real], split) == [real]
    # Partly covered — some wall remains around it — keeps the symbol.
    partial = [OpenInterface(orientation="vertical", coord=10.0, start=2.5, end=5.0, room_ids=[])]
    assert _suppress_covered_cased_openings([cased, real], partial) == [cased, real]
    # A different wall line is not this opening.
    elsewhere = [OpenInterface(orientation="vertical", coord=11.4, start=0.0, end=5.0, room_ids=[])]
    assert _suppress_covered_cased_openings([cased, real], elsewhere) == [cased, real]


# ------------------------------------------------------------------ 2. the real plan

@pytest.fixture(scope="module")
def spine_plan():
    """The plan the rule was written for: 4BR + safe room, open plan, on a plain rectangle —
    west column living/dining/kitchen over a master + bath row, hall spine, east bedroom column."""
    program = ProgramSpec(bedrooms=4, safe_room=True, open_plan_living=True, wet_rooms=2,
                          parking_spaces=2, target_built_area_m2=200)
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program)
    assert result.design is not None, result.notes
    return result, to_demo_design(result.design, result.validation)


def _hall_id(demo) -> str:
    halls = [r.id for r in demo.rooms if r.type in ("HALL", "CIRCULATION")]
    assert len(halls) == 1, halls
    return halls[0]


def _facing(segments, hall: str):
    return {tuple(sorted(s.room_ids)): s for s in segments if hall in s.room_ids}


def test_long_public_facing_corridor_wall_opens(spine_plan):
    result, demo = spine_plan
    hall = _hall_id(demo)
    public = {z for g in result.design.open_groups for z in g}
    assert public, "this brief is open plan"
    opened = [o for o in demo.open_interfaces if hall in o.room_ids]
    assert {z for o in opened for z in o.room_ids} - {hall} == public
    # No partition is left anywhere between the hall and the public zone.
    assert not [s for s in demo.walls
                if hall in s.room_ids and set(s.room_ids) & public]
    # It is the long stretch — most of the hall's length, not a token piece.
    hall_room = next(r for r in demo.rooms if r.id == hall)
    opened_len = sum(o.end - o.start for o in opened)
    assert opened_len > 0.7 * hall_room.depth_m, (opened_len, hall_room.depth_m)


def test_private_facing_portions_of_the_corridor_remain(spine_plan):
    result, demo = spine_plan
    hall = _hall_id(demo)
    private = {r.id for r in demo.rooms
               if r.type in ("BEDROOM", "MASTER_BEDROOM", "BATHROOM", "SAFE_ROOM", "TOILET")}
    walled = {z for s in demo.walls if hall in s.room_ids for z in s.room_ids} - {hall}
    touching = {z for s in demo.walls + demo.open_interfaces if hall in s.room_ids
                for z in s.room_ids} - {hall}
    assert private & touching, "the hall borders the private wing"
    assert private & touching <= walled, (private & touching) - walled
    # Nothing private ever appears on an open interface with the hall.
    assert not [o for o in demo.open_interfaces if hall in o.room_ids and set(o.room_ids) & private]


def test_door_bearing_segment_remains_and_carries_its_door(spine_plan):
    result, demo = spine_plan
    hall = _hall_id(demo)
    segs = _facing(demo.walls, hall)
    for door in demo.doors:
        if door.kind != "DOOR" or door.is_entrance or hall not in (door.a, door.b):
            continue
        seg = segs[tuple(sorted((door.a, door.b)))]
        assert seg.orientation == door.orientation
        along, across = ((door.y, door.x) if door.orientation == "vertical" else (door.x, door.y))
        assert across == pytest.approx(seg.coord)
        assert seg.start - 1e-6 <= along - door.width_m / 2 and along + door.width_m / 2 <= seg.end + 1e-6


def test_exterior_and_rc_never_open_in_the_real_plan(spine_plan):
    result, demo = spine_plan
    hall = _hall_id(demo)
    hall_room = next(r for r in demo.rooms if r.id == hall)
    exterior_sides = [s for s, f in hall_room.walls.items() if f["boundary_context"] == "EXTERIOR"]
    assert exterior_sides, "a spine hall runs from the front wall to the back wall"
    assert [s for s in demo.walls if s.room_ids == [hall] and s.boundary_context == "EXTERIOR"]
    safe = next(r.id for r in demo.rooms if r.type == "SAFE_ROOM")
    rc = [s for s in demo.walls if set(s.room_ids) == {hall, safe}]
    assert rc and all(s.construction == "RC_SAFE_ROOM" for s in rc)
    assert all(o.room_ids != [hall] for o in demo.open_interfaces)


def test_cased_opening_symbol_is_suppressed_where_its_wall_went(spine_plan):
    result, demo = spine_plan
    hall = _hall_id(demo)
    declared = [d for d in result.design.interior_doors if d.kind == "CASED_OPENING"]
    assert declared and all(hall in (d.a, d.b) for d in declared)
    assert not [d for d in demo.doors if d.kind == "CASED_OPENING"]
    # Every real door survived, untouched.
    assert [(d.a, d.b) for d in demo.doors if not d.is_entrance] == \
        [(d.a, d.b) for d in result.design.interior_doors if d.kind == "DOOR"]


def test_access_and_validation_remain_green(spine_plan):
    result, demo = spine_plan
    assert result.validation.ok, result.validation.failures()
    assert demo.validation.passed
    for code in ("C5", "C6", "C7", "C13"):
        assert demo.validation.checks[code], code
    # The rule is drawing truth only: room geometry, net areas and the corridor's measured
    # width are exactly what the engine solved. The drawing rectangle (x, y, gross_*) is the
    # engine's GROSS `rect_m` (Issue #34); `width_m`/`depth_m`/`area_m2` are its NET triple.
    hall = _hall_id(demo)
    engine_hall = next(r for r in result.design.rooms if r.zone_id == hall)
    demo_hall = next(r for r in demo.rooms if r.id == hall)
    assert (demo_hall.x, demo_hall.y, demo_hall.gross_width_m, demo_hall.gross_depth_m) == engine_hall.rect_m
    assert (demo_hall.width_m, demo_hall.depth_m) == (engine_hall.net_w_m, engine_hall.net_h_m)
    assert demo_hall.area_m2 == engine_hall.net_area_m2
    assert demo.corridor is not None
    assert demo.corridor.realized_width_m == pytest.approx(
        round(min(engine_hall.net_w_m, engine_hall.net_h_m), 2))


def test_a_closed_plan_keeps_its_corridor_walled():
    program = ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=False, wet_rooms=2,
                          parking_spaces=2, target_built_area_m2=None)
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program)
    assert result.design is not None, result.notes
    demo = to_demo_design(result.design, result.validation)
    hall = _hall_id(demo)
    assert result.design.open_groups == ()
    assert not [o for o in demo.open_interfaces if hall in o.room_ids]
    assert [d for d in demo.doors if d.kind == "CASED_OPENING"], "the living room's entrance stays"
