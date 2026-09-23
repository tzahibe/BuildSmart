"""``RealizationIntent`` (Issue #109, Phase 2 Track 3, POC-only) — the structure a retrieved
``PlanReference`` carries that ``ConceptSpec``/``AdaptedConcept`` currently drop: adjacency, access,
exterior exposure, relative placement, public/private clusters, circulation nodes, wet-core
groups, the entrance relationship, each room's OWN proportions (never a fixed per-type constant),
and the footprint's own wing/band proportions.

``intent_from(reference, concept, brief) -> RealizationIntent`` builds it. Every field is either
a direct copy of a fact already present on ``reference`` (adjacency_edges, access_edges, exterior
exposure, the entrance room/side, room width/depth/area) or a DETERMINISTIC, DOCUMENTED geometric
derivation from facts already on ``reference`` (relative_placement's FRONT/REAR/LEFT/RIGHT/
ABOVE/BELOW labelling, the footprint's own fill-ratio/aspect, wet-core connected components) —
never a value invented where the reference carries none. Where the reference genuinely has no
fact to carry (no entrance, no measured exposure, no adjacency/access edges at all), the
corresponding field is the honest empty/``UNKNOWN`` case, exactly mirroring
``plan_reference.py``'s own convention.

This module never re-derives ``patterns.py``'s own architectural classifications
(circulation_class, zoning, ...) — those already exist on ``ConceptSpec``. It only carries forward
the structural facts ``ConceptSpec``/``AdaptedConcept`` have no field for at all, which is exactly
what gets lost between retrieval and realization today (see the Issue's "Current behavior").

``reference`` must be the PRIMARY donor's own ``PlanReference`` — the one ``concept.baseline_rooms``
was built from (``synthesis._build_candidate`` sets ``baseline_rooms=primary.plan_reference.rooms``)
-- ``intent_from`` asserts every ``baseline_rooms`` id is one of ``reference``'s own room ids, so
passing the wrong reference fails loudly rather than silently building a mismatched intent.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass

from shapely.geometry import Polygon

from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.patterns import PRIVATE_TYPES, PUBLIC_TYPES, WET_TYPES, _connected_components
from spikes.architectural_brain.plan_reference import PlanReference, UNKNOWN
from spikes.architectural_brain.synthesis import ConceptSpec

SCHEMA_VERSION = "1.0"

#: A tiny tolerance for "this room's centroid sits (almost) exactly on the splitting axis" --
#: below this, this module reports UNKNOWN for that axis component rather than an arbitrary side.
_AXIS_EPS = 1e-6


def _minimum_rotated_rectangle(poly: Polygon) -> Polygon:
    """Same suppression as ``patterns._minimum_rotated_rectangle`` -- shapely's oriented-envelope
    routine warns (benignly) on the axis-aligned inputs this dataset always has."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return poly.minimum_rotated_rectangle


@dataclass(frozen=True)
class AdjacencyFact:
    """Two rooms whose polygons share a wall on the reference -- copied verbatim from
    ``reference.adjacency_edges``, never inferred."""

    room_a: str
    room_b: str

    def to_dict(self) -> dict:
        return {"room_a": self.room_a, "room_b": self.room_b}

    @classmethod
    def from_dict(cls, d: dict) -> "AdjacencyFact":
        return cls(room_a=d["room_a"], room_b=d["room_b"])


@dataclass(frozen=True)
class AccessFact:
    """Two rooms walkable between one another on the reference -- copied verbatim from
    ``reference.access_edges``."""

    room_a: str
    room_b: str
    kind: str

    def to_dict(self) -> dict:
        return {"room_a": self.room_a, "room_b": self.room_b, "kind": self.kind}

    @classmethod
    def from_dict(cls, d: dict) -> "AccessFact":
        return cls(room_a=d["room_a"], room_b=d["room_b"], kind=d["kind"])


@dataclass(frozen=True)
class ExposureFact:
    """One room's exterior exposure on the reference. ``known=False`` means the reference itself
    carries no window geometry for this room (the honest UNKNOWN, from ``Room.exposure_known``) --
    ``sides`` is only ever a real measured fact when ``known`` is ``True``."""

    room_id: str
    sides: tuple[str, ...]
    known: bool

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "sides": list(self.sides), "known": self.known}

    @classmethod
    def from_dict(cls, d: dict) -> "ExposureFact":
        return cls(room_id=d["room_id"], sides=tuple(d["sides"]), known=bool(d["known"]))


