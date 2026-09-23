"""Master-suite access and privacy — Issue #42.

The ensuite is already hosted by its bedroom (`wet_rooms.ResolvedWetRoom.host_zone`; C17 fails
closed on WHO may enter it, C24 fails closed on a room reachable only by passing through another
PRIVATE room). Nothing before this module reasoned about how the PIECES of the suite relate to
each other once that access is legal: where the ensuite door and any linked dressing-room door
land relative to the bed, whether a person standing in the hall with the bedroom door open sees
straight in, and whether reaching the ensuite or the wardrobe means walking through where the bed
sits. `compute_master_suites` answers that, per `MASTER_BEDROOM` zone, from the REALIZED geometry
only (rects, walls, doors) — the same discipline `wet_privacy.py`/`wet_core.py` already hold to,
never the requirement that produced it.

THE BED ZONE (`_bed_zone_polygon_m`) is a conservative placeholder footprint, not a real furniture
placement — same discipline `door_clearance.py`'s wet-fixture footprint already uses: a single
(width, depth) box — `MIN_FURNITURE_ENVELOPE_M[MASTER_BEDROOM]`, the same bed-plus-clearance
envelope `furniture.py`'s feasibility screen already relies on — anchored at the bedroom's own
net-rect corner FARTHEST from its own entry door (the door connecting it to the hall/circulation),
the corner a bed is actually placed to keep clear of the doorway. PARAMETER, not a verified
furniture dimension.

THE WARDROBE ENVELOPE reuses `MIN_FURNITURE_ENVELOPE_M[DRESSING_ROOM]` (a hanging rail plus the
passage to stand in front of it) as a stand-in for an in-room wardrobe footprint too — the same
envelope, whether the rail sits in its own room or against the bedroom's own wall.

THE ONE HARD RULE for a master suite is already `validation.py`'s C24 (an ensuite — or anything
else — reachable only by passing through another private room fails the access-topology check);
this module adds no new blocking rule. Everything here is quality data: `suite_score`/
`candidate_suite_key`/`better_candidate` for ranking two otherwise-equal candidates against each
other, never a gate — the same role `wet_privacy.candidate_privacy_key` already plays for wet-room
privacy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from shapely.geometry import LineString, Polygon, box

from .doors import Door
from .geometry_core.engine import WallMap
from .geometry_core.model import (
    MIN_FURNITURE_ENVELOPE_M,
    Fixture,
    ProgramRole,
    Rect,
    Side,
    inset_u,
    m_to_u,
    min_furniture_envelope_m,
    u_to_m,
)
from .wet_privacy import ZoneClass, classify_zone
from .wet_rooms import ResolvedWetRoom
from .spec import WetRoomKind

_OPPOSITE_SIDE = {Side.N: Side.S, Side.S: Side.N, Side.E: Side.W, Side.W: Side.E}

#: The wardrobe envelope stand-in — see the module docstring. Not a separate table: reusing
#: DRESSING_ROOM's own declared envelope keeps this module from inventing a second furniture
#: parameter for the same physical thing (a hanging rail plus the passage to use it).
_WARDROBE_ENVELOPE_M = MIN_FURNITURE_ENVELOPE_M[ProgramRole.DRESSING_ROOM]

#: `suite_score` weights — LOWER IS BETTER, ranking only, never a gate (see module docstring). A
#: route across the bed clearance is the worst offence (the person cannot avoid stepping over/
#: around the bed just to reach the ensuite); a blind sight line into the ensuite from the hall is
#: a lesser, cosmetic one. Ordering mirrors `wet_privacy`'s own exposure-band ordering (a hard-
#: feeling defect scores higher than a soft one), not a calibrated study.
_SCORE_ENSUITE_ROUTE_CROSSES_BED = 1.0
_SCORE_WARDROBE_ROUTE_CROSSES_BED = 0.5
_SCORE_HALL_SIGHT_LINE_TO_BED = 0.3
_SCORE_HALL_SIGHT_LINE_TO_ENSUITE_DOOR = 0.2


class EnsuiteAccess(str, Enum):
    #: Entered straight off this bedroom — the only state that clears C17 for an ENSUITE.
    DIRECT = "DIRECT"
    #: Entered from a hall/circulation zone rather than this bedroom directly (never legal for a
    #: real ENSUITE under C17, but this module only observes, never validates — see docstring).
    VIA_CIRCULATION = "VIA_CIRCULATION"
    #: No ensuite hosted by this bedroom.
    NONE = "NONE"


class WardrobeRelationship(str, Enum):
    #: A linked `DRESSING_ROOM` zone entered directly from this bedroom.
    DRESSING_ROOM = "DRESSING_ROOM"
    #: No separate dressing room, but the bedroom's own net floor comfortably holds a wardrobe
    #: envelope alongside the bed envelope (area-only heuristic — see module docstring).
    IN_ROOM = "IN_ROOM"
    #: Neither a dressing room nor comfortable in-room space for one.
    NONE = "NONE"


@dataclass(frozen=True)
class MasterSuite:
    """One master bedroom's suite standing. See the module docstring for how each field is read
    off the realized geometry."""

    bedroom_zone_id: str
    ensuite_zone_id: str | None
    ensuite_access: EnsuiteAccess
    wardrobe_zone_id: str | None
    wardrobe_relationship: WardrobeRelationship
    #: Does a person in the hall, with the bedroom door open, see straight into the bed zone?
    hall_sight_line_to_bed: bool
    #: Does a person in the hall, with the bedroom door open, see straight to the ensuite door?
    hall_sight_line_to_ensuite_door: bool
    #: Does the straight path from the bedroom's own entry door to the ensuite door cross the bed
    #: clearance zone?
    ensuite_route_crosses_bed: bool
    #: Same, for the path to the wardrobe/dressing-room door (`False` when there is none).
    wardrobe_route_crosses_bed: bool
    #: One aggregate number, LOWER IS BETTER, for ranking two otherwise-equal candidates against
    #: each other — never a gate.
    suite_score: float


def _net_rect_u(zone_id: str, rect: Rect, walls: WallMap) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the zone's NET rectangle, in grid units — same definition
    `door_clearance._net_rect_u` uses, needed here (rather than `engine.net_rect_m`'s dimensions-
    only form) because the bed-zone anchor needs the net rectangle's POSITION too."""
    west = inset_u(walls[(zone_id, Side.W)])
    east = inset_u(walls[(zone_id, Side.E)])
    north = inset_u(walls[(zone_id, Side.N)])
    south = inset_u(walls[(zone_id, Side.S)])
    return rect.x + west, rect.y + north, rect.w - west - east, rect.h - north - south


