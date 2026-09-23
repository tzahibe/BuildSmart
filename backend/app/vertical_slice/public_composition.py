"""Public-zone composition: kitchen, dining and living as a coherent architectural composition,
not three independent rectangular strips (Issue #41).

`quality_metrics.py`'s M6 already reports whether the public zone is one contiguous OPEN-PLAN
group; the hub parti and the strip-room quality tier already shape public rooms; `contract.py`'s
`_open_corridor_to_public` already opens the hall<->LDK wall visually. Nothing before this module
measured the kitchen-dining-living RELATIONSHIPS themselves (are they actually adjacent/linked, not
merely both "public"), the entrance's relation to the public zone, or whether a person's walking
path from the entrance to a public room is obstructed by another room's own furniture.

Reads `app.vertical_slice.design_output.GeometricDesign` alone — the same realized-plan type
`circulation_metrics.py`/`entrance_sequence.py` already read, for the same reason: a check, a
ranking decision and a report must never disagree about what a plan's composition looks like — plus
`interior_layout.compute_layout(design)` for the furniture clearance rectangles the circulation-path
signal needs. Pure and deterministic; never mutates or re-solves anything.

    measure(design)                     -> PublicComposition   # one plan's own facts
    hard_violations(composition)        -> list[str]            # C31's gate (validation.py)
    composition_prefers(current, cand)  -> str | None            # the (currently unwired) ranking term

OPEN PLAN IS NEVER PENALIZED. `public_zone_coherent` and the two pairwise `_related` facts below can
only ever help `composition_score` (lower is better) or leave it unchanged — never a term that
scores a merged/open public zone worse than a closed one for being open (AC-1).

THE ONE HARD RULE (C31): a public (LIVING/DINING/KITCHEN) room whose only realized path from the
entrance/hall passes THROUGH another room's furniture clearance zone with no way around it — not
"furniture exists in a room on the way" (an ordinary, expected fact), but the specific case where
the only route between that room's own entry opening and its own exit opening onward is blocked.
Computed geometrically (`shapely`, the same library `interior_layout.py` places furniture with):
each intermediate room's NET rectangle minus the union of every placed item's own
`clearance_rect_m` is the room's walkable free space; the entry and exit openings are "connected"
only when they sit in the SAME connected piece of that free space. A room with no furniture, or
furniture that leaves a berth around it, is trivially connected — this never fires on an ordinary
plan with a normally-sized dining table pushed to one side.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from shapely.geometry import Point, box
from shapely.ops import unary_union

from . import interior_layout
from .design_output import DoorOut, GeometricDesign, RoomOut
from .geometry_core.model import WallType, WALL_THICKNESS_M

#: Mirrors `quality_metrics.PUBLIC` exactly — the three roles this Issue's composition covers.
_LDK_ROLES = frozenset({"LIVING", "DINING", "KITCHEN"})

#: How far inside a room's own net rectangle an opening's reference point sits, so it reads as
#: genuinely INSIDE the walkable free space rather than sitting on its own boundary (where a
#: polygon's `contains`/`covers` test is unreliable to floating-point noise). Small relative to any
#: real room's own net dimensions (the smallest room template is well over 1 m short side).
_OPENING_NUDGE_M = 0.3

#: Two points are "the same spot" within this tolerance — mirrors
#: `circulation_metrics._DOOR_END_TOLERANCE_M`/`entrance_sequence._SAME_POINT_TOLERANCE_M` for the
#: same 5 cm solver-grid reason.
_SIDE_TOLERANCE_M = 0.05

#: `composition_score`'s own per-defect weights — LOWER IS BETTER, the same convention
#: `wet_privacy.privacy_score` uses. A `None` fact (the plan genuinely has no room of that kind) is
#: NEVER penalized — only a definite, measured defect costs anything.
_SCORE_NOT_RELATED = 1.0
_SCORE_NO_PUBLIC_PATH = 1.0
_SCORE_NO_EXTERIOR = 1.0
_SCORE_NO_WINDOW = 0.5
_SCORE_BLOCKED_ROOM = 2.0


@dataclass(frozen=True)
class PublicComposition:
    """One realized plan's public-zone composition facts. A field is `None` only when the plan
    genuinely has no room of the kind that fact needs (e.g. no DINING room at all) — the same
    "no metric where nothing of that kind exists" discipline `quality_metrics.QualityMetrics` and
    `wet_privacy.WetPrivacy` both already use."""

    #: Is a KITCHEN linked to a DINING room by a door or an open-plan join (either counts — this is
    #: a relationship fact, not an open-plan preference)? `None` when the plan has no KITCHEN or no
    #: DINING room.
    kitchen_dining_related: bool | None
    #: The same question for DINING<->LIVING.
    dining_living_related: bool | None
    #: Is every LIVING/DINING/KITCHEN room in the plan one connected OPEN-PLAN group (an `OPEN`
    #: wall side joins them, mirrors `quality_metrics._public_zone_contiguous`/M6 exactly, computed
    #: independently here since M6 reads a different design type)? `None` when the plan has fewer
    #: than two LDK rooms.
    public_zone_coherent: bool | None
    #: Is ANY LIVING/DINING/KITCHEN room reachable at all from the entrance's own arrival zone,
    #: over the realized access graph?
    entrance_reaches_public: bool
    #: Does the LIVING room (if any) have at least one exterior-envelope wall?
    living_exterior_exposed: bool | None
    #: Does the LIVING room (if any) have a placeable window?
    living_has_window: bool | None
    #: C31's own defect list: the zone_id of every LDK room whose only realized path from the
    #: entrance is blocked by another room's own furniture clearance, with no way around it. `()`
    #: on every plan measured so far in this codebase's own corpus and canonical fixtures.
    blocked_public_rooms: tuple[str, ...]
    #: One aggregate number, LOWER IS BETTER, for ranking two otherwise-equal candidates against
    #: each other — never a gate; `blocked_public_rooms` above (via `hard_violations`) is the only
    #: fail-closed path. See the module docstring for why openness itself never costs anything here.
    composition_score: float


# --------------------------------------------------------------------------- shared adjacency

def _adjacency(design: GeometricDesign) -> dict[str, set[str]]:
    """Mirrors `circulation_metrics._adjacency`/`entrance_sequence._adjacency` exactly — a small,
    deliberate duplicate (see those modules' own docstrings for why each sibling keeps its own
    copy rather than sharing one)."""
    adj: dict[str, set[str]] = {}

    def link(a: str, b: str) -> None:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    for door in design.interior_doors:
        if door.placeable:
            link(door.a, door.b)
    if design.entrance_door.placeable:
        link("OUTSIDE", design.entrance_door.b)
    for group in design.open_groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                link(group[i], group[j])
    return adj


def _ldk_rooms(design: GeometricDesign) -> list[RoomOut]:
    return [r for r in design.rooms if set(r.roles) & _LDK_ROLES]


def _rooms_with_role(design: GeometricDesign, role: str) -> list[str]:
    return [r.zone_id for r in design.rooms if role in r.roles]


def _related(adjacency: dict[str, set[str]], a_rooms: list[str], b_rooms: list[str]) -> bool | None:
    if not a_rooms or not b_rooms:
        return None
    return any(b in adjacency.get(a, ()) for a in a_rooms for b in b_rooms)


def _open_adjacency(design: GeometricDesign) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {}
    for group in design.open_groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                adj.setdefault(group[i], set()).add(group[j])
                adj.setdefault(group[j], set()).add(group[i])
    return adj


def _public_zone_coherent(design: GeometricDesign) -> bool | None:
    """Mirrors `quality_metrics._public_zone_contiguous` (M6) exactly, on `GeometricDesign`'s own
    `open_groups` rather than `DemoDesign`'s flattened `open_interfaces`."""
    ldk = [r.zone_id for r in _ldk_rooms(design)]
    if len(ldk) < 2:
        return None
    ldk_set = set(ldk)
    open_adj = _open_adjacency(design)
    seen: set[str] = set()
    stack = [ldk[0]]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(x for x in open_adj.get(n, ()) if x in ldk_set)
    return all(z in seen for z in ldk)


