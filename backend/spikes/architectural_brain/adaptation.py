"""``adapt(concept, brief, site) -> AdaptedConcept | Rejection``: semantic/topological operations
on a synthesized ``ConceptSpec``'s ``baseline_rooms`` (the primary donor reference's own rooms) --
never a single global scale factor. Every operation is recorded as an ``Adaptation``.

Operations implemented (see AC-3 -- "records >= 1 semantic operation per adapted concept", not
every operation the Issue names is required per candidate):

- ``RESIZE_ROOMS`` (always applied): each room type's TOTAL area across the donor's own rooms of
  that type is anchored to a fixed per-TYPE target (``TARGET_AREA_M2`` below), but each individual
  room's own SHARE of that total carries the donor's own proportion forward (``room.area_m2 /``
  the donor's own mean area for that type) rather than collapsing every room of one type to the
  same constant. Two donors whose rooms of one type are sized differently relative to each other
  (e.g. one donor's two bedrooms are near-equal, another's are skewed) therefore adapt to
  DIFFERENT individual room areas even when both target the SAME aggregate per type -- this is
  what makes two different donors realize to genuinely different geometry within one topology
  (Issue #96's own finding: before this, ``RESIZE_ROOMS`` discarded every donor's own proportions,
  so two different donors with the same brief-authoritative room types/counts adapted to
  byte-identical room lists and realized to identical geometry). The aggregate-per-type ratio is
  still non-uniform across types BY CONSTRUCTION (each type's own donor-mean differs from its own
  fixed target by a different relative amount) -- this is what "changes room-area ratios
  non-uniformly, no global scaling" means and how ``test_adaptation.py`` verifies it.
- ``BEDROOM_COUNT_ADJUST`` (when the donor's bedroom count differs from ``brief.program.bedrooms``):
  adds or removes bedroom-type rooms at the fixed target area, preserving every other room.
- ``WET_ZONE_ADJUST`` (when the brief asks for an ensuite but the donor's ``wet_core_strategy`` is
  ``"CLUSTERED"`` -- all wet rooms in one block, not attached to a bedroom): relabels the adapted
  concept's wet-core strategy to ``"MIXED"`` (one wet room detached to become an ensuite) rather
  than leaving a strategy that cannot host what the brief asked for.

REJECTION (``Rejection``, never a crash, never a silently-wrong plan):

- the site's buildable area (``PlotSpec.buildable_size_m()``) is smaller than the summed MINIMUM
  area of every authoritative room the brief requires (``MIN_AREA_M2`` below) -- "no place for the
  SAFE_ROOM" and every other authoritative room generalises to this one measurable check.
- the brief requires an ENSUITE wet room but the donor concept's ``wet_core_strategy`` is
  ``"UNKNOWN"`` (the donor reference had zero measurable wet rooms at all -- no placement evidence
  exists to adapt an ensuite relationship from) -- "wet core unreachable".
"""
from __future__ import annotations

from dataclasses import dataclass

from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.synthesis import ConceptSpec

from app.vertical_slice.spec import PlotSpec

#: Fixed per-type target areas this POC adapts toward -- a semantic decision (each room type has
#: its own architecturally sensible size), never a multiplier on the donor's own area. Deliberately
#: this spike's own numbers (not imported from app/architect/gateway.py's TARGET_AREA_M2) so this
#: package has no runtime dependency on that module's placeholder values changing independently.
TARGET_AREA_M2: dict[str, float] = {
    "BEDROOM": 12.0,
    "MASTER_BEDROOM": 16.0,
    "LIVING": 24.0,
    "DINING": 10.0,
    "KITCHEN": 10.0,
    "FAMILY_ROOM": 14.0,
    "BATHROOM": 5.0,
    "TOILET": 2.5,
    "SAFE_ROOM": 9.0,
    "STORAGE": 3.0,
    "STAIRWELL": 4.0,
    "CIRCULATION": 4.0,
}

