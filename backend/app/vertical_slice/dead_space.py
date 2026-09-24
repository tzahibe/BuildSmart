"""Dead-space / residual-pocket detection INSIDE zones (Issue #43).

C2 (`validation.py`) already guarantees zero residual area OUTSIDE rooms — every cell in the
footprint belongs to some zone, by construction. That says nothing about dead space INSIDE a
zone: a corridor that keeps going past the last door it serves, a room realized narrower than
any furniture could use, a corner a door's own swing makes impractical to reach, or a hall grown
well past what a transition node needs. Issue #22 (`entrance_sequence.py`, C25) already owns ONE
specific shape of this — the ARRIVAL zone's own pocket and a stray zone beside the entrance —
measured from the entrance door outward; this module is deliberately disjoint from that: every
region kind here is either scoped away from the entrance door's own reach (STUB only counts a
circulation room's end that C25's own reachability walk never serves) or is not a circulation
concept at all (SLIVER, CORNER, OVERSIZED_HALL).

Reads `app.vertical_slice.design_output.GeometricDesign` alone — the SAME realized-plan type
`circulation_metrics.py`/`entrance_sequence.py` already read (never the fixture, the concept tree,
or a solver internal) — so a check, a ranking decision and a report can never disagree about what
a plan's residual geometry looks like. Four region kinds, one per bullet of the Issue's own
"required behavior":

  * STUB — a HALL/CIRCULATION room's own END with neither a placeable door nor an open-plan join
    (mirrors `circulation_metrics._end_is_served`), measured as the AXIAL length from that end to
    the nearest opening's own position along the room's long axis (never merely "is there a dead
    end", which `circulation_metrics.dead_end_count` already reports as a boolean) — the corridor
    keeps going past the last room it actually serves.
  * SLIVER — a non-circulation room realized narrower, on its own short side, than any real
    furniture could use. `validation.check`'s C3 already holds every room to its own `ZoneSpec`
    minimum, so this never fires on a C3-compliant room in production; it exists for a future
    sizing path that relaxes its own spec, the same defence-in-depth discipline C20/C21 already
    apply to aspect/area.
  * CORNER — the small notch a door's own swing arc cuts out of the room corner nearest its hinge
    (a quarter-circle inscribed in a square leaves `side²(1 - π/4)` of the square unreachable while
    the leaf can still open) — a conservative, fixed-shape approximation off the door's own
    `hinge_m`/`swing_deg`/`width_m` (`design_output.DoorOut`, the engine's own decisions), the same
    disclosure discipline `door_clearance.py`'s wet-fixture footprint and `windows.py`'s glazing
    fractions use, not a full room-reachability solve.
  * OVERSIZED_HALL — a HALL/CIRCULATION room's own net area past
    `concept_generator.ROOM_TEMPLATES[HALL].hard_max` (30 m2 today) — C20/C21 deliberately exclude
    HALL from the aspect/area ceilings every other room is held to ("its width is what C14
    measures"), so nothing before this module reported a hall that simply grew past what any
    transition node needs. Only the EXCESS beyond the budget is dead space, not the whole room —
    the budget itself is a legitimate transition-node size, not zero.

    measure(design)             -> DeadSpaceMetrics   # one plan's own regions + totals
    classify_hard(metrics)      -> str | None          # C32's gate (validation.py)
    dead_space_prefers(a, b)    -> str | None           # the ranking term (not yet wired — see
                                                          # the module's own "Known follow-ups")
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.geometry_domain.walls import Construction

from .concept_generator import ROOM_TEMPLATES
from .design_output import DoorOut, GeometricDesign, RoomOut
from .geometry_core.model import ProgramRole

#: A room carrying either role is circulation — mirrors `circulation_metrics._CIRCULATION_ROLES`.
_CIRCULATION_ROLES = ("HALL", "CIRCULATION")

#: The 5 cm solver grid makes a door's centre and a room's own edge agree only to within a few
#: centimetres once metres are rounded twice — mirrors `circulation_metrics._DOOR_END_TOLERANCE_M`.
_DOOR_END_TOLERANCE_M = 0.15

#: Below this, a measured residual is solver-grid noise, not a real region — never reported.
_NOISE_FLOOR_M = 0.05

# --------------------------------------------------------------------------- PARAMETER constants

#: PARAMETER · calibrated on the full frozen 432-context regression corpus
#: (`scripts/dead_space_sweep.py`, `docs/DEAD_SPACE_SWEEP.md`): every one of the 394 PLANNED
#: contexts' own circulation dead ends measures 0.75-1.50 m past its last opening (mean 1.12 m — the
#: ordinary "hall's own width plus jamb clearance" shape `ENTRANCE_POCKET_MAX_M`'s own docstring
#: already documents for the POCKET measure, structurally capped at 1.50 m by this generator's own
#: template geometry today, not a coincidence across contexts). The Issue's own illustrative default
#: (1.5 m) sits EXACTLY at that ceiling — zero headroom, the same shape `ENTRANCE_POCKET_MAX_M`'s
#: own docstring warns 0.6 m didn't survive contact with real data. 2.0 m gives real headroom above
#: every measured PLANNED context while staying well below this module's own STUB test fixture (a
#: genuinely abandoned corridor, several metres long). C32 (`validation.py`) fails closed on this
#: alone among the four kinds this module measures — see that check's own comment for why the other
#: three stay reported, not gated.
DEAD_SPACE_STUB_HARD_LIMIT_M = 2.0

#: PARAMETER · every `ROOM_TEMPLATES` entry a SLIVER could apply to (HALL/CIRCULATION excluded, see
#: `_is_circulation`) carries its own `min_short_side_m` at 1.0 m or above (STORAGE, the narrowest);
#: C3 already holds every realized room to its own template's minimum, so this sits BELOW every one
#: of them on purpose — a SLIVER never fires on a C3-compliant room today, only on a fixture that
#: bypasses C3 entirely (a hand-built `GeometricDesign`) or a future sizing path that relaxes its
#: own spec, the same defence-in-depth discipline C20/C21 already apply.
SLIVER_MIN_USABLE_WIDTH_M = 0.9

#: The transition-node budget OVERSIZED_HALL measures against: `ROOM_TEMPLATES[HALL].hard_max` —
#: reused rather than a new constant, since it is already the calibrated ceiling this codebase
#: holds every other room's role to (C21) and HALL alone is excluded from. Read once, not
#: hand-copied, so a future change to that template moves this budget with it.
_HALL_AREA_BUDGET_M2 = ROOM_TEMPLATES[ProgramRole.HALL].hard_max

#: Two dead-space area/length numbers within this of each other are the same value for ranking
#: purposes — mirrors `circulation_metrics._EPS`.
_EPS = 0.02


def _is_circulation(roles: tuple[str, ...]) -> bool:
    return any(r in _CIRCULATION_ROLES for r in roles)


@dataclass(frozen=True)
class DeadSpaceRegion:
    """One residual region: its own size, shape, accessibility and ownership — the four facts the
    Issue's own "required behavior" names. `accessible` is whether a door opens directly ONTO this
    region (never merely "the room it sits in has some door elsewhere") — `False` for every kind
    but OVERSIZED_HALL, whose whole room is normally reachable, only oversized."""

    zone_id: str
    role: str
    kind: str  # "STUB" | "SLIVER" | "CORNER" | "OVERSIZED_HALL"
    area_m2: float
    #: Long/short of the region itself; `None` where the region has no meaningful long/short axis
    #: (CORNER's notch).
    aspect: float | None
    accessible: bool
    detail: str
    #: The STUB's own axial length in metres — `None` for every other kind. Carried alongside
    #: `area_m2`/`aspect` (rather than recomputed from them) because C32's own hard limit
    #: (`DEAD_SPACE_STUB_HARD_LIMIT_M`) is a LENGTH, not an area.
    length_m: float | None = None


@dataclass(frozen=True)
class DeadSpaceMetrics:
    """One realized plan's dead-space facts, read off `GeometricDesign` alone."""

    regions: tuple[DeadSpaceRegion, ...]
    dead_space_m2: float
    #: `dead_space_m2` / the plan's total room NET area — mirrors `circulation_metrics.ratio`.
    dead_space_share: float


