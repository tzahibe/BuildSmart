"""Multi-level Phase 1 — the pinned per-level layout: `LevelProgram -> ConceptCandidate`.

A SECOND ENTRY POINT into `concept_generator`'s machinery, alongside `generate_concepts`/`_build` —
not a change to either. This module takes a level's rooms (already split by `level_program.py`)
and a PINNED core band, and reuses the generator's row/column/depth/spec machinery exactly as
`l_parti.py` reuses it for the L (see that module's own docstring for the same architectural
argument). `_build`, `_allocations` and `generate_concepts` are never called here and are never
imported by anything that calls into this module — the single-storey path is untouched.

THE CORE BAND (`MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` §4, follow-up report §1). A vertical
strip beside the corridor, at the seat both levels are pinned to:

    CoreLobbyForm.FULL (recommended, upper level)          CoreLobbyForm.SHRUNK (recommended, ground)
    ┌───────────────────────────────┐                       ┌──────────────────────────────┐
    │  HALL_2 (lobby, full band,    │                       │ strip room (front)            │
    │  band_w x (fh-L))             │                       ├────────────────────────────────┤
    ├───────────┬────────────────────┤                       │ STAIR │  HALL (corridor,      │
    │  STAIR    │ HALL (corridor)   │                       │ (rear)│  full depth fh)        │
    │  (rear,   │                   │                       │       │                        │
    │  s x L)   │                   │                       └───────┴───────────────────────┘
    └───────────┴───────────────────┘

    CoreLobbyForm.ABSORBED (ground only, open-plan public topology only — see `eligible_for_absorbed`)
    ┌───────────────────────────────┐
    │  front rows, full column      │  ← the level's own open-plan group; the join with STAIR is
    │  width (west_w = col_w + s)   │    marked wall-less STRUCTURALLY (the mechanism an open
    ├────────────────┬───────────────┤    LDK's doors already skip), never a plain adjacency —
    │ rear rows      │ STAIR │ HALL  │    follow-up report §1.4: sound for a flight rising inside
    │ (col_w)        │ (s×L) │(c×fh) │    an open living space, never for a private room, hence
    └────────────────┴───────────────┘    ground-only here.

`L` is the straight flight's length (`vertical.straight_flight_length_m`), fixed by the floor-to-
floor height and identical on both levels by construction (both cuts are forced). `s`/`c` are the
seat's strip/corridor widths. `fixed_seam_m`, when given, pins the strip-side column's width to
the GROUND's REALIZED stair rectangle x (the coordinator's join, first report §4.2) — the upper
level never searches its own seam.

WHAT IS REUSED, unchanged: `scale_program`, `_rows_of`, `_orient_row`, `_daylight_order`,
`_seam_options`, `_columns_at_seam`, `_row_widths`, `_row_depths`, `_zone_spec`,
`_specs_within_maxima`, `_forced_chain`, `_build_access`, `_column_min_width`, `_column_width`,
`ROOM_TEMPLATES`, `ASSUMED_EFFICIENCY`, `_EDGE_INSET_ALLOWANCE_M`. `_unforced`/`_contains_hall`
are generalised here as `_unforced_pinned`/`_contains_pinned` over the core band's zone ids
instead of `HALL` alone — the same free-twin idea, a wider pinned set.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from . import concept_generator as cg
from .concept import Concept
from .concept_generator import (
    ASSUMED_EFFICIENCY,
    ROOM_TEMPLATES,
    ConceptCandidate,
    ConceptStrategy,
    ProgramRoom,
    RejectionReason,
    ZoneGroup,
    _EDGE_INSET_ALLOWANCE_M,
)
from .geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    Node,
    ProgramRole,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from .level_program import GroundLayout, LevelProgram
from .vertical import straight_flight_length_m

#: A door's clearance (`doors.INTERIOR_DOOR_WIDTH_M` + `doors.DOOR_MARGIN_M` x 2) — the shortest
#: run of circulation frontage a room that needs a door may be planned against. Mirrors the
#: generator's own door-placeability arithmetic rather than importing `doors.py` (a stage that
#: runs AFTER this one) — this is a PRE-check, exactly like every other early-feasibility test in
#: `concept_generator.py`; `doors.generate_interior_doors` and C7 are what actually prove it.
DOOR_CLEAR_M = 1.1

#: The strip room `SHRUNK` adds when the programme has no eligible guest WC to reuse — an engine
#: room, never a fabricated bathroom.
_STRIP_ROOM_ROLE = ProgramRole.STORAGE
_STRIP_ROOM_ID = "SROOM"


class CoreLobbyForm(str, Enum):
    """How the core band's front is used, ahead of the stair strip. See the module docstring.

    Phase 1's approved scope: `SHRUNK` on the ground, `FULL` on the upper, `ABSORBED` optional on
    the ground only (`eligible_for_absorbed`). Nothing HERE refuses `FULL` on the ground or
    `SHRUNK`/`ABSORBED` on the upper — this module is the mechanism; the coordinator is the
    policy that keeps to the approved pairing.
    """

    #: The whole band is a lobby, `band_w x (fh - L)` (V0, first report §4.2). Needed on the
    #: ground for the front door's frontage; costs the most circulation (follow-up report §1.1).
    FULL = "full"
    #: The lobby shrinks to what a strip room's own shape needs; the strip room (the programme's
    #: guest WC when eligible, else an engine STORAGE room) takes the rest (V1, follow-up §1.2-3).
    SHRUNK = "shrunk"
    #: No lobby: the corridor spans the full depth and the strip-side column jogs, front rows the
    #: full column width, rear rows narrower beside the stair (V2, follow-up §1.2/§1.4). Requires
    #: `eligible_for_absorbed`.
    ABSORBED = "absorbed"


@dataclass(frozen=True)
class StairSeat:
    """The core band's fixed geometry — a search variable for the coordinator, pinned for both
    level planners once chosen. `strip_w_m`/`corridor_w_m` are CENTERLINE widths (net = width -
    the wall allowance either side), chosen so the flight nets >= `STAIRWELL.min_short_side_m`
    and the corridor nets >= `HALL.min_short_side_m`."""

    strip_w_m: float
    corridor_w_m: float
    floor_to_floor_m: float = 3.0  # PARAMETER · UNVERIFIED — `building.FLOOR_TO_FLOOR_M`'s value

    @property
    def stair_len_m(self) -> float:
        return straight_flight_length_m(self.floor_to_floor_m)

    @property
    def band_w_m(self) -> float:
        return self.strip_w_m + self.corridor_w_m


#: Recommended default seat (follow-up report §1.5) — the seat every candidate in the Phase-1
#: measurement used: the smallest strip/corridor that keeps the flight and the corridor at their
#: templates' minimum short sides once wall-inset.
DEFAULT_SEAT = StairSeat(strip_w_m=1.2, corridor_w_m=1.4)


@dataclass(frozen=True)
class LevelFailure:
    reason: str
    detail: str = ""


def eligible_for_absorbed(level: LevelProgram) -> bool:
    """Whether `CoreLobbyForm.ABSORBED` may even be ATTEMPTED on this level — the structural
    precondition (follow-up report §1.4): an open-plan public group (the LIVING/DINING/KITCHEN
    chain a closed-kitchen ground still has for LIVING+DINING), with EVERY trailing (circulation-
    door-free) strip row already an open-plan member OTHER than the first — the first public
    member is never eligible to be part of that trailing block, since it is where the front
    block's own cased opening to circulation lands. This is a PRECONDITION, not the proof:
    whether the flight's boundary can legitimately be marked wall-less is what `_build_access`'s
    declared OPEN_CONNECTION and the unchanged C6/C13 actually prove, on the geometry `plan_level`
    goes on to produce.
    """
    if not level.open_plan:
        return False
    # CLOSED_KITCHEN's KITCHEN is a PUBLIC-group room but NOT an open-plan member any more (it is
    # a closed, door-entered room on the corridor side) — excluded here exactly as `plan_level`
    # excludes it from `full_open_ids`/`door_exempt_ids`, so this precondition and the geometry
    # it gates agree on what "open" means.
    open_public = [r for r in level.rooms if r.group is ZoneGroup.PUBLIC
                  and not (level.ground_layout is GroundLayout.CLOSED_KITCHEN and r.zone_id == "KITCHEN")]
    if len(open_public) < 2:
        return False
    exempt_ids = frozenset(r.zone_id for r in open_public[1:])
    trailing = _trailing_door_free_rows(list(level.strip_rows), exempt_ids)
    trailing_ids = {r.zone_id for row in trailing for r in row}
    open_ids = {r.zone_id for r in open_public}
    return bool(trailing_ids) and trailing_ids <= open_ids


def _needs_door(room: ProgramRoom, open_ids: frozenset[str]) -> bool:
    return room.entered_from is None and room.zone_id not in open_ids


def _trailing_door_free_rows(rows: list, open_ids) -> list:
    """The rows at the END of the strip column that need no circulation door of their own — the
    block `ABSORBED` may recess behind the flight. Order preserved (front to rear)."""
    open_ids = frozenset(open_ids)
    n_rear = 0
    for row in reversed(rows):
        if any(_needs_door(r, open_ids) for r in row):
            break
        n_rear += 1
    return list(rows[len(rows) - n_rear:]) if n_rear else []


def plan_level(level: LevelProgram, footprint_w_m: float, footprint_h_m: float,
              x0_u: int, y0_u: int, seat: StairSeat, lobby_form: CoreLobbyForm, *,
              kind: str, allow_deficit: bool = False, allow_hard: bool = False,
              fixed_seam_m: float | None = None,
              ) -> tuple[list[ConceptCandidate], LevelFailure | None]:
    """One level, planned with the core band PINNED at `seat`/`lobby_form`, at plot-absolute
    origin `(x0_u, y0_u)`.

    Returns up to a small bounded set of candidates (a forced tree and its free twin), best
    first, or a `LevelFailure` naming the first cause reached. The SAME sizing-tier fallback
    ladder `_build` uses (normal -> shrunk -> over_preferred -> both) is the coordinator's to
    walk by calling this again with `allow_deficit`/`allow_hard` — this function tries exactly
    one tier per call, like `plan_layout` does for a single-wing candidate.
    """
    L = seat.stair_len_m
    if footprint_h_m - L < 2.0:
        return [], LevelFailure("OUTLINE_TOO_SHALLOW_FOR_STAIR",
                                f"{footprint_h_m:.2f} m depth leaves < 2.0 m ahead of a {L:.2f} m flight")
    if lobby_form is CoreLobbyForm.ABSORBED and not eligible_for_absorbed(level):
        return [], LevelFailure("ABSORBED_NOT_ELIGIBLE",
                                "the trailing strip rows are not all open-plan members")

    rooms, strip_rows, corridor_rooms, strip_room = _band_rooms(level, lobby_form)
    # TWO distinct public-room sets, not one (a bug this file had mid-write): the FULL open-plan
    # group (`full_open_ids`, for `_access`'s wall-less declaration and `eligible_for_absorbed`'s
    # own check) versus which of its members are EXEMPT from needing their own circulation
    # frontage (`door_exempt_ids`) — every member except the FIRST, which still takes a cased
    # opening from circulation and needs the same clearance a door would
    # (`_build_access`'s own docstring: "a cased opening only needs the ordinary door-placement
    # clearance"). Conflating the two under one name let LIVING's own cased-opening frontage go
    # unchecked.
    public_order = [r.zone_id for r in rooms if r.group is ZoneGroup.PUBLIC
                   and not (level.ground_layout is GroundLayout.CLOSED_KITCHEN and r.zone_id == "KITCHEN")]
    full_open_ids = frozenset(public_order) if level.open_plan and len(public_order) > 1 else frozenset()
    door_exempt_ids = frozenset(public_order[1:]) if level.open_plan and len(public_order) > 1 else frozenset()

    band_w = seat.corridor_w_m if lobby_form is CoreLobbyForm.ABSORBED else seat.band_w_m
    usable = footprint_w_m - band_w
    west_min = max(sum(r.template.min_short_side_m for r in row) for row in strip_rows) + _EDGE_INSET_ALLOWANCE_M
    if lobby_form is CoreLobbyForm.ABSORBED:
        west_min += seat.strip_w_m  # the front block also carries the strip's own width
    east_min = cg._column_min_width(list(corridor_rooms))
    if west_min + east_min > usable + 1e-9:
        return [], LevelFailure("COLUMN_WIDTH_EXCEEDED",
                                f"{west_min:.2f}+{east_min:.2f} > {usable:.2f} beside a {band_w:.2f} m band")

    net_depth = max(footprint_h_m - _EDGE_INSET_ALLOWANCE_M, 1e-6)
    base = cg.scale_program(rooms, footprint_w_m * footprint_h_m * ASSUMED_EFFICIENCY)
    areas = {z: sp.net_area_target_m2 for z, sp in base.items()}
    strip_flat = [r for row in strip_rows for r in row]
    west_rows = [cg._orient_row(list(row), True) for row in strip_rows]
    east_rows = [cg._orient_row(row, False) for row in
                cg._daylight_order(cg._rows_of(list(corridor_rooms)), north_is_envelope=True)]
    west_raw = cg._column_width(strip_flat, areas, net_depth)
    east_raw = cg._column_width(list(corridor_rooms), areas, net_depth)
    natural = usable * west_raw / max(west_raw + east_raw, 1e-6)

    if fixed_seam_m is not None:
        if not (west_min - 1e-9 <= fixed_seam_m <= usable - east_min + 1e-9):
            return [], LevelFailure("SEAM_PINNED_OUTSIDE_WINDOW",
                                    f"pinned west {fixed_seam_m:.2f} not in "
                                    f"[{west_min:.2f}, {usable - east_min:.2f}]")
        seams = [fixed_seam_m]
    else:
        seams = cg._seam_options(natural, west_min, usable - east_min)

    last: LevelFailure | None = None
    out: list[ConceptCandidate] = []
    for seam_w in seams:
        east_w = round((usable - seam_w) / 0.05) * 0.05
        west_w = footprint_w_m - band_w - east_w
        attempt = _attempt_seam(rooms, west_rows, east_rows, areas, west_w, east_w, footprint_h_m,
                                seat, lobby_form, strip_room, door_exempt_ids, full_open_ids,
                                allow_deficit, allow_hard)
        if isinstance(attempt, LevelFailure):
            last = attempt
            continue
        west_plan, east_plan, specs = attempt
        tree, hall_seed = _band_tree(west_plan, east_plan, west_w, east_w, band_w, footprint_h_m,
                                     seat, lobby_form, strip_room, door_exempt_ids, full_open_ids)
        access, groups = _access(rooms, level, west_plan, east_plan, footprint_h_m, seat,
                                 lobby_form, strip_room, hall_seed, door_exempt_ids, full_open_ids)
        wing = Wing("W", x0_u, y0_u, m_to_u(footprint_w_m), m_to_u(footprint_h_m), tree)
        fixture = Fixture(f"ML_{kind}_{lobby_form.value}", (wing,),
                          tuple(specs[r.zone_id] for r in rooms), access, open_groups=groups)
        rationale = (f"{kind} core-band ({lobby_form.value}): west {west_w:.2f} m | "
                    f"band {band_w:.2f} m | east {east_w:.2f} m over {footprint_h_m:.2f} m")
        candidate = ConceptCandidate(
            Concept(fixture, hall_seed, Side.N, footprint_w_m, footprint_h_m),
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, (0,), rationale,
            used_area_m2=round(footprint_w_m * footprint_h_m, 2), unused_wing_area_m2=0.0,
            wet_rooms=cg.wet_rooms_of([r for r in rooms if r.wet is not None]),
            shrunk=allow_deficit, over_preferred=allow_hard)
        out.append(candidate)
        out.append(_pinned_twin(candidate, strip_room.zone_id if strip_room is not None else None))
        break  # the FIRST seam that solves — nearest-natural-first, exactly like `plan_layout`
    if not out:
        return [], last or LevelFailure("NO_SEAM", "no seam accepted")
    return out, None


def _band_rooms(level: LevelProgram, lobby_form: CoreLobbyForm,
               ) -> tuple[list[ProgramRoom], list[tuple[ProgramRoom, ...]], tuple[ProgramRoom, ...],
                         ProgramRoom | None]:
    """The level's rooms PLUS the circulation rooms this band form needs, and the (front-to-rear)
    strip rows. Nothing here decides geometry — only which rooms exist for this form."""
    hall = ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION, ROOM_TEMPLATES[ProgramRole.HALL])
    stair = ProgramRoom("STAIR", ProgramRole.STAIRWELL, ZoneGroup.CIRCULATION,
                        ROOM_TEMPLATES[ProgramRole.STAIRWELL])
    rooms = list(level.rooms) + [hall, stair]
    strip_rows = list(level.strip_rows)
    strip_room: ProgramRoom | None = None

    if lobby_form in (CoreLobbyForm.FULL, CoreLobbyForm.SHRUNK):
        lobby = ProgramRoom("HALL_2", ProgramRole.HALL, ZoneGroup.CIRCULATION,
                            ROOM_TEMPLATES[ProgramRole.HALL])
        rooms.append(lobby)
    corridor_rooms = level.corridor_rooms
    if lobby_form is CoreLobbyForm.SHRUNK:
        # the strip room is the programme's own guest WC when it exists as one of ≥ 2 corridor-
        # side wet rooms (else it is that level's only bathroom and must not move), else an
        # engine STORAGE room — never a fabricated bathroom.
        wc = next((r for r in corridor_rooms if r.role is ProgramRole.TOILET), None)
        strip_room = wc if (wc is not None and len(corridor_rooms) > 1) else \
            ProgramRoom(_STRIP_ROOM_ID, _STRIP_ROOM_ROLE, ZoneGroup.SERVICE, ROOM_TEMPLATES[_STRIP_ROOM_ROLE])
        if strip_room is wc:
            # moved OUT of the corridor column so it is never planned there too — the single
            # most consequential line in this function: without it the same zone id ends up in
            # both columns, which Geometry Core cannot make sense of.
            corridor_rooms = tuple(r for r in corridor_rooms if r is not wc)
        else:
            rooms.append(strip_room)
    # ABSORBED: no lobby room, no strip room — the strip rows reach the band directly.

    return rooms, strip_rows, corridor_rooms, strip_room


def _attempt_seam(rooms, west_rows, east_rows, areas, west_w, east_w, fh, seat, lobby_form,
                  strip_room, door_exempt_ids, full_open_ids, allow_deficit, allow_hard):
    L, s = seat.stair_len_m, seat.strip_w_m
    if lobby_form is CoreLobbyForm.ABSORBED:
        front_rows, rear_rows = _split_front_rear(west_rows, door_exempt_ids)
        if not front_rows or not rear_rows:
            return LevelFailure("ABSORBED_NO_JOG", f"front {len(front_rows)} rear {len(rear_rows)} rows")
        col_w = west_w - s
        front_d = rear_d = None
        for rows, w, depth, where, ends in ((front_rows, west_w, fh - L, "front block", (True, False)),
                                            (rear_rows, col_w, L, "rear block", (False, True))):
            for row in rows:
                if cg._row_widths(row, w - _EDGE_INSET_ALLOWANCE_M) is None:
                    return LevelFailure(RejectionReason.ROW_WIDTH_EXCEEDED.value,
                                        f"{where}: {'+'.join(r.zone_id for r in row)} at {w:.2f}")
            depths, failure = cg._row_depths(rows, areas, w - _EDGE_INSET_ALLOWANCE_M, depth, where,
                                             ends_exterior=ends, allow_deficit=allow_deficit,
                                             allow_hard=allow_hard)
            if failure is not None:
                return LevelFailure(failure.reason.value, failure.detail)
            if where == "front block":
                front_d = depths
            else:
                rear_d = depths
        plans, plan_fail = cg._columns_at_seam(west_w, east_w, front_rows, east_rows, areas, fh,
                                               None, allow_deficit, allow_hard)
        if plans is None:
            return LevelFailure(plan_fail.reason.value, plan_fail.detail)
        west_plan = cg.ColumnPlan(west_w, list(front_rows) + list(rear_rows), list(front_d) + list(rear_d))
        east_plan = plans[1]
    else:
        plans, plan_fail = cg._columns_at_seam(west_w, east_w, west_rows, east_rows, areas, fh,
                                               None, allow_deficit, allow_hard)
        if plans is None:
            return LevelFailure(plan_fail.reason.value, plan_fail.detail)
        west_plan, east_plan = plans
        blocked = _frontage_failure(west_plan, fh, L, lobby_form, seat, door_exempt_ids, strip_room)
        if blocked:
            return blocked

    specs = _specs(rooms, [west_plan, east_plan], allow_hard, seat, lobby_form, fh, strip_room)
    failure = cg._specs_within_maxima(rooms, specs, "columns", allow_hard)
    if failure is not None:
        return LevelFailure(failure.reason.value, failure.detail)
    return west_plan, east_plan, specs


def _split_front_rear(west_rows: list[list[ProgramRoom]], open_ids: frozenset[str]):
    trailing = _trailing_door_free_rows(west_rows, open_ids)
    if not trailing:
        return west_rows, []
    return west_rows[:len(west_rows) - len(trailing)], trailing


def _frontage_failure(west_plan, fh, L, lobby_form, seat, open_ids, strip_room):
    """FULL/SHRUNK only: every strip-side room that needs a circulation door must reach the
    lobby (the part of the strip ahead of the stair/strip-room line) by >= a door's clearance."""
    lobby_depth = fh - L if lobby_form is CoreLobbyForm.FULL else _shrunk_lobby_depth(fh, L, seat, strip_room)
    y = 0.0
    for row, d in zip(west_plan.rows, west_plan.row_depths_m):
        for r in row:
            if strip_room is not None and r.zone_id == strip_room.zone_id:
                continue
            frontage = max(0.0, min(y + d, lobby_depth) - y)
            if _needs_door(r, open_ids) and frontage < DOOR_CLEAR_M - 1e-9:
                return LevelFailure("STAIR_BLOCKS_FRONTAGE",
                                    f"{r.zone_id} has {frontage:.2f} m of lobby frontage "
                                    f"(row {y:.2f}..{y + d:.2f}, lobby to {lobby_depth:.2f})")
        y += d
    return None