#: Hard floors used only for the rejection feasibility check -- "no place for the SAFE_ROOM" made
#: measurable: the site must have room for at least this much of every authoritative room type.
MIN_AREA_M2: dict[str, float] = {
    "BEDROOM": 9.0,
    "LIVING": 14.0,
    "KITCHEN": 6.0,
    "BATHROOM": 3.5,
    "TOILET": 1.5,
    "SAFE_ROOM": 9.0,
}


@dataclass(frozen=True)
class AdaptedRoom:
    id: str
    room_type: str
    area_m2: float


@dataclass(frozen=True)
class Adaptation:
    kind: str
    before: str
    after: str
    reason: str


@dataclass(frozen=True)
class AdaptedConcept:
    concept_id: str
    rooms: tuple[AdaptedRoom, ...]
    wet_core_strategy: str
    adaptations: tuple[Adaptation, ...]


@dataclass(frozen=True)
class Rejection:
    concept_id: str
    reason: str


def room_area_ratios(adapted: AdaptedConcept, concept: ConceptSpec) -> dict[str, float]:
    """adapted-area / baseline-area per room TYPE present in both -- what a caller (or a test)
    reads to confirm an adaptation changed ratios non-uniformly, i.e. is not a global scale."""
    baseline_by_type: dict[str, float] = {}
    for room in concept.baseline_rooms:
        baseline_by_type[room.type] = baseline_by_type.get(room.type, 0.0) + room.area_m2
    adapted_by_type: dict[str, float] = {}
    for room in adapted.rooms:
        adapted_by_type[room.room_type] = adapted_by_type.get(room.room_type, 0.0) + room.area_m2
    return {
        t: adapted_by_type[t] / baseline_by_type[t]
        for t in adapted_by_type
        if t in baseline_by_type and baseline_by_type[t] > 1e-9
    }


def _feasibility_rejection(concept: ConceptSpec, brief: Brief, site: PlotSpec) -> Rejection | None:
    site_w, site_h = site.buildable_size_m()
    buildable_area = site_w * site_h
    if buildable_area <= 0:
        return Rejection(concept.concept_id,
                         f"site has no buildable area after setbacks ({site_w:.1f}m x {site_h:.1f}m)")

    program = brief.program
    required = program.bedrooms * MIN_AREA_M2["BEDROOM"] + MIN_AREA_M2["LIVING"] + MIN_AREA_M2["KITCHEN"]
    required += program.wet_rooms * MIN_AREA_M2["BATHROOM"]
    if program.safe_room:
        required += MIN_AREA_M2["SAFE_ROOM"]
    if buildable_area < required:
        return Rejection(
            concept.concept_id,
            f"insufficient buildable area for the brief's authoritative rooms: required "
            f"{required:.1f} m2, buildable {buildable_area:.1f} m2")

    ensuite_requested = any(k.kind.value == "ensuite" for k in program.wet_room_kinds)
    if ensuite_requested and concept.wet_core_strategy == "UNKNOWN":
        return Rejection(
            concept.concept_id,
            "wet core unreachable: the donor concept has no measured wet-room placement "
            "(wet_core_strategy=UNKNOWN) to adapt an ensuite relationship from")

    return None


def _resize_rooms(concept: ConceptSpec) -> tuple[tuple[AdaptedRoom, ...], Adaptation]:
    before_total = sum(r.area_m2 for r in concept.baseline_rooms)

    # This donor's OWN mean area per room type -- the anchor `proportion` below is measured
    # against, so a type with only one donor room always gets proportion=1.0 (nothing to be
    # proportionate TO), while a type with several donor rooms of different sizes carries their
    # OWN relative spread forward into the adapted areas.
    type_totals: dict[str, float] = {}
    type_counts: dict[str, int] = {}
    for room in concept.baseline_rooms:
        type_totals[room.type] = type_totals.get(room.type, 0.0) + room.area_m2
        type_counts[room.type] = type_counts.get(room.type, 0) + 1
    type_mean = {t: type_totals[t] / type_counts[t] for t in type_totals}

    adapted: list[AdaptedRoom] = []
    for room in concept.baseline_rooms:
        target = TARGET_AREA_M2.get(room.type, room.area_m2)
        mean_for_type = type_mean.get(room.type, room.area_m2)
        proportion = room.area_m2 / mean_for_type if mean_for_type > 1e-9 else 1.0
        adapted.append(AdaptedRoom(id=room.id, room_type=room.type, area_m2=target * proportion))
    after_total = sum(r.area_m2 for r in adapted)
    adaptation = Adaptation(
        kind="RESIZE_ROOMS",
        before=f"total {before_total:.1f} m2 across {len(concept.baseline_rooms)} donor rooms",
        after=f"total {after_total:.1f} m2 after per-type target resizing",
        reason="each room type's aggregate resized to its own architectural target area, "
              "independently -- never a single scale factor applied to every room -- and each "
              "individual room's OWN share of that aggregate carries the donor's own proportion "
              "forward, so a different donor with a different internal size spread adapts to "
              "different individual room areas even at the same aggregate target")
    return tuple(adapted), adaptation


