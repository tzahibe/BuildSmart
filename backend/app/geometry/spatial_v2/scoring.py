"""Architectural quality scoring (SPATIAL_V2 Phase 3). Every component is independently computed
and reported -- `ArchitecturalScore.components` is a plain dict, never collapsed into one opaque
number without also exposing what it's made of (Phase 3's explicit requirement).

Reuses existing, unmodified Spatial V1 / production functions wherever the underlying geometric
fact is already computed correctly there: `_shared_edge_length`, `_group_by_type`,
`_touches_perimeter` (app.geometry.solver) and `compute_quality_metrics` (app.geometry.quality).
Nothing here re-derives room touching/overlap/area from scratch.
"""
from dataclasses import dataclass, field

from app.architect.models import ArchitecturalSpec
from app.geometry.models import BuildingFootprintSpec, RoomInstance
from app.geometry.quality import compute_quality_metrics
from app.geometry.solver import _group_by_type, _shared_edge_length, _touches_perimeter
from app.geometry.spatial_v2.intent import (
    EXTERIOR_PREFERRED_ROOM_TYPES,
    GENERIC_ADJACENCY_PREFERENCES,
    Zone,
    zone_by_room_type,
)

# Weights: rewards are added, penalties are subtracted -- all named, all inspectable, none hidden
# inside a formula. Not fitted per-scenario; chosen so no single term can dominate the total by
# construction (every term is pre-normalized to roughly a 0..1 range before weighting).
W_ADJACENCY = 2.0
W_ZONING = 2.0
W_CIRCULATION = 1.0
W_COMPACTNESS = 1.0
W_BALANCE = 1.5
W_UTILIZATION = 1.0
W_EXTERIOR = 1.5
W_CORRIDOR_PENALTY = 1.5
W_STRIP_PENALTY = 2.0
W_PRIVACY_PENALTY = 1.5
W_DEAD_SPACE_PENALTY = 1.0

_STRIP_ASPECT_THRESHOLD = 1.8  # beyond this bounding-box aspect ratio, a layout reads as a "strip"
_CORRIDOR_AREA_RATIO_CEILING = 0.15  # corridor area beyond 15% of programmed area is inefficient


@dataclass(frozen=True)
class ArchitecturalScore:
    total_score: float
    components: dict[str, float] = field(default_factory=dict)


def _adjacency_score(placed: list[RoomInstance], by_type: dict[str, list[RoomInstance]]) -> float:
    """Generic adjacency-preference satisfaction, normalized to [0, 1] by the total possible
    weight magnitude so it's comparable across programs of any size."""
    if not GENERIC_ADJACENCY_PREFERENCES:
        return 1.0
    raw = 0.0
    total_weight = 0.0
    for pref in GENERIC_ADJACENCY_PREFERENCES:
        a_list = by_type.get(pref.room_type_a, [])
        b_list = by_type.get(pref.room_type_b, [])
        if not a_list or not b_list:
            continue
        touching = any(
            _shared_edge_length(a, b) > 1e-6
            for a in a_list for b in b_list if a.id != b.id
        )
        total_weight += abs(pref.weight)
        if pref.weight > 0:
            raw += pref.weight if touching else 0.0
        else:
            raw += pref.weight if touching else -pref.weight  # reward AVOIDING a discouraged pair
    if total_weight == 0:
        return 1.0
    return max(0.0, min(1.0, (raw / total_weight + 1.0) / 2.0 if raw < 0 else raw / total_weight))


def _zoning_score(zones: dict[str, Zone], by_type: dict[str, list[RoomInstance]]) -> float:
    """Fraction of same-zone room-instance pairs (within PUBLIC/PRIVATE/SERVICE zones only --
    CIRCULATION/OUTDOOR are excluded, since those room types are expected to interface with every
    zone rather than cluster with each other) that ended up adjacent."""
    cohesive_zones = {Zone.PUBLIC, Zone.PRIVATE, Zone.SERVICE}
    instances_by_zone: dict[Zone, list[RoomInstance]] = {}
    for room_type, instances in by_type.items():
        zone = zones.get(room_type)
        if zone in cohesive_zones:
            instances_by_zone.setdefault(zone, []).extend(instances)

    total_pairs = 0
    adjacent_pairs = 0
    for instances in instances_by_zone.values():
        for i in range(len(instances)):
            for j in range(i + 1, len(instances)):
                total_pairs += 1
                if _shared_edge_length(instances[i], instances[j]) > 1e-6:
                    adjacent_pairs += 1
    if total_pairs == 0:
        return 1.0
    return adjacent_pairs / total_pairs


def _circulation_score(zones: dict[str, Zone], by_type: dict[str, list[RoomInstance]]) -> float:
    circulation_instances = [
        instance for room_type, instances in by_type.items()
        if zones.get(room_type) == Zone.CIRCULATION for instance in instances
    ]
    non_circulation = [
        instance for room_type, instances in by_type.items()
        if zones.get(room_type) != Zone.CIRCULATION for instance in instances
    ]
    if not circulation_instances or not non_circulation:
        return 1.0  # no circulation rooms in this program -- vacuously fine, not a defect
    reached = sum(
        1 for instance in non_circulation
        if any(_shared_edge_length(instance, c) > 1e-6 for c in circulation_instances)
    )
    return reached / len(non_circulation)