def _rooms_by_id(design: GeometricDesign) -> dict[str, RoomOut]:
    return {r.zone_id: r for r in design.rooms}


def _door_touches_side(door: DoorOut, room: RoomOut, side: str) -> bool:
    if not door.placeable or room.zone_id not in (door.a, door.b):
        return False
    x, y, w, h = room.rect_m
    cx, cy = door.center_m
    if side == "W":
        return door.orientation == "vertical" and abs(cx - x) <= _DOOR_END_TOLERANCE_M
    if side == "E":
        return door.orientation == "vertical" and abs(cx - (x + w)) <= _DOOR_END_TOLERANCE_M
    if side == "N":
        return door.orientation == "horizontal" and abs(cy - y) <= _DOOR_END_TOLERANCE_M
    if side == "S":
        return door.orientation == "horizontal" and abs(cy - (y + h)) <= _DOOR_END_TOLERANCE_M
    return False


def _end_sides(room: RoomOut) -> tuple[str, str]:
    """The two sides at the ENDS of a room's own long (walking) axis — mirrors
    `circulation_metrics._end_sides`."""
    return ("W", "E") if room.net_w_m >= room.net_h_m else ("N", "S")


def _end_is_served(design: GeometricDesign, room: RoomOut, side: str) -> bool:
    """Mirrors `circulation_metrics._end_is_served` exactly: an open-plan join at this end, or a
    placeable door touching it, means nothing is stuck past this end."""
    facts = room.wall_facts.get(side)
    if facts is not None and facts.construction is Construction.NONE:
        return True
    doors = (*design.interior_doors, design.entrance_door)
    return any(_door_touches_side(d, room, side) for d in doors)


