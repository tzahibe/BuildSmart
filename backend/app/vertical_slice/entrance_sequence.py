"""Entrance-to-circulation integration (Issue #22).

The front door has to land in a zone that keeps going, not at the end of an isolated stub. Two
related, deliberately UN-EQUAL facts about the arrival zone — the zone `doors.resolve_entrance`
named — read off REALIZED geometry (`GeometricDesign`), the same pattern `circulation_metrics.py`
already uses for C26:

  * POCKET — the walking distance from the entrance door to the NEAREST other opening (a door, or
    an open-plan join) reachable from the arrival zone itself. Zero — or unmeasurable, when the
    arrival zone has no other opening at all — is dead space directly behind the front door with
    no function: BLOCKING (C25), because nothing about it is a parti decision, only wasted area.
    A SEPARATE circulation zone that independently fronts the street with its own unserved stub
    (`stray_pockets`) is the same defect in a different place — "a blind pocket BESIDE the
    entrance" rather than in front of it — and blocks the same way.
  * TUNNEL — the walking distance from the entrance door to the first PUBLIC-group room reached,
    threading only through further circulation zones, plus how many PRIVATE rooms' doors were
    passed on the way. A long walk past bedroom doors before reaching the living room reads poorly
    but is not broken — fixing it is a parti change (a future "Entrance Sequence Quality" Issue),
    so this is NON-BLOCKING: reported and a candidate tiebreak, never a gate.

An arrival zone that is not itself circulation (e.g. the front door opens straight into LIVING)
has no pocket to measure — `pocket_length_m` is `0.0`, never `None`, and the whole POCKET question
is moot: the visitor has already arrived somewhere useful.

    measure(design) -> EntranceSequence   # one plan's own facts, C25's own input
    classify_tunnel(seq)  -> str | None    # the non-blocking quality signal
    entrance_sequence_prefers(current, candidate) -> str | None   # the ranking term
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from app.geometry_domain.walls import Construction

from . import access_rules
from .design_output import GeometricDesign, RoomOut

#: A room carrying either role is circulation — mirrors `circulation_metrics._CIRCULATION_ROLES`.
_CIRCULATION_ROLES = ("HALL", "CIRCULATION")
_PUBLIC_ROLES = frozenset(r.value for r in access_rules.PUBLIC_ROLES)
_PRIVATE_ROLES = frozenset(r.value for r in access_rules.PRIVATE_ROLES)

#: PARAMETER · UNVERIFIED (Issue #22). Calibrated on `scripts/entrance_sequence_sweep.py`'s sweep
#: of the frozen regression corpus + geometry fixtures (`docs/ENTRANCE_CIRCULATION_SWEEP.md`) —
#: the same "measure real plans, then set the limit with headroom above every one of them"
#: discipline `circulation_metrics.EXTREME_RATIO`/`EXTREME_LONGEST_SEGMENT_M` use, not a code
#: minimum. Governs the ARRIVAL zone's own pocket only (`_pocket_length_m`) — the Issue's own
#: illustrative default (0.6 m) does not survive contact with real plans here: an ordinary hall's
#: distance to the first room off it (0.00-3.28 m across the corpus, mean 1.82 m) is a normal
#: architectural fact, not wasted space, so this constant has real headroom above it. See that
#: report for the measured distribution this value sits above, and `ENTRANCE_STRAY_POCKET_MAX_M`
#: below for the OTHER pocket shape, which does not need this headroom.
ENTRANCE_POCKET_MAX_M = 4.0

#: PARAMETER · UNVERIFIED (Issue #22). Governs `_stray_pockets` only — a SEPARATE circulation zone
#: (not the arrival zone) independently fronting the street unserved beside the entrance. Unlike
#: `ENTRANCE_POCKET_MAX_M` above, this shape needs no headroom: the sweep found ZERO contexts in
#: the full 432-context corpus with a second circulation zone at all (every real spine candidate
#: has exactly one `HALL` leaf, `concept_generator.py`'s `_concept_from`) — so this constant carries
#: the Issue's own illustrative default (0.6 m) unchanged, with a genuine, currently-untested
#: protective margin rather than a value backed into just above the corpus's own maximum.
ENTRANCE_STRAY_POCKET_MAX_M = 0.6

#: PARAMETER · UNVERIFIED. More than this much walking distance from the entrance to the first
#: PUBLIC-group room, with only private/service doors passed on the way, reads as a tunnel — a
#: NON-BLOCKING quality signal (see the module docstring for why this never gates a plan).
ENTRANCE_TUNNEL_MAX_M = 4.0

#: The two Euclidean-distance tolerances this module needs: telling "the entrance door's own
#: point" apart from "a genuinely different opening" on the same wall (a few cm of solver-grid
#: rounding), and comparing two tunnel distances for ranking (mirrors
#: `circulation_metrics._EPS`/`_DOOR_END_TOLERANCE_M`).
_SAME_POINT_TOLERANCE_M = 0.15
_EPS = 0.02


def _is_circulation(roles: tuple[str, ...]) -> bool:
    return any(r in _CIRCULATION_ROLES for r in roles)


def _is_public(roles: tuple[str, ...]) -> bool:
    return any(r in _PUBLIC_ROLES for r in roles)


def _is_private(roles: tuple[str, ...]) -> bool:
    return any(r in _PRIVATE_ROLES for r in roles)


def _center(rect_m) -> tuple[float, float]:
    x, y, w, h = rect_m
    return (x + w / 2, y + h / 2)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass(frozen=True)
class EntranceSequence:
    """One realized plan's entrance-sequence facts, read off `GeometricDesign` alone.

    `arrival_zone` is `None` only when the entrance door itself is not placeable — nothing else
    here is measurable in that case either, and C7/C11 already fail closed on it independently.
    """

    #: The zone `doors.resolve_entrance`/`build_entrance_door` named — the entrance door's `.b`.
    arrival_zone: str | None
    arrival_roles: tuple[str, ...]
    is_circulation_arrival: bool
    #: The distance to the arrival zone's own nearest other opening (see `_pocket_length_m`) —
    #: `0.0` whenever the arrival zone is not circulation (already arrived).
    pocket_length_m: float
    #: Is a PUBLIC-group room reachable at all from the arrival zone, through further circulation?
    has_public_opening: bool
    #: `None` only when `has_public_opening` is `False`.
    distance_to_public_m: float | None
    #: Distinct PRIVATE rooms whose door was passed walking the corridor to the first public room.
    private_doors_passed: int
    #: Heuristic, reporting-only: the arrival zone carries the HALL role (a declared foyer/hall,
    #: not a bare CIRCULATION corridor segment) and the sequence is clean (no pocket, a public
    #: opening exists) — an intentional foyer, not a defect. Never gates anything.
    foyer: bool
    #: The OTHER failure shape (the Issue's own "Current behavior": "leaving the corridor's
    #: street-facing end as a blind pocket BESIDE the entrance") — every OTHER circulation zone
    #: (not the arrival zone) that independently fronts the street with more than
    #: `ENTRANCE_STRAY_POCKET_MAX_M` of unserved depth before its own first opening. `()` when none.
    stray_pockets: tuple[tuple[str, float], ...] = ()


def _rooms_by_id(design: GeometricDesign) -> dict[str, RoomOut]:
    return {r.zone_id: r for r in design.rooms}


def _openings_of(design: GeometricDesign, room: RoomOut) -> list[tuple[float, float]]:
    """Every point (a placeable door's centre, or an open-plan join's side midpoint) this room can
    be left by — the entrance door's own point included; the caller filters that one out."""
    points: list[tuple[float, float]] = []
    for door in (*design.interior_doors, design.entrance_door):
        if door.placeable and room.zone_id in (door.a, door.b):
            points.append(door.center_m)
    x, y, w, h = room.rect_m
    sides = {"W": (x, y + h / 2), "E": (x + w, y + h / 2),
             "N": (x + w / 2, y), "S": (x + w / 2, y + h)}
    for side, point in sides.items():
        facts = room.wall_facts.get(side)
        if facts is not None and facts.construction is Construction.NONE:
            points.append(point)
    return points