def _entrance_reaches_public(design: GeometricDesign, adjacency: dict[str, set[str]]) -> bool:
    if not design.entrance_door.placeable:
        return False
    arrival = design.entrance_door.b
    ldk_ids = {r.zone_id for r in _ldk_rooms(design)}
    if not ldk_ids:
        return False
    seen = {arrival}
    frontier = [arrival]
    while frontier:
        cur = frontier.pop()
        if cur in ldk_ids:
            return True
        for nxt in adjacency.get(cur, ()):
            if nxt != "OUTSIDE" and nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return arrival in ldk_ids


def _living_exposure(design: GeometricDesign) -> tuple[bool | None, bool | None]:
    living = [r for r in design.rooms if "LIVING" in r.roles]
    if not living:
        return None, None
    exterior = any(f.is_on_envelope for r in living for f in r.wall_facts.values())
    has_window = any(w.zone_id == r.zone_id and w.placeable for r in living for w in design.windows)
    return exterior, has_window


# --------------------------------------------------------------------------- C31: blocked paths


def _net_origin_m(room: RoomOut) -> tuple[float, float]:
    """A small, deliberate duplicate of `interior_layout._net_origin_m` — see that module's own
    docstring for why each sibling in this vertical slice keeps its own tiny copy of geometry math
    like this rather than importing another module's private helper."""
    x, y, _, _ = room.rect_m
    inset_w = WALL_THICKNESS_M[WallType(room.walls["W"])] / 2
    inset_n = WALL_THICKNESS_M[WallType(room.walls["N"])] / 2
    return x + inset_w, y + inset_n