def _door_side(rect: Rect, door: Door) -> Side | None:
    """Which of `rect`'s four walls `door` sits in, read off the door's own centerline center —
    exact by construction (`doors.generate_interior_doors` sets it from this same rect)."""
    x, y = door.center_u
    if x == rect.x:
        return Side.W
    if x == rect.x2:
        return Side.E
    if y == rect.y:
        return Side.N
    if y == rect.y2:
        return Side.S
    return None


def _spans_overlap_axis(door_a: Door, door_b: Door, axis: int) -> bool:
    """Do the two doors' own opening spans overlap along `axis` (0=x, 1=y) — the same overlap
    test `wet_privacy._spans_overlap`/`_opening_span_u` use for a facing-door pair, reimplemented
    locally so this module never reaches into another module's private helpers."""
    a_half = m_to_u(door_a.width_m) // 2
    b_half = m_to_u(door_b.width_m) // 2
    a = door_a.center_u[axis]
    b = door_b.center_u[axis]
    return max(a - a_half, b - b_half) < min(a + a_half, b + b_half)


def _direct_sight_line(rect: Rect, entry_door: Door | None, target_door: Door | None) -> bool:
    """Is `target_door` directly ahead through `entry_door`, on the OPPOSITE wall with an
    overlapping opening span — what a person looking straight through the open bedroom doorway
    would see, without turning their head toward a side wall."""
    if entry_door is None or target_door is None:
        return False
    entry_side = _door_side(rect, entry_door)
    target_side = _door_side(rect, target_door)
    if entry_side is None or target_side is None or target_side != _OPPOSITE_SIDE[entry_side]:
        return False
    axis = 0 if entry_side in (Side.N, Side.S) else 1
    return _spans_overlap_axis(entry_door, target_door, axis)