def _fronts_street(design: GeometricDesign, room: RoomOut) -> bool:
    return abs(room.rect_m[1] - design.footprint_m[1]) <= _SAME_POINT_TOLERANCE_M


def _stray_pocket_length_m(design: GeometricDesign, room: RoomOut) -> float:
    """How far from the street line before this OTHER circulation zone's first opening — measured
    from the midpoint of its own street-facing wall, since it has no entrance door of its own to
    measure from. `math.inf` when it has no opening at all."""
    x, y, w, h = room.rect_m
    reference = (x + w / 2, y)
    others = _openings_of(design, room)
    return min((_dist(reference, p) for p in others), default=math.inf)


def _stray_pockets(design: GeometricDesign, rooms: dict[str, RoomOut],
                   arrival_zone: str | None) -> tuple[tuple[str, float], ...]:
    found = []
    for room in design.rooms:
        if room.zone_id == arrival_zone or not _is_circulation(room.roles):
            continue
        if not _fronts_street(design, room):
            continue
        length = round(_stray_pocket_length_m(design, room), 4)
        if length > ENTRANCE_STRAY_POCKET_MAX_M + 1e-9:
            found.append((room.zone_id, length))
    return tuple(sorted(found))


def _pocket_length_m(design: GeometricDesign, arrival: RoomOut) -> float:
    """The walking distance from the entrance door to the NEAREST other opening on the arrival
    zone — a door into a room, an open-plan join, or a door onward into further circulation —
    whichever DIRECTION it is in.

    Deliberately "nearest in any direction", not "the far wall straight ahead": a compact hub
    with doors branching off close to the entrance is the architecturally preferred circulation
    topology (specs/005), and an ordinary spine hall's own far end (opposite the entrance) is a
    KNOWN, ACCEPTED dead end by construction (`circulation_metrics.dead_end_count` tolerates
    exactly one) — neither is a pocket. What IS a pocket is nothing being reachable ANYWHERE near
    the entrance at all, confirmed empirically on the sweep (`docs/ENTRANCE_CIRCULATION_SWEEP.md`):
    every real generator plan's nearest opening is well under `ENTRANCE_POCKET_MAX_M`, and only a
    genuinely isolated stub (AC-5's hand-built fixture) measures past it.
    """
    entrance_point = design.entrance_door.center_m
    others = [p for p in _openings_of(design, arrival)
             if _dist(p, entrance_point) > _SAME_POINT_TOLERANCE_M]
    return min((_dist(entrance_point, p) for p in others), default=math.inf)


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


