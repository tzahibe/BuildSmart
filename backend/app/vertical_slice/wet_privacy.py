"""Wet-room privacy and access quality — Issue #37.

C17 (`validation.py`) already fails closed on WHO may enter a wet room (an ensuite only from its
host bedroom, everything else only from circulation) — but it says nothing about what a person
standing in a public room sees, or feels, when that door is open. This module answers the
question C17 does not: per wet room, a deterministic `WetPrivacy` record built from the REALIZED
geometry (rects, walls, doors) — never from the programme's stated intent, the same discipline
every check in `validation.py` already holds to.

    entered_from / entered_from_class   which zone the one realized door connects to, and
                                         whether that zone reads as PRIVATE, CIRCULATION, PUBLIC
                                         or SERVICE (`ZoneClass`, from the zone's `ProgramRole`s)
    door_facing / direct_sight_line     the zone a person standing at the open door sees INTO:
                                         the entered-from zone itself when it is not circulation,
                                         or — a real segment test on the realized rects — the zone
                                         directly across a circulation zone's width, when one
                                         zone's door faces another's from the opposite wall. The
                                         segment test reads each door's own SIDE and opening span
                                         off the realized rects directly (`_side_between`,
                                         `_opening_span_u`) rather than off `Door.orientation`'s
                                         string or `Door.swings_into`: the rects are the geometry
                                         those two fields were themselves derived from, so reading
                                         them directly is the same fact with one less indirection,
                                         never a different one. `swings_into` answers a different
                                         question (which room's floor the leaf itself occupies when
                                         open) that this record does not need.
    public_exposure_score               0.0 (fully private) .. 1.0 (opens straight onto a public
                                         seating/dining zone) — the tiered quality score
    circulation_obstruction             the door's own opening width against the corridor's net
                                         clear width, entered-from-circulation rooms only
    adjacency_quality                   shares an interior wall with another wet room or the
                                         kitchen (the same relationship M5 measures, read directly
                                         off this one room rather than the whole plan)
    privacy_score                       one aggregate number, LOWER IS BETTER, for ranking two
                                         otherwise-equal candidates against each other — never a
                                         gate; `hard_violations` below is the only fail-closed path

THE ONE HARD RULE (validation.py's C29): a wet room entered DIRECTLY from KITCHEN or DINING — the
door opens straight onto a public seating/dining zone with a direct sight line by construction,
since the room being entered from IS that zone. Corridor access, however exposed the facing
geometry, is never refused here — decision A of specs/009-guest-wc-placement already settled that
proximity/exposure is a ranking concern, not a law, and this module keeps that line: LIVING is a
legitimate corridor-class-adjacent entry (specs/009 §0 decision C lists it as the third-choice
public access zone for a guest WC), KITCHEN and DINING are not.

Everything else computed here is read-only quality data: `QualityOut.wet_privacy`
(`app.demo.contract`) for display, and `privacy_score`/`candidate_privacy_key` below for a caller
that is choosing between otherwise-equal candidate plans — `app.demo.service._break_l_tie` is
that caller today (the last tiebreak among L-massing peers already tied on the person's
garden/street preference and on `LQuality`'s Pareto comparison, via `_privacy_key_of_plan`); this
module never places a room, never moves a door and never re-scores a row partition
(`concept_generator.py`'s own quality tier is a separate, EARLIER-stage mechanism — realized doors
do not exist yet at that stage, so a privacy signal could not be computed there at all — this
module does not touch it).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .doors import Door
from .geometry_core.engine import WallMap, net_rect_m
from .geometry_core.model import Fixture, ProgramRole, Rect, Side, WallType, m_to_u

_OPPOSITE_SIDE = {Side.N: Side.S, Side.S: Side.N, Side.E: Side.W, Side.W: Side.E}


class ZoneClass(str, Enum):
    PRIVATE = "PRIVATE"
    CIRCULATION = "CIRCULATION"
    PUBLIC = "PUBLIC"
    SERVICE = "SERVICE"
    OTHER = "OTHER"


#: Every `ProgramRole` a wet room could plausibly be entered from or face, classified once here —
#: the single table both `classify_zone` and `hard_violations` read, so the two can never disagree
#: about what counts as public.
_ZONE_CLASS: dict[ProgramRole, ZoneClass] = {
    ProgramRole.BEDROOM: ZoneClass.PRIVATE,
    ProgramRole.MASTER_BEDROOM: ZoneClass.PRIVATE,
    ProgramRole.SAFE_ROOM: ZoneClass.PRIVATE,
    ProgramRole.DRESSING_ROOM: ZoneClass.PRIVATE,
    ProgramRole.STUDY: ZoneClass.PRIVATE,
    ProgramRole.HALL: ZoneClass.CIRCULATION,
    ProgramRole.CIRCULATION: ZoneClass.CIRCULATION,
    ProgramRole.LIVING: ZoneClass.PUBLIC,
    ProgramRole.DINING: ZoneClass.PUBLIC,
    ProgramRole.KITCHEN: ZoneClass.PUBLIC,
    ProgramRole.FAMILY_ROOM: ZoneClass.PUBLIC,
    ProgramRole.BATHROOM: ZoneClass.SERVICE,
    ProgramRole.TOILET: ZoneClass.SERVICE,
    ProgramRole.LAUNDRY: ZoneClass.SERVICE,
    ProgramRole.STORAGE: ZoneClass.SERVICE,
}

#: The C29 hard-fail set: a wet room entered directly from either of these IS, by construction, a
#: door opening straight onto a public seating/dining zone with a direct sight line — the person
#: entering it and the person already in the room are the same doorway. See the module docstring
#: for why LIVING is deliberately not in this set.
_HARD_FAIL_ROLES = frozenset({ProgramRole.KITCHEN, ProgramRole.DINING})

#: A wet room's own kind — never counted as its own neighbour, and never itself "public".
_WET_ROLES = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET})

#: `adjacency_quality`'s neighbour set — another wet room, or the kitchen (M5's own WET_NEIGHBOURS,
#: `quality_metrics.py`, minus LAUNDRY: this record is per-room and LAUNDRY carries no privacy
#: signal of its own; a wet room beside a laundry is a plumbing question, not a privacy one).
_ADJACENCY_ROLES = _WET_ROLES | {ProgramRole.KITCHEN}

#: `circulation_obstruction`'s threshold: a door whose own opening consumes at least half the
#: corridor's net clear width reads as an obstruction when open, whichever way it swings.
_OBSTRUCTION_WIDTH_RATIO = 0.5

#: `public_exposure_score` bands — 0.0 fully private .. 1.0 the C29 hard-fail case itself. Ordered
#: so a caller reading the raw number can place it without consulting this module again.
_EXPOSURE_PRIVATE = 0.0
_EXPOSURE_CIRCULATION_BLIND = 0.2
_EXPOSURE_CIRCULATION_FACING_PUBLIC = 0.5
_EXPOSURE_PUBLIC_SOFT = 0.7          # entered directly from LIVING/FAMILY_ROOM
_EXPOSURE_PUBLIC_HARD = 1.0          # entered directly from KITCHEN/DINING (C29 fails on this)
_EXPOSURE_OTHER = 0.3                # entered from SERVICE/OTHER (e.g. off a laundry/storage run)


def classify_zone(roles: tuple[ProgramRole, ...]) -> ZoneClass:
    """The first classified role wins — a room's PRIMARY role decides its class, exactly the way
    `ZoneSpec.primary_role` already reads `roles[0]` everywhere else in this vertical slice."""
    for role in roles:
        cls = _ZONE_CLASS.get(role)
        if cls is not None:
            return cls
    return ZoneClass.OTHER


@dataclass(frozen=True)
class WetPrivacy:
    """One wet room's privacy standing — see the module docstring for each field."""

    zone_id: str
    entered_from: str | None
    entered_from_class: ZoneClass
    door_facing: str | None
    direct_sight_line: bool
    public_exposure_score: float
    circulation_obstruction: bool
    adjacency_quality: bool
    privacy_score: float