def _bed_zone_polygon_m(rect: Rect, walls: WallMap, zone_id: str,
                        entry_door: Door | None, envelope_m: tuple[float, float] | None) -> Polygon | None:
    """The bed's conservative footprint (see module docstring): `envelope_m` anchored at the net-
    rect corner FARTHEST from `entry_door`'s own center — `None` when there is no declared
    envelope for this role or no rect to anchor it in."""
    if envelope_m is None:
        return None
    nx, ny, nw, nh = _net_rect_u(zone_id, rect, walls)
    corners = [(nx, ny), (nx + nw, ny), (nx, ny + nh), (nx + nw, ny + nh)]
    hx, hy = entry_door.center_u if entry_door is not None else (nx, ny)
    far = max(corners, key=lambda c: (c[0] - hx) ** 2 + (c[1] - hy) ** 2)

    bw_u = min(m_to_u(envelope_m[0]), nw)
    bh_u = min(m_to_u(envelope_m[1]), nh)
    x0, x1 = (nx, nx + bw_u) if far[0] == nx else (nx + nw - bw_u, nx + nw)
    y0, y1 = (ny, ny + bh_u) if far[1] == ny else (ny + nh - bh_u, ny + nh)
    return box(u_to_m(x0), u_to_m(y0), u_to_m(x1), u_to_m(y1))


def _forward_ray_m(entry_door: Door, net_rect_u: tuple[int, int, int, int]) -> LineString:
    """A straight segment from `entry_door`'s own center to the point directly opposite it on the
    far wall — what a person looking straight ahead through the open doorway sees."""
    nx, ny, nw, nh = net_rect_u
    cx, cy = entry_door.center_u
    if entry_door.orientation == "horizontal":
        far_y = ny + nh if cy <= ny else ny
        p0, p1 = (cx, cy), (cx, far_y)
    else:
        far_x = nx + nw if cx <= nx else nx
        p0, p1 = (cx, cy), (far_x, cy)
    return LineString([(u_to_m(p0[0]), u_to_m(p0[1])), (u_to_m(p1[0]), u_to_m(p1[1]))])


def _route_crosses_bed(entry_door: Door | None, target_door: Door | None,
                       bed_polygon: Polygon | None) -> bool:
    """Does the straight path between the two door centers cross the bed clearance zone — the
    "route bedroom door -> ensuite/wardrobe door without crossing the bed clearance" signal."""
    if entry_door is None or target_door is None or bed_polygon is None:
        return False
    route = LineString([
        (u_to_m(entry_door.center_u[0]), u_to_m(entry_door.center_u[1])),
        (u_to_m(target_door.center_u[0]), u_to_m(target_door.center_u[1])),
    ])
    return route.intersects(bed_polygon)


def _ensuite_access(bedroom_zone_id: str, ensuite_zone_id: str | None,
                    roles_of: dict[str, tuple[ProgramRole, ...]],
                    interior_doors: Sequence[Door]) -> EnsuiteAccess:
    if ensuite_zone_id is None:
        return EnsuiteAccess.NONE
    entered_from = {d.a if d.b == ensuite_zone_id else d.b
                    for d in interior_doors if ensuite_zone_id in (d.a, d.b)}
    if entered_from == {bedroom_zone_id}:
        return EnsuiteAccess.DIRECT
    return EnsuiteAccess.VIA_CIRCULATION


def _wardrobe_relationship(has_dressing_room: bool, bed_envelope_m: tuple[float, float] | None,
                           net_w_m: float, net_h_m: float) -> WardrobeRelationship:
    if has_dressing_room:
        return WardrobeRelationship.DRESSING_ROOM
    if bed_envelope_m is None:
        return WardrobeRelationship.NONE
    needed_area = bed_envelope_m[0] * bed_envelope_m[1] + _WARDROBE_ENVELOPE_M[0] * _WARDROBE_ENVELOPE_M[1]
    return WardrobeRelationship.IN_ROOM if net_w_m * net_h_m >= needed_area else WardrobeRelationship.NONE


def _suite_score(ensuite_route_crosses_bed: bool, wardrobe_route_crosses_bed: bool,
                 hall_sight_line_to_bed: bool, hall_sight_line_to_ensuite_door: bool) -> float:
    score = 0.0
    if ensuite_route_crosses_bed:
        score += _SCORE_ENSUITE_ROUTE_CROSSES_BED
    if wardrobe_route_crosses_bed:
        score += _SCORE_WARDROBE_ROUTE_CROSSES_BED
    if hall_sight_line_to_bed:
        score += _SCORE_HALL_SIGHT_LINE_TO_BED
    if hall_sight_line_to_ensuite_door:
        score += _SCORE_HALL_SIGHT_LINE_TO_ENSUITE_DOOR
    return round(score, 4)