def _path_to_first_public(rooms: dict[str, RoomOut], adjacency: dict[str, set[str]],
                          start: str) -> list[str] | None:
    """BFS from `start`, walked only through `start` itself and further CIRCULATION rooms (a
    private/public leaf reached is never expanded past) — the same deterministic sorted-neighbour
    order `circulation_metrics._farthest_path` uses. `None` when no PUBLIC-group room is
    reachable that way at all."""
    if start not in rooms:
        return None
    if _is_public(rooms[start].roles):
        return [start]
    parent: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    target: str | None = None
    while queue and target is None:
        current = queue.popleft()
        if current != start and not _is_circulation(rooms[current].roles):
            continue  # a private/service/public leaf — do not walk further from it
        for nxt in sorted(adjacency.get(current, ())):
            if nxt == "OUTSIDE" or nxt in parent or nxt not in rooms:
                continue
            parent[nxt] = current
            if _is_public(rooms[nxt].roles):
                target = nxt
                break
            queue.append(nxt)
    if target is None:
        return None
    path = [target]
    node: str | None = target
    while parent[node] is not None:
        node = parent[node]
        path.append(node)
    return list(reversed(path))


def _private_doors_passed(rooms: dict[str, RoomOut], adjacency: dict[str, set[str]],
                          path: list[str]) -> int:
    passed: set[str] = set()
    for zone_id in path[:-1]:
        for neighbour in adjacency.get(zone_id, ()):
            if neighbour in rooms and _is_private(rooms[neighbour].roles):
                passed.add(neighbour)
    return len(passed)


def measure(design: GeometricDesign) -> EntranceSequence:
    """Every entrance-sequence fact this module measures, for one realized plan."""
    entrance = design.entrance_door
    if not entrance.placeable:
        return EntranceSequence(None, (), False, 0.0, False, None, 0, False)
    rooms = _rooms_by_id(design)
    arrival = rooms.get(entrance.b)
    if arrival is None:
        return EntranceSequence(None, (), False, 0.0, False, None, 0, False)

    is_circ = _is_circulation(arrival.roles)
    pocket_length_m = round(_pocket_length_m(design, arrival), 4) if is_circ else 0.0

    adjacency = _adjacency(design)
    path = _path_to_first_public(rooms, adjacency, arrival.zone_id)
    if path is None:
        distance_to_public_m = None
        private_doors_passed = 0
        has_public_opening = False
    else:
        distance_to_public_m = round(sum(
            _dist(_center(rooms[path[i]].rect_m), _center(rooms[path[i + 1]].rect_m))
            for i in range(len(path) - 1)), 4)
        private_doors_passed = _private_doors_passed(rooms, adjacency, path)
        has_public_opening = True

    foyer = (is_circ and "HALL" in arrival.roles and has_public_opening
             and pocket_length_m <= ENTRANCE_POCKET_MAX_M + 1e-9)
    stray_pockets = _stray_pockets(design, rooms, arrival.zone_id)

    return EntranceSequence(
        arrival_zone=arrival.zone_id, arrival_roles=arrival.roles,
        is_circulation_arrival=is_circ, pocket_length_m=pocket_length_m,
        has_public_opening=has_public_opening, distance_to_public_m=distance_to_public_m,
        private_doors_passed=private_doors_passed, foyer=foyer, stray_pockets=stray_pockets,
    )


