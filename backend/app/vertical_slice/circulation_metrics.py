"""Dedicated-circulation metrics from REALIZED geometry (Issue #36).

`quality_metrics.py`'s M3 (`circulation_share`) and M4 (hall door count/aspect) already report a
plan's circulation SHARE and its own long/short ratio, but nothing measures a corridor's own
LENGTH, how many dead ends it has, how many turns a person walks through it, or whether two
segments duplicate each other — so nothing can tell "a long corridor" (common, and fine — the
spine parti's hall spans the full depth by construction, `concept_generator._concept_from`) apart
from "an EXTREME one" (uncommon, and a real defect: a corridor that is disproportionately long,
wide-and-long, or dead-ends repeatedly for no served room).

Everything here reads `app.vertical_slice.design_output.GeometricDesign` — the SAME realized-plan
type `hub_guard`/`l_massing_guard` compare on — never the fixture, the concept tree, or a solver
internal. A room's ROLE decides whether it is circulation (`ProgramRole.HALL`/`CIRCULATION`, read
off its already-resolved `.roles`, never a zone_id or a coordinate); everything else is measured
from `.rect_m`, `.wall_facts` and the door list. Pure and deterministic: the same design always
measures the same, and nothing here mutates or re-solves anything.

    measure(design)                    -> CirculationMetrics   # one plan's own facts
    classify_extreme(metrics)          -> str | None            # C26's gate (validation.py)
    circulation_prefers(a, b, ...)     -> str | None             # the ranking term (general_pipeline.py)

Two entry points read a `GeometricDesign` that was assembled purely to measure circulation (C26
runs before the pipeline's own `assemble()` call) as well as the pipeline's real one (the ranking
term, and `QualityOut.metrics`) — the SAME function either way, so a check and a report can never
disagree about what a plan's circulation looks like.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.geometry_domain.walls import Construction

from .design_output import DoorOut, GeometricDesign, RoomOut
from .hub_guard import AREA_KEEP_RATIO

#: A room carrying either role is circulation — mirrors `quality_metrics.HALL`, read off the
#: role tuple every room already carries (never a zone_id, so a fixture's own naming is never a
#: signal this module reads).
_CIRCULATION_ROLES = ("HALL", "CIRCULATION")

#: The 5 cm solver grid (`geometry_core.model.UNIT_M`) makes a door's centre and a room's own edge
#: agree only to within a few centimetres once metres are rounded twice (rect + door). A door
#: further from the end than this is genuinely mid-run (serving a room off the corridor's LENGTH,
#: not sitting at its END), not a rounding artefact.
_DOOR_END_TOLERANCE_M = 0.15

#: Two aspect/area numbers within this of each other are the same value for ranking purposes — the
#: same tolerance `hub_guard._ASPECT_EPS`/`l_massing_guard._SHARE_EPS` use for the same reason (the
#: 5 cm grid).
_EPS = 0.02


def _is_circulation(roles: tuple[str, ...]) -> bool:
    return any(r in _CIRCULATION_ROLES for r in roles)


def _long_short(room: RoomOut) -> tuple[float, float]:
    return (max(room.net_w_m, room.net_h_m), min(room.net_w_m, room.net_h_m))


@dataclass(frozen=True)
class CirculationMetrics:
    """One realized plan's dedicated-circulation facts, all read off `GeometricDesign` alone.

    `None` only where the plan genuinely has no circulation room to measure (`longest_segment_m`,
    `narrowest_width_m`) — the same "no metric where nothing of that kind exists" discipline
    `quality_metrics.QualityMetrics` uses.
    """

    #: Total NET area of every HALL/CIRCULATION room.
    area_m2: float
    #: `area_m2` / the plan's total room NET area — the same ratio M3 reports, computed
    #: independently here so this module never depends on `quality_metrics`'s own field names.
    ratio: float
    #: The longest circulation room's own long dimension (its walking length).
    longest_segment_m: float | None
    #: Every circulation room's long dimension, summed — one long spine sums to itself; a
    #: branching hub (HALL_MAIN + HALL_SPUR) sums both arms.
    total_length_m: float
    #: The narrowest circulation room's own short dimension — pairs with `longest_segment_m` to
    #: catch a corridor that is long AND narrow at once (the width x length extreme), not just long.
    narrowest_width_m: float | None
    #: Circulation-room ends (there are two per room, along its own long axis) with neither a
    #: placeable door nor an open-plan join at that end — space that leads nowhere.
    dead_end_count: int
    #: Direction changes along the realized entrance -> farthest-room path (BFS hop count, ties
    #: broken by the deterministic room-id order the graph is walked in).
    turn_count: int
    #: Pairs of circulation rooms that are NOT directly joined to each other (so not a branching
    #: hub's own arms) but serve an overlapping set of non-circulation rooms — two parallel
    #: corridors doing the same job.
    duplicated_segment_count: int
    #: The smaller room's area from every such pair, summed — what a duplicated segment costs.
    duplicated_area_m2: float


def _wall_facts_get(room: RoomOut, side: str):
    return room.wall_facts.get(side)


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
    """The two sides at the ENDS of a room's own long (walking) axis."""
    return ("W", "E") if room.net_w_m >= room.net_h_m else ("N", "S")