def _shrunk_lobby_depth(fh: float, L: float, seat: StairSeat, strip_room: ProgramRoom | None) -> float:
    """SHRUNK's lobby depth: as little as the strip room needs at its own aspect band, so the
    strip room absorbs as much of FULL's lobby as its template's shape allows — but never less
    than `DOOR_CLEAR_M`: the lobby still carries the first open-plan public room's own cased-
    opening frontage (`_frontage_failure`), and a lobby narrower than a door's clearance could
    never realize that opening regardless of what the strip room is willing to give up."""
    if strip_room is None:
        return fh - L
    net_w = seat.strip_w_m - _EDGE_INSET_ALLOWANCE_M
    max_strip_depth = strip_room.template.max_aspect_ratio * net_w + _EDGE_INSET_ALLOWANCE_M / 2
    # the floor is on the NET depth after wall insets (`_EDGE_INSET_ALLOWANCE_M`), not the
    # centerline one — a lobby whose net depth falls under the clearance realizes a leaf
    # Geometry Core refuses outright, at a centerline depth that LOOKS sufficient.
    return max(fh - L - max_strip_depth, DOOR_CLEAR_M + _EDGE_INSET_ALLOWANCE_M)


def _specs(rooms, plans, allow_hard, seat, lobby_form, fh, strip_room):
    specs: dict[str, ZoneSpec] = {}
    for plan in plans:
        net_w = plan.width_m - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(plan.rows, plan.row_depths_m):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths = cg._row_widths(row, net_w, net_d) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths):
                specs[room.zone_id] = cg._zone_spec(room, w, net_d, 0.60, 1.60, allow_hard)
    L, s, c = seat.stair_len_m, seat.strip_w_m, seat.corridor_w_m
    # HALL's own DEPTH in the tree is `fh - lobby_depth` for FULL/SHRUNK — the corridor runs
    # beside the whole rear block (the strip room's row AND the stair), not beside the stair
    # alone; for FULL, `lobby_depth == fh - L` so this reduces to `L` exactly, as it always has.
    lobby_depth = 0.0
    if lobby_form in (CoreLobbyForm.FULL, CoreLobbyForm.SHRUNK):
        lobby_depth = fh - L if lobby_form is CoreLobbyForm.FULL else _shrunk_lobby_depth(fh, L, seat, strip_room)
    corridor_depth = fh if lobby_form is CoreLobbyForm.ABSORBED else fh - lobby_depth
    t_hall = (c - _EDGE_INSET_ALLOWANCE_M) * max(corridor_depth - _EDGE_INSET_ALLOWANCE_M / 2, 0.1)
    specs["HALL"] = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION),
                             t_hall * 0.55, t_hall, t_hall * 1.75,
                             ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 12.0)
    if lobby_form in (CoreLobbyForm.FULL, CoreLobbyForm.SHRUNK):
        band_w = seat.band_w_m
        t_lobby = (band_w - _EDGE_INSET_ALLOWANCE_M) * max(lobby_depth - _EDGE_INSET_ALLOWANCE_M / 2, 0.1)
        specs["HALL_2"] = ZoneSpec("HALL_2", (ProgramRole.HALL, ProgramRole.CIRCULATION),
                                   max(t_lobby * 0.55, 0.5), t_lobby, t_lobby * 1.75, 1.0, 12.0)
        if strip_room is not None:
            strip_depth = fh - L - lobby_depth
            specs[strip_room.zone_id] = cg._zone_spec(strip_room, s - 0.10, max(strip_depth - 0.10, 0.5),
                                                       0.60, 1.60, allow_hard)
    t_stair = (s - 0.10) * (L - 0.10)
    specs["STAIR"] = ZoneSpec("STAIR", (ProgramRole.STAIRWELL,), t_stair * 0.8, t_stair,
                              min(t_stair * 1.3, 12.0), ROOM_TEMPLATES[ProgramRole.STAIRWELL].min_short_side_m, 4.2)
    return specs


