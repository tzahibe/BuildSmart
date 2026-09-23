"""Stage 2 (B/2), Issue #134 — building a `contract.RealizationIntent` from one donor plan.

Adapted from POC Issue #109's own `spikes/architectural_brain/realization_intent.py::intent_from`
(not merged to `main`, not importable — transcribed, not imported, per `docs/stage2/CONTRACT.md`'s
own precedent), simplified to take a `donor.DonorPlan` directly rather than a `ConceptSpec`/`Brief`
pair: Stage 2 "seeds, does not search" (Required Behaviour 1) — there is no synthesized concept
between the donor and this intent, the donor's OWN room roster IS `baseline_rooms`. Every field
below is either a direct copy of a fact `DonorPlan` states or the SAME deterministic, documented
geometric derivation #109's own module already used (`_relative_placement_for`'s FRONT/REAR/LEFT/
RIGHT/ABOVE/BELOW rule, `_room_proportions`'s donor-mean anchor, `_footprint_relationships`'s
fill-ratio) — never an invented value.
"""
from __future__ import annotations

import warnings
from collections import defaultdict

from shapely.geometry import Polygon

from .contract import (
    AccessFact,
    AdjacencyFact,
    Clusters,
    EntranceRelationship,
    ExposureFact,
    FootprintRelationships,
    RealizationIntent,
    RelativePlacement,
    RoomProportion,
)
from .donor import DonorPlan

SCHEMA_VERSION = "1.0"

#: Mirrors `spikes/architectural_brain/patterns.py`'s own vocabulary (transcribed, same values).
PUBLIC_TYPES = frozenset({"LIVING", "DINING", "KITCHEN", "FAMILY_ROOM"})
PRIVATE_TYPES = frozenset({"BEDROOM", "MASTER_BEDROOM", "STUDY", "DRESSING_ROOM"})
WET_TYPES = frozenset({"BATHROOM", "TOILET"})

_AXIS_EPS = 1e-6
UNKNOWN = "UNKNOWN"


def _connected_components(ids: list[str], edges: set[frozenset[str]]) -> list[set[str]]:
    """Transcribed from `patterns._connected_components` (same algorithm, same tie-breaking)."""
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        a, b = tuple(e)
        if a in ids and b in ids:
            adj[a].add(b)
            adj[b].add(a)
    seen: set[str] = set()
    components: list[set[str]] = []
    for start in ids:
        if start in seen:
            continue
        comp = {start}
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            for nb in adj[node]:
                if nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    stack.append(nb)
        components.append(comp)
    return components


def _minimum_rotated_rectangle(poly: Polygon) -> Polygon:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return poly.minimum_rotated_rectangle


def _relative_placement_for(room_id: str, centroid: tuple[float, float],
                             center: tuple[float, float], entrance_side: str) -> RelativePlacement:
    """Transcribed verbatim from `realization_intent._relative_placement_for` (Issue #109)."""
    dx = centroid[0] - center[0]
    dy = centroid[1] - center[1]

    def label(delta: float, near: str, far: str) -> str:
        if abs(delta) < _AXIS_EPS:
            return UNKNOWN
        return near if delta < 0 else far

    if entrance_side in ("N", "S"):
        front_near, front_far = ("FRONT", "REAR") if entrance_side == "N" else ("REAR", "FRONT")
        primary = label(dy, front_near, front_far)
        secondary = label(dx, "LEFT", "RIGHT")
    elif entrance_side in ("E", "W"):
        front_near, front_far = ("REAR", "FRONT") if entrance_side == "E" else ("FRONT", "REAR")
        primary = label(dx, front_near, front_far)
        secondary = label(dy, "ABOVE", "BELOW")
    else:
        primary = label(dy, "ABOVE", "BELOW")
        secondary = label(dx, "LEFT", "RIGHT")

    return RelativePlacement(room_id=room_id, primary_axis=primary, secondary_axis=secondary)


def _footprint_relationships(donor: DonorPlan) -> FootprintRelationships:
    poly = Polygon(donor.footprint_m)
    minx, miny, maxx, maxy = poly.bounds
    width_m, depth_m = maxx - minx, maxy - miny
    aspect_ratio = (max(width_m, depth_m) / min(width_m, depth_m)
                    if min(width_m, depth_m) > _AXIS_EPS else None)
    mrr_area = _minimum_rotated_rectangle(poly).area
    fill_ratio = poly.area / mrr_area if mrr_area > _AXIS_EPS else None
    return FootprintRelationships(width_m=width_m, depth_m=depth_m,
                                   aspect_ratio=aspect_ratio, fill_ratio=fill_ratio)


