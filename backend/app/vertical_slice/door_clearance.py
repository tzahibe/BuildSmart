"""Stage 8b — Door usability (Issue #38).

C7 proves a door is PLACEABLE (real clearance on the shared wall). Nothing before this module
asked whether the leaf, once hung, is actually USABLE: two doors swinging into the same corner,
a door swinging into a wet-room fixture, a door that cannot reach 90 degrees open because the
room behind it is too shallow, or a door narrower than the access-rules width for its role pair.

Everything here reasons about the LEAF'S SWING ENVELOPE — the quarter-circle it sweeps from
closed (flat against the wall it's hung in) to open (flat against the perpendicular direction
`Door.swing_deg` names), radius the door's own width, apex `Door.hinge_at`. That geometry is
never invented here: `hinge_at`/`swing_deg` are the engine's own decisions (`doors.py`), made
before any conflict is known. `resolve_swings` is the one place this module makes a NEW decision —
flipping a conflicting door's swing to the room on the other side, deterministically, before
`check_doors_usable` (wired into `validation.py` as C28) fails closed on whatever is left.

THE WET-ROOM FIXTURE FOOTPRINT (`_wet_fixture_polygon_m`) is a conservative approximation, not a
real fixture catalogue — Issue 9 owns real furniture/fixture placement. A single WC-pan-and-
clearance box (`WET_FIXTURE_FOOTPRINT_M`), anchored at the TOILET/BATHROOM zone's own net-rect
corner farthest from the door(s) that enter it (the corner a real fixture would occupy precisely
because it is away from the door), same placeholder discipline as `windows.py`'s glazing
fractions: PARAMETER, not a verified fixture dimension.
"""
from __future__ import annotations

import math
from dataclasses import replace

from shapely.geometry import Polygon, box

from . import access_rules
from .access_rules import DoorKind
from .doors import Door, hinge_at_for, swing_deg_for
from .geometry_core.engine import WallMap
from .geometry_core.model import Fixture, ProgramRole, Rect, Side, inset_u, m_to_u, u_to_m
from .spec import CorridorRequirement

#: Ignore floating-point slivers: two envelopes/an envelope-and-fixture must overlap by more than
#: this to count as a real conflict.
_OVERLAP_TOL_M2 = 1e-4
_LEN_TOL_M = 1e-6
_ARC_SEGMENTS = 12

#: A conservative WC-pan-and-clearance box, not a real fixture catalogue — see module docstring.
WET_FIXTURE_ROLES = frozenset({ProgramRole.TOILET, ProgramRole.BATHROOM})
WET_FIXTURE_FOOTPRINT_M = (0.4, 0.6)

_CIRCULATION_ROLES = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})


# --------------------------------------------------------------------------- geometry helpers

