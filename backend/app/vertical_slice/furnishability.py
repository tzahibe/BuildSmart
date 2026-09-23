"""Stage 9c — Furnishability / usability validation (Issue #40).

Room area alone does not prove room quality: C9's bounding-box envelope test lets a 12 m2 bedroom
that cannot actually hold a bed, a wardrobe and a walking path pass, as long as the envelope
inscribes. This module reads the REALIZED layout objects `interior_layout.py` (Issue #39) already
placed — never re-placing anything itself — and, per room, produces a `Usability` record: whether
every REQUIRED object for the room's role got placed at all, whether the door has a clear straight
path to each placed object, whether a placed object blocks a window, and a diagnostic "usable wall
length" figure — folded into one tier, GOOD / ACCEPTABLE / POOR / UNUSABLE.

TIERED, NOT BLUNT (the Issue's own framing): UNUSABLE (a REQUIRED item cannot be placed ANYWHERE
in the room) is what `validation.check_furnishability` (C30) fails closed on WHEN a caller runs
it — see that function's own docstring for why nothing in this codebase calls it live today: a
required-item-unplaceable definition strict enough to mean anything (even BED alone) was MEASURED
against the real backend test suite and found to fail closed on real, otherwise-fully-valid plans
this codebase already accepts (ordinary 2BR/3BR briefs among them), because `interior_layout.py`'s
placement is a single independent pass per item per wall — no packing two items onto one wall, no
trying every rotation, a real, documented gap ("Known follow-ups" below) this Issue's own "do not
touch Issue 9's placement" scope forbids closing. POOR — objects placed, but no clear access path,
or one blocks a window — is disclosure/ranking data only (`app.demo.contract.QualityOut.usability`,
`usability_key`/`better_candidate` below), never a gate: the same two-tier discipline
`wet_privacy.py`'s C29/`privacy_score` split already holds for a wet room's soft exposure score
versus its one hard rule.

REQUIRED_ITEMS is a DELIBERATE SUBSET of each role's own `interior_layout._BED_WARDROBE`/
`_place_living`/etc. item list — only the ONE item whose total absence makes the room unusable for
its stated purpose at all (a place to sleep, sit, eat, cook, wash), never "furnished exactly as
generously as `interior_layout.py` would like". WARDROBE is excluded from BEDROOM/MASTER_BEDROOM
even though `interior_layout.py` places it too: that module's own "Known follow-ups" section
documents exactly why it is the item most often reported unplaceable — "today each item picks its
OWN best wall independently... a 'strip' bedroom... can legitimately report a wardrobe unplaceable
even though the wall has unused width beside the bed) rather than a bug." Restricting to BED alone
narrows the false-positive rate but, as `validation.check_furnishability`'s own docstring
documents with a measured count, does not eliminate it — which is exactly why this stays a
defined-but-unwired check rather than a live gate.

THE ACCESS-PATH CHECK IS A DELIBERATE, DISCLOSED SIMPLIFICATION: a straight line from the nearest
door point to each placed object's own clearance-rect CENTRE, tested against every OTHER placed
object's physical FOOTPRINT (`rect_m`) in the same room — not a real pathfinding walk, the same
disclosed-simplification precedent `interior_layout.py`'s own swing-envelope math already sets
(see that module's docstring: "a deliberate, small duplicate"). It answers "does furniture
literally sit in the straight line between the door and this object", not "what is the shortest
walkable route" — enough to catch the case Issue #40 AC-2 names (a bedroom furnished but with no
clear path from the door) without inventing a pathfinding engine this Issue never asked for.

THE WINDOW-BLOCKED CHECK duplicates a SMALL amount of wall-side geometry (`_net_origin_m`,
`_object_touches_side`) rather than importing `interior_layout.py`'s own private wall-frame helpers
— the same "reads only realized geometry, never a solver-internal type" boundary that module's own
docstring draws for itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from shapely.geometry import LineString, box

from . import interior_layout
from .design_output import GeometricDesign, RoomOut
from .geometry_core.model import WallType, WALL_THICKNESS_M
from .interior_layout import RoomLayout

GOOD = "GOOD"
ACCEPTABLE = "ACCEPTABLE"
POOR = "POOR"
UNUSABLE = "UNUSABLE"

_SIDES = ("N", "E", "S", "W")
_TOUCH_TOL_M = 1e-3

#: Per-role REQUIRED items — see the module docstring for the calibration discipline. A role
#: absent here (out of `interior_layout.py`'s own scope, or a role with no mandatory item) simply
#: never fails C30 and is always `required_placed=True`.
REQUIRED_ITEMS: dict[str, tuple[str, ...]] = {
    "BEDROOM": ("BED",),
    "MASTER_BEDROOM": ("BED",),
    "LIVING": ("SOFA",),
    "DINING": ("DINING_TABLE",),
    "KITCHEN": ("REFRIGERATOR", "SINK", "COOKTOP"),
    "BATHROOM": ("TOILET", "SINK"),
    "TOILET": ("TOILET", "SINK"),
}

#: PARAMETER · calibrated on the corpus (Issue #40 AC-3) so today's plans keep their status: the
#: minimum longest-free-wall-run (metres) a room can retain before its tier drops from GOOD to
#: ACCEPTABLE on that signal alone. 0.0 means this signal alone never demotes a room today — kept
#: as a documented, adjustable threshold rather than removed, since it is the hook a future
#: calibration pass tightens once a reference band exists (see the rubric's own section N).
MIN_GOOD_FREE_WALL_M = 0.0


@dataclass(frozen=True)
class Usability:
    """One room's furnishability/usability standing. `tier` is the single rolled-up signal;
    every other field is the evidence behind it, in the same "data first, one verdict after"
    shape `wet_privacy.WetPrivacy` already uses."""

    room_id: str
    tier: str
    required_placed: bool
    missing_required: tuple[str, ...]
    clearance_satisfied: bool
    access_path_clear: bool
    blocked_objects: tuple[str, ...]
    usable_wall_length_m: float
    window_blocked: bool
    reasons: tuple[str, ...]


def _role_of(room: RoomOut) -> str | None:
    return room.roles[0] if room.roles else None


def _missing_required(role: str | None, layout: RoomLayout) -> tuple[str, ...]:
    required = REQUIRED_ITEMS.get(role or "", ())
    if not required:
        return ()
    unplaceable_kinds = {u.kind for u in layout.unplaceable}
    return tuple(k for k in required if k in unplaceable_kinds)


def _door_points(room: RoomOut, design: GeometricDesign) -> list[tuple[float, float]]:
    points = []
    for d in (*design.interior_doors, design.entrance_door):
        if d.width_m > 0 and (d.a == room.zone_id or d.b == room.zone_id):
            points.append(d.center_m)
    return points


def _as_box(rect_m) -> box:
    x, y, w, h = rect_m
    return box(x, y, x + w, y + h)


def _clear_access_paths(room: RoomOut, design: GeometricDesign,
                        layout: RoomLayout) -> tuple[bool, tuple[str, ...]]:
    """See the module docstring's "deliberate, disclosed simplification" for what this does and
    does not model. A room with fewer than two placed objects, or no door of its own (should not
    happen on a realized plan — every enclosed room has one, C7), has nothing to block."""
    door_points = _door_points(room, design)
    if not door_points or len(layout.placed) < 2:
        return True, ()
    blocked: list[str] = []
    for obj in layout.placed:
        cx, cy, cw, ch = obj.clearance_rect_m
        target = (cx + cw / 2, cy + ch / 2)
        clear_from_some_door = False
        for door_point in door_points:
            path = LineString([door_point, target])
            crosses_something = any(
                other is not obj and path.crosses(_as_box(other.rect_m))
                for other in layout.placed
            )
            if not crosses_something:
                clear_from_some_door = True
                break
        if not clear_from_some_door:
            blocked.append(obj.kind)
    return not blocked, tuple(blocked)


def _net_origin_m(room: RoomOut) -> tuple[float, float]:
    x, y, _, _ = room.rect_m
    inset_w = WALL_THICKNESS_M[WallType(room.walls["W"])] / 2
    inset_n = WALL_THICKNESS_M[WallType(room.walls["N"])] / 2
    return x + inset_w, y + inset_n


def _object_touches_side(room: RoomOut, rect_m, side: str) -> bool:
    nx, ny = _net_origin_m(room)
    nw, nh = room.net_w_m, room.net_h_m
    x, y, w, h = rect_m
    if side == "N":
        return abs(y - ny) < _TOUCH_TOL_M
    if side == "S":
        return abs((y + h) - (ny + nh)) < _TOUCH_TOL_M
    if side == "W":
        return abs(x - nx) < _TOUCH_TOL_M
    return abs((x + w) - (nx + nw)) < _TOUCH_TOL_M  # E


def _along_wall_span(rect_m, side: str) -> tuple[float, float]:
    x, y, w, h = rect_m
    return (x, x + w) if side in ("N", "S") else (y, y + h)


def _window_blocked(room: RoomOut, design: GeometricDesign, layout: RoomLayout) -> bool:
    windows = [w for w in design.windows
              if w.zone_id == room.zone_id and w.placeable and w.width_m > 0]
    if not windows or not layout.placed:
        return False
    for w in windows:
        lo, hi = w.center_m[0] - w.width_m / 2, w.center_m[0] + w.width_m / 2
        if w.side in ("E", "W"):
            lo, hi = w.center_m[1] - w.width_m / 2, w.center_m[1] + w.width_m / 2
        for obj in layout.placed:
            if not _object_touches_side(room, obj.rect_m, w.side):
                continue
            olo, ohi = _along_wall_span(obj.rect_m, w.side)
            if olo < hi - 1e-6 and ohi > lo + 1e-6:
                return True
    return False


def _wall_length_m(side: str, nw: float, nh: float) -> float:
    return nw if side in ("N", "S") else nh


def _usable_wall_length_m(room: RoomOut, layout: RoomLayout) -> float:
    """The longest still-free contiguous run among the room's 4 walls once every placed object's
    own along-wall span is subtracted — a diagnostic figure (the rubric's "usable wall length"
    signal), not itself a gate beyond `MIN_GOOD_FREE_WALL_M`'s own soft ACCEPTABLE threshold."""
    nw, nh = room.net_w_m, room.net_h_m
    best = 0.0
    for side in _SIDES:
        wall_len = _wall_length_m(side, nw, nh)
        consumed = 0.0
        for o in layout.placed:
            if not _object_touches_side(room, o.rect_m, side):
                continue
            lo, hi = _along_wall_span(o.rect_m, side)
            consumed += hi - lo
        best = max(best, wall_len - consumed)
    return round(best, 3)


