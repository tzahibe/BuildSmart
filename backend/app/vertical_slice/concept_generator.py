"""General Concept Generator V1.

Replaces the hand-authored canonical concept on the general path. `concept.py` keeps its
hard-coded 3BR+safe-room fixture ONLY as the frozen regression baseline that
`pipeline.run_demo` and the baseline tests pin; nothing general calls it any more.

WHAT WAS KEPT FROM THE CANONICAL CONCEPT (architectural patterns, re-derived generically):
  * open-plan LDK as one open group with no artificial doors between its zones;
  * a circulation spine that borders every private room, so no room is reached through another
    (destination-only rooms are never transit);
  * the safe room reached directly from circulation, never through a bedroom;
  * an ensuite paired with the master bedroom, entered from the bedroom rather than the hall;
  * forced cuts ONLY where two sibling subtrees must align, unforced everywhere else — the
    lesson that hand-forcing every depth produced two infeasible values in a row.

WHAT WAS DISCARDED (canonical-fixture accidents, not architecture):
  * every literal dimension (12.0 x 14.2, and the 4.7 / 1.6 / 3.45 / 5.0 / 4.5 / 3.8 cuts);
  * the fixed eleven-room list and its literal area bands;
  * the fixed access-edge list;
  * the two-segment hall (HALL_MAIN/HALL_SPUR): a single spine column bordering the whole
    private stack serves every room, so branching is generated only when a layout needs it.

TOPOLOGY BEFORE DIMENSIONS: this module decides grouping, zoning, open groups and the access
graph from the programme alone. Only after that does it choose a footprint and column widths,
and Geometry Core remains solely responsible for exact realization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum

from .concept import Concept
from .geometry_core.model import (
    UNIT_M,
    WALL_THICKNESS_M,
    WallType,
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    Node,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
    u_to_m,
)
from .safe_adapter import SolverGeometryCandidate
from .spec import (
    ENSUITE_HOST_BEDROOM,
    ENSUITE_HOST_MASTER,
    ArchitecturalSpec,
    CorridorRequirement,
    CorridorWidthMode,
    WetRoomKind,
    WetRoomRequirement,
    WetRoomStrength,
)
from .wet_rooms import (
    ResolvedWetRoom,
    WetRoomResolutionError,
    check_wet_room_invariants,
    default_wet_room_kinds,
    resolve_wet_rooms,
)
from .windows import DAYLIGHT_ROLES

# --------------------------------------------------------------------------- product policy
# PRODUCT POLICY placeholders, in the same sense as WALL_THICKNESS_M's safe-room entry: plausible
# working demo/architectural defaults, NOT verified regulation and NOT sourced from any external
# tool's output — see EXCESS_AREA_ALLOCATION_AUDIT and ROOM_AREA_CAPS_AND_WET_ROOM_WINDOW_REPORT
# for the review that produced these values. `elasticity` is this template's EXPANSION_PRIORITY:
# how much of a larger house's surplus area a role should absorb. It is the one field that answers
# "when there's extra room, who gets it" — everything below is ranked by it, deliberately:
#   LIVING / DINING / KITCHEN  >  MASTER_BEDROOM / BEDROOM  >  BATHROOM  >  HALL (circulation)
# HALL must never outrank BEDROOM, and neither must BATHROOM — circulation and wet rooms are the
# LOWEST-priority claims on surplus, not the highest, even though row/rectangle geometry used to
# let them win anyway (see `scale_program`'s `net_area_max_m2` and `_row_depths`' weight floor).
# SAFE_ROOM stays a separate case: elasticity 0.0, a regulated floor, never part of this ranking.

@dataclass(frozen=True)
class RoomTemplate:
    min_area_m2: float
    target_area_m2: float
    max_area_m2: float
    min_short_side_m: float
    max_aspect_ratio: float = 2.5
    #: EXPANSION_PRIORITY: this role's share of any surplus area, relative to the other roles in
    #: the same programme. Also caps how much geometric headroom ABOVE target this role's
    #: `net_area_max_m2` gets (see `scale_program`) — low priority means both "grows slowly" and
    #: "the tiling solver has little room to drift upward," not just the first of those.
    elasticity: float = 0.0


ROOM_TEMPLATES: dict[ProgramRole, RoomTemplate] = {
    ProgramRole.LIVING: RoomTemplate(16.0, 22.0, 46.0, 3.0, 2.5, elasticity=3.0),
    ProgramRole.DINING: RoomTemplate(10.0, 14.0, 30.0, 2.6, 3.0, elasticity=1.5),
    ProgramRole.KITCHEN: RoomTemplate(9.0, 13.0, 26.0, 2.4, 3.0, elasticity=1.0),
    # Caps set by the user directly: a standard bedroom is ~9 m2, a master 11-20 m2 — a
    # generous house should get MORE rooms, or a bigger hall/living room (elasticity above),
    # never one bedroom stretched to fill leftover footprint. Below the public tier's floor
    # (KITCHEN's 1.0), as the priority ranking requires.
    ProgramRole.MASTER_BEDROOM: RoomTemplate(11.0, 14.0, 20.0, 3.0, 2.5, elasticity=0.9),
    ProgramRole.BEDROOM: RoomTemplate(9.0, 10.5, 14.0, 2.6, 2.5, elasticity=0.5),
    # Regulated minimum: never scaled down, and not inflated just because the house is large.
    ProgramRole.SAFE_ROOM: RoomTemplate(9.0, 10.5, 14.0, 2.4, 2.5, elasticity=0.0),
    # max_area_m2 (12.0) is a conservative DEMO PRODUCT POLICY ceiling for a generous full
    # bathroom — not a verified regulatory or legal figure for any jurisdiction, and specifically
    # NOT copied from any external tool's suggested dimensions (regulatory/architectural
    # verification of this number is separate, future work). Left at its ORIGINAL 12.0 rather
    # than lowered further: `program_capacity_gross_m2` sums every role's max_area_m2 to decide
    # how big a footprint this room programme can responsibly fill, so a lower absolute cap here
    # shrinks that ceiling for every scenario, not just the excess-allocation ones — measured
    # regressions in otherwise-tight footprints when tried. The real tightening is `elasticity`
    # (below BEDROOM's, as the ranking requires): the geometric band a room can actually DRIFT
    # INTO above its target (`scale_program`'s `_expansion_headroom_mult`) is scaled by priority,
    # so a low-priority room's EFFECTIVE ceiling sits well under 12.0 in practice without lowering
    # the hard outer bound every footprint-capacity decision depends on.
    ProgramRole.BATHROOM: RoomTemplate(4.5, 6.5, 12.0, 1.6, 3.0, elasticity=0.15),
    # A WC-only room ("שירותים"). Every number here is smaller than BATHROOM's on purpose — this
    # room holds a pan and a basin, not a shower — and `min_short_side_m` is what actually makes
    # it read as a different room on the plan: the private column's rows span the column's full
    # width, so a wet room's SHORT side is its row depth, and 1.1 m against a bathroom's 1.6 m is
    # the visible difference between the two. PRODUCT POLICY placeholders like every other row in
    # this table, NOT verified regulation. `max_aspect_ratio` is looser than BATHROOM's (3.5 vs
    # 3.0) because the same column width divided by a shallower row is a longer rectangle, and
    # gating on 3.0 would reject the room for being exactly the shape this role asks for.
    ProgramRole.TOILET: RoomTemplate(2.2, 4.0, 6.0, 1.1, 3.5, elasticity=0.10),
    # ---- VOCABULARY, not new behaviour -------------------------------------------------------
    # The six rows below close the naming gap found by the real-plan realizability study: every
    # sampled plan contained at least one room this table could not name, so the study had to draw
    # a dressing room, a laundry, a store, a work nook and a stair core all as "שירותים". These are
    # PRODUCT POLICY placeholders like every other row here, NOT verified regulation.
    #
    # NOTHING PRODUCES THESE YET. `build_room_program` derives its rooms from `ProgramSpec`, which
    # has no field that asks for a store or a laundry, so no demo brief can currently reach them —
    # by design: adding the request path is a Concept Generator change and was explicitly out of
    # scope. What these rows buy today is that anything constructing a `ZoneSpec` directly (the
    # realizability harness, a future concept builder) can name the room correctly instead of
    # borrowing a wet room's identity.
    #
    # `elasticity` places each row in the ranking already documented at the top of this table
    # (PUBLIC > habitable PRIVATE > service/wet > circulation > fixed); none of them disturbs the
    # existing ordering, and in particular none outranks BEDROOM except the public-tier den.
    #
    # Public tier, below DINING and above KITCHEN: a den is a real sitting room and should take
    # surplus like one, but never ahead of the dining area it is secondary to.
    ProgramRole.FAMILY_ROOM: RoomTemplate(12.0, 16.0, 30.0, 2.8, 2.5, elasticity=1.2),
    # Habitable-private tier, deliberately EQUAL to BEDROOM rather than under it: a work room is
    # the same class of habitable room, and there is no architectural case for starving it first.
    ProgramRole.STUDY: RoomTemplate(6.0, 8.5, 14.0, 2.1, 2.5, elasticity=0.5),
    # Service tier, just UNDER BATHROOM: a walk-in closet is not a better claim on surplus area
    # than the bathroom next to it. min_short_side_m 1.5 = a 0.6 hanging rail plus a 0.9 passage,
    # which is what separates a room you walk into from a cupboard.
    ProgramRole.DRESSING_ROOM: RoomTemplate(3.0, 5.0, 9.0, 1.5, 3.0, elasticity=0.12),
    # Service tier, level with TOILET. Same 1.5 m short side, arrived at independently: a 0.6
    # appliance plus the 0.9 to stand in front of it and open its door.
    ProgramRole.LAUNDRY: RoomTemplate(2.5, 4.0, 8.0, 1.5, 3.0, elasticity=0.10),
    # The lowest expansion priority of any FURNISHED role in this table. A store that grows because
    # the house had area left over is the exact defect the caps work exists to prevent.
    ProgramRole.STORAGE: RoomTemplate(1.5, 3.0, 6.0, 1.0, 4.0, elasticity=0.05),
    # Elasticity 0.0, like SAFE_ROOM and for the same kind of reason: a stair's footprint is set by
    # the flight it holds, so surplus area must never flow here. `max_aspect_ratio` 4.0 because a
    # straight flight IS a long thin rectangle, and gating it at 2.5 would reject the room for
    # being the shape the role requires.
    ProgramRole.STAIRWELL: RoomTemplate(4.0, 6.0, 12.0, 1.1, 4.0, elasticity=0.0),
    # ---- end vocabulary ----------------------------------------------------------------------
    # Circulation: the LOWEST expansion priority of any room type below, below even BATHROOM —
    # a corridor is not a value-adding space, so it should be the last claim on surplus area, not
    # (as it was) the third-highest. max_area_m2 is left generous (30.0) as a geometric safety
    # ceiling for long double-loaded spines; `elasticity` is what actually restrains it now.
    ProgramRole.HALL: RoomTemplate(5.0, 11.0, 30.0, 1.2, 8.0, elasticity=0.1),
    # Absorbs whatever area the real programme cannot responsibly use — see `generate_concepts`.
    # A small non-zero min/target (not 0) matters: the front-band parti prices every public room's
    # SHARE of the band's width from this same template before the real shortfall is known, and a
    # zero there priced FLEX at exactly 0.00 m wide. Max is generous on purpose, since refusing to
    # plan a house because this one zone would be "too big" is exactly the outcome it exists to
    # avoid. Elasticity is the highest of any template so the surplus-redistribution loop in
    # `scale_program` lands here first, not on a bedroom.
    ProgramRole.FLEX: RoomTemplate(3.0, 6.0, 500.0, 1.0, 6.0, elasticity=5.0),
}

#: The room lobby of the hub parti (feature 005) — the compact circulation cell the private wing's
#: rooms open onto. PRODUCT POLICY placeholders like every row above, derived from a visual census
#: of 21 professional plans rather than from regulation: the lobby measures ~2.5-3.5 m a side, is
#: near-square, and carries 4-7 doors. It is NOT a `ROOM_TEMPLATES` row: the hub keeps zone id
#: "HALL" and role HALL (so C14, the twin's root->HALL rule and every label keyed on the hall are
#: unchanged) and merely carries this template instead of HALL's. Elasticity equals HALL's — a hub
#: is still circulation and never outranks a bedroom for surplus.
#: `max_area_m2` 16.0 (v2; v1 had 12.0): a flank that stacks a bedroom over a bathroom makes the
#: lobby ~4.6 m deep, and at aspect <= 1.5 that is ~3.1 x 4.6 = 14 m2 — the size of the TV-room
#: hubs in the larger reference plans (~3.5 x 4.5), not of the small lobbies the 12 m2 came from.
HUB_TEMPLATE = RoomTemplate(6.0, 8.5, 16.0, 2.4, 1.5, elasticity=0.1)

#: Net/gross ratio used to size a footprint from a programme. Measured 0.90-0.92 in the spike.
ASSUMED_EFFICIENCY = 0.90
#: Wall inset allowance used by the pre-check (exterior half 0.15 + partition half 0.05).
_EDGE_INSET_ALLOWANCE_M = 0.20
#: MEASURED AND REJECTED, left here so it is not retried: a tolerance on the row-depth comparison
#: in `_row_depths` (3 cm, with the rows shaved proportionally to keep tiling the column exactly).
#: The motivation was real — several scenarios' tightest attempt misses by single MILLIMETRES
#: (14.507 m against 14.500 m). The effect was not: it rescued 19 scenarios of a 418-scenario
#: sweep and 18 of those came back BELOW 80% of the area the person asked for (median 50%; a
#: 440 m2 request answered with a 107.8 m2 house). `_proportions` visits candidates nearest the
#: target first, so a near-target proportion that misses does so by far more than centimetres;
#: the only proportion inside the tolerance is the programme's own minimum footprint. Relaxing
#: the comparison therefore converts an honest refusal into a house half the requested size,
#: which is the built-area defect `_proportions`' ordering exists to prevent.
#: Floors are raised slightly above the bare minimum so the fixed point settles
#: ABOVE the pre-check threshold instead of a few centimetres under it.
_FLOOR_MARGIN = 1.06
#: Preferred footprint proportion (width:depth) before the candidate clamps it.
_FOOTPRINT_ASPECT_PREF = 0.82


class ZoneGroup(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SERVICE = "SERVICE"
    CIRCULATION = "CIRCULATION"


class ConceptStrategy(str, Enum):
    #: public column | hall spine | private column, all in one wing.
    SPINE_PUBLIC_PRIVATE = "SPINE_PUBLIC_PRIVATE"
    #: as above, but the service (wet) rooms are clustered at the far end of the private stack.
    SPINE_SERVICE_CLUSTER = "SPINE_SERVICE_CLUSTER"
    #: rooms on BOTH sides of the hall (double-loaded corridor) — halves the row count.
    SPINE_DOUBLE_LOADED = "SPINE_DOUBLE_LOADED"
    #: private stack split across two columns with a branched hall (for larger programmes).
    BRANCHED_TWO_STACK = "BRANCHED_TWO_STACK"
    #: public zones as a full-width band across the front, corridor and bedrooms behind it.
    FRONT_PUBLIC_BAND = "FRONT_PUBLIC_BAND"
    #: public band across the front; behind it a private wing organised around a compact room
    #: lobby that the bedrooms open onto from its flanks and from the band below it (feature 005).
    HUB_PRIVATE_WING = "HUB_PRIVATE_WING"
    #: programme allocated across two safe wings.
    MULTI_WING_SPLIT = "MULTI_WING_SPLIT"


class RejectionReason(str, Enum):
    INSUFFICIENT_TOTAL_AREA = "INSUFFICIENT_TOTAL_AREA"
    INSUFFICIENT_WING_AREA = "INSUFFICIENT_WING_AREA"
    WING_TOO_NARROW = "WING_TOO_NARROW"
    # ---- layout-geometry refusals ------------------------------------------------------------
    # These six replace a single `ROOM_BELOW_MINIMUM_DIMENSION`, which every layout failure was
    # funnelled through regardless of what actually bound. It claimed a room minimum in cases where
    # no room was ever sized (the footprint was narrower than the parti's own minimum width) and,
    # worse, in cases that were the exact OPPOSITE — a room pushed past its MAXIMUM area. A reason
    # code that names four unrelated causes cannot direct a fix, so each cause now says its own name.
    #: A column's stacked rows need more depth than the column has.
    COLUMN_DEPTH_EXCEEDED = "COLUMN_DEPTH_EXCEEDED"
    #: The rooms sharing one row cannot sit side by side across the column's net width.
    ROW_WIDTH_EXCEEDED = "ROW_WIDTH_EXCEEDED"
    #: The columns themselves cannot sit side by side across the footprint beside the hall.
    COLUMN_WIDTH_EXCEEDED = "COLUMN_WIDTH_EXCEEDED"
    #: A front-band public zone would be narrower than its own minimum short side.
    BAND_WIDTH_BELOW_MINIMUM = "BAND_WIDTH_BELOW_MINIMUM"
    #: The geometry would push a room ABOVE its template maximum area.
    ROOM_ABOVE_MAXIMUM_AREA = "ROOM_ABOVE_MAXIMUM_AREA"
    #: No footprint proportion was even tried: the programme's minimum width exceeds the candidate's.
    FOOTPRINT_BELOW_MINIMUM_WIDTH = "FOOTPRINT_BELOW_MINIMUM_WIDTH"
    SAFE_ROOM_CONSTRAINT = "SAFE_ROOM_CONSTRAINT"
    ACCESS_DEGREE_EXCEEDED = "ACCESS_DEGREE_EXCEEDED"
    OPEN_GROUP_INCOMPATIBLE = "OPEN_GROUP_INCOMPATIBLE"
    NO_SEAM_ALIGNMENT = "NO_SEAM_ALIGNMENT"
    CIRCULATION_WOULD_CROSS_PRIVATE = "CIRCULATION_WOULD_CROSS_PRIVATE"
    TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY = "TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY"


@dataclass(frozen=True)
class ConceptRejection:
    strategy: ConceptStrategy
    reason: RejectionReason
    detail: str
    wing_orders: tuple[int, ...] = ()


@dataclass(frozen=True)
class PlanFailure:
    """Why one footprint proportion could not be planned — the reason CODE travels with the text.

    The layout planners used to return a bare string, so the strategy loops above them had nothing
    to report but a hard-coded reason. Carrying the code out of the planner is what lets each
    failure keep its own name all the way into the log.

    `shortfall_m` is how far THIS attempt was from fitting, where that is a measurable distance.
    It exists so a strategy can report its NEAREST MISS instead of whichever proportion happened to
    be tried last — see `_nearest_miss`.
    """
    reason: RejectionReason
    detail: str
    shortfall_m: float | None = None


def _nearest_miss(current: PlanFailure | None, candidate: PlanFailure) -> PlanFailure:
    """The more informative of two failures: the one that came CLOSEST to fitting.

    A strategy tries many footprint proportions and, when none plans, has to report one of them.
    Reporting the last was close to meaningless: `_proportions` visits candidates nearest the
    person's requested area FIRST, so the last attempt is the one furthest from what they asked for
    — a 10 x 20 m request was being explained with numbers from a proportion it never wanted
    ("west column needs 13.19 m but has 8.20 m"). Failures with no measurable distance rank behind
    ones that have it, and ties keep the earlier attempt, which is the nearer to the target.
    """
    if current is None:
        return candidate
    if candidate.shortfall_m is None:
        return current
    if current.shortfall_m is None:
        return candidate
    return candidate if candidate.shortfall_m < current.shortfall_m else current


@dataclass(frozen=True)
class ProgramRoom:
    zone_id: str
    role: ProgramRole
    group: ZoneGroup
    template: RoomTemplate
    #: Entered from this room rather than from circulation (an ensuite).
    entered_from: str | None = None
    #: Wet rooms only: the RESOLVED kind this room was built to (never `UNSPECIFIED` — see
    #: `resolve_wet_rooms`). `None` for every other room.
    wet_kind: WetRoomKind | None = None


@dataclass(frozen=True)
class ConceptCandidate:
    concept: Concept
    strategy: ConceptStrategy
    wing_orders: tuple[int, ...]
    rationale: str
    used_area_m2: float
    unused_wing_area_m2: float


@dataclass(frozen=True)
class GenerationResult:
    candidates: tuple[ConceptCandidate, ...]
    rejections: tuple[ConceptRejection, ...]
    program: tuple[ProgramRoom, ...]

    @property
    def any(self) -> bool:
        return bool(self.candidates)


# --------------------------------------------------------------------------- 1. programme

def build_room_program(spec: ArchitecturalSpec) -> list[ProgramRoom]:
    """ArchitecturalSpec -> room groups. No scenario branching, no fixed room list."""
    program = spec.program
    rooms: list[ProgramRoom] = []

    def add(zone_id: str, role: ProgramRole, group: ZoneGroup, entered_from: str | None = None):
        rooms.append(ProgramRoom(zone_id, role, group, ROOM_TEMPLATES[role], entered_from))

    # Public zones. Open-plan yields three zones of one space; otherwise living + kitchen only,
    # because a separate dining room is a choice the spec does not currently express.
    if program.open_plan_living:
        add("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC)
        add("DINING", ProgramRole.DINING, ZoneGroup.PUBLIC)
        add("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC)
    else:
        add("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC)
        add("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC)

    add("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION)

    if program.bedrooms >= 1:
        add("MASTER", ProgramRole.MASTER_BEDROOM, ZoneGroup.PRIVATE)
    for i in range(1, program.bedrooms):
        add(f"BEDROOM_{i}", ProgramRole.BEDROOM, ZoneGroup.PRIVATE)

    if program.safe_room:
        add("SAFE_ROOM", ProgramRole.SAFE_ROOM, ZoneGroup.PRIVATE)

    # Wet rooms come from the brief's kinds, resolved to zone ids and hosts by `resolve_wet_rooms`
    # — which is also where the legacy default (a bare count) is turned into kinds.
    for wet in resolve_wet_rooms(program):
        role = ProgramRole.TOILET if wet.kind is WetRoomKind.GUEST_WC else ProgramRole.BATHROOM
        rooms.append(ProgramRoom(wet.zone_id, role, ZoneGroup.SERVICE, ROOM_TEMPLATES[role],
                                 wet.host_zone, wet.kind))

    return rooms


def programme_variants(spec: ArchitecturalSpec) -> list[list[ProgramRoom]]:
    """The room programme, plus arrangements of the SAME rooms that need less depth.

    WHY THIS EXISTS. The private column stacks one room per row; only an ensuite shares its
    bedroom's row. So 3 bedrooms + 2 wet rooms is four rows — 10.60 m of depth at the minimums —
    and measurement showed the planner needs about 149 m² of footprint before any proportion works,
    against a 99.6 m² geometric floor. One extra row costs roughly 40 m².

    A shared bathroom placed OFF A BEDROOM instead of off the corridor is the same rooms in three
    rows rather than four. That is an ordinary house — a second ensuite — not a compromise, and it
    is not chosen for the person: it is offered as an ADDITIONAL candidate so that a plan that fits
    the corridor-entered version still wins.

    WHAT A VARIANT MAY NOT DO. The literal programme is the brief's authoritative reading of who
    reaches which bathroom, and a variant exists to improve geometry, never to trade that away for
    area. So a variant is eligible only while it keeps every bathroom-access fact the brief relies
    on — see `variant_keeps_bathroom_access`. Without that rule the variant could hang the house's
    ONLY shared bathroom off a child's bedroom: measured in the failure-log sweep, every one of 11
    plans it "gained" and 4 production primaries it replaced had done exactly that, with a brief
    that asked for a guest WC ending up with no wet room anyone but the two bedrooms could reach.

    ORDER IS NOT A GUARANTEE. `generate_concepts` sorts candidates by closeness to the requested
    area when there is one, so a variant can be tried BEFORE the literal reading and win the
    primary. That is why eligibility is decided HERE, on semantics, and not left to ranking: an
    ineligible variant never enters the pool, whatever the order.

    Bounded by construction: at most one extra variant, and only when there is a shared bathroom
    to move, a secondary bedroom to attach it to, and another shared bathroom left behind.
    """
    base = build_room_program(spec)
    variants = [base]

    bedrooms = [r for r in base if r.role is ProgramRole.BEDROOM]
    # BATHROOM only, never the TOILET: a guest WC hung off a child's bedroom is not "a second
    # ensuite", it is a WC nobody else can reach.
    shared_wet = [r for r in base
                  if r.role is ProgramRole.BATHROOM and r.entered_from is None]
    if bedrooms and len(shared_wet) >= 1 and len(base) > 3:
        # The LAST shared wet room joins the LAST secondary bedroom: taking the first would move the
        # guest WC away from the entrance, which is the one wet room that wants to stay there.
        attach_to, moved = bedrooms[-1], shared_wet[-1]
        variant = [
            replace(room, entered_from=attach_to.zone_id) if room.zone_id == moved.zone_id else room
            for room in base
        ]
        if variant_keeps_bathroom_access(base, variant):
            variants.append(variant)
    return variants


def _shared_bathrooms(rooms: list[ProgramRoom]) -> list[ProgramRoom]:
    """Full bathrooms entered from circulation — the ones anyone in the house can use."""
    return [r for r in rooms if r.role is ProgramRole.BATHROOM and r.entered_from is None]


def variant_keeps_bathroom_access(base: list[ProgramRoom], variant: list[ProgramRoom]) -> bool:
    """Whether a programme variant preserves the brief's bathroom-access semantics.

    The rule: a variant must never consume the LAST shared bathroom. If the literal programme has
    a full bathroom reachable from circulation, the variant must still have one — a WC does not
    count, because a house whose only corridor-entered wet room has no shower gives every bedroom
    but the suites nowhere to wash. Making a shared bathroom private is a semantic change to the
    brief, and a variant may only make it where the house keeps a shared bathroom regardless.

    Written as the general predicate rather than a count on `wet_rooms` so it holds for any
    programme `build_room_program` may produce, and so a future variant that moves a different room
    is judged by the same fact.
    """
    return not _shared_bathrooms(base) or bool(_shared_bathrooms(variant))


#: How much geometric headroom ABOVE target a room's `net_area_max_m2` gets, as a function of its
#: own EXPANSION_PRIORITY (`elasticity`) — +45% at priority 1.0 (LIVING/DINING/KITCHEN-tier and
#: up, unchanged from before), tapering down to +10% at priority 0.0. The +10% FLOOR — rather than
#: zero headroom for a zero-priority room like SAFE_ROOM — is deliberately kept: Geometry Core's
#: exact-tiling solver needs SOME slack in every zone's [min, max] band to find a feasible tiling
#: at all, and collapsing a room's band to a single point (min == max) risks turning a policy
#: preference into a geometric infeasibility the room programme did not actually have. This is
#: what stops the solver from spending leftover residue on a low-value room just because its old,
#: flat +45% band happened to have room for it — the band itself now reflects the same priority
#: `scale_program` uses to set the target, instead of one multiplier applied to every room alike.
_MAX_HEADROOM_FRACTION = 0.45
_MIN_HEADROOM_FRACTION = 0.10


def _expansion_headroom_mult(elasticity: float) -> float:
    priority = min(1.0, max(0.0, elasticity))
    return 1.0 + _MIN_HEADROOM_FRACTION + (_MAX_HEADROOM_FRACTION - _MIN_HEADROOM_FRACTION) * priority


def scale_program(rooms: list[ProgramRoom], net_available_m2: float,
                  area_floors: dict[str, float] | None = None) -> dict[str, ZoneSpec]:
    """Fit the programme's target areas to the area actually available.

    Geometry Core tiles the footprint EXACTLY, so the room areas must be able to absorb all of
    it — a fixed template list would either overflow a small wing or leave a large one
    unsatisfiable. Surplus is distributed by `elasticity` (a room's EXPANSION_PRIORITY), so a
    bigger house grows its living space rather than its safe room or its bathrooms — and
    `net_area_max_m2` below caps that growth at the room's own `max_area_m2`, hard, so a
    low-priority room cannot be inflated past its product-policy ceiling just to tile the
    footprint exactly.
    """
    floors = area_floors or {}

    def floor_of(room: ProgramRoom) -> float:
        return max(room.template.min_area_m2, floors.get(room.zone_id, 0.0))

    base = sum(max(r.template.target_area_m2, floor_of(r)) for r in rooms)
    surplus = net_available_m2 - base
    weight_total = sum(r.template.elasticity for r in rooms) or 1.0

    targets: dict[str, float] = {}
    for room in rooms:
        t = room.template
        start = max(t.target_area_m2, floor_of(room))
        if surplus >= 0:
            extra = surplus * (t.elasticity / weight_total)
            targets[room.zone_id] = max(start, min(start + extra, max(t.max_area_m2, start)))
        else:
            # Shrink proportionally, but never below the room's floor.
            shrink = (-surplus) * (start / base)
            targets[room.zone_id] = max(start - shrink, floor_of(room))

    # Re-balance any residue onto the elastic rooms so the totals still add up. A room already AT
    # its own ceiling is dropped from the pool each pass — not just clamped — so a low-priority
    # room that hit its max stops diluting the split and the residue actually REDIRECTS to
    # whichever higher-priority rooms still have headroom, rather than being re-offered to (and
    # wasted on) a room that cannot take any more.
    residue = net_available_m2 - sum(targets.values())
    for _ in range(4):
        if abs(residue) < 0.05:
            break
        elastic = [r for r in rooms if r.template.elasticity > 0
                   and targets[r.zone_id] < max(r.template.max_area_m2, floor_of(r)) - 1e-9]
        if not elastic:
            break
        share = residue / sum(r.template.elasticity for r in elastic)
        for room in elastic:
            t = room.template
            targets[room.zone_id] = max(
                floor_of(room),
                min(targets[room.zone_id] + share * t.elasticity,
                    max(t.max_area_m2, floor_of(room))),
            )
        residue = net_available_m2 - sum(targets.values())

    specs: dict[str, ZoneSpec] = {}
    for room in rooms:
        t = room.template
        target = targets[room.zone_id]
        roles = (room.role,) if room.role is not ProgramRole.HALL else (
            ProgramRole.HALL, ProgramRole.CIRCULATION)
        specs[room.zone_id] = ZoneSpec(
            zone_id=room.zone_id,
            roles=roles,
            net_area_min_m2=max(floor_of(room), target * 0.70),
            net_area_target_m2=target,
            # HARD cap at the template's own max_area_m2 — never above it, full stop; the only
            # exception is a `floor_of(room)` that itself exceeds max_area_m2 (an external
            # regulatory floor overriding product policy), in which case max cannot legally sit
            # below the floor either, so it tracks the floor instead. `target` already respects
            # `max_area_m2` (see the loops above), but the solver tiles the footprint EXACTLY and
            # may otherwise spend residue anywhere inside [min, max] — which used to let a room
            # drift past its own cap purely to absorb space (DINING once came out at 30.66 m2
            # against a 30.0 cap). The band's WIDTH above target is scaled by this room's own
            # EXPANSION_PRIORITY (`_expansion_headroom_mult`), not a flat +45% for every room
            # alike — a low-priority room gets little headroom to drift into even within its cap.
            net_area_max_m2=max(
                min(target * _expansion_headroom_mult(t.elasticity), t.max_area_m2),
                target,
            ),
            min_short_side_m=t.min_short_side_m,
            max_aspect_ratio=t.max_aspect_ratio,
        )
    return specs


def target_gross_area_m2(rooms: list[ProgramRoom]) -> float:
    return sum(r.template.target_area_m2 for r in rooms) / ASSUMED_EFFICIENCY


def program_capacity_gross_m2(rooms: list[ProgramRoom]) -> float:
    """The largest house THIS programme can responsibly fill.

    `scale_program` never grows a room past its template `max_area_m2`, and Geometry Core tiles the
    footprint EXACTLY — so a footprint bigger than the sum of those maxima cannot be absorbed: the
    surplus has nowhere to go and the layout is rejected. This is a limit of the current room
    programme and its template table, NOT a statement that such a house is impossible to build.
    """
    return sum(r.template.max_area_m2 for r in rooms) / ASSUMED_EFFICIENCY


# --------------------------------------------------------------------------- 2. footprint

def minimum_footprint_width_m(rooms: list[ProgramRoom]) -> float:
    """A three-column layout cannot be narrower than its columns' own minimums. Deriving the
    footprint proportions from an aspect preference alone produced columns too narrow for a
    3 m master bedroom, so the requirement floors the width."""
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    hall = ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m + _EDGE_INSET_ALLOWANCE_M
    return _column_min_width(public) + hall + _column_min_width(private)


def footprint_of(candidate: Rect, width_m: float, depth_m: float) -> Rect:
    """A grid-aligned sub-rectangle of a proven-safe candidate, anchored to its street side and
    centred across it — the same convention the site stage uses."""
    w_u = min(candidate.w, max(1, m_to_u(width_m)))
    h_u = min(candidate.h, max(1, m_to_u(depth_m)))
    return Rect(candidate.x + (candidate.w - w_u) // 2, candidate.y, w_u, h_u)


def choose_footprint(candidate: Rect, target_gross_m2: float,
                     min_width_m: float = 0.0) -> Rect:
    """A grid-aligned sub-rectangle of a proven-safe candidate, sized for the programme.

    Anchored to the candidate's street side and centred across it — the same convention the
    site stage uses — so a candidate that exactly fits reproduces the canonical placement.
    """
    cw, ch = u_to_m(candidate.w), u_to_m(candidate.h)
    width = max(min_width_m, math.sqrt(target_gross_m2 * _FOOTPRINT_ASPECT_PREF))
    width = min(width, cw)
    depth = min(ch, target_gross_m2 / max(width, 1e-6))
    if width > cw:
        width = cw
        depth = min(ch, target_gross_m2 / width)
    w_u = min(candidate.w, max(1, m_to_u(width)))
    h_u = min(candidate.h, max(1, m_to_u(depth)))
    return Rect(candidate.x + (candidate.w - w_u) // 2, candidate.y, w_u, h_u)


# --------------------------------------------------------------------------- 3. tree synthesis

def _h_chain(nodes: list[Node]) -> Node:
    """Right-nested H chain. Unforced: nothing outside the column aligns to these boundaries."""
    if len(nodes) == 1:
        return nodes[0]
    return Split(Cut.H, nodes[0], _h_chain(nodes[1:]), None)


def _private_rows(rooms: list[ProgramRoom]) -> list[Node]:
    """Private + service rooms as stack rows. An ensuite is paired into its bedroom's row with a
    V-split, so the bedroom keeps the hall frontage and the ensuite is entered from it."""
    ensuites = {r.entered_from: r for r in rooms if r.entered_from}
    rows: list[Node] = []
    for room in rooms:
        if room.entered_from:
            continue
        ensuite = ensuites.get(room.zone_id)
        if ensuite is not None:
            rows.append(Split(Cut.V, Leaf(room.zone_id), Leaf(ensuite.zone_id), None))
        else:
            rows.append(Leaf(room.zone_id))
    return rows


def _rows_of(stack: list[ProgramRoom]) -> list[list[ProgramRoom]]:
    """Stack rows: an ensuite shares its bedroom's row (a V-split), everything else is its own."""
    present = {r.zone_id for r in stack}
    ensuites = {r.entered_from: r for r in stack
                if r.entered_from and r.entered_from in present}
    paired = {r.zone_id for r in ensuites.values()}
    rows: list[list[ProgramRoom]] = []
    for room in stack:
        if room.zone_id in paired:
            continue  # contributed by its bedroom's row
        mate = ensuites.get(room.zone_id)
        rows.append([room, mate] if mate else [room])
    return rows


def _orient_row(row: list[ProgramRoom], corridor_on_east: bool) -> list[ProgramRoom]:
    """Order a shared row so the member that needs corridor access actually touches it.

    A V-split places `row[0]` to the WEST and `row[1]` to the EAST, so the corridor-facing
    position depends on which side of the hall the column sits. Placing the bedroom first
    unconditionally was correct for the east column and wrong for the west one: there it put the
    ensuite against the corridor and buried the bedroom behind it, so HALL-MASTER was declared
    but no door could ever be built.

    The rule is general, not per-fixture: the member entered from CIRCULATION takes the
    corridor-facing slot; the member entered from its neighbour (an ensuite) takes the far one.
    """
    if len(row) < 2:
        return row
    corridor_facing = [r for r in row if r.entered_from is None]
    dependent = [r for r in row if r.entered_from is not None]
    if not corridor_facing or not dependent:
        return row
    return dependent + corridor_facing if corridor_on_east else corridor_facing + dependent


def _needs_column_end(row: list[ProgramRoom]) -> bool:
    """Whether this row's daylight depends on sitting at one of its column's exterior ends.

    A full-width row spans its column, so it always reaches the column's outer long edge. A
    SHARED row is split again by a V-cut: the outer slot takes that edge and the inner slot —
    the corridor-facing one, by `_orient_row` — is left with only the row's own north and south
    edges, which are building envelope only at the column's ends. So the row is at risk exactly
    when a corridor-facing member of a shared row is a room C8 requires a window for.
    """
    return len(row) >= 2 and any(r.entered_from is None and r.role in DAYLIGHT_ROLES for r in row)


def _daylight_order(rows: list[list[ProgramRoom]], *,
                    north_is_envelope: bool) -> list[list[ProgramRoom]]:
    """Order one column's rows so every shared row keeps its inner member on the envelope.

    See `_needs_column_end` for why a shared row is at risk. Which ends are envelope depends on
    the parti: in the COLUMN partis the column runs the full depth, so both its first row's
    north edge and its last row's south edge are exterior. In the FRONT-BAND parti only the
    south end is: the rear columns start under the public band, so a shared row placed first is
    enclosed on all four sides — north the band, south the next row, east the hall, west its own
    ensuite. That is exactly how a 3-bedroom closed-plan house put MASTER in a windowless box and
    failed C8, with an ensuite bathroom holding the only exterior wall of the pair.

    The same enclosure arises in a column parti as soon as a column carries TWO shared rows —
    which `programme_variants` produces by hanging the last shared bathroom off a secondary
    bedroom — with a full-width row after them: the second suite is then boxed in between the
    first suite, the full row, the hall and its own ensuite. Measured on a 15.00 x 11.73 m
    two-bedroom open-plan house, where SPINE_PUBLIC_PRIVATE solved three candidates and every one
    failed C8 on BEDROOM_1.

    Rows already at an exterior end are left where they are, and a column with no stranded
    shared row is returned untouched, so plans that were fine keep their drawing. When a shared
    row IS stranded, the at-risk rows take the available ends — one at the north end where that
    is envelope and the rest at the south, in their programme order — and the other rows keep
    their relative order between them. Putting a lone suite at the rear rather than the front is
    also the better arrangement architecturally: the master suite lands at the quiet rear rather
    than against the living space. With more at-risk rows than exterior ends the surplus stays
    internal; there is no arrangement of a single column that gives it a window, and C8 refuses
    that candidate so the search moves on.
    """
    last = len(rows) - 1
    stranded = [i for i, row in enumerate(rows)
                if _needs_column_end(row) and not (i == last or (north_is_envelope and i == 0))]
    if not stranded:
        return list(rows)
    at_risk = [row for row in rows if _needs_column_end(row)]
    others = [row for row in rows if not _needs_column_end(row)]
    head = at_risk[:1] if north_is_envelope and len(at_risk) >= 2 else []
    return head + others + at_risk[len(head):]


#: The corridor width used when the brief asks for none. Unchanged default behaviour: the column
#: partis derive a width from the hall's own area and clamp it here, and the front-band parti uses
#: the lower figure directly because its hall is short.
_DERIVED_HALL_CAP_M = 2.4
_FRONT_BAND_HALL_M = 1.4


def _corridor_wall_allowance_m(has_safe_room: bool) -> float:
    """Gross-to-net allowance for the corridor, budgeted for the WORST wall it can touch.

    A corridor between two partitions loses half of each (0.05 + 0.05). Where the programme has a
    safe room its RC envelope may abut the hall, and that side loses 0.15 instead. The planner fixes
    the corridor width BEFORE wall types are derived, so it cannot know which case applies and must
    budget for the worse one — under-budgeting realized a requested 1.60 m as 1.50 m of usable
    corridor, which C14 then (correctly) rejected. Over-budgeting only ever makes the corridor
    slightly wider than asked, which is why EXACT tolerates a small overshoot upward and none down.
    """
    half_partition = WALL_THICKNESS_M[WallType.PARTITION] / 2
    other = WALL_THICKNESS_M[WallType.RC_SAFE_ROOM] / 2 if has_safe_room else half_partition
    return half_partition + other


def _hall_width_m(corridor: CorridorRequirement | None, derived_m: float, *, cap_m: float,
                  has_safe_room: bool = False) -> float:
    """The corridor width to plan to, on the 5 cm grid.

    Without a requirement this is exactly what the code did before: the derived width, clamped by
    `cap_m`. With one, the REQUIREMENT wins and the cap does not apply — the cap exists to stop an
    area-derived hall from ballooning, not to overrule the person. The two constants it replaces
    (a 2.4 m ceiling and a fixed 1.4 m) are why a request for 1.8 m could never have been honoured
    even if it had been extracted.

    MINIMUM and PREFERENCE are floors, so a hall the layout wants wider stays wider. EXACT is
    planned to the stated width.
    """
    if corridor is None:
        return round(min(derived_m, cap_m) / UNIT_M) * UNIT_M

    # The person means the width they can WALK, so the requirement is a NET dimension. The planner
    # works in gross rectangles, so the wall insets have to be added back or a request for 1.6 m
    # would be realized as 1.4 m of usable corridor and C14 would (correctly) reject it.
    #
    # The allowance is ONE PARTITION THICKNESS: a corridor is flanked by two partitions and loses
    # half of each. `_EDGE_INSET_ALLOWANCE_M` is the wrong figure here — it budgets for an exterior
    # half — and over-granting by 10 cm made an EXACT 2.00 m request realize at 2.10 m and get
    # rejected for being too wide. Where a thicker wall (an RC safe-room envelope) actually abuts
    # the hall the net comes out narrower than this predicts, which is exactly what C14 measures
    # and reports rather than something the planner pretends to know in advance.
    gross = corridor.width_m + _corridor_wall_allowance_m(has_safe_room)
    if corridor.mode is CorridorWidthMode.EXACT:
        return round(gross / UNIT_M) * UNIT_M
    return round(max(derived_m, gross) / UNIT_M) * UNIT_M


def _proportions(min_width_m: float, max_width_m: float, max_depth_m: float,
                 gross_m2: float, target_m2: float | None) -> list[tuple[float, float]]:
    """The footprint proportions to try, IN THE ORDER THEY SHOULD BE TRIED.

    This ordering is the whole fix for the built-area defect. The search used to walk the width up
    from the programme's own minimum and take the first proportion that planned, with depth derived
    from the programme's target gross — so it always produced the SMALLEST feasible house and the
    user's requested area acted only as a ceiling. A 2-bedroom brief came out at 104.5 m² whether
    150, 180 or 200 m² was asked for.

    With a target, the same candidate proportions are simply visited nearest-target-area first, so
    the first feasible one is the closest to what the person asked for rather than the smallest that
    fits. The objective is to TRACK the target, not to maximise: a proportion 5 m² over the target
    is preferred to one 40 m² under it, and vice versa. Ties break toward the smaller house, then on
    dimensions, so the search stays deterministic.

    Without a target the original order is reproduced exactly, which is what keeps the site-driven
    baselines (L-shape, curved facade, obstacle, disconnected) numerically unchanged.
    """
    widths: list[float] = []
    w = min_width_m
    while w <= max_width_m + 1e-9 and len(widths) < 14:
        widths.append(round(w / 0.05) * 0.05)
        w += 0.5

    pairs: list[tuple[float, float]] = []
    for width in widths:
        base_depth = min(max_depth_m, gross_m2 / max(width, 1e-6))
        depth = base_depth
        step = max(0.25, (max_depth_m - base_depth) / 6) if max_depth_m > base_depth else 0.0
        for _ in range(7):
            pairs.append((width, depth))
            if step <= 0 or depth >= max_depth_m - 1e-9:
                break
            depth = min(max_depth_m, depth + step)

    if target_m2 is None:
        return pairs
    return sorted(pairs, key=lambda wd: (round(abs(wd[0] * wd[1] - target_m2), 4),
                                         round(wd[0] * wd[1], 4), wd[0], wd[1]))


@dataclass(frozen=True)
class ColumnPlan:
    width_m: float
    rows: list[list[ProgramRoom]]
    row_depths_m: list[float]


@dataclass(frozen=True)
class LayoutPlan:
    west: ColumnPlan
    east: ColumnPlan
    hall_w_m: float
    specs: dict[str, ZoneSpec]


def _row_widths(row: list[ProgramRoom], net_width: float) -> list[float] | None:
    """Widths for the members of a shared row, or None if they cannot all fit.

    Area share alone is not enough: an ensuite is ~30% of its bedroom by area, and 30% of a
    5 m column is 1.39 m — under a bathroom's 1.6 m minimum. Every member gets its minimum
    first; only the surplus is shared by area.
    """
    minimums = [r.template.min_short_side_m for r in row]
    if sum(minimums) > net_width + 1e-9:
        return None
    surplus = net_width - sum(minimums)
    areas = [r.template.target_area_m2 for r in row]
    total = sum(areas) or 1.0
    return [m + surplus * a / total for m, a in zip(minimums, areas)]


def _width_share(room: ProgramRoom, row: list[ProgramRoom]) -> float:
    """Area-proportional share, used only where no net width is available to clamp against."""
    total = sum(r.template.target_area_m2 for r in row)
    return room.template.target_area_m2 / total if total else 1.0 / len(row)


def _column_min_width(rooms: list[ProgramRoom]) -> float:
    """Narrowest a column may be: the widest minimum among its rows (a shared row needs both of
    its rooms side by side), plus the wall inset allowance."""
    widest = 0.0
    for row in _rows_of(rooms):
        widest = max(widest, sum(r.template.min_short_side_m for r in row))
    return widest + _EDGE_INSET_ALLOWANCE_M


def _column_width(rooms: list[ProgramRoom], specs_area: dict[str, float], net_depth: float) -> float:
    """A column runs the footprint's full depth, so its width is forced by area / depth."""
    return sum(specs_area[r.zone_id] for r in rooms) / max(net_depth, 1e-6)


#: How many column seams a single footprint proportion may try. Every one is a full re-plan of
#: both columns, and a FAILING strategy pays for all of them, so this is the runtime knob.
_MAX_SEAM_OPTIONS = 9
#: Step between seam candidates. Coarser than the 0.05 m planning grid on purpose: the seam only
#: has to land in the feasible WINDOW, and the row planner absorbs the remainder either way.
_SEAM_STEP_M = 0.25


def _seam_options(natural_m: float, lo_m: float, hi_m: float) -> list[float]:
    """West-column widths to try, the area-share value FIRST and then outward in even steps.

    Area share is the natural width only for the AREA term: a column runs the footprint's full
    depth, so `area / width` is the depth its rows need, and splitting the usable width by area
    equalises that quotient across both columns. It stops being natural the moment a row's
    MINIMUM SHORT SIDE binds instead, because a floor does not shrink when its column is widened.
    A column whose rows are floor-bound gains nothing from extra width, while the column opposite
    may be starving for it — so the seam that fits is the one that moves width from the first to
    the second. Which rows are floor-bound is itself a function of the width, so that point has no
    closed form and is searched.

    Nearest-first ordering is what makes this safe to add: the first candidate is exactly the seam
    the planner used before, so every layout that already planned still plans the same way, and
    only proportions that used to be REFUSED can reach the alternatives.
    """
    if hi_m < lo_m - 1e-9:
        return []
    natural = min(max(natural_m, lo_m), hi_m)

    def snapped(value: float) -> float:
        return round(min(max(value, lo_m), hi_m) / 0.05) * 0.05

    out = [snapped(natural)]
    offset = _SEAM_STEP_M
    while len(out) < _MAX_SEAM_OPTIONS and offset <= (hi_m - lo_m) + _SEAM_STEP_M:
        for candidate in (natural + offset, natural - offset):
            if lo_m - 1e-9 <= candidate <= hi_m + 1e-9:
                value = snapped(candidate)
                if all(abs(value - seen) > 1e-9 for seen in out):
                    out.append(value)
                    if len(out) >= _MAX_SEAM_OPTIONS:
                        break
        offset += _SEAM_STEP_M
    return out


def _columns_at_seam(west_w: float, east_w: float, west_rows: list[list[ProgramRoom]],
                     east_rows: list[list[ProgramRoom]], areas: dict[str, float],
                     footprint_h_m: float) -> tuple[list[ColumnPlan] | None, PlanFailure | None]:
    """Both columns planned at ONE seam position — the unit the seam search repeats."""
    plans = []
    for name, width, rows in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        if net_w <= 0:
            return None, PlanFailure(RejectionReason.COLUMN_WIDTH_EXCEEDED,
                                     f"{name} column has no net width at {width:.2f} m")
        for row in rows:
            if _row_widths(row, net_w) is None:
                return None, PlanFailure(
                    RejectionReason.ROW_WIDTH_EXCEEDED,
                    f"{' + '.join(r.zone_id for r in row)} cannot share the {name} "
                    f"column's {net_w:.2f} m of net width at their minimums")
        depths, why, short_m = _row_depths(rows, areas, net_w, footprint_h_m)
        if depths is None:
            return None, PlanFailure(RejectionReason.COLUMN_DEPTH_EXCEEDED,
                                     f"{name} column {why}", short_m)
        plans.append(ColumnPlan(width, rows, depths))
    return plans, None


def _row_depths(rows: list[list[ProgramRoom]], areas: dict[str, float], net_width: float,
                column_depth: float) -> tuple[list[float] | None, str, float | None]:
    """Row depths, chosen DIRECTLY rather than inferred from areas.

    The first design drove depth from area (`depth = area / width`) and then tried to steer the
    areas until the depths came out legal. That is an unstable fixed point: a small room in a
    wide column is always too shallow, and nudging its area moves the column width too. Choosing
    the depth first — floored by each row's own minimum short side — and deriving the areas from
    `width x depth` afterwards makes the result feasible BY CONSTRUCTION.

    On refusal the text names EVERY row and which of the two terms set its depth: the area
    quotient, or the row's own minimum short side. That distinction is the whole diagnosis — a
    column can overflow with no room minimum involved anywhere, and the old message asserted the
    opposite ("at their minimum dimensions") in every case.
    """
    wanted = []
    terms = []
    for row in rows:
        area = sum(areas[r.zone_id] for r in row)
        floor = max(r.template.min_short_side_m for r in row) + _EDGE_INSET_ALLOWANCE_M
        by_area = area / max(net_width, 1e-6)
        wanted.append(max(by_area, floor))
        ids = "+".join(r.zone_id for r in row)
        terms.append(f"{ids} {floor:.2f} (min side, area wanted {by_area:.2f})"
                     if floor > by_area else f"{ids} {by_area:.2f} (area)")
    total = sum(wanted)
    if total > column_depth + 1e-9:  # exact on purpose — see the rejected-tolerance note above
        return None, (f"needs {total:.2f} m of depth but has {column_depth:.2f} m "
                      f"[{'; '.join(terms)}]"), total - column_depth
    surplus = column_depth - total
    weights = [max(0.15, sum(r.template.elasticity for r in row)) for row in rows]
    wsum = sum(weights)
    return ([round((d + surplus * w / wsum) / 0.05) * 0.05
             for d, w in zip(wanted, weights)], "", None)


def plan_layout(rooms: list[ProgramRoom], west: list[ProgramRoom], east: list[ProgramRoom],
                hall_ids: list[str], footprint_w_m: float, footprint_h_m: float,
                corridor: CorridorRequirement | None = None,
                ) -> tuple[LayoutPlan | None, PlanFailure | None]:
    """Column widths, row depths and the resulting zone specs, all mutually consistent."""
    net_depth = max(footprint_h_m - _EDGE_INSET_ALLOWANCE_M, 1e-6)
    net_available = footprint_w_m * footprint_h_m * ASSUMED_EFFICIENCY
    base = scale_program(rooms, net_available)
    areas = {z: spec.net_area_target_m2 for z, spec in base.items()}

    hall_area = sum(areas[h] for h in hall_ids)
    hall_w = _hall_width_m(
        corridor,
        max(base[hall_ids[0]].min_short_side_m + _EDGE_INSET_ALLOWANCE_M,
            hall_area / net_depth + _EDGE_INSET_ALLOWANCE_M),
        cap_m=_DERIVED_HALL_CAP_M,
        has_safe_room=any(r.role is ProgramRole.SAFE_ROOM for r in rooms))

    usable = footprint_w_m - hall_w
    west_min = _column_min_width(west)
    east_min = _column_min_width(east)
    if west_min + east_min > usable + 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_WIDTH_EXCEEDED,
            f"columns need {west_min:.2f} + {east_min:.2f} m of width but only "
            f"{usable:.2f} m is available beside the {hall_w:.2f} m hall")
    # The hall sits between the two columns, so it is EAST of the west column and WEST of the
    # east one. Orient every shared row accordingly, before widths, specs or the tree are built.
    # Neither the rows nor their orientation depend on the seam, so both are settled once here.
    west_rows = [_orient_row(r, corridor_on_east=True)
                 for r in _daylight_order(_rows_of(west), north_is_envelope=True)]
    east_rows = [_orient_row(r, corridor_on_east=False)
                 for r in _daylight_order(_rows_of(east), north_is_envelope=True)]

    # Area share is the NATURAL width (a column runs the full depth, so width == area / depth).
    # Only then is a column raised to its own minimum, taking the difference from its neighbour
    # — allocating minimums first and sharing the surplus starved whichever column had the
    # larger programme. That value is now the FIRST seam tried rather than the only one: see
    # `_seam_options` for why area share stops being the right split once a row's floor binds.
    west_raw = _column_width(west, areas, net_depth)
    east_raw = _column_width(east, areas, net_depth)
    natural_w = usable * west_raw / max(west_raw + east_raw, 1e-6)

    plans: list[ColumnPlan] | None = None
    failure: PlanFailure | None = None
    for seam_w in _seam_options(natural_w, west_min, usable - east_min):
        east_w = round((usable - seam_w) / 0.05) * 0.05
        west_w = footprint_w_m - hall_w - east_w  # absorb rounding
        plans, failure = _columns_at_seam(west_w, east_w, west_rows, east_rows,
                                          areas, footprint_h_m)
        if plans is not None:
            break

    if plans is None:
        return None, failure

    # Areas now FOLLOW the geometry: each zone's band is centred on the rect it will occupy.
    specs: dict[str, ZoneSpec] = {}
    for plan in plans:
        net_w = plan.width_m - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(plan.rows, plan.row_depths_m):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths_in_row = _row_widths(row, net_w) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths_in_row):
                target = w * net_d
                specs[room.zone_id] = ZoneSpec(
                    room.zone_id, _roles_of(room),
                    net_area_min_m2=target * 0.60,
                    net_area_target_m2=target,
                    net_area_max_m2=target * 1.60,
                    min_short_side_m=room.template.min_short_side_m,
                    max_aspect_ratio=max(room.template.max_aspect_ratio,
                                         max(w, net_d) / max(1e-6, min(w, net_d)) + 0.3),
                )
    for hall_id in hall_ids:
        hall_depth = footprint_h_m / len(hall_ids)
        target = (hall_w - _EDGE_INSET_ALLOWANCE_M) * (hall_depth - _EDGE_INSET_ALLOWANCE_M / 2)
        specs[hall_id] = ZoneSpec(
            hall_id, (ProgramRole.HALL, ProgramRole.CIRCULATION),
            target * 0.55, target, target * 1.75,
            ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 12.0)

    return LayoutPlan(plans[0], plans[1], hall_w, specs), ""