@dataclass(frozen=True)
class RelativePlacement:
    """One room's position relative to the reference footprint's own centre, along two
    perpendicular axes -- see ``_relative_placement_for`` for the exact deterministic rule.
    Either component is ``UNKNOWN`` only when the room's centroid sits (almost) exactly on that
    axis -- never a guessed side."""

    room_id: str
    primary_axis: str
    secondary_axis: str

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "primary_axis": self.primary_axis,
                "secondary_axis": self.secondary_axis}

    @classmethod
    def from_dict(cls, d: dict) -> "RelativePlacement":
        return cls(room_id=d["room_id"], primary_axis=d["primary_axis"],
                   secondary_axis=d["secondary_axis"])


@dataclass(frozen=True)
class Clusters:
    """Room ids grouped by ``patterns.py``'s own PUBLIC_TYPES / PRIVATE_TYPES vocabulary -- a room
    whose type is in neither set (e.g. CIRCULATION, STORAGE) is in neither cluster, never guessed
    into one."""

    public: tuple[str, ...]
    private: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"public": list(self.public), "private": list(self.private)}

    @classmethod
    def from_dict(cls, d: dict) -> "Clusters":
        return cls(public=tuple(d["public"]), private=tuple(d["private"]))


@dataclass(frozen=True)
class CirculationNode:
    """One CIRCULATION room on the reference and the room ids it is directly access-connected to
    (``reference.access_edges``) -- "what it serves"."""

    room_id: str
    serves: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "serves": list(self.serves)}

    @classmethod
    def from_dict(cls, d: dict) -> "CirculationNode":
        return cls(room_id=d["room_id"], serves=tuple(d["serves"]))


@dataclass(frozen=True)
class EntranceRelationship:
    """The reference's own entrance -> room fact, copied verbatim from ``reference.entrance``."""

    room_id: str | None
    side: str

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "side": self.side}

    @classmethod
    def from_dict(cls, d: dict) -> "EntranceRelationship":
        return cls(room_id=d["room_id"], side=d["side"])


@dataclass(frozen=True)
class RoomProportion:
    """One donor room's OWN proportions -- never a fixed per-type constant.

    ``aspect_ratio`` is the room's own ``width_m / depth_m`` (``None`` -- UNKNOWN -- only if
    ``depth_m`` is ~0). ``area_share_of_type`` is this room's own area divided by the MEAN area of
    every donor room of the same type (1.0 when it is the only room of its type) -- the same
    donor-proportion anchor ``adaptation._resize_rooms`` already uses, so a realizer can recover
    this room's own adapted area as ``TARGET_AREA_M2[type] * area_share_of_type`` without
    collapsing every room of one type to the same size."""

    room_id: str
    room_type: str
    aspect_ratio: float | None
    area_share_of_type: float

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id, "room_type": self.room_type,
            "aspect_ratio": round(self.aspect_ratio, 6) if self.aspect_ratio is not None else None,
            "area_share_of_type": round(self.area_share_of_type, 6),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RoomProportion":
        return cls(room_id=d["room_id"], room_type=d["room_type"],
                   aspect_ratio=d["aspect_ratio"], area_share_of_type=float(d["area_share_of_type"]))