def _end_is_served(design: GeometricDesign, room: RoomOut, side: str) -> bool:
    facts = _wall_facts_get(room, side)
    if facts is not None and facts.construction is Construction.NONE:
        return True  # an open-plan join — the space continues past this end without a wall
    doors = (*design.interior_doors, design.entrance_door)
    return any(_door_touches_side(d, room, side) for d in doors)


def _dead_end_count(design: GeometricDesign, circulation: list[RoomOut]) -> int:
    return sum(
        1 for room in circulation for side in _end_sides(room)
        if not _end_is_served(design, room, side)
    )


def _adjacency(design: GeometricDesign) -> dict[str, set[str]]:
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


def _farthest_path(adjacency: dict[str, set[str]], start: str) -> list[str]:
    """BFS from `start`; the path to the LAST room reached at the greatest hop count — a
    deterministic farthest room, since every neighbour set is walked in sorted order."""
    dist = {start: 0}
    parent: dict[str, str | None] = {start: None}
    order = [start]
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in sorted(adjacency.get(current, ())):
            if nxt == "OUTSIDE" or nxt in dist:
                continue
            dist[nxt] = dist[current] + 1
            parent[nxt] = current
            order.append(nxt)
            queue.append(nxt)
    farthest = max(order, key=lambda z: dist[z])
    path = []
    node: str | None = farthest
    while node is not None:
        path.append(node)
        node = parent[node]
    return list(reversed(path))


def _turn_count(design: GeometricDesign, path: list[str]) -> int:
    if len(path) < 3:
        return 0
    rooms = {r.zone_id: r for r in design.rooms}
    centers = []
    for zone_id in path:
        room = rooms.get(zone_id)
        if room is None:
            continue
        x, y, w, h = room.rect_m
        centers.append((x + w / 2, y + h / 2))
    turns = 0
    axis = None
    for i in range(1, len(centers)):
        dx = centers[i][0] - centers[i - 1][0]
        dy = centers[i][1] - centers[i - 1][1]
        if dx == 0 and dy == 0:
            continue
        current_axis = "H" if abs(dx) >= abs(dy) else "V"
        if axis is not None and current_axis != axis:
            turns += 1
        axis = current_axis
    return turns


def _served_non_circulation(adjacency: dict[str, set[str]], corridor_ids: set[str],
                            zone_id: str) -> set[str]:
    return {n for n in adjacency.get(zone_id, ()) if n not in corridor_ids and n != "OUTSIDE"}


def _duplication(adjacency: dict[str, set[str]], circulation: list[RoomOut]) -> tuple[int, float]:
    corridor_ids = {r.zone_id for r in circulation}
    count = 0
    area = 0.0
    for i in range(len(circulation)):
        for j in range(i + 1, len(circulation)):
            a, b = circulation[i], circulation[j]
            if b.zone_id in adjacency.get(a.zone_id, ()):
                continue  # directly joined — a branching hub's own arms, not a duplicate
            served_a = _served_non_circulation(adjacency, corridor_ids, a.zone_id)
            served_b = _served_non_circulation(adjacency, corridor_ids, b.zone_id)
            if served_a & served_b:
                count += 1
                area += min(a.net_area_m2, b.net_area_m2)
    return count, round(area, 4)


def measure(design: GeometricDesign) -> CirculationMetrics:
    """Every dedicated-circulation fact this module measures, for one realized plan."""
    circulation = [r for r in design.rooms if _is_circulation(r.roles)]
    total_area = sum(r.net_area_m2 for r in design.rooms)
    area_m2 = round(sum(r.net_area_m2 for r in circulation), 4)
    ratio = area_m2 / total_area if total_area else 0.0
    longs_shorts = [_long_short(r) for r in circulation]
    longest_segment_m = max((ls[0] for ls in longs_shorts), default=None)
    narrowest_width_m = min((ls[1] for ls in longs_shorts), default=None)
    total_length_m = round(sum(ls[0] for ls in longs_shorts), 4)
    dead_end_count = _dead_end_count(design, circulation)
    adjacency = _adjacency(design)
    entrance_room = design.entrance_door.b if design.entrance_door.placeable else None
    turn_count = (_turn_count(design, _farthest_path(adjacency, entrance_room))
                 if entrance_room is not None and entrance_room in adjacency else 0)
    duplicated_segment_count, duplicated_area_m2 = _duplication(adjacency, circulation)
    return CirculationMetrics(
        area_m2=area_m2, ratio=ratio, longest_segment_m=longest_segment_m,
        total_length_m=total_length_m, narrowest_width_m=narrowest_width_m,
        dead_end_count=dead_end_count, turn_count=turn_count,
        duplicated_segment_count=duplicated_segment_count, duplicated_area_m2=duplicated_area_m2,
    )


