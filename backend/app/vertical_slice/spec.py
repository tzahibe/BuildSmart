"""Stage 1 — `ArchitecturalSpec`: the vertical slice's input contract.

This is deliberately tiny. It is NOT the `app.architect.models.ArchitecturalSpec` used by the
live `app/design` pipeline (a different, older domain model) — building a translator between
the two is real integration work, out of scope for "first vertical slice only, no new
domain-model research." This module's `ArchitecturalSpec` is this slice's own, self-contained
input, and is named to match the pipeline the review approved
(ArchitecturalSpec -> Concept/DesiredAccessTopology -> Site -> Geometry Core -> ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class PlotSpec:
    """A rectangular plot, street-facing edge at y=0. PARAMETER · UNVERIFIED: setbacks below
    are plausible placeholders, not sourced from a specific municipal plan (matches how
    `RC_SAFE_ROOM` thickness is flagged in geometry_core.model — no regulation number here is
    a verified legal figure)."""

    width_m: float
    depth_m: float
    front_setback_m: float = 5.5   # building line offset from the street edge (parking lives here)
    side_setback_m: float = 3.0
    rear_setback_m: float = 4.0

    def buildable_origin_m(self) -> tuple[float, float]:
        return (self.side_setback_m, self.front_setback_m)

    def buildable_size_m(self) -> tuple[float, float]:
        return (
            self.width_m - 2 * self.side_setback_m,
            self.depth_m - self.front_setback_m - self.rear_setback_m,
        )


class CorridorWidthMode(str, Enum):
    """How the person worded a corridor width, which decides what may be done with it.

    EXACT and MINIMUM are binding: a plan that does not meet them is not returned. PREFERENCE is
    attempted first and dropped with a warning if the programme cannot fit it — the distinction
    exists because "המסדרון חייב להיות לפחות 1.6 מטר" and "אני מעדיף מסדרון של 2 מטר" ask for the
    same thing and must fail differently.
    """

    EXACT = "exact"        # "מסדרון ברוחב 1.8 מטר" — plan to this width
    MINIMUM = "minimum"    # "לפחות 1.6 מטר" — never narrower; wider is fine
    PREFERENCE = "preference"


@dataclass(frozen=True)
class CorridorRequirement:
    """An authoritative corridor width, in metres, plus how binding it is."""

    width_m: float
    mode: CorridorWidthMode = CorridorWidthMode.MINIMUM

    @property
    def is_binding(self) -> bool:
        return self.mode is not CorridorWidthMode.PREFERENCE

    def satisfied_by(self, realized_m: float, *, tol_m: float = 0.005) -> bool:
        """Does a realized corridor meet this requirement?

        MINIMUM and PREFERENCE are one-sided — wider is always fine. EXACT is two-sided, but only
        downward-strict in practice: the grid is 5 cm, so a couple of millimetres of rounding must
        not fail a plan that is otherwise exactly right.
        """
        if self.mode is CorridorWidthMode.EXACT:
            # Never narrower than asked; up to one partition-half wider is accepted. The planner
            # fixes the corridor before wall types are known and budgets for the thickest wall the
            # hall might touch, so a corridor that lands slightly generous is the cost of never
            # landing short. Rejecting it would send the person to change a request that was met.
            return -tol_m <= realized_m - self.width_m <= 0.105
        return realized_m >= self.width_m - tol_m


class RoomRelation(str, Enum):
    """What the person asked for between two rooms. Four distinct things, never collapsed.

    ADJACENT is a shared wall. DIRECT_ACCESS is a door THROUGH that wall — a separate request, and
    one that must never be inferred from adjacency. NEAR has one fixed, measurable meaning defined
    in `relationships.py`. NOT_ADJACENT forbids a shared wall.
    """

    ADJACENT = "adjacent"
    DIRECT_ACCESS = "direct_access"
    NEAR = "near"
    NOT_ADJACENT = "not_adjacent"


class RelationStrength(str, Enum):
    HARD_REQUIREMENT = "hard_requirement"
    PREFERENCE = "preference"


@dataclass(frozen=True)
class RoomRelationshipRequirement:
    """One relationship, in role tokens rather than zone ids — the person named a KIND of room and
    the plan decides which zone that is (see `relationships.resolve_reference`)."""

    source_role: str
    target_role: str
    relation: RoomRelation
    strength: RelationStrength = RelationStrength.PREFERENCE
    source_text: str = ""


class WetRoomKind(str, Enum):
    """What a wet room IS, in terms of who reaches it. Four distinct things, never collapsed.

    A wet room used to be a count, and `build_room_program` re-invented the kinds from the number —
    so "ensuite + guest WC" and "two shared bathrooms" arrived as the same brief. The kinds carry
    what the person actually said; `UNSPECIFIED` is the honest value for what they did not.
    """

    SHARED_BATHROOM = "shared_bathroom"   # full bathroom, entered from circulation
    ENSUITE = "ensuite"                   # full bathroom, entered ONLY from its host bedroom
    GUEST_WC = "guest_wc"                 # WC + basin, entered from circulation
    UNSPECIFIED = "unspecified"           # counted by the brief, kind not stated


class WetRoomStrength(str, Enum):
    """REQUIRED is the brief as written. FLEXIBLE means the person said the placement does not
    matter — the only case in which the planner may hang a shared bathroom off a bedroom."""

    REQUIRED = "required"
    FLEXIBLE = "flexible"


class WetRoomOrigin(str, Enum):
    """WHO DECIDED THIS ROOM EXISTS. EXPLICIT: the person named it as a room (or confirmed it on
    the review screen). COUNT_DERIVED: the system made a room out of a number — a bare "שירותים"
    left over after every bathroom already holds a toilet, or the legacy bare-count default.

    A toilet is a FIXTURE; every bathroom contains one. Only the surplus becomes a room, and a
    room that exists only because of a count is a weaker claim than one the person asked for:
    the review screen says so, and specs/009 (decision B) plans its placement as a preference
    rather than a law. Measured 2026-09-15 before this existed: the parser counted every
    "שירותים" as a room in 16 of 29 briefs that also named a bathroom, and the delivered plans
    carried a surplus full bathroom in 13 of 37.
    """

    EXPLICIT = "explicit"
    COUNT_DERIVED = "count_derived"


#: Host tokens an ENSUITE may name. Which secondary bedroom hosts a `BEDROOM` ensuite is the
#: programme's choice (`concept_generator.resolve_wet_rooms`), never the brief's.
ENSUITE_HOST_MASTER = "MASTER_BEDROOM"
ENSUITE_HOST_BEDROOM = "BEDROOM"


class LaundryDemand(str, Enum):
    """What the brief asked for a laundry room to be.

    Two values today. A niche/alcove treatment (a laundry appliance recessed into circulation or
    the kitchen rather than its own room) is a real future option this enum deliberately leaves
    room for — the name is reserved in the docs this phase produced — but it is NOT implemented:
    `NONE`/`ROOM` are the only members, and nothing in this codebase should assume a third exists.
    """

    NONE = "none"
    ROOM = "room"


@dataclass(frozen=True)
class LaundryRequirement:
    """What the brief said about a laundry room, with the words that said it.

    There is no COUNT_DERIVED case here the way there is for `WetRoomOrigin` — a laundry room is
    never padded in from a number, never inferred from an appliance mention (see
    `requirements/parser.py`'s extraction rules). `demand` is `ROOM` only when the person named a
    room; `source_text` is empty whenever it is not.
    """

    demand: LaundryDemand = LaundryDemand.NONE
    source_text: str = ""


@dataclass(frozen=True)
class WetRoomRequirement:
    """One wet room the brief counted, with whatever the brief said about it."""

    kind: WetRoomKind = WetRoomKind.UNSPECIFIED
    #: ENSUITE only: `ENSUITE_HOST_MASTER` (the default when an ensuite names no host) or
    #: `ENSUITE_HOST_BEDROOM`. `None` for every other kind.
    host: str | None = None
    strength: WetRoomStrength = WetRoomStrength.REQUIRED
    source_text: str = ""
    origin: WetRoomOrigin = WetRoomOrigin.EXPLICIT


@dataclass(frozen=True)
class ProgramSpec:
    """What the house must contain. Counts, plus the size the user asked for.

    `target_built_area_m2` is the TARGET BUILT AREA the person entered — the gross area the
    generated house should come out at, not a ceiling it merely has to stay under. It is optional
    because the site-driven scenarios (`run_general` on an L-shaped or curved parcel) have no user
    target at all; there it stays `None` and the generator keeps its original programme-minimum
    sizing, which is what those baselines were measured against.
    """

    bedrooms: int = 3
    safe_room: bool = True
    open_plan_living: bool = True
    wet_rooms: int = 2
    parking_spaces: int = 2
    target_built_area_m2: float | None = None
    #: The corridor width the person asked for, when they asked for one. `None` keeps the
    #: generator's own derived width and its existing default behaviour.
    corridor: CorridorRequirement | None = None
    #: Room relationships the brief asked for. Hard ones gate the plan; preferences rank candidates.
    relationships: tuple[RoomRelationshipRequirement, ...] = ()
    #: What the brief said about each wet room, in order. Empty (the legacy value) means every wet
    #: room is `UNSPECIFIED`; shorter than `wet_rooms` is padded with `UNSPECIFIED`; longer is a
    #: defect the engine refuses (`concept_generator.resolve_wet_rooms`). The COUNT stays the
    #: authority on how many.
    wet_room_kinds: tuple[WetRoomRequirement, ...] = ()
    #: Whether the brief asked for a laundry room of its own (2026-09-16 phase 1). Never derived,
    #: never padded — `LaundryDemand.NONE` (the default) is the honest value for "not asked".
    #: Emitting an actual room for `ROOM` is additionally gated by
    #: `concept_generator.LAUNDRY_ROOM_ENABLED` until the planner sweep this phase produced is
    #: accepted — see docs/LAUNDRY_ROOM_OPTION_REVIEW.md.
    laundry: LaundryRequirement = LaundryRequirement()

    @property
    def total_built_area_m2(self) -> float | None:
        """The requested built area as the TOTAL over every level of the house.

        One number has been doing four jobs — total requested area, storey count, per-storey area
        and footprint — because the demo plans one storey and the four coincide. This is the name
        for the first of them. It is an alias of `target_built_area_m2` today and reads the same
        field; when a second level exists the per-level targets are derived FROM this total by the
        allocation stage, and nothing below that stage should read the total directly.
        """
        return self.target_built_area_m2


# --------------------------------------------------------------------------- house concept
#
# HOW the house is organised, as distinct from WHAT it contains (`ProgramSpec`). Every field here
# is either a PROGRAM-ALLOCATION fact (which level a room class lives on) or a SEARCH-ORDERING
# preference (which parti to try first). None of them is a dimension: no footprint, no ratio, no
# stair size. That is the whole point — a concept says "a plan with these qualities", never "this
# geometry" — and it is what keeps the principle that the person chooses plans, not footprints.
#
# Nothing in the geometry stack reads `HouseConcept`. It reaches the engine only through the
# level programs the allocation stage derives from it and through a strategy sort key.


class LevelRef(str, Enum):
    """Which level a room class is asked to live on. `ENGINE` = the allocation stage decides."""

    GROUND = "ground"
    UPPER = "upper"
    ENGINE = "engine"


class PublicPrivateStrategy(str, Enum):
    """How the public and private zones are split between two levels."""

    #: LDK, guest WC, entrance on the ground; every bedroom and its bathrooms above.
    PUBLIC_BELOW_PRIVATE_ABOVE = "public_below_private_above"
    #: As above, but the master suite stays on the ground.
    MASTER_SUITE_BELOW = "master_suite_below"
    #: Public plus one ordinary bedroom on the ground; the rest above.
    PUBLIC_PLUS_ONE_BEDROOM_BELOW = "public_plus_one_bedroom_below"
    #: The allocation stage chooses. The ONLY legal value on a single-storey house.
    ENGINE = "engine"


class BedroomGrouping(str, Enum):
    TOGETHER = "together"
    ENGINE = "engine"


class CirculationStyle(str, Enum):
    """The circulation parti to try FIRST. Ordering only — never a gate, never a dimension."""

    SPINE = "spine"
    FRONT_BAND = "front_band"
    HUB = "hub"
    ENGINE = "engine"


class PublicOpenSide(str, Enum):
    """Which side the public rooms should open to. `GARDEN` names a parti the generator does not
    have yet (every parti puts the public zone west or on the street front); a concept that BINDS
    it is refused as an unsupported hard requirement rather than quietly honoured as `STREET`."""

    STREET = "street"
    GARDEN = "garden"
    ENGINE = "engine"


class ConceptSource(str, Enum):
    USER_EXAMPLE = "user_example"
    CHAT = "chat"
    ENGINE = "engine"


@dataclass(frozen=True)
class LevelAreaPreference:
    """"About this much on this level" — a PREFERENCE the per-level proportion search aims at.
    Never a constraint: the total is the request; the split is the engine's unless said."""

    level_index: int
    area_m2: float


@dataclass(frozen=True)
class HouseConcept:
    """The architectural concept a house is organised around. See the module comment above.

    STRENGTH. `stories` is always binding — a person who chose two storeys is not handed one with a
    note. Every other field is a preference unless its name is in `hard_fields`, in which case a
    plan that cannot honour it is refused rather than returned with a warning. This is the same
    grammar `CorridorRequirement.mode` and `RelationStrength` use: binding gates, preference orders.

    DEFAULT = "the engine decides everything, one storey" — which is exactly the house the demo
    plans today, so an `ArchitecturalSpec` built without a concept behaves as it always has.
    """

    stories: int = 1
    public_private_strategy: PublicPrivateStrategy = PublicPrivateStrategy.ENGINE
    entrance_level: LevelRef = LevelRef.GROUND
    master_level: LevelRef = LevelRef.ENGINE
    bedroom_grouping: BedroomGrouping = BedroomGrouping.ENGINE
    circulation_style: CirculationStyle = CirculationStyle.ENGINE
    public_open_side: PublicOpenSide = PublicOpenSide.ENGINE
    level_area_preferences: tuple[LevelAreaPreference, ...] = ()
    #: An optional concept-card id, for diagnostics and display grouping only — like
    #: `DemoDesign.family`, never parsed for meaning.
    family: str | None = None
    source: ConceptSource = ConceptSource.ENGINE
    #: Preference fields the person made BINDING, by field name. `stories` need not be listed.
    hard_fields: frozenset[str] = frozenset()

    #: Fields that may be bound. `stories` is always bound; `source`, `family` and the area
    #: preferences carry no strength of their own.
    BINDABLE = frozenset({"public_private_strategy", "entrance_level", "master_level",
                          "bedroom_grouping", "circulation_style", "public_open_side"})

    def __post_init__(self) -> None:
        if self.stories < 1:
            raise ValueError(f"stories must be at least 1, got {self.stories}")
        if self.stories == 1:
            # A one-level house has no "below" and "above" to split anything between. Refusing
            # the combination here keeps a stale two-storey field from silently surviving a
            # switch back to one storey and being read by whatever looks at it next.
            if self.public_private_strategy is not PublicPrivateStrategy.ENGINE:
                raise ValueError("public_private_strategy applies only when stories > 1")
            if self.master_level is LevelRef.UPPER:
                raise ValueError("master_level=UPPER needs a second storey")
        if self.entrance_level is not LevelRef.GROUND:
            raise ValueError("entrance_level: only GROUND is modelled (no basement or split level)")
        for pref in self.level_area_preferences:
            if not 0 <= pref.level_index < self.stories:
                raise ValueError(f"level_area_preferences names level {pref.level_index}; the "
                                 f"house has {self.stories} storey(s)")
            if pref.area_m2 <= 0:
                raise ValueError("a level area preference must be positive")
        unknown = self.hard_fields - self.BINDABLE
        if unknown:
            raise ValueError(f"hard_fields names fields that cannot be bound: {sorted(unknown)}; "
                             f"bindable: {sorted(self.BINDABLE)}")

    def is_binding(self, field_name: str) -> bool:
        """Whether a plan that cannot honour `field_name` must be REFUSED (else: warned)."""
        return field_name == "stories" or field_name in self.hard_fields

    @property
    def is_single_storey(self) -> bool:
        return self.stories == 1


@dataclass(frozen=True)
class ArchitecturalSpec:
    plot: PlotSpec
    program: ProgramSpec
    #: How the house is organised. Defaults to the engine's own one-storey house, so the two-field
    #: constructor every caller uses today builds exactly the spec it always did.
    concept: HouseConcept = field(default_factory=HouseConcept)


def demo_spec() -> ArchitecturalSpec:
    """The one scenario this vertical slice targets: ~150-180 m² single-floor private house,
    3 bedrooms + safe room, open-plan LDK, 2 wet rooms, 2 parking spaces, entrance + garden."""
    return ArchitecturalSpec(
        plot=PlotSpec(width_m=20.0, depth_m=24.0),
        program=ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=True,
                             wet_rooms=2, parking_spaces=2),
    )