def _roles_of(room: ProgramRoom) -> tuple[ProgramRole, ...]:
    if room.role is ProgramRole.HALL:
        return (ProgramRole.HALL, ProgramRole.CIRCULATION)
    return (room.role,)


def _forced_chain(rows: list[list[ProgramRoom]], depths: list[float], net_width: float) -> Node:
    """Right-nested H chain with every cut forced to the depth chosen above; a shared row gets a
    forced V cut at its members' width share."""
    def row_node(row: list[ProgramRoom]) -> Node:
        if len(row) == 1:
            return Leaf(row[0].zone_id)
        widths = _row_widths(row, net_width) or [net_width / len(row)] * len(row)
        first_w = widths[0] + _EDGE_INSET_ALLOWANCE_M / 2
        return Split(Cut.V, Leaf(row[0].zone_id), Leaf(row[1].zone_id),
                     m_to_u(round(first_w / 0.05) * 0.05))

    def build(index: int) -> Node:
        if index == len(rows) - 1:
            return row_node(rows[index])
        return Split(Cut.H, row_node(rows[index]), build(index + 1), m_to_u(depths[index]))

    return build(0)


# --------------------------------------------------------------------------- 5. access graph

def _build_access(rooms: list[ProgramRoom], hall_ids: list[str],
                  public_ids: list[str], open_plan: bool,
                  hall_for: dict[str, str],
                  hall_borders_only_first_public: bool = False,
                  ) -> tuple[DesiredAccessTopology, tuple[tuple[str, ...], ...]]:
    """Access topology from the programme — never from the rectangle dimensions.

    Rules applied, all general: circulation reaches every private and service room directly;
    the safe room is reached from circulation, never through a bedroom; an ensuite is entered
    from its bedroom; open-plan zones connect with OPEN_CONNECTION and therefore no doors; the
    living room's own entrance from circulation is a CASED_OPENING — no door leaf there, ever.

    CASED_OPENING rather than OPEN_CONNECTION: a wall-less join needs the two zones to share a
    FULL matching edge (`_discover_open_interfaces`), which circulation and the living room never
    do once any other room lines the same corridor — an empirical fact, checked by sweeping every
    programme x geometry combination this generator produces (rectangle, L-shape, obstacle,
    curved facade, disconnected site, open-plan on and off), and it was unrealized (C13) in all
    of them. A cased opening only needs the ordinary door-placement clearance, which the HALL and
    LIVING interface already has by construction — so the living room's entrance stays as open as
    the geometry actually allows, just without the leaf.

    `hall_borders_only_first_public` states a PARTI fact, not a dimension: in the front-band
    parti the public zones lie side by side across the front and the hall runs south from under
    the FIRST of them (`_plan_front_band` sizes that zone to span the hall's x-range exactly so
    the hall has a public neighbour at all). Every later band zone therefore begins at the hall's
    far edge and shares no boundary with it. Declaring HALL -> each public zone there produced a
    door that could never be built: with the kitchen closed rather than open-plan, HALL-KITCHEN
    was declared, C13 rejected it as unrealized and C5 found the kitchen unreachable. A closed
    band is a CHAIN — the hall enters the first zone, and each later zone is entered from its
    neighbour, which is the interface that actually exists. In the column partis every public
    zone is its own full-width row against the spine, so each really does border circulation and
    the flat form stays correct.
    """
    edges: list[DesiredAccessEdge] = []
    groups: list[tuple[str, ...]] = []

    if open_plan and len(public_ids) > 1:
        groups.append(tuple(public_ids))
        for a, b in zip(public_ids, public_ids[1:]):
            edges.append(DesiredAccessEdge(a, b, ConnectionKind.OPEN_CONNECTION))
        edges.append(DesiredAccessEdge(hall_ids[0], public_ids[0], ConnectionKind.CASED_OPENING))
    elif hall_borders_only_first_public:
        edges.append(DesiredAccessEdge(hall_ids[0], public_ids[0], ConnectionKind.CASED_OPENING))
        for a, b in zip(public_ids, public_ids[1:]):
            edges.append(DesiredAccessEdge(a, b, ConnectionKind.DOOR))
    else:
        for public_id in public_ids:
            kind = ConnectionKind.CASED_OPENING if public_id == public_ids[0] else ConnectionKind.DOOR
            edges.append(DesiredAccessEdge(hall_ids[0], public_id, kind))

    if len(hall_ids) > 1:
        groups.append(tuple(hall_ids))
        for a, b in zip(hall_ids, hall_ids[1:]):
            edges.append(DesiredAccessEdge(a, b, ConnectionKind.OPEN_CONNECTION))

    for room in rooms:
        if room.group in (ZoneGroup.PUBLIC, ZoneGroup.CIRCULATION):
            continue
        if room.entered_from:
            edges.append(DesiredAccessEdge(room.entered_from, room.zone_id, ConnectionKind.DOOR))
        else:
            edges.append(DesiredAccessEdge(hall_for[room.zone_id], room.zone_id, ConnectionKind.DOOR))

    return DesiredAccessTopology(tuple(edges)), tuple(groups)


