"""ConceptSpec contract (Issue #75, Concept Engine v2 1/5).

Makes "topologically different" a deterministic, testable fact BEFORE any new concept is
generated. Three things, all metadata:

    CirculationClass          the parti a candidate belongs to (`ConceptCandidate.circulation_class`,
                              set explicitly by each builder — see `concept_generator.py`).
    realized_circulation_class the SAME classification, read off the SOLVED geometry (hall aspect,
                              door count and hall-room adjacency from `validation.realized_connections`,
                              wing count) — never inferred from the tree the builder used.
    topologically_distinct     a pure, deterministic comparison of two candidates' `ConceptSpec`s.

Also carries two other non-authoritative inputs, both read-only metadata:

    circulation_style_of        maps a person's own stated preference (`spec.HouseConcept
                                .circulation_style`) onto this module's `CirculationClass` —
                                the SAME enum, never a duplicate vocabulary.
    ArchitectModelHints /
    apply_architect_hints       a HINT slot for `app.architect.gateway.ArchitectModelGateway`
                                output (zoning/relationships/circulation-style/entry-room guesses
                                from that separate subsystem). NEVER a source of truth and NEVER
                                used to determine geometry: `apply_architect_hints` only ATTACHES
                                a hint for the record, or DROPS AND REPORTS one that contradicts an
                                authoritative fact this module already decided — the same precedent
                                `app.architect.authoritative_merge.merge_authoritative_requirements`
                                sets for BuildSmart's own hard requirements winning over anything a
                                model returned.

Nothing in `general_pipeline.py`'s selection, ranking or the shown set reads any of this (see each
module's own docstring) — this module only makes the fact available and checkable.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Sequence

from .geometry_core.engine import WallMap
from .geometry_core.model import Fixture, ProgramRole, Rect, u_to_m
from .spec import CirculationStyle

if TYPE_CHECKING:
    from .doors import Door
    from .wet_rooms import ResolvedWetRoom


class CirculationClass(str, Enum):
    """How a house's circulation is organised — the tag every `ConceptCandidate` carries.

    `BRANCHED` is produced by `concept_compilers.compile_branched` (Issue #79) — a hand-authored
    two-hall tree, never by `concept_generator.py`'s own strategies. `RING` is not produced by any
    builder today — it exists so `realized_circulation_class` and `topologically_distinct` do not
    need to change the day a future planner path produces one; making the generator ever emit a
    RING plan is explicitly out of scope for this Issue.
    """

    SPINE = "SPINE"
    FRONT_BAND = "FRONT_BAND"
    HUB_LOBBY = "HUB_LOBBY"
    BRANCHED = "BRANCHED"
    RING = "RING"
    TWO_WING = "TWO_WING"


class ZoningSplit(str, Enum):
    """Where the public zone sits relative to circulation/private — independent of the class a
    HUB_LOBBY and a FRONT_BAND candidate are both `FRONT_REAR` (a full-width public band across
    the front); they are distinguished by `circulation_class`, not by this field."""

    #: Public and private are columns either side of the hall/spine (every SPINE allocation).
    SIDE_BY_SIDE = "SIDE_BY_SIDE"
    #: Public zones form a full-width band across the front; private rooms sit behind it.
    FRONT_REAR = "FRONT_REAR"
    #: The programme spans two safe wings meeting at a seam (the L parti).
    WRAPPED = "WRAPPED"


class WetCoreGrouping(str, Enum):
    """How a concept's wet rooms group relative to their host bedroom — the same coarse
    vocabulary `ConceptSpec.wet_core_strategy`/`_wet_core_strategy` already compute per candidate
    (kept as a separate enum here, additive only, so neither existing field's `str` type nor any
    caller of it changes)."""

    ALL_ENSUITE = "ALL_ENSUITE"
    ALL_SHARED = "ALL_SHARED"
    MIXED = "MIXED"
    NONE = "NONE"


class MasterPlacement(str, Enum):
    """Where the primary/master bedroom sits relative to the concept's own circulation —
    descriptive metadata for `references/index.json` entries and `concept_patterns.py` pattern
    records (Issue #77), not read by any generator today."""

    #: Foot band of a hub, entered from the hub the way `HUB_PRIVATE_WING` FR-3 places it
    #: (`specs/005-hub-private-wing/spec.md` §4).
    HUB_FOOT = "HUB_FOOT"
    #: At the end of a single spine corridor.
    WING_END = "WING_END"
    #: In its own wing, in a two-wing (L parti) or ring (courtyard) massing.
    OWN_WING = "OWN_WING"
    #: On its own storey in a multi-level concept.
    UPPER_LEVEL = "UPPER_LEVEL"


class EntranceSide(str, Enum):
    """Where the entrance sits relative to the concept's massing — descriptive metadata for
    `references/index.json` entries and `concept_patterns.py` pattern records (Issue #77), not
    read by any generator today."""

    #: Opens directly into the front/public zone.
    FRONT = "FRONT"
    #: Opens into a court formed by two wings meeting at a seam (the L parti's inner corner).
    ENTRY_COURT = "ENTRY_COURT"
    #: On a side elevation rather than the front (a corner plot, an angled/T-shaped envelope).
    SIDE = "SIDE"


#: `spec.CirculationStyle` (a PERSON's own stated preference on `HouseConcept`) -> `CirculationClass`
#: (this module's authoritative vocabulary) — mapped, never duplicated. `ENGINE` ("no preference
#: stated") has no class: `circulation_style_of` returns `None` for it, same as an unset field.
_CLASS_BY_CIRCULATION_STYLE: dict[CirculationStyle, CirculationClass] = {
    CirculationStyle.SPINE: CirculationClass.SPINE,
    CirculationStyle.FRONT_BAND: CirculationClass.FRONT_BAND,
    CirculationStyle.HUB: CirculationClass.HUB_LOBBY,
}


def circulation_style_of(style: CirculationStyle) -> CirculationClass | None:
    """The `CirculationClass` a person's `HouseConcept.circulation_style` preference names, or
    `None` for `CirculationStyle.ENGINE` (no preference — the engine decides)."""
    return _CLASS_BY_CIRCULATION_STYLE.get(style)


@dataclass(frozen=True)
class ArchitectModelHints:
    """Non-authoritative hints extracted from one `app.architect.gateway.ArchitectModelGateway`
    response (`app.architect.models.ArchitecturalSpec`) — see the module docstring. Every field is
    a GUESS from that separate subsystem, never a fact `app.vertical_slice` itself vouches for.

    `circulation_style_hint`: `"SPINE"` when the model's `Circulation.requires_hallway` is True,
    `"OPEN"` when False, `None` when the model returned no circulation opinion at all.
    `zoning_hint`: the model's own zone names (`Zone.name`), informational only.
    `relationship_hints`: `"{room_type_a}<->{room_type_b}"` per relationship the model proposed.
    `concept_hint`: the model's own entry-room type, as a free-form label.
    """

    circulation_style_hint: str | None
    zoning_hint: tuple[str, ...]
    relationship_hints: tuple[str, ...]
    concept_hint: str | None


def hints_from_architect_spec(spec) -> ArchitectModelHints:
    """`ArchitectModelHints` from an `app.architect.models.ArchitecturalSpec` — duck-typed against
    that shape (`.circulation`, `.zones`, `.relationships`) so this module never imports
    `app.architect.*` at runtime, the same discipline `quality_metrics.py` uses for `DemoDesign`:
    the Architect Model pipeline is a separate subsystem this Issue only interfaces with, not one
    `app.vertical_slice` depends on."""
    circulation = getattr(spec, "circulation", None)
    circulation_hint = None if circulation is None else ("SPINE" if circulation.requires_hallway
                                                          else "OPEN")
    zoning_hint = tuple(z.name for z in getattr(spec, "zones", ()))
    relationship_hints = tuple(f"{r.room_type_a}<->{r.room_type_b}"
                               for r in getattr(spec, "relationships", ()))
    concept_hint = None if circulation is None else circulation.entry_room_type
    return ArchitectModelHints(circulation_hint, zoning_hint, relationship_hints, concept_hint)


@dataclass(frozen=True)
class DroppedHint:
    """One `ArchitectModelHints` field `apply_architect_hints` refused to apply — named and
    explained, so a caller can report it rather than have it silently disappear."""

    field: str
    hinted_value: str
    authoritative_value: str
    reason: str


#: `ArchitectModelHints.circulation_style_hint` -> `CirculationClass`, when the hint is precise
#: enough to compare against one. `"OPEN"` deliberately maps to nothing: it rules out a corridor
#: but does not itself name FRONT_BAND vs HUB_LOBBY, so it is never grounds to drop anything.
_CLASS_BY_HINT: dict[str, CirculationClass] = {"SPINE": CirculationClass.SPINE}


def apply_architect_hints(concept_spec: ConceptSpec,
                          hints: ArchitectModelHints) -> tuple[ConceptSpec, tuple[DroppedHint, ...]]:
    """Attach `hints` to `concept_spec` for the record; DROP AND REPORT (never apply) any hint
    that contradicts an authoritative fact `concept_spec` already carries.

    `concept_spec`'s `circulation_class`/`zoning`/`wet_core_groups`/programme facts are NEVER
    changed by this function, hint or no hint — the same precedent
    `app.architect.authoritative_merge.merge_authoritative_requirements` sets for BuildSmart's own
    hard requirements always winning over anything a model returned: the fact BuildSmart (here,
    the concept builder) already decided is kept, and every dropped hint is reported so nothing
    silently disappears.
    """
    dropped: list[DroppedHint] = []
    hinted_class = _CLASS_BY_HINT.get(hints.circulation_style_hint or "")
    if hinted_class is not None and hinted_class != concept_spec.circulation_class:
        dropped.append(DroppedHint(
            field="circulation_class",
            hinted_value=hinted_class.value,
            authoritative_value=concept_spec.circulation_class.value,
            reason="the Architect Model's circulation hint contradicts the circulation_class "
                   "already decided by the builder that produced this candidate; the "
                   "authoritative value is kept, the hint is dropped"))
    return replace(concept_spec, architect_hints=hints), tuple(dropped)


@dataclass(frozen=True)
class ConceptSpec:
    """One candidate's topology, decided from the candidate alone — before Geometry Core ever
    solves it.

    `wet_core_groups` is the candidate's wet rooms partitioned BY HOST: an ensuite groups with its
    bedroom, every circulation-entered ("shared") wet room falls into one shared group — the
    pre-solve analogue of `wet_core.WetCore.clusters`'s realized wall-adjacency clustering, built
    here from `ResolvedWetRoom.host_zone` because a `ConceptSpec` exists before the fixture is
    solved and there is no realized wall to measure yet.

    `programme_reference` is every zone id the candidate's fixture declares, sorted — what
    programme this spec describes, without re-deriving it from `ConceptCandidate.strategy`.
    `outline_reference` is `ConceptCandidate.wing_orders` — which safe-geometry outline(s) the
    candidate was fit to.

    The remaining fields are additional descriptive metadata, all derived from data the candidate
    already carries pre-solve (never requiring realized geometry):
    `entrance_strategy` — the concept's own declared entrance zone id (`Concept.entrance_zone_id`);
    `wet_core_strategy` — `"ALL_ENSUITE"`/`"ALL_SHARED"`/`"MIXED"`/`"NONE"`, a coarse summary of
    `wet_core_groups`; `massing` — `"1W"`/`"2W"`, the wing count (`general_pipeline.massing_of`'s
    own value, not duplicated logic — see `concept_spec_of`); `relationships` — this candidate's
    own requested-relationship outcomes, `()` until a REALIZED plan attaches them (nothing does
    yet — see the module scope note); `family` — `general_pipeline._family_signature`'s value for
    this candidate, carried here rather than re-derived by every caller that wants it.
    `architect_hints` — see `ArchitectModelHints`; `None` until `apply_architect_hints` attaches
    one, and never a source of truth for anything above.
    """

    circulation_class: CirculationClass
    zoning: ZoningSplit
    wet_core_groups: tuple[tuple[str, ...], ...]
    programme_reference: tuple[str, ...]
    outline_reference: tuple[int, ...]
    entrance_strategy: str = ""
    wet_core_strategy: str = "NONE"
    massing: str = "1W"
    relationships: tuple[str, ...] = ()
    family: str | None = None
    architect_hints: ArchitectModelHints | None = None


#: `ConceptCandidate.strategy.value` -> `ZoningSplit`. Keyed by the string value (not the enum
#: itself) so this module never imports `concept_generator.ConceptStrategy` — that module imports
#: `CirculationClass` from here, and the two are leaf/consumer, not peers.
_ZONING_BY_STRATEGY_VALUE: dict[str, ZoningSplit] = {
    "SPINE_PUBLIC_PRIVATE": ZoningSplit.SIDE_BY_SIDE,
    "SPINE_DOUBLE_LOADED": ZoningSplit.SIDE_BY_SIDE,
    "SPINE_SERVICE_CLUSTER": ZoningSplit.SIDE_BY_SIDE,
    "BRANCHED_TWO_STACK": ZoningSplit.SIDE_BY_SIDE,
    "FRONT_PUBLIC_BAND": ZoningSplit.FRONT_REAR,
    "HUB_PRIVATE_WING": ZoningSplit.FRONT_REAR,
    "MULTI_WING_SPLIT": ZoningSplit.WRAPPED,
}


def zoning_of(strategy) -> ZoningSplit:
    """The `ZoningSplit` a `ConceptCandidate.strategy` implies. Raises on an unrecognised
    strategy rather than guessing — every strategy `concept_generator.py`/`l_parti.py` can produce
    today is listed above; a new one must be classified here explicitly, not silently defaulted."""
    value = getattr(strategy, "value", strategy)
    try:
        return _ZONING_BY_STRATEGY_VALUE[value]
    except KeyError:
        raise ValueError(f"no ZoningSplit mapped for concept strategy {value!r}") from None


def _wet_core_groups(wet_rooms: Sequence["ResolvedWetRoom"]) -> tuple[tuple[str, ...], ...]:
    """Wet-room zone ids partitioned by host — see `ConceptSpec.wet_core_groups`."""
    by_host: dict[str, list[str]] = {}
    for room in wet_rooms:
        key = room.host_zone if room.host_zone is not None else ""
        by_host.setdefault(key, []).append(room.zone_id)
    return tuple(sorted(tuple(sorted(group)) for group in by_host.values()))


def _wet_core_strategy(wet_rooms: Sequence["ResolvedWetRoom"]) -> str:
    """A coarse label for `ConceptSpec.wet_core_strategy` — see that field's docstring."""
    if not wet_rooms:
        return "NONE"
    hosted = [r for r in wet_rooms if r.host_zone is not None]
    if len(hosted) == len(wet_rooms):
        return "ALL_ENSUITE"
    if not hosted:
        return "ALL_SHARED"
    return "MIXED"


def concept_spec_of(candidate) -> ConceptSpec:
    """The `ConceptSpec` for one `ConceptCandidate` — pure, derived entirely from fields the
    candidate already carries (`strategy`, `wet_rooms`, `wing_orders`, its fixture's zones)."""
    # Local import: `general_pipeline.py` imports this module at load time (`RealizedPlan
    # .circulation_class`); a module-level import here would cycle back to a partially
    # initialised `general_pipeline`. Deferred to call time, mirroring `realized_circulation_class`
    # 's own `validation` import below.
    from . import general_pipeline as gp

    programme = tuple(sorted(z.zone_id for z in candidate.concept.fixture.zones))
    return ConceptSpec(
        circulation_class=candidate.circulation_class,
        zoning=zoning_of(candidate.strategy),
        wet_core_groups=_wet_core_groups(candidate.wet_rooms),
        programme_reference=programme,
        outline_reference=tuple(candidate.wing_orders),
        entrance_strategy=candidate.concept.entrance_zone_id,
        wet_core_strategy=_wet_core_strategy(candidate.wet_rooms),
        massing=f"{len(candidate.concept.fixture.wings)}W",
        family=gp._family_signature(candidate.concept.fixture, candidate.strategy),
    )


def topologically_distinct(a: ConceptSpec, b: ConceptSpec) -> bool:
    """Whether two candidates read as topologically DIFFERENT houses.

    Pure and deterministic: compares exactly (`circulation_class`, `zoning`, `wet_core_groups`) —
    dimensions, room ids and rationale text never enter the comparison, so two candidates that
    differ only in proportions (a "relabeling") come back NOT distinct. Tie rule: equal on all
    three -> not distinct; different on any one -> distinct.
    """
    return ((a.circulation_class, a.zoning, a.wet_core_groups)
            != (b.circulation_class, b.zoning, b.wet_core_groups))


#: A hall at or under this long/short ratio reads as a compact lobby rather than a spine — the
#: same threshold `quality_metrics.COMPACT_HALL_ASPECT_MAX` and `concept_generator.HUB_TEMPLATE`'s
#: own `max_aspect_ratio` (1.5) already use for exactly this judgement.
_COMPACT_HALL_ASPECT_MAX = 1.5

#: A room lobby's own quality gate targets 4-7 doors onto it (measured against 21 professional
#: plans — `docs/wiki/architecture/geometry-validation.md`); a spine hall's doors are almost
#: always fewer, so 4 separates the two without ever being reached by a two/three-room spine hall.
_HUB_DOOR_COUNT_MIN = 4

#: A public zone whose combined bounding-box width reaches this share of the footprint's width
#: reads as a full-width band across the front; a SPINE candidate's public zone is confined to one
#: column (never above roughly half the footprint width, by construction — see `_allocations`).
_FRONT_BAND_WIDTH_RATIO = 0.85

_PUBLIC_ROLES = frozenset({ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN})
_HALL_ROLES = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})