def compute_master_suites(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                          interior_doors: Sequence[Door],
                          wet_rooms: Sequence[ResolvedWetRoom]) -> tuple[MasterSuite, ...]:
    """One `MasterSuite` per `MASTER_BEDROOM` zone actually in this plan. Every fact read off
    `rects`/`walls`/`interior_doors`, never off `wet_rooms` beyond which zone hosts an ensuite —
    the same "read the geometry, not the intent" split `wet_privacy.compute_wet_privacy` holds to.
    """
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    zone_by_id = {z.zone_id: z for z in fixture.zones}
    ensuite_host_of = {w.host_zone: w.zone_id for w in wet_rooms
                       if w.kind is WetRoomKind.ENSUITE and w.host_zone is not None}

    out: list[MasterSuite] = []
    for zone in fixture.zones:
        if ProgramRole.MASTER_BEDROOM not in zone.roles:
            continue
        bedroom_id = zone.zone_id
        rect = rects.get(bedroom_id)
        if rect is None:
            continue

        touching = [d for d in interior_doors if bedroom_id in (d.a, d.b)]

        def _other(door: Door) -> str:
            return door.b if door.a == bedroom_id else door.a

        entry_door = next(
            (d for d in touching if classify_zone(roles_of.get(_other(d), ())) is ZoneClass.CIRCULATION),
            None)

        ensuite_zone_id = ensuite_host_of.get(bedroom_id)
        ensuite_door = (next((d for d in touching if ensuite_zone_id in (d.a, d.b)), None)
                        if ensuite_zone_id is not None else None)

        dressing_zone_id = next(
            (_other(d) for d in touching if ProgramRole.DRESSING_ROOM in roles_of.get(_other(d), ())),
            None)
        wardrobe_door = (next((d for d in touching if dressing_zone_id in (d.a, d.b)), None)
                         if dressing_zone_id is not None else None)

        ensuite_access = _ensuite_access(bedroom_id, ensuite_zone_id, roles_of, interior_doors)

        bed_envelope_m = min_furniture_envelope_m(zone_by_id[bedroom_id])
        bed_polygon = _bed_zone_polygon_m(rect, walls, bedroom_id, entry_door, bed_envelope_m)

        net_rect_u = _net_rect_u(bedroom_id, rect, walls)
        net_w_m, net_h_m = u_to_m(net_rect_u[2]), u_to_m(net_rect_u[3])

        wardrobe_relationship = _wardrobe_relationship(
            dressing_zone_id is not None, bed_envelope_m, net_w_m, net_h_m)

        hall_sight_line_to_bed = (entry_door is not None and bed_polygon is not None
                                  and _forward_ray_m(entry_door, net_rect_u).intersects(bed_polygon))
        hall_sight_line_to_ensuite_door = _direct_sight_line(rect, entry_door, ensuite_door)
        ensuite_route_crosses_bed = _route_crosses_bed(entry_door, ensuite_door, bed_polygon)
        wardrobe_route_crosses_bed = _route_crosses_bed(entry_door, wardrobe_door, bed_polygon)

        out.append(MasterSuite(
            bedroom_zone_id=bedroom_id,
            ensuite_zone_id=ensuite_zone_id,
            ensuite_access=ensuite_access,
            wardrobe_zone_id=dressing_zone_id,
            wardrobe_relationship=wardrobe_relationship,
            hall_sight_line_to_bed=hall_sight_line_to_bed,
            hall_sight_line_to_ensuite_door=hall_sight_line_to_ensuite_door,
            ensuite_route_crosses_bed=ensuite_route_crosses_bed,
            wardrobe_route_crosses_bed=wardrobe_route_crosses_bed,
            suite_score=_suite_score(ensuite_route_crosses_bed, wardrobe_route_crosses_bed,
                                     hall_sight_line_to_bed, hall_sight_line_to_ensuite_door),
        ))
    return tuple(out)


def candidate_suite_key(records: Sequence[MasterSuite]) -> tuple[float, float]:
    """(worst suite's score, sum of every suite's score) — LOWER IS BETTER. Mirrors
    `wet_privacy.candidate_privacy_key`: the worst suite is what a person notices first, the sum
    breaks a tie between two candidates whose worst suite is equally exposed but whose OTHER
    suites are not. Never a gate — a caller comparing two otherwise-equal candidate plans picks the
    one with the lower key."""
    scores = [r.suite_score for r in records]
    if not scores:
        return (0.0, 0.0)
    return (round(max(scores), 4), round(sum(scores), 4))


def better_candidate(a: Sequence[MasterSuite], b: Sequence[MasterSuite]) -> Sequence[MasterSuite]:
    """Which of two candidates' suite records reads as more livable — `a` on an exact tie, so the
    choice is deterministic rather than depending on argument order by accident."""
    return a if candidate_suite_key(a) <= candidate_suite_key(b) else b