# --------------------------------------------------------------------------- 6. strategies
#
# Every strategy is the SAME layout — west column | hall spine | east column — and differs only
# in how the programme is allocated between the two columns. The hall runs the full depth
# against both, so every room borders circulation directly and none is reached through another.

#: How many feasible footprint proportions a single strategy may offer when a target area is set.
#: One is not enough: `plan_layout` is a PRE-CHECK, and a proportion it accepts can still be
#: rejected by Geometry Core. Committing each strategy to exactly one proportion meant that when the
#: nearest-target proportion failed in the solver, the whole strategy was lost — a 3BR + 3 wet brief
#: that used to plan stopped planning entirely. Offering the nearest few lets the pipeline fall to
#: the next-closest instead of off a cliff. Bounded so the solver attempt count stays small.
_MAX_PROPORTIONS_PER_STRATEGY = 3


def _build(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
           strategy: ConceptStrategy, west: list[ProgramRoom], east: list[ProgramRoom],
           rationale: str) -> tuple[list[ConceptCandidate], ConceptRejection | None]:
    if not west or not east:
        return [], ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                    "allocation left a column empty")
    hall_ids = ["HALL"]
    gross = target_gross_area_m2(rooms)
    min_width = minimum_footprint_width_m(rooms)
    target_m2 = spec.program.target_built_area_m2
    corridor = spec.program.corridor

    # Bounded, deterministic search over footprint PROPORTIONS. A single aspect constant cannot
    # work: widen the footprint and the columns get wide enough but the rows get shallow; deepen
    # it and the reverse. Rather than guess, walk the width from the layout's own minimum up to
    # the candidate's, at 0.25 m steps, and take the first proportion the planner accepts.
    footprint = None
    plan = None
    failure: PlanFailure | None = None
    max_width = u_to_m(candidate.w)
    max_depth = u_to_m(candidate.h)

    # Depth is searched as well as derived: the minimum-dimension floors make rooms LARGER than
    # their template targets, so the programme genuinely needs more gross area than the template
    # estimate. Re-proportioning a fixed area can never satisfy that; letting the footprint grow
    # into the proven-safe candidate can. `_proportions` decides the ORDER — nearest the user's
    # target first when there is one (see its docstring).
    wanted = _MAX_PROPORTIONS_PER_STRATEGY if target_m2 is not None else 1
    found: list[tuple[Rect, LayoutPlan]] = []
    proportions = _proportions(min_width, max_width, max_depth, gross, target_m2)
    if not proportions:
        # No proportion was ever TRIED, so no room was ever sized. Reporting a room minimum here
        # (as the single catch-all reason did) named a cause that had not been reached yet.
        return [], ConceptRejection(
            strategy, RejectionReason.FOOTPRINT_BELOW_MINIMUM_WIDTH,
            f"the programme needs a footprint at least {min_width:.2f} m wide; this candidate "
            f"offers {max_width:.2f} m")
    for width, depth in proportions:
        trial = footprint_of(candidate, width, depth)
        tw, th = u_to_m(trial.w), u_to_m(trial.h)
        attempt, reason = plan_layout(rooms, west, east, hall_ids, tw, th, corridor)
        if attempt is not None:
            if any(f.w == trial.w and f.h == trial.h for f, _ in found):
                continue  # `footprint_of` clamps, so distinct proportions can land on one rectangle
            found.append((trial, attempt))
            if len(found) >= wanted:
                break
        else:
            failure = _nearest_miss(failure, reason)

    if not found:
        return [], ConceptRejection(strategy, failure.reason, failure.detail)

    built = [_concept_from(spec, rooms, candidate, strategy, rationale, footprint, plan)
             for footprint, plan in found]
    return built, None


