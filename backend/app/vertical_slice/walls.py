"""Wall semantic model — Issue #45.

Walls up to this Issue exist only as PER-ROOM-SIDE facts (`RoomOut.walls`/`wall_facts`, keyed
`zone_id, side`) — there is no single list a caller can hand a door/window/fixture an id from, and
no class that distinguishes a wet-room's own interior wall or a safe room's envelope from an
ordinary partition. This module derives that single list from the REALIZED geometry
(`design_output.GeometricDesign`, the same output `app.demo.contract._wall_segments` already reads
for drawing) — never a second, independently-solved source of truth.

`WallClass` is a single-value COLLAPSE of the orthogonal facts `app.geometry_domain.walls.WallFacts`
already keeps separate (`boundary_context`, `construction`) — the same collapse a physical wall
schedule needs. THE PRECEDENCE THAT MATTERS: `EXTERIOR` (boundary_context) wins over `PROTECTED`
(construction RC_SAFE_ROOM), not the other way around. This is not an arbitrary choice — it is the
same fact `WallFacts`'s own module docstring exists to preserve ("a ממ"ד wall that is also on the
building envelope resolves to RC_SAFE_ROOM and the EXTERIOR fact is destroyed" — the exact defect
that made `WallFacts` orthogonal in the first place). Collapsing PROTECTED over EXTERIOR here would
silently reintroduce that same defect one layer up, this time for the wall SCHEDULE rather than
window placement. So the precedence, highest first:

    EXTERIOR      boundary_context is EXTERIOR (on the building envelope), whatever construction
                  the wall carries underneath — including a safe room's own outward wall.
    PROTECTED     construction is RC_SAFE_ROOM and NOT on the envelope — the safe room's own
                  walls facing the REST OF THE HOUSE, which is where "protected" (the room behind
                  it must stay sealed RC) is actually the wall's whole job.
    WET_SERVICE   an ordinary interior partition where at least one side is a wet room (BATHROOM
                  or TOILET) — the wall a plumbing stack, a waterproofing membrane or a fixture
                  schedule cares about differently from an ordinary partition. Mirrors
                  `wet_core.py`'s own "wet room" role set exactly, so the two never disagree about
                  what counts as wet.
    INTERIOR      everything else — an ordinary partition between two dry rooms.

`structural_candidate` is a placeholder field, always `False` here: NOTHING in this codebase
performs structural engineering (load paths, bearing analysis, a structural grid) — this module
does not start doing so. The field exists so a FUTURE structural engine has somewhere to record its
own opinion without changing this type's shape; it is not computed, inferred or defaulted from
anything geometric by this module, and no caller should read `False` as "verified non-structural".

`hosts` carries the door/window ids realized on this wall's own segment (matched by position: same
orientation, same coordinate, the opening's span inside the segment's own span) — never fixture ids
today: no fixture-PLACEMENT engine exists anywhere in this codebase (`furniture.py` is a bounding-box
feasibility SCREEN only, per-zone, with no fixture position), so there is nothing real to host. The
schema's `hosts` tuple is simply always empty of fixture ids until one exists — not a stub, not a
TODO marker, just an accurate empty set today.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .design_output import DoorOut, GeometricDesign, RoomOut, WindowOut
from .geometry_core.model import WALL_THICKNESS_M, WallType

_EPS = 1e-6

#: Mirrors `wet_core._WET_ROLES` exactly — the same "wet room" role set, so a wall this module
#: calls WET_SERVICE and a plan's plumbing-cluster report never disagree about what counts as wet.
#: Public: `app.demo.contract._wall_segments` reuses it so the drawing's own wall-class enrichment
#: never drifts from this module's definition of "wet".
WET_ROLES = frozenset({"BATHROOM", "TOILET"})


class WallClass(str, Enum):
    EXTERIOR = "EXTERIOR"
    INTERIOR = "INTERIOR"
    WET_SERVICE = "WET_SERVICE"
    PROTECTED = "PROTECTED"


@dataclass(frozen=True)
class WallSegmentM:
    """A drawable straight run, in metres — the same shape `app.demo.contract.WallSegment` draws
    from, kept as its own type here so this module owes nothing to the `app.demo` layer."""

    orientation: str  # "horizontal" | "vertical"
    coord: float
    start: float
    end: float


@dataclass(frozen=True)
class Wall:
    id: str
    wall_class: WallClass
    thickness_m: float
    segment: WallSegmentM
    #: Every room this wall's segment borders — one entry for an exterior wall, two for a shared
    #: interior wall.
    zones: tuple[str, ...]
    #: Door/window ids realized on this segment — see the module docstring for why fixture ids are
    #: never populated today.
    hosts: tuple[str, ...] = ()
    #: See the module docstring. Always `False` here; reserved for a future structural engine.
    structural_candidate: bool = False


def classify(*, on_envelope: bool, touches_safe: bool, touches_wet: bool) -> WallClass:
    """The precedence documented at the top of this module, as one pure function — the ONLY place
    that decision is made. `app.demo.contract._wall_segments` calls this too (it builds the same
    physical cuts for drawing, cosmetically re-opened afterward for the corridor rule), so a wall
    this module and the one the drawing enriches with a class can never disagree about which one a
    given segment gets."""
    if on_envelope:
        return WallClass.EXTERIOR
    if touches_safe:
        return WallClass.PROTECTED
    if touches_wet:
        return WallClass.WET_SERVICE
    return WallClass.INTERIOR


def door_id(a: str, b: str) -> str:
    return f"door:{a}->{b}"


def window_id(zone_id: str, side: str) -> str:
    return f"window:{zone_id}:{side}"


def _edges_m(room: RoomOut) -> dict[str, tuple[str, float, float, float]]:
    """side -> (orientation, coord, start, end), in metres, this room's own gross rectangle."""
    x, y, w, h = room.rect_m
    return {
        "N": ("horizontal", y, x, x + w),
        "S": ("horizontal", y + h, x, x + w),
        "W": ("vertical", x, y, y + h),
        "E": ("vertical", x + w, y, y + h),
    }