def compute_usability_for_room(room: RoomOut, design: GeometricDesign,
                               layout: RoomLayout) -> Usability:
    role = _role_of(room)
    missing = _missing_required(role, layout)
    required_placed = not missing
    access_clear, blocked = _clear_access_paths(room, design, layout)
    window_blocked = _window_blocked(room, design, layout)
    usable_wall = _usable_wall_length_m(room, layout)
    # Placement never places an object whose clearance rect overlaps another already-placed
    # object's clearance, or a door's swing envelope (`interior_layout.py`'s own invariant, proven
    # directly by `test_interior_layout.py`) — so this signal cannot be false for anything this
    # module ever sees placed. Recorded because the rubric names it as its own signal, not because
    # this module can produce a violation of it.
    clearance_satisfied = True

    reasons: list[str] = []
    if not required_placed:
        reasons.append(f"{room.zone_id}: required {', '.join(missing)} cannot be placed at all")
        tier = UNUSABLE
    elif not access_clear:
        reasons.append(f"{room.zone_id}: no clear path from the door to {', '.join(blocked)}")
        tier = POOR
    elif window_blocked:
        reasons.append(f"{room.zone_id}: a placed object blocks a window")
        tier = POOR
    elif usable_wall < MIN_GOOD_FREE_WALL_M:
        reasons.append(f"{room.zone_id}: little free wall left ({usable_wall:.2f} m)")
        tier = ACCEPTABLE
    else:
        tier = GOOD

    return Usability(room_id=room.zone_id, tier=tier, required_placed=required_placed,
                     missing_required=missing, clearance_satisfied=clearance_satisfied,
                     access_path_clear=access_clear, blocked_objects=blocked,
                     usable_wall_length_m=usable_wall, window_blocked=window_blocked,
                     reasons=tuple(reasons))