def _unforced(node: Node) -> Node:
    """The same slicing tree with every forced cut position removed.

    A forced cut is the concept stage's GUESS at where a boundary lands, computed from a flat wall
    allowance (`_EDGE_INSET_ALLOWANCE_M`, exterior half + partition half). Geometry Core nets every
    leaf by the wall it actually gets on each side — 0.05 for a partition, 0.15 for an exterior or
    RC safe-room wall — and accepts a forced position only on exact equality. The two disagree by up
    to 0.30 m per column whenever a safe room or an exterior side is involved, and that gap was the
    single largest cause of refusal: 170 of 171 concept-stage successes that never became a design
    died on "no split ... at forced position", 139 of them with the safe room in the failing leaves.

    Without the forced positions the solver chooses each split itself, nearest the children's
    target-area ratio (`assign`), so the proportions the concept asked for are still what it aims
    at — it simply lands them where the walls allow. Measured over the 256 concept-stage successes:
    85 designs with forced cuts, 219 without, and the rescued plans track the requested area
    (median 90 %).

    The unforced trees are offered only after EVERY forced candidate, never interleaved with them:
    the pipeline takes the first candidate the solver realizes, so a plan that exists today is
    still found at the same position in the list and comes out with exactly today's geometry. The
    twins can only matter when no forced tree solved at all. Interleaving (each twin right behind
    its own forced tree) was tried first and rejected: an early strategy's twin pre-empted a later
    strategy's forced tree that used to win, and four site-driven baselines changed shape — one of
    them lost the physical openness of its living/dining/kitchen group.

    One family of cuts stays forced in the twin: every cut on the path from the root to the HALL
    leaf — the cuts that together fix the corridor's rectangle. Those positions are not a guess:
    the hall's width IS the corridor width, which `_hall_width_m` derives from the brief's corridor
    requirement when there is one, and its depth is what the band/rear cut leaves it; C14 measures
    the realized short side against the request. Releasing the two seams let the solver size a
    requested 6.00 m corridor at 1.20 m (the area-ratio choice); keeping the seams but releasing the
    band/rear cut let it give the front band almost everything and leave a 1.20 m deep hall — the
    same C14 refusal from the other axis. Where the forced tree fails geometrically, the service's
    retry-without-preference path used to produce a plan; a "solved" twin with a wrong corridor
    would pre-empt that path, so the corridor's shape is exactly what the twin may not touch.
    Everything that shapes a ROOM — row depths, ensuite and band widths — is a guess and is released.
    """
    if not isinstance(node, Split):
        return node
    keep = node.fixed_at_u if _contains_hall(node) else None
    return Split(node.cut, _unforced(node.first), _unforced(node.second), keep)