def _adjust_bedroom_count(rooms: tuple[AdaptedRoom, ...],
                          brief: Brief) -> tuple[tuple[AdaptedRoom, ...], Adaptation | None]:
    bedroom_types = ("BEDROOM", "MASTER_BEDROOM")
    current = [r for r in rooms if r.room_type in bedroom_types]
    other = [r for r in rooms if r.room_type not in bedroom_types]
    target_count = brief.program.bedrooms
    if len(current) == target_count:
        return rooms, None
    if len(current) < target_count:
        added = [
            AdaptedRoom(id=f"BEDROOM_ADAPTED_{i}", room_type="BEDROOM",
                       area_m2=TARGET_AREA_M2["BEDROOM"])
            for i in range(target_count - len(current))
        ]
        new_rooms = tuple(other + current + added)
        adaptation = Adaptation(
            kind="BEDROOM_COUNT_ADJUST",
            before=f"{len(current)} bedroom(s)", after=f"{target_count} bedroom(s)",
            reason=f"brief requires {target_count} bedroom(s); added "
                  f"{target_count - len(current)} to match, each at its own target area")
        return new_rooms, adaptation
    keep = sorted(current, key=lambda r: r.id)[:target_count]
    new_rooms = tuple(other + keep)
    adaptation = Adaptation(
        kind="BEDROOM_COUNT_ADJUST",
        before=f"{len(current)} bedroom(s)", after=f"{target_count} bedroom(s)",
        reason=f"brief requires {target_count} bedroom(s); removed "
              f"{len(current) - target_count} node(s) to match")
    return new_rooms, adaptation


def _adjust_wet_zone(concept: ConceptSpec, brief: Brief) -> tuple[str, Adaptation | None]:
    ensuite_requested = any(k.kind.value == "ensuite" for k in brief.program.wet_room_kinds)
    if ensuite_requested and concept.wet_core_strategy == "CLUSTERED":
        adaptation = Adaptation(
            kind="WET_ZONE_ADJUST",
            before="CLUSTERED (all wet rooms in one block, none bedroom-hosted)",
            after="MIXED (one wet room detached to host as an ensuite)",
            reason="brief requires an ensuite; the donor's wet rooms were all clustered together "
                  "with no bedroom relationship to adapt, so one is moved to host a bedroom "
                  "instead of leaving a strategy the brief's requirement cannot be met by")
        return "MIXED", adaptation
    return concept.wet_core_strategy, None


def adapt(concept: ConceptSpec, brief: Brief, site: PlotSpec) -> AdaptedConcept | Rejection:
    rejection = _feasibility_rejection(concept, brief, site)
    if rejection is not None:
        return rejection

    rooms, resize_adaptation = _resize_rooms(concept)
    adaptations = [resize_adaptation]

    rooms, bedroom_adaptation = _adjust_bedroom_count(rooms, brief)
    if bedroom_adaptation is not None:
        adaptations.append(bedroom_adaptation)

    wet_core_strategy, wet_adaptation = _adjust_wet_zone(concept, brief)
    if wet_adaptation is not None:
        adaptations.append(wet_adaptation)

    return AdaptedConcept(
        concept_id=concept.concept_id,
        rooms=rooms,
        wet_core_strategy=wet_core_strategy,
        adaptations=tuple(adaptations),
    )