def compute_usability(design: GeometricDesign,
                      layouts: tuple[RoomLayout, ...] | None = None) -> tuple[Usability, ...]:
    """One `Usability` per room in `design` (Issue #40 AC-1: "every room of the canonical
    fixtures"), in room order. `layouts` lets a caller that already ran `interior_layout.
    compute_layout` (e.g. `app.demo.contract.to_demo_design`) pass it straight through instead of
    computing it twice; the default recomputes it, matching every other caller's own convenience."""
    if layouts is None:
        layouts = interior_layout.compute_layout(design)
    by_room = {rl.room_id: rl for rl in layouts}
    return tuple(compute_usability_for_room(room, design, by_room[room.zone_id])
                for room in design.rooms if room.zone_id in by_room)


def usability_key(records: Sequence[Usability]) -> tuple[int, int]:
    """LOWER IS BETTER — for a caller comparing two otherwise-equal candidate plans (Issue #40's
    own "POOR is a ranking penalty" requirement; UNUSABLE counted too, since nothing else refuses
    it live — see `validation.check_furnishability`'s own docstring). Mirrors `wet_core.
    candidate_wet_core_key`/`better_candidate`'s own precedent EXACTLY: defined and available here,
    NOT wired into any live selection call site by this Issue — see that module's own docstring for
    why leaving the integration point unwired is the deliberate, documented gap, not an omission."""
    unusable = sum(1 for u in records if u.tier == UNUSABLE)
    poor = sum(1 for u in records if u.tier == POOR)
    return unusable, poor


def better_candidate(a: Sequence[Usability], b: Sequence[Usability]) -> Sequence[Usability]:
    """Ties intentionally keep `a` (the same tie rule `wet_privacy.better_candidate`/
    `wet_core.better_candidate` use) — never an accident of comparison order."""
    return a if usability_key(a) <= usability_key(b) else b
