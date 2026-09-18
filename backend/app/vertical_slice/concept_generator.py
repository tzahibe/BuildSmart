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

import bisect
import math
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import Enum

from .concept import Concept
from .constraints import SAFE_ROOM_NOT_REALIZED_DETAIL, TypedConstraint, assert_realized
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
    LaundryDemand,
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
    """A role's size policy. TWO ceilings (2026-09-15):

      * `max_area_m2` is the PREFERRED maximum — the quality target the planner sizes to: surplus
        is distributed up to it first, and a room above it is reported as a quality warning.
        It is also what `program_capacity_gross_m2` sums (unchanged).
      * `hard_max_area_m2` is the ABSOLUTE ceiling — validation C21's gate, and the most a planner
        may size a room to, and only when a proportion cannot be planned inside the preferred
        maxima at all (`ConceptCandidate.over_preferred`). None means the preferred maximum is
        also the hard one.

    Calibrated on the deficit-enabled planner over the 431-context log (see the Phase-2 report):
    the knee of each role's tail — bedroom 18 (20 admits 96 rooms past 1.3x preferred for one
    more plan), master 23 (22 costs six plans, 24 buys none), public rooms +10 %. The safe room's
    hard maximum is its preferred one on purpose: elasticity 0, it never receives surplus, so any
    room past 14 m2 was structure filling space.
    """
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
    hard_max_area_m2: float | None = None
    #: PREFERRED aspect ratio (long/short) — a QUALITY TARGET, never a gate (2026-09-16). The hard
    #: `max_aspect_ratio` stays what `room_depth_band_m`, `_zone_spec` and validation C20 hold a
    #: room to; this is the shape the planner tries to REACH by re-partitioning rows
    #: (`_quality_candidates`) beside a normal plan that leaves the room past it. None: no target.
    preferred_aspect_ratio: float | None = None

    @property
    def preferred_max_area_m2(self) -> float:
        return self.max_area_m2

    @property
    def hard_max(self) -> float:
        return self.hard_max_area_m2 if self.hard_max_area_m2 is not None else self.max_area_m2

    def ceiling_m2(self, hard: bool) -> float:
        """The maximum a planner may size this room to: hard only when allowed to exceed preferred."""
        return self.hard_max if hard else self.max_area_m2


ROOM_TEMPLATES: dict[ProgramRole, RoomTemplate] = {
    ProgramRole.LIVING: RoomTemplate(16.0, 22.0, 46.0, 3.0, 2.5, elasticity=3.0, hard_max_area_m2=50.0),
    ProgramRole.DINING: RoomTemplate(10.0, 14.0, 30.0, 2.6, 3.0, elasticity=1.5, hard_max_area_m2=33.0),
    ProgramRole.KITCHEN: RoomTemplate(9.0, 13.0, 26.0, 2.4, 3.0, elasticity=1.0, hard_max_area_m2=28.0),
    # Caps set by the user directly: a standard bedroom is ~9 m2, a master 11-20 m2 — a
    # generous house should get MORE rooms, or a bigger hall/living room (elasticity above),
    # never one bedroom stretched to fill leftover footprint. Below the public tier's floor
    # (KITCHEN's 1.0), as the priority ranking requires.
    # `preferred_aspect_ratio` 1.5 for the three bedroom-class rooms (2026-09-16, the proportion
    # report): measured over the 431-context log the realized bedroom aspects are BIMODAL — a
    # well-shaped mode up to ~1.5 (short side >= 3.0 m, median 1.28, the census range) and a strip
    # mode at 1.7-2.1 (a lone room at its 2.6 m floor across a ~5 m column); the trough between
    # them is the 1.5-1.6 bin. The safe room is one of the bedrooms (the census), same target.
    ProgramRole.MASTER_BEDROOM: RoomTemplate(11.0, 14.0, 20.0, 3.0, 2.5, elasticity=0.9, hard_max_area_m2=23.0,
                                             preferred_aspect_ratio=1.5),
    ProgramRole.BEDROOM: RoomTemplate(9.0, 10.5, 14.0, 2.6, 2.5, elasticity=0.5, hard_max_area_m2=18.0,
                                      preferred_aspect_ratio=1.5),
    # Regulated minimum: never scaled down, and not inflated just because the house is large.
    ProgramRole.SAFE_ROOM: RoomTemplate(9.0, 10.5, 14.0, 2.4, 2.5, elasticity=0.0, preferred_aspect_ratio=1.5),
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
    # `preferred_aspect_ratio` 2.0 (2026-09-16, docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md): the
    # knee of the corpus's BATHROOM distribution — 1.8 x 3.0-3.6 m (5.4-6.5 m2) is a normal
    # bathroom at 1.7-2.0; short side >= 1.8 m sits at median 1.70. A target only: `_preferred_aspects`
    # (the quality tier's own objective) additionally excludes any ENSUITE-kind room regardless of
    # this value — an ensuite's shape comes from a different mechanism (its host's row depth, not
    # its own), left untouched by this change (see that report's §5).
    ProgramRole.BATHROOM: RoomTemplate(4.5, 6.5, 12.0, 1.6, 3.0, elasticity=0.15, hard_max_area_m2=14.0,
                                       preferred_aspect_ratio=2.0),
    # A WC-only room ("שירותים"). Every number here is smaller than BATHROOM's on purpose — this
    # room holds a pan and a basin, not a shower — and `min_short_side_m` is what actually makes
    # it read as a different room on the plan: the private column's rows span the column's full
    # width, so a wet room's SHORT side is its row depth, and 1.1 m against a bathroom's 1.6 m is
    # the visible difference between the two. PRODUCT POLICY placeholders like every other row in
    # this table, NOT verified regulation. `max_aspect_ratio` is looser than BATHROOM's (3.5 vs
    # 3.0) because the same column width divided by a shallower row is a longer rectangle, and
    # gating on 3.0 would reject the room for being exactly the shape this role asks for.
    # `preferred_aspect_ratio` 2.5 (2026-09-16, docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md): a
    # 1.2 x 2.4-3.0 m WC is 2.0-2.5; the 1.25 x 4.3 m rows at 3.4 are the strips. This role is
    # always a GUEST_WC (`build_room_program` never gives it any other kind), so no kind exclusion
    # is needed here the way BATHROOM's ENSUITE case needs one.
    ProgramRole.TOILET: RoomTemplate(2.2, 4.0, 6.0, 1.1, 3.5, elasticity=0.10, hard_max_area_m2=7.0,
                                     preferred_aspect_ratio=2.5),
    # ---- VOCABULARY, not new behaviour -------------------------------------------------------
    # The six rows below close the naming gap found by the real-plan realizability study: every
    # sampled plan contained at least one room this table could not name, so the study had to draw
    # a dressing room, a laundry, a store, a work nook and a stair core all as "שירותים". These are
    # PRODUCT POLICY placeholders like every other row here, NOT verified regulation.
    #
    # NOTHING PRODUCES FIVE OF THESE SIX YET. `build_room_program` derives its rooms from
    # `ProgramSpec`, which has no field that asks for a store, a den, a study, a dressing room or a
    # stair core, so no demo brief can currently reach them — by design: adding each request path
    # is its own Concept Generator change and was explicitly out of scope here. What these five
    # rows buy today is that anything constructing a `ZoneSpec` directly (the realizability
    # harness, a future concept builder) can name the room correctly instead of borrowing a wet
    # room's identity.
    #
    # LAUNDRY is the exception (2026-09-16 phase 1): `ProgramSpec.laundry` now carries an explicit
    # request, and `build_room_program` emits the room from it — gated by `LAUNDRY_ROOM_ENABLED`
    # below until the planner sweep this phase produced is accepted. See
    # docs/LAUNDRY_ROOM_OPTION_REVIEW.md.
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

#: LAUNDRY ROOM — ACTIVATED (2026-09-16, docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md). Phase 1
#: (docs/LAUNDRY_ROOM_OPTION_REVIEW.md, docs/LAUNDRY_ROOM_PHASE1_REPORT.md) landed this gate as
#: `False` pending the area-budget product decision; the investigation
#: (docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md) and this activation's own measured 31-cell matrix
#: plus a real-418-context regression pass answered it — service-first allocation
#: (`_laundry_deficit_targets`) plus a disclosure notice (`contract.QualityOut.laundry_notice`),
#: 0 payload/status changes for any brief without a laundry room. This is the single point that
#: decides whether real users see a generated laundry room; nothing else in this module should
#: gate on `ProgramSpec.laundry` itself.
LAUNDRY_ROOM_ENABLED = True

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

#: How far above its PREFERRED maximum a realized room may be before it is anything more than a
#: number on the contract. Calibrated with the two-level maxima on the 431-context log (two-level
#: run: 440 rooms above preferred in 395 plans — 306 under 1.10x, 86 at 1.10-1.20x, 48 above
#: 1.20x, every one of the last a bedroom):
#:   * up to `OVER_PREFERRED_SIGNAL_RATIO`: metadata only — a 14.5 m2 bedroom is not a finding;
#:   * up to `OVER_PREFERRED_NOTICE_RATIO`: a quality SIGNAL, for ranking and diagnostics, unseen;
#:   * above it: a user-facing quality notice (one per plan, aggregated) — 30 plans, 8 %.
#: "Near the hard ceiling" is deliberately NOT a rule: the preferred->hard band is 1.15x for the
#: master and 1.08-1.10x for the public rooms, so it fired on 25 masters at 1.02-1.10x. Beyond the
#: hard maximum is validation C21, not a notice.
OVER_PREFERRED_SIGNAL_RATIO = 1.10
OVER_PREFERRED_NOTICE_RATIO = 1.20

#: Net/gross ratio used to size a footprint from a programme. Measured 0.90-0.92 in the spike.
ASSUMED_EFFICIENCY = 0.90
#: Wall inset allowance used by the pre-check (exterior half 0.15 + partition half 0.05).
_EDGE_INSET_ALLOWANCE_M = 0.20
#: Slack on a planned rectangle's area against its template maximum — float noise on the 5 cm
#: grid, nothing more. The realized room is held to the same maximum by validation C21 with the
#: validator's own tolerance.
_AREA_TOL_M2 = 0.01
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
    #: At the width the parti gives a room, NO depth satisfies both its template aspect ratio and
    #: its maximum area — the room can only be a strip or oversized. Distinct from the two above
    #: because neither dimension is short of anything: the room simply does not belong at that
    #: width, and the seam/strategy search must move on. See `room_depth_band_m`.
    ROOM_SHAPE_INFEASIBLE = "ROOM_SHAPE_INFEASIBLE"
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
    #: Some attempt behind this failure was refused for a room's SHAPE (`ROOM_SHAPE_INFEASIBLE`),
    #: even if the nearest miss reported here is another reason. The planners report their
    #: nearest miss by shortfall, and a shape refusal has none, so without this flag the one
    #: signal that says "repartition would help" is exactly the one the diagnosis drops.
    shape_seen: bool = False
    #: Which fallback MECHANISM could address this failure (reason-aware gating, `_build`):
    #: `deficit_fixable` — the rows' WANTS overflow the column but their FLOORS fit, so shrinking
    #: the wants toward the floors (`allow_deficit`) can plan it; `hard_fixable` — a PREFERRED
    #: maximum is what blocked, and the room concerned has hard headroom above it, so sizing past
    #: preferred (`allow_hard`) can plan it. Aggregated over a seam search like `shape_seen`: true
    #: when ANY seam failed that way. A fallback whose mechanism no failure asked for is not run —
    #: measured before this, every proportion paid up to six planner attempts regardless.
    deficit_fixable: bool = False
    hard_fixable: bool = False


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
    #: Wet rooms only: the RESOLVED requirement this room was built to (kind never `UNSPECIFIED` —
    #: see `resolve_wet_rooms`). `None` for every other room. Carried on the room so every concept
    #: built from a programme can hand validation the requirements THAT programme was built to.
    wet: ResolvedWetRoom | None = None

    @property
    def wet_kind(self) -> WetRoomKind | None:
        return None if self.wet is None else self.wet.kind


@dataclass(frozen=True)
class ConceptCandidate:
    concept: Concept
    strategy: ConceptStrategy
    wing_orders: tuple[int, ...]
    rationale: str
    used_area_m2: float
    unused_wing_area_m2: float
    #: The wet-room requirements of the programme THIS candidate was built from — the literal
    #: brief's, or an eligible variant's — for C17 to hold the realized doors to. A candidate built
    #: from a rearranged programme is validated against that arrangement, which is what makes the
    #: rearrangement legitimate rather than a violation of the brief.
    wet_rooms: tuple[ResolvedWetRoom, ...] = ()
    #: 008: this hub candidate was placed after every other candidate because its bound missed the
    #: §6 gates on this outline. Carried on the candidate so the pipeline can still COMPARE it with
    #: whatever took its place (`hub_guard`), rather than assume the replacement is better.
    hub_last_resort: bool = False
    #: Tier 2 (`Repartition`): this candidate was planned with rows re-partitioned after the normal
    #: attempt at the same proportion failed for a room's shape. Ordered after every tier-1
    #: candidate and its twin, so a brief that plans normally never receives one.
    repartitioned: bool = False
    #: This candidate was planned with its rows SHRUNK toward their floors (`_row_depths` deficit
    #: distribution), attempted only after the normal attempt at the same proportion could not fit
    #: the rows' wants. It ranks by area proximity like any candidate — a shrunk 186 m2 plan is a
    #: better answer to a 216 m2 ask than a normal 144 m2 one — and loses only a TIE to a normal
    #: candidate of the same area. Measured: ranking shrunk plans strictly after every normal one
    #: handed the regression brief the 144 m2 front band (67 %) instead of the 186 m2 spine (86 %).
    shrunk: bool = False
    #: This candidate was planned with rooms allowed past their PREFERRED maxima up to their HARD
    #: ones (`RoomTemplate`), attempted only after the proportion could not be planned inside the
    #: preferred maxima. Ranks by area proximity like any candidate and loses only a tie to one
    #: that stayed inside. Validation C21 holds it to the hard maxima; the contract reports the
    #: rooms above preferred as a quality warning.
    over_preferred: bool = False
    #: QUALITY TIER (2026-09-16): this candidate is a found plan re-partitioned for room
    #: PROPORTIONS — the tier-2 pairing applied beside a plan that leaves a bedroom-class room past
    #: its `preferred_aspect_ratio`, at the same footprint, programme and sizing tier
    #: (`_quality_layouts`). Always `repartitioned` as well (it IS re-partitioned rows, and the
    #: pipeline's tier-2 rule applies), and ordered after every other one-wing candidate: it never
    #: displaces the plan a brief already had — ranking among them is a later review's question.
    quality_repartitioned: bool = False


@dataclass(frozen=True)
class GenerationResult:
    candidates: tuple[ConceptCandidate, ...]
    rejections: tuple[ConceptRejection, ...]
    program: tuple[ProgramRoom, ...]
    #: The spec's typed constraints (Issue #35), carried alongside the programme they were
    #: derived from. Empty for a spec with none.
    constraints: tuple[TypedConstraint, ...] = ()

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
                                 wet.host_zone, wet))

    # Laundry room — phase 1 (2026-09-16, docs/LAUNDRY_ROOM_OPTION_REVIEW.md). The brief's request
    # (`program.laundry`) and whether it is actually PLANNED are two different questions:
    # `LAUNDRY_ROOM_ENABLED` answers the second, independently of what was asked, until the sweep
    # this phase produced is reviewed. `entered_from` is deliberately never set — a laundry room is
    # circulation-accessible like a WC, never an ensuite-style dependent; `_build_access` already
    # reaches every SERVICE room from the hall with no room-specific code.
    if LAUNDRY_ROOM_ENABLED and program.laundry.demand is LaundryDemand.ROOM:
        add("LAUNDRY", ProgramRole.LAUNDRY, ZoneGroup.SERVICE)

    return rooms


def wet_rooms_of(rooms: list[ProgramRoom]) -> tuple[ResolvedWetRoom, ...]:
    """The wet-room requirements a programme was built to, in programme order."""
    return tuple(r.wet for r in rooms if r.wet is not None)


def programme_variants(spec: ArchitecturalSpec) -> list[list[ProgramRoom]]:
    """The room programme, plus arrangements of the SAME requirements that need less depth.

    WHY THIS EXISTS. The private column stacks one room per row; only an ensuite shares its
    bedroom's row. So 3 bedrooms + 2 wet rooms is four rows — 10.60 m of depth at the minimums —
    and measurement showed the planner needs about 149 m² of footprint before any proportion works,
    against a 99.6 m² geometric floor. One extra row costs roughly 40 m².

    A shared bathroom placed OFF A BEDROOM instead of off the corridor is the same rooms in three
    rows rather than four. That is an ordinary house — a second ensuite — but it is a DIFFERENT
    HOUSE from the one described, so it is offered only when the person allowed it.

    WHAT A VARIANT MAY DO (specs/007 FR-7). A variant is a rearrangement of the same requirements.
    It may make a corridor-entered full bathroom private to a secondary bedroom only when that wet
    room's requirement is FLEXIBLE — the person said its placement does not matter — and only if the
    resulting programme still satisfies every access invariant (`check_wet_room_invariants`): in
    practice, a shared full bathroom remains, or every bedroom ends up with its own. A brief with no
    flexible wet room — every legacy brief, every bare count — gets the literal programme and
    nothing else. Measured before this rule existed, the variant had put the house's ONLY shared
    bathroom inside a child's bedroom in 45 delivered plans, for briefs that had asked for a guest
    WC; none of them had asked for a second suite.

    ORDER IS NOT A GUARANTEE. `generate_concepts` sorts candidates by closeness to the requested
    area when there is one, so a variant can be tried BEFORE the literal reading and win the
    primary. That is why eligibility is decided HERE, on semantics, and not left to ranking: an
    ineligible variant never enters the pool, whatever the order.

    Bounded by construction: at most one extra variant — the LAST flexible shared bathroom joins the
    LAST secondary bedroom (taking the first would move the guest WC away from the entrance, which
    is the one wet room that wants to stay there).
    """
    base = build_room_program(spec)
    program = spec.program
    resolved = resolve_wet_rooms(program)  # `base` was built from it, so it resolves
    flexible = [r for r in resolved
                if r.kind is WetRoomKind.SHARED_BATHROOM and r.strength is WetRoomStrength.FLEXIBLE]
    if not flexible or program.bedrooms < 2:
        return [base]

    moved = flexible[-1]
    # The variant is expressed as REQUIREMENTS, then resolved and checked like any brief. Every
    # item is materialized from its resolved kind — not re-padded from the count — so an
    # unstated item keeps the default it already had instead of shifting when one item changes.
    def as_requirement(r: ResolvedWetRoom) -> WetRoomRequirement:
        if r.zone_id == moved.zone_id:
            return WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_BEDROOM, r.strength,
                                      r.source_text, r.origin)
        host = None
        if r.kind is WetRoomKind.ENSUITE:
            host = ENSUITE_HOST_MASTER if r.host_zone == "MASTER" else ENSUITE_HOST_BEDROOM
        return WetRoomRequirement(r.kind, host, r.strength, r.source_text, r.origin)

    variant_program = replace(program, wet_room_kinds=tuple(as_requirement(r) for r in resolved))
    if check_wet_room_invariants(variant_program):
        return [base]
    variant = build_room_program(replace(spec, program=variant_program))
    return [base, variant]


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


#: Roles `_laundry_deficit_targets` draws from FIRST. Not "wet rooms" in general (LAUNDRY itself
#: is deliberately excluded — it is the newly requested room the deficit exists to fund, not a
#: source for funding itself) — exactly BATHROOM/TOILET, the two roles the activation decision
#: (docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md) measured this against.
_LAUNDRY_DEFICIT_SOURCE_ROLES = (ProgramRole.BATHROOM, ProgramRole.TOILET)