def _contains_hall(node: Node) -> bool:
    if isinstance(node, Leaf):
        return node.zone_id == "HALL"
    return _contains_hall(node.first) or _contains_hall(node.second)


def _free_twin(candidate: ConceptCandidate) -> ConceptCandidate:
    """The same candidate with every forced cut removed — see `_unforced`."""
    fixture = candidate.concept.fixture
    wings = tuple(replace(w, tree=_unforced(w.tree)) for w in fixture.wings)
    return replace(candidate,
                   concept=replace(candidate.concept, fixture=replace(fixture, wings=wings)),
                   rationale=f"{candidate.rationale}; {FREE_TWIN_RATIONALE}")


#: Marker appended to an unforced twin's rationale, so logs and diagnostics show which variant the
#: solver actually realized.
FREE_TWIN_RATIONALE = "cut positions chosen by the solver"


def _concept_from(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
                  strategy: ConceptStrategy, rationale: str,
                  footprint: Rect, plan: LayoutPlan) -> ConceptCandidate:
    """One realized proportion -> one `ConceptCandidate`. Split out of `_build` unchanged so that
    function can offer several proportions without duplicating any of this."""
    hall_ids = ["HALL"]
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)

    specs = plan.specs
    west_tree = _forced_chain(plan.west.rows, plan.west.row_depths_m,
                              plan.west.width_m - _EDGE_INSET_ALLOWANCE_M)
    east_tree = _forced_chain(plan.east.rows, plan.east.row_depths_m,
                              plan.east.width_m - _EDGE_INSET_ALLOWANCE_M)
    tree = Split(Cut.V, west_tree,
                 Split(Cut.V, Leaf("HALL"), east_tree, m_to_u(plan.hall_w_m)),
                 m_to_u(plan.west.width_m))

    public_ids = [r.zone_id for r in rooms if r.group is ZoneGroup.PUBLIC]
    hall_for = {r.zone_id: "HALL" for r in rooms
                if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)}
    access, groups = _build_access(rooms, hall_ids, public_ids,
                                   spec.program.open_plan_living, hall_for)

    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    fixture = Fixture(f"GEN_{strategy.value}", (wing,),
                      tuple(specs[r.zone_id] for r in rooms), access, open_groups=groups)
    return ConceptCandidate(
        Concept(fixture, "HALL", Side.N, fw, fh), strategy, (0,),
        rationale=(f"{rationale}; west {plan.west.width_m:.2f} m ({len(plan.west.rows)} rows) | "
                   f"hall {plan.hall_w_m:.2f} m | east {plan.east.width_m:.2f} m "
                   f"({len(plan.east.rows)} rows) over {fh:.2f} m"),
        used_area_m2=round(fw * fh, 2),
        unused_wing_area_m2=round(candidate.area_m2() - fw * fh, 2),
    )