def _axis_index(room: RoomOut) -> int:
    """0 for the x-coordinate (a horizontal, W/E-ended room), 1 for y (a vertical, N/S-ended one)."""
    return 0 if room.net_w_m >= room.net_h_m else 1


def _opening_positions(design: GeometricDesign, room: RoomOut, axis: int) -> list[float]:
    """Every opening this room has (any placeable door touching it, or a fully open side's own
    midpoint), projected onto the room's own long axis — the positions `_stub_length_m` measures
    the room's own ends against."""
    x, y, w, h = room.rect_m
    positions: list[float] = []
    for door in (*design.interior_doors, design.entrance_door):
        if door.placeable and room.zone_id in (door.a, door.b):
            positions.append(door.center_m[axis])
    sides = {"W": (x, y + h / 2), "E": (x + w, y + h / 2),
             "N": (x + w / 2, y), "S": (x + w / 2, y + h)}
    for side, point in sides.items():
        facts = room.wall_facts.get(side)
        if facts is not None and facts.construction is Construction.NONE:
            positions.append(point[axis])
    return positions


def _stub_length_m(design: GeometricDesign, room: RoomOut, side: str) -> float:
    """How far this UNSERVED end sits from the room's own nearest opening, measured along the
    room's long axis. `math.inf` when the room has no opening at all (never expected in
    production — C24 already requires every enclosed room to have at least one door)."""
    axis = _axis_index(room)
    x, y, w, h = room.rect_m
    end_coord = {"W": x, "E": x + w, "N": y, "S": y + h}[side]
    positions = _opening_positions(design, room, axis)
    if not positions:
        return math.inf
    if side in ("W", "N"):
        return max(0.0, min(positions) - end_coord)
    return max(0.0, end_coord - max(positions))


def _stub_regions(design: GeometricDesign) -> list[DeadSpaceRegion]:
    regions = []
    for room in design.rooms:
        if not _is_circulation(room.roles):
            continue
        short = min(room.net_w_m, room.net_h_m)
        for side in _end_sides(room):
            if _end_is_served(design, room, side):
                continue
            length = _stub_length_m(design, room, side)
            if math.isinf(length) or length <= _NOISE_FLOOR_M:
                continue
            length = round(length, 4)
            area = round(length * short, 4)
            regions.append(DeadSpaceRegion(
                zone_id=room.zone_id, role=room.roles[0] if room.roles else "", kind="STUB",
                area_m2=area, aspect=round(length / short, 3) if short > 0 else None,
                accessible=False,
                detail=f"{length:.2f} m of {room.zone_id} past its last opening on the {side} end",
                length_m=length))
    return regions


def _sliver_regions(design: GeometricDesign) -> list[DeadSpaceRegion]:
    regions = []
    for room in design.rooms:
        if _is_circulation(room.roles):
            continue
        short = min(room.net_w_m, room.net_h_m)
        if short >= SLIVER_MIN_USABLE_WIDTH_M - 1e-9:
            continue
        long_ = max(room.net_w_m, room.net_h_m)
        regions.append(DeadSpaceRegion(
            zone_id=room.zone_id, role=room.roles[0] if room.roles else "", kind="SLIVER",
            area_m2=round(room.net_area_m2, 4),
            aspect=round(long_ / short, 3) if short > 0 else None,
            accessible=True,
            detail=f"{room.zone_id} net short side {short:.2f} m under the "
                   f"{SLIVER_MIN_USABLE_WIDTH_M:.2f} m usable-width floor"))
    return regions