def _laundry_deficit_targets(rooms: list[ProgramRoom], starts: dict[str, float], base: float,
                             deficit: float, floor_of) -> dict[str, float]:
    """Deficit distribution for a programme that includes an explicitly requested LAUNDRY room
    (2026-09-16, activation — docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md, "Policy B" in the
    investigation that preceded it). CONTAINED to this one case: `scale_program`'s caller only
    reaches this function when `rooms` already contains a `ProgramRole.LAUNDRY` room AND the
    programme is short of area — for every other programme, `scale_program`'s original uniform
    proportional shrink below is untouched, byte for byte.

    The deficit is drawn from BATHROOM/TOILET headroom FIRST — proportional to each one's own
    room to shrink toward its floor, never past it — before any PRIVATE room (bedroom, master,
    safe room) or CIRCULATION is touched at all. Only the remainder, if service headroom cannot
    cover the whole deficit, cascades to every other room (bedrooms, circulation, public rooms,
    and the laundry room itself alike) via the same proportional-to-target rule `scale_program`
    already uses for a plain deficit — so circulation is never the FIRST source, and PRIVATE rooms
    are never touched before service headroom is exhausted, matching the activation decision
    exactly. Every room's floor (`floor_of`) is respected throughout, in both tiers.
    """
    targets = dict(starts)
    service = [r for r in rooms if r.role in _LAUNDRY_DEFICIT_SOURCE_ROLES]
    service_capacity = sum(starts[r.zone_id] - floor_of(r) for r in service)
    take = min(deficit, service_capacity)
    if take > 0 and service_capacity > 0:
        for r in service:
            headroom = starts[r.zone_id] - floor_of(r)
            targets[r.zone_id] = starts[r.zone_id] - take * (headroom / service_capacity)
    remaining = deficit - take
    if remaining > 1e-9:
        others = [r for r in rooms if r.role not in _LAUNDRY_DEFICIT_SOURCE_ROLES]
        other_base = sum(starts[r.zone_id] for r in others)
        for r in others:
            share = remaining * (starts[r.zone_id] / other_base) if other_base > 0 else 0.0
            targets[r.zone_id] = max(starts[r.zone_id] - share, floor_of(r))
    return targets


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

    A DEFICIT (surplus < 0) shrinks every room proportionally to its own target, never below its
    floor — EXCEPT when `rooms` includes an explicitly requested LAUNDRY room, in which case
    `_laundry_deficit_targets` applies instead (service/wet-room headroom first). That branch is
    unreachable for any programme without a laundry room, so this function is otherwise identical
    to its pre-2026-09-16 form.
    """
    floors = area_floors or {}

    def floor_of(room: ProgramRoom) -> float:
        return max(room.template.min_area_m2, floors.get(room.zone_id, 0.0))

    base = sum(max(r.template.target_area_m2, floor_of(r)) for r in rooms)
    surplus = net_available_m2 - base
    weight_total = sum(r.template.elasticity for r in rooms) or 1.0
    starts = {r.zone_id: max(r.template.target_area_m2, floor_of(r)) for r in rooms}

    if surplus < 0 and any(r.role is ProgramRole.LAUNDRY for r in rooms):
        targets = _laundry_deficit_targets(rooms, starts, base, -surplus, floor_of)
    else:
        targets = {}
        for room in rooms:
            t = room.template
            start = starts[room.zone_id]
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


def program_capacity_gross_m2(rooms: list[ProgramRoom], *, hard: bool = False) -> float:
    """The largest house THIS programme can responsibly fill.

    `scale_program` never grows a room past its template `max_area_m2`, and Geometry Core tiles the
    footprint EXACTLY — so a footprint bigger than the sum of those maxima cannot be absorbed: the
    surplus has nowhere to go and the layout is rejected. This is a limit of the current room
    programme and its template table, NOT a statement that such a house is impossible to build.

    `hard=True` is the same sum over the rooms' HARD ceilings (`RoomTemplate.hard_max`): the most a
    planner may ever size them to (`over_preferred`). A FLEX zone is not a room and is left out of
    that sum — it exists to take what the rooms cannot, so a footprint above the rooms' hard
    capacity is FLEX's to fill, never a reason to inflate a room past its preferred maximum
    (`_absorbable_over_preferred`).
    """
    if hard:
        return sum(r.template.hard_max for r in rooms if r.role is not ProgramRole.FLEX) / ASSUMED_EFFICIENCY
    return sum(r.template.max_area_m2 for r in rooms) / ASSUMED_EFFICIENCY


def _absorbable_over_preferred(rooms: list[ProgramRoom], gross_m2: float) -> bool:
    """Whether a proportion of `gross_m2` (the planner's gross footprint area, the same figure as
    `ConceptCandidate.used_area_m2`) could be absorbed by rooms sized past their preferred maxima
    at all. Above the rooms' HARD capacity it cannot — every room at its hard ceiling still leaves
    area over — so the over_preferred attempts at such a proportion are skipped: measured, they
    planned 268-250 m² houses for a 200 m² programme that Geometry Core then refused, and their
    candidates crowded out the 223-211 m² shrunk plans that solve. Nothing at or below the hard
    capacity is ever skipped."""
    return gross_m2 <= program_capacity_gross_m2(rooms, hard=True) + 1e-6


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


def room_depth_band_m(template: RoomTemplate, net_w_m: float,
                      hard: bool = False) -> tuple[float, float] | None:
    """The NET depths a room may take at NET width `net_w_m` under its template — at least
    `min_short_side` and `w / aspect`, at most the smaller of `w * aspect` and `max_area / w` —
    or None when that band is empty.

    THE SHAPE-AND-SIZE RULE, in one place. Every sizing path in this module (`_row_depths`, the
    front band, the hub's flanks and foot) floors its depths with the lower end and refuses on
    None, so the planned rectangles already satisfy the template that `ZoneSpec` then hands to
    Geometry Core unrelaxed. Before this, the depth was floored by the short side ALONE and the
    aspect ratio was relaxed to whatever the plan produced (+0.3), which is how a 6.1 x 1.2 m WC
    passed every check on the way to a drawing.

    None is the strip-or-oversized dilemma: the floor — the aspect ratio's or the short side's,
    whichever binds — already exceeds `max_area / w`. A 5.2 m wide WC needs 1.49 m for its 3.5
    aspect and may have 1.15 m for its 6 m2 maximum; a 6.1 m wide bedroom needs its 2.6 m short
    side and may have 2.30 m for its 14 m2 maximum. A room offered such a width can only be a
    strip or oversized, so the parti that offered it is the thing to change, never the room. The
    short-side case used to be exempt ("the planners do not yet hold rooms to their area maxima"),
    which is how a 6.1 x 2.6 m bedroom at 15.9 m2 and a 7.5 x 3.1 m master at 23 m2 reached the
    drawing; the maxima are hard now (`_row_depths`, `_zone_spec`, validation C21).
    """
    aspect_floor = net_w_m / template.max_aspect_ratio
    # The floor also carries the template's MINIMUM AREA. It never used to matter — every row
    # was sized by its area target, well above the minimum — until deficit distribution began
    # shrinking rows to their floors on purpose: a 2.75 m wide bedroom at its 2.6 m short side is
    # 7.3 m2 against a 9 m2 minimum, and a safe room 6.5 against its regulated 9.
    lo = max(template.min_short_side_m, aspect_floor, template.min_area_m2 / max(net_w_m, 1e-6))
    # `hard`: the band under the hard maximum instead of the preferred one — a room that is
    # oversized at this width under the preferred ceiling but legal under the hard one has a band
    # only for a planner allowed to exceed preferred (`ConceptCandidate.over_preferred`).
    hi = min(net_w_m * template.max_aspect_ratio, template.ceiling_m2(hard) / max(net_w_m, 1e-6))
    if lo > hi + 1e-9:
        return None
    return (lo, hi)


def _shape_failure(room: ProgramRoom, net_w_m: float, net_d_m: float,
                   where: str, hard: bool = False) -> PlanFailure | None:
    """Why a planned NET `net_w_m x net_d_m` rectangle breaks `room`'s shape rule, or None.

    Three things are checked. The depth band must exist at this width (`room_depth_band_m`); the
    depth must sit inside the template's ASPECT band both ways — too shallow for its width is the
    classic strip, too deep for its width is the same strip stood on end (an ensuite at its
    minimum width beside a deep bedroom); and the rectangle's area must not exceed the template's
    MAXIMUM. The area refusal carries its own reason so a log can tell "this room would be too
    big" from "this room would be a strip" — they call for different remedies.
    """
    t = room.template
    limit = t.ceiling_m2(hard)
    band = room_depth_band_m(t, net_w_m, hard)
    if band is None:
        return PlanFailure(
            RejectionReason.ROOM_SHAPE_INFEASIBLE,
            f"{room.zone_id} at {net_w_m:.2f} m wide in the {where} has no depth that keeps its "
            f"{t.max_aspect_ratio} aspect ratio and {t.min_short_side_m} m short side under its "
            f"{limit:.0f} m2 {'hard ' if hard else 'preferred '}maximum (needs "
            f"{max(t.min_short_side_m, net_w_m / t.max_aspect_ratio):.2f} m, allowed "
            f"{limit / net_w_m:.2f} m)",
            hard_fixable=not hard and room_depth_band_m(t, net_w_m, hard=True) is not None)
    aspect_lo = net_w_m / t.max_aspect_ratio
    aspect_hi = net_w_m * t.max_aspect_ratio
    if net_d_m < aspect_lo - 1e-6:
        return PlanFailure(
            RejectionReason.ROOM_SHAPE_INFEASIBLE,
            f"{room.zone_id} would be {net_w_m:.2f} x {net_d_m:.2f} m in the {where}, past its "
            f"{t.max_aspect_ratio} aspect ratio", aspect_lo - net_d_m)
    if net_d_m > aspect_hi + 1e-6:
        return PlanFailure(
            RejectionReason.ROOM_SHAPE_INFEASIBLE,
            f"{room.zone_id} would be {net_w_m:.2f} x {net_d_m:.2f} m in the {where}, past its "
            f"{t.max_aspect_ratio} aspect ratio the other way", net_d_m - aspect_hi)
    if net_w_m * net_d_m > limit + _AREA_TOL_M2:
        return PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"{room.zone_id} would be {net_w_m:.2f} x {net_d_m:.2f} m = {net_w_m * net_d_m:.1f} m2 "
            f"in the {where}, past its {limit:.0f} m2 {'hard ' if hard else 'preferred '}maximum",
            net_w_m * net_d_m - limit,
            hard_fixable=not hard and t.hard_max > t.max_area_m2 + _AREA_TOL_M2)
    return None


def _hard_headroom(rooms: Iterable[ProgramRoom]) -> bool:
    """Whether sizing past the PREFERRED maxima can change anything for these rooms: at least one
    has a hard maximum above its preferred one. Under `allow_hard` the surplus distribution, the
    band and the ceilings all move with that headroom, so any failure decided after it is in play
    is marked `hard_fixable` when this holds — conservatively: a hard attempt may still fail, but
    one is never skipped where it could have planned."""
    return any(r.template.hard_max > r.template.max_area_m2 + _AREA_TOL_M2 for r in rooms)


def _row_widths(row: list[ProgramRoom], net_width: float,
                net_depth: float | None = None) -> list[float] | None:
    """Widths for the members of a shared row, or None if they cannot all fit.

    Area share alone is not enough: an ensuite is ~30% of its bedroom by area, and 30% of a
    5 m column is 1.39 m — under a bathroom's 1.6 m minimum. Every member gets its minimum
    first; only the surplus is shared by area.

    With `net_depth` known, a member's minimum is also its depth over its aspect ratio: a 1.6 m
    ensuite beside a 5.6 m deep bedroom is a 1:3.5 strip, and the short side alone would never say
    so. Callers that size the row's depth pass it; the depth planner itself calls this without one
    to get the floor it then sizes against, and again with the chosen depth to verify.
    """
    minimums = [r.template.min_short_side_m for r in row]
    if net_depth is not None:
        minimums = [max(m, net_depth / r.template.max_aspect_ratio) for m, r in zip(minimums, row)]
    # `net_width` has the column's two outer walls netted off; a shared row also has the
    # partition BETWEEN its members, which nobody had paid for — the members' widths summed to a
    # net width they could not both have, and a master at its 3.0 m minimum on the exterior side
    # came back 2.90. That slipped through while surplus gave every shared row slack; a row at
    # its minimums (deficit distribution) has none. The members' widths are their TRUE nets now,
    # and `_forced_chain` places the cut so the solver returns exactly them.
    budget = net_width - WALL_THICKNESS_M[WallType.PARTITION] * (len(row) - 1)
    if sum(minimums) > budget + 1e-9:
        return None
    surplus = budget - sum(minimums)
    areas = [r.template.target_area_m2 for r in row]
    total = sum(areas) or 1.0
    return [m + surplus * a / total for m, a in zip(minimums, areas)]


def _depth_allowance_m(room: ProgramRoom) -> float:
    """The wall allowance a room's DEPTH FLOOR carries: the planner's flat allowance, or for the
    safe room the two RC halves its envelope always has.

    The flat 0.20 m assumes an exterior half on one side and a partition half on the other. A safe
    room is RC on every side and loses 0.15 m to each, so a floor built on the flat figure hands
    Geometry Core a 2.6 m safe room that nets 2.3 m against its 2.4 m minimum and the forced tree
    is refused. That was invisible while the safe room absorbed surplus it was not entitled to
    (elasticity 0, yet it grew); now that a zero-elasticity row gets none, the floor has to be
    right on its own."""
    if room.role is ProgramRole.SAFE_ROOM:
        return WALL_THICKNESS_M[WallType.RC_SAFE_ROOM]
    return _EDGE_INSET_ALLOWANCE_M


def _row_depth_floor_m(row: list[ProgramRoom], net_width: float, where: str,
                       allowance_m: float | None = None, hard: bool = False,
                       ) -> tuple[float, PlanFailure | None]:
    """The CENTERLINE depth a row needs at this column width: every member's depth band lower
    end at the width it gets, plus the wall allowance — `allowance_m` when the caller knows the
    row's neighbours (`_row_wall_allowances_m`), else what each member's own construction needs.
    The failure is the member whose band is empty at that width — the row cannot be planned at
    this width at all."""
    widths = _row_widths(row, net_width) or [net_width / len(row)] * len(row)
    floor = 0.0
    for room, w in zip(row, widths):
        band = room_depth_band_m(room.template, w, hard)
        if band is None:
            return 0.0, _shape_failure(room, w, 0.0, where, hard)
        floor = max(floor, band[0] + (allowance_m if allowance_m is not None
                                      else _depth_allowance_m(room)))
    return floor, None


def _row_wall_allowances_m(rows: list[list[ProgramRoom]],
                           ends_exterior: tuple[bool, bool]) -> list[float]:
    """Per row, the depth it loses to the walls on its north and south sides — half of each.

    The flat allowance (`_EDGE_INSET_ALLOWANCE_M`) assumes one exterior half and one partition
    half. A row's actual north/south walls are known from its place in the column: exterior at a
    column end that meets the envelope (`ends_exterior`), RC wherever the row or its neighbour
    holds the safe room, a partition otherwise. A row that sits AT its floor — which deficit
    distribution now produces on purpose — has no slack to absorb the difference: a bathroom
    under the safe room and against the back wall planned at 1.6 + 0.20 came back 1.50 m net
    against its 1.6 m minimum, and the forced tree was refused.

    Never BELOW the flat allowance: an interior row's true figure is 0.10, but lowering floors
    that every plan so far was built on would move rows that were never the problem. The flat
    figure stays the minimum; this only raises it where the real walls exceed it."""
    half = {WallType.EXTERIOR: WALL_THICKNESS_M[WallType.EXTERIOR] / 2,
            WallType.RC_SAFE_ROOM: WALL_THICKNESS_M[WallType.RC_SAFE_ROOM] / 2,
            WallType.PARTITION: WALL_THICKNESS_M[WallType.PARTITION] / 2}
    holds_safe = [any(r.role is ProgramRole.SAFE_ROOM for r in row) for row in rows]

    def side(i: int, j: int, exterior: bool) -> float:
        if exterior:
            return half[WallType.EXTERIOR]
        if holds_safe[i] or holds_safe[j]:
            return half[WallType.RC_SAFE_ROOM]
        return half[WallType.PARTITION]

    out = []
    for i in range(len(rows)):
        north = side(i, i - 1, i == 0 and ends_exterior[0]) if i > 0 or ends_exterior[0] else side(i, i, False)
        south = side(i, i + 1, i == len(rows) - 1 and ends_exterior[1]) if i < len(rows) - 1 or ends_exterior[1] else side(i, i, False)
        out.append(max(_EDGE_INSET_ALLOWANCE_M, north + south))
    return out


def _verify_row_shapes(rows: list[list[ProgramRoom]], depths: list[float], net_width: float,
                       where: str, hard: bool = False) -> PlanFailure | None:
    """Every member of every row inside its template's shape band at the depth finally chosen —
    the check the surplus distribution and the 5 cm grid are held to, after the floors."""
    for row, depth in zip(rows, depths):
        net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
        widths = _row_widths(row, net_width, net_d)
        if widths is None:
            return PlanFailure(
                RejectionReason.ROW_WIDTH_EXCEEDED,
                f"{' + '.join(r.zone_id for r in row)} cannot share the {where}'s {net_width:.2f} m "
                f"of net width at {net_d:.2f} m deep without one of them becoming a strip")
        for room, w in zip(row, widths):
            failure = _shape_failure(room, w, net_d, where, hard)
            if failure is not None:
                return failure
    return None


def _after_distribution(failure: PlanFailure | None, rows: list[list[ProgramRoom]],
                        hard: bool) -> PlanFailure | None:
    """A failure decided on depths the surplus distribution chose: under `allow_hard` the
    distribution itself differs wherever a row has hard headroom, so the failure may not recur."""
    if failure is None or hard or failure.hard_fixable:
        return failure
    return replace(failure, hard_fixable=_hard_headroom(r for row in rows for r in row))


@dataclass(frozen=True)
class Repartition:
    """Tier-2 planning options — the generic fallback for a room that cannot be shaped alone.

    The normal path plans each column with the rows `_rows_of` gives it and refuses a room that
    has no shape band at the column's width (`room_depth_band_m` is None: a strip or oversized).
    Tier 2 runs ONLY at a (strategy, proportion) where that normal attempt failed and a shape
    refusal was among the reasons (`PlanFailure.shape_seen`), and does three things the normal path
    does not: it lets such a room SHARE a row with any partner the access model permits
    (`_repartition_rows`), it searches the column seam over its whole feasible range rather than
    the nine steps around the area share (`_seam_options(limit=None)`), and in the front band it
    searches the rear seam at all. Sizing is unchanged: minimums (short side and shape floor)
    first, surplus by elasticity (`_row_depths`), widths by minimums then area share
    (`_row_widths`). Nothing here is per role: a WC, a kitchen and a bedroom are handled by the
    same rule, and the candidates it produces are ordered after every normal one.

    `open_chain` is the open-plan public zones in the order `_build_access` declares their OPEN
    connections (consecutive members must share an edge; empty for a closed plan); `hall_public`
    the public zone that carries the hall's opening and must therefore keep touching the corridor;
    `never_shared` the zones that must keep a row of their own — the FLEX zone, which exists to
    absorb the surplus a target above capacity leaves (`generate_concepts`), and a row it shared
    would hand that surplus to its partner instead (measured: a kitchen at 41.6 m2 against 26).
    """
    open_chain: tuple[str, ...]
    hall_public: str | None
    north_is_envelope: bool
    never_shared: frozenset[str] = frozenset()
    #: QUALITY TIER (2026-09-16): re-partition for room PROPORTIONS rather than for a shape refusal.
    #: With `quality`, `_rows_for_width` keeps the normal path's rows and then lets a lone row
    #: take the master's slot beside the ensuite where that brings a bedroom-class room toward
    #: its `preferred_aspect_ratio` (`_quality_candidates`), choosing the `quality_rank`-th best
    #: legal pairing; `hard` is the ceiling tier the base plan was sized under, so the shape
    #: estimate floors rows the same way. The seam window stays the normal nine (`plan_layout`).
    quality: bool = False
    quality_rank: int = 0
    hard: bool = False

    @property
    def open_group(self) -> frozenset[str]:
        return frozenset(self.open_chain)


def _pair_with_dependent(rows: list[list[ProgramRoom]], index: int) -> list[list[ProgramRoom]] | None:
    """Row `index`'s lone room folded into a dependent room's row, or None if the column has none.

    THE ONE PAIRING A CORRIDOR-FACING ROOM ADMITS. A shared row is a V-split beside the hall, so
    exactly one of its members touches the corridor; the other must be entered from a neighbour,
    and the only rooms in the programme that are, are dependents — an ensuite, from its bedroom.
    So `[BEDROOM, ENSUITE]` + `[ROOM]` becomes `[BEDROOM]` + `[ROOM, ENSUITE]`, the new row directly
    beside the bedroom's: the room takes the corridor-facing slot the bedroom had (same
    orientation, same side), the ensuite keeps its slot and now meets its bedroom across the row
    boundary instead of beside it — a door on that edge is the same door, and C17 reads the same
    access. The bedroom, full-width, reaches the column's outer edge on its own; if the room that
    moved in needs daylight itself, `_daylight_order` puts the row at a column end afterwards. Two
    wet rooms sharing a wall is also the adjacency the reference plans show (spec 005 §1 M5).
    """
    return next(iter(_dependent_pairings(rows, index)), None)


def _dependent_pairings(rows: list[list[ProgramRoom]], index: int) -> list[list[list[ProgramRoom]]]:
    """Every row list `_pair_with_dependent` could return, in-place placement first.

    Only a row that still holds a dependent BESIDE ITS OWN HOST is a partner: once a room has
    taken the host's slot, the row is spoken for, and letting the next room take it would leave
    the first one alone again. The host must also stay beside the pair after the daylight
    re-ordering (`_access_intact`), which moves a shared row whose corridor-facing member needs a
    window to a column end — so beside the in-place placement the block [host, pair] is also
    offered at each end of the column, where `_daylight_order` leaves it alone.
    """
    out_all = []
    for j, row in enumerate(rows):
        if len(row) != 2 or j == index:
            continue
        dependent = [r for r in row if r.entered_from]
        host = [r for r in row if not r.entered_from]
        if len(dependent) != 1 or len(host) != 1 or dependent[0].entered_from != host[0].zone_id:
            continue
        room = rows[index][0]
        # the room takes the host's slot, so the row keeps the orientation `_orient_row` chose
        paired = [room if r is host[0] else r for r in row]
        rest = [list(r) for i, r in enumerate(rows) if i != index and i != j]
        at = min(j, len(rest))
        in_place = rest[:at] + [[host[0]], paired] + rest[at:]
        south = rest + [[host[0]], paired]
        north = [paired, [host[0]]] + rest
        for candidate in (in_place, south, north):
            if candidate not in out_all:
                out_all.append(candidate)
    return out_all


def _pair_with_open_member(rows: list[list[ProgramRoom]], index: int, options: Repartition,
                           corridor_on_east: bool) -> list[list[list[ProgramRoom]]]:
    """Row `index`'s lone room beside a lone NEIGHBOUR of its open chain — every such row list.

    Two zones of one open group need no door between them and no corridor of their own — the
    cut between them is wall-less by construction (`_mark_open_interfaces`) — so either may take
    the far slot, with one exception: the zone that carries the hall's opening (`hall_public`)
    must stay on the corridor side. Otherwise the room being re-partitioned takes the far slot
    (the column's outer edge, where a window is). Only a chain NEIGHBOUR is a partner: the
    declared OPEN edges run along the chain, and a pair of neighbours placed where the room's row
    was keeps both of them touching the rows above and below. Whether the whole chain survives
    the daylight re-ordering is checked afterwards (`_access_intact`).
    """
    room = rows[index][0]
    chain = options.open_chain
    if room.zone_id not in chain or room.zone_id in options.never_shared:
        return []
    at = chain.index(room.zone_id)
    neighbours = [z for z in (chain[at - 1] if at > 0 else None,
                              chain[at + 1] if at + 1 < len(chain) else None) if z]
    # the partner that needs no daylight first: the corridor-facing member of a shared row only
    # gets a window at a column end, and `_daylight_order` would move the row there
    candidates = sorted(((j, row[0]) for j, row in enumerate(rows)
                         if j != index and len(row) == 1 and row[0].zone_id in neighbours
                         and row[0].zone_id not in options.never_shared),
                        key=lambda jr: (jr[1].role in DAYLIGHT_ROLES, abs(jr[0] - index)))
    out_all = []
    for j, partner in candidates:
        corridor_side = room if room.zone_id == options.hall_public else partner
        far_side = partner if corridor_side is room else room
        # a V-split places row[0] to the WEST and row[1] to the EAST (see `_orient_row`)
        paired = [far_side, corridor_side] if corridor_on_east else [corridor_side, far_side]
        out = [list(r) for i, r in enumerate(rows) if i != j]
        out[out.index(list(rows[index]))] = paired
        out_all.append(out)
    return out_all


def _repartition_rows(rows: list[list[ProgramRoom]], net_width: float, options: Repartition,
                      corridor_on_east: bool) -> list[list[ProgramRoom]]:
    """Tier 2: every lone room that has no shape band at `net_width` shares a row with a partner
    the access model permits — an open-group member first (a kitchen beside its dining area), a
    dependent's row otherwise (a WC or a bedroom taking the master's slot beside the ensuite).
    A room with no legal partner keeps its row and is refused downstream, exactly as before. The
    result is re-ordered for daylight and re-oriented for the corridor, because a shared row's
    corridor-facing member may now be one that needs a window."""
    def finished(candidate: list[list[ProgramRoom]]) -> list[list[ProgramRoom]]:
        return _finish_rows(candidate, options, corridor_on_east)

    out = [list(r) for r in rows]
    changed = False
    seen: set[str] = set()
    while True:
        index = next((i for i, row in enumerate(out)
                      if len(row) == 1 and row[0].zone_id not in seen
                      and room_depth_band_m(row[0].template, net_width) is None), None)
        if index is None:
            break
        seen.add(out[index][0].zone_id)
        if out[index][0].zone_id in options.never_shared:
            continue
        candidates = (_pair_with_open_member(out, index, options, corridor_on_east)
                      + _dependent_pairings(out, index))
        for candidate in candidates:
            if _access_intact(finished(candidate), options, corridor_on_east):
                out, changed = candidate, True
                break
    if not changed:
        return rows
    return finished(out)


def _access_intact(rows: list[list[ProgramRoom]], options: Repartition,
                   corridor_on_east: bool) -> bool:
    """Every declared connection these rows must realize still has a physical interface: each
    OPEN connection of the chain, each dependent room's door to its host, and the hall's opening
    into the zone that carries it (which must therefore touch the corridor).

    Two rooms share an edge when they are in one row (the V cut) or in ADJACENT rows where at
    least one of them spans the column, or both sit in the same slot. Two shared rows with the
    members in opposite slots only overlap by whatever their widths happen to leave, which is not
    a connection to promise.
    """
    where: dict[str, tuple[int, int | None]] = {}
    for i, row in enumerate(rows):
        for slot, room in enumerate(row):
            where[room.zone_id] = (i, slot if len(row) == 2 else None)

    def touch(a: str, b: str) -> bool:
        (ia, sa), (ib, sb) = where[a], where[b]
        return ia == ib or (abs(ia - ib) == 1 and (sa is None or sb is None or sa == sb))

    chain = [z for z in options.open_chain if z in where]
    if not all(touch(a, b) for a, b in zip(chain, chain[1:])):
        return False
    for row in rows:
        for room in row:
            if room.entered_from and room.entered_from in where \
                    and not touch(room.zone_id, room.entered_from):
                return False
    if options.hall_public in where:
        i, slot = where[options.hall_public]
        corridor_slot = 1 if corridor_on_east else 0
        if slot is not None and slot != corridor_slot:
            return False
    return True


def _finish_rows(candidate: list[list[ProgramRoom]], options: Repartition,
                 corridor_on_east: bool) -> list[list[ProgramRoom]]:
    """A re-partitioned row list made plan-ready: re-ordered for daylight and every shared row
    re-oriented for the corridor — a shared row's corridor-facing member may now be one that
    needs a window. Shared by tier 2 and the quality tier."""
    return [_orient_row(r, corridor_on_east) if any(m.entered_from for m in r) else r
            for r in _daylight_order(candidate, north_is_envelope=options.north_is_envelope)]


# --------------------------------------------------------------------------- quality tier (2026-09-16)
#
# Re-partition for room PROPORTIONS. Measured over the 431-context log (docs/
# ROOM_PROPORTION_REPARTITION_REPORT.md): 85 % of delivered plans leave a bedroom-class room past
# 1.6, almost all of them a lone full-width row across a ~5 m column — a bedroom at its 2.6 m
# floor, a safe room at its 2.4 m — and the one legal move that reshapes such a room is the
# pairing tier 2 already knows: a lone room of any role takes the master's corridor-facing slot
# beside the ensuite and the master goes full-width (`_dependent_pairings`). Applied as a quality
# move beside a plan that succeeded (rather than as the repair of a shape refusal) it brings the
# worst bedroom-class aspect of a plan from a median 1.98 to 1.56 in 132 of 350 replayed spine
# primaries, at the same footprint and area. Its ceiling is topology: one ensuite per programme,
# one host slot. Nothing here shrinks a room, relaxes a maximum, moves a wet room's door or
# changes the ranking — a quality candidate is an ADDITIONAL candidate, ordered last.

#: Marker appended to a quality-tier candidate's rationale.
QUALITY_RATIONALE = "; rows re-partitioned for room proportions (quality)"
#: Which tier `_quality_score` judges a role in — PRIVATE (bedroom-class) strictly before SERVICE
#: (wet), see that function. Keyed by ROLE, not by a `ProgramRoom.group` lookup, so a caller that
#: only has a role (`general_pipeline._prefer_quality_twin`'s realized-shape check, which reads
#: `ZoneSpec.primary_role`, not a `ProgramRoom`) can supply the same grouping without a second
#: role list to keep in sync. Mirrors `build_room_program`'s own, unconditional group assignment
#: for exactly these five roles (2026-09-16, docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md).
_QUALITY_TIER_GROUP: dict[ProgramRole, ZoneGroup] = {
    ProgramRole.BEDROOM: ZoneGroup.PRIVATE,
    ProgramRole.MASTER_BEDROOM: ZoneGroup.PRIVATE,
    ProgramRole.SAFE_ROOM: ZoneGroup.PRIVATE,
    ProgramRole.BATHROOM: ZoneGroup.SERVICE,
    ProgramRole.TOILET: ZoneGroup.SERVICE,
}
#: How many legal pairings a plan may be re-partitioned with, best-estimated first — the bound on
#: the search beside the normal nine seams (`_seam_options`) each attempt keeps.
_MAX_QUALITY_PAIRINGS = 3
#: The least a plan's worst bedroom-class aspect must move toward its target for the re-partitioned
#: plan to be offered at all: a swap that merely shuffles which room is the strip is not a plan.
_QUALITY_MIN_GAIN = 0.1
#: How far past its preferred aspect a room that was INSIDE it may be carried by the pairing. The
#: host goes full-width across its column, and a 4.8 m wide master at its 3.0-3.1 m depth is 1.55:
#: refusing that kept the 4.8 m L arm's best pairing (a 1.96 safe room to 1.2 beside a 1.25 master
#: to 1.55) off the table. Up to the trough between the two modes (1.5 + 0.1 = 1.6), never into
#: the strip mode; the plan's worst room must still have moved by `_QUALITY_MIN_GAIN`. Applies
#: unconditionally to PRIVATE rooms; for SERVICE rooms it is the FLAT allowance used whenever the
#: trade is not justified by a PRIVATE-tier gain (`_QUALITY_LOWER_TIER_SEVERE_FRACTION`, below,
#: applies instead when it is) — see `_quality_accepts`.
_QUALITY_SPILL = 0.1
#: 2026-09-17 (docs/WET_ROOM_QUALITY_TIER_IMPLEMENTATION_REPORT.md's follow-up): measured on the
#: 432-context corpus, `_QUALITY_SPILL` applied flat to SERVICE (wet) rooms too vetoed the ONLY
#: two cases it ever fired on — both a peer that squared four PRIVATE rooms at the cost of
#: carrying one previously-fine bathroom from 1.875 to 2.121 (a 0.121 spill against 2.0 preferred,
#: over the 0.1 flat allowance) — reverting the primary to the UNFIXED base plan instead. A
#: PRIVATE-tier gain is exactly the "meaningful improvement to higher-tier rooms" a lower-tier
#: soft degradation must not veto; wet rooms still need protection from a truly severe push,
#: which this ties to the room's OWN hard headroom rather than a second flat number: at most
#: halfway from its preferred aspect to its hard `max_aspect_ratio` (BATHROOM 2.0->3.0 allows up
#: to 2.5; TOILET 2.5->3.5 allows up to 3.0) — a bathroom at 2.121 clears this easily; one pushed
#: to, say, 2.7 would not. Hard limits, geometry validity and tier-1 rescue are untouched by this
#: constant; it only widens what the QUALITY tier's own soft spill guard tolerates, and only for
#: a trade a PRIVATE-tier gain already justifies.
_QUALITY_LOWER_TIER_SEVERE_FRACTION = 0.5


def _row_shapes(rows: list[list[ProgramRoom]], depths: list[float], net_width: float,
                ) -> dict[str, tuple[float, float]]:
    """zone -> the NET (width, depth) the planner gave it: rows at their chosen CENTERLINE depths,
    members at `_row_widths`' widths — the rectangles `_zone_spec` is built from, before the
    solver. The solver lands within the wall insets of these (`_largest_net_area_m2`)."""
    out: dict[str, tuple[float, float]] = {}
    for row, depth in zip(rows, depths):
        net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
        widths = _row_widths(row, net_width, net_d) or [net_width / len(row)] * len(row)
        for room, w in zip(row, widths):
            out[room.zone_id] = (w, net_d)
    return out


def _estimated_row_shapes(rows: list[list[ProgramRoom]], net_width: float,
                          areas: dict[str, float], hard: bool,
                          ) -> dict[str, tuple[float, float]] | None:
    """The shapes a column's rows would take at `net_width` BEFORE the column's depth is known:
    each row at the larger of its area quotient and its shape floor — `_row_depths`' wants, from
    which the surplus distribution can only deepen a row. None when a row cannot be shaped at
    this width at all. This ranks pairings inside `_rows_for_width`, where the column depth is
    not in hand; the plan a pairing produces is judged on its exact shapes afterwards
    (`_quality_accepts`)."""
    depths = []
    for row, allowance in zip(rows, _row_wall_allowances_m(rows, (True, True))):
        floor, failure = _row_depth_floor_m(row, net_width, "column", allowance, hard)
        if failure is not None:
            return None
        depths.append(max(sum(areas[r.zone_id] for r in row) / max(net_width, 1e-6), floor))
    return _row_shapes(rows, depths, net_width)


def _preferred_aspects(shapes: dict[str, tuple[float, float]], rooms: Iterable[ProgramRoom],
                       ) -> dict[str, float]:
    """zone -> planned aspect (long/short), for every room that carries a preferred aspect.

    An ENSUITE-kind room is excluded regardless of its template's `preferred_aspect_ratio`
    (2026-09-16, docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md §5): it is always V-split into its
    host bedroom's row (`_rows_of`), so its shape comes from the ROW's combined depth, not its
    own area/width — a different mechanism from the lone SHARED_BATHROOM/GUEST_WC row this
    objective targets. Left for the ensuite-sub-row's own future phase, untouched here."""
    out: dict[str, float] = {}
    for room in rooms:
        if (room.template.preferred_aspect_ratio is None or room.zone_id not in shapes
                or room.wet_kind is WetRoomKind.ENSUITE):
            continue
        w, d = shapes[room.zone_id]
        out[room.zone_id] = max(w, d) / max(min(w, d), 1e-6)
    return out