def _band_tree(west_plan, east_plan, west_w, east_w, band_w, fh, seat, lobby_form, strip_room,
               door_exempt_ids, full_open_ids) -> tuple[Node, str]:
    """The pinned tree — every cut inside the band, and the two column splits either side of it,
    forced; row cuts inside each column are unforced (`_forced_chain`'s own row-depth cuts) and
    released again for the free twin by `_unforced_pinned`. Returns `(tree, hall_seed_zone_id)` —
    the zone id `_build_access` should treat as the level's public entrance into circulation.

    ABSORBED only: the front/rear split uses `door_exempt_ids` (every open-plan member except
    the first — the first is where the front block's cased opening to circulation lands, so it
    can never be part of the trailing block); the STRUCTURAL open-group marking passed to
    `_forced_chain` uses `full_open_ids` (every open-plan member, front row included) since the
    front AND rear rows together with STAIR are meant to read as one continuous open volume."""
    L, s, c = seat.stair_len_m, seat.strip_w_m, seat.corridor_w_m
    east_tree = cg._forced_chain(east_plan.rows, east_plan.row_depths_m,
                                 east_plan.width_m - _EDGE_INSET_ALLOWANCE_M, frozenset(),
                                 exterior_first=False)

    if lobby_form is CoreLobbyForm.ABSORBED:
        front_rows, rear_rows = _split_front_rear(west_plan.rows, door_exempt_ids)
        front_depths = west_plan.row_depths_m[:len(front_rows)]
        rear_depths = west_plan.row_depths_m[len(front_rows):]
        col_w = west_w - s
        front_tree = cg._forced_chain(front_rows, front_depths, west_w - _EDGE_INSET_ALLOWANCE_M,
                                      frozenset(full_open_ids), exterior_first=True)
        rear_tree = cg._forced_chain(rear_rows, rear_depths, col_w - _EDGE_INSET_ALLOWANCE_M,
                                     frozenset(), exterior_first=True) if rear_rows else Leaf("STAIR")
        west_tree = Split(Cut.H, front_tree,
                          Split(Cut.V, rear_tree, Leaf("STAIR"), m_to_u(col_w)) if rear_rows else rear_tree,
                          m_to_u(fh - L))
        tree = Split(Cut.V, west_tree, Split(Cut.V, Leaf("HALL"), east_tree, m_to_u(c)), m_to_u(west_w))
        return tree, "HALL"

    west_tree = cg._forced_chain(west_plan.rows, west_plan.row_depths_m,
                                 west_plan.width_m - _EDGE_INSET_ALLOWANCE_M, frozenset(),
                                 exterior_first=True)
    if lobby_form is CoreLobbyForm.FULL:
        strip: Node = Leaf("STAIR")
        lobby_depth = fh - L
    else:  # SHRUNK
        lobby_depth = _shrunk_lobby_depth(fh, L, seat, strip_room)
        strip_h = fh - L - lobby_depth
        strip = Split(Cut.H, Leaf(strip_room.zone_id), Leaf("STAIR"), m_to_u(strip_h))
    rear = Split(Cut.V, strip, Leaf("HALL"), m_to_u(s))
    band_tree = Split(Cut.H, Leaf("HALL_2"), rear, m_to_u(lobby_depth))
    tree = Split(Cut.V, west_tree, Split(Cut.V, band_tree, east_tree, m_to_u(band_w)), m_to_u(west_w))
    return tree, "HALL_2"