@dataclass(frozen=True)
class FootprintRelationships:
    """The reference's own overall footprint proportions -- ``fill_ratio`` is
    ``footprint_area / oriented_bounding_box_area`` (the same measure ``patterns._circulation_class``
    uses to detect TWO_WING footprints): 1.0 for a genuinely rectangular footprint, markedly lower
    for an L/two-wing footprint. ``None`` fields are UNKNOWN only when the footprint degenerates
    (zero-area bounding box)."""

    width_m: float
    depth_m: float
    aspect_ratio: float | None
    fill_ratio: float | None

    def to_dict(self) -> dict:
        return {
            "width_m": round(self.width_m, 4), "depth_m": round(self.depth_m, 4),
            "aspect_ratio": round(self.aspect_ratio, 6) if self.aspect_ratio is not None else None,
            "fill_ratio": round(self.fill_ratio, 6) if self.fill_ratio is not None else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FootprintRelationships":
        return cls(width_m=float(d["width_m"]), depth_m=float(d["depth_m"]),
                   aspect_ratio=d["aspect_ratio"], fill_ratio=d["fill_ratio"])


@dataclass(frozen=True)
class RealizationIntent:
    schema_version: str
    source_plan_id: str
    concept_id: str
    adjacency_edges: tuple[AdjacencyFact, ...]
    access_edges: tuple[AccessFact, ...]
    exterior_exposure: tuple[ExposureFact, ...]
    relative_placement: tuple[RelativePlacement, ...]
    public_private_clusters: Clusters
    circulation_nodes: tuple[CirculationNode, ...]
    wet_core_groups: tuple[tuple[str, ...], ...]
    entrance_relationship: EntranceRelationship
    room_proportions: tuple[RoomProportion, ...]
    footprint_relationships: FootprintRelationships

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source_plan_id": self.source_plan_id,
            "concept_id": self.concept_id,
            "adjacency_edges": [e.to_dict() for e in self.adjacency_edges],
            "access_edges": [e.to_dict() for e in self.access_edges],
            "exterior_exposure": [e.to_dict() for e in self.exterior_exposure],
            "relative_placement": [p.to_dict() for p in self.relative_placement],
            "public_private_clusters": self.public_private_clusters.to_dict(),
            "circulation_nodes": [n.to_dict() for n in self.circulation_nodes],
            "wet_core_groups": [list(g) for g in self.wet_core_groups],
            "entrance_relationship": self.entrance_relationship.to_dict(),
            "room_proportions": [p.to_dict() for p in self.room_proportions],
            "footprint_relationships": self.footprint_relationships.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RealizationIntent":
        return cls(
            schema_version=d["schema_version"],
            source_plan_id=d["source_plan_id"],
            concept_id=d["concept_id"],
            adjacency_edges=tuple(AdjacencyFact.from_dict(x) for x in d["adjacency_edges"]),
            access_edges=tuple(AccessFact.from_dict(x) for x in d["access_edges"]),
            exterior_exposure=tuple(ExposureFact.from_dict(x) for x in d["exterior_exposure"]),
            relative_placement=tuple(RelativePlacement.from_dict(x) for x in d["relative_placement"]),
            public_private_clusters=Clusters.from_dict(d["public_private_clusters"]),
            circulation_nodes=tuple(CirculationNode.from_dict(x) for x in d["circulation_nodes"]),
            wet_core_groups=tuple(tuple(g) for g in d["wet_core_groups"]),
            entrance_relationship=EntranceRelationship.from_dict(d["entrance_relationship"]),
            room_proportions=tuple(RoomProportion.from_dict(x) for x in d["room_proportions"]),
            footprint_relationships=FootprintRelationships.from_dict(d["footprint_relationships"]),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "RealizationIntent":
        return cls.from_dict(json.loads(text))


def _relative_placement_for(room_id: str, centroid: tuple[float, float],
                            center: tuple[float, float], entrance_side: str) -> RelativePlacement:
    """Deterministic geometric labelling, relative to the footprint's own bounding-box centre.

    ResPlan geometry is grid-aligned in an image-like frame: N/W are the smaller-coordinate sides,
    S/E the larger-coordinate sides (the same convention ``patterns._side_of_bbox_center`` uses).

    - If the entrance side is known and lies on the N/S (y) edge: the y-axis is PRIMARY, labelled
      FRONT/REAR (nearer/farther from the entrance's own side); the x-axis is SECONDARY, labelled
      LEFT (W side) / RIGHT (E side).
    - If the entrance side is known and lies on the E/W (x) edge: the x-axis is PRIMARY, labelled
      FRONT/REAR; the y-axis is SECONDARY, labelled ABOVE (N side) / BELOW (S side) -- "left/right"
      would be ambiguous once the front-facing axis itself is E/W.
    - If the entrance side is UNKNOWN: no FRONT/REAR can be honestly claimed. The y-axis is
      PRIMARY, labelled ABOVE (N) / BELOW (S) purely from plan coordinates; the x-axis is
      SECONDARY, labelled LEFT (W) / RIGHT (E).

    Either label is UNKNOWN when the room's centroid is within ``_AXIS_EPS`` of that axis.
    """
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


def _footprint_relationships(reference: PlanReference) -> FootprintRelationships:
    poly = Polygon(reference.footprint)
    minx, miny, maxx, maxy = poly.bounds
    width_m, depth_m = maxx - minx, maxy - miny
    aspect_ratio = (max(width_m, depth_m) / min(width_m, depth_m)
                    if min(width_m, depth_m) > _AXIS_EPS else None)
    mrr_area = _minimum_rotated_rectangle(poly).area
    fill_ratio = poly.area / mrr_area if mrr_area > _AXIS_EPS else None
    return FootprintRelationships(width_m=width_m, depth_m=depth_m,
                                  aspect_ratio=aspect_ratio, fill_ratio=fill_ratio)


def _room_proportions(reference: PlanReference) -> tuple[RoomProportion, ...]:
    type_totals: dict[str, float] = {}
    type_counts: dict[str, int] = {}
    for room in reference.rooms:
        type_totals[room.type] = type_totals.get(room.type, 0.0) + room.area_m2
        type_counts[room.type] = type_counts.get(room.type, 0) + 1
    type_mean = {t: type_totals[t] / type_counts[t] for t in type_totals}

    proportions = []
    for room in reference.rooms:
        aspect_ratio = room.width_m / room.depth_m if room.depth_m > _AXIS_EPS else None
        mean_for_type = type_mean.get(room.type, room.area_m2)
        area_share = room.area_m2 / mean_for_type if mean_for_type > _AXIS_EPS else 1.0
        proportions.append(RoomProportion(room_id=room.id, room_type=room.type,
                                          aspect_ratio=aspect_ratio, area_share_of_type=area_share))
    return tuple(proportions)


def _wet_core_groups(reference: PlanReference) -> tuple[tuple[str, ...], ...]:
    wet_ids = [r.id for r in reference.rooms if r.type in WET_TYPES]
    if not wet_ids:
        return ()
    adjacency = {frozenset((e.room_a, e.room_b)) for e in reference.adjacency_edges}
    components = _connected_components(wet_ids, adjacency)
    groups = [tuple(sorted(c)) for c in components]
    return tuple(sorted(groups, key=lambda g: g[0]))


def _circulation_nodes(reference: PlanReference) -> tuple[CirculationNode, ...]:
    access: dict[str, set[str]] = {}
    for e in reference.access_edges:
        access.setdefault(e.room_a, set()).add(e.room_b)
        access.setdefault(e.room_b, set()).add(e.room_a)
    nodes = []
    for room in reference.rooms:
        if room.type != "CIRCULATION":
            continue
        served = tuple(sorted(access.get(room.id, set())))
        nodes.append(CirculationNode(room_id=room.id, serves=served))
    return tuple(nodes)


def intent_from(reference: PlanReference, concept: ConceptSpec, brief: Brief) -> RealizationIntent:
    baseline_ids = {r.id for r in concept.baseline_rooms}
    reference_ids = {r.id for r in reference.rooms}
    missing = baseline_ids - reference_ids
    if missing:
        raise ValueError(
            f"reference {reference.plan_id!r} does not carry {concept.concept_id!r}'s baseline "
            f"rooms {sorted(missing)} -- intent_from requires the PRIMARY donor's own reference")

    if (concept.bedrooms, concept.safe_room, concept.wet_rooms, concept.wet_room_kinds, concept.stories) != (
        brief.program.bedrooms, brief.program.safe_room, brief.program.wet_rooms,
        tuple(k.kind.value for k in brief.program.wet_room_kinds), brief.stories,
    ):
        raise ValueError(
            f"brief and concept {concept.concept_id!r} disagree on the authoritative requirements "
            "-- intent_from expects the SAME brief synthesize() built this concept from")

    footprint_poly = Polygon(reference.footprint)
    fminx, fminy, fmaxx, fmaxy = footprint_poly.bounds
    center = ((fminx + fmaxx) / 2.0, (fminy + fmaxy) / 2.0)
    entrance_side = reference.entrance.side

    placements = tuple(
        _relative_placement_for(
            room.id, Polygon(room.polygon).centroid.coords[0], center, entrance_side)
        for room in reference.rooms
    )
    exposures = tuple(
        ExposureFact(room_id=room.id,
                    sides=room.exterior_exposure if room.exposure_known else (),
                    known=room.exposure_known)
        for room in reference.rooms
    )
    clusters = Clusters(
        public=tuple(sorted(r.id for r in reference.rooms if r.type in PUBLIC_TYPES)),
        private=tuple(sorted(r.id for r in reference.rooms if r.type in PRIVATE_TYPES)),
    )

    return RealizationIntent(
        schema_version=SCHEMA_VERSION,
        source_plan_id=reference.plan_id,
        concept_id=concept.concept_id,
        adjacency_edges=tuple(AdjacencyFact(e.room_a, e.room_b) for e in reference.adjacency_edges),
        access_edges=tuple(AccessFact(e.room_a, e.room_b, e.kind) for e in reference.access_edges),
        exterior_exposure=exposures,
        relative_placement=placements,
        public_private_clusters=clusters,
        circulation_nodes=_circulation_nodes(reference),
        wet_core_groups=_wet_core_groups(reference),
        entrance_relationship=EntranceRelationship(room_id=reference.entrance.room_id, side=entrance_side),
        room_proportions=_room_proportions(reference),
        footprint_relationships=_footprint_relationships(reference),
    )