def _quality_shortfall(aspects: dict[str, float], rooms_by_zone: dict[str, ProgramRoom]) -> float:
    """How far the worst room sits past its preferred aspect; 0.0 when every room is inside."""
    return max((a - rooms_by_zone[z].template.preferred_aspect_ratio for z, a in aspects.items()),
               default=0.0)


#: PRIVATE (bedroom-class) is judged strictly BEFORE service/wet rooms in `_quality_score` and
#: `_quality_accepts` (2026-09-16, docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md): extending
#: `preferred_aspect_ratio` to BATHROOM/TOILET means a lone row's pairing can now be scored for
#: either class, and the two compete for the SAME single host slot a programme ever has. Measured
#: directly (`test_the_l_arm_gets_a_quality_candidate_through_the_generic_hook`): pooling both
#: classes into one "worst room" objective let a candidate that improved a bathroom from 3.0 to
#: 1.1 outrank — and REPLACE — one that improved the bedroom from 1.745 to 1.71, because the
#: bathroom's shortfall against its 2.0 preferred was simply larger. That is the host-slot
#: contention the investigation report's fix-A section flagged as a real risk, now closed by
#: ORDER rather than by a new threshold: a candidate is never preferred for what it does to a
#: SERVICE room if it makes any PRIVATE room worse. `ZoneGroup.PRIVATE`/`ZoneGroup.SERVICE` are
#: the existing groups `build_room_program` already assigns (bedroom-class is always PRIVATE, a
#: shared bathroom or WC is always SERVICE) — no new role list to keep in sync.
def _quality_score(aspects: dict[str, float], rooms_by_zone: dict[str, ProgramRoom],
                   ) -> tuple[float, int, float, int, float]:
    """(PRIVATE worst shortfall, PRIVATE rooms past target, SERVICE worst shortfall, SERVICE rooms
    past target, mean aspect over every scored room) — lower is better, compared in that order.
    The worst PRIVATE room is what a person sees first; the count is what the one pairing a
    programme has can still change when two lone rooms are equally poor (a 4.8 m arm holding a
    bedroom AND the safe room at 1.85: pairing either leaves the other as the worst). SERVICE
    (wet) rooms are scored the same way, one full tier lower, so they can only ever break a tie
    the PRIVATE rooms leave open."""
    def tier(sub: dict[str, float]) -> tuple[float, int]:
        short = _quality_shortfall(sub, rooms_by_zone)
        over = sum(1 for z, a in sub.items()
                   if a > rooms_by_zone[z].template.preferred_aspect_ratio + 1e-6)
        return round(short, 4), over

    private = {z: a for z, a in aspects.items()
              if _QUALITY_TIER_GROUP.get(rooms_by_zone[z].role) is ZoneGroup.PRIVATE}
    service = {z: a for z, a in aspects.items()
              if _QUALITY_TIER_GROUP.get(rooms_by_zone[z].role) is ZoneGroup.SERVICE}
    p_short, p_over = tier(private)
    s_short, s_over = tier(service)
    mean = sum(aspects.values()) / max(len(aspects), 1)
    return (p_short, p_over, s_short, s_over, round(mean, 4))


def _quality_accepts(base: dict[str, float], new: dict[str, float],
                     rooms_by_zone: dict[str, ProgramRoom]) -> bool:
    """A re-partitioned plan is offered only if it does not leave any PRIVATE (bedroom-class) room
    worse than the base (worst shortfall up, or more rooms past target) — checked strictly first
    — AND, given that, either PRIVATE or SERVICE (wet) rooms improve by at least
    `_QUALITY_MIN_GAIN` toward their target (or, no worse, one room fewer past it) — AND no room
    that was inside its preferred aspect is carried too far past it. A SERVICE room's gain is
    never accepted at a PRIVATE room's expense (see `_quality_score`).

    The spill allowance is TIER-RELATIVE, not a single flat number (2026-09-17): a PRIVATE room
    is always held to `_QUALITY_SPILL` — a soft SERVICE-side degradation must never cost a
    bedroom-class room anything beyond what the rule always allowed. A SERVICE room gets the same
    flat `_QUALITY_SPILL` UNLESS the PRIVATE tier is what is actually improving this trade, in
    which case its allowance widens to `_QUALITY_LOWER_TIER_SEVERE_FRACTION` of its own hard
    headroom — still refusing anything that reaches a materially severe degradation, just not
    vetoing a real bedroom-class win over a comfortably-inside-hard-limits wet room."""
    base_p_short, base_p_over, base_s_short, base_s_over, _ = _quality_score(base, rooms_by_zone)
    new_p_short, new_p_over, new_s_short, new_s_over, _ = _quality_score(new, rooms_by_zone)
    if new_p_short > base_p_short + 1e-6 or new_p_over > base_p_over:
        return False

    def improves(new_short: float, base_short: float, new_over: int, base_over: int) -> bool:
        return (new_short <= base_short - _QUALITY_MIN_GAIN + 1e-9
                or (new_short <= base_short + 1e-6 and new_over < base_over))

    private_improves = improves(new_p_short, base_p_short, new_p_over, base_p_over)
    if not (private_improves
            or improves(new_s_short, base_s_short, new_s_over, base_s_over)):
        return False
    for zone, aspect in new.items():
        room = rooms_by_zone[zone]
        preferred = room.template.preferred_aspect_ratio
        if base.get(zone, aspect) > preferred + 1e-6:
            continue  # already past preferred in the base plan: nothing here to spill
        tier = _QUALITY_TIER_GROUP.get(room.role)
        if tier is ZoneGroup.SERVICE and private_improves:
            hard = room.template.max_aspect_ratio
            allowance = _QUALITY_LOWER_TIER_SEVERE_FRACTION * (hard - preferred)
        else:
            allowance = _QUALITY_SPILL
        if aspect > preferred + allowance + 1e-6:
            return False
    return True


def _quality_candidates(rows: list[list[ProgramRoom]], net_width: float, areas: dict[str, float],
                        options: Repartition, corridor_on_east: bool,
                        ) -> list[list[list[ProgramRoom]]]:
    """The legal re-partitions of `rows` that bring the column's worst PRIVATE (bedroom-class) or
    SERVICE (wet) room toward its preferred aspect at `net_width` — PRIVATE judged first, so a
    candidate is ranked ahead only where it does not cost a PRIVATE room anything (`_quality_score`)
    — best-estimated first, at most `_MAX_QUALITY_PAIRINGS`.

    Only the dependent pairing is tried (`_dependent_pairings`): a lone row of ANY role — a shared
    bath, the safe room, a bedroom, a WC, a closed kitchen — takes the host's corridor-facing slot
    beside the ensuite, and the host (always a bedroom-class room) goes full-width; the ensuite
    keeps its door across the row edge. The open-chain pairing (`_pair_with_open_member`) reshapes
    public rooms, which is outside this tier's objective, and is left to tier 2. Legality is
    exactly tier 2's (`_access_intact` after `_finish_rows`); FLEX never shares a row.
    """
    by_zone = {r.zone_id: r for row in rows for r in row}
    base = _estimated_row_shapes(rows, net_width, areas, options.hard)
    if base is None:
        return []
    base_aspects = _preferred_aspects(base, by_zone.values())
    if _quality_shortfall(base_aspects, by_zone) <= 1e-6:
        return []  # every scored room (PRIVATE or SERVICE) is already inside its preferred aspect
    base_score = _quality_score(base_aspects, by_zone)
    ranked: list[tuple[tuple[float, int, float, int, float], tuple, list[list[ProgramRoom]]]] = []
    seen: set[tuple] = set()
    for index, row in enumerate(rows):
        if len(row) != 1 or row[0].zone_id in options.never_shared:
            continue
        for candidate in _dependent_pairings(rows, index):
            finished = _finish_rows(candidate, options, corridor_on_east)
            key = tuple(tuple(r.zone_id for r in rr) for rr in finished)
            if key in seen or not _access_intact(finished, options, corridor_on_east):
                continue
            seen.add(key)
            shapes = _estimated_row_shapes(finished, net_width, areas, options.hard)
            if shapes is None:
                continue
            score = _quality_score(_preferred_aspects(shapes, by_zone.values()), by_zone)
            if score < base_score:
                ranked.append((score, key, finished))
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in ranked[:_MAX_QUALITY_PAIRINGS]]


def _quality_repartition_rows(rows: list[list[ProgramRoom]], net_width: float,
                              areas: dict[str, float], options: Repartition,
                              corridor_on_east: bool) -> list[list[ProgramRoom]]:
    """The `options.quality_rank`-th best quality re-partition at this width, or the rows
    unchanged when there is none of that rank — the caller then finds the base plan again and
    stops (`_quality_layouts`)."""
    candidates = _quality_candidates(rows, net_width, areas, options, corridor_on_east)
    if options.quality_rank < len(candidates):
        return candidates[options.quality_rank]
    return rows


#: Roles eligible for `_rows_for_width`'s tier-1 rescue below. This was `ZoneGroup.SERVICE` (an
#: attribute, not a role list) until measurement (2026-09-16,
#: docs/LAUNDRY_ROOM_PHASE1_REPORT.md §3) found that the group is WIDER than what was actually
#: proven safe: on the real 418-context corpus, widening to the full group also rescued a lone
#: BATHROOM in 1 of 404 previously-planned briefs — a different, still-valid plan, but a real
#: deviation from this phase's own "no change to an existing brief" bar. TOILET (2026-09-14) and
#: LAUNDRY (this phase) are the two roles actually measured safe here. BATHROOM's own eligibility
#: for this rescue is a real, separate question — already in motion as its own measured
#: row-sharing quality initiative (see project memory) — and is deliberately left to that
#: decision rather than entering as a side effect of the laundry gate.
_ROW_RESCUE_ROLES = (ProgramRole.TOILET, ProgramRole.LAUNDRY)