def _shared_side(room: RoomOut, other: RoomOut) -> str | None:
    ax, ay, aw, ah = room.rect_m
    bx, by, bw, bh = other.rect_m
    if abs((ax + aw) - bx) <= _SIDE_TOLERANCE_M:
        return "E"
    if abs(ax - (bx + bw)) <= _SIDE_TOLERANCE_M:
        return "W"
    if abs((ay + ah) - by) <= _SIDE_TOLERANCE_M:
        return "S"
    if abs(ay - (by + bh)) <= _SIDE_TOLERANCE_M:
        return "N"
    return None


def _door_or_entrance_between(design: GeometricDesign, a: str, b: str) -> DoorOut | None:
    for door in (*design.interior_doors, design.entrance_door):
        if door.placeable and {door.a, door.b} == {a, b}:
            return door
    return None


def _opening_point_in_room(design: GeometricDesign, room: RoomOut, neighbor_id: str,
                           rooms: dict[str, RoomOut]) -> tuple[float, float] | None:
    """A point just inside `room`'s own net rectangle, near wherever it connects to `neighbor_id`
    (another room's zone_id, or `"OUTSIDE"` for the entrance door itself) — a door's own position
    along the shared wall when one exists, otherwise the shared side's own midpoint (a full-side
    open-plan join). `None` only when the two share no physical connection at all (should not
    happen for a real adjacency edge; defensive, not expected)."""
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    depth_ns = min(_OPENING_NUDGE_M, nh)
    depth_ew = min(_OPENING_NUDGE_M, nw)
    door = _door_or_entrance_between(design, room.zone_id, neighbor_id)
    if door is not None:
        cx, cy = door.center_m
        rx, ry, rw, rh = room.rect_m
        if door.orientation == "horizontal":  # sits on the room's N or S wall
            u = min(max(cx - nx, 0.0), nw)
            on_north = abs(cy - ry) <= abs(cy - (ry + rh))
            return (nx + u, ny + depth_ns) if on_north else (nx + u, ny + nh - depth_ns)
        v = min(max(cy - ny, 0.0), nh)  # sits on the room's W or E wall
        on_west = abs(cx - rx) <= abs(cx - (rx + rw))
        return (nx + depth_ew, ny + v) if on_west else (nx + nw - depth_ew, ny + v)

    other = rooms.get(neighbor_id)
    if other is None:
        return None
    side = _shared_side(room, other)
    if side is None:
        return None
    if side == "N":
        return (nx + nw / 2, ny + depth_ns)
    if side == "S":
        return (nx + nw / 2, ny + nh - depth_ns)
    if side == "W":
        return (nx + depth_ew, ny + nh / 2)
    return (nx + nw - depth_ew, ny + nh / 2)  # E


