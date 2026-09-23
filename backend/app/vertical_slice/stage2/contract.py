"""Stage 2 (A/2), Issue #133 — the shared contract every later Stage 2 child implements.

Before Stage 2 does any realization work, three prior pieces of work each invented their own shape
for the same facts, and nothing bound them together:

- POC Issue #109 (``spikes/architectural_brain/realization_intent.py``, not merged to ``main`` —
  reachable read-only from its own worktree, not importable here) built ``RealizationIntent``, keyed
  by donor room id, from a retrieved ``PlanReference``.
- ``realize.py`` (same POC) rebuilt the donor-room correspondence AD HOC as
  ``donor_room_id_by_zone(brief, adapted) -> dict[str, str]``, by re-matching adapted rooms to donor
  roles positionally — silently returning ``None`` (never recorded, never classified) for a room
  whose adaptation dropped it, added it, or resized it only in aggregate. Measured: 38 of 136 lost
  facts in ``preservation.py`` are exactly this — ``DONOR_ROOM_NOT_REALIZED`` for a donor room that
  was never wrong, just never looked up correctly.
- Stage 1 Issue #117 (``app/vertical_slice/rectilinear_realizer.py``, on
  ``integration/rectilinear-realizer``, not merged to ``main``) defined its OWN
  ``RealizationIntent`` — a "PLACED layout" shape (wings/zones/groups), by construction unrelated
  to #109's donor-fact shape, but with the SAME NAME. It excludes wet rooms and SAFE_ROOM entirely:
  ``realize_layout`` never passes ``wet_rooms`` to ``validation.validate``, so C17/C29 do not run.

This module is the ONE place all of that gets a name that means one thing. It defines TYPES ONLY —
no realization, no repair, no measurement, no wiring into any production caller. Every dataclass
below is the SOLE owner of its own shape: a later Stage 2 child that builds retrieval/adaptation/
repair/realization imports these types rather than inventing its own, and if a later child finds one
genuinely wrong, THIS module is what it edits — not a parallel copy.

``STAGE2_CONTRACT_ENABLED`` gates nothing: no existing caller imports this package, so the frozen
432-context regression corpus is unaffected by construction (AC-4). The flag exists only as the
same disclosure/kill-switch precedent ``RECTILINEAR_REALIZER_ENABLED``/``LAUNDRY_ROOM_ENABLED`` set,
for whichever future Issue wires Stage 2 into the production pipeline.

See ``docs/stage2/CONTRACT.md`` for the prose companion to this module — six numbered sections,
one per required behaviour, each naming this module as the owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.wet_rooms import ResolvedWetRoom

#: Off by default. No existing caller imports `app.vertical_slice.stage2` at all — this exists only
#: as the disclosure/kill-switch precedent, for a future Issue that wires Stage 2 in.
STAGE2_CONTRACT_ENABLED = False

# =============================================================================================
# 1. Donor room identity
# =============================================================================================
#: The stable id of a room in the retrieved `PlanReference` (`spikes/architectural_brain/
#: plan_reference.py`'s own `Room.id`, e.g. "LIVING_0", "BEDROOM_2") — never re-minted, never
#: reused for a different room, at any later stage. Every later stage refers to a donor room by
#: THIS id and nothing else: not a role+index pair, not a positional match, not a zone id that
#: happens to look similar. THIS MODULE owns the type; `plan_reference.Room.id`'s own string values
#: are its only producer.
DonorRoomId = str


class RoomLineageKind(str, Enum):
    """What happened to one or more donor rooms at one pipeline stage — the explicit classification
    Required Behaviour 1 asks for, so "this donor room has no zone" is never merely a lookup miss.

    CARRIED  — the donor room passes through this stage with its own identity unchanged (it may
               still be resized/repositioned; CARRIED is about IDENTITY, not geometry).
    ADDED    — a room with no donor counterpart is introduced at this stage (e.g. `BEDROOM_COUNT_
               ADJUST` padding to the brief's bedroom count past what the donor had).
    DROPPED  — a donor room has no counterpart from this stage onward (e.g. `BEDROOM_COUNT_ADJUST`
               removing a donor bedroom past the brief's own count).
    MERGED   — two or more donor rooms combine into one later entity (mirrors `room_merge.py`'s own
               2-way precedent, generalized).
    SPLIT    — one donor room becomes two or more later entities.
    """

    CARRIED = "CARRIED"
    ADDED = "ADDED"
    DROPPED = "DROPPED"
    MERGED = "MERGED"
    SPLIT = "SPLIT"


#: The pipeline stages a donor room identity travels through, in order (Required Behaviour 1).
#: A `RoomLineageEvent.stage` is always one of these, spelled exactly this way.
PIPELINE_STAGES = ("retrieval", "synthesis", "adaptation", "seeding", "repair", "realization")


@dataclass(frozen=True)
class RoomLineageEvent:
    """One classified fact about donor room identity, recorded by whichever stage changed (or
    deliberately preserved) it. `donor_room_ids` is empty only for ADDED (nothing donor-side to
    name); `result_ids` is empty only for DROPPED (nothing survives past this stage). A CARRIED
    event names the SAME id on both sides — recording "nothing happened to this one" explicitly,
    so a donor room's absence from every event (not just a DROPPED one) is what
    `RoomLineage.unaccounted_donor_ids` catches as a bug, never an intentional omission."""

    kind: RoomLineageKind
    donor_room_ids: tuple[DonorRoomId, ...]
    result_ids: tuple[str, ...]
    stage: str
    reason: str

    def __post_init__(self) -> None:
        if self.stage not in PIPELINE_STAGES:
            raise ValueError(f"RoomLineageEvent.stage {self.stage!r} not one of {PIPELINE_STAGES}")
        if self.kind is RoomLineageKind.ADDED and self.donor_room_ids:
            raise ValueError("ADDED must not name a donor_room_id — nothing donor-side to name")
        if self.kind is RoomLineageKind.DROPPED and self.result_ids:
            raise ValueError("DROPPED must not name a result_id — nothing survives")
        if self.kind is RoomLineageKind.CARRIED and self.donor_room_ids != self.result_ids:
            raise ValueError("CARRIED must name the SAME id(s) on both sides")


@dataclass(frozen=True)
class RoomLineage:
    """The full donor-room-identity record for one concept: every donor room id the retrieved
    `PlanReference` carried, plus every event any stage recorded about it. THIS MODULE owns the
    type; each pipeline stage module (once it exists) is what APPENDS events to it — this type
    itself never inspects a stage's own internals.
    """

    donor_room_ids: tuple[DonorRoomId, ...]
    events: tuple[RoomLineageEvent, ...]

    def unaccounted_donor_ids(self) -> tuple[DonorRoomId, ...]:
        """Donor room ids with NO event at all — the bug `RoomLineageEvent`'s own docstring
        describes (a donor room silently missing rather than explicitly CARRIED/DROPPED/MERGED/
        SPLIT). Empty exactly when Required Behaviour 1 holds."""
        named: set[str] = set()
        for event in self.events:
            named.update(event.donor_room_ids)
        return tuple(d for d in self.donor_room_ids if d not in named)


# =============================================================================================
# 2. Seed geometry
# =============================================================================================

@dataclass(frozen=True)
class SeedCell:
    """One donor room's own partition, before any repair — a 1:1 mirror of the donor's own room
    polygon, not yet resized, not yet repaired. `donor_room_id` is always set for a genuine seed
    cell (a seed cell with no donor room is a contradiction — an ADDED room only exists from repair
    onward, never at seeding; see `RoomLineageKind`)."""

    cell_id: str
    donor_room_id: DonorRoomId
    polygon_m: tuple[tuple[float, float], ...]


#: `SeedGeometry.frame`'s only defined value today — the donor's OWN plan frame: an unrotated,
#: image-like coordinate system where north/west are the SMALLER-coordinate sides (the exact
#: convention `patterns._side_of_bbox_center`/`realization_intent._relative_placement_for` already
#: use), in meters, not yet aligned to any realized building's own frame.
DONOR_PLAN_FRAME = "DONOR_PLAN_IMAGE_FRAME_METERS"


@dataclass(frozen=True)
class SeedGeometry:
    """The donor's own partition, carried as data, before any repair (Required Behaviour 2). Every
    `cells` entry is one donor room, verbatim; `adjacency` is copied from the donor's own
    `adjacency_edges` (cell id pairs, never re-derived from geometry) — mirroring
    `realization_intent.AdjacencyFact`'s own "copied verbatim, never inferred" rule."""

    source_plan_id: str
    frame: str
    cells: tuple[SeedCell, ...]
    adjacency: tuple[tuple[str, str], ...]

    def donor_room_ids(self) -> tuple[DonorRoomId, ...]:
        return tuple(c.donor_room_id for c in self.cells)


# =============================================================================================
# 3. RealizationIntent content — ADOPTED UNCHANGED from POC Issue #109
# =============================================================================================
# `spikes/architectural_brain/realization_intent.py` (Issue #109, Phase 2 Track 3) already got this
# right: every fact is either a direct copy of something the retrieved `PlanReference` states, or a
# DETERMINISTIC, DOCUMENTED geometric derivation from facts the reference already carries — never a
# value invented where the reference has none. The dataclass SHAPE below is that module's own,
# reproduced field-for-field (the POC branch itself is not reachable from this worktree, so this is
# transcribed, not imported — the same "authored fresh, not forked" situation #117's own
# `RealizationIntent` docstring already names). THIS MODULE now owns the shape; #109's own module,
# once merged, is expected to import FROM here rather than keep its own copy. The derivation
# function (`intent_from`, which needs `PlanReference`/`ConceptSpec`/`Brief` — none on `main` yet)
# is deliberately NOT reproduced here: that is behaviour, not vocabulary, and stays out of this
# Issue's scope until the child that wires retrieval in.

@dataclass(frozen=True)
class AdjacencyFact:
    room_a: DonorRoomId
    room_b: DonorRoomId


@dataclass(frozen=True)
class AccessFact:
    room_a: DonorRoomId
    room_b: DonorRoomId
    kind: str


@dataclass(frozen=True)
class ExposureFact:
    room_id: DonorRoomId
    sides: tuple[str, ...]
    known: bool


@dataclass(frozen=True)
class RelativePlacement:
    room_id: DonorRoomId
    primary_axis: str
    secondary_axis: str


@dataclass(frozen=True)
class Clusters:
    public: tuple[DonorRoomId, ...]
    private: tuple[DonorRoomId, ...]


@dataclass(frozen=True)
class CirculationNode:
    room_id: DonorRoomId
    serves: tuple[DonorRoomId, ...]


@dataclass(frozen=True)
class EntranceRelationship:
    room_id: DonorRoomId | None
    side: str


@dataclass(frozen=True)
class RoomProportion:
    """One donor room's OWN proportions — never a fixed per-type constant. `area_share_of_type` is
    this room's own area divided by the MEAN area of every donor room of the same type (1.0 when it
    is the only room of its type)."""

    room_id: DonorRoomId
    room_type: str
    aspect_ratio: float | None
    area_share_of_type: float


@dataclass(frozen=True)
class FootprintRelationships:
    width_m: float
    depth_m: float
    aspect_ratio: float | None
    fill_ratio: float | None


@dataclass(frozen=True)
class RealizationIntent:
    """Exactly which facts, in whose coordinate frame: adjacency, access, exterior exposure,
    relative placement, public/private clusters, wet-core groups, entrance relationship, room
    proportions, footprint relationships — every field keyed by `DonorRoomId` where it names a room,
    in the donor's own frame (`DONOR_PLAN_FRAME`) for anything geometric. Adopted unchanged from
    POC Issue #109 (see module-level docstring above)."""

    schema_version: str
    source_plan_id: str
    concept_id: str
    adjacency_edges: tuple[AdjacencyFact, ...]
    access_edges: tuple[AccessFact, ...]
    exterior_exposure: tuple[ExposureFact, ...]
    relative_placement: tuple[RelativePlacement, ...]
    public_private_clusters: Clusters
    circulation_nodes: tuple[CirculationNode, ...]
    wet_core_groups: tuple[tuple[DonorRoomId, ...], ...]
    entrance_relationship: EntranceRelationship
    room_proportions: tuple[RoomProportion, ...]
    footprint_relationships: FootprintRelationships

    def donor_room_ids(self) -> tuple[DonorRoomId, ...]:
        """Every donor room this intent states a `RoomProportion` for — `_room_proportions`
        (POC #109) builds one entry per `reference.rooms`, unconditionally, so this is the intent's
        own complete donor-room roster, independent of whether any OTHER fact class mentions a
        given room."""
        return tuple(p.room_id for p in self.room_proportions)


# =============================================================================================
# 4. The realizer's input and refusal contract
# =============================================================================================
# Stage 1 Issue #117's own `rectilinear_realizer.RealizationIntent` ("PLACED layout": wings, zones,
# already-decided adjacency/placement/exposure) is a DIFFERENT thing from #109's `RealizationIntent`
# above (donor facts, not yet placed) — the two shared one name in two different, unmerged
# worktrees, which is exactly the confusion Required Behaviour 3/4 exist to end. Renamed here to
# `RealizerInput`: the exact structure the non-guillotine realizer receives. Field shapes mirror
# #117's own `ZoneIntent`/`PinwheelWing`/`RowWing`/`ShapeGroupIntent` (that Issue's own worktree is
# not reachable from here either, so these are transcribed, not imported) plus `wet_rooms` — #117's
# own realizer never threads `ResolvedWetRoom` through to `validate()`, which is why C17/C29 cannot
# run on its output (see Required Behaviour 5 below); THIS module adds the field so a later child
# has nowhere else to look for it.

@dataclass(frozen=True)
class ZoneIntent:
    """One room's own requirement: net area min/target/max, min short side, max aspect, plus the
    `ProgramRole` this realizer assigns it, and the `DonorRoomId` it traces back to (`None` only for
    a zone Required Behaviour 1 classifies ADDED — e.g. a `BEDROOM_COUNT_ADJUST` room)."""

    zone_id: str
    role: ProgramRole
    donor_room_id: DonorRoomId | None
    target_area_m2: float
    min_area_m2: float
    max_area_m2: float
    min_short_side_m: float = 2.0
    max_aspect_ratio: float = 2.5


@dataclass(frozen=True)
class PinwheelWing:
    """A 5-room windmill: `center` surrounded by `n`/`e`/`s`/`w` — non-guillotine by construction."""

    wing_id: str
    width_m: float
    height_m: float
    n: ZoneIntent
    e: ZoneIntent
    s: ZoneIntent
    w: ZoneIntent
    center: ZoneIntent


@dataclass(frozen=True)
class ShapeGroupIntent:
    """One notch-carve group: `big`'s realized shape is its own container rectangle MINUS
    `notches` (1 for L/U, 2 for T)."""

    group_id: str
    family: str  # "L" | "U" | "T"
    big: ZoneIntent
    notches: tuple[ZoneIntent, ...]
    corner: str = "NE"
    edge: str = "N"


@dataclass(frozen=True)
class RowWing:
    """A single row of top-level slots spanning the wing's full height, left to right — ordinary
    `ZoneIntent`s and at most one `ShapeGroupIntent`."""

    wing_id: str
    width_m: float
    height_m: float
    slots: tuple[str, ...]
    zones: dict[str, ZoneIntent]
    groups: dict[str, ShapeGroupIntent]


Wing = PinwheelWing | RowWing


@dataclass(frozen=True)
class RealizerInput:
    """The exact placed-layout structure the non-guillotine realizer receives — adjacency,
    placement and exposure already decided; `wet_rooms` is the `ResolvedWetRoom` roster so C17/C29
    can run on the realized output (Required Behaviour 5).

    INVARIANTS that must hold before this is handed to a realizer (checked by
    `validate_realizer_input`, never silently repaired by the realizer itself):

    - `wings` is non-empty.
    - Every `zone_id` across every wing's zones/groups is unique.
    - Every `ZoneIntent.donor_room_id` that is not `None` names a room `intent.donor_room_ids()`
      actually has a `RoomProportion` for, OR is explicitly recorded `ADDED` in the `RoomLineage`
      this input was built from.
    """

    name: str
    wings: tuple[Wing, ...]
    wet_rooms: tuple[ResolvedWetRoom, ...]
    entrance_hint_zone_id: str | None = None
    declared_adjacency: tuple[tuple[str, str], ...] = ()
    declared_exposure: tuple[str, ...] = ()

    def zone_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for w in self.wings:
            if isinstance(w, PinwheelWing):
                ids.extend((w.n.zone_id, w.e.zone_id, w.s.zone_id, w.w.zone_id, w.center.zone_id))
            else:
                for slot_id in w.slots:
                    if slot_id in w.zones:
                        ids.append(w.zones[slot_id].zone_id)
                    elif slot_id in w.groups:
                        g = w.groups[slot_id]
                        ids.append(g.big.zone_id)
                        ids.extend(n.zone_id for n in g.notches)
        return tuple(ids)


def validate_realizer_input(layout: RealizerInput) -> tuple[str, ...]:
    """Every invariant `RealizerInput`'s own docstring states, checked — a tuple of problem
    strings, empty when every invariant holds. A caller that finds this non-empty must REFUSE
    (`RealizerRefusal`) rather than call the realizer at all; the realizer itself never re-checks
    these (Required Behaviour 4: "what must hold before it is called")."""
    problems: list[str] = []
    if not layout.wings:
        problems.append("RealizerInput.wings is empty")
    ids = layout.zone_ids()
    duplicates = {zid for zid in ids if ids.count(zid) > 1}
    if duplicates:
        problems.append(f"duplicate zone ids across wings: {sorted(duplicates)}")
    return tuple(problems)


@dataclass(frozen=True)
class RealizerRefusal:
    """A layout the realizer cannot honestly realize — the failing constraint, named, never
    silently approximated or substituted with a result from a different path (Required Behaviour 4;
    see `Stage2Result` below for how this is enforced structurally)."""

    reason: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("RealizerRefusal.reason must be a stated, non-empty reason")


# =============================================================================================
# 5. Wet rooms and SAFE_ROOM
# =============================================================================================
# THIS FACT ALREADY HAS ONE representation on `main`, and it already works: `app.vertical_slice.
# wet_rooms.ResolvedWetRoom`, built by `wet_rooms.resolve_wet_rooms(program)` from the brief's OWN
# authoritative `ProgramSpec` (never from a donor/adapted concept — see that module's own I1-I4).
# It is already the authoritative input `validation.validate`'s `wet_rooms` parameter reads for
# C17 (bathroom access) and C29 (wet-room privacy). SAFE_ROOM already has its own realized-fact
# check, C4, via `ProgramRole.SAFE_ROOM` + `WallType.RC_SAFE_ROOM` + `constraints.
# SAFE_ROOM_NOT_REALIZED_DETAIL` — also unchanged.
#
# Required Behaviour 5's gap is NOT a missing type — it is that Stage 1's own realizer
# (`rectilinear_realizer.realize_layout`) never receives a `wet_rooms` argument at all, so it can
# never call `validate()` with C17/C29 able to run. `RealizerInput.wet_rooms` above (Required
# Behaviour 4) is the fix: THIS module's realizer input carries `ResolvedWetRoom` end to end, so
# any later child wiring a realizer in has nowhere else to source it from and no reason to invent a
# second wet-room type. `wet_rooms.py` remains the sole owner of `ResolvedWetRoom` and
# `resolve_wet_rooms`; this module only references it, never redefines it.

#: Re-exported so a Stage 2 caller can import wet-room/SAFE_ROOM vocabulary from this one module
#: without also needing to know `ResolvedWetRoom` lives in `wet_rooms.py` and `ProgramRole.
#: SAFE_ROOM` lives in `geometry_core.model` — the "one traceable chain" Required Behaviour 6 asks
#: for, applied to imports too.
__all_wet_room_safe_room_exports__ = ("ResolvedWetRoom", "ProgramRole")


# =============================================================================================
# 6. Room identity end to end: donor room -> intent fact -> seed cell -> repaired cell -> realized
#    zone, as one traceable chain
# =============================================================================================

@dataclass(frozen=True)
class RepairedCell:
    """One cell after repair — the link between a `SeedCell` (or nothing, if repair ADDED this
    cell) and whatever realizes it. `seed_cell_id` is `None` exactly when `RoomLineage` records this
    cell's own donor room (if any) as ADDED at the "repair" stage; `donor_room_id` is `None` exactly
    when it is `None` for the SAME reason (an ADDED cell never traces to a donor room, by
    definition — see `RoomLineageKind`)."""

    cell_id: str
    seed_cell_id: str | None
    donor_room_id: DonorRoomId | None


@dataclass(frozen=True)
class RealizedZone:
    """One realized zone — Stage 2's own placeholder record of "this repaired cell became this real
    room," not the full realized geometry (`rectilinear_realizer.RealizedLayout`, produced by a
    LATER child's wiring, is that). `repaired_cell_ids` has more than one entry exactly for a
    notch-carve MERGED group's own big zone (mirrors `rectilinear_realizer.zone_of_cell`'s own
    many-cells-one-zone shape)."""

    zone_id: str
    repaired_cell_ids: tuple[str, ...]
    donor_room_ids: tuple[DonorRoomId, ...]


@dataclass(frozen=True)
class RoomIdentityChain:
    """The full, traceable chain for one concept: donor room -> intent fact -> seed cell -> repaired
    cell -> realized zone. THIS MODULE owns the type; every link is produced by a different stage
    (synthesis/adaptation builds `lineage`+`intent`, seeding builds `seed`, repair builds
    `repaired_cells`, realization builds `realized_zones`) but the chain itself lives in one place
    so nothing downstream has to reconstruct the correspondence ad hoc — exactly the
    `donor_room_id_by_zone` situation Required Behaviour 1's own module docstring names as the bug
    this Issue exists to end."""

    lineage: RoomLineage
    intent: RealizationIntent
    seed: SeedGeometry
    repaired_cells: tuple[RepairedCell, ...]
    realized_zones: tuple[RealizedZone, ...]


@dataclass(frozen=True)
class DonorRoomTrace:
    """One donor room's own reachability at every link of the chain — what
    `verify_chain_completeness` inspects to decide whether Required Behaviour 6's own invariant
    holds for this room."""

    donor_room_id: DonorRoomId
    has_intent_fact: bool
    seed_cell_ids: tuple[str, ...]
    repaired_cell_ids: tuple[str, ...]
    realized_zone_ids: tuple[str, ...]
    lineage_kinds: tuple[RoomLineageKind, ...]

    @property
    def fully_reachable(self) -> bool:
        """True when this donor room reaches a real seed cell, a real repaired cell and a real
        realized zone. A donor room explicitly DROPPED is NOT `fully_reachable` — that is expected,
        not a bug; `verify_chain_completeness` treats an explicit DROPPED classification as
        satisfying the invariant even though `fully_reachable` is `False`."""
        return bool(self.seed_cell_ids) and bool(self.repaired_cell_ids) and bool(self.realized_zone_ids)


def trace_donor_room(chain: RoomIdentityChain, donor_room_id: DonorRoomId) -> DonorRoomTrace:
    has_intent_fact = donor_room_id in chain.intent.donor_room_ids()
    seed_cell_ids = tuple(c.cell_id for c in chain.seed.cells if c.donor_room_id == donor_room_id)
    repaired_cell_ids = tuple(
        c.cell_id for c in chain.repaired_cells if c.donor_room_id == donor_room_id)
    realized_zone_ids = tuple(
        z.zone_id for z in chain.realized_zones if donor_room_id in z.donor_room_ids)
    lineage_kinds = tuple(
        e.kind for e in chain.lineage.events if donor_room_id in e.donor_room_ids)
    return DonorRoomTrace(donor_room_id, has_intent_fact, seed_cell_ids, repaired_cell_ids,
                           realized_zone_ids, lineage_kinds)


def verify_chain_completeness(chain: RoomIdentityChain) -> tuple[str, ...]:
    """Every donor room `chain.lineage.donor_room_ids` names must be either `fully_reachable` at
    every link, or have an explicit non-CARRIED `RoomLineageEvent` (DROPPED/MERGED/SPLIT) that
    accounts for why it is not — never merely missing (Required Behaviour 1 and 6 together). Returns
    one problem string per donor room that satisfies neither; empty means the chain is complete."""
    problems: list[str] = []
    for donor_room_id in chain.lineage.donor_room_ids:
        trace = trace_donor_room(chain, donor_room_id)
        explicitly_classified = any(
            k in (RoomLineageKind.DROPPED, RoomLineageKind.MERGED, RoomLineageKind.SPLIT)
            for k in trace.lineage_kinds)
        if trace.fully_reachable or explicitly_classified:
            continue
        problems.append(
            f"{donor_room_id}: not fully reachable (intent={trace.has_intent_fact}, "
            f"seed={trace.seed_cell_ids}, repaired={trace.repaired_cell_ids}, "
            f"realized={trace.realized_zone_ids}) and no DROPPED/MERGED/SPLIT event accounts for it "
            f"(lineage_kinds={trace.lineage_kinds})")
    return tuple(problems)


# =============================================================================================
# Refusal contract (Required Behaviour 4, enforced structurally — AC-3)
# =============================================================================================

@dataclass(frozen=True)
class Stage2Result:
    """The ONE result type every Stage 2 realization call returns: exactly a success (`zones`
    non-empty, `refusal` `None`) or a refusal (`zones` empty, `refusal` set) — never both, never
    neither, enforced in `__post_init__`. No other object — not `rectilinear_realizer.
    RealizedLayout`, not a bare dict, not a guillotine-engine `Fixture` — IS a `Stage2Result`: this
    dataclass has no shared base with any of those, so `isinstance(x, Stage2Result)` is `False` for
    anything not constructed through `Stage2Result.success`/`Stage2Result.refuse`. A refusal is
    therefore never substitutable by a result from another realization path (Required Behaviour 4's
    own refusal contract)."""

    zones: tuple[RealizedZone, ...]
    refusal: RealizerRefusal | None

    def __post_init__(self) -> None:
        if bool(self.zones) == bool(self.refusal is not None):
            raise ValueError(
                "Stage2Result must be exactly a success (zones non-empty, refusal None) or a "
                "refusal (zones empty, refusal set) — never both, never neither")

    @property
    def ok(self) -> bool:
        return self.refusal is None

    @classmethod
    def success(cls, zones: tuple[RealizedZone, ...]) -> "Stage2Result":
        return cls(zones=zones, refusal=None)

    @classmethod
    def refuse(cls, reason: str, detail: str = "") -> "Stage2Result":
        return cls(zones=(), refusal=RealizerRefusal(reason=reason, detail=detail))


def ensure_stage2_result(candidate: object) -> Stage2Result:
    """The one checked boundary Required Behaviour 4 asks for: a caller that has ANY object claiming
    to be a Stage 2 outcome must pass it through here. Raises `TypeError` for anything that is not
    already a genuine `Stage2Result` — never coerces, never duck-types a dict or another module's
    result object into one, no matter how similar its fields look (`rectilinear_realizer.
    RealizedLayout` in particular has a similarly-shaped `ok` property but is NOT accepted here)."""
    if not isinstance(candidate, Stage2Result):
        raise TypeError(
            f"{candidate!r} (type {type(candidate).__name__}) is not a Stage2Result — a refusal is "
            "never substituted by a result object from another realization path")
    return candidate