def _rows_for_width(rows: list[list[ProgramRoom]], net_width: float,
                    fallback: Repartition | None = None,
                    corridor_on_east: bool = True,
                    areas: dict[str, float] | None = None) -> list[list[ProgramRoom]]:
    """The rows a column plans with at `net_width`.

    The normal path (no `fallback`) keeps a column's rows, with one settled exception: a lone
    room of a `_ROW_RESCUE_ROLES` role that cannot be shaped at this width (`room_depth_band_m`
    is None — it would be a strip or oversized) and is not itself a dependent shares an ensuite's
    row (`_pair_with_dependent`); a column with no ensuite keeps its rows and is refused downstream
    with its own reason. This was the WC's fix (2026-09-14) and now also reaches a requested
    laundry room (2026-09-16, docs/LAUNDRY_ROOM_PHASE1_REPORT.md) — same mechanism, same
    eligibility test: `_pair_with_dependent`'s swap is safe for ANY room that is (a) hall-facing
    already (`not entered_from`, so the swap cannot orphan a door) and (b) not an open-plan member
    (a PUBLIC room's legal partner is a chain neighbour, `_pair_with_open_member`, which this fast
    path does not try; that is tier 2's job) — `_ROW_RESCUE_ROLES` narrows that GENERAL condition
    to the roles measurement has actually cleared, not the other way round.

    Tier 2 (`fallback` given, `fallback.quality` False) applies the fuller idea to ANY room, with
    every partner the access model permits (`_repartition_rows`), open-chain pairing included —
    tier 2 was never narrowed, since its own eligibility is already proven generic by
    `test_tier2_pairs_a_bedroom_with_the_ensuite_row_and_puts_it_at_a_column_end` and was not part
    of what the laundry phase measured or changed. The QUALITY tier (`fallback.quality` True)
    instead starts from the rescue's own rows and re-partitions for proportions
    (`_quality_repartition_rows`), across BOTH the PRIVATE (bedroom-class) and SERVICE (wet) tiers
    `f2092af` added; it needs the row `areas` to estimate shapes at this width. The two mechanisms
    are independent: the quality tier's own candidate search only considers rows still of length
    1, so it never re-touches a row the rescue above has already paired, and `_ROW_RESCUE_ROLES`'
    LAUNDRY is invisible to it either way — LAUNDRY carries no `preferred_aspect_ratio` and is not
    in `_QUALITY_TIER_GROUP`, both deliberately left unchanged by the laundry work.
    """
    if fallback is not None and not fallback.quality:
        return _repartition_rows(rows, net_width, fallback, corridor_on_east)
    for i, row in enumerate(rows):
        if (len(row) == 1 and row[0].role in _ROW_RESCUE_ROLES and not row[0].entered_from
                and room_depth_band_m(row[0].template, net_width) is None):
            shared = _pair_with_dependent(rows, i)
            if shared is not None:
                rows = shared
                break
    if fallback is not None:
        if areas is None:
            raise ValueError("the quality tier needs the row areas to estimate shapes")
        return _quality_repartition_rows(rows, net_width, areas, fallback, corridor_on_east)
    return rows


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


def _seam_options(natural_m: float, lo_m: float, hi_m: float,
                  limit: int | None = _MAX_SEAM_OPTIONS) -> list[float]:
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

    `limit=None` (tier 2, `Repartition`) walks the whole feasible window in the same order: a
    column that must narrow by more than the nine steps allow — a 7 m bedroom column that can be
    at most 5.9 m — is reached only then.
    """
    if hi_m < lo_m - 1e-9:
        return []
    natural = min(max(natural_m, lo_m), hi_m)

    def snapped(value: float) -> float:
        return round(min(max(value, lo_m), hi_m) / 0.05) * 0.05

    out = [snapped(natural)]
    offset = _SEAM_STEP_M
    while (limit is None or len(out) < limit) and offset <= (hi_m - lo_m) + _SEAM_STEP_M:
        for candidate in (natural + offset, natural - offset):
            if lo_m - 1e-9 <= candidate <= hi_m + 1e-9:
                value = snapped(candidate)
                if all(abs(value - seen) > 1e-9 for seen in out):
                    out.append(value)
                    if limit is not None and len(out) >= limit:
                        break
        offset += _SEAM_STEP_M
    return out


def _columns_at_seam(west_w: float, east_w: float, west_rows: list[list[ProgramRoom]],
                     east_rows: list[list[ProgramRoom]], areas: dict[str, float],
                     footprint_h_m: float, fallback: Repartition | None = None,
                     allow_deficit: bool = False, allow_hard: bool = False,
                     ) -> tuple[list[ColumnPlan] | None, PlanFailure | None]:
    """Both columns planned at ONE seam position — the unit the seam search repeats."""
    plans = []
    for name, width, rows, corridor_on_east in (("west", west_w, west_rows, True),
                                                ("east", east_w, east_rows, False)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        if net_w <= 0:
            return None, PlanFailure(RejectionReason.COLUMN_WIDTH_EXCEEDED,
                                     f"{name} column has no net width at {width:.2f} m")
        rows = _rows_for_width(rows, net_w, fallback, corridor_on_east, areas)
        for row in rows:
            if _row_widths(row, net_w) is None:
                return None, PlanFailure(
                    RejectionReason.ROW_WIDTH_EXCEEDED,
                    f"{' + '.join(r.zone_id for r in row)} cannot share the {name} "
                    f"column's {net_w:.2f} m of net width at their minimums")
        depths, failure = _row_depths(rows, areas, net_w, footprint_h_m, f"{name} column",
                                      allow_deficit=allow_deficit, allow_hard=allow_hard)
        if depths is None:
            return None, failure
        plans.append(ColumnPlan(width, rows, depths))
    return plans, None


def _row_depths(rows: list[list[ProgramRoom]], areas: dict[str, float], net_width: float,
                column_depth: float, where: str = "column",
                ends_exterior: tuple[bool, bool] = (True, True), allow_deficit: bool = False,
                allow_hard: bool = False,
                ) -> tuple[list[float] | None, PlanFailure | None]:
    """Row depths, chosen DIRECTLY rather than inferred from areas.

    The first design drove depth from area (`depth = area / width`) and then tried to steer the
    areas until the depths came out legal. That is an unstable fixed point: a small room in a
    wide column is always too shallow, and nudging its area moves the column width too. Choosing
    the depth first — floored by each row's own shape band — and deriving the areas from
    `width x depth` afterwards makes the result feasible BY CONSTRUCTION.

    On refusal the failure names EVERY row and which of the two terms set its depth: the area
    quotient, or the row's own shape floor. That distinction is the whole diagnosis — a column can
    overflow with no room minimum involved anywhere, and the old message asserted the opposite
    ("at their minimum dimensions") in every case. A row that cannot be shaped at this width at all
    is a different refusal again (`ROOM_SHAPE_INFEASIBLE`), and carries its own code out.

    DEFICIT AS WELL AS SURPLUS. A row's wanted depth is the larger of its area quotient and its
    floor, and the area quotient is a TARGET, not a need: `scale_program` sized it to fill the
    footprint, and a room may legally be smaller (its ZoneSpec minimum is well under it). The
    pre-check used to compare the SUM OF WANTS against the column and refuse on any excess, so a
    column whose floors fit with metres to spare was refused for 4 cm of area-want — measured:
    the safe room's depth floor gaining the RC allowance it always needed (2.60 -> 2.70) turned
    eight planning briefs into refusals, each at every seam, with the floors summing to ~11.5 m
    against a 14 m column. Now the refusal is on the FLOORS: when the wants exceed the column but
    the floors fit, every row above its floor gives up the same share of what it wanted beyond
    the floor (`_shrink_to_column`), and the plan goes on at the footprint's own area. This is
    not the rejected 3 cm tolerance above — nothing is shaved below a floor and no proportion
    becomes feasible that its floors refuse; a proportion that fits only with its rooms at their
    floors was always a legal plan, just one this planner could not find.

    `allow_deficit` is asked for by `_build` / the front band only AFTER the normal attempt at a
    proportion failed, and the candidate it yields is marked `shrunk` (see `ConceptCandidate`):
    every plan that planned at its wants still plans the same way, and shrinking rescues what
    could not plan at all.

    `where` names the column in the failure text; the reason code is the planner's to keep.
    """
    wanted = []
    floors = []
    terms = []
    allowances = _row_wall_allowances_m(rows, ends_exterior)
    for row, allowance in zip(rows, allowances):
        area = sum(areas[r.zone_id] for r in row)
        # The floor is the row's shape band, not its short side alone: a wet room alone in a wide
        # column is floored by width / aspect, and refused outright where that floor would already
        # exceed its maximum area (`room_depth_band_m`).
        floor, failure = _row_depth_floor_m(row, net_width, where, allowance, allow_hard)
        if failure is not None:
            return None, failure
        by_area = area / max(net_width, 1e-6)
        wanted.append(max(by_area, floor))
        floors.append(floor)
        ids = "+".join(r.zone_id for r in row)
        terms.append(f"{ids} {floor:.2f} (shape floor, area wanted {by_area:.2f})"
                     if floor > by_area else f"{ids} {by_area:.2f} (area, floor {floor:.2f})")
    if not allow_hard:
        # A row whose FLOOR is already past its preferred maximum (a bedroom 6.1 m wide at its
        # 2.6 m short side is 15.9 m2 against 14) can only be planned by a caller allowed to
        # exceed preferred; the band under the hard maximum exists, so the hard pass plans it.
        # Measured on the planned net rectangle, the same rule as `_shape_failure` — not on the
        # conservative ceiling the distribution uses, which would send rows that realize inside
        # preferred to the hard fallback ahead of a tier-2 plan that stays inside. Checked AFTER
        # every row's shape: a strip refusal in a later row is the diagnosis tier 2 acts on, and
        # must not be masked by an earlier row's size.
        failure = _verify_row_shapes(rows, floors, net_width, where, hard=False)
        if failure is not None and failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA:
            # The hard pass does not make this check at all (it clamps the row to its ceiling
            # instead), so it can plan the row whether or not the room has hard headroom.
            return None, replace(failure, hard_fixable=True)
    need = sum(floors)
    if need > column_depth + 1e-9:  # exact on purpose — see the rejected-tolerance note above
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"{where} needs {need:.2f} m of depth for its rows' floors but has {column_depth:.2f} m "
            f"[{'; '.join(terms)}]", need - column_depth)
    if sum(wanted) > column_depth + 1e-9:
        if not allow_deficit:
            return None, PlanFailure(
                RejectionReason.COLUMN_DEPTH_EXCEEDED,
                f"{where} needs {sum(wanted):.2f} m of depth but has {column_depth:.2f} m "
                f"[{'; '.join(terms)}]", sum(wanted) - column_depth, deficit_fixable=True)
        wanted = _shrink_to_column(wanted, floors, column_depth)
    depths, failure = _distribute_column_surplus(rows, wanted, net_width, column_depth, where,
                                                 floors=floors, allow_hard=allow_hard)
    if depths is None:
        return None, _after_distribution(failure, rows, allow_hard)
    # The surplus can deepen a shared row past what its narrow member's width allows (the ensuite
    # stood on end), and the width shift can carry a member past its maximum; the widths are
    # re-derived from the final depth and every member re-checked for shape AND area.
    failure = _verify_row_shapes(rows, depths, net_width, where, allow_hard)
    if failure is not None:
        return None, _after_distribution(failure, rows, allow_hard)
    return depths, None


#: The thinnest inset a CLOSED room can lose on one side: half a partition. The planner's flat
#: allowance (`_EDGE_INSET_ALLOWANCE_M`) assumes an exterior half on one side and a partition half
#: on the other, but Geometry Core insets by the wall each side actually gets, and a room can get
#: LESS than the allowance assumed — the interior member of a shared row has partitions both sides
#: (0.05 + 0.05, not 0.15 + 0.05), and an open-plan zone has NO wall on its open sides. A realized
#: net area can therefore exceed the planner's net by up to 0.10 x depth for a closed room and
#: 0.20 x depth for an open-plan one. The maxima are hard, so a ceiling has to be taken on the
#: LARGEST net the room can come back with, not the allowance's estimate.
_MIN_SIDE_INSET_M = WALL_THICKNESS_M[WallType.PARTITION] / 2


def _largest_net_area_m2(room: ProgramRoom, gross_w: float, gross_d: float) -> float:
    """The largest NET area a room planned at this CENTERLINE rectangle can come back with.

    A public zone may be open on any side (the open groups are the public zones and nothing
    else, `_build_access`), so its bound is the gross rectangle. Any other room has at least half
    a partition on every side. Measured: a dining room planned at 7.00 x 4.25 = 29.75 m2 net came
    back 7.15 x 4.25 = 30.4 against its 30 m2 maximum — and with the ZoneSpec capped at the
    maximum the forced tree was infeasible, where the 1.6x band used to absorb exactly this.
    """
    if room.group is ZoneGroup.PUBLIC:
        return gross_w * gross_d
    return max(gross_w - 2 * _MIN_SIDE_INSET_M, 0.0) * max(gross_d - 2 * _MIN_SIDE_INSET_M, 0.0)


def _row_depth_ceiling_m(row: list[ProgramRoom], net_width: float, depth_m: float,
                         hard: bool = False) -> float:
    """The deepest CENTERLINE depth (5 cm grid) at which every member of `row` is still inside
    its template MAXIMUM AREA, at the widths THAT depth gives it. Held on `_largest_net_area_m2`,
    the biggest net rect a member can realize, not on the planner's flat allowance.

    A fixed point, not a formula: in a shared row the widths follow the depth (`_row_widths` —
    the narrow member's aspect minimum grows with depth, so it widens and its partner narrows)
    and the binding member changes with them. Measured on BATH_1 + MASTER at 5.35 m: at 3.8 m
    deep the master binds at 5.80; at 5.80 the bath has widened, the master narrowed, and the
    bath binds at 5.95; at 5.95 the bath binds at 5.85. The answer is the deepest grid depth D
    with ceiling(D) >= D — 5.90 here — found from the first estimate by stepping down until the
    row is inside its maxima and then up while it stays so. `depth_m` is only where the search
    starts."""
    step = 0.05
    share = _EDGE_INSET_ALLOWANCE_M / len(row)  # a member's centerline width beyond its net share

    def at(depth: float) -> float:
        """The depth at which the first member reaches its maximum, at this depth's widths."""
        net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
        widths = _row_widths(row, net_width, net_d) or [net_width / len(row)] * len(row)
        found = math.inf
        for room, w in zip(row, widths):
            gross_w = w + share
            # depth D such that _largest_net_area_m2(room, gross_w, D) == max_area
            limit = room.template.ceiling_m2(hard)
            if room.group is ZoneGroup.PUBLIC:
                found = min(found, limit / max(gross_w, 1e-6))
            else:
                found = min(found, limit
                            / max(gross_w - 2 * _MIN_SIDE_INSET_M, 1e-6) + 2 * _MIN_SIDE_INSET_M)
        return math.floor(found / step + 1e-9) * step

    ceiling = at(depth_m)
    for _ in range(40):                      # down to a depth the row is inside its maxima at
        if at(ceiling) >= ceiling - 1e-9:
            break
        ceiling -= step
    for _ in range(40):                      # then up, while it stays inside
        if at(ceiling + step) < ceiling + step - 1e-9:
            break
        ceiling += step
    return round(ceiling / step) * step


def _shrink_to_column(wanted: list[float], floors: list[float], column_depth: float) -> list[float]:
    """The wanted depths scaled DOWN to the column, each row keeping the same fraction of what it
    wanted beyond its floor — so no row drops below its floor and the rows still tile the column.
    Callers check `sum(floors) <= column_depth` first; with nothing above the floors to give, the
    floors themselves are returned."""
    slack = [max(w - f, 0.0) for w, f in zip(wanted, floors)]
    total = sum(slack)
    if total <= 1e-9:
        return list(floors)
    keep = max(0.0, (column_depth - sum(floors)) / total)
    return [f + s * keep for f, s in zip(floors, slack)]


def _distribute_column_surplus(rows: list[list[ProgramRoom]], wanted: list[float],
                               net_width: float, column_depth: float, where: str,
                               floors: list[float] | None = None, allow_hard: bool = False,
                               ) -> tuple[list[float] | None, PlanFailure | None]:
    """The column's spare depth spread over its rows by EXPANSION PRIORITY and BOUNDED by each
    row's template maxima — or the refusal that the column cannot absorb it.

    THE RULE THAT MAKES THE MAXIMA HARD. A column runs the footprint's full depth and a row runs
    the column's full width, so every metre of depth the rows' own needs leave over has to land on
    SOME row, and it used to land by elasticity alone: a bathroom got 0.15 of every metre whether
    or not it was already 12 m2, and a safe room — elasticity 0, the one room that must never
    grow — got the same 0.15 through the weight floor that kept the division defined. Measured
    over the demo's programmes and outlines: 56 % of plans had a room past its maximum, a
    bathroom reached 62 m2 alone in a rear column, a safe room 30 m2.

    Water-filling instead: each row's ceiling is the depth at which its first member reaches its
    maximum (`_row_depth_ceiling_m`); surplus is shared by elasticity among the rows still under
    their ceiling, a row that reaches it leaves the pool and the residue REDIRECTS to the rest —
    the same drop-from-the-pool loop `scale_program` uses for areas — and a row whose members all
    have elasticity 0 never joins the pool. What no row can take is a refusal
    (`ROOM_ABOVE_MAXIMUM_AREA`) for this seam; the seam search and the proportion search then do
    what they exist for, and a programme that cannot fill the outline within its maxima reaches
    the capacity refusal instead of a 62 m2 bathroom.

    TWO CEILINGS. The pool fills to the PREFERRED maxima first; only the residue no row could
    take within them is offered — when `allow_hard` — a second time against the HARD maxima, to
    the same elastic rows. A zero-elasticity row (the safe room) is in neither pool: it never
    grows past its want to fill space, whatever ceiling is in force. Callers ask for the hard
    pass only after a proportion could not be planned within the preferred maxima at all, and
    mark the candidate `over_preferred` so it ranks behind an equal plan that stayed inside.

    The grid: every depth is rounded to 5 cm and clamped to its ceiling (itself on the grid), and
    the tiling is exact, so any centimetres the rounding leaves are given to rows with headroom
    5 cm at a time — never to a row at its ceiling — and any centimetres the rounding overshoots
    by are taken back from rows still above their `floors` (the wants, when none are given).
    """
    step = 0.05
    weights = [sum(r.template.elasticity for r in row) for row in rows]
    ceilings = [_row_depth_ceiling_m(row, net_width, d) for row, d in zip(rows, wanted)]
    hard_ceilings = ([_row_depth_ceiling_m(row, net_width, d, hard=True) for row, d in zip(rows, wanted)]
                     if allow_hard else None)
    # A shared row's narrow member widens as the row deepens (its aspect minimum,
    # `_row_widths`), so a ceiling taken at the wanted depth can sit too high once surplus has
    # deepened the row: BATH_1 came out 2.08 x 5.85 = 12.1 m2. The ceilings are therefore
    # re-taken at the distributed depths and the distribution repeated; a ceiling only ever
    # falls, so this settles in a pass or two.
    for _ in range(4):
        # A row's wanted depth can sit above its ceiling by the floor's extra wall allowance (the
        # floor carries the full allowance, the ceiling the half that `_zone_spec` nets off), or
        # when a shared row's area share lands past its narrow member's maximum; either way the
        # ceiling wins and the depth it frees is surplus like any other.
        depths = [min(d, c) for d, c in zip(wanted, ceilings)]
        remaining = column_depth - sum(depths)
        for _ in range(len(rows) + 1):
            if remaining <= 1e-9:
                break
            pool = [i for i in range(len(rows)) if weights[i] > 0 and depths[i] < ceilings[i] - 1e-9]
            if not pool:
                break
            wsum = sum(weights[i] for i in pool)
            for i in pool:
                depths[i] += min(remaining * weights[i] / wsum, ceilings[i] - depths[i])
            remaining = column_depth - sum(depths)
        settled = [min(c, _row_depth_ceiling_m(row, net_width, d))
                   for row, d, c in zip(rows, depths, ceilings)]
        if all(abs(a - b) < 1e-9 for a, b in zip(settled, ceilings)):
            break
        ceilings = settled

    if hard_ceilings is not None and column_depth - sum(depths) > 1e-9:
        # The residue against the hard maxima, same pool rule, same rows; the ceilings in force
        # from here on are the hard ones (re-taken at the deeper depths like the preferred ones).
        for _ in range(4):
            remaining = column_depth - sum(depths)
            for _ in range(len(rows) + 1):
                if remaining <= 1e-9:
                    break
                pool = [i for i in range(len(rows)) if weights[i] > 0 and depths[i] < hard_ceilings[i] - 1e-9]
                if not pool:
                    break
                wsum = sum(weights[i] for i in pool)
                for i in pool:
                    depths[i] += min(remaining * weights[i] / wsum, hard_ceilings[i] - depths[i])
                remaining = column_depth - sum(depths)
            settled = [min(c, _row_depth_ceiling_m(row, net_width, d, hard=True))
                       for row, d, c in zip(rows, depths, hard_ceilings)]
            if all(abs(a - b) < 1e-9 for a, b in zip(settled, hard_ceilings)):
                break
            hard_ceilings = settled
            depths = [min(d, c) for d, c in zip(depths, hard_ceilings)]
        ceilings = hard_ceilings

    depths = [min(round(d / step) * step, c) for d, c in zip(depths, ceilings)]
    residual = round((column_depth - sum(depths)) / step)
    lows = list(floors) if floors is not None else list(wanted)
    while residual < 0:
        # Rounding overshot the column: take a grid step back from the row with the most depth
        # above its floor, never from one at its floor.
        candidates = [i for i in range(len(rows)) if depths[i] - step >= lows[i] - 1e-9]
        if not candidates:
            break
        i = max(candidates, key=lambda j: depths[j] - lows[j])
        depths[i] -= step
        residual += 1
    while residual > 0:
        # An ELASTIC row with headroom takes a grid step; a zero-elasticity row never does, not
        # even the rounding of its neighbours — the rule is that it receives no surplus at all.
        candidates = [i for i in range(len(rows))
                      if weights[i] > 0 and depths[i] + step <= ceilings[i] + 1e-9]
        if not candidates:
            break
        i = max(candidates, key=lambda j: (ceilings[j] - depths[j], weights[j]))
        depths[i] += step
        residual -= 1
    if residual < 0:
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"{where}'s rows at their floors, on the 5 cm grid, exceed its {column_depth:.2f} m "
            f"by {-residual * step:.2f} m", -residual * step)
    if residual > 0:
        ceiling_terms = "; ".join(
            f"{'+'.join(r.zone_id for r in row)} at most {c:.2f} m ({', '.join(f'{r.zone_id} {r.template.ceiling_m2(allow_hard):.0f} m2' for r in row)})"
            for row, c in zip(rows, ceilings))
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"{where} has {residual * step:.2f} m of depth no row can take within its rooms' "
            f"{'hard' if allow_hard else 'preferred'} maximum areas [{ceiling_terms}]", residual * step,
            hard_fixable=not allow_hard and any(r.template.hard_max > r.template.max_area_m2 + _AREA_TOL_M2
                                                 for row in rows for r in row))
    return depths, None