def _allocations(rooms: list[ProgramRoom]) -> list[tuple[ConceptStrategy, list[ProgramRoom],
                                                         list[ProgramRoom], str]]:
    """The bounded, deterministic candidate set. Architectural priorities are explicit here:
    the public zones stay together nearest the entrance, bedrooms stay grouped, and wet rooms
    are either clustered or distributed — never scattered arbitrarily."""
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    private = [r for r in rooms if r.group is ZoneGroup.PRIVATE]
    service = [r for r in rooms if r.group is ZoneGroup.SERVICE]
    ensuite = [r for r in service if r.entered_from]
    shared_wet = [r for r in service if not r.entered_from]

    out = []
    # 1. Public one side, everything private the other.
    out.append((ConceptStrategy.SPINE_PUBLIC_PRIVATE, list(public),
                private + service, "public wing vs private wing"))
    # 2. Balanced: split the private rows so both columns carry a similar number.
    rows = _rows_of(private + service)
    half = max(1, (len(rows) + len(public)) // 2 - len(public))
    west_extra = [r for row in rows[:half] for r in row]
    east_rest = [r for row in rows[half:] for r in row]
    if east_rest:
        out.append((ConceptStrategy.SPINE_DOUBLE_LOADED, public + west_extra, east_rest,
                    "double-loaded: rooms on both sides of the hall"))
    # 3. Wet rooms clustered opposite the public zones.
    if shared_wet and len(private) > 1:
        out.append((ConceptStrategy.SPINE_SERVICE_CLUSTER,
                    public + private[:1] + ensuite,
                    private[1:] + shared_wet, "wet rooms clustered"))
    # 4. Evenly balanced by TOTAL row count, public included — the variant large programmes
    #    need, where even a half/half private split leaves one column too deep.
    if len(rows) >= 4:
        total = len(public) + len(rows)
        take = max(1, total // 2 - len(public) + 1)
        west_b = [r for row in rows[:take] for r in row]
        east_b = [r for row in rows[take:] for r in row]
        if east_b:
            out.append((ConceptStrategy.SPINE_DOUBLE_LOADED, public + west_b, east_b,
                        "balanced by total row count"))
    # 5. Bedrooms grouped opposite public + the shared wet rooms (an ensuite always travels
    #    with its bedroom, or it would be orphaned in a column its mate is not in).
    if shared_wet:
        out.append((ConceptStrategy.BRANCHED_TWO_STACK, public + shared_wet,
                    private + ensuite, "bedrooms grouped opposite public and service"))
    return out


def _forced_v_chain(rooms: list[ProgramRoom], widths: list[float]) -> Node:
    """Right-nested V chain with every cut forced to the width chosen for it."""
    def build(index: int) -> Node:
        if index == len(rooms) - 1:
            return Leaf(rooms[index].zone_id)
        return Split(Cut.V, Leaf(rooms[index].zone_id), build(index + 1), m_to_u(widths[index]))
    return build(0)


def _front_band_concept(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
                        ) -> tuple[ConceptCandidate | None, ConceptRejection | None]:
    """Public zones as a full-width band across the front; corridor and bedrooms behind it.

    This is the parti that unblocks large programmes. In the two-column spine the public zones
    sit IN a column and consume its depth — a living room needs ~5 m of it — so a 4BR + safe
    room + 3 wet programme wanted seven bedroom rows in whatever depth was left and never fitted.
    Moving the public zones ACROSS the front frees the entire rear depth for bedrooms, and the
    hall gains a third neighbour: it borders the public band to the north AND both bedroom
    columns to east and west.

    Why the corridor is still straight: a genuinely BENT (L or T) corridor cannot be one
    open-plan space in this engine, because open-marking requires the group's leaves to be
    siblings in the slicing tree and two siblings are always aligned rectangles. Declaring a
    bent hall as an open group would leave a real partition wall between its arms while the
    access graph claimed they were joined — connected on paper, walled in fact. So the shape of
    the parti changes instead of the shape of the corridor.
    """
    strategy = ConceptStrategy.FRONT_PUBLIC_BAND
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    if any(r.role is ProgramRole.FLEX for r in rooms):
        # This parti already has its OWN way of absorbing surplus: "the public band absorbs
        # whatever depth is left over — which is what a living room's elasticity is for" (see
        # `_plan_front_band`). Combining that with an explicit FLEX zone double-counts the same
        # surplus and produced both an inflated LIVING *and* a leftover FLEX zone in the same
        # plan. FLEX is for the SPINE partis, which have no such mechanism of their own.
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            "front band already absorbs surplus through its own elasticity; not combined with FLEX")
    if len(public) < 2 or len(private) < 3:
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            f"{len(public)} public / {len(private)} private rooms — too few to be worth a "
            f"separate front band")

    rows = _rows_of(private)
    if len(rows) < 3:
        return None, ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                      "too few private rows for two rear columns")
    # Try several rear splits, nearest-balanced first. Fixing the split at the midpoint made a
    # 4BR programme fail on a column that needed 11.6 m of depth where 9.95 m existed, while a
    # 3/4 split of the same rows fits — the balance point is a search variable, not a constant.
    midpoint = (len(rows) + 1) // 2
    split_options = sorted(range(1, len(rows)), key=lambda i: (abs(i - midpoint), i))

    gross = target_gross_area_m2(rooms)
    min_width = minimum_footprint_width_m(rooms)
    max_width, max_depth = u_to_m(candidate.w), u_to_m(candidate.h)

    plan = None
    footprint = None
    west_rows: list[list[ProgramRoom]] = []
    east_rows: list[list[ProgramRoom]] = []
    failure: PlanFailure | None = None
    proportions = _proportions(min_width, max_width, max_depth, gross,
                               spec.program.target_built_area_m2)
    if not proportions:
        return None, ConceptRejection(
            strategy, RejectionReason.FOOTPRINT_BELOW_MINIMUM_WIDTH,
            f"the programme needs a footprint at least {min_width:.2f} m wide; this candidate "
            f"offers {max_width:.2f} m")
    for width, depth in proportions:
        trial = footprint_of(candidate, width, depth)
        for split_at in split_options:
            west_try = [_orient_row(r, corridor_on_east=True)
                        for r in _daylight_order(rows[:split_at], north_is_envelope=False)]
            east_try = [_orient_row(r, corridor_on_east=False)
                        for r in _daylight_order(rows[split_at:], north_is_envelope=False)]
            attempt, reason = _plan_front_band(rooms, public, west_try, east_try,
                                               u_to_m(trial.w), u_to_m(trial.h))
            if attempt is not None:
                footprint, plan = trial, attempt
                west_rows, east_rows = west_try, east_try
                break
            failure = _nearest_miss(failure, reason)
        if plan is not None:
            break

    if plan is None or footprint is None:
        return None, ConceptRejection(strategy, failure.reason, failure.detail)

    band_depth, public_widths, west_w, hall_w, east_w, west_depths, east_depths, specs = plan
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)

    band_tree = _forced_v_chain(public, public_widths)
    rear = Split(Cut.V,
                 _forced_chain(west_rows, west_depths, west_w - _EDGE_INSET_ALLOWANCE_M),
                 Split(Cut.V, Leaf("HALL"),
                       _forced_chain(east_rows, east_depths, east_w - _EDGE_INSET_ALLOWANCE_M),
                       m_to_u(hall_w)),
                 m_to_u(west_w))
    tree = Split(Cut.H, band_tree, rear, m_to_u(band_depth))

    hall_for = {r.zone_id: "HALL" for r in private}
    access, groups = _build_access(rooms, ["HALL"], [r.zone_id for r in public],
                                   spec.program.open_plan_living, hall_for,
                                   hall_borders_only_first_public=True)

    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    fixture = Fixture(f"GEN_{strategy.value}", (wing,),
                      tuple(specs[r.zone_id] for r in rooms), access, open_groups=groups)
    return ConceptCandidate(
        Concept(fixture, "HALL", Side.N, fw, fh), strategy, (0,),
        rationale=(f"front public band {band_depth:.2f} m deep; rear west {west_w:.2f} m "
                   f"({len(west_rows)} rows) | hall {hall_w:.2f} m | east {east_w:.2f} m "
                   f"({len(east_rows)} rows)"),
        used_area_m2=round(fw * fh, 2),
        unused_wing_area_m2=round(candidate.area_m2() - fw * fh, 2),
    ), None


def _plan_front_band(rooms, public, west_rows, east_rows, fw, fh, corridor=None):
    """Band depth, public widths, rear column widths and row depths — all mutually consistent.

    Order matters, and it is the opposite of the obvious one. Sizing the rooms from the whole
    footprint first inflates the BEDROOMS when the footprint is generous, and inflated bedrooms
    need more rear depth than exists. So the rear is sized from the bedrooms' own programme,
    takes exactly the depth it needs, and the PUBLIC BAND absorbs whatever depth is left over —
    which is what a living room's elasticity is for.
    """
    private = [r for row in west_rows + east_rows for r in row]
    modest = scale_program(rooms, sum(r.template.target_area_m2 for r in rooms))
    areas = {z: spec.net_area_target_m2 for z, spec in modest.items()}

    hall_w = _hall_width_m(
        corridor,
        max(ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m + _EDGE_INSET_ALLOWANCE_M,
            _FRONT_BAND_HALL_M),
        cap_m=_FRONT_BAND_HALL_M,
        has_safe_room=any(r.role is ProgramRole.SAFE_ROOM for r in rooms))
    west = [r for row in west_rows for r in row]
    east = [r for row in east_rows for r in row]
    usable = fw - hall_w
    west_min, east_min = _column_min_width(west), _column_min_width(east)
    if west_min + east_min > usable + 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_WIDTH_EXCEEDED,
            f"rear columns need {west_min:.2f} + {east_min:.2f} m beside the "
            f"{hall_w:.2f} m hall but only {usable:.2f} m is available")

    west_raw = sum(areas[r.zone_id] for r in west)
    east_raw = sum(areas[r.zone_id] for r in east)
    west_w = usable * west_raw / max(west_raw + east_raw, 1e-6)
    west_w = round(min(max(west_w, west_min), usable - east_min) / 0.05) * 0.05
    east_w = round((usable - west_w) / 0.05) * 0.05
    west_w = fw - hall_w - east_w

    # How much depth the rear genuinely needs, from the bedrooms' own programme.
    rear_need = 0.0
    for name, width, rws in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        for row in rws:
            if _row_widths(row, net_w) is None:
                return None, PlanFailure(
                    RejectionReason.ROW_WIDTH_EXCEEDED,
                    f"{' + '.join(r.zone_id for r in row)} cannot share the rear "
                    f"{name} column's {net_w:.2f} m of net width at their minimums")
        need = sum(max(sum(areas[r.zone_id] for r in row) / max(net_w, 1e-6),
                       max(r.template.min_short_side_m for r in row) + _EDGE_INSET_ALLOWANCE_M)
                   for row in rws)
        rear_need = max(rear_need, need)

    # The first public zone must span the hall's x-range, or the hall has no public neighbour.
    needed_first = west_w + hall_w
    remaining = fw - needed_first
    other = public[1:]
    other_area = sum(areas[r.zone_id] for r in other) or 1.0
    widths = [needed_first]
    for room in other[:-1]:
        widths.append(round(remaining * areas[room.zone_id] / other_area / 0.05) * 0.05)
    last_w = fw - sum(widths)
    for room, w in zip(public, widths + [last_w]):
        if w - _EDGE_INSET_ALLOWANCE_M + 1e-6 < room.template.min_short_side_m:
            return None, PlanFailure(
                RejectionReason.BAND_WIDTH_BELOW_MINIMUM,
                f"{room.zone_id} would be {w:.2f} m wide in the front band, below its "
                f"{room.template.min_short_side_m} m minimum")

    band_min = max(r.template.min_short_side_m for r in public) + _EDGE_INSET_ALLOWANCE_M
    # Round the rear UP: rounding to nearest could land a couple of centimetres BELOW the
    # requirement this value was just derived from, and the row planner would then reject it.
    rear_depth = math.ceil(min(rear_need, fh - band_min) / 0.05 - 1e-9) * 0.05
    band_depth = round((fh - rear_depth) / 0.05) * 0.05
    rear_depth = fh - band_depth
    if rear_depth < 1.0 or band_depth < band_min - 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"rear needs {rear_need:.2f} m and the front band at least {band_min:.2f} m, "
            f"which does not fit {fh:.2f} m of depth")

    # The band takes whatever depth the rear does not need, and that is where surplus area used to
    # be dumped: at 220 m2 a 2-bedroom house came out with an 81.5 m2 living room against its own
    # 46 m2 maximum. Elasticity is meant to be BOUNDED by the template maxima, so a band deeper than
    # the public rooms can absorb is not a plan to accept — reject the proportion and let the
    # footprint search fall to a smaller one, which is exactly the behaviour the multi-proportion
    # search was added for.
    # The band's width per room is already fixed above, so the depth is what decides each public
    # room's area. The BINDING room is the one that reaches its own maximum first — the living room
    # in practice, whose width is forced to span the hall.
    binding = min(((r.template.max_area_m2 / max(w - _EDGE_INSET_ALLOWANCE_M, 1e-6), r)
                   for r, w in zip(public, widths + [last_w])), key=lambda t: t[0])
    band_cap_depth = binding[0] + _EDGE_INSET_ALLOWANCE_M / 2
    if band_depth > band_cap_depth + 1e-9:
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"a {band_depth:.2f} m front band would push {binding[1].zone_id} past its "
            f"{binding[1].template.max_area_m2:.0f} m2 maximum")

    depths = []
    for name, width, rws in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        d, why, short_m = _row_depths(rws, areas, net_w, rear_depth)
        if d is None:
            return None, PlanFailure(RejectionReason.COLUMN_DEPTH_EXCEEDED,
                                     f"rear {name} column {why}", short_m)
        depths.append(d)

    specs: dict[str, ZoneSpec] = {}
    net_band = band_depth - _EDGE_INSET_ALLOWANCE_M
    for room, w in zip(public, widths + [last_w]):
        target = (w - _EDGE_INSET_ALLOWANCE_M) * net_band
        specs[room.zone_id] = ZoneSpec(room.zone_id, _roles_of(room), target * 0.55, target,
                                       target * 1.70, room.template.min_short_side_m,
                                       max(room.template.max_aspect_ratio, 4.0))
    for width, rws, ds in ((west_w, west_rows, depths[0]), (east_w, east_rows, depths[1])):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(rws, ds):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths_in_row = _row_widths(row, net_w) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths_in_row):
                target = w * net_d
                specs[room.zone_id] = ZoneSpec(
                    room.zone_id, _roles_of(room), target * 0.55, target, target * 1.70,
                    room.template.min_short_side_m,
                    max(room.template.max_aspect_ratio,
                        max(w, net_d) / max(1e-6, min(w, net_d)) + 0.3))
    target_hall = (hall_w - _EDGE_INSET_ALLOWANCE_M) * (rear_depth - _EDGE_INSET_ALLOWANCE_M / 2)
    specs["HALL"] = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION),
                             target_hall * 0.5, target_hall, target_hall * 1.9,
                             ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 14.0)

    return (band_depth, widths, west_w, hall_w, east_w, depths[0], depths[1], specs), ""


# --------------------------------------------------------------------------- hub parti (005)

#: Hub widths to try, nearest the census centre first. Five values on the 0.30 m grid — the search
#: is bounded and deterministic like `_seam_options`.
_HUB_WIDTHS_M = (3.0, 2.7, 3.3, 2.4, 3.6)
#: A brief needs this many bedrooms before a room lobby is worth its area (spec Q5; references with
#: two bedrooms use a small entrance lobby instead).
_HUB_MIN_BEDROOMS = 3


@dataclass(frozen=True)
class HubAllocation:
    """Which room sits where around the lobby — see specs/005 data-model.md.

    v2: a flank is one room, or two stacked (top over bottom, an H split) — the reference pattern of
    a bedroom over a bathroom beside the lobby. Every flank room shares the lobby's side over its
    own depth, so each gets a door and each touches the wing's outer wall.
    """
    public: list[ProgramRoom]
    hub: ProgramRoom
    flank_west: list[ProgramRoom]   # top to bottom, 1-2 rooms
    flank_east: list[ProgramRoom]
    #: rooms along the band under the lobby, outer-west to outer-east; an ensuite sits next to its
    #: bedroom on the OUTER side, so the bedroom is the member that reaches the lobby
    foot: list[ProgramRoom]


@dataclass(frozen=True)
class HubPlan:
    band_depth_m: float
    public_widths_m: list[float]
    west_w_m: float
    hub_w_m: float
    east_w_m: float
    hub_d_m: float
    #: depth of each stacked flank room, top to bottom; sums to hub_d_m
    west_depths_m: list[float]
    east_depths_m: list[float]
    foot_depth_m: float
    foot_widths_m: list[float]
    specs: dict[str, ZoneSpec]
    doors_on_hub: int