def _side_between(a: Rect, b: Rect) -> Side | None:
    if a.x2 == b.x:
        return Side.E
    if b.x2 == a.x:
        return Side.W
    if a.y2 == b.y:
        return Side.S
    if b.y2 == a.y:
        return Side.N
    return None


def _doors_touching(zone_id: str, doors: Sequence[Door]) -> list[Door]:
    return [d for d in doors if zone_id in (d.a, d.b)]


def _opening_span_u(door: Door, side: Side) -> tuple[int, int]:
    """The opening's own extent along the corridor's LENGTH axis, in grid units — the axis two
    doors on opposite E/W walls must overlap on is y (their span runs along y); on opposite N/S
    walls it is x."""
    half = m_to_u(door.width_m) // 2
    cx, cy = door.center_u
    coord = cy if side in (Side.E, Side.W) else cx
    return (coord - half, coord + half)


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return max(a[0], b[0]) < min(a[1], b[1])


def _facing_zone(zone_id: str, corridor_id: str, my_door: Door, roles_of: dict[str, tuple],
                 rects: dict[str, Rect], doors: Sequence[Door]) -> str | None:
    """The zone directly across `corridor_id` from `zone_id`'s own door — a real segment test on
    the realized rects, not a guess: another door on the corridor's OPPOSITE wall whose opening
    overlaps `my_door`'s own span along the corridor. `None` when no door faces it (the corridor
    wall opposite is blank, or the nearest facing door does not line up)."""
    corridor = rects.get(corridor_id)
    my_side = _side_between(corridor, rects[zone_id]) if corridor is not None else None
    if corridor is None or my_side is None:
        return None
    opposite = _OPPOSITE_SIDE[my_side]
    my_span = _opening_span_u(my_door, my_side)
    for door in doors:
        if door is my_door or corridor_id not in (door.a, door.b):
            continue
        other = door.b if door.a == corridor_id else door.a
        if other == zone_id:
            continue
        other_rect = rects.get(other)
        if other_rect is None or _side_between(corridor, other_rect) != opposite:
            continue
        if _spans_overlap(my_span, _opening_span_u(door, opposite)):
            return other
    return None