def _net_rect_u(zone_id: str, rect: Rect, walls: WallMap) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the zone's NET rectangle, in grid units — centerline minus this leaf's own
    wall insets, same definition `geometry_core.engine.net_rect_m` uses, kept as (x, y, w, h) here
    because the fixture-footprint/door-wall checks need the net rectangle's POSITION too, not just
    its dimensions."""
    west = inset_u(walls[(zone_id, Side.W)])
    east = inset_u(walls[(zone_id, Side.E)])
    north = inset_u(walls[(zone_id, Side.N)])
    south = inset_u(walls[(zone_id, Side.S)])
    return rect.x + west, rect.y + north, rect.w - west - east, rect.h - north - south


def _wall_dir_deg(door: Door) -> float:
    """The CLOSED leaf's direction from `hinge_at` — along the wall the door is hung in, toward
    the far jamb. Always perpendicular to `swing_deg` by construction (that is exactly what a 90
    degree swing means)."""
    hx, hy = door.hinge_at
    cx, cy = door.center_u
    if door.orientation == "horizontal":
        far_x = 2 * cx - hx
        return 0.0 if far_x > hx else 180.0
    far_y = 2 * cy - hy
    return 90.0 if far_y > hy else 270.0


def swing_envelope_m(door: Door) -> Polygon:
    """The quarter-circle the leaf sweeps, in metres: a pie slice from the CLOSED direction
    (`_wall_dir_deg`) to the OPEN direction (`door.swing_deg`), radius `door.width_m`, apex
    `door.hinge_at`. Used for door-door and door-fixture conflict detection."""
    hinge_m = (u_to_m(door.hinge_at[0]), u_to_m(door.hinge_at[1]))
    start_deg = _wall_dir_deg(door)
    diff = (door.swing_deg - start_deg) % 360
    if diff > 180:
        diff -= 360
    points = [hinge_m]
    for i in range(_ARC_SEGMENTS + 1):
        theta = math.radians(start_deg + diff * i / _ARC_SEGMENTS)
        points.append((hinge_m[0] + door.width_m * math.cos(theta),
                       hinge_m[1] + door.width_m * math.sin(theta)))
    return Polygon(points)


def _perp_depth_m(door: Door, room_rect_u: tuple[int, int, int, int]) -> float:
    """How much of the room's NET depth lies beyond the door's own wall, in the direction the leaf
    swings open (`door.swing_deg`) — what the leaf's tip needs, at minimum, to reach 90 degrees
    without hitting the room's far wall."""
    hx, hy = door.hinge_at
    nx, ny, nw, nh = room_rect_u
    if door.orientation == "horizontal":
        depth_u = (ny + nh - hy) if door.swing_deg == 90.0 else (hy - ny)
    else:
        depth_u = (nx + nw - hx) if door.swing_deg == 0.0 else (hx - nx)
    return u_to_m(depth_u)


def _wet_fixture_polygon_m(zone_id: str, rects: dict[str, Rect], walls: WallMap,
                           doors_into_zone: list[Door]) -> Polygon | None:
    """The conservative wet-room fixture footprint for `zone_id` (see module docstring): a
    `WET_FIXTURE_FOOTPRINT_M` box anchored at the net-rect corner FARTHEST from the door(s)
    entering this zone (the corner a real fixture is placed to keep clear of the door)."""
    rect = rects.get(zone_id)
    if rect is None:
        return None
    nx, ny, nw, nh = _net_rect_u(zone_id, rect, walls)
    corners = [(nx, ny), (nx + nw, ny), (nx, ny + nh), (nx + nw, ny + nh)]
    hinges = [d.hinge_at for d in doors_into_zone] or [(nx, ny)]
    mx = sum(p[0] for p in hinges) / len(hinges)
    my = sum(p[1] for p in hinges) / len(hinges)
    far = max(corners, key=lambda c: (c[0] - mx) ** 2 + (c[1] - my) ** 2)

    fw_u = min(m_to_u(WET_FIXTURE_FOOTPRINT_M[0]), nw)
    fh_u = min(m_to_u(WET_FIXTURE_FOOTPRINT_M[1]), nh)
    x0, x1 = (nx, nx + fw_u) if far[0] == nx else (nx + nw - fw_u, nx + nw)
    y0, y1 = (ny, ny + fh_u) if far[1] == ny else (ny + nh - fh_u, ny + nh)
    return box(u_to_m(x0), u_to_m(y0), u_to_m(x1), u_to_m(y1))


# --------------------------------------------------------------------------- defect classes

def _door_door_defects(doors: list[Door]) -> list[str]:
    """Overlapping swing envelopes — including two leaves colliding in a shared corner, which
    shows up as exactly the same overlapping-envelope fact."""
    defects = []
    envelopes = [(d, swing_envelope_m(d)) for d in doors]
    for i in range(len(envelopes)):
        d1, e1 = envelopes[i]
        for j in range(i + 1, len(envelopes)):
            d2, e2 = envelopes[j]
            if e1.intersection(e2).area > _OVERLAP_TOL_M2:
                defects.append(f"{d1.a}-{d1.b} and {d2.a}-{d2.b}: door swing envelopes overlap")
    return defects


