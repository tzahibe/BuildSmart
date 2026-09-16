"""Multi-level Phase 1 — level-program allocation: `(ProgramSpec) -> [ (strategy, ground, upper) ]`.

DOMAIN ONLY IN, GEOMETRY OUT. This stage turns a two-storey programme into a bounded, deterministic
list of `LevelAllocation` candidates — each a `PublicPrivateStrategy` (`spec.py`, Phase 0) paired
with a ground `LevelProgram` and an upper `LevelProgram`. No footprint, no seam, no stair rectangle:
those are `level_planner`'s and the coordinator's job (see
`MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` §3–§4 and the follow-up report §2–§3).

TWO STRATEGIES, per the accepted Phase 1 scope — no others:

  PUBLIC_BELOW_PRIVATE_ABOVE ("A")        every bedroom upstairs; the ground's public column
                                           cannot balance a private side of one safe room ± a WC
                                           (measured: 0/36 open, 0/36 repartitioned), so its
                                           ground layout is ALWAYS closed-kitchen.
  PUBLIC_PLUS_ONE_BEDROOM_BELOW ("C")     one secondary bedroom moves to the ground floor's strip
                                           column, which is what gives the corridor-side column
                                           (kitchen + safe room ± wet rooms) the width allocation A
                                           was missing. Tried OPEN first (a genuine LDK, no closed
                                           kitchen — 21/36 measured), then CLOSED as a fallback
                                           layout of the SAME strategy (14/36, where open's column
                                           widths do not work but the room list is unchanged).

`MASTER_SUITE_BELOW` ("B") is NOT implemented here — out of this phase's approved scope.

WET-ROOM SEMANTICS (follow-up report §3). `check_wet_room_invariants` is called ONCE, on the
whole `ProgramSpec`, exactly as a single-storey house calls it — this module adds no new gate
there. What IS new: after the split, a bedroom-carrying level that ends up with no full bathroom
of its own is a WARNING on that `LevelProgram`, never a refusal and never a fabricated room. The
building-level question ("does every requested wet room exist, exactly once, somewhere in the
building") is `building_validation.V8`, proved after both levels are realized — this stage never
proves it, only carries the rooms it was given.

SINGLE-LEVEL COMPATIBILITY. Nothing here is imported by `build_room_program`, `generate_concepts`
or `run_general`. A one-storey `ArchitecturalSpec` never reaches `allocate_levels` at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .concept_generator import ROOM_TEMPLATES, ProgramRoom, ZoneGroup, target_gross_area_m2
from .geometry_core.model import ProgramRole
from .spec import ProgramSpec, PublicPrivateStrategy, WetRoomKind
from .wet_rooms import check_wet_room_invariants, resolve_wet_rooms

#: Bedroom-class roles — the roles that make a level "bedroom-carrying" for the per-level
#: bathroom warning, and that `k` (§ below) counts over.
BEDROOM_CLASS_ROLES = (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM, ProgramRole.SAFE_ROOM)

#: The two strategies this phase implements, in the order they are tried — allocation A first
#: (the simpler, always-closed-kitchen ground), C second. `_allocate_levels`'s own ordering
#: within each strategy (open before closed, for C) is a layout fallback, not a ranking between
#: strategies: this module makes candidates available, in a fixed and reported order; nothing
#: here picks a "primary" (the accepted-scope exclusion — "no global A vs C ranking yet").
IMPLEMENTED_STRATEGIES = (PublicPrivateStrategy.PUBLIC_BELOW_PRIVATE_ABOVE,
                          PublicPrivateStrategy.PUBLIC_PLUS_ONE_BEDROOM_BELOW)


class GroundLayout(str, Enum):
    """How the ground floor's public rooms are arranged. Domain-level — no geometry here; the
    level planner turns this into a tree. See the module docstring for which strategy admits
    which layout, and the follow-up report §2 for why `OPEN` never plans under
    `PUBLIC_BELOW_PRIVATE_ABOVE`."""

    #: LIVING (+ DINING) one open-plan group; KITCHEN a normal member of the same group. A
    #: genuine open floor plan — no closed room, no extra door the brief did not ask for.
    OPEN = "open"
    #: KITCHEN moved to the corridor-side column as its own closed room, entered by its own door.
    #: A reinterpretation of `open_plan_living` and must be reported as one (`LevelProgram`'s
    #: `warnings`), never applied silently.
    CLOSED_KITCHEN = "closed_kitchen"


@dataclass(frozen=True)
class LevelProgram:
    """One level's rooms, already split into the two columns the core band sits between.

    `strip_rows` is FRONT TO REAR, explicit: the level planner needs to know which row sits at
    the flight's end (it must be the one row-group that needs no circulation door — see the
    stair-seat rule, first report §4.1) — that is an allocation fact, not something the level
    planner should infer from room order.
    """

    strategy: PublicPrivateStrategy
    rooms: tuple[ProgramRoom, ...]
    strip_rows: tuple[tuple[ProgramRoom, ...], ...]
    corridor_rooms: tuple[ProgramRoom, ...]
    open_plan: bool
    #: `GroundLayout.CLOSED_KITCHEN` reinterprets `open_plan_living`; `None` on the upper level
    #: (the concept does not apply — it has no public rooms).
    ground_layout: GroundLayout | None = None
    #: Warnings this LEVEL carries — never a refusal, never a fabricated room. Today's one
    #: producer: "this bedroom-carrying level has no full bathroom of its own" (§ below).
    warnings: tuple[str, ...] = ()

    @property
    def target_gross_m2(self) -> float:
        return target_gross_area_m2(list(self.rooms))

    @property
    def has_bedroom_class_room(self) -> bool:
        return any(r.role in BEDROOM_CLASS_ROLES for r in self.rooms)

    @property
    def has_full_bathroom(self) -> bool:
        return any(r.role is ProgramRole.BATHROOM for r in self.rooms)


@dataclass(frozen=True)
class LevelAllocation:
    """One candidate split of the programme across two levels."""

    strategy: PublicPrivateStrategy
    ground: LevelProgram
    upper: LevelProgram


def _room(zone_id: str, role: ProgramRole, group: ZoneGroup, entered_from: str | None = None,
         wet=None) -> ProgramRoom:
    return ProgramRoom(zone_id, role, group, ROOM_TEMPLATES[role], entered_from, wet)


def _wet_room(wet) -> ProgramRoom:
    role = ProgramRole.TOILET if wet.kind is WetRoomKind.GUEST_WC else ProgramRole.BATHROOM
    return ProgramRoom(wet.zone_id, role, ZoneGroup.SERVICE, ROOM_TEMPLATES[role], wet.host_zone, wet)


def allocate_levels(program: ProgramSpec) -> tuple[LevelAllocation, ...]:
    """The programme's TOTAL rooms -> a bounded, deterministic set of two-level candidates.

    Refuses (empty tuple) only when the WHOLE-BUILDING wet-room invariants (`wet_rooms.py`,
    unchanged) reject the programme outright, or when the programme has too few bedroom-class
    rooms for two levels to each get one (`stories == 2` needs >= 2). Every candidate this
    function DOES return is a legal room list; whether it can be PLANNED is the level planner's
    and Geometry Core's question, not this one's.
    """
    if check_wet_room_invariants(program):
        return ()
    if program.bedrooms < 2:
        return ()

    wet = resolve_wet_rooms(program)
    ensuite = [w for w in wet if w.kind is WetRoomKind.ENSUITE]
    shared = [w for w in wet if w.kind is WetRoomKind.SHARED_BATHROOM]
    wcs = [w for w in wet if w.kind is WetRoomKind.GUEST_WC]
    secondary_bedrooms = [f"BEDROOM_{i}" for i in range(1, program.bedrooms)]

    out: list[LevelAllocation] = []
    for strategy in IMPLEMENTED_STRATEGIES:
        down = secondary_bedrooms[-1:] if strategy is PublicPrivateStrategy.PUBLIC_PLUS_ONE_BEDROOM_BELOW else []
        candidate = _split(program, strategy, down, ensuite, shared, wcs, secondary_bedrooms)
        if candidate is None:
            continue
        out.append(candidate)
    return tuple(out)


def _split(program: ProgramSpec, strategy: PublicPrivateStrategy, down_bedrooms: list[str],
          ensuite, shared, wcs, secondary_bedrooms: list[str]) -> LevelAllocation | None:
    ground: list[ProgramRoom] = []
    upper: list[ProgramRoom] = []

    public = [_room("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC)]
    if program.open_plan_living:
        public += [_room("DINING", ProgramRole.DINING, ZoneGroup.PUBLIC),
                  _room("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC)]
    else:
        public.append(_room("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC))
    ground.extend(public)

    # entrance level holds the entrance sequence (HARD, first report §4.2) -> master stays
    # upstairs in both implemented strategies; MASTER_SUITE_BELOW is not implemented here.
    upper.append(_room("MASTER", ProgramRole.MASTER_BEDROOM, ZoneGroup.PRIVATE))
    for bedroom_id in secondary_bedrooms:
        (ground if bedroom_id in down_bedrooms else upper).append(
            _room(bedroom_id, ProgramRole.BEDROOM, ZoneGroup.PRIVATE))
    if program.safe_room:
        # ENGINE default (first report §4.2): the safe room stays on the entrance level unless a
        # rule pins it elsewhere — not decided here, not modelled here.
        ground.append(_room("SAFE_ROOM", ProgramRole.SAFE_ROOM, ZoneGroup.PRIVATE))
    for w in ensuite:
        upper.append(_wet_room(w))  # the master is always upstairs in this phase
    for w in wcs:
        ground.append(_wet_room(w))

    # Shared bathrooms: the first to whichever level has a bedroom-class room and none yet
    # (upper always does), the rest in the same order. Deterministic; never adds a room.
    shared_rooms = [_wet_room(w) for w in shared]
    remaining = list(shared_rooms)
    for level_rooms in (upper, ground):
        if remaining and any(r.role in BEDROOM_CLASS_ROLES for r in level_rooms) \
                and not any(r.role is ProgramRole.BATHROOM for r in level_rooms):
            level_rooms.append(remaining.pop(0))
    ground.extend(remaining)  # any still-spare shared bathroom goes to the entrance level

    warnings: list[str] = []
    for name, level_rooms in (("ground", ground), ("upper", upper)):
        has_bedroom = any(r.role in BEDROOM_CLASS_ROLES for r in level_rooms)
        has_bath = any(r.role is ProgramRole.BATHROOM for r in level_rooms)
        if has_bedroom and not has_bath:
            wc_only = any(r.role is ProgramRole.TOILET for r in level_rooms)
            warnings.append(f"{name} level has a bedroom-class room but no full bathroom of its "
                            f"own ({'a guest WC only' if wc_only else 'no wet room at all'})")

    if not any(r.role in BEDROOM_CLASS_ROLES for r in upper):
        return None  # the upper level needs SOMETHING private, or two storeys is meaningless

    ground_strip_rooms = [r for r in public]  # front to rear: LIVING, then DINING/KITCHEN
    ground_program = _ground_program(strategy, ground, ground_strip_rooms, warnings, program)
    upper_program = _upper_program(strategy, upper, warnings)
    if not ground_program.corridor_rooms or not upper_program.rooms:
        return None
    return LevelAllocation(strategy, ground_program, upper_program)


def _ground_program(strategy: PublicPrivateStrategy, ground: list[ProgramRoom],
                    public: list[ProgramRoom], warnings: list[str],
                    program: ProgramSpec) -> LevelProgram:
    """The GROUND `LevelProgram`, OPEN where the strategy admits it, else closed-kitchen.

    `PUBLIC_BELOW_PRIVATE_ABOVE` is closed-kitchen ALWAYS (measured 0/36 open, follow-up §2.1).
    `PUBLIC_PLUS_ONE_BEDROOM_BELOW` offers OPEN — the level planner tries it, and the coordinator
    falls back to CLOSED on the same strategy's room list if OPEN cannot be planned (measured:
    open 21/36, closed 14/36, on largely DIFFERENT briefs — a genuine fallback, not a strict
    ordering of quality). This function returns the OPEN form for C and the CLOSED form for A;
    `closed_variant` below derives C's closed fallback from the same rooms.
    """
    other = [r for r in ground if r not in public]
    if strategy is PublicPrivateStrategy.PUBLIC_BELOW_PRIVATE_ABOVE or not program.open_plan_living:
        return _closed_kitchen_program(strategy, ground, public, other, warnings)
    strip_rows = tuple((r,) for r in public)
    return LevelProgram(strategy, tuple(ground), strip_rows, tuple(other), True,
                        GroundLayout.OPEN, tuple(warnings))


def _closed_kitchen_program(strategy: PublicPrivateStrategy, ground: list[ProgramRoom],
                            public: list[ProgramRoom], other: list[ProgramRoom],
                            warnings: list[str]) -> LevelProgram:
    kitchen = next((r for r in public if r.role is ProgramRole.KITCHEN), None)
    if kitchen is None or len(public) < 2:
        # not open-plan to begin with (LIVING+KITCHEN only) -> nothing to close; the kitchen
        # already sits wherever LIVING does not, and both are strip rows.
        strip_rows = tuple((r,) for r in public)
        return LevelProgram(strategy, tuple(ground), strip_rows, tuple(other), False, None,
                            tuple(warnings))
    strip_public = [r for r in public if r is not kitchen]
    strip_rows = tuple((r,) for r in strip_public)
    corridor_rooms = (kitchen, *other)
    reinterpretation = ("the kitchen is closed and moved beside the corridor — the requested "
                        "open-plan living/dining stays open, the kitchen does not")
    return LevelProgram(strategy, tuple(ground), strip_rows, corridor_rooms, True,
                        GroundLayout.CLOSED_KITCHEN, (*warnings, reinterpretation))


def closed_fallback(allocation: LevelAllocation, program: ProgramSpec) -> LevelAllocation | None:
    """The CLOSED-kitchen ground layout for a candidate whose ground is currently OPEN — the
    coordinator's fallback when the open ground cannot be planned on any outline. `None` when the
    ground is already closed (allocation A) or has no kitchen to close."""
    if allocation.ground.ground_layout is not GroundLayout.OPEN:
        return None
    public = [r for row in allocation.ground.strip_rows for r in row]
    other = list(allocation.ground.corridor_rooms)
    closed = _closed_kitchen_program(allocation.strategy, list(allocation.ground.rooms), public,
                                     other, list(allocation.ground.warnings))
    if closed.ground_layout is not GroundLayout.CLOSED_KITCHEN:
        return None
    return LevelAllocation(allocation.strategy, closed, allocation.upper)


def _upper_program(strategy: PublicPrivateStrategy, upper: list[ProgramRoom],
                   warnings: list[str]) -> LevelProgram:
    """The UPPER `LevelProgram` with NO strip choice made yet (`strip_rows` empty) — the
    coordinator's `k` search (how many secondary bedrooms sit in front of the master on the
    strip column) fills it in via `with_upper_strip` below; this is bounded proportion-style
    search over an existing candidate, not a new allocation strategy."""
    return LevelProgram(strategy, tuple(upper), (), tuple(upper), False, None, tuple(warnings))


def with_upper_strip(allocation: LevelAllocation, strip_bedroom_count: int) -> LevelAllocation:
    """The upper `LevelProgram` with `k` secondary bedrooms placed on the strip column ahead of
    the master, which is always last on the strip (its ensuite, if any, travels behind it —
    first report §5.3/§4.2). `k` ranges `0 .. len(secondary bedrooms upstairs)`; bounded by the
    coordinator, never searched inside this module."""
    upper = allocation.upper
    rooms = list(upper.rooms)
    beds = [r for r in rooms if r.role is ProgramRole.BEDROOM or r.role is ProgramRole.SAFE_ROOM]
    master = [r for r in rooms if r.zone_id == "MASTER"]
    ensuite = [r for r in rooms if r.entered_from == "MASTER"]
    k = max(0, min(strip_bedroom_count, len(beds)))
    strip_members = beds[:k] + master + ensuite
    strip_rows = tuple((r,) for r in beds[:k]) + tuple((r,) for r in master) + tuple((r,) for r in ensuite)
    corridor_rooms = tuple(r for r in rooms if r not in strip_members)
    return LevelAllocation(allocation.strategy,
                           allocation.ground,
                           LevelProgram(upper.strategy, upper.rooms, strip_rows, corridor_rooms,
                                       False, None, upper.warnings))