def _exposure_score(entered_from_class: ZoneClass, entered_from_role: ProgramRole | None,
                    direct_sight_line: bool) -> float:
    if entered_from_class is ZoneClass.PRIVATE:
        return _EXPOSURE_PRIVATE
    if entered_from_class is ZoneClass.CIRCULATION:
        return _EXPOSURE_CIRCULATION_FACING_PUBLIC if direct_sight_line else _EXPOSURE_CIRCULATION_BLIND
    if entered_from_class is ZoneClass.PUBLIC:
        return _EXPOSURE_PUBLIC_HARD if entered_from_role in _HARD_FAIL_ROLES else _EXPOSURE_PUBLIC_SOFT
    return _EXPOSURE_OTHER


def _adjacency_quality(zone_id: str, rects: dict[str, Rect], walls: WallMap,
                       roles_of: dict[str, tuple]) -> bool:
    rect = rects.get(zone_id)
    if rect is None:
        return False
    for other_id, other_rect in rects.items():
        if other_id == zone_id or rect.shared_edge_len_u(other_rect) <= 0:
            continue
        if not (set(roles_of.get(other_id, ())) & _ADJACENCY_ROLES):
            continue
        side = _side_between(rect, other_rect)
        if side is not None and walls.get((zone_id, side)) is not WallType.EXTERIOR:
            return True
    return False


def _circulation_obstruction(zone_id: str, door: Door, corridor_id: str,
                             rects: dict[str, Rect], walls: WallMap) -> bool:
    corridor_rect = rects.get(corridor_id)
    if corridor_rect is None:
        return False
    nw, nh, _ = net_rect_m(corridor_id, corridor_rect, walls)
    corridor_width_m = min(nw, nh)
    if corridor_width_m <= 0:
        return False
    return door.width_m >= corridor_width_m * _OBSTRUCTION_WIDTH_RATIO