def _balance_score(placed: list[RoomInstance], footprint: BuildingFootprintSpec) -> float:
    """SPATIAL_V2 Phase 4: how centered the area-weighted centroid of all placed rooms is within
    the footprint, in [0, 1] (1.0 = centroid exactly at the footprint center). Does NOT force
    centering as a requirement -- it is one of several weighted terms, not the objective itself --
    but it is the first term in this whole scoring system that depends on ABSOLUTE position within
    the footprint at all, which is exactly the gap Phase 1 identified in the existing V1 objective
    (soft_relationships/zone/circulation/utilization/compactness/fragmentation are all translation-
    invariant -- a corner-hugging arrangement scores identically to the same arrangement centered)."""
    total_area = sum(room.area_m2 for room in placed) or 1.0
    centroid_x = sum((room.x + room.width / 2) * room.area_m2 for room in placed) / total_area
    centroid_y = sum((room.y + room.height / 2) * room.area_m2 for room in placed) / total_area
    fx, fy = footprint.width_m / 2, footprint.depth_m / 2
    dx = abs(centroid_x - fx) / fx if fx > 0 else 0.0
    dy = abs(centroid_y - fy) / fy if fy > 0 else 0.0
    return max(0.0, 1.0 - (dx + dy) / 2.0)


def _exterior_score(placed: list[RoomInstance], footprint: BuildingFootprintSpec) -> float:
    candidates = [room for room in placed if room.type in EXTERIOR_PREFERRED_ROOM_TYPES]
    if not candidates:
        return 1.0
    touching = sum(1 for room in candidates if _touches_perimeter(room, footprint))
    return touching / len(candidates)


def _corridor_penalty(placed: list[RoomInstance], zones: dict[str, Zone], programmed_area_m2: float) -> float:
    corridor_area = sum(room.area_m2 for room in placed if zones.get(room.type) == Zone.CIRCULATION)
    if programmed_area_m2 <= 0:
        return 0.0
    ratio = corridor_area / programmed_area_m2
    return max(0.0, min(1.0, ratio / _CORRIDOR_AREA_RATIO_CEILING - 1.0)) if ratio > _CORRIDOR_AREA_RATIO_CEILING else 0.0


def _strip_penalty(placed: list[RoomInstance]) -> float:
    """SPATIAL_V2 Phase 4: penalizes an overall bounding-box aspect ratio far from square --
    generic (based on the arrangement's own geometry, not any footprint or scenario assumption)."""
    if not placed:
        return 0.0
    min_x = min(room.x for room in placed)
    max_x = max(room.x + room.width for room in placed)
    min_y = min(room.y for room in placed)
    max_y = max(room.y + room.height for room in placed)
    bbox_w, bbox_h = max_x - min_x, max_y - min_y
    if bbox_w <= 0 or bbox_h <= 0:
        return 0.0
    aspect = max(bbox_w, bbox_h) / min(bbox_w, bbox_h)
    return max(0.0, min(1.0, (aspect - _STRIP_ASPECT_THRESHOLD) / _STRIP_ASPECT_THRESHOLD))


def _privacy_penalty(by_type: dict[str, list[RoomInstance]]) -> float:
    discouraged = [p for p in GENERIC_ADJACENCY_PREFERENCES if p.weight < 0]
    if not discouraged:
        return 0.0
    applicable = 0
    violated = 0
    for pref in discouraged:
        a_list = by_type.get(pref.room_type_a, [])
        b_list = by_type.get(pref.room_type_b, [])
        if not a_list or not b_list:
            continue
        applicable += 1
        if any(_shared_edge_length(a, b) > 1e-6 for a in a_list for b in b_list if a.id != b.id):
            violated += 1
    return violated / applicable if applicable else 0.0


def score_layout(
    spec: ArchitecturalSpec, footprint: BuildingFootprintSpec, placed: list[RoomInstance]
) -> ArchitecturalScore:
    by_type = _group_by_type(placed)
    zones = zone_by_room_type(spec.zones, set(by_type.keys()))
    quality = compute_quality_metrics(spec, footprint, placed, by_type, _shared_edge_length)

    adjacency = _adjacency_score(placed, by_type)
    zoning = _zoning_score(zones, by_type)
    circulation = _circulation_score(zones, by_type)
    compactness = quality.compactness
    balance = _balance_score(placed, footprint)
    utilization = quality.utilization_ratio
    exterior = _exterior_score(placed, footprint)
    corridor_penalty = _corridor_penalty(placed, zones, quality.programmed_area_m2)
    strip_penalty = _strip_penalty(placed)
    privacy_penalty = _privacy_penalty(by_type)
    dead_space_penalty = 1.0 - quality.unused_region_fragmentation_ratio

    total = (
        W_ADJACENCY * adjacency + W_ZONING * zoning + W_CIRCULATION * circulation
        + W_COMPACTNESS * compactness + W_BALANCE * balance + W_UTILIZATION * utilization
        + W_EXTERIOR * exterior
        - W_CORRIDOR_PENALTY * corridor_penalty - W_STRIP_PENALTY * strip_penalty
        - W_PRIVACY_PENALTY * privacy_penalty - W_DEAD_SPACE_PENALTY * dead_space_penalty
    )

    return ArchitecturalScore(
        total_score=round(total, 4),
        components={
            "adjacency": round(adjacency, 4),
            "zoning": round(zoning, 4),
            "circulation": round(circulation, 4),
            "compactness": round(compactness, 4),
            "balance": round(balance, 4),
            "utilization": round(utilization, 4),
            "exterior_access": round(exterior, 4),
            "corridor_penalty": round(corridor_penalty, 4),
            "strip_penalty": round(strip_penalty, 4),
            "privacy_penalty": round(privacy_penalty, 4),
            "dead_space_penalty": round(dead_space_penalty, 4),
        },
    )