def plan_layout(rooms: list[ProgramRoom], west: list[ProgramRoom], east: list[ProgramRoom],
                hall_ids: list[str], footprint_w_m: float, footprint_h_m: float,
                corridor: CorridorRequirement | None = None,
                fallback: Repartition | None = None, allow_deficit: bool = False,
                allow_hard: bool = False,
                ) -> tuple[LayoutPlan | None, PlanFailure | None]:
    """Column widths, row depths and the resulting zone specs, all mutually consistent.

    With `fallback` (tier 2) the seam search covers the whole feasible window and every column's
    rows may be re-partitioned at each seam; without it this is the normal path, unchanged.
    With `allow_deficit` a column whose rows' wants exceed it may shrink them toward their floors
    (`_row_depths`); the caller asks for that only after the normal attempt failed, and marks the
    candidate `shrunk`. With `allow_hard` rows may grow past their PREFERRED maxima up to the
    HARD ones (`RoomTemplate`); likewise only after the attempt inside the preferred maxima
    failed, and the candidate is marked `over_preferred`."""
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
    shape_seen = deficit_seen = hard_seen = False
    # Tier 2 walks the whole seam window; the QUALITY tier keeps the normal nine — the window is
    # the runtime knob (measured: a third of every planner call is a tier-2 seam walk).
    seams = _seam_options(natural_w, west_min, usable - east_min,
                          limit=None if fallback is not None and not fallback.quality
                          else _MAX_SEAM_OPTIONS)
    for seam_w in seams:
        east_w = round((usable - seam_w) / 0.05) * 0.05
        west_w = footprint_w_m - hall_w - east_w  # absorb rounding
        plans, failure = _columns_at_seam(west_w, east_w, west_rows, east_rows,
                                          areas, footprint_h_m, fallback, allow_deficit, allow_hard)
        if plans is not None:
            break
        shape_seen = shape_seen or failure.reason is RejectionReason.ROOM_SHAPE_INFEASIBLE
        deficit_seen = deficit_seen or failure.deficit_fixable
        hard_seen = hard_seen or failure.hard_fixable

    if plans is None:
        return None, replace(failure, shape_seen=shape_seen, deficit_fixable=deficit_seen,
                             hard_fixable=hard_seen)

    # Areas now FOLLOW the geometry: each zone's band is centred on the rect it will occupy. The
    # ASPECT RATIO does not: it is the template's, unrelaxed — see `_zone_spec`.
    specs: dict[str, ZoneSpec] = {}
    for plan in plans:
        net_w = plan.width_m - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(plan.rows, plan.row_depths_m):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths_in_row = _row_widths(row, net_w, net_d) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths_in_row):
                specs[room.zone_id] = _zone_spec(room, w, net_d, 0.60, 1.60, allow_hard)
    for hall_id in hall_ids:
        hall_depth = footprint_h_m / len(hall_ids)
        target = (hall_w - _EDGE_INSET_ALLOWANCE_M) * (hall_depth - _EDGE_INSET_ALLOWANCE_M / 2)
        specs[hall_id] = ZoneSpec(
            hall_id, (ProgramRole.HALL, ProgramRole.CIRCULATION),
            target * 0.55, target, target * 1.75,
            ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 12.0)
    failure = _specs_within_maxima(rooms, specs, "columns", allow_hard)
    if failure is not None:
        return None, failure

    return LayoutPlan(plans[0], plans[1], hall_w, specs), ""


def _roles_of(room: ProgramRoom) -> tuple[ProgramRole, ...]:
    if room.role is ProgramRole.HALL:
        return (ProgramRole.HALL, ProgramRole.CIRCULATION)
    return (room.role,)


def _zone_spec(room: ProgramRoom, net_w: float, net_d: float, lo: float, hi: float,
               hard: bool = False) -> ZoneSpec:
    """The ZoneSpec for a room the planner has placed in a NET `net_w x net_d` rectangle.

    The AREA band follows the planned rectangle (`lo`..`hi` times its area), because the wall
    insets Geometry Core applies differ from the flat allowance the planner used and the solved
    rect must be allowed to land near — not on — the plan. The ASPECT RATIO is the template's and
    nothing else. It used to be `max(template, planned aspect + 0.3)`, which handed the solver and
    validator C3 a limit derived from the very rectangle they were meant to judge: a 6.1 x 1.2 m WC
    got a 5.38 ceiling and passed. The planner is now held to the template BEFORE this point
    (`room_depth_band_m`), so a plan that reaches here already fits; if a future sizing path does
    not, the solver refuses the forced tree and the unforced twin re-proportions it — and C20
    measures the drawing against the template regardless of what any ZoneSpec says.
    """
    target = net_w * net_d
    # The band's bottom never sits under the template's MINIMUM either: a row shrunk to its floor
    # (deficit distribution) plans at or just above the minimum, and 0.6x that would let the
    # solver drift under it.
    # The band's top is the TEMPLATE'S maximum, never above it: `hi` only says how far the solved
    # rect may drift from the plan, and drifting past the room's ceiling was the one direction
    # that used to be allowed (DINING at 30.66 against 30; a bathroom at 62 against 12 — the
    # planned rectangle itself was over, and the band centred on it legitimised that). A planned
    # target above the maximum is the planner's error, refused by `_specs_within_maxima` where
    # `_row_depths` did not already prevent it.
    return ZoneSpec(room.zone_id, _roles_of(room),
                    min(max(target * lo, room.template.min_area_m2), target), target,
                    min(target * hi, room.template.ceiling_m2(hard)),
                    room.template.min_short_side_m, room.template.max_aspect_ratio)


def _specs_within_maxima(rooms: list[ProgramRoom], specs: dict[str, ZoneSpec],
                         where: str, hard: bool = False) -> PlanFailure | None:
    """The refusal for any planned room whose target sits above its template maximum, or None.

    The one gate every sizing path passes through after its ZoneSpecs exist — the column partis
    (already held by `_row_depths`, so this is their backstop), the front band's public band
    (held by its own cap) and the hub's flanks and foot (sized by the wing's geometry, with no
    distribution step of their own to bound). A planner that lets a room over its maximum fails
    the CANDIDATE here rather than handing Geometry Core a spec whose target exceeds its own cap.
    """
    for room in rooms:
        spec = specs.get(room.zone_id)
        if spec is None or room.role is ProgramRole.HALL:
            continue
        limit = room.template.ceiling_m2(hard)
        if spec.net_area_target_m2 > limit + _AREA_TOL_M2:
            return PlanFailure(
                RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
                f"{room.zone_id} is planned at {spec.net_area_target_m2:.1f} m2 in the {where}, "
                f"past its {limit:.0f} m2 {'hard ' if hard else 'preferred '}maximum",
                spec.net_area_target_m2 - limit, hard_fixable=not hard and _hard_headroom(rooms))
    return None


def _forced_chain(rows: list[list[ProgramRoom]], depths: list[float], net_width: float,
                  open_block: frozenset[str] = frozenset(), exterior_first: bool = True) -> Node:
    """Right-nested H chain with every cut forced to the depth chosen above; a shared row gets a
    forced V cut at its members' width share.

    `exterior_first`: whether the row's FIRST (west) member sits against the column's exterior
    wall — true for the west column, false for the east one, where the hall is on the west. The
    V cut lands at the first member's net width plus the two half-walls on its sides (exterior
    or partition, then the shared partition), so each member nets exactly the width
    `_row_widths` gave it whichever side the exterior is on.

    `open_block` (tier 2 only) names zones joined by OPEN connections: a run of consecutive rows
    whose rooms all belong to it is nested as its own sub-chain, so the cuts inside the run are
    inside one subtree of the group and Geometry Core marks them wall-less structurally
    (`_mark_open_interfaces`). A right-nested chain leaves the cut between the run's first row
    and the rest of the column outside any such subtree, and the geometric discovery that saves
    full-width rows (`_discover_open_interfaces`) needs FULL matching edges — which a shared row
    under a full-width one does not have. Measured: LIVING over [KITCHEN | DINING] came out with
    a partition between them and failed C13. Without `open_block` the tree is exactly as before.
    """
    def row_node(row: list[ProgramRoom], depth: float) -> Node:
        if len(row) == 1:
            return Leaf(row[0].zone_id)
        net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
        widths = _row_widths(row, net_width, net_d) or [net_width / len(row)] * len(row)
        outer = WALL_THICKNESS_M[WallType.EXTERIOR if exterior_first else WallType.PARTITION] / 2
        first_w = widths[0] + outer + WALL_THICKNESS_M[WallType.PARTITION] / 2
        return Split(Cut.V, Leaf(row[0].zone_id), Leaf(row[1].zone_id),
                     m_to_u(round(first_w / 0.05) * 0.05))

    def in_block(row: list[ProgramRoom]) -> bool:
        return bool(open_block) and all(r.zone_id in open_block for r in row)

    def chain(start: int, stop: int) -> Node:
        """Rows start..stop (inclusive), right-nested; every cut at its row's depth."""
        if start == stop:
            return row_node(rows[start], depths[start])
        return Split(Cut.H, row_node(rows[start], depths[start]), chain(start + 1, stop),
                     m_to_u(depths[start]))

    def build(index: int) -> Node:
        if index == len(rows) - 1:
            return row_node(rows[index], depths[index])
        if in_block(rows[index]):
            stop = index
            while stop + 1 < len(rows) and in_block(rows[stop + 1]):
                stop += 1
            if stop > index:
                block = chain(index, stop)
                if stop == len(rows) - 1:
                    return block
                return Split(Cut.H, block, build(stop + 1),
                             m_to_u(round(sum(depths[index:stop + 1]) / 0.05) * 0.05))
        return Split(Cut.H, row_node(rows[index], depths[index]), build(index + 1),
                     m_to_u(depths[index]))

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
    proportions = _proportions(min_width, max_width, max_depth, gross, target_m2)
    if not proportions:
        # No proportion was ever TRIED, so no room was ever sized. Reporting a room minimum here
        # (as the single catch-all reason did) named a cause that had not been reached yet.
        return [], ConceptRejection(
            strategy, RejectionReason.FOOTPRINT_BELOW_MINIMUM_WIDTH,
            f"the programme needs a footprint at least {min_width:.2f} m wide; this candidate "
            f"offers {max_width:.2f} m")
    repartition = _repartition_for(spec, rooms, north_is_envelope=True)
    tier2_miss: PlanFailure | None = None
    found: list[tuple[Rect, LayoutPlan, bool, bool, bool]] = []   # footprint, plan, repartitioned, shrunk, over_preferred

    def budget_left(flags: tuple[bool, bool, bool]) -> bool:
        """Each class of candidate — normal, and every combination of the fallback flags — keeps
        up to `wanted` of its own. Measured with ONE shared fallback budget: three over_preferred
        plans at 268/259/250 m² (found first, refused by Geometry Core later) filled it, and the
        223/217/211 m² shrunk plans that solve were never offered; the brief got 130 m²."""
        return sum(1 for _, _, t2, sh, op in found if (t2, sh, op) == flags) < wanted

    def already_found(trial: Rect, attempt: LayoutPlan) -> bool:
        """The same rectangle in the same class, or the very same plan reached by another path —
        a fallback pass that ends up with the depths the previous one had is not a new offer."""
        return any((f.w == trial.w and f.h == trial.h and (t2, sh, op) == flags_of(attempt))
                   or pl == attempt for f, pl, t2, sh, op in found)

    def flags_of(_attempt: LayoutPlan) -> tuple[bool, bool, bool]:
        return (repartitioned, shrunk, over_preferred)

    for width, depth in proportions:
        trial = footprint_of(candidate, width, depth)
        tw, th = u_to_m(trial.w), u_to_m(trial.h)
        attempt, reason = plan_layout(rooms, west, east, hall_ids, tw, th, corridor)
        repartitioned = shrunk = over_preferred = False
        asks = _FallbackAsks.of(reason) if attempt is None else None
        if attempt is None and asks.shape:
            # Tier 2, at THIS proportion only: the normal attempt failed and a room's shape was
            # among the reasons, so the same proportion is planned with rows re-partitioned. The
            # normal diagnosis is kept; tier 2's own nearest miss is appended to it below.
            attempt, tier2_reason = plan_layout(rooms, west, east, hall_ids, tw, th, corridor,
                                                fallback=repartition)
            repartitioned = attempt is not None
            if attempt is None:
                tier2_miss = _nearest_miss(tier2_miss, tier2_reason)
                asks = asks.plus(tier2_reason)
        if attempt is None:
            # Fallbacks, at THIS proportion only and only now, and ONLY the ones that add a
            # mechanism some failure asked for (`_FallbackAsks.worth`). Inside the preferred
            # maxima first: rows shrunk toward
            # their floors (`shrunk`, `_row_depths` deficit distribution). Only if that cannot
            # plan either, rows allowed past their preferred maxima up to the hard ones
            # (`over_preferred`) — exceeding preferred is for a plan that has no other way, never
            # for a plan that fits with smaller rooms — and last both. Each also re-partitioned
            # where a shape was refused. A failed attempt widens what is asked for: a shrunk
            # attempt that dies on a preferred maximum is what makes the hard attempt worth it.
            hard_possible = _absorbable_over_preferred(rooms, tw * th)
            tried: set[tuple[bool, bool]] = set()
            for allow_deficit, allow_hard in ((True, False), (False, True), (True, True)):
                if allow_hard and not hard_possible:
                    continue
                if not asks.worth(allow_deficit, allow_hard, tried):
                    continue
                tried.add((allow_deficit, allow_hard))
                attempt, fb_reason = plan_layout(rooms, west, east, hall_ids, tw, th, corridor,
                                                 allow_deficit=allow_deficit, allow_hard=allow_hard)
                if attempt is None:
                    asks = asks.plus(fb_reason)
                if attempt is None and _shape_refused(reason):
                    attempt, fb_reason = plan_layout(rooms, west, east, hall_ids, tw, th, corridor,
                                                     fallback=repartition, allow_deficit=allow_deficit,
                                                     allow_hard=allow_hard)
                    repartitioned = attempt is not None
                    if attempt is None:
                        asks = asks.plus(fb_reason)
                if attempt is not None:
                    over_preferred, shrunk = allow_hard, allow_deficit
                    break
        if attempt is not None:
            if already_found(trial, attempt):
                continue  # `footprint_of` clamps, so distinct proportions can land on one rectangle
            # Fallback plans never count toward the NORMAL budget and never end the walk: the
            # normal candidates this strategy offers — and their order — are exactly what they
            # were. Each fallback class keeps up to `wanted` of its own (`budget_left`).
            if repartitioned or shrunk or over_preferred:
                if budget_left((repartitioned, shrunk, over_preferred)):
                    found.append((trial, attempt, repartitioned, shrunk, over_preferred))
                continue
            found.append((trial, attempt, False, False, False))
            if not budget_left((False, False, False)):
                break
        else:
            failure = _nearest_miss(failure, reason)

    if not found:
        return [], ConceptRejection(strategy, failure.reason,
                                    _with_tier2_miss(failure.detail, tier2_miss))

    built = [_concept_from(spec, rooms, candidate, strategy,
                           rationale + (REPARTITIONED_RATIONALE if repartitioned else "")
                           + (SHRUNK_RATIONALE if shrunk else "")
                           + (OVER_PREFERRED_RATIONALE if over_preferred else ""),
                           footprint, plan, repartitioned=repartitioned, shrunk=shrunk,
                           over_preferred=over_preferred)
             for footprint, plan, repartitioned, shrunk, over_preferred in found]
    # QUALITY TIER: every plan above is kept exactly as it is; beside one that leaves a
    # bedroom-class room past its preferred aspect, the same proportion re-partitioned for
    # proportions is offered as well (`_quality_layouts`), ordered last by `generate_concepts`.
    built.extend(_concept_from(spec, rooms, candidate, strategy,
                               rationale + QUALITY_RATIONALE
                               + (SHRUNK_RATIONALE if shrunk else "")
                               + (OVER_PREFERRED_RATIONALE if over_preferred else ""),
                               footprint, plan, repartitioned=True, shrunk=shrunk,
                               over_preferred=over_preferred, quality_repartitioned=True)
                 for footprint, plan, shrunk, over_preferred
                 in _quality_layouts(rooms, west, east, hall_ids, corridor, repartition, found))
    return built, None


def _quality_layouts(rooms: list[ProgramRoom], west: list[ProgramRoom], east: list[ProgramRoom],
                     hall_ids: list[str], corridor: CorridorRequirement | None,
                     repartition: Repartition,
                     found: list[tuple[Rect, LayoutPlan, bool, bool, bool]],
                     ) -> list[tuple[Rect, LayoutPlan, bool, bool]]:
    """The quality tier for the column partis: for each plan `_build` found that leaves a
    bedroom-class room past its preferred aspect, the same proportion planned again with rows
    re-partitioned for proportions — (footprint, plan, shrunk, over_preferred), at most one per
    base plan.

    BOUNDED, and nothing else moves: the base plan's own sizing tier (a shrunk base is
    re-partitioned shrunk, an over-preferred one at the hard ceilings — nothing is shrunk or
    inflated that the base was not), the normal nine seams (`plan_layout`), at most
    `_MAX_QUALITY_PAIRINGS` pairings tried best-estimated first (`Repartition.quality_rank`; a
    rank with no pairing left returns the base plan, which ends the walk), and the exact planned
    shapes must clear `_quality_accepts`. Tier-2 plans are already re-partitioned and are not
    re-partitioned again.
    """
    by_zone = {r.zone_id: r for r in rooms}
    out: list[tuple[Rect, LayoutPlan, bool, bool]] = []
    for footprint, plan, repartitioned, shrunk, over_preferred in found:
        if repartitioned:
            continue
        base = _preferred_aspects(_layout_shapes(plan), rooms)
        if _quality_shortfall(base, by_zone) <= 1e-6:
            continue
        tw, th = u_to_m(footprint.w), u_to_m(footprint.h)
        best: tuple[tuple[float, int, float], LayoutPlan] | None = None
        for rank in range(_MAX_QUALITY_PAIRINGS):
            options = replace(repartition, quality=True, quality_rank=rank, hard=over_preferred)
            attempt, _ = plan_layout(rooms, west, east, hall_ids, tw, th, corridor,
                                     fallback=options, allow_deficit=shrunk, allow_hard=over_preferred)
            if attempt is None:
                continue
            if attempt == plan:
                break   # no pairing of this rank at any seam: the base plan came back
            new = _preferred_aspects(_layout_shapes(attempt), rooms)
            if not _quality_accepts(base, new, by_zone):
                continue
            score = _quality_score(new, by_zone)
            if best is None or score < best[0]:
                best = (score, attempt)
        if best is not None and all(pl != best[1] for _, pl, *_ in found) \
                and all(pl != best[1] for _, pl, *_ in out):
            out.append((footprint, best[1], shrunk, over_preferred))
    return out


def _layout_shapes(plan: LayoutPlan) -> dict[str, tuple[float, float]]:
    """Every column room's planned NET (width, depth) — see `_row_shapes`."""
    shapes: dict[str, tuple[float, float]] = {}
    for column in (plan.west, plan.east):
        shapes.update(_row_shapes(column.rows, column.row_depths_m,
                                  column.width_m - _EDGE_INSET_ALLOWANCE_M))
    return shapes


def _front_band_shapes(plan: tuple) -> dict[str, tuple[float, float]]:
    """The rear columns' planned NET shapes of a front-band plan (`_plan_front_band_at`'s tuple);
    the band's public rooms carry no preferred aspect and are not read."""
    (_, _, west_w, _, east_w, west_depths, east_depths, _, west_rows, east_rows) = plan
    shapes = _row_shapes(west_rows, west_depths, west_w - _EDGE_INSET_ALLOWANCE_M)
    shapes.update(_row_shapes(east_rows, east_depths, east_w - _EDGE_INSET_ALLOWANCE_M))
    return shapes


#: Marker appended to a tier-2 candidate's rationale, so logs show the rows were re-partitioned.
REPARTITIONED_RATIONALE = "; rows re-partitioned (tier 2)"
#: Marker appended to a shrunk candidate's rationale, so logs show the rows gave up area.
SHRUNK_RATIONALE = "; rows shrunk toward their floors (deficit)"
#: Marker appended to a candidate planned past its rooms' preferred maxima (up to the hard ones).
OVER_PREFERRED_RATIONALE = "; rooms past their preferred maxima (hard ceiling)"


@dataclass(frozen=True)
class _FallbackAsks:
    """What the failures at one proportion have asked for, mechanism by mechanism.

    `shape` — a room's shape was refused, so re-partitioning (tier 2) may help; `deficit` — the
    rows' wants overflowed a column whose floors fit, so shrinking may help; `hard` — a preferred
    maximum blocked a room that has hard headroom, so sizing past preferred may help. A fallback
    class is skipped when what it adds was not asked for (`worth`): shrinking a column whose
    FLOORS already overflow, or inflating rooms that were never blocked by their maximum, cannot
    plan anything and used to cost a full planner attempt each, at every proportion, for every
    strategy. Every failed attempt adds what IT asked for (`plus`), so a shrunk attempt that dies
    on a preferred maximum is what earns the hard attempt after it.
    """
    shape: bool = False
    deficit: bool = False
    hard: bool = False

    @classmethod
    def of(cls, failure: PlanFailure | None) -> "_FallbackAsks":
        return cls().plus(failure)

    def plus(self, failure: PlanFailure | None) -> "_FallbackAsks":
        if failure is None:
            return self
        return _FallbackAsks(self.shape or _shape_refused(failure),
                             self.deficit or failure.deficit_fixable,
                             self.hard or failure.hard_fixable)

    def worth(self, allow_deficit: bool, allow_hard: bool,
              tried: set[tuple[bool, bool]]) -> bool:
        """Whether the fallback class `(allow_deficit, allow_hard)` can still plan something the
        attempts so far could not. A mechanism no failure asked for is INERT — shrinking only acts
        where wants overflow a column whose floors fit, hard ceilings only where a preferred one
        blocked — so the class behaves exactly like the class with those mechanisms dropped: with
        nothing left it is the normal attempt again, and with a class already `tried` (and failed)
        here it is that attempt again. Only then is it skipped."""
        effective = (allow_deficit and self.deficit, allow_hard and self.hard)
        if effective == (False, False):
            return False
        return effective == (allow_deficit, allow_hard) or effective not in tried


def _shape_refused(failure: PlanFailure | None) -> bool:
    return failure is not None and (failure.reason is RejectionReason.ROOM_SHAPE_INFEASIBLE
                                    or failure.shape_seen)