def _neighbours_along(rooms: tuple[RoomOut, ...], room: RoomOut, orientation: str, coord: float,
                       start: float, end: float):
    """The pieces of this side, cut where the room on the other side changes — the same cutting
    rule `app.demo.contract._wall_segments` uses, so a wall this module reports and the segment the
    renderer draws for the same physical wall are always cut identically."""
    cuts = {start, end}
    for other in rooms:
        if other.zone_id == room.zone_id:
            continue
        ox, oy, ow, oh = other.rect_m
        touches = (abs(ox - coord) < _EPS or abs(ox + ow - coord) < _EPS) if orientation == "vertical" \
            else (abs(oy - coord) < _EPS or abs(oy + oh - coord) < _EPS)
        if not touches:
            continue
        lo, hi = (oy, oy + oh) if orientation == "vertical" else (ox, ox + ow)
        if hi <= start + _EPS or lo >= end - _EPS:
            continue
        cuts.add(max(lo, start))
        cuts.add(min(hi, end))
    ordered = sorted(cuts)
    for lo, hi in zip(ordered, ordered[1:]):
        if hi - lo < _EPS:
            continue
        mid = (lo + hi) / 2
        facing = None
        for other in rooms:
            if other.zone_id == room.zone_id:
                continue
            ox, oy, ow, oh = other.rect_m
            touches = (abs(ox - coord) < _EPS or abs(ox + ow - coord) < _EPS) if orientation == "vertical" \
                else (abs(oy - coord) < _EPS or abs(oy + oh - coord) < _EPS)
            if not touches:
                continue
            olo, ohi = (oy, oy + oh) if orientation == "vertical" else (ox, ox + ow)
            if olo - _EPS <= mid <= ohi + _EPS:
                facing = other.zone_id
                break
        yield lo, hi, facing


def _door_on_segment(d: DoorOut, orientation: str, coord: float, start: float, end: float) -> bool:
    if d.orientation != orientation:
        return False
    along, across = (1, 0) if orientation == "vertical" else (0, 1)
    if abs(d.center_m[across] - coord) > _EPS:
        return False
    half = d.width_m / 2
    return d.center_m[along] - half < end - _EPS and d.center_m[along] + half > start + _EPS