def _corner_regions(design: GeometricDesign) -> list[DeadSpaceRegion]:
    """The small notch a door's own swing cuts from the room corner nearest its hinge — see the
    module docstring's CORNER bullet for the `side²(1 - π/4)` derivation. Only counted when the
    hinge itself sits within `_DOOR_END_TOLERANCE_M` of BOTH the room's own long and short walls at
    once (a hinge genuinely at a corner, not merely somewhere on a wall) — a narrow, rare condition
    by construction, so this virtually never fires on real generator output."""
    rooms = _rooms_by_id(design)
    regions = []
    notch = round((1.0 - math.pi / 4.0), 6)
    for door in (*design.interior_doors, design.entrance_door):
        if not door.placeable:
            continue
        for zone_id in (door.a, door.b):
            room = rooms.get(zone_id)
            if room is None:
                continue
            x, y, w, h = room.rect_m
            hx, hy = door.hinge_m
            near_x = min(abs(hx - x), abs(hx - (x + w))) <= _DOOR_END_TOLERANCE_M
            near_y = min(abs(hy - y), abs(hy - (y + h))) <= _DOOR_END_TOLERANCE_M
            if not (near_x and near_y):
                continue
            area = round(door.width_m ** 2 * notch, 4)
            if area <= _NOISE_FLOOR_M ** 2:
                continue
            regions.append(DeadSpaceRegion(
                zone_id=zone_id, role=room.roles[0] if room.roles else "", kind="CORNER",
                area_m2=area, aspect=None, accessible=False,
                detail=f"{area:.2f} m² notch behind the {door.a}-{door.b} door's swing in "
                       f"{zone_id}'s corner"))
    return regions


def _oversized_hall_regions(design: GeometricDesign) -> list[DeadSpaceRegion]:
    regions = []
    for room in design.rooms:
        if not _is_circulation(room.roles):
            continue
        excess = room.net_area_m2 - _HALL_AREA_BUDGET_M2
        if excess <= _NOISE_FLOOR_M:
            continue
        regions.append(DeadSpaceRegion(
            zone_id=room.zone_id, role=room.roles[0] if room.roles else "", kind="OVERSIZED_HALL",
            area_m2=round(excess, 4), aspect=None, accessible=True,
            detail=f"{room.zone_id} net {room.net_area_m2:.2f} m² exceeds the "
                   f"{_HALL_AREA_BUDGET_M2:.0f} m² transition-node budget by {excess:.2f} m²"))
    return regions


def measure(design: GeometricDesign) -> DeadSpaceMetrics:
    """Every dead-space fact this module measures, for one realized plan."""
    regions = (
        _stub_regions(design) + _sliver_regions(design)
        + _corner_regions(design) + _oversized_hall_regions(design)
    )
    total_area = sum(r.net_area_m2 for r in design.rooms)
    dead_space_m2 = round(sum(r.area_m2 for r in regions), 4)
    dead_space_share = dead_space_m2 / total_area if total_area else 0.0
    return DeadSpaceMetrics(regions=tuple(regions), dead_space_m2=dead_space_m2,
                            dead_space_share=dead_space_share)


# --------------------------------------------------------------------------- C32: the hard gate

def classify_hard(metrics: DeadSpaceMetrics) -> str | None:
    """`None` when C32 passes; otherwise every STUB region past `DEAD_SPACE_STUB_HARD_LIMIT_M`, so
    a refusal names the real cause. Only STUB gates — SLIVER/CORNER/OVERSIZED_HALL are measured and
    reported (`QualityOut.metrics`) but never fail a plan closed: a narrow room a future sizing
    path might produce is C3's own gate to fail on, a swing notch is normal architecture everywhere
    a door exists, and an oversized hall is a quality signal (`_HALL_AREA_BUDGET_M2`), not a
    correctness one."""
    reasons = [r.detail for r in metrics.regions
              if r.kind == "STUB" and r.length_m is not None
              and r.length_m > DEAD_SPACE_STUB_HARD_LIMIT_M + 1e-9]
    return "; ".join(reasons) if reasons else None


# --------------------------------------------------------------------------- the ranking term

def dead_space_prefers(current: DeadSpaceMetrics, candidate: DeadSpaceMetrics) -> str | None:
    """`None`: `candidate` has strictly less measured dead space than `current` and so earns it the
    comparison on this measure alone — mirrors `circulation_metrics.circulation_prefers`'s single-
    measure shape (no area floor: this is never the only signal a caller compares candidates on).

    NOT YET WIRED into `general_pipeline.run_general`'s candidate loop or `_guard_demoted_hub` —
    see the module's own "Known follow-ups": wiring a NEW active-path ranking term safely needs a
    full corpus sweep of its own to bound the primary-signature delta, the same discipline
    `entrance_sequence_prefers`/`circulation_prefers` were calibrated under before they were wired;
    that sweep is future work, not part of this Issue's verified scope. This function is exported
    and unit-tested on its own so that sweep can start from a proven-correct comparator.
    """
    if candidate.dead_space_m2 < current.dead_space_m2 - _EPS:
        return None
    return (f"candidate's dead space ({candidate.dead_space_m2:.2f} m²) is not less than the "
           f"current plan's ({current.dead_space_m2:.2f} m²)")