def _with_tier2_miss(detail: str, tier2_miss: PlanFailure | None) -> str:
    return detail if tier2_miss is None else f"{detail}; re-partitioned: {tier2_miss.detail}"


def _repartition_for(spec: ArchitecturalSpec, rooms: list[ProgramRoom], *,
                     north_is_envelope: bool) -> Repartition:
    """Tier-2 options for a programme: which zones are joined by OPEN connections and which one
    carries the hall's opening — the same facts `_build_access` encodes, read off the programme."""
    public_ids = [r.zone_id for r in rooms if r.group is ZoneGroup.PUBLIC]
    chain = tuple(public_ids) if spec.program.open_plan_living and len(public_ids) > 1 else ()
    return Repartition(chain, public_ids[0] if public_ids else None, north_is_envelope,
                       never_shared=frozenset(r.zone_id for r in rooms
                                              if r.role is ProgramRole.FLEX))


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
                  footprint: Rect, plan: LayoutPlan, *, repartitioned: bool = False,
                  shrunk: bool = False, over_preferred: bool = False,
                  quality_repartitioned: bool = False) -> ConceptCandidate:
    """One realized proportion -> one `ConceptCandidate`. Split out of `_build` unchanged so that
    function can offer several proportions without duplicating any of this."""
    hall_ids = ["HALL"]
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)

    specs = plan.specs
    public_ids = [r.zone_id for r in rooms if r.group is ZoneGroup.PUBLIC]
    # tier 2 may have put two open-plan zones in one row; the tree must then keep the open block
    # together (see `_forced_chain`). The normal path passes nothing and its tree is unchanged —
    # and so does the quality tier, which never pairs public rooms (`_quality_candidates`).
    open_block = (frozenset(public_ids)
                  if repartitioned and not quality_repartitioned
                  and spec.program.open_plan_living and len(public_ids) > 1
                  else frozenset())
    west_tree = _forced_chain(plan.west.rows, plan.west.row_depths_m,
                              plan.west.width_m - _EDGE_INSET_ALLOWANCE_M, open_block,
                              exterior_first=True)
    east_tree = _forced_chain(plan.east.rows, plan.east.row_depths_m,
                              plan.east.width_m - _EDGE_INSET_ALLOWANCE_M, open_block,
                              exterior_first=False)
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
        wet_rooms=wet_rooms_of(rooms),
        repartitioned=repartitioned,
        shrunk=shrunk,
        over_preferred=over_preferred,
        quality_repartitioned=quality_repartitioned,
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
                        ) -> tuple[list[ConceptCandidate], ConceptRejection | None]:
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
        return [], ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            "front band already absorbs surplus through its own elasticity; not combined with FLEX")
    if len(public) < 2 or len(private) < 3:
        return [], ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            f"{len(public)} public / {len(private)} private rooms — too few to be worth a "
            f"separate front band")

    rows = _rows_of(private)
    if len(rows) < 3:
        return [], ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
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
        return [], ConceptRejection(
            strategy, RejectionReason.FOOTPRINT_BELOW_MINIMUM_WIDTH,
            f"the programme needs a footprint at least {min_width:.2f} m wide; this candidate "
            f"offers {max_width:.2f} m")
    repartition = _repartition_for(spec, rooms, north_is_envelope=False)
    tier2_miss: PlanFailure | None = None
    tier2: tuple[Rect, tuple] | None = None
    # One fallback plan PER CLASS (shrunk / over_preferred / both), never one slot shared: an
    # over_preferred plan at an oversized proportion must not keep a smaller shrunk plan that
    # solves from being offered (see `_build`'s `budget_left`).
    fallback_plans: dict[tuple[bool, bool], tuple[Rect, tuple]] = {}
    for width, depth in proportions:
        trial = footprint_of(candidate, width, depth)
        splits = [([_orient_row(r, corridor_on_east=True)
                    for r in _daylight_order(rows[:split_at], north_is_envelope=False)],
                   [_orient_row(r, corridor_on_east=False)
                    for r in _daylight_order(rows[split_at:], north_is_envelope=False)])
                  for split_at in split_options]
        shape_refused = False
        asks = _FallbackAsks()
        for west_try, east_try in splits:
            attempt, reason = _plan_front_band(rooms, public, west_try, east_try,
                                               u_to_m(trial.w), u_to_m(trial.h))
            if attempt is not None:
                footprint, plan = trial, attempt
                break
            failure = _nearest_miss(failure, reason)
            shape_refused = shape_refused or _shape_refused(reason)
            asks = asks.plus(reason)
        if plan is None and shape_refused and tier2 is None:
            # Tier 2 at this proportion: the same splits, rows re-partitioned and the rear seam
            # searched (`Repartition`). The walk for a NORMAL plan continues regardless, so the
            # candidate this parti offered before is offered still, and the tier-2 one beside it.
            for west_try, east_try in splits:
                attempt, reason = _plan_front_band(rooms, public, west_try, east_try,
                                                   u_to_m(trial.w), u_to_m(trial.h),
                                                   fallback=repartition)
                if attempt is not None:
                    tier2 = (trial, attempt)
                    break
                tier2_miss = _nearest_miss(tier2_miss, reason)
                asks = asks.plus(reason)
        if plan is None and tier2 is None and len(fallback_plans) < 3:
            # Fallbacks at this proportion, in `_build`'s order: shrunk toward the floors (inside
            # the preferred maxima), past the preferred maxima, both — the first class that plans
            # here takes its slot if that slot is still free; the classes already served are not
            # tried again. Past the rooms' hard capacity the hard attempts are skipped
            # (`_absorbable_over_preferred`).
            hard_possible = _absorbable_over_preferred(rooms, u_to_m(trial.w) * u_to_m(trial.h))
            tried: set[tuple[bool, bool]] = set()
            for allow_deficit, allow_hard in ((True, False), (False, True), (True, True)):
                if (allow_deficit, allow_hard) in fallback_plans or (allow_hard and not hard_possible):
                    continue
                if not asks.worth(allow_deficit, allow_hard, tried):
                    continue   # no failure asked for what this class adds (`_FallbackAsks`)
                tried.add((allow_deficit, allow_hard))
                for west_try, east_try in splits:
                    attempt, fb_reason = _plan_front_band(rooms, public, west_try, east_try,
                                                          u_to_m(trial.w), u_to_m(trial.h),
                                                          allow_deficit=allow_deficit, allow_hard=allow_hard)
                    if attempt is None:
                        asks = asks.plus(fb_reason)
                    if attempt is None and shape_refused:
                        attempt, fb_reason = _plan_front_band(rooms, public, west_try, east_try,
                                                              u_to_m(trial.w), u_to_m(trial.h),
                                                              fallback=repartition, allow_deficit=allow_deficit,
                                                              allow_hard=allow_hard)
                        if attempt is None:
                            asks = asks.plus(fb_reason)
                    if attempt is not None:
                        if all(prev[1] != attempt for prev in fallback_plans.values()):
                            fallback_plans[(allow_deficit, allow_hard)] = (trial, attempt)
                        break
                if (allow_deficit, allow_hard) in fallback_plans:
                    break
        if plan is not None:
            break

    if plan is None and tier2 is None and not fallback_plans:
        return [], ConceptRejection(strategy, failure.reason,
                                    _with_tier2_miss(failure.detail, tier2_miss))
    built = []
    if plan is not None:
        built.append(_front_band_candidate(spec, rooms, candidate, public, private, footprint,
                                           plan, repartitioned=False))
    if tier2 is not None:
        built.append(_front_band_candidate(spec, rooms, candidate, public, private, tier2[0],
                                           tier2[1], repartitioned=True))
    for (shrunk, over_preferred), (fp, fallback_plan) in fallback_plans.items():
        built.append(_front_band_candidate(spec, rooms, candidate, public, private, fp,
                                           fallback_plan, repartitioned=False,
                                           shrunk=shrunk, over_preferred=over_preferred))
    # QUALITY TIER, the column partis' rule on the rear columns (`_quality_layouts`): beside a
    # plan that leaves a bedroom-class room past its preferred aspect, the same proportion with
    # its rear rows re-partitioned for proportions. Ordered last by `generate_concepts`.
    bases = ([(footprint, plan, False, False)] if plan is not None else []) + [
        (fp, fallback_plan, shrunk, over_preferred)
        for (shrunk, over_preferred), (fp, fallback_plan) in fallback_plans.items()]
    for fp, quality_plan, shrunk, over_preferred in _quality_front_bands(rooms, public, repartition, bases):
        built.append(_front_band_candidate(spec, rooms, candidate, public, private, fp,
                                           quality_plan, repartitioned=True, shrunk=shrunk,
                                           over_preferred=over_preferred, quality_repartitioned=True))
    return built, None


def _quality_front_bands(rooms: list[ProgramRoom], public: list[ProgramRoom],
                         repartition: Repartition,
                         bases: list[tuple[Rect, tuple, bool, bool]],
                         ) -> list[tuple[Rect, tuple, bool, bool]]:
    """`_quality_layouts` for the front band: each base plan's rear rows (as it planned them)
    re-partitioned for proportions at the same footprint and sizing tier, the rear seam searched
    over the normal nine positions (`_plan_front_band`), at most `_MAX_QUALITY_PAIRINGS` pairings,
    the exact planned shapes held to `_quality_accepts`."""
    by_zone = {r.zone_id: r for r in rooms}
    out: list[tuple[Rect, tuple, bool, bool]] = []
    for footprint, plan, shrunk, over_preferred in bases:
        base = _preferred_aspects(_front_band_shapes(plan), rooms)
        if _quality_shortfall(base, by_zone) <= 1e-6:
            continue
        west_rows, east_rows = plan[8], plan[9]
        fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)
        best: tuple[tuple[float, int, float], tuple] | None = None
        for rank in range(_MAX_QUALITY_PAIRINGS):
            options = replace(repartition, quality=True, quality_rank=rank, hard=over_preferred)
            attempt, _ = _plan_front_band(rooms, public, west_rows, east_rows, fw, fh,
                                          fallback=options, allow_deficit=shrunk,
                                          allow_hard=over_preferred)
            if attempt is None:
                continue
            if attempt == plan:
                break
            new = _preferred_aspects(_front_band_shapes(attempt), rooms)
            if not _quality_accepts(base, new, by_zone):
                continue
            score = _quality_score(new, by_zone)
            if best is None or score < best[0]:
                best = (score, attempt)
        if best is not None and all(b[1] != best[1] for b in bases) and all(o[1] != best[1] for o in out):
            out.append((footprint, best[1], shrunk, over_preferred))
    return out


def _front_band_candidate(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
                          public: list[ProgramRoom], private: list[ProgramRoom],
                          footprint: Rect, plan: tuple, *, repartitioned: bool,
                          shrunk: bool = False, over_preferred: bool = False,
                          quality_repartitioned: bool = False) -> ConceptCandidate:
    """One planned front band -> one `ConceptCandidate`. The rows come with the plan: a WC may
    have joined an ensuite's row, or (tier 2) any room a partner's."""
    strategy = ConceptStrategy.FRONT_PUBLIC_BAND
    (band_depth, public_widths, west_w, hall_w, east_w, west_depths, east_depths, specs,
     west_rows, east_rows) = plan
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)

    band_tree = _forced_v_chain(public, public_widths)
    rear = Split(Cut.V,
                 _forced_chain(west_rows, west_depths, west_w - _EDGE_INSET_ALLOWANCE_M,
                               exterior_first=True),
                 Split(Cut.V, Leaf("HALL"),
                       _forced_chain(east_rows, east_depths, east_w - _EDGE_INSET_ALLOWANCE_M,
                                     exterior_first=False),
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
                   f"({len(east_rows)} rows)"
                   + (QUALITY_RATIONALE if quality_repartitioned
                      else REPARTITIONED_RATIONALE if repartitioned else "")
                   + (SHRUNK_RATIONALE if shrunk else "")
                   + (OVER_PREFERRED_RATIONALE if over_preferred else "")),
        used_area_m2=round(fw * fh, 2),
        unused_wing_area_m2=round(candidate.area_m2() - fw * fh, 2),
        wet_rooms=wet_rooms_of(rooms),
        repartitioned=repartitioned,
        shrunk=shrunk,
        over_preferred=over_preferred,
        quality_repartitioned=quality_repartitioned,
    )