def compute_wet_privacy(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                        interior_doors: Sequence[Door], wet_rooms: Sequence) -> tuple[WetPrivacy, ...]:
    """One `WetPrivacy` per zone id in `wet_rooms` (a `ResolvedWetRoom` sequence, or anything with
    a `.zone_id`) that is actually in this plan — every fact READ off `rects`/`walls`/
    `interior_doors`, never off `wet_rooms` itself beyond which zone ids to report on (the same
    "never read intent off the geometry, but never trust intent over it either" split C17 keeps)."""
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    out: list[WetPrivacy] = []
    for wet_room in wet_rooms:
        zone_id = wet_room.zone_id
        if zone_id not in rects:
            continue
        touching = _doors_touching(zone_id, interior_doors)
        entered_from = None
        if len(touching) == 1:
            door = touching[0]
            entered_from = door.b if door.a == zone_id else door.a
        entered_from_class = (classify_zone(roles_of.get(entered_from, ()))
                              if entered_from is not None else ZoneClass.OTHER)
        entered_from_role = roles_of.get(entered_from, (None,))[0] if entered_from else None

        door_facing: str | None = None
        direct_sight_line = False
        if entered_from is not None and entered_from_class is ZoneClass.CIRCULATION:
            door_facing = _facing_zone(zone_id, entered_from, touching[0], roles_of, rects,
                                       interior_doors)
            direct_sight_line = (door_facing is not None
                                 and classify_zone(roles_of.get(door_facing, ())) is ZoneClass.PUBLIC)
        elif entered_from is not None:
            door_facing = entered_from
            direct_sight_line = entered_from_class is ZoneClass.PUBLIC

        exposure = _exposure_score(entered_from_class, entered_from_role, direct_sight_line)
        obstruction = (entered_from_class is ZoneClass.CIRCULATION
                       and _circulation_obstruction(zone_id, touching[0], entered_from, rects, walls))
        adjacency = _adjacency_quality(zone_id, rects, walls, roles_of)
        privacy_score = round(exposure + (0.15 if obstruction else 0.0)
                              - (0.1 if adjacency else 0.0), 4)

        out.append(WetPrivacy(
            zone_id=zone_id, entered_from=entered_from, entered_from_class=entered_from_class,
            door_facing=door_facing, direct_sight_line=direct_sight_line,
            public_exposure_score=exposure, circulation_obstruction=obstruction,
            adjacency_quality=adjacency, privacy_score=privacy_score,
        ))
    return tuple(out)


def hard_violations(fixture: Fixture, records: Sequence[WetPrivacy]) -> list[str]:
    """C29's fail-closed list — empty means every wet room clears the hard rule. See the module
    docstring: entered directly from KITCHEN or DINING only; corridor access never fails here,
    however its facing geometry scores in `public_exposure_score`."""
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    bad: list[str] = []
    for record in records:
        if record.entered_from is None:
            continue
        role = roles_of.get(record.entered_from, (None,))[0]
        if role in _HARD_FAIL_ROLES:
            bad.append(f"{record.zone_id}: entered directly from {record.entered_from} "
                      f"({role.value}) — a public seating/dining zone, direct sight line")
    return bad


def candidate_privacy_key(records: Sequence[WetPrivacy]) -> tuple[float, float]:
    """(worst room's privacy_score, sum of every room's privacy_score) — LOWER IS BETTER. The
    worst room is what a person notices first (the same "worst case first" ordering
    `concept_generator._quality_score` already uses for room proportions); the sum breaks a tie
    between two candidates whose worst room is equally exposed but whose OTHER wet rooms are not.
    A caller comparing two otherwise-equal candidate plans (siblings differing only in which way a
    wet room's door was mirrored, e.g.) picks the one with the lower key — never a gate, exactly
    like `_l_quality_of_plan`'s role in the L-orientation tiebreak."""
    scores = [r.privacy_score for r in records]
    if not scores:
        return (0.0, 0.0)
    return (round(max(scores), 4), round(sum(scores), 4))


def better_candidate(a: Sequence[WetPrivacy], b: Sequence[WetPrivacy]) -> Sequence[WetPrivacy]:
    """Which of two candidates' wet-room privacy records reads as more private — `a` on an exact
    tie, so the choice is deterministic rather than depending on argument order by accident."""
    return a if candidate_privacy_key(a) <= candidate_privacy_key(b) else b
