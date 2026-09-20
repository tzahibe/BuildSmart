"""ConceptSpec contract (Issue #75, Concept Engine v2 1/5).

Makes "topologically different" a deterministic, testable fact BEFORE any new concept is
generated. Three things, all metadata:

    CirculationClass          the parti a candidate belongs to (`ConceptCandidate.circulation_class`,
                              set explicitly by each builder — see `concept_generator.py`).
    realized_circulation_class the SAME classification, read off the SOLVED geometry (hall aspect,
                              door count and hall-room adjacency from `validation.realized_connections`,
                              wing count) — never inferred from the tree the builder used.
    topologically_distinct     a pure, deterministic comparison of two candidates' `ConceptSpec`s.

Nothing in `general_pipeline.py`'s selection, ranking or the shown set reads any of this (see each
module's own docstring) — this module only makes the fact available and checkable.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Sequence

from .geometry_core.engine import WallMap
from .geometry_core.model import Fixture, ProgramRole, Rect, u_to_m

if TYPE_CHECKING:
    from .doors import Door
    from .wet_rooms import ResolvedWetRoom


class CirculationClass(str, Enum):
    """How a house's circulation is organised — the tag every `ConceptCandidate` carries.

    `BRANCHED` and `RING` are not produced by any builder today (`concept_generator.py`,
    `l_parti.py`) — they exist so `realized_circulation_class` and `topologically_distinct` do not
    need to change the day a future planner path produces one; making the generator ever emit them
    is explicitly out of scope for this Issue.
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
    """

    circulation_class: CirculationClass
    zoning: ZoningSplit
    wet_core_groups: tuple[tuple[str, ...], ...]
    programme_reference: tuple[str, ...]
    outline_reference: tuple[int, ...]


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


def concept_spec_of(candidate) -> ConceptSpec:
    """The `ConceptSpec` for one `ConceptCandidate` — pure, derived entirely from fields the
    candidate already carries (`strategy`, `wet_rooms`, `wing_orders`, its fixture's zones)."""
    programme = tuple(sorted(z.zone_id for z in candidate.concept.fixture.zones))
    return ConceptSpec(
        circulation_class=candidate.circulation_class,
        zoning=zoning_of(candidate.strategy),
        wet_core_groups=_wet_core_groups(candidate.wet_rooms),
        programme_reference=programme,
        outline_reference=tuple(candidate.wing_orders),
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