def _plan_front_band(rooms, public, west_rows, east_rows, fw, fh, corridor=None,
                     fallback: Repartition | None = None, allow_deficit: bool = False,
                     allow_hard: bool = False):
    """Band depth, public widths, rear column widths and row depths — all mutually consistent.

    Order matters, and it is the opposite of the obvious one. Sizing the rooms from the whole
    footprint first inflates the BEDROOMS when the footprint is generous, and inflated bedrooms
    need more rear depth than exists. So the rear is sized from the bedrooms' own programme,
    takes exactly the depth it needs, and the PUBLIC BAND absorbs whatever depth is left over —
    which is what a living room's elasticity is for.

    The rear seam is the area share of the two columns — one value, as it always was. With
    `fallback` (tier 2) it is searched over its feasible window like the spine's, nearest the
    area share first, and each column's rows may be re-partitioned at each seam.
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
    natural_w = usable * west_raw / max(west_raw + east_raw, 1e-6)
    if fallback is None:
        seams = [round(min(max(natural_w, west_min), usable - east_min) / 0.05) * 0.05]
    elif fallback.quality:
        seams = _seam_options(natural_w, west_min, usable - east_min)   # the normal nine
    else:
        seams = _seam_options(natural_w, west_min, usable - east_min, limit=None)

    failure: PlanFailure | None = None
    shape_seen = deficit_seen = hard_seen = False
    for seam_w in seams:
        east_w = round((usable - seam_w) / 0.05) * 0.05
        west_w = fw - hall_w - east_w
        plan, reason = _plan_front_band_at(rooms, public, west_rows, east_rows, fw, fh, areas,
                                           hall_w, west_w, east_w, fallback, allow_deficit,
                                           allow_hard)
        if plan is not None:
            return plan, ""
        failure = _nearest_miss(failure, reason)
        shape_seen = shape_seen or reason.reason is RejectionReason.ROOM_SHAPE_INFEASIBLE
        deficit_seen = deficit_seen or reason.deficit_fixable
        hard_seen = hard_seen or reason.hard_fixable
    return None, replace(failure, shape_seen=shape_seen, deficit_fixable=deficit_seen,
                         hard_fixable=hard_seen)


def _plan_front_band_at(rooms, public, west_rows, east_rows, fw, fh, areas, hall_w, west_w,
                        east_w, fallback: Repartition | None, allow_deficit: bool = False,
                        allow_hard: bool = False):
    """`_plan_front_band` at ONE rear seam — the unit its search repeats."""
    # How much depth the rear genuinely needs, from the bedrooms' own programme. The rows are
    # settled here for the widths just chosen: a WC that cannot be shaped across its column shares
    # an ensuite's row (`_rows_for_width`), and every later step plans the rows settled here.
    west_rows = _rows_for_width(west_rows, west_w - _EDGE_INSET_ALLOWANCE_M, fallback, True, areas)
    east_rows = _rows_for_width(east_rows, east_w - _EDGE_INSET_ALLOWANCE_M, fallback, False, areas)
    rear_need = 0.0
    rear_cap = math.inf  # the shallower column's rows at their maxima — what the rear CAN take
    for name, width, rws in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        for row in rws:
            if _row_widths(row, net_w) is None:
                return None, PlanFailure(
                    RejectionReason.ROW_WIDTH_EXCEEDED,
                    f"{' + '.join(r.zone_id for r in row)} cannot share the rear "
                    f"{name} column's {net_w:.2f} m of net width at their minimums")
        need = 0.0
        can_take = 0.0
        for row, allowance in zip(rws, _row_wall_allowances_m(rws, (False, True))):
            floor, failure = _row_depth_floor_m(row, net_w, f"rear {name} column", allowance,
                                                allow_hard)
            if failure is not None:
                return None, failure
            wanted = max(sum(areas[r.zone_id] for r in row) / max(net_w, 1e-6), floor)
            need += wanted
            can_take += _row_depth_ceiling_m(row, net_w, wanted, allow_hard)
        rear_need = max(rear_need, need)
        rear_cap = min(rear_cap, can_take)

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

    # The band's floor is each public room's shape band at the width it was just given — a 9 m
    # living room needs 3.6 m of depth for its 2.5 aspect, not the 3.0 m of its short side.
    band_min = 0.0
    for room, w in zip(public, widths + [last_w]):
        band = room_depth_band_m(room.template, w - _EDGE_INSET_ALLOWANCE_M, allow_hard)
        if band is None:
            return None, _shape_failure(room, w - _EDGE_INSET_ALLOWANCE_M, 0.0, "front band",
                                        allow_hard)
        band_min = max(band_min, band[0] + _EDGE_INSET_ALLOWANCE_M)
    # Round the rear UP: rounding to nearest could land a couple of centimetres BELOW the
    # requirement this value was just derived from, and the row planner would then reject it.
    # But never past what its rows can absorb within their maxima (`rear_cap`, itself on the
    # grid): a rear rounded up one step onto a column whose rows are all at their ceilings has
    # 5 cm no row can take, and that 5 cm belongs to the band.
    rear_depth = math.ceil(min(rear_need, fh - band_min) / 0.05 - 1e-9) * 0.05
    rear_depth = min(rear_depth, math.floor(rear_cap / 0.05 + 1e-9) * 0.05)
    band_depth = round((fh - rear_depth) / 0.05) * 0.05
    rear_depth = fh - band_depth
    if rear_depth < 1.0 or band_depth < band_min - 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"rear needs {rear_need:.2f} m and the front band at least {band_min:.2f} m, "
            f"which does not fit {fh:.2f} m of depth",
            hard_fixable=not allow_hard and _hard_headroom(rooms))   # `rear_cap` moves with hard

    # The band takes whatever depth the rear does not need, and that is where surplus area used to
    # be dumped: at 220 m2 a 2-bedroom house came out with an 81.5 m2 living room against its own
    # 46 m2 maximum. Elasticity is meant to be BOUNDED by the template maxima, so a band deeper than
    # the public rooms can absorb is not a plan to accept — reject the proportion and let the
    # footprint search fall to a smaller one, which is exactly the behaviour the multi-proportion
    # search was added for.
    # The band's width per room is already fixed above, so the depth is what decides each public
    # room's area. The BINDING room is the one that reaches its own maximum first — the living room
    # in practice, whose width is forced to span the hall.
    # GROSS, like `_row_depth_ceiling_m` and for the same reason: an open-plan band zone loses no
    # depth to its open sides, so a cap netted with the flat allowance let it realize over.
    binding = min(((r.template.ceiling_m2(allow_hard) / max(w, 1e-6), r)
                   for r, w in zip(public, widths + [last_w])), key=lambda t: t[0])
    band_cap_depth = binding[0]
    if band_depth > band_cap_depth + 1e-9:
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"a {band_depth:.2f} m front band would push {binding[1].zone_id} past its "
            f"{binding[1].template.ceiling_m2(allow_hard):.0f} m2 "
            f"{'hard ' if allow_hard else 'preferred '}maximum",
            hard_fixable=not allow_hard and _hard_headroom(rooms))   # the band or `rear_cap` moves

    depths = []
    for name, width, rws in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        d, failure = _row_depths(rws, areas, net_w, rear_depth, f"rear {name} column",
                                 ends_exterior=(False, True), allow_deficit=allow_deficit,
                                 allow_hard=allow_hard)
        if d is None:
            return None, failure
        depths.append(d)

    specs: dict[str, ZoneSpec] = {}
    net_band = band_depth - _EDGE_INSET_ALLOWANCE_M
    for room, w in zip(public, widths + [last_w]):
        failure = _shape_failure(room, w - _EDGE_INSET_ALLOWANCE_M, net_band, "front band",
                                 allow_hard)
        if failure is not None:
            return None, _after_distribution(failure, [public], allow_hard)
        specs[room.zone_id] = _zone_spec(room, w - _EDGE_INSET_ALLOWANCE_M, net_band, 0.55, 1.70,
                                         allow_hard)
    for width, rws, ds in ((west_w, west_rows, depths[0]), (east_w, east_rows, depths[1])):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(rws, ds):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths_in_row = _row_widths(row, net_w, net_d) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths_in_row):
                specs[room.zone_id] = _zone_spec(room, w, net_d, 0.55, 1.70, allow_hard)
    target_hall = (hall_w - _EDGE_INSET_ALLOWANCE_M) * (rear_depth - _EDGE_INSET_ALLOWANCE_M / 2)
    specs["HALL"] = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION),
                             target_hall * 0.5, target_hall, target_hall * 1.9,
                             ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 14.0)
    failure = _specs_within_maxima(rooms, specs, "front band", allow_hard)
    if failure is not None:
        return None, failure

    return (band_depth, widths, west_w, hall_w, east_w, depths[0], depths[1], specs,
            west_rows, east_rows), ""


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
    """Stacked rooms each need their own minimum short side plus the wall they lose. `_plan_hub_wing`
    itself floors each room by its shape band at the flank's width (`room_depth_band_m`); this
    short-side sum is the weaker, width-free floor `hub_bound` uses as a necessary condition."""
    return sum(r.template.min_short_side_m + _EDGE_INSET_ALLOWANCE_M for r in flank)


def _hub_min_width_m(alloc: HubAllocation, hub_w_m: float) -> float:
    return _flank_min_width_m(alloc.flank_west) + hub_w_m + _flank_min_width_m(alloc.flank_east)


def _hub_public_widths(alloc: HubAllocation, fw: float, west_w: float, areas: dict[str, float],
                       opening_m: float, inset: float,
                       ) -> tuple[list[float] | None, float, PlanFailure | None]:
    """The front band's zone widths for a lobby whose west flank is `west_w` wide, and the band
    depth at which the binding zone reaches its maximum area (`band_cap`).

    The first public zone must overlap the lobby by a full opening (the cased opening's shared
    edge) — not span it entirely, as the front band does for its 1.4 m corridor: spanning a 3.3 m
    lobby plus a flank left 1.9 m for the dining zone on every proportion of a 12.4 m front.
    Inside that window the band follows the zones' area shares. And it must reach past the
    footprint's centre: the entrance resolver prefers the middle of the street wall and names the
    first public zone as the room it opens into (C16), and with parking bays along the front the
    middle is often the only span clear of them (C11). A 4.45 m living zone at the west edge left
    the door at x=8.50 with the living room ending at 8.00.
    """
    others = alloc.public[1:]
    other_area = sum(areas[r.zone_id] for r in others) or 1.0
    others_min = sum(r.template.min_short_side_m + inset for r in others)
    lo_first = max(west_w + opening_m, fw / 2 + opening_m / 2)  # the door, centred, on its wall
    hi_first = fw - others_min
    wanted_first = fw * areas[alloc.public[0].zone_id] / max(areas[alloc.public[0].zone_id] + other_area, 1e-6)
    if hi_first + 1e-6 < lo_first:
        return None, 0.0, PlanFailure(
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
            return None, 0.0, PlanFailure(
                RejectionReason.BAND_WIDTH_BELOW_MINIMUM,
                f"{room.zone_id} would be {w:.2f} m wide in the front band, below its "
                f"{room.template.min_short_side_m} m minimum")
    # GROSS (see `_row_depth_ceiling_m`): a realized net area never exceeds its gross rectangle.
    band_cap = min(r.template.max_area_m2 / max(w, 1e-6) for r, w in zip(alloc.public, public_widths))
    return public_widths, band_cap, None


def _hub_plan_tail(rooms: list[ProgramRoom], alloc: HubAllocation, fw: float, fh: float,
                   hub_w: float, hub_d: float, west_w: float, east_w: float,
                   west_depths: list[float], east_depths: list[float], foot_depth: float,
                   widths: list[float], areas: dict[str, float],
                   ) -> tuple[HubPlan | None, PlanFailure | None]:
    """The public band and every ZoneSpec, given the wing's sizing — shared by v2's area-share
    sizing and the 008 witness path, so both are held to the same checks."""
    from .doors import DOOR_MARGIN_M, INTERIOR_DOOR_WIDTH_M
    opening_m = INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M
    inset = _EDGE_INSET_ALLOWANCE_M

    # Public band: takes the depth the wing leaves, floored by its own minimum and capped by the
    # room that reaches its maximum first (the same rule as `_plan_front_band`). The widths are
    # chosen below, so the floor here is the short side; the shape band is checked once they are.
    band_min = max(r.template.min_short_side_m for r in alloc.public) + inset
    band_depth = round((fh - hub_d - foot_depth) / 0.05) * 0.05
    if band_depth < band_min - 1e-9:
        return None, PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"lobby {hub_d:.2f} m + foot band {foot_depth:.2f} m leave {band_depth:.2f} m for the "
            f"public band, below its {band_min:.2f} m minimum", band_min - band_depth)
    hub_d = fh - band_depth - foot_depth  # absorb rounding into the lobby, not the band

    public_widths, band_cap, why = _hub_public_widths(alloc, fw, west_w, areas, opening_m, inset)
    if public_widths is None:
        return None, why
    if band_depth > band_cap + 1e-9:
        binding = min(((r.template.max_area_m2 / max(w - inset, 1e-6), r)
                       for r, w in zip(alloc.public, public_widths)), key=lambda t: t[0])[1]
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"a {band_depth:.2f} m front band would push {binding.zone_id} past its "
            f"{binding.template.max_area_m2:.0f} m2 maximum")

    specs: dict[str, ZoneSpec] = {}
    net_band = band_depth - inset
    for room, w in zip(alloc.public, public_widths):
        failure = _shape_failure(room, w - inset, net_band, "front band")
        if failure is not None:
            return None, failure
        specs[room.zone_id] = _zone_spec(room, w - inset, net_band, 0.55, 1.70)
    for flank, w, depths in ((alloc.flank_west, west_w, west_depths),
                             (alloc.flank_east, east_w, east_depths)):
        for room, d in zip(flank, depths):
            specs[room.zone_id] = _zone_spec(room, w - inset, d - inset / 2, 0.55, 1.70)
    for room, w in zip(alloc.foot, widths):
        specs[room.zone_id] = _zone_spec(room, w - inset, foot_depth - inset / 2, 0.55, 1.70)
    hub_target = (hub_w - inset) * (hub_d - inset / 2)
    specs[alloc.hub.zone_id] = ZoneSpec(
        alloc.hub.zone_id, (ProgramRole.HALL, ProgramRole.CIRCULATION),
        hub_target * 0.5, hub_target, hub_target * 1.9, HUB_TEMPLATE.min_short_side_m,
        HUB_TEMPLATE.max_aspect_ratio)
    failure = _specs_within_maxima(rooms, specs, "private wing")
    if failure is not None:
        return None, failure

    doors = (len(alloc.flank_west) + len(alloc.flank_east)
             + sum(1 for r in alloc.foot if not r.entered_from))
    return HubPlan(band_depth, public_widths, west_w, hub_w, east_w, hub_d,
                   west_depths, east_depths, foot_depth, widths, specs, doors), None


def _plan_hub_wing_from_witness(rooms: list[ProgramRoom], alloc: HubAllocation, fw: float,
                                fh: float, hub_w: float, witness: HubSizing,
                                areas: dict[str, float]) -> tuple[HubPlan | None, PlanFailure | None]:
    """The wing sized exactly as `hub_bound` found it; the same minimum checks v2 applies."""
    inset = _EDGE_INSET_ALLOWANCE_M
    if abs(witness.hub_w_m - hub_w) > 1e-9:
        return None, PlanFailure(RejectionReason.COLUMN_WIDTH_EXCEEDED,
                                 f"witness lobby width {witness.hub_w_m:.2f} m is not {hub_w:.2f} m")
    hub_d = witness.hub_d_m
    west_w, east_w = witness.west_w_m, fw - hub_w - witness.west_w_m
    west_depths, east_depths = list(witness.west_depths_m), list(witness.east_depths_m)
    widths, foot_depth = list(witness.foot_widths_m), witness.foot_depth_m
    for flank, w, depths in ((alloc.flank_west, west_w, west_depths), (alloc.flank_east, east_w, east_depths)):
        if len(depths) != len(flank) or abs(sum(depths) - hub_d) > 1e-6:
            return None, PlanFailure(RejectionReason.COLUMN_DEPTH_EXCEEDED,
                                     "witness flank depths do not tile the lobby band")
        for room, d in zip(flank, depths):
            if w - inset + 1e-6 < room.template.min_short_side_m or d - inset + 1e-6 < room.template.min_short_side_m:
                return None, PlanFailure(RejectionReason.ROW_WIDTH_EXCEEDED,
                                         f"witness leaves {room.zone_id} below its minimum ({w:.2f} x {d:.2f})")
    if len(widths) != len(alloc.foot) or abs(sum(widths) - fw) > 1e-6:
        return None, PlanFailure(RejectionReason.ROW_WIDTH_EXCEEDED, "witness foot widths do not span the front")
    for room, w in zip(alloc.foot, widths):
        if w - inset + 1e-6 < room.template.min_short_side_m or foot_depth - inset + 1e-6 < room.template.min_short_side_m:
            return None, PlanFailure(RejectionReason.ROW_WIDTH_EXCEEDED,
                                     f"witness leaves {room.zone_id} below its minimum in the foot band")
    return _hub_plan_tail(rooms, alloc, fw, fh, hub_w, hub_d, west_w, east_w, west_depths, east_depths,
                          foot_depth, widths, areas)


def _plan_hub_wing(rooms: list[ProgramRoom], alloc: HubAllocation, fw: float, fh: float,
                   hub_w: float, witness: HubSizing | None = None,
                   ) -> tuple[HubPlan | None, PlanFailure | None]:
    """Band depth, lobby rectangle, flank and foot widths, foot depth and every ZoneSpec — mutually
    consistent, in the same order of decisions `_plan_front_band` takes: the rear (here the lobby
    band and the foot band) is sized from the rooms' own programme and the public band absorbs
    what is left, capped by the binding public room's maximum."""
    from .doors import DOOR_MARGIN_M, INTERIOR_DOOR_WIDTH_M
    opening_m = INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M
    inset = _EDGE_INSET_ALLOWANCE_M

    modest = scale_program(rooms, sum(r.template.target_area_m2 for r in rooms))
    areas = {z: spec.net_area_target_m2 for z, spec in modest.items()}

    # 008 follow-up: an ELIGIBLE hub takes the sizing its bound found to pass the gates — the
    # witness — instead of the area shares below; every check the band applies still applies, and
    # a witness that fails one is reported, never adjusted. Last-resort hubs keep v2's sizing.
    if witness is not None:
        return _plan_hub_wing_from_witness(rooms, alloc, fw, fh, hub_w, witness, areas)

    # Lobby depth: deep enough for the deeper flank (stacked rooms add up) and for itself, inside
    # its own aspect band.
    flanks = [alloc.flank_west, alloc.flank_east]
    mins = [_flank_min_width_m(f) for f in flanks]

    def flank_floors_m(flank: list[ProgramRoom], width: float,
                       ) -> tuple[list[float] | None, PlanFailure | None]:
        """Each stacked room's CENTERLINE depth floor at the flank width `width` — its shape band's
        lower end (`room_depth_band_m`), not its short side alone — or the room that has no band."""
        out = []
        for room in flank:
            band = room_depth_band_m(room.template, width - inset)
            if band is None:
                return None, _shape_failure(room, width - inset, 0.0, "lobby flank")
            out.append(band[0] + _depth_allowance_m(room))
        return out, None

    def lobby_depth(flank_needs: list[float], flank_caps: list[float] = (),
                    ) -> tuple[float | None, PlanFailure | None]:
        floors = flank_needs + [
            HUB_TEMPLATE.min_short_side_m + inset,
            areas[alloc.hub.zone_id] / max(hub_w - inset, 1e-6) + inset / 2]
        d = round(max(floors) / 0.05) * 0.05
        d = max(d, round(hub_w / HUB_TEMPLATE.max_aspect_ratio / 0.05) * 0.05)
        # A flank's rooms are as deep as the lobby together, so the lobby may not be deeper than
        # the shallower flank can absorb within its rooms' maxima — the same rule as a column's.
        # Rounding the lobby up one grid step past that left 5 cm no flank room could take.
        if flank_caps and d > min(flank_caps) + 1e-9:
            d = math.floor(min(flank_caps) / 0.05 + 1e-9) * 0.05
            if d < max(floors) - 1e-9:
                return None, PlanFailure(
                    RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
                    f"the flanks need a {max(floors):.2f} m lobby but can absorb only "
                    f"{min(flank_caps):.2f} m within their rooms' maximum areas",
                    max(floors) - min(flank_caps))
        if d > hub_w * HUB_TEMPLATE.max_aspect_ratio + 1e-9:
            return None, PlanFailure(
                RejectionReason.COLUMN_DEPTH_EXCEEDED,
                f"a {hub_w:.2f} m lobby would need {d:.2f} m of depth for its flanks, past its "
                f"{HUB_TEMPLATE.max_aspect_ratio} aspect", d - hub_w * HUB_TEMPLATE.max_aspect_ratio)
        if (hub_w - inset) * (d - inset / 2) > HUB_TEMPLATE.max_area_m2 + 1e-9:
            return None, PlanFailure(
                RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
                f"a {hub_w:.2f} x {d:.2f} m lobby exceeds its {HUB_TEMPLATE.max_area_m2:.0f} m2 maximum")
        return d, None

    # First pass at the flanks' own minimum widths — the narrowest they can be, so the shallowest
    # they can be. The widths chosen below can only widen them, and a wider flank may need a
    # deeper lobby; that is the second pass.
    first_floors = []
    for flank, width in zip(flanks, mins):
        floors, failure = flank_floors_m(flank, width)
        if failure is not None:
            return None, failure
        first_floors.append(floors)
    def flank_caps_m(flank_floors: list[list[float]], widths: list[float]) -> list[float]:
        return [sum(_row_depth_ceiling_m([r], width - inset, d) for r, d in zip(flank, floors))
                for flank, floors, width in zip(flanks, flank_floors, widths)]

    hub_d, failure = lobby_depth([sum(f) for f in first_floors], flank_caps_m(first_floors, mins))
    if hub_d is None:
        return None, failure

    # Depths within a stacked flank: each room its floor, the surplus by expansion priority and
    # BOUNDED by each room's maximum — the column rule (`_distribute_column_surplus`), so a flank
    # that cannot absorb the lobby's depth within its rooms' maxima fails the candidate here
    # rather than handing a bedroom 20 m2. (It used to be area share with no ceiling.)
    def stacked(flank: list[ProgramRoom], mins_d: list[float], width: float,
                ) -> tuple[list[float] | None, PlanFailure | None]:
        return _distribute_column_surplus([[r] for r in flank], mins_d, width - inset, hub_d,
                                          "lobby flank")
    west_depths, failure = stacked(flanks[0], first_floors[0], mins[0])
    if west_depths is None:
        return None, failure
    east_depths, failure = stacked(flanks[1], first_floors[1], mins[1])
    if east_depths is None:
        return None, failure

    # Flank widths: minimums first, surplus by area — the `_row_widths` rule across the lobby band;
    # a stacked flank is as wide as its widest member wants.
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
    west_w = max(round(share[0] / 0.05) * 0.05, math.ceil(mins[0] / 0.05 - 1e-9) * 0.05)
    east_w = fw - hub_w - west_w

    # Second pass at the widths actually chosen: a bathroom under a 5 m bedroom flank needs 1.7 m
    # of depth for its aspect, not its 1.6 m short side, and the lobby must be that deep. The
    # widths stay; only the depths follow.
    final_floors = []
    for flank, width in zip(flanks, (west_w, east_w)):
        floors, failure = flank_floors_m(flank, width)
        if failure is not None:
            return None, failure
        final_floors.append(floors)
    needed = max(sum(f) for f in final_floors)
    final_caps = flank_caps_m(final_floors, [west_w, east_w])
    if needed > hub_d + 1e-9 or hub_d > min(final_caps) + 1e-9:
        hub_d, failure = lobby_depth([sum(f) for f in final_floors], final_caps)
        if hub_d is None:
            return None, failure
    west_depths, failure = stacked(flanks[0], final_floors[0], west_w)
    if west_depths is None:
        return None, failure
    east_depths, failure = stacked(flanks[1], final_floors[1], east_w)
    if east_depths is None:
        return None, failure
    for flank, width, depths in zip(flanks, (west_w, east_w), (west_depths, east_depths)):
        for room, d in zip(flank, depths):
            failure = _shape_failure(room, width - inset, d - inset / 2, "lobby flank")
            if failure is not None:
                return None, failure

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
    # The boundary must also leave each side its rooms' minimum widths (a bedroom plus its
    # ensuite side by side); the window is narrowed to that before the area share is applied,
    # so a lobby 5 cm further west does not fail the pair by 5 cm.
    need_west = sum(r.template.min_short_side_m + inset for r in west_group)
    need_east = sum(r.template.min_short_side_m + inset for r in east_group)
    lo, hi = max(lo, need_west), min(hi, fw - need_east)
    if hi + 1e-6 < lo:
        return None, PlanFailure(
            RejectionReason.ROW_WIDTH_EXCEEDED,
            f"the foot band's two sides need {need_west:.2f} + {need_east:.2f} m but their "
            f"boundary can only sit in a window that leaves less", lo - hi)
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
    foot_floor = 0.0
    for room, w in zip(alloc.foot, widths):
        band = room_depth_band_m(room.template, w - inset)
        if band is None:
            return None, _shape_failure(room, w - inset, 0.0, "foot band")
        foot_floor = max(foot_floor, band[0] + _depth_allowance_m(room))
    foot_depth = max(foot_floor,
                     max(areas[r.zone_id] / max(w - inset, 1e-6) for r, w in zip(alloc.foot, widths))
                     + inset / 2)
    foot_depth = round(foot_depth / 0.05) * 0.05
    # One depth for the whole foot band, so the member that reaches its maximum first caps it —
    # the hungriest member's want no longer stretches a safe room past 14 m2.
    foot_cap = min(_row_depth_ceiling_m([r], w - inset, foot_depth) for r, w in zip(alloc.foot, widths))
    if foot_cap < foot_floor - 1e-9:
        binding = min(alloc.foot, key=lambda r: r.template.max_area_m2)
        return None, PlanFailure(
            RejectionReason.ROOM_ABOVE_MAXIMUM_AREA,
            f"the foot band needs {foot_floor:.2f} m of depth but {binding.zone_id} reaches its "
            f"{binding.template.max_area_m2:.0f} m2 maximum at {foot_cap:.2f} m", foot_floor - foot_cap)
    foot_depth = min(foot_depth, foot_cap)
    for room, w in zip(alloc.foot, widths):
        failure = _shape_failure(room, w - inset, foot_depth - inset / 2, "foot band")
        if failure is not None:
            return None, failure

    return _hub_plan_tail(rooms, alloc, fw, fh, hub_w, hub_d, west_w, east_w, west_depths, east_depths,
                          foot_depth, widths, areas)


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
    widths = _hub_widths(spec, rooms)
    if widths is None:
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            f"a {corridor.width_m:.2f} m corridor request is outside what a room lobby can be "
            f"({min(_HUB_WIDTHS_M):.1f}-{max(_HUB_WIDTHS_M):.1f} m)")

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
        wet_rooms=wet_rooms_of(rooms),
    )


# --------------------------------------------------------------------------- hub eligibility (008)

@dataclass(frozen=True)
class HubGates:
    """The §6 acceptance numbers a hub plan is held to — referenced, never re-derived."""
    bedroom_aspect: float
    master_aspect: float
    wet_adjacency: float


HUB_GATES = HubGates(bedroom_aspect=1.35, master_aspect=1.40, wet_adjacency=0.80)


@dataclass(frozen=True)
class HubSizing:
    """A sizing of the v2 hub tree that the bound found to pass the gates — the witness. Gross
    metres on the 0.05 m grid, in the terms `_plan_hub_wing` plans in."""
    hub_w_m: float
    hub_d_m: float
    west_w_m: float
    west_depths_m: tuple[float, ...]
    east_depths_m: tuple[float, ...]
    foot_widths_m: tuple[float, ...]
    foot_depth_m: float


@dataclass(frozen=True)
class HubBound:
    """The best the v2 hub tree can do on one outline for one programme, under the access and
    wet-adjacency rules — specs/008 data-model.md. `gated_*` are None when no sizing reaches the
    wet gate at all (the 3-wet case)."""
    fw_m: float
    fh_m: float
    hub_widths_m: tuple[float, ...]
    required_doors: int
    seated_doors: int
    best_wet_adjacency: float
    gated_bedroom_aspect: float | None
    gated_master_aspect: float | None
    gated_safe_aspect: float | None
    evaluated: int
    #: the sizing that passed the gates, when one did (ELIGIBLE); None otherwise
    witness: HubSizing | None = None

    def describe(self) -> str:
        if self.gated_bedroom_aspect is None:
            return (f"wet adjacency reaches {100 * self.best_wet_adjacency:.0f}% at best "
                    f"(gate {100 * HUB_GATES.wet_adjacency:.0f}%)")
        return (f"best reachable bedroom-class aspect {self.gated_bedroom_aspect:.2f} "
                f"(gate {HUB_GATES.bedroom_aspect}), master {self.gated_master_aspect:.2f} "
                f"(gate {HUB_GATES.master_aspect}), wet {100 * self.best_wet_adjacency:.0f}%")


class HubEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    LAST_RESORT = "LAST_RESORT"


def hub_eligibility(bound: HubBound) -> HubEligibility:
    if (bound.gated_bedroom_aspect is not None
            and bound.gated_bedroom_aspect <= HUB_GATES.bedroom_aspect + 1e-9
            and bound.gated_master_aspect is not None
            and bound.gated_master_aspect <= HUB_GATES.master_aspect + 1e-9):
        return HubEligibility.ELIGIBLE
    return HubEligibility.LAST_RESORT


def _hub_widths(spec: ArchitecturalSpec, rooms: list[ProgramRoom]) -> tuple[float, ...] | None:
    """The lobby widths `_hub_concept` tries: the census set, or the one a corridor request pins;
    None when the request is outside what a lobby can be (the hub is declined)."""
    corridor = spec.program.corridor
    if corridor is None:
        return _HUB_WIDTHS_M
    wanted = _hall_width_m(corridor, HUB_TEMPLATE.target_area_m2 ** 0.5, cap_m=max(_HUB_WIDTHS_M),
                           has_safe_room=any(r.role is ProgramRole.SAFE_ROOM for r in rooms))
    if wanted > max(_HUB_WIDTHS_M) + 1e-9 or wanted < min(_HUB_WIDTHS_M) - 1e-9:
        return None
    return (round(wanted / 0.05) * 0.05,)


_RectM = tuple[float, float, float, float]  # x, y, w, h — gross metres


def _shared_edge_m(a: _RectM, b: _RectM) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if abs(ax + aw - bx) < 1e-6 or abs(bx + bw - ax) < 1e-6:
        return max(0.0, min(ay + ah, by + bh) - max(ay, by))
    if abs(ay + ah - by) < 1e-6 or abs(by + bh - ay) < 1e-6:
        return max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    return 0.0


def _bound_grid(lo: float, hi: float, step: float) -> list[float]:
    """`lo` itself (a room's exact minimum), then the grid points above it, up to `hi`."""
    if lo > hi + 1e-9:
        return []
    out = [round(lo, 2)]
    x = math.floor(lo / step + 1e-9) * step + step
    while x <= hi + 1e-9:
        out.append(round(x, 2))
        x += step
    return out