def realized_circulation_class(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                               interior_doors: "list[Door]") -> CirculationClass:
    """Classify a REALIZED plan from its own geometry — never from the tree/strategy that built
    it. See the module docstring for the three facts this reads and why each threshold is set
    where it is."""
    # Local import: `validation.py` imports `concept_generator.py` (ROOM_TEMPLATES), which imports
    # `CirculationClass` from this module — a module-level import here would cycle back to a
    # partially-initialised `concept_generator`. Deferred to call time, where every module is
    # already loaded.
    from . import validation as validation_module

    if len(fixture.wings) > 1:
        return CirculationClass.TWO_WING

    hall_ids = {z.zone_id for z in fixture.zones if _HALL_ROLES & set(z.roles)}
    hall_rects = [rects[h] for h in hall_ids if h in rects]

    # BRANCHED (Issue #79): two HALL/CIRCULATION zones, in one wing, that are themselves directly
    # connected — the generator-level compilers this Issue adds are the first to ever produce this
    # (`concept_compilers.compile_branched`): two hall LEAVES in adjacent, non-sibling subtrees,
    # joined by a declared CASED_OPENING edge (never an OPEN_CONNECTION — `_mark_open_interfaces`
    # requires the group's leaves to be one subtree with a FULL matching edge, which a genuinely
    # bent corridor never has). Checked before HUB_LOBBY/FRONT_BAND/SPINE below: a two-hall
    # fixture with no direct hall-to-hall connection falls through to those, unchanged.
    if len(hall_ids) >= 2:
        connections = validation_module.realized_connections(rects, walls, interior_doors)
        if any((c.a in hall_ids and c.b in hall_ids) for c in connections):
            return CirculationClass.BRANCHED

    if hall_rects:
        connections = validation_module.realized_connections(rects, walls, interior_doors)
        hall_door_count = sum(
            1 for c in connections
            if c.kind == "DOOR" and (c.a in hall_ids or c.b in hall_ids))
        aspects = []
        for r in hall_rects:
            w_m, h_m = u_to_m(r.w), u_to_m(r.h)
            aspects.append(max(w_m, h_m) / max(min(w_m, h_m), 1e-6))
        hall_aspect_median = statistics.median(aspects)
        if hall_aspect_median <= _COMPACT_HALL_ASPECT_MAX and hall_door_count >= _HUB_DOOR_COUNT_MIN:
            return CirculationClass.HUB_LOBBY

    public_ids = [z.zone_id for z in fixture.zones if _PUBLIC_ROLES & set(z.roles)]
    public_rects = [rects[z] for z in public_ids if z in rects]
    if public_rects:
        footprint_w_u = fixture.wings[0].w_u
        band_w_u = max(r.x + r.w for r in public_rects) - min(r.x for r in public_rects)
        if footprint_w_u and band_w_u >= _FRONT_BAND_WIDTH_RATIO * footprint_w_u:
            return CirculationClass.FRONT_BAND

    return CirculationClass.SPINE


@dataclass(frozen=True)
class ClassMismatch:
    """`verify_class`'s answer when a candidate's declared class and its realized class disagree."""

    expected: CirculationClass
    realized: CirculationClass


def verify_class(candidate, plan) -> ClassMismatch | None:
    """Whether `candidate.circulation_class` matches `plan.circulation_class` (the same fact,
    recomputed from the realized geometry at the point `plan` — a `general_pipeline.RealizedPlan`
    — was built). `None` on agreement."""
    if candidate.circulation_class == plan.circulation_class:
        return None
    return ClassMismatch(expected=candidate.circulation_class, realized=plan.circulation_class)