def _free_space(room: RoomOut, layout: interior_layout.RoomLayout | None):
    nx, ny = _net_origin_m(room)
    room_poly = box(nx, ny, nx + room.net_w_m, ny + room.net_h_m)
    if layout is None or not layout.placed:
        return room_poly
    obstacles = [box(x, y, x + w, y + h) for x, y, w, h in
                (item.clearance_rect_m for item in layout.placed)]
    return room_poly.difference(unary_union(obstacles))


def _connected(free_space, p1: tuple[float, float], p2: tuple[float, float]) -> bool:
    if free_space.is_empty:
        return False
    parts = list(getattr(free_space, "geoms", None) or [free_space])
    pt1, pt2 = Point(p1), Point(p2)
    part1 = next((i for i, part in enumerate(parts) if part.buffer(1e-6).contains(pt1)), None)
    part2 = next((i for i, part in enumerate(parts) if part.buffer(1e-6).contains(pt2)), None)
    return part1 is not None and part1 == part2


def _furniture_reachable_rooms(design: GeometricDesign, rooms: dict[str, RoomOut],
                               adjacency: dict[str, set[str]], arrival: str,
                               layouts: dict[str, interior_layout.RoomLayout]) -> set[str]:
    """Every room reachable from `arrival` when a room may only be CROSSED between two of its own
    openings if that specific pass-through is not furniture-blocked — unlike a plain graph BFS
    (`_adjacency` alone), a room with three openings can be blocked between ONE pair and still
    passable between another, and an ALTERNATE route through a different room is explored exactly
    like any other graph edge. Standing just inside a room (having crossed its own doorway) always
    counts as "reached", even when every further pass-through it offers is blocked.

    Nodes are `(room_id, entered_from)` so the SAME room can be revisited via a different entry
    opening — the only way a room with several doors can legitimately offer more than one route
    onward. Free space and opening points are computed once per room and cached, so this stays
    linear in the number of (room, opening) pairs, not the number of paths."""
    free_space_cache: dict[str, object] = {}
    point_cache: dict[tuple[str, str], tuple[float, float] | None] = {}

    def free_space_of(zone_id: str):
        if zone_id not in free_space_cache:
            free_space_cache[zone_id] = _free_space(rooms[zone_id], layouts.get(zone_id))
        return free_space_cache[zone_id]

    def point_of(zone_id: str, neighbor_id: str) -> tuple[float, float] | None:
        key = (zone_id, neighbor_id)
        if key not in point_cache:
            point_cache[key] = _opening_point_in_room(design, rooms[zone_id], neighbor_id, rooms)
        return point_cache[key]

    reached_rooms = {arrival}
    seen_nodes = {(arrival, "OUTSIDE")}
    queue: deque[tuple[str, str]] = deque([(arrival, "OUTSIDE")])
    while queue:
        room_id, entered_from = queue.popleft()
        entry_point = point_of(room_id, entered_from)
        for neighbor_id in sorted(adjacency.get(room_id, ())):
            if neighbor_id in (entered_from, "OUTSIDE"):
                continue
            if entry_point is not None:
                exit_point = point_of(room_id, neighbor_id)
                if exit_point is not None and not _connected(free_space_of(room_id),
                                                              entry_point, exit_point):
                    continue  # THIS specific pass-through is blocked; another route may still work
            reached_rooms.add(neighbor_id)
            node = (neighbor_id, room_id)
            if node not in seen_nodes and neighbor_id in rooms:
                seen_nodes.add(node)
                queue.append(node)
    return reached_rooms