# --------------------------------------------------------------------------- C26: extreme gate

#: A plan's circulation ratio above this is extreme. Calibrated on a corpus-shaped sweep through
#: `generate_demo_design` (varied footprints/bedroom/wet-room counts, including narrow-deep
#: footprints down to 8 x 28 m — deeper than the frozen regression corpus's own deepest footprint,
#: 24 m): plans cluster at 0.08-0.16, worst case measured 0.180. This leaves real headroom above
#: every measured plan while still catching a corridor that has taken over a genuinely
#: disproportionate share of the house.
EXTREME_RATIO = 0.24

#: A single circulation room's own long (walking) dimension above this is extreme. Calibrated the
#: same way: the worst measured single-hall spine is 17.3 m, on an 8 x 28 m footprint — deeper than
#: any footprint in the frozen regression corpus (max 24 m); this is set with real headroom above
#: that, so an ordinary spine — however long the house genuinely is — still passes, and only a
#: corridor stretched well past what any measured plan produces trips it.
EXTREME_LONGEST_SEGMENT_M = 20.0

#: More than this many un-served corridor ends (see `CirculationMetrics.dead_end_count`) is
#: extreme. Every measured spine/hub plan has at most one real dead end (the far end of a single
#: spine, or one arm of a branching hub) — its OTHER end is always the entrance or a served room by
#: construction. Two is already twice that; three or more is the plan this check exists to catch.
EXTREME_DEAD_END_COUNT = 2


def classify_extreme(metrics: CirculationMetrics) -> str | None:
    """`None` when this plan's circulation is within the calibrated limits (see the constants
    above); otherwise every limit it exceeds, so a refusal names the real cause."""
    reasons = []
    if metrics.ratio > EXTREME_RATIO + 1e-9:
        reasons.append(f"circulation ratio {metrics.ratio:.0%} exceeds {EXTREME_RATIO:.0%}")
    if metrics.longest_segment_m is not None and metrics.longest_segment_m > EXTREME_LONGEST_SEGMENT_M + 1e-9:
        reasons.append(f"longest corridor segment {metrics.longest_segment_m:.2f} m exceeds "
                       f"{EXTREME_LONGEST_SEGMENT_M:.2f} m")
    if metrics.dead_end_count > EXTREME_DEAD_END_COUNT:
        reasons.append(f"{metrics.dead_end_count} corridor dead ends exceeds {EXTREME_DEAD_END_COUNT}")
    return "; ".join(reasons) if reasons else None


# --------------------------------------------------------------------------- the ranking term

def circulation_prefers(current: CirculationMetrics, current_area_m2: float,
                        candidate: CirculationMetrics, candidate_area_m2: float,
                        *, area_keep_ratio: float = AREA_KEEP_RATIO) -> str | None:
    """`None`: `candidate`'s circulation earns it the primary over `current`. Otherwise why not.

    Mirrors `hub_guard.hub_keeps_primary`'s two-rule shape (a correctness check, then an area
    floor) — the SAME pattern, not a weighted score, and reusing its area threshold rather than a
    new one:

    1. CORRECTNESS — `candidate` must be better on at least one of ratio, longest segment or dead
       ends (fewer/shorter/fewer — never worse on all three and merely different).
    2. POLICY — `candidate` must still deliver at least `area_keep_ratio` of `current`'s area.

    Turns and duplication are reported on `CirculationMetrics` but never compared here: a turn is
    how a branching/compact hub reads on this measure, which this module's own thresholds already
    treat as no worse than a straight spine (`EXTREME_*` never gates on turn count) — scoring
    "fewer turns" as better would bias the ranking term back toward the straight spine the hub
    parti exists to move away from.
    """
    better = []
    if candidate.ratio < current.ratio - _EPS:
        better.append("ratio")
    if (candidate.longest_segment_m is not None and current.longest_segment_m is not None
            and candidate.longest_segment_m < current.longest_segment_m - _EPS):
        better.append("longest_segment")
    if candidate.dead_end_count < current.dead_end_count:
        better.append("dead_end_count")
    if candidate_area_m2 > current_area_m2 + 0.05:
        better.append("area")
    if not better:
        return ("candidate's circulation is better on nothing measured and not larger "
                f"({candidate_area_m2:.1f} vs {current_area_m2:.1f} m2)")
    if candidate_area_m2 < area_keep_ratio * current_area_m2:
        return (f"candidate delivers {candidate_area_m2:.1f} m2, under {area_keep_ratio:.0%} of "
               f"the current plan's {current_area_m2:.1f} m2")
    return None
