"""Stage 9b — Interior layout: engine-owned semantic layout objects (Issue #39).

Plans have looked like room outlines with a bounding-box furniture feasibility SCREEN
(`furniture.py`, C9) rather than architectural drawings. This module places real, typed objects
per room role — bed/wardrobe, sofa/coffee table/focal wall, dining table, kitchen counter run,
bathroom fixtures — so the renderer has something to draw "as-is": no decorative invention on
either side.

DELIBERATELY reads only `design_output.GeometricDesign` (rooms/doors/windows, already in metres) —
the same decoupling `circulation_metrics.py` and the renderer itself rely on — never
`geometry_core`'s `Fixture`/`Rect`/grid units beyond the two FROZEN constants
(`WallType`/`WALL_THICKNESS_M`) needed to recover a room's net-rect ORIGIN: `RoomOut` carries net
WIDTH/HEIGHT but not net (x, y), since nothing needed it before this Issue. Geometry Core itself is
untouched.

Called ONCE, from `app.demo.contract.to_demo_design`, on the final assembled design for every plan
actually delivered — never during candidate search/generation, so it costs nothing there (the same
reasoning `validation.py`'s C26 comment gives for keeping `assemble()` itself cheap).

THE SWING-ENVELOPE MATH IS A DELIBERATE, SMALL DUPLICATE of `door_clearance.swing_envelope_m` —
that one operates on grid-unit `doors.Door` objects, this one on the metre-scale `design_output.
DoorOut` already available here. Same precedent as `app.demo.service._street_fronting_roles` being
a separate implementation of `doors.street_fronting_roles`'s idea for the same decoupling reason
(see that function's own docstring).

PLACEMENT POLICY, one deterministic pass per room, role by role (`room.roles[0]`, the same
primary-role convention `contract._template_of` already uses):

  * a role's items are requested in a fixed order (see `_ROLE_ITEMS`/the per-role placers below)
  * each item is offered a wall in priority order: longest usable run first (deterministic
    tie-break by a fixed N/E/S/W order), never a wall carrying a door (`_door_sides`, matched by
    orientation+coordinate against every interior door AND the entrance door — whichever side of
    the door this room is on), and — only for an item that would BLOCK a window (`blocks_window`,
    e.g. a wardrobe) — never a wall carrying a placeable window either
  * the item is placed FLUSH against the chosen wall; its `clearance_rect_m` extends from the wall
    into the room by the item's own required clearance depth, clipped to the room's own net
    rectangle — which is why "never overlaps a wall" holds by construction: the room's NET
    rectangle already excludes every wall's own thickness
  * an item is reported `unplaceable` (a reason string, in `RoomLayout.unplaceable` — never raised,
    never forced) when no wall/position clears the room's net rectangle, every ALREADY-PLACED
    item's own clearance rectangle in this room, and every swing envelope of a door that opens
    INTO this room (`_swing_obstacles`)

ONE DOCUMENTED EXCEPTION: LIVING's `COFFEE_TABLE` is checked against the room's door-swing
obstacles only, never against the `SOFA`'s own clearance rectangle it is deliberately placed INSIDE
(`_place_coffee_table`) — that clearance zone IS the seating/conversation area a coffee table
belongs in. Physical FOOTPRINTS (`rect_m`) never overlap regardless; only the two CLEARANCE
rectangles are allowed to, and only for this one pair.

Roles outside the Issue's explicit list (FAMILY_ROOM, STUDY, DRESSING_ROOM, a SAFE_ROOM-only zone,
circulation, FLEX, ...) get no layout objects — additive, never a regression, and explicitly out of
scope (public-zone composition is Issue 11's).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon, box

from .design_output import DoorOut, GeometricDesign, RoomOut
from .geometry_core.model import WallType, WALL_THICKNESS_M

#: (x, y, w, h) in metres, plot-absolute — the same convention every other design_output type uses.
RectM = tuple[float, float, float, float]

_OVERLAP_TOL_M2 = 1e-4
_ARC_SEGMENTS = 12
_SIDES = ("N", "E", "S", "W")
_OPPOSITE_SIDE = {"N": "S", "S": "N", "E": "W", "W": "E"}
#: The open leaf's own convention (`doors.py::Door.swing_deg`) reused for a flush-mounted object's
#: own facing: which way it "looks" into the room. N=facing south/+y, S=facing north/-y, etc.
_ROTATION_DEG = {"N": 0.0, "S": 180.0, "W": 90.0, "E": 270.0}
_SIDE_OF_ROTATION = {v: k for k, v in _ROTATION_DEG.items()}


@dataclass(frozen=True)
class LayoutObject:
    """One placed semantic object. `rotation` is degrees, `_ROTATION_DEG`'s convention. Both rects
    are plot-absolute metres; `clearance_rect_m` always contains `rect_m` (it is the object's own
    footprint plus its required use clearance, never a disjoint zone)."""

    kind: str
    room_id: str
    rect_m: RectM
    rotation: float
    clearance_rect_m: RectM


@dataclass(frozen=True)
class UnplaceableItem:
    """Data, not a refusal (Issue #39 requirement 3) — an item this room's geometry could not fit,
    with a diagnosis, exactly like `FurnitureCheck.fits is False` already is for the C9 screen."""

    kind: str
    room_id: str
    reason: str


@dataclass(frozen=True)
class RoomLayout:
    room_id: str
    placed: tuple[LayoutObject, ...]
    unplaceable: tuple[UnplaceableItem, ...]


@dataclass(frozen=True)
class _ItemSpec:
    kind: str
    w_m: float          # along-wall (or, for a freestanding item, plan-x) footprint
    d_m: float           # perpendicular-to-wall (or plan-y) footprint
    front_clearance_m: float
    blocks_window: bool = False


# --------------------------------------------------------------------------- geometry helpers

def _net_origin_m(room: RoomOut) -> tuple[float, float]:
    """The room's net rectangle's own (x, y) — `RoomOut` only carries net WIDTH/HEIGHT (`net_w_m`/
    `net_h_m`), never the origin, since nothing needed it before this Issue."""
    x, y, _, _ = room.rect_m
    inset_w = WALL_THICKNESS_M[WallType(room.walls["W"])] / 2
    inset_n = WALL_THICKNESS_M[WallType(room.walls["N"])] / 2
    return x + inset_w, y + inset_n


def _wall_length_m(side: str, nw: float, nh: float) -> float:
    return nw if side in ("N", "S") else nh


def _perp_available_m(side: str, nw: float, nh: float) -> float:
    return nh if side in ("N", "S") else nw


def _frame_rect(side: str, nx: float, ny: float, nw: float, nh: float,
                u: float, v: float, along: float, depth: float) -> RectM:
    """A rectangle `along` long (parallel to `side`, starting at offset `u` from that side's own
    start corner) and `depth` deep (perpendicular, starting `v` from the wall), in plot-absolute
    metres. `v=0` sits flush against the wall — the invariant every furniture placement below
    relies on to avoid ever overlapping it."""
    if side == "N":
        return (nx + u, ny + v, along, depth)
    if side == "S":
        return (nx + u, ny + nh - v - depth, along, depth)
    if side == "W":
        return (nx + v, ny + u, depth, along)
    return (nx + nw - v - depth, ny + u, depth, along)  # E


def _poly(rect: RectM) -> Polygon:
    x, y, w, h = rect
    return box(x, y, x + w, y + h)


def _gross_sides(room: RoomOut) -> dict[str, tuple[str, float]]:
    x, y, w, h = room.rect_m
    return {"N": ("horizontal", y), "S": ("horizontal", y + h),
            "W": ("vertical", x), "E": ("vertical", x + w)}


def _door_sides(room: RoomOut, design: GeometricDesign) -> set[str]:
    """Every wall side of `room` that carries a door — either direction, so furniture is never set
    against a doorway even on the side the leaf does not swing into."""
    sides = _gross_sides(room)
    all_doors = (*design.interior_doors, design.entrance_door)
    found: set[str] = set()
    for side, (orientation, coord) in sides.items():
        for d in all_doors:
            if d.width_m <= 0 or d.orientation != orientation:
                continue
            if not (d.a == room.zone_id or d.b == room.zone_id):
                continue
            other_coord = d.center_m[1] if orientation == "horizontal" else d.center_m[0]
            if abs(other_coord - coord) < 1e-6:
                found.add(side)
    return found


def _window_sides(room: RoomOut, design: GeometricDesign) -> set[str]:
    return {w.side for w in design.windows if w.zone_id == room.zone_id and w.placeable}


def _wall_dir_deg(door: DoorOut) -> float:
    """The CLOSED leaf's own direction from its hinge — see `door_clearance._wall_dir_deg`, the
    grid-unit twin of this function."""
    hx, hy = door.hinge_m
    cx, cy = door.center_m
    if door.orientation == "horizontal":
        far_x = 2 * cx - hx
        return 0.0 if far_x > hx else 180.0
    far_y = 2 * cy - hy
    return 90.0 if far_y > hy else 270.0


def _swing_envelope(door: DoorOut) -> Polygon:
    """The leaf's own swept quarter-circle, in metres — `door_clearance.swing_envelope_m`'s twin,
    off `DoorOut` fields directly (see module docstring)."""
    hinge = door.hinge_m
    start_deg = _wall_dir_deg(door)
    diff = (door.swing_deg - start_deg) % 360
    if diff > 180:
        diff -= 360
    points = [hinge]
    for i in range(_ARC_SEGMENTS + 1):
        theta = math.radians(start_deg + diff * i / _ARC_SEGMENTS)
        points.append((hinge[0] + door.width_m * math.cos(theta),
                       hinge[1] + door.width_m * math.sin(theta)))
    return Polygon(points)


def _swing_obstacles(room: RoomOut, design: GeometricDesign) -> list[Polygon]:
    all_doors = (*design.interior_doors, design.entrance_door)
    return [_swing_envelope(d) for d in all_doors
            if d.width_m > 0 and d.swings_into == room.zone_id]


def _overlaps_any(poly: Polygon, obstacles: list[Polygon]) -> bool:
    return any(poly.intersection(o).area > _OVERLAP_TOL_M2 for o in obstacles)


# --------------------------------------------------------------------------- wall-anchored placement

@dataclass(frozen=True)
class _Placement:
    obj: LayoutObject
    side: str
    u: float


def _place_item(room: RoomOut, occupied: list[Polygon], item: _ItemSpec,
                door_sides: set[str], window_sides: set[str],
                only_side: str | None = None) -> tuple[_Placement | None, str | None]:
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    if only_side is not None:
        candidates = [] if only_side in door_sides else [only_side]
    else:
        candidates = [s for s in _SIDES if s not in door_sides]
        if item.blocks_window:
            no_window = [s for s in candidates if s not in window_sides]
            if no_window:
                candidates = no_window
        candidates = sorted(candidates, key=lambda s: (-_wall_length_m(s, nw, nh), _SIDES.index(s)))

    for side in candidates:
        wall_len = _wall_length_m(side, nw, nh)
        perp = _perp_available_m(side, nw, nh)
        if item.w_m > wall_len + 1e-6 or item.d_m > perp + 1e-6:
            continue
        u = (wall_len - item.w_m) / 2
        rect = _frame_rect(side, nx, ny, nw, nh, u, 0.0, item.w_m, item.d_m)
        clearance_depth = min(item.d_m + item.front_clearance_m, perp)
        clearance = _frame_rect(side, nx, ny, nw, nh, u, 0.0, item.w_m, clearance_depth)
        if _overlaps_any(_poly(clearance), occupied):
            continue
        obj = LayoutObject(item.kind, room.zone_id, rect, _ROTATION_DEG[side], clearance)
        return _Placement(obj, side, u), None

    return None, (f"no wall in {room.zone_id} clears {item.kind} "
                  f"({item.w_m:.2f}x{item.d_m:.2f} m + {item.front_clearance_m:.2f} m clearance) "
                  f"of a door, a window or another object")


def _place_sequential(room: RoomOut, occupied: list[Polygon], items: tuple[_ItemSpec, ...],
                      door_sides: set[str], window_sides: set[str],
                      ) -> tuple[list[LayoutObject], list[UnplaceableItem]]:
    placed: list[LayoutObject] = []
    unplaceable: list[UnplaceableItem] = []
    local = list(occupied)
    for item in items:
        placement, reason = _place_item(room, local, item, door_sides, window_sides)
        if placement is None:
            unplaceable.append(UnplaceableItem(item.kind, room.zone_id, reason or ""))
            continue
        placed.append(placement.obj)
        local.append(_poly(placement.obj.clearance_rect_m))
    return placed, unplaceable


def _place_freestanding(room: RoomOut, occupied: list[Polygon],
                        item: _ItemSpec) -> tuple[LayoutObject | None, str | None]:
    """Centred in the room's net rectangle — a table is not wall-anchored; its clearance is the
    footprint plus `front_clearance_m` on every side (the chair pull-out margin)."""
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    total_w = item.w_m + 2 * item.front_clearance_m
    total_h = item.d_m + 2 * item.front_clearance_m
    if total_w > nw + 1e-6 or total_h > nh + 1e-6:
        return None, (f"{room.zone_id} net {nw:.2f}x{nh:.2f} m cannot inscribe {item.kind} plus "
                      f"its {item.front_clearance_m:.2f} m clearance on every side")
    rect = (nx + (nw - item.w_m) / 2, ny + (nh - item.d_m) / 2, item.w_m, item.d_m)
    clearance = (nx + (nw - total_w) / 2, ny + (nh - total_h) / 2, total_w, total_h)
    if _overlaps_any(_poly(clearance), occupied):
        return None, f"{item.kind} placement in {room.zone_id} is obstructed by a door swing"
    return LayoutObject(item.kind, room.zone_id, rect, 0.0, clearance), None


# --------------------------------------------------------------------------- BEDROOM / MASTER_BEDROOM

_BED_WARDROBE = {
    "BEDROOM": (_ItemSpec("BED", 1.4, 2.0, 0.7), _ItemSpec("WARDROBE", 1.2, 0.6, 0.6, blocks_window=True)),
    "MASTER_BEDROOM": (_ItemSpec("BED", 1.8, 2.0, 0.7),
                       _ItemSpec("WARDROBE", 1.8, 0.6, 0.6, blocks_window=True)),
}


# --------------------------------------------------------------------------- LIVING

_SOFA = _ItemSpec("SOFA", 2.0, 0.9, 0.9)
_COFFEE_TABLE = _ItemSpec("COFFEE_TABLE", 1.0, 0.5, 0.0)
_COFFEE_GAP_M = 0.35
_FOCAL_WALL_DEPTH_M = 0.05
_FOCAL_WALL_MAX_LEN_M = 2.0


def _place_coffee_table(room: RoomOut, sofa: _Placement,
                        occupied: list[Polygon]) -> tuple[LayoutObject | None, str | None]:
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    side = sofa.side
    perp = _perp_available_m(side, nw, nh)
    v = _SOFA.d_m + _COFFEE_GAP_M
    if v + _COFFEE_TABLE.d_m > perp + 1e-6:
        return None, f"no room in front of the sofa in {room.zone_id} for a coffee table"
    u = sofa.u + (_SOFA.w_m - _COFFEE_TABLE.w_m) / 2
    rect = _frame_rect(side, nx, ny, nw, nh, u, v, _COFFEE_TABLE.w_m, _COFFEE_TABLE.d_m)
    if _overlaps_any(_poly(rect), occupied):
        return None, f"coffee table position in {room.zone_id} is obstructed"
    return LayoutObject("COFFEE_TABLE", room.zone_id, rect, _ROTATION_DEG[side], rect), None


def _place_focal_wall(room: RoomOut, sofa_side: str, door_sides: set[str],
                      occupied: list[Polygon]) -> tuple[LayoutObject | None, str | None]:
    """A thin marker along the wall OPPOSITE the sofa — where a television/fireplace reads on the
    plan. Not real furniture footprint (`_FOCAL_WALL_DEPTH_M` is a symbol, not a fixture)."""
    side = _OPPOSITE_SIDE[sofa_side]
    if side in door_sides:
        return None, f"the wall opposite the sofa in {room.zone_id} carries a door"
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    wall_len = _wall_length_m(side, nw, nh)
    length = min(_FOCAL_WALL_MAX_LEN_M, wall_len)
    u = (wall_len - length) / 2
    rect = _frame_rect(side, nx, ny, nw, nh, u, 0.0, length, _FOCAL_WALL_DEPTH_M)
    if _overlaps_any(_poly(rect), occupied):
        return None, f"the wall opposite the sofa in {room.zone_id} is obstructed"
    return LayoutObject("FOCAL_WALL", room.zone_id, rect, _ROTATION_DEG[side], rect), None


def _place_living(room: RoomOut, occupied: list[Polygon], door_sides: set[str],
                  window_sides: set[str]) -> tuple[list[LayoutObject], list[UnplaceableItem]]:
    placement, reason = _place_item(room, occupied, _SOFA, door_sides, window_sides)
    if placement is None:
        return [], [
            UnplaceableItem("SOFA", room.zone_id, reason or ""),
            UnplaceableItem("COFFEE_TABLE", room.zone_id, "no sofa placed to anchor it"),
            UnplaceableItem("FOCAL_WALL", room.zone_id, "no sofa placed to face it"),
        ]
    placed = [placement.obj]
    # The coffee table sits WITHIN the sofa's own clearance zone by design (that zone IS the
    # conversation/seating area a coffee table belongs in) — so it is checked only against the
    # SWING obstacles, never against the sofa's own clearance rectangle it necessarily overlaps.
    unplaceable: list[UnplaceableItem] = []
    table, table_reason = _place_coffee_table(room, placement, list(occupied))
    local = [*occupied, _poly(placement.obj.clearance_rect_m)]
    if table is not None:
        placed.append(table)
        local.append(_poly(table.rect_m))
    else:
        unplaceable.append(UnplaceableItem("COFFEE_TABLE", room.zone_id, table_reason or ""))

    focal, focal_reason = _place_focal_wall(room, placement.side, door_sides, local)
    if focal is not None:
        placed.append(focal)
    else:
        unplaceable.append(UnplaceableItem("FOCAL_WALL", room.zone_id, focal_reason or ""))

    return placed, unplaceable


# --------------------------------------------------------------------------- DINING

_DINING_TABLE = _ItemSpec("DINING_TABLE", 1.2, 0.8, 0.6)


# --------------------------------------------------------------------------- KITCHEN

#: Adjacent, non-overlapping segments laid end to end along one wall — `None` width is a plain
#: counter run, sized from whatever length remains. Minimum total (2.4 m) matches
#: `geometry_core.model.MIN_FURNITURE_ENVELOPE_M[KITCHEN]`'s own (2.4, 1.8) screen exactly, so a
#: kitchen that already passes C9 always has enough WALL LENGTH for this run too.
_KITCHEN_SEGMENTS: tuple[tuple[str, float | None], ...] = (
    ("REFRIGERATOR", 0.6), ("COUNTER_RUN", None), ("SINK", 0.6),
    ("COUNTER_RUN", None), ("COOKTOP", 0.6),
)
_KITCHEN_DEPTH_M = 0.6
_KITCHEN_CLEARANCE_M = 1.2
_KITCHEN_MIN_RUN_M = 0.3
_ISLAND_ITEM = _ItemSpec("ISLAND", 1.2, 0.6, 0.9)


def _place_kitchen(room: RoomOut, occupied: list[Polygon],
                   door_sides: set[str]) -> tuple[list[LayoutObject], list[UnplaceableItem]]:
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    fixed = sum(w for _, w in _KITCHEN_SEGMENTS if w is not None)
    n_runs = sum(1 for _, w in _KITCHEN_SEGMENTS if w is None)
    min_total = fixed + n_runs * _KITCHEN_MIN_RUN_M
    candidates = sorted((s for s in _SIDES if s not in door_sides),
                        key=lambda s: (-_wall_length_m(s, nw, nh), _SIDES.index(s)))

    for side in candidates:
        wall_len = _wall_length_m(side, nw, nh)
        perp = _perp_available_m(side, nw, nh)
        if min_total > wall_len + 1e-6 or _KITCHEN_DEPTH_M + _KITCHEN_CLEARANCE_M > perp + 1e-6:
            continue
        run_w = (wall_len - fixed) / n_runs
        clearance_depth = min(_KITCHEN_DEPTH_M + _KITCHEN_CLEARANCE_M, perp)
        segments: list[LayoutObject] = []
        u = 0.0
        ok = True
        for kind, width_m in _KITCHEN_SEGMENTS:
            width = width_m if width_m is not None else run_w
            rect = _frame_rect(side, nx, ny, nw, nh, u, 0.0, width, _KITCHEN_DEPTH_M)
            clearance = _frame_rect(side, nx, ny, nw, nh, u, 0.0, width, clearance_depth)
            if _overlaps_any(_poly(clearance), occupied):
                ok = False
                break
            segments.append(LayoutObject(kind, room.zone_id, rect, _ROTATION_DEG[side], clearance))
            u += width
        if ok:
            return segments, []

    reason = (f"no wall in {room.zone_id} fits the kitchen counter run "
             f"(needs >= {min_total:.2f} m of wall clear of doors and other objects)")
    return [], [UnplaceableItem(kind, room.zone_id, reason) for kind, _ in _KITCHEN_SEGMENTS]


def _maybe_place_island(room: RoomOut, kitchen_objs: list[LayoutObject], occupied: list[Polygon],
                        door_sides: set[str]) -> LayoutObject | None:
    """Only when the room is genuinely deep enough to leave the counter's own working clearance
    AND the island's own clearance free at once — "only when ... appropriate" (Issue #39); this
    engine has no "island requested" input to honour, so appropriateness is the only signal."""
    if not kitchen_objs:
        return None
    counter_side = _SIDE_OF_ROTATION[kitchen_objs[0].rotation]
    nw, nh = room.net_w_m, room.net_h_m
    perp = _perp_available_m(counter_side, nw, nh)
    needed = _KITCHEN_DEPTH_M + _KITCHEN_CLEARANCE_M + _ISLAND_ITEM.d_m + _ISLAND_ITEM.front_clearance_m
    if needed > perp + 1e-6:
        return None
    opposite = _OPPOSITE_SIDE[counter_side]
    placement, _reason = _place_item(room, occupied, _ISLAND_ITEM, door_sides, window_sides=set(),
                                     only_side=opposite)
    return placement.obj if placement is not None else None


# --------------------------------------------------------------------------- BATHROOM / TOILET

_TOILET_PAN = _ItemSpec("TOILET", 0.4, 0.6, 0.55)
_BATH_SINK = _ItemSpec("SINK", 0.5, 0.4, 0.5)
_SHOWER = _ItemSpec("SHOWER", 0.9, 0.9, 0.6)


def _place_bathroom(room: RoomOut, occupied: list[Polygon], include_shower: bool,
                    door_sides: set[str]) -> tuple[list[LayoutObject], list[UnplaceableItem]]:
    items = (_TOILET_PAN, _BATH_SINK, _SHOWER) if include_shower else (_TOILET_PAN, _BATH_SINK)
    return _place_sequential(room, occupied, items, door_sides, window_sides=set())


# --------------------------------------------------------------------------- dispatch

def layout_for_room(room: RoomOut, design: GeometricDesign) -> RoomLayout:
    role = room.roles[0] if room.roles else None
    door_sides = _door_sides(room, design)
    window_sides = _window_sides(room, design)
    occupied = _swing_obstacles(room, design)

    if role in _BED_WARDROBE:
        placed, unplaceable = _place_sequential(room, occupied, _BED_WARDROBE[role],
                                                 door_sides, window_sides)
    elif role == "LIVING":
        placed, unplaceable = _place_living(room, occupied, door_sides, window_sides)
    elif role == "DINING":
        obj, reason = _place_freestanding(room, occupied, _DINING_TABLE)
        placed = [obj] if obj is not None else []
        unplaceable = [] if obj is not None else [UnplaceableItem("DINING_TABLE", room.zone_id, reason or "")]
    elif role == "KITCHEN":
        placed, unplaceable = _place_kitchen(room, occupied, door_sides)
        island = _maybe_place_island(
            room, placed, [*occupied, *(_poly(o.clearance_rect_m) for o in placed)], door_sides)
        if island is not None:
            placed = [*placed, island]
    elif role in ("BATHROOM", "TOILET"):
        placed, unplaceable = _place_bathroom(room, occupied, role == "BATHROOM", door_sides)
    else:
        placed, unplaceable = [], []

    return RoomLayout(room.zone_id, tuple(placed), tuple(unplaceable))


def compute_layout(design: GeometricDesign) -> tuple[RoomLayout, ...]:
    """One `RoomLayout` per room in `design`, in room order. Pure and side-effect-free — never
    raises; every failure a room's geometry produces is data on that `RoomLayout.unplaceable`."""
    return tuple(layout_for_room(room, design) for room in design.rooms)