def _hub_allocation(rooms: list[ProgramRoom], hub_w_m: float,
                    ) -> tuple[HubAllocation | None, ConceptRejection | None]:
    """Rooms -> flanks and foot band. Rejects when more rooms need a lobby door than v1 can seat.

    v1 seats FOUR rooms with a door on the lobby: one on each flank (full lobby depth, so any room
    qualifies) and two in the foot band, which meet under the lobby's centre line so each overlaps
    it by hub_w/2 — at least 1.2 m against the 1.10 m an opening needs
    (`INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M`). A third foot-band room could only reach the lobby
    at 1.1 m of overlap each under a 3.3 m lobby, i.e. as a 1.1 m wide toilet — deferred. An ensuite
    needs no lobby door (it is entered from its bedroom) and travels with it.

    Flanks take bedrooms first — a flank room comes out `hub_d` deep and its template's width, which
    is the near-square room the references have — then the safe room, then a wet room. The master
    suite goes to the foot band because its ensuite needs a slot beside it.
    """
    strategy = ConceptStrategy.HUB_PRIVATE_WING
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    hub = next(r for r in rooms if r.group is ZoneGroup.CIRCULATION)
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    rows = _rows_of(private)

    single = [row[0] for row in rows if len(row) == 1]
    suites = [row for row in rows if len(row) == 2]
    if len(suites) > 1:
        return None, ConceptRejection(strategy, RejectionReason.ACCESS_DEGREE_EXCEEDED,
                                      "the lobby's foot band seats one suite (bedroom + ensuite)")

    def rank(room: ProgramRoom) -> int:  # who gets a flank first
        if room.role is ProgramRole.BEDROOM:
            return 0
        if room.role is ProgramRole.SAFE_ROOM:
            return 1
        return 2  # wet / service

    ordered = sorted(single, key=rank)
    needing = len(rows)
    if needing > 6:
        return None, ConceptRejection(
            strategy, RejectionReason.ACCESS_DEGREE_EXCEEDED,
            f"{needing} rooms need a door on the lobby but it seats 6 "
            f"(two rooms on each flank, two in the foot band)")
    if needing < 4:
        return None, ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                      f"{needing} private rows — too few to organise around a lobby")

    # Seats fill in this order: the foot band (the suite plus one room, meeting under the lobby),
    # then the flank TOPS (bedrooms/safe room, near-square at the lobby's depth), then the flank
    # BOTTOMS — wet rooms stacked under a flank bedroom, each directly above the foot band's outer
    # room so the wet rooms end up back to back (the reference pattern).
    habitable = [r for r in ordered if rank(r) < 2]   # bedrooms, then the safe room
    wet = [r for r in ordered if rank(r) == 2]
    foot: list[ProgramRoom] = []
    if suites:
        bedroom, ensuite = suites[0]
        foot += [ensuite, bedroom]
    elif habitable:
        foot.append(habitable.pop(0))
    if len(habitable) < 2:
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            "a lobby needs a bedroom-class room on each flank")
    tops, habitable = habitable[:2], habitable[2:]
    second = habitable.pop(0) if habitable else (wet.pop(0) if wet else None)
    if second is None:
        return None, ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                      "no room left to share the foot band")
    foot.append(second)
    if habitable or len(wet) > 2:
        return None, ConceptRejection(
            strategy, RejectionReason.ACCESS_DEGREE_EXCEEDED,
            "only two wet rooms can stack under the flank bedrooms; left over: "
            f"{[r.zone_id for r in habitable + wet[2:]]}")
    bottoms = wet  # 0-2 wet rooms, west flank first (above the ensuite, when there is one)
    flank_west = [tops[0]] + bottoms[:1]
    flank_east = [tops[1]] + bottoms[1:2]
    return HubAllocation(public, hub, flank_west, flank_east, foot), None


def _flank_min_width_m(flank: list[ProgramRoom]) -> float:
    return max(r.template.min_short_side_m for r in flank) + _EDGE_INSET_ALLOWANCE_M


def _flank_min_depth_m(flank: list[ProgramRoom]) -> float:
    """Stacked rooms each need their own minimum short side plus the wall they lose."""
    return sum(r.template.min_short_side_m + _EDGE_INSET_ALLOWANCE_M for r in flank)


def _hub_min_width_m(alloc: HubAllocation, hub_w_m: float) -> float:
    return _flank_min_width_m(alloc.flank_west) + hub_w_m + _flank_min_width_m(alloc.flank_east)


def _plan_hub_wing(rooms: list[ProgramRoom], alloc: HubAllocation, fw: float, fh: float,
                   hub_w: float) -> tuple[HubPlan | None, PlanFailure | None]:
    """Band depth, lobby rectangle, flank and foot widths, foot depth and every ZoneSpec — mutually
    consistent, in the same order of decisions `_plan_front_band` takes: the rear (here the lobby
    band and the foot band) is sized from the rooms' own programme and the public band absorbs
    what is left, capped by the binding public room's maximum."""
    from .doors import DOOR_MARGIN_M, INTERIOR_DOOR_WIDTH_M
    opening_m = INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M
    inset = _EDGE_INSET_ALLOWANCE_M

    modest = scale_program(rooms, sum(r.template.target_area_m2 for r in rooms))
    areas = {z: spec.net_area_target_m2 for z, spec in modest.items()}

    # Lobby depth: deep enough for the deeper flank (stacked rooms add up) and for itself, inside
    # its own aspect band.
    flanks = [alloc.flank_west, alloc.flank_east]
    floors = [_flank_min_depth_m(f) for f in flanks] + [
        HUB_TEMPLATE.min_short_side_m + inset,
        areas[alloc.hub.zone_id] / max(hub_w - inset, 1e-6) + inset / 2]
    hub_d = round(max(floors) / 0.05) * 0.05
    hub_d = max(hub_d, round(hub_w / HUB_TEMPLATE.max_aspect_ratio / 0.05) * 0.05)
    if hub_d > hub_w * HUB_TEMPLATE.max_aspect_ratio + 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"a {hub_w:.2f} m lobby would need {hub_d:.2f} m of depth for its flanks, past its "
            f"{HUB_TEMPLATE.max_aspect_ratio} aspect", hub_d - hub_w * HUB_TEMPLATE.max_aspect_ratio)
    if (hub_w - inset) * (hub_d - inset / 2) > HUB_TEMPLATE.max_area_m2 + 1e-9:
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"a {hub_w:.2f} x {hub_d:.2f} m lobby exceeds its {HUB_TEMPLATE.max_area_m2:.0f} m2 maximum")

    # Depths within a stacked flank: each room its minimum, the surplus by area share.
    def stacked(flank: list[ProgramRoom]) -> list[float]:
        mins_d = [r.template.min_short_side_m + inset for r in flank]
        spare = hub_d - sum(mins_d)
        total = sum(areas[r.zone_id] for r in flank) or 1.0
        depths = [m + spare * areas[r.zone_id] / total for m, r in zip(mins_d, flank)]
        depths = [round(d / 0.05) * 0.05 for d in depths[:-1]]
        return depths + [hub_d - sum(depths)]
    west_depths, east_depths = stacked(alloc.flank_west), stacked(alloc.flank_east)

    # Flank widths: minimums first, surplus by area — the `_row_widths` rule across the lobby band;
    # a stacked flank is as wide as its widest member wants.
    mins = [_flank_min_width_m(f) for f in flanks]
    wants = [max(m, max(areas[r.zone_id] / max(d - inset / 2, 1e-6) + inset
                        for r, d in zip(f, ds)))
             for m, f, ds in zip(mins, flanks, (west_depths, east_depths))]
    usable = fw - hub_w
    if sum(mins) > usable + 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_WIDTH_EXCEEDED,
            f"flanks need {mins[0]:.2f} + {mins[1]:.2f} m beside a {hub_w:.2f} m lobby but the "
            f"footprint is {fw:.2f} m wide", sum(mins) + hub_w - fw)
    flank_area = [sum(areas[r.zone_id] for r in f) for f in flanks]
    total_want = sum(wants)
    if total_want <= usable:
        share = [w + (usable - total_want) * a / max(sum(flank_area), 1e-6)
                 for w, a in zip(wants, flank_area)]
    else:
        share = [m + (usable - sum(mins)) * (w - m) / max(total_want - sum(mins), 1e-6)
                 for m, w in zip(mins, wants)]
    west_w = round(share[0] / 0.05) * 0.05
    east_w = fw - hub_w - west_w

    # Foot band: one row across the full width. The two members that need a lobby door meet under
    # the lobby's centre line, so each overlaps the lobby by hub_w/2 >= 1.2 m > the 1.10 m an
    # opening needs. An ensuite sits outside its bedroom and takes its own minimum plus a share of
    # what its side has to spare; the bedroom keeps the rest up to the centre line.
    doored = [r for r in alloc.foot if not r.entered_from]
    # The boundary between the two door-needing rooms may sit anywhere both still overlap the lobby
    # by a full opening; inside that window it follows their area shares. (v1 pinned it to the
    # lobby's centre line, which gave the master everything up to the centre and a 1.59 aspect.)
    lo, hi = west_w + opening_m, west_w + hub_w - opening_m
    if hi + 1e-6 < lo:
        return None, PlanFailure(
            RejectionReason.ROW_WIDTH_EXCEEDED,
            f"a {hub_w:.2f} m lobby cannot give two foot-band rooms {opening_m:.2f} m of shared "
            f"edge each", lo - hi)
    west_group = [r for r in alloc.foot[:alloc.foot.index(doored[1])]]
    east_group = [r for r in alloc.foot[alloc.foot.index(doored[1]):]]
    a_west = sum(areas[r.zone_id] for r in west_group)
    a_east = sum(areas[r.zone_id] for r in east_group)
    wanted_boundary = fw * a_west / max(a_west + a_east, 1e-6)
    centre = round(min(max(wanted_boundary, lo), hi) / 0.05) * 0.05
    widths: list[float] = []
    for i, room in enumerate(alloc.foot):
        if room.entered_from:
            continue
        side_w = centre if room is doored[0] else fw - centre
        mate = next((e for e in alloc.foot if e.entered_from == room.zone_id), None)
        if mate is None:
            widths.append(side_w)
            continue
        mate_min = mate.template.min_short_side_m + inset
        room_min = room.template.min_short_side_m + inset
        if mate_min + room_min > side_w + 1e-9:
            return None, PlanFailure(
                RejectionReason.ROW_WIDTH_EXCEEDED,
                f"{room.zone_id} + {mate.zone_id} need {room_min + mate_min:.2f} m on their side of "
                f"the lobby but have {side_w:.2f} m", room_min + mate_min - side_w)
        spare = side_w - mate_min - room_min
        mate_w = mate_min + spare * areas[mate.zone_id] / max(areas[mate.zone_id] + areas[room.zone_id], 1e-6)
        mate_w = round(mate_w / 0.05) * 0.05
        # the ensuite is listed before its bedroom on the west side, after it on the east side
        if alloc.foot.index(mate) < i:
            widths.append(mate_w); widths.append(side_w - mate_w)
        else:
            widths.append(side_w - mate_w); widths.append(mate_w)
    # widths now follow alloc.foot order; convert the first to a net figure like the others
    for room, w in zip(alloc.foot, widths):
        if w - inset + 1e-6 < room.template.min_short_side_m:
            return None, PlanFailure(
                RejectionReason.ROW_WIDTH_EXCEEDED,
                f"{room.zone_id} would be {w:.2f} m wide in the foot band, below its "
                f"{room.template.min_short_side_m} m minimum",
                room.template.min_short_side_m + inset - w)
    foot_depth = max(max(r.template.min_short_side_m for r in alloc.foot) + inset,
                     max(areas[r.zone_id] / max(w - inset, 1e-6) for r, w in zip(alloc.foot, widths))
                     + inset / 2)
    foot_depth = round(foot_depth / 0.05) * 0.05

    # Public band: takes the depth the wing leaves, floored by its own minimum and capped by the
    # room that reaches its maximum first (the same rule as `_plan_front_band`).
    band_min = max(r.template.min_short_side_m for r in alloc.public) + inset
    band_depth = round((fh - hub_d - foot_depth) / 0.05) * 0.05
    if band_depth < band_min - 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"lobby {hub_d:.2f} m + foot band {foot_depth:.2f} m leave {band_depth:.2f} m for the "
            f"public band, below its {band_min:.2f} m minimum", band_min - band_depth)
    hub_d = fh - band_depth - foot_depth  # absorb rounding into the lobby, not the band

    # The first public zone must overlap the lobby by a full opening (the cased opening's shared
    # edge) — not span it entirely, as the front band does for its 1.4 m corridor: spanning a 3.3 m
    # lobby plus a flank left 1.9 m for the dining zone on every proportion of a 12.4 m front.
    # Inside that window the band follows the zones' area shares.
    others = alloc.public[1:]
    other_area = sum(areas[r.zone_id] for r in others) or 1.0
    others_min = sum(r.template.min_short_side_m + inset for r in others)
    # ...and it must reach past the footprint's centre: the entrance resolver prefers the middle of
    # the street wall and names the first public zone as the room it opens into (C16), and with
    # parking bays along the front the middle is often the only span clear of them (C11). A 4.45 m
    # living zone at the west edge left the door at x=8.50 with the living room ending at 8.00.
    lo_first = max(west_w + opening_m, fw / 2 + opening_m / 2)  # the door, centred, on its wall
    hi_first = fw - others_min
    wanted_first = fw * areas[alloc.public[0].zone_id] / max(areas[alloc.public[0].zone_id] + other_area, 1e-6)
    if hi_first + 1e-6 < lo_first:
        return None, PlanFailure(
            RejectionReason.BAND_WIDTH_BELOW_MINIMUM,
            f"the front band cannot give {alloc.public[0].zone_id} {lo_first:.2f} m to reach the "
            f"lobby and still seat the other public zones at their minimums", lo_first - hi_first)
    first_w = round(min(max(wanted_first, lo_first), hi_first) / 0.05) * 0.05
    public_widths = [first_w]
    for room in others[:-1]:
        public_widths.append(round((fw - first_w) * areas[room.zone_id] / other_area / 0.05) * 0.05)
    if others:
        public_widths.append(fw - sum(public_widths))
    for room, w in zip(alloc.public, public_widths):
        if w - inset + 1e-6 < room.template.min_short_side_m:
            return None, PlanFailure(
                RejectionReason.BAND_WIDTH_BELOW_MINIMUM,
                f"{room.zone_id} would be {w:.2f} m wide in the front band, below its "
                f"{room.template.min_short_side_m} m minimum")
    binding = min(((r.template.max_area_m2 / max(w - inset, 1e-6), r)
                   for r, w in zip(alloc.public, public_widths)), key=lambda t: t[0])
    if band_depth > binding[0] + inset / 2 + 1e-9:
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"a {band_depth:.2f} m front band would push {binding[1].zone_id} past its "
            f"{binding[1].template.max_area_m2:.0f} m2 maximum")

    specs: dict[str, ZoneSpec] = {}

    def spec_for(room: ProgramRoom, w: float, d: float, lo: float, hi: float) -> ZoneSpec:
        target = w * d
        aspect = max(w, d) / max(1e-6, min(w, d))
        return ZoneSpec(room.zone_id, _roles_of(room), target * lo, target, target * hi,
                        room.template.min_short_side_m,
                        max(room.template.max_aspect_ratio, aspect + 0.3))

    net_band = band_depth - inset
    for room, w in zip(alloc.public, public_widths):
        specs[room.zone_id] = spec_for(room, w - inset, net_band, 0.55, 1.70)
    for flank, w, depths in ((alloc.flank_west, west_w, west_depths),
                             (alloc.flank_east, east_w, east_depths)):
        for room, d in zip(flank, depths):
            specs[room.zone_id] = spec_for(room, w - inset, d - inset / 2, 0.55, 1.70)
    for room, w in zip(alloc.foot, widths):
        specs[room.zone_id] = spec_for(room, w - inset, foot_depth - inset / 2, 0.55, 1.70)
    hub_target = (hub_w - inset) * (hub_d - inset / 2)
    specs[alloc.hub.zone_id] = ZoneSpec(
        alloc.hub.zone_id, (ProgramRole.HALL, ProgramRole.CIRCULATION),
        hub_target * 0.5, hub_target, hub_target * 1.9, HUB_TEMPLATE.min_short_side_m,
        max(HUB_TEMPLATE.max_aspect_ratio, max(hub_w, hub_d) / max(1e-6, min(hub_w, hub_d)) + 0.3))

    doors = (len(alloc.flank_west) + len(alloc.flank_east)
             + sum(1 for r in alloc.foot if not r.entered_from))
    return HubPlan(band_depth, public_widths, west_w, hub_w, east_w, hub_d,
                   west_depths, east_depths, foot_depth, widths, specs, doors), None