def hub_bound(rooms: list[ProgramRoom], fw: float, fh: float, widths: tuple[float, ...],
              grid: float = 0.25) -> HubBound:
    """Phase 0's bound, on the engine's own allocation: for each lobby width, the tree
    `_hub_allocation` would build is sized over a grid — lobby depth, flank split, stack splits,
    foot boundary, ensuite share, foot depth — and checked as rectangles for door seats (>= 1.10 m
    of shared edge with the lobby), the ensuite beside its master, and M5 wet adjacency (a wet room
    touching a wet room; the kitchen is ignored, conservatively). Returns the best bedroom-class
    aspect among sizings that seat every door AND reach the wet gate, exiting early once one passes
    the §6 gates. Nothing here chooses a sizing: `_plan_hub_wing` is untouched and its own sizing is
    a point in this space, so the bound is never stricter than the engine on feasibility — only on
    quality (specs/008 research R1–R5).

    Cost: the flank and foot parts only meet through the lobby's position and depth, so each is
    tabulated once and combined — a few thousand cheap evaluations per lobby width.
    """
    from .doors import DOOR_MARGIN_M, INTERIOR_DOOR_WIDTH_M
    opening = INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M
    inset = _EDGE_INSET_ALLOWANCE_M

    def net_aspect(w: float, d: float) -> float:
        w, d = w - inset, d - inset
        return max(w, d) / max(min(w, d), 1e-6)

    best_wet = 0.0
    gated: tuple[float, float, float] | None = None   # (bedroom-class max, master, safe)
    required = seated_max = evaluated = 0
    modest = scale_program(rooms, sum(r.template.target_area_m2 for r in rooms))
    areas = {z: spec.net_area_target_m2 for z, spec in modest.items()}

    for hw in widths:
        alloc, _ = _hub_allocation(rooms, hw)
        if alloc is None:
            continue
        flanks = [alloc.flank_west, alloc.flank_east]
        doored = [r for r in alloc.foot if not r.entered_from]
        needs_door = [r for f in flanks for r in f] + doored
        required = max(required, len(needs_door))
        band_min = max(r.template.min_short_side_m for r in alloc.public) + inset
        hub_floor = max([_flank_min_depth_m(f) for f in flanks]
                        + [HUB_TEMPLATE.min_short_side_m + inset,
                           HUB_TEMPLATE.target_area_m2 / max(hw - inset, 1e-6) + inset / 2,
                           hw / HUB_TEMPLATE.max_aspect_ratio])
        hub_floor = math.ceil(hub_floor / 0.05 - 1e-9) * 0.05   # on the engine's cut grid (witness)
        hub_cap = min(hw * HUB_TEMPLATE.max_aspect_ratio,
                      HUB_TEMPLATE.max_area_m2 / max(hw - inset, 1e-6) + inset / 2)
        mins_w = [_flank_min_width_m(f) for f in flanks]
        foot_floor = max(r.template.min_short_side_m + inset for r in alloc.foot)
        master = next((r for r in alloc.foot if r.role is ProgramRole.MASTER_BEDROOM), None)
        safe = next((r for r in rooms if r.role is ProgramRole.SAFE_ROOM), None)
        mate = next((r for r in alloc.foot if r.entered_from), None)
        private_ids = {r.zone_id for r in rooms if r.group is ZoneGroup.PRIVATE}

        # --- structural facts, once per allocation on a representative sizing: door seats and
        # wet adjacency depend on which room is where, not on the grid (every flank room borders
        # the lobby over its own depth; the foot boundary window guarantees the two doored rooms
        # an opening; a wet room under a flank shares its column's bottom edge with the foot).
        def rectangles(hd: float, w: float, west_d: list[float], east_d: list[float],
                       fws: list[float], fd: float) -> dict[str, _RectM]:
            band = fh - hd - fd
            rects: dict[str, _RectM] = {}
            y = band
            for room, d in zip(alloc.flank_west, west_d):
                rects[room.zone_id] = (0.0, y, w, d); y += d
            rects[alloc.hub.zone_id] = (w, band, hw, hd)
            y = band
            for room, d in zip(alloc.flank_east, east_d):
                rects[room.zone_id] = (w + hw, y, fw - hw - w, d); y += d
            x = 0.0
            for room, fw_ in zip(alloc.foot, fws):
                rects[room.zone_id] = (x, band + hd, fw_, fd); x += fw_
            return rects

        def foot_widths(centre: float, ens_w: float) -> list[float] | None:
            out: list[float] = []
            for i, room in enumerate(alloc.foot):
                if room.entered_from:
                    continue
                side_w = centre if room is doored[0] else fw - centre
                m = next((e for e in alloc.foot if e.entered_from == room.zone_id), None)
                if m is None:
                    out.append(side_w)
                    continue
                if ens_w + room.template.min_short_side_m + inset > side_w + 1e-9:
                    return None
                out += [ens_w, side_w - ens_w] if alloc.foot.index(m) < i else [side_w - ens_w, ens_w]
            for room, w_ in zip(alloc.foot, out):
                if w_ < room.template.min_short_side_m + inset - 1e-9:
                    return None
            return out

        # --- foot table: per boundary and ensuite share, the foot's worst private aspect at every
        # depth on the grid, folded into prefix minima so a lobby depth (which caps the foot's depth)
        # reads its best foot in one lookup.
        ens_min = mate.template.min_short_side_m + inset if mate is not None else 0.0
        fds_all = _bound_grid(foot_floor, fh - hub_floor - band_min, grid)
        foot_table: list[tuple[float, list[tuple[float, float, float, float]], list[float]]] = []  # centre, per-fd (worst, master, safe, fd), widths
        for centre in _bound_grid(mins_w[0] + opening, fw - hw - mins_w[1] + hw - opening, grid):
            ens_opts = [ens_min]
            if mate is not None:
                side = centre if alloc.foot.index(mate) < alloc.foot.index(doored[1]) else fw - centre
                room_min = next(r for r in alloc.foot if r.zone_id == mate.entered_from).template.min_short_side_m + inset
                ens_opts = _bound_grid(ens_min, side - room_min, grid) or [ens_min]
            for ens_w in ens_opts:
                fws = foot_widths(centre, ens_w)
                if fws is None:
                    continue
                priv = [(r, w_) for r, w_ in zip(alloc.foot, fws) if r.zone_id in private_ids]
                per_fd: list[tuple[float, float, float, float]] = []
                for fd in fds_all:
                    evaluated += 1
                    # A foot depth that puts any foot room past its maximum (GROSS, see
                    # `_row_depth_ceiling_m`) is no sizing at all: it can never pass the gate.
                    if any(_largest_net_area_m2(r, w_, fd) > r.template.max_area_m2 + _AREA_TOL_M2
                           for r, w_ in zip(alloc.foot, fws)):
                        per_fd.append((math.inf, math.inf, math.inf, fd))
                        continue
                    worst = max((net_aspect(w_, fd) for _, w_ in priv), default=1.0)
                    m_asp = next((net_aspect(w_, fd) for r, w_ in priv if r is master), worst)
                    s_asp = next((net_aspect(w_, fd) for r, w_ in priv if r is safe), 0.0)
                    per_fd.append((worst, m_asp, s_asp, fd))
                foot_table.append((centre, per_fd, fws))
        if not foot_table:
            continue

        checked_structure = False
        for hd in _bound_grid(hub_floor, hub_cap, grid):
            fd_hi = fh - hd - band_min
            if fd_hi < foot_floor - 1e-9:
                continue

            def splits(flank: list[ProgramRoom]) -> list[list[float]]:
                if len(flank) == 1:
                    return [[hd]]
                top_min = flank[0].template.min_short_side_m + inset
                bot_min = flank[1].template.min_short_side_m + inset
                return [[d1, hd - d1] for d1 in _bound_grid(top_min, hd - bot_min, grid)]
            west_splits, east_splits = splits(alloc.flank_west), splits(alloc.flank_east)

            for w in _bound_grid(mins_w[0], fw - hw - mins_w[1], grid):
                e = fw - hw - w
                # the front band must be able to seat its zones beside this lobby position, and
                # its depth may not push the binding zone past its maximum — the engine's checks
                public, band_cap, _ = _hub_public_widths(alloc, fw, w, areas, opening, inset)
                if public is None:
                    continue
                fd_lo = max(foot_floor, fh - hd - band_cap)
                # best flank split for this (hd, w): the private rooms' worst aspect
                flank_best: tuple[float, list[float], list[float], float] | None = None
                for wd in west_splits:
                    for ed in east_splits:
                        evaluated += 1
                        # Same rule for the flanks: a split that puts a room past its maximum is
                        # skipped, so the witness the bound returns is inside every maximum.
                        if (any(_largest_net_area_m2(r, w, d) > r.template.max_area_m2 + _AREA_TOL_M2
                                for r, d in zip(alloc.flank_west, wd))
                                or any(_largest_net_area_m2(r, e, d) > r.template.max_area_m2 + _AREA_TOL_M2
                                       for r, d in zip(alloc.flank_east, ed))):
                            continue
                        worst = max([net_aspect(w, d) for r, d in zip(alloc.flank_west, wd) if r.zone_id in private_ids]
                                    + [net_aspect(e, d) for r, d in zip(alloc.flank_east, ed) if r.zone_id in private_ids]
                                    or [1.0])
                        s_asp = max([net_aspect(w, d) for r, d in zip(alloc.flank_west, wd) if r is safe]
                                    + [net_aspect(e, d) for r, d in zip(alloc.flank_east, ed) if r is safe] or [0.0])
                        if flank_best is None or worst < flank_best[0] - 1e-9:
                            flank_best = (worst, wd, ed, s_asp)
                if flank_best is None:
                    continue
                lo, hi = w + opening, w + hw - opening
                i_lo = bisect.bisect_left(fds_all, fd_lo - 1e-9)
                i_hi = bisect.bisect_right(fds_all, fd_hi + 1e-9)
                if i_hi <= i_lo:
                    continue
                for centre, per_fd, fws in foot_table:
                    if centre < lo - 1e-9 or centre > hi + 1e-9:
                        continue
                    f_worst, m_asp, s_asp_foot, fd_best = min(per_fd[i_lo:i_hi], key=lambda t: t[0])
                    if not checked_structure:
                        rects = rectangles(hd, w, flank_best[1], flank_best[2], fws, fds_all[0])
                        hub_rect = rects[alloc.hub.zone_id]
                        seated = sum(1 for r in needs_door
                                     if _shared_edge_m(rects[r.zone_id], hub_rect) >= opening - 1e-6)
                        seated_max = max(seated_max, seated)
                        ens_ok = mate is None or _shared_edge_m(
                            rects[mate.zone_id], rects[mate.entered_from]) >= opening - 1e-6
                        # M5 wet adjacency: SERVICE rooms are exactly the plumbed ones — the gate
                        # applied to whichever of them the programme has (BATHROOM/TOILET before
                        # 2026-09-16; now also a requested LAUNDRY, docs/LAUNDRY_ROOM_PHASE1_REPORT.md)
                        # with no role named here. Unlike `_ROW_RESCUE_ROLES` above, this is NOT
                        # narrowed to specific roles: with the laundry gate off, `ZoneGroup.SERVICE`
                        # is populated by exactly BATHROOM/TOILET (build_room_program's only other
                        # source), so this form is identical to the old 2-role tuple for every
                        # existing brief BY CONSTRUCTION, not by measurement — there is nothing here
                        # for a sweep to have found.
                        wets = [r for r in rooms if r.group is ZoneGroup.SERVICE and r.zone_id in rects]
                        adj = sum(1 for r in wets if any(
                            _shared_edge_m(rects[r.zone_id], rects[o.zone_id]) > 0.3 for o in wets if o is not r))
                        wet = adj / len(wets) if wets else 1.0
                        best_wet = max(best_wet, wet)
                        checked_structure = True
                        structure_ok = seated == len(needs_door) and ens_ok and wet >= HUB_GATES.wet_adjacency - 1e-9
                    if not structure_ok:
                        break
                    worst = max(flank_best[0], f_worst)
                    s_asp = max(flank_best[3], s_asp_foot)
                    if gated is None or worst < gated[0] - 1e-9:
                        gated = (worst, m_asp, s_asp)
                    if worst <= HUB_GATES.bedroom_aspect + 1e-9 and m_asp <= HUB_GATES.master_aspect + 1e-9:
                        witness = HubSizing(hw, hd, w, tuple(flank_best[1]), tuple(flank_best[2]),
                                            tuple(fws), fd_best)
                        return HubBound(fw, fh, tuple(widths), len(needs_door), len(needs_door),
                                        best_wet, worst, m_asp, s_asp, evaluated, witness)
                if checked_structure and not structure_ok:
                    break
            if checked_structure and not structure_ok:
                break
    return HubBound(fw, fh, tuple(widths), required, seated_max, best_wet,
                    gated[0] if gated else None, gated[1] if gated else None,
                    gated[2] if gated else None, evaluated)


def _hub_from_witness(spec: ArchitecturalSpec, hub_rooms: list[ProgramRoom], hub: ConceptCandidate,
                      bound: HubBound, note: str) -> tuple[ConceptCandidate, str]:
    """The eligible hub candidate rebuilt with its bound's witness sizing (same footprint, same
    tree, same access); on any failure the v2 candidate is returned with the reason in the note."""
    witness = bound.witness
    assert witness is not None
    alloc, rej = _hub_allocation(hub_rooms, witness.hub_w_m)
    if alloc is None:
        return hub, f"{note}; witness not planned: {rej.detail if rej else 'no allocation'}"
    fw, fh = hub.concept.footprint_width_m, hub.concept.footprint_depth_m
    plan, why = _plan_hub_wing(hub_rooms, alloc, fw, fh, witness.hub_w_m, witness=witness)
    if plan is None:
        return hub, f"{note}; witness not planned: {why.detail if why else '?'}"
    wing = hub.concept.fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    rebuilt = _hub_candidate(spec, hub_rooms, footprint, footprint, alloc, plan)
    rebuilt = replace(rebuilt, unused_wing_area_m2=hub.unused_wing_area_m2,
                      rationale=f"{rebuilt.rationale} (sized by its bound's witness)")
    return rebuilt, note


def _two_wing_pair(candidates: list[SolverGeometryCandidate],
                   ) -> tuple[SolverGeometryCandidate, SolverGeometryCandidate] | ConceptRejection | None:
    """The two adjacent safe wings the L parti may plan across, the reason there are none, or
    None when the adapter offered one wing.

    This used to be `_multi_wing_assessment`, which declined EVERY second wing: where the seam
    covered only part of the primary's side it concluded a hall against it would be part
    exterior and part seam (the spike's L2 finding) and refused. L2's own resolution — a forced
    cut so the hall spans exactly the seam and a room takes the rest of the depth — is what the
    spike's F2 fixture did and what `l_parti` now authors, so the partial-seam case is planned
    rather than refused. A wing that shares no boundary is still declined here with its reason.
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
    return primary, secondary


# --------------------------------------------------------------------------- 7. entry point

def generate_concepts(spec: ArchitecturalSpec,
                      candidates: list[SolverGeometryCandidate]) -> GenerationResult:
    """A small, bounded, deterministic set of plausible concepts, best first."""
    variants = programme_variants(spec)
    rooms = variants[0]                     # the literal reading of the brief, for the diagnostics
    constraint = spec.safe_room_constraint
    # Issue #35, stage assertion 1/3: the room PROGRAMME this concept stage is about to build
    # candidates from must still carry an authoritative constraint's room. `build_room_program`
    # (via `programme_variants`) is the only place that adds SAFE_ROOM to `rooms`, so this also
    # protects every later variant (`programme_variants` only ever rearranges wet rooms, never
    # drops SAFE_ROOM) and every return below, which all derive from `rooms`/`variants`.
    assert_realized(constraint, any(r.role is ProgramRole.SAFE_ROOM for r in rooms),
                    stage="concept_generation", detail=SAFE_ROOM_NOT_REALIZED_DETAIL)
    accepted: list[ConceptCandidate] = []
    rejections: list[ConceptRejection] = []
    last_resort: set[int] = set()   # ids of hub candidates demoted by their outline's bound (008)

    if not candidates:
        return GenerationResult((), (ConceptRejection(
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, RejectionReason.INSUFFICIENT_TOTAL_AREA,
            "no safe solver geometry available"),), tuple(rooms), (constraint,))

    needed = target_gross_area_m2(rooms)
    usable = [c for c in candidates if c.area_m2 >= needed * 0.55]
    if not usable:
        return GenerationResult((), (ConceptRejection(
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, RejectionReason.INSUFFICIENT_TOTAL_AREA,
            f"largest safe wing is {candidates[0].area_m2:.1f} m2; the programme needs about "
            f"{needed:.1f} m2"),), tuple(rooms), (constraint,))

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
    pair = _two_wing_pair(candidates)
    # Every arrangement of the same requirements, the brief as written first. Insertion order is
    # NOT what keeps a rearranged programme from displacing the literal one — the area sort below
    # may rank it first — so nothing about access semantics is decided here: `programme_variants`
    # only returns arrangements the brief allows (specs/007 FR-7/FR-8), and the sort chooses among
    # candidates that are all acceptable.
    for variant in variants:
        bands, rejection = _front_band_concept(spec, variant, primary.rect)
        accepted.extend(bands)
        if not bands and rejection is not None and variant is rooms:
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
            # 008: a hub is offered as a peer of the other partis only where its tree can meet the
            # §6 gates on THIS outline (the Phase 0 bound, computed on the engine's own allocation);
            # elsewhere it is kept as the last resort so no rescued brief becomes a refusal.
            hub_rooms = [ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION, HUB_TEMPLATE)
                         if r.group is ZoneGroup.CIRCULATION else r for r in variant]
            bound = hub_bound(hub_rooms, hub.concept.footprint_width_m, hub.concept.footprint_depth_m,
                              _hub_widths(spec, variant) or _HUB_WIDTHS_M)
            eligibility = hub_eligibility(bound)
            note = ("hub eligible on this outline: " if eligibility is HubEligibility.ELIGIBLE
                    else "hub last resort on this outline: ") + bound.describe()
            if eligibility is HubEligibility.ELIGIBLE and bound.witness is not None:
                # 008 follow-up: size the eligible wing as the bound's witness, re-planned through
                # the same checks; if the witness cannot be planned the v2 candidate stands and the
                # rationale says why (reported, never tuned around).
                hub, note = _hub_from_witness(spec, hub_rooms, hub, bound, note)
            hub = replace(hub, rationale=f"{hub.rationale}; {note}",
                          hub_last_resort=eligibility is HubEligibility.LAST_RESORT)
            if eligibility is HubEligibility.LAST_RESORT:
                last_resort.add(id(hub))
            accepted.append(hub)
        elif rejection is not None and variant is rooms:
            rejections.append(rejection)

        # THE L, last in insertion order like the hub and for the same reason: without a target the
        # order is the ranking, and a two-wing plan must not displace the plan a brief already had.
        # With a target the area sort decides among all of them alike — nothing ranks the L up or
        # down. Only two ADJACENT safe wings reach the parti; a single wing never does, so every
        # one-wing brief costs exactly what it cost before.
        if isinstance(pair, tuple):
            from . import l_parti  # local: l_parti builds on this module's helpers
            l_built, rejection = l_parti.l_concepts(spec, variant, *pair)
            accepted.extend(l_built)
            if not l_built and rejection is not None and variant is rooms:
                rejections.append(rejection)

    if isinstance(pair, ConceptRejection):
        rejections.append(pair)

    # "Best first" now means CLOSEST TO THE REQUESTED AREA first, not simply the order the
    # strategies happen to be generated in — the pipeline takes the first concept Geometry Core can
    # realize, so this ordering is what actually decides the delivered house size. Without a target
    # the original strategy order is kept, so the site-driven baselines do not move.
    # Tier 2 (`Repartition`) candidates are ranked among themselves the same way but AFTER every
    # normal candidate and its twin: a brief that plans normally never receives one, and one is
    # delivered only when nothing normal can be realized. Ordering only — no score, no bonus.
    tier2 = [c for c in accepted if c.repartitioned and not c.quality_repartitioned]
    # The QUALITY tier (`_quality_layouts`) is its own block after tier 2, ordered the same way:
    # a plan re-partitioned for proportions is offered beside the plan it came from, never in
    # front of any candidate a brief already had. Ranking among them is a later review's question.
    quality = [c for c in accepted if c.quality_repartitioned]
    accepted = [c for c in accepted if not c.repartitioned]
    if target_m2 is not None:
        # A shrunk candidate (`ConceptCandidate.shrunk`) ranks by the same proximity and loses
        # only a tie in area to a normal one.
        accepted.sort(key=lambda c: (round(abs(c.used_area_m2 - target_m2), 4),
                                     c.over_preferred or c.shrunk, c.over_preferred,
                                     round(c.used_area_m2, 4), c.strategy.value))
        tier2.sort(key=lambda c: (round(abs(c.used_area_m2 - target_m2), 4),
                                  round(c.used_area_m2, 4), c.strategy.value))
        quality.sort(key=lambda c: (round(abs(c.used_area_m2 - target_m2), 4),
                                    c.over_preferred or c.shrunk, c.over_preferred,
                                    round(c.used_area_m2, 4), c.strategy.value))

    else:
        # Without a target the strategy order is kept; the fallbacks (shrunk, then over
        # preferred) follow the normal candidates.
        accepted.sort(key=lambda c: (c.over_preferred or c.shrunk, c.over_preferred))
    # Every forced tree first, in the order just decided; then the same trees with their cut
    # positions left to the solver, in the same order. See `_unforced` for why this ordering — and
    # not one twin behind each forced tree — is the one that leaves every existing plan untouched.
    twins = [_free_twin(c) for c in accepted]
    for forced, twin in zip(accepted, twins):
        if id(forced) in last_resort:
            last_resort.add(id(twin))
    accepted.extend(twins)
    # ...and only then tier 2, forced trees first and their twins after, the same way.
    accepted.extend(tier2)
    accepted.extend(_free_twin(c) for c in tier2)
    # ...and after tier 2 the quality tier, the same way again.
    accepted.extend(quality)
    accepted.extend(_free_twin(c) for c in quality)

    # 008: last-resort hubs go after EVERY other candidate — the other partis' twins included — in
    # the order they already had (forced tree before its twin), so the first-realizable pipeline
    # reaches them only when nothing else plans. Ordering only: no score, no bonus.
    if last_resort:
        accepted = ([c for c in accepted if id(c) not in last_resort]
                    + [c for c in accepted if id(c) in last_resort])

    # THE L LAST OF ALL without a target — after every one-wing candidate, its twin, tier 2 and the
    # last-resort hubs, in the order they already had. Without a target the order IS the ranking,
    # and a two-wing plan must not displace the plan a brief already had (the hub's rule, applied
    # to the whole list because an L normal candidate would otherwise precede a one-wing fallback
    # that used to be the primary). With a target the area sort above decided, and the L competes
    # under exactly the rules every other candidate does.
    if target_m2 is None:
        accepted = ([c for c in accepted if c.strategy is not ConceptStrategy.MULTI_WING_SPLIT]
                    + [c for c in accepted if c.strategy is ConceptStrategy.MULTI_WING_SPLIT])

    return GenerationResult(tuple(accepted), tuple(rejections), tuple(rooms), (constraint,))