def _door_wall_defects(rects: dict[str, Rect], walls: WallMap, doors: list[Door]) -> list[str]:
    """The leaf cannot reach 90 degrees open because the room it swings into is too shallow in
    that direction."""
    defects = []
    for d in doors:
        rect = rects.get(d.swings_into)
        if rect is None:
            continue
        room_rect_u = _net_rect_u(d.swings_into, rect, walls)
        depth_m = _perp_depth_m(d, room_rect_u)
        if depth_m + _LEN_TOL_M < d.width_m:
            defects.append(
                f"{d.a}-{d.b}: only {depth_m:.2f} m of {d.swings_into}'s depth in the swing "
                f"direction, needs {d.width_m} m to open 90 degrees without hitting the far wall")
    return defects


def _door_fixture_defects(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                          doors: list[Door]) -> list[str]:
    """The leaf's swing envelope intersects the wet room's own fixture footprint."""
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    by_zone: dict[str, list[Door]] = {}
    for d in doors:
        by_zone.setdefault(d.swings_into, []).append(d)

    defects = []
    for zone_id, roles in roles_of.items():
        if not (WET_FIXTURE_ROLES & set(roles)):
            continue
        doors_into = by_zone.get(zone_id, [])
        if not doors_into:
            continue
        fixture_poly = _wet_fixture_polygon_m(zone_id, rects, walls, doors_into)
        if fixture_poly is None:
            continue
        for d in doors_into:
            if swing_envelope_m(d).intersection(fixture_poly).area > _OVERLAP_TOL_M2:
                defects.append(f"{d.a}-{d.b}: door swing intersects the {zone_id} fixture footprint")
    return defects


def _required_width_m(door: Door, roles_of: dict[str, tuple[ProgramRole, ...]]) -> float:
    if door.a == "OUTSIDE":
        return access_rules.DOOR_WIDTH_M[DoorKind.ENTRANCE_DOOR]
    kind = access_rules.door_kind_for_zones(roles_of.get(door.a, ()), roles_of.get(door.b, ()))
    return access_rules.DOOR_WIDTH_M[kind]


def _access_width_defects(roles_of: dict[str, tuple[ProgramRole, ...]], doors: list[Door]) -> list[str]:
    """The realized door is narrower than the access-rules width for its role pair (0.9 m rooms /
    0.8 m service / 1.0 m entrance, `access_rules.DOOR_WIDTH_M`) — normally unreachable, since
    `generate_interior_doors`/`build_entrance_door` already set the width from that table; this
    is the check that would catch a FUTURE path drifting from it."""
    defects = []
    for d in doors:
        required = _required_width_m(d, roles_of)
        if d.width_m + _LEN_TOL_M < required:
            defects.append(f"{d.a}-{d.b}: {d.width_m} m door narrower than the required "
                           f"{required} m access width for its role pair")
    return defects


def check_doors_usable(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                       doors: list[Door]) -> list[str]:
    """Every C28 defect for this plan's doors, empty when every door is usable. `doors` should be
    the plan's interior doors plus its entrance door, AFTER `resolve_swings` has already tried to
    flip away any door-door/door-fixture conflict — this never repairs anything itself, only
    reports what conflict resolution could not fix. A zero-width placeholder door (multi-level's
    synthetic stair "entrance") carries no real leaf and is skipped."""
    real_doors = [d for d in doors if d.width_m > 0]
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    return (_door_door_defects(real_doors)
            + _door_wall_defects(rects, walls, real_doors)
            + _door_fixture_defects(fixture, rects, walls, real_doors)
            + _access_width_defects(roles_of, real_doors))


# --------------------------------------------------------------------------- swing resolution