def _hub_concept(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
                 ) -> tuple[ConceptCandidate | None, ConceptRejection | None]:
    """The hub parti: public band across the front, a room lobby behind it with bedrooms on its
    flanks and a band of rooms under it. Additive — nothing here touches the other partis.

    Why a lobby and not a corridor: measured against 21 professional plans, the engine's private
    wing was the one structural gap — a hall spine at long/short 9.4 where every reference has a
    compact lobby (~18/21, none a straight double-loaded corridor) that rooms wrap on up to three
    sides. The tree here is the same three-band, full-width slicing structure the front band already
    builds; the lobby is simply the middle band's centre leaf, so every cut on the root->HALL path
    stays forced in the unforced twin (`_contains_hall`) and the lobby's rectangle is never moved by
    the solver, exactly as the corridor's is not.
    """
    strategy = ConceptStrategy.HUB_PRIVATE_WING
    if spec.program.bedrooms < _HUB_MIN_BEDROOMS:
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            f"{spec.program.bedrooms} bedrooms — a room lobby is offered from {_HUB_MIN_BEDROOMS}")
    if any(r.role is ProgramRole.FLEX for r in rooms):
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            "front band already absorbs surplus through its own elasticity; not combined with FLEX")
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    if len(public) < 2:
        return None, ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                      f"{len(public)} public rooms — too few for a front band")

    # The lobby is the variant's HALL room carrying the hub template (research R1).
    hub_rooms = [ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION, HUB_TEMPLATE)
                 if r.group is ZoneGroup.CIRCULATION else r for r in rooms]
    max_width, max_depth = u_to_m(candidate.w), u_to_m(candidate.h)
    gross = target_gross_area_m2(hub_rooms)

    # A requested corridor width is a requirement on the lobby's short side (C14 measures it on
    # the realized plan). The lobby is planned to exactly that width, like the column partis plan
    # their hall to it; a request beyond what a lobby can be is declined here so the brief falls
    # through to the partis — and, for a preference, to the service's retry without it.
    corridor = spec.program.corridor
    widths = _HUB_WIDTHS_M
    if corridor is not None:
        wanted = _hall_width_m(corridor, HUB_TEMPLATE.target_area_m2 ** 0.5, cap_m=max(_HUB_WIDTHS_M),
                               has_safe_room=any(r.role is ProgramRole.SAFE_ROOM for r in rooms))
        if wanted > max(_HUB_WIDTHS_M) + 1e-9 or wanted < min(_HUB_WIDTHS_M) - 1e-9:
            return None, ConceptRejection(
                strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                f"a {corridor.width_m:.2f} m corridor request is outside what a room lobby can be "
                f"({min(_HUB_WIDTHS_M):.1f}-{max(_HUB_WIDTHS_M):.1f} m)")
        widths = (round(wanted / 0.05) * 0.05,)

    failure: PlanFailure | None = None
    rejection: ConceptRejection | None = None
    for hub_w in widths:
        alloc, rej = _hub_allocation(hub_rooms, hub_w)
        if alloc is None:
            rejection = rejection or rej
            continue
        proportions = _proportions(_hub_min_width_m(alloc, hub_w), max_width, max_depth, gross,
                                   spec.program.target_built_area_m2)
        if not proportions:
            failure = _nearest_miss(failure, PlanFailure(
                RejectionReason.FOOTPRINT_BELOW_MINIMUM_WIDTH,
                f"the lobby wing needs at least {_hub_min_width_m(alloc, hub_w):.2f} m of width; "
                f"this candidate offers {max_width:.2f} m"))
            continue
        for width, depth in proportions:
            trial = footprint_of(candidate, width, depth)
            fw, fh = u_to_m(trial.w), u_to_m(trial.h)
            plan, why = _plan_hub_wing(hub_rooms, alloc, fw, fh, hub_w)
            if plan is None:
                failure = _nearest_miss(failure, why)
                continue
            return _hub_candidate(spec, hub_rooms, candidate, trial, alloc, plan), None

    if failure is not None:
        return None, ConceptRejection(strategy, failure.reason, failure.detail)
    return None, rejection


def _hub_candidate(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
                   footprint: Rect, alloc: HubAllocation, plan: HubPlan) -> ConceptCandidate:
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)
    band_tree = _forced_v_chain(alloc.public, plan.public_widths_m)

    def flank_tree(flank: list[ProgramRoom], depths: list[float]) -> Node:
        if len(flank) == 1:
            return Leaf(flank[0].zone_id)
        return Split(Cut.H, Leaf(flank[0].zone_id), Leaf(flank[1].zone_id), m_to_u(depths[0]))

    hub_band = Split(Cut.V, flank_tree(alloc.flank_west, plan.west_depths_m),
                     Split(Cut.V, Leaf(alloc.hub.zone_id),
                           flank_tree(alloc.flank_east, plan.east_depths_m),
                           m_to_u(plan.hub_w_m)),
                     m_to_u(plan.west_w_m))
    foot_tree = _forced_v_chain(alloc.foot, plan.foot_widths_m)  # gross spans, summing to fw
    wing = Split(Cut.H, hub_band, foot_tree, m_to_u(plan.hub_d_m))
    tree = Split(Cut.H, band_tree, wing, m_to_u(plan.band_depth_m))

    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    hall_for = {r.zone_id: alloc.hub.zone_id for r in private}
    access, groups = _build_access(rooms, [alloc.hub.zone_id], [r.zone_id for r in alloc.public],
                                   spec.program.open_plan_living, hall_for,
                                   hall_borders_only_first_public=True)
    fixture = Fixture(f"GEN_{ConceptStrategy.HUB_PRIVATE_WING.value}",
                      (Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree),),
                      tuple(plan.specs[r.zone_id] for r in rooms), access, open_groups=groups)
    return ConceptCandidate(
        Concept(fixture, alloc.hub.zone_id, Side.N, fw, fh), ConceptStrategy.HUB_PRIVATE_WING, (0,),
        rationale=(f"room lobby {plan.hub_w_m:.2f} x {plan.hub_d_m:.2f} m with {plan.doors_on_hub} "
                   f"doors; front band {plan.band_depth_m:.2f} m; flanks {plan.west_w_m:.2f} | "
                   f"{plan.east_w_m:.2f} m; foot band {plan.foot_depth_m:.2f} m "
                   f"({len(alloc.foot)} rooms)"),
        used_area_m2=round(fw * fh, 2),
        unused_wing_area_m2=round(candidate.area_m2() - fw * fh, 2),
    )


def _multi_wing_assessment(candidates: list[SolverGeometryCandidate],
                           ) -> ConceptRejection | None:
    """Evaluate whether a second safe wing can host part of the programme.

    A secondary wing is usable only if circulation in the primary wing can reach it directly,
    which means the hall column must sit against the seam. But the hall must also border the
    room stacks, and in an L decomposition the seam covers only PART of the primary wing's side
    — so a hall placed against it would be partly exterior and partly seam, and a single leaf
    side cannot be both (the spike's L2 finding). Reaching the wing would therefore require
    routing circulation through a private room, which the architectural priorities forbid.

    The wing is CONSIDERED and declined with the reason, never silently ignored.
    """
    if len(candidates) < 2:
        return None
    primary, secondary = candidates[0], candidates[1]
    if secondary.order not in primary.adjacent_orders:
        return ConceptRejection(
            ConceptStrategy.MULTI_WING_SPLIT, RejectionReason.NO_SEAM_ALIGNMENT,
            f"wing {secondary.order} ({secondary.area_m2:.1f} m2) shares no boundary with the "
            f"primary wing, so no access topology can span them",
            (primary.order, secondary.order))

    seam_u = primary.rect.shared_edge_len_u(secondary.rect)
    vertical_seam = (primary.rect.x2 == secondary.rect.x or secondary.rect.x2 == primary.rect.x)
    primary_side_u = primary.rect.h if vertical_seam else primary.rect.w
    if seam_u < primary_side_u:
        return ConceptRejection(
            ConceptStrategy.MULTI_WING_SPLIT, RejectionReason.CIRCULATION_WOULD_CROSS_PRIVATE,
            f"seam covers {u_to_m(seam_u):.1f} m of the primary wing's "
            f"{u_to_m(primary_side_u):.1f} m side, so a hall column against it would be part "
            f"exterior and part seam; reaching wing {secondary.order} "
            f"({secondary.area_m2:.1f} m2) would route circulation through a private room",
            (primary.order, secondary.order))
    return None


# --------------------------------------------------------------------------- 7. entry point

def generate_concepts(spec: ArchitecturalSpec,
                      candidates: list[SolverGeometryCandidate]) -> GenerationResult:
    """A small, bounded, deterministic set of plausible concepts, best first."""
    variants = programme_variants(spec)
    rooms = variants[0]                     # the literal reading of the brief, for the diagnostics
    accepted: list[ConceptCandidate] = []
    rejections: list[ConceptRejection] = []

    if not candidates:
        return GenerationResult((), (ConceptRejection(
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, RejectionReason.INSUFFICIENT_TOTAL_AREA,
            "no safe solver geometry available"),), tuple(rooms))

    needed = target_gross_area_m2(rooms)
    usable = [c for c in candidates if c.area_m2 >= needed * 0.55]
    if not usable:
        return GenerationResult((), (ConceptRejection(
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, RejectionReason.INSUFFICIENT_TOTAL_AREA,
            f"largest safe wing is {candidates[0].area_m2:.1f} m2; the programme needs about "
            f"{needed:.1f} m2"),), tuple(rooms))

    # The requested target may simply be more area than THIS room programme can absorb: real room
    # growth stops at each template's max_area_m2. That USED to be a refusal — "add rooms or shrink
    # the target" — but the person did not ask for more rooms, and forcing that choice on them is
    # exactly what this exists to avoid. Geometry Core still tiles the footprint EXACTLY, so the
    # gap becomes a real zone (FLEX) rather than nowhere: honest about the shortfall, visible on the
    # plan, and never absorbed by inflating a bedroom past its own cap.
    target_m2 = spec.program.target_built_area_m2
    capacity = program_capacity_gross_m2(rooms)
    if target_m2 is not None and target_m2 > capacity + 1e-6:
        flex_template = ROOM_TEMPLATES[ProgramRole.FLEX]
        # Tried sharing LIVING's row the way an ensuite shares its bedroom's — it avoided the extra
        # row's depth cost, but a shared row's DEPTH is set by the pair's COMBINED area, which
        # stretched LIVING itself past its own 46 m2 cap (59 m2, observed) to satisfy FLEX's share.
        # That is the exact defect this exists to prevent, just relocated. FLEX gets its own row:
        # more expensive in depth, but every OTHER room's cap stays intact, which is the one
        # property that must never give.
        def _with_flex(variant: list[ProgramRoom]) -> list[ProgramRoom]:
            return [*variant, ProgramRoom("FLEX", ProgramRole.FLEX, ZoneGroup.PUBLIC, flex_template)]
        variants = [_with_flex(variant) for variant in variants]
        rooms = variants[0]                 # keep `variant is rooms` true for the literal reading

        # KNOWN LIMIT, LEFT AS IS. FLEX still pays the row-based representation's per-row depth
        # cost like any other room — the row's DEPTH must come from somewhere in the candidate
        # rectangle regardless of how little area FLEX itself needs. On a near-square footprint
        # with only a small excess, there is sometimes no spare depth for one more row, and every
        # strategy below will report COLUMN_DEPTH_EXCEEDED and return no design. Measured at
        # ~34% of a 288-scenario sweep (bedrooms x wet rooms x safe room x open plan x four excess
        # levels): a real improvement over the unconditional refusal this replaced (0%), not a full
        # fix. That failure is a genuine constraint of tiling the footprint into fixed-width rows —
        # not a crash, and not evidence the house itself is impossible on a different footprint
        # shape. Closing it needs the row representation itself to change (a room sharing width
        # within an existing row without inheriting that row's full depth requirement), which is a
        # Geometry Core change, deliberately not attempted here. Do not paper over it with another
        # per-strategy heuristic — the last two attempts (sharing LIVING's row, above) each moved
        # the failure rather than removing it.

    primary = usable[0]
    # Every arrangement of the same rooms, in order: the brief as written first, then the ones that
    # need less depth. A plan from the literal reading always outranks a rearranged one, because the
    # candidates are tried in this order and the first realizable wins.
    for variant in variants:
        band, rejection = _front_band_concept(spec, variant, primary.rect)
        if band is not None:
            accepted.append(band)
        elif rejection is not None and variant is rooms:
            rejections.append(rejection)

        for strategy, west, east, rationale in _allocations(variant):
            built, rejection = _build(spec, variant, primary.rect, strategy, west, east, rationale)
            accepted.extend(built)
            if not built and rejection is not None and variant is rooms:
                rejections.append(rejection)

        # The hub parti comes LAST in insertion order. With a target area the sort below decides
        # anyway; without one (the site-driven baselines) insertion order is the ranking, and a
        # hub plan must not displace the plan a brief already had — when a hub should out-rank an
        # area-closer spine plan is an open product question (specs/005 §11), not a side effect.
        hub, rejection = _hub_concept(spec, variant, primary.rect)
        if hub is not None:
            accepted.append(hub)
        elif rejection is not None and variant is rooms:
            rejections.append(rejection)

    multi = _multi_wing_assessment(candidates)
    if multi is not None:
        rejections.append(multi)

    # "Best first" now means CLOSEST TO THE REQUESTED AREA first, not simply the order the
    # strategies happen to be generated in — the pipeline takes the first concept Geometry Core can
    # realize, so this ordering is what actually decides the delivered house size. Without a target
    # the original strategy order is kept, so the site-driven baselines do not move.
    if target_m2 is not None:
        accepted.sort(key=lambda c: (round(abs(c.used_area_m2 - target_m2), 4),
                                     round(c.used_area_m2, 4), c.strategy.value))

    # Every forced tree first, in the order just decided; then the same trees with their cut
    # positions left to the solver, in the same order. See `_unforced` for why this ordering — and
    # not one twin behind each forced tree — is the one that leaves every existing plan untouched.
    accepted.extend([_free_twin(c) for c in accepted])

    return GenerationResult(tuple(accepted), tuple(rejections), tuple(rooms))