def _blocked_public_rooms(design: GeometricDesign,
                          layouts: dict[str, interior_layout.RoomLayout]) -> tuple[str, ...]:
    """C31's own defect list: every LDK room the plain access graph says IS reachable (so this is
    never misdiagnosing a genuine C5 unreachability) but that no furniture-respecting route above
    ever reaches — i.e. genuinely "no path", not merely "the first path tried is blocked"."""
    if not design.entrance_door.placeable:
        return ()
    arrival = design.entrance_door.b
    rooms = {r.zone_id: r for r in design.rooms}
    if arrival not in rooms:
        return ()
    adjacency = _adjacency(design)
    ldk_ids = {r.zone_id for r in _ldk_rooms(design)}
    graph_reachable = set()
    frontier = [arrival]
    seen = {arrival}
    while frontier:
        cur = frontier.pop()
        for nxt in adjacency.get(cur, ()):
            if nxt != "OUTSIDE" and nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    graph_reachable = seen & ldk_ids
    furniture_reachable = _furniture_reachable_rooms(design, rooms, adjacency, arrival, layouts)
    return tuple(sorted(graph_reachable - furniture_reachable))


# --------------------------------------------------------------------------- public API

def measure(design: GeometricDesign) -> PublicComposition:
    """Every public-zone composition fact this module measures, for one realized plan."""
    adjacency = _adjacency(design)
    kitchen_dining = _related(adjacency, _rooms_with_role(design, "KITCHEN"),
                              _rooms_with_role(design, "DINING"))
    dining_living = _related(adjacency, _rooms_with_role(design, "DINING"),
                             _rooms_with_role(design, "LIVING"))
    coherent = _public_zone_coherent(design)
    reaches_public = _entrance_reaches_public(design, adjacency)
    exterior, window = _living_exposure(design)
    layouts = {rl.room_id: rl for rl in interior_layout.compute_layout(design)}
    blocked = _blocked_public_rooms(design, layouts)

    score = 0.0
    if kitchen_dining is False:
        score += _SCORE_NOT_RELATED
    if dining_living is False:
        score += _SCORE_NOT_RELATED
    if not reaches_public:
        score += _SCORE_NO_PUBLIC_PATH
    if exterior is False:
        score += _SCORE_NO_EXTERIOR
    if window is False:
        score += _SCORE_NO_WINDOW
    score += len(blocked) * _SCORE_BLOCKED_ROOM

    return PublicComposition(
        kitchen_dining_related=kitchen_dining,
        dining_living_related=dining_living,
        public_zone_coherent=coherent,
        entrance_reaches_public=reaches_public,
        living_exterior_exposed=exterior,
        living_has_window=window,
        blocked_public_rooms=blocked,
        composition_score=round(score, 4),
    )


def hard_violations(composition: PublicComposition) -> list[str]:
    """C31's fail-closed list — empty means every public room clears the hard rule. See the module
    docstring: a public room whose only realized path is blocked by another room's furniture, with
    no way around it. Everything else `PublicComposition` reports is quality/ranking data only."""
    return [f"{zone_id}: only realized path to it is blocked by furniture in an intermediate room, "
           f"no way around it" for zone_id in composition.blocked_public_rooms]


def composition_prefers(current: PublicComposition, candidate: PublicComposition) -> str | None:
    """`None`: `candidate`'s composition earns it the primary over `current` on this measure alone.
    Otherwise why not — mirrors `circulation_metrics.circulation_prefers`/
    `entrance_sequence.entrance_sequence_prefers`'s shape (a single correctness comparison). LOWER
    `composition_score` wins; an exact tie keeps `current` (never promotes on a non-improvement)."""
    if candidate.composition_score < current.composition_score - 1e-9:
        return None
    return (f"candidate's composition score ({candidate.composition_score:.2f}) is not better than "
           f"the current plan's ({current.composition_score:.2f})")