def _pinned_twin(candidate: ConceptCandidate, strip_room_id: str | None) -> ConceptCandidate:
    """`candidate` with every cut free EXCEPT the ones on the path to a core-band zone
    (`HALL`, `HALL_2`, `STAIR`, and the strip room — whatever zone id it carries, including a
    reused guest WC) — `_contains_hall` generalised to a pinned set (first report §5.2). The
    core's rectangle is then identical on both levels by construction; `building_validation.V1`
    proves it rather than trusting it."""
    pinned = frozenset({"HALL", "HALL_2", "STAIR"} | ({strip_room_id} if strip_room_id else set()))
    fixture = candidate.concept.fixture
    wings = tuple(replace(w, tree=_unforced_pinned(w.tree, pinned)) for w in fixture.wings)
    return replace(candidate, concept=replace(candidate.concept, fixture=replace(fixture, wings=wings)),
                  rationale=candidate.rationale + "; " + cg.FREE_TWIN_RATIONALE)


def _contains_pinned(node: Node, pinned: frozenset[str]) -> bool:
    if isinstance(node, Leaf):
        return node.zone_id in pinned
    return _contains_pinned(node.first, pinned) or _contains_pinned(node.second, pinned)


def _unforced_pinned(node: Node, pinned: frozenset[str]) -> Node:
    if not isinstance(node, Split):
        return node
    keep = node.fixed_at_u if _contains_pinned(node, pinned) else None
    return Split(node.cut, _unforced_pinned(node.first, pinned), _unforced_pinned(node.second, pinned), keep)