def _flip(roles_of: dict[str, tuple[ProgramRole, ...]], rects: dict[str, Rect],
         door: Door) -> Door | None:
    """The same door, hung the other way — swinging into whichever of `a`/`b` it does NOT swing
    into today. `None` for the entrance door (`a == "OUTSIDE"`): there is no other side to flip
    to, the street is not a room. Also `None` when the flip would swing the door INTO a
    HALL/CIRCULATION zone while the side it swings into today is not circulation — `doors.py`'s
    `_swing` refuses that by default (a leaf opening into a corridor blocks the corridor), and
    conflict resolution must not undo that guarantee just to shave a conflict count elsewhere.
    Flipping between two circulation zones (both sides already circulation, the one case `_swing`
    itself cannot avoid) is still allowed, since it is no worse than the default."""
    if door.a == "OUTSIDE":
        return None
    other = door.b if door.swings_into == door.a else door.a

    def is_circulation(zone_id: str) -> bool:
        return any(r in _CIRCULATION_ROLES for r in roles_of.get(zone_id, ()))

    if is_circulation(other) and not is_circulation(door.swings_into):
        return None
    width_u = m_to_u(door.width_m)
    hinge_at = hinge_at_for(rects, other, door.center_u, door.orientation, width_u)
    swing_deg = swing_deg_for(rects, other, door.center_u, door.orientation)
    return replace(door, swings_into=other, hinge_at=hinge_at, swing_deg=swing_deg)


def _conflict_count(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                    doors: list[Door]) -> int:
    real_doors = [d for d in doors if d.width_m > 0]
    return len(_door_door_defects(real_doors)
              + _door_wall_defects(rects, walls, real_doors)
              + _door_fixture_defects(fixture, rects, walls, real_doors))


def resolve_swings(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                   doors: list[Door]) -> list[Door]:
    """The engine's own conflict avoidance, run BEFORE C28: flip a door's swing to the room on the
    other side whenever that strictly reduces the number of door-door/door-wall/door-fixture
    defects, one flip at a time, until no further flip helps. Deterministic (doors are always
    tried in the same order) and bounded (at most `len(doors)` passes). Access-width defects are
    never swing-dependent, so they are not part of what this tries to fix — `check_doors_usable`
    fails closed on those regardless.

    A caller that already has a conflict-free door list gets it back unchanged, at the cost of one
    conflict count — the same cost every OTHER plan in the corpus pays today, which is why this is
    safe to call unconditionally rather than only when C28 would otherwise fail."""
    doors = list(doors)
    if _conflict_count(fixture, rects, walls, doors) == 0:
        return doors
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    for _ in range(len(doors)):
        current = _conflict_count(fixture, rects, walls, doors)
        if current == 0:
            break
        improved = False
        for i, d in enumerate(doors):
            flipped = _flip(roles_of, rects, d)
            if flipped is None:
                continue
            trial = list(doors)
            trial[i] = flipped
            if _conflict_count(fixture, rects, walls, trial) < current:
                doors = trial
                improved = True
                break
        if not improved:
            break
    return doors


# --------------------------------------------------------------------------- corridor quality note

def corridor_obstruction_notes(fixture: Fixture, doors: list[Door],
                               corridor: CorridorRequirement | None,
                               realized_corridor_width_m: float | None) -> list[str]:
    """Non-blocking quality note: a door whose leaf swings into circulation narrows the realized
    corridor below the requested C14 width WHILE OPEN — never a validation failure (a corridor is
    still walkable with the door closed), always worth disclosing. Empty when no corridor width
    was requested (nothing to measure against) or none was realized (C14 already fails closed on
    that)."""
    if corridor is None or realized_corridor_width_m is None:
        return []
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    notes = []
    for d in doors:
        if d.width_m <= 0 or not (_CIRCULATION_ROLES & set(roles_of.get(d.swings_into, ()))):
            continue
        available = realized_corridor_width_m - d.width_m
        if available + _LEN_TOL_M < corridor.width_m:
            notes.append(
                f"{d.a}-{d.b}: the open leaf narrows {d.swings_into} to {available:.2f} m, "
                f"below the requested {corridor.width_m:.2f} m corridor width")
    return notes