def _room_proportions(donor: DonorPlan) -> tuple[RoomProportion, ...]:
    type_totals: dict[str, float] = {}
    type_counts: dict[str, int] = {}
    for room in donor.rooms:
        type_totals[room.type] = type_totals.get(room.type, 0.0) + room.area_m2
        type_counts[room.type] = type_counts.get(room.type, 0) + 1
    type_mean = {t: type_totals[t] / type_counts[t] for t in type_totals}

    proportions = []
    for room in donor.rooms:
        aspect_ratio = room.width_m / room.depth_m if room.depth_m > _AXIS_EPS else None
        mean_for_type = type_mean.get(room.type, room.area_m2)
        area_share = room.area_m2 / mean_for_type if mean_for_type > _AXIS_EPS else 1.0
        proportions.append(RoomProportion(room_id=room.id, room_type=room.type,
                                           aspect_ratio=aspect_ratio, area_share_of_type=area_share))
    return tuple(proportions)


def _wet_core_groups(donor: DonorPlan) -> tuple[tuple[str, ...], ...]:
    wet_ids = [r.id for r in donor.rooms if r.type in WET_TYPES]
    if not wet_ids:
        return ()
    adjacency = {frozenset((a, b)) for a, b in donor.adjacency_edges}
    components = _connected_components(wet_ids, adjacency)
    groups = [tuple(sorted(c)) for c in components]
    return tuple(sorted(groups, key=lambda g: g[0]))


def _circulation_nodes(donor: DonorPlan):
    from .contract import CirculationNode
    access: dict[str, set[str]] = {}
    for a, b, _kind in donor.access_edges:
        access.setdefault(a, set()).add(b)
        access.setdefault(b, set()).add(a)
    nodes = []
    for room in donor.rooms:
        if room.type != "CIRCULATION":
            continue
        served = tuple(sorted(access.get(room.id, set())))
        nodes.append(CirculationNode(room_id=room.id, serves=served))
    return tuple(nodes)


def build_realization_intent(donor: DonorPlan, concept_id: str) -> RealizationIntent:
    """One `RealizationIntent` per donor plan, unconditionally — every donor room gets a
    `RoomProportion` regardless of what adaptation/repair later does to it (mirrors #109's own
    `_room_proportions`), so `intent.donor_room_ids()` is the intent's own complete donor-room
    roster independent of any later CARRIED/DROPPED/ADDED decision."""
    footprint_poly = Polygon(donor.footprint_m)
    fminx, fminy, fmaxx, fmaxy = footprint_poly.bounds
    center = ((fminx + fmaxx) / 2.0, (fminy + fmaxy) / 2.0)
    entrance_side = donor.entrance_side

    placements = tuple(
        _relative_placement_for(room.id, room.centroid_m, center, entrance_side)
        for room in donor.rooms
    )
    exposures = tuple(
        ExposureFact(room_id=room.id,
                     sides=room.exterior_exposure if room.exposure_known else (),
                     known=room.exposure_known)
        for room in donor.rooms
    )
    clusters = Clusters(
        public=tuple(sorted(r.id for r in donor.rooms if r.type in PUBLIC_TYPES)),
        private=tuple(sorted(r.id for r in donor.rooms if r.type in PRIVATE_TYPES)),
    )

    return RealizationIntent(
        schema_version=SCHEMA_VERSION,
        source_plan_id=donor.plan_id,
        concept_id=concept_id,
        adjacency_edges=tuple(AdjacencyFact(a, b) for a, b in donor.adjacency_edges),
        access_edges=tuple(AccessFact(a, b, kind) for a, b, kind in donor.access_edges),
        exterior_exposure=exposures,
        relative_placement=placements,
        public_private_clusters=clusters,
        circulation_nodes=_circulation_nodes(donor),
        wet_core_groups=_wet_core_groups(donor),
        entrance_relationship=EntranceRelationship(room_id=donor.entrance_room_id, side=entrance_side),
        room_proportions=_room_proportions(donor),
        footprint_relationships=_footprint_relationships(donor),
    )