def _window_on_segment(w: WindowOut, zones: tuple[str, ...], orientation: str, coord: float,
                        start: float, end: float, edges_of: dict[str, dict]) -> bool:
    if w.zone_id not in zones:
        return False
    w_orientation, w_coord, _, _ = edges_of[w.zone_id][w.side]
    if w_orientation != orientation or abs(w_coord - coord) > _EPS:
        return False
    along = 1 if orientation == "vertical" else 0
    half = w.width_m / 2
    return w.center_m[along] - half < end - _EPS and w.center_m[along] + half > start + _EPS


def derive_walls(design: GeometricDesign) -> tuple[Wall, ...]:
    """One `Wall` per physical segment of the realized geometry — exterior envelope, interior
    partitions, safe-room and wet-room walls alike. An `OPEN` side (no wall at all — an open-plan
    join) yields no `Wall`, exactly like `app.demo.contract._wall_segments`'s own `opens` split."""
    rooms = design.rooms
    is_safe = {r.zone_id: "SAFE_ROOM" in r.roles for r in rooms}
    is_wet = {r.zone_id: bool(WET_ROLES & set(r.roles)) for r in rooms}
    edges_of = {r.zone_id: _edges_m(r) for r in rooms}

    #: key -> accumulated facts for one physical segment.
    segments: dict[tuple, dict] = {}
    order: list[tuple] = []
    for room in rooms:
        for side, (orientation, coord, start, end) in edges_of[room.zone_id].items():
            facts = room.wall_facts[side]
            if facts.construction.value == "NONE":
                continue  # OPEN — no wall at all, mirrors `_wall_segments`'s `opens` split
            raw_type = WallType(room.walls[side])
            for lo, hi, facing in _neighbours_along(rooms, room, orientation, coord, start, end):
                key = (orientation, round(coord, 4), round(lo, 4), round(hi, 4))
                entry = segments.get(key)
                if entry is None:
                    entry = {"zones": [], "on_envelope": False, "touches_safe": False,
                             "touches_wet": False, "thickness_m": 0.0}
                    segments[key] = entry
                    order.append(key)
                if room.zone_id not in entry["zones"]:
                    entry["zones"].append(room.zone_id)
                if facts.boundary_context.value == "EXTERIOR":
                    entry["on_envelope"] = True
                if is_safe[room.zone_id] or (facing and is_safe.get(facing)):
                    entry["touches_safe"] = True
                if is_wet[room.zone_id] or (facing and is_wet.get(facing)):
                    entry["touches_wet"] = True
                entry["thickness_m"] = max(entry["thickness_m"], WALL_THICKNESS_M[raw_type])

    # `width_m > 0` excludes a placeholder door (e.g. the multi-level upper level's own sentinel
    # `entrance_door`, `building_coordinator.py`'s `Door("STAIR", "STAIR", ..., 0.0, ...)` — "no
    # real leaf" by its own comment) — the same real-door convention `door_clearance.py` uses.
    all_doors = [d for d in (*design.interior_doors, design.entrance_door) if d.width_m > 0]
    real_windows = [w for w in design.windows if w.width_m > 0]

    walls: list[Wall] = []
    for i, key in enumerate(order):
        orientation, coord, start, end = key
        entry = segments[key]
        wall_class = classify(on_envelope=entry["on_envelope"], touches_safe=entry["touches_safe"],
                              touches_wet=entry["touches_wet"])
        zones = tuple(entry["zones"])
        hosts = [door_id(d.a, d.b) for d in all_doors
                 if _door_on_segment(d, orientation, coord, start, end)]
        hosts += [window_id(w.zone_id, w.side) for w in real_windows
                  if _window_on_segment(w, zones, orientation, coord, start, end, edges_of)]
        walls.append(Wall(
            id=f"wall-{i}",
            wall_class=wall_class,
            thickness_m=entry["thickness_m"],
            segment=WallSegmentM(orientation=orientation, coord=coord, start=start, end=end),
            zones=zones,
            hosts=tuple(hosts),
        ))
    return tuple(walls)