def _access(rooms, level, west_plan, east_plan, fh, seat, lobby_form, strip_room, hall_seed,
           door_exempt_ids, full_open_ids) -> tuple[DesiredAccessTopology, tuple[tuple[str, ...], ...]]:
    """Access topology: a room opens onto whichever circulation leaf it borders on the PLANNED
    depths (the lobby ahead of the stair line, or the corridor behind it) — the same rule
    `_build_access`'s `hall_borders_only_first_public` states for the front band, generalised."""
    L = seat.stair_len_m
    lobby_depth = (fh - L if lobby_form is CoreLobbyForm.FULL
                  else _shrunk_lobby_depth(fh, L, seat, strip_room) if lobby_form is CoreLobbyForm.SHRUNK
                  else 0.0)

    def hall_of(plan) -> dict[str, str]:
        """HALL_2 spans the band's FULL width (`Split(Cut.H, Leaf("HALL_2"), rear, lobby_depth)`
        sits ABOVE the strip/corridor V-split, not beside it) — so a CORRIDOR-side row at the
        front borders the lobby exactly as a strip-side one does. Both columns use the same
        `lobby_depth` threshold for that reason; there is no per-column exemption."""
        out, y = {}, 0.0
        for row, d in zip(plan.rows, plan.row_depths_m):
            front = max(0.0, min(y + d, lobby_depth) - y)
            which = "HALL_2" if (lobby_form is not CoreLobbyForm.ABSORBED and front >= DOOR_CLEAR_M - 1e-9) else "HALL"
            for r in row:
                out[r.zone_id] = which
            y += d
        return out

    borders = {**hall_of(west_plan), **hall_of(east_plan)}
    closed_kitchen = level.ground_layout is GroundLayout.CLOSED_KITCHEN
    public_ids = [r.zone_id for r in rooms if r.group is ZoneGroup.PUBLIC
                 and not (closed_kitchen and r.zone_id == "KITCHEN")]
    skip = {"STAIR", "HALL", "HALL_2"}
    if closed_kitchen:
        skip.add("KITCHEN")
    if strip_room is not None:
        skip.add(strip_room.zone_id)
    hall_for = {r.zone_id: borders.get(r.zone_id, "HALL") for r in rooms
               if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)}
    first_hall = borders.get(public_ids[0], hall_seed) if public_ids else hall_seed
    access, groups = cg._build_access([r for r in rooms if r.zone_id not in skip], [first_hall],
                                      public_ids, level.open_plan, hall_for)
    edges = list(access.edges)
    open_groups = list(groups)

    if lobby_form is CoreLobbyForm.ABSORBED:
        edges.append(DesiredAccessEdge("HALL", "STAIR", ConnectionKind.CASED_OPENING))
        rear_ids = [r.zone_id for row in _trailing_door_free_rows(west_plan.rows, door_exempt_ids) for r in row]
        open_groups = [g for g in open_groups if not set(g) & set(full_open_ids)]
        open_groups.append(tuple(full_open_ids) + ("STAIR",))
        if rear_ids:
            edges.append(DesiredAccessEdge(rear_ids[-1], "STAIR", ConnectionKind.OPEN_CONNECTION))
    elif lobby_form is CoreLobbyForm.FULL:
        edges += [DesiredAccessEdge("HALL_2", "HALL", ConnectionKind.OPEN_CONNECTION),
                 DesiredAccessEdge("HALL", "STAIR", ConnectionKind.OPEN_CONNECTION),
                 DesiredAccessEdge("HALL_2", "STAIR", ConnectionKind.OPEN_CONNECTION)]
        open_groups.append(("HALL_2", "STAIR", "HALL"))
    else:  # SHRUNK
        edges += [DesiredAccessEdge("HALL_2", "HALL", ConnectionKind.CASED_OPENING),
                 DesiredAccessEdge("HALL", "STAIR", ConnectionKind.CASED_OPENING)]

    if closed_kitchen:
        edges.append(DesiredAccessEdge(borders.get("KITCHEN", "HALL"), "KITCHEN", ConnectionKind.DOOR))
    if strip_room is not None:
        strip_hall = "HALL_2" if lobby_form is CoreLobbyForm.SHRUNK else "HALL"
        edges.append(DesiredAccessEdge(strip_hall, strip_room.zone_id, ConnectionKind.DOOR))

    return DesiredAccessTopology(tuple(edges)), tuple(open_groups)