# --------------------------------------------------------------------------- C25: the pocket gate

def classify_pocket(seq: EntranceSequence) -> str | None:
    """`None` when C25 passes; otherwise every defect it found, so a refusal names the real cause.

    Three independent failure modes, any one enough to fail closed:

    1. The arrival zone is circulation and more than `ENTRANCE_POCKET_MAX_M` of it is unserved
       beyond the entrance door (including "unmeasurable" — no other opening at all).
    2. No PUBLIC-group room is reachable from the arrival zone at all, whatever its own role.
    3. A SEPARATE circulation zone independently fronts the street with more than
       `ENTRANCE_STRAY_POCKET_MAX_M` of unserved stub beside the entrance (`seq.stray_pockets`).
    """
    if seq.arrival_zone is None:
        return None  # C7/C11/C16 already own an unplaceable entrance door
    reasons = []
    if seq.is_circulation_arrival and seq.pocket_length_m > ENTRANCE_POCKET_MAX_M + 1e-9:
        if math.isinf(seq.pocket_length_m):
            reasons.append(f"{seq.arrival_zone} has no other opening at all beyond the entrance "
                           f"door — a fully sealed dead-end stub")
        else:
            reasons.append(f"{seq.pocket_length_m:.2f} m of unserved corridor beyond the entrance "
                           f"door in {seq.arrival_zone} exceeds {ENTRANCE_POCKET_MAX_M:.2f} m")
    if not seq.has_public_opening:
        reasons.append(f"{seq.arrival_zone} has no opening to a public room or open zone")
    for zone_id, length in seq.stray_pockets:
        reasons.append(f"{length:.2f} m of unserved corridor beside the entrance in {zone_id} "
                       f"exceeds {ENTRANCE_STRAY_POCKET_MAX_M:.2f} m")
    return "; ".join(reasons) if reasons else None


# --------------------------------------------------------------------------- the tunnel signal

def classify_tunnel(seq: EntranceSequence) -> str | None:
    """`None` unless the walk to the first public opening is a tunnel — NEVER a gate (see the
    module docstring); reported on `QualityOut.entrance_sequence` and used only by
    `entrance_sequence_prefers` below."""
    if (seq.distance_to_public_m is not None
            and seq.distance_to_public_m > ENTRANCE_TUNNEL_MAX_M + 1e-9
            and seq.private_doors_passed > 0):
        return (f"{seq.distance_to_public_m:.2f} m to the first public opening, passing "
               f"{seq.private_doors_passed} private room door(s), exceeds "
               f"{ENTRANCE_TUNNEL_MAX_M:.2f} m")
    return None


def entrance_sequence_prefers(current: EntranceSequence, candidate: EntranceSequence) -> str | None:
    """`None`: `candidate`'s entrance sequence earns it the primary over `current` on this measure
    alone. Otherwise why not — mirrors `circulation_metrics.circulation_prefers`'s shape (a single
    correctness comparison, no area floor needed since this is never the only signal a caller
    compares on). Only the TUNNEL distance is compared — the pocket is already a hard gate (C25)
    that both candidates already passed to be compared at all."""
    if (current.distance_to_public_m is None or candidate.distance_to_public_m is None):
        return "one candidate has no measurable path to a public room"
    if candidate.distance_to_public_m < current.distance_to_public_m - _EPS:
        return None
    return (f"candidate's distance to the first public opening "
           f"({candidate.distance_to_public_m:.2f} m) is not better than the current plan's "
           f"({current.distance_to_public_m:.2f} m)")
