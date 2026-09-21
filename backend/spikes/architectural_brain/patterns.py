"""``derive_pattern(ref) -> ArchitecturalPattern``: measurable architectural semantics from a
``PlanReference``. See ``docs/reports/poc-architectural-brain/dataset.md`` for the rule-by-rule
description of every field below.

Every rule here is a deterministic function of geometry/graph facts already present on the
``PlanReference`` — no field is a guess, and every field that cannot be measured (no bedrooms, no
wet rooms, no window data, no entrance) reports ``None``/``"UNKNOWN"`` rather than a default.
"""
from __future__ import annotations

import warnings
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from math import hypot

from shapely.geometry import Polygon

from spikes.architectural_brain.plan_reference import PlanReference, Room

UNKNOWN = "UNKNOWN"

PUBLIC_TYPES = frozenset({"LIVING", "DINING", "KITCHEN", "FAMILY_ROOM"})
PRIVATE_TYPES = frozenset({"BEDROOM", "MASTER_BEDROOM", "STUDY", "DRESSING_ROOM"})
HABITABLE_TYPES = PUBLIC_TYPES | PRIVATE_TYPES | frozenset({"SAFE_ROOM"})
WET_TYPES = frozenset({"BATHROOM", "TOILET"})
BEDROOM_TYPES = frozenset({"BEDROOM", "MASTER_BEDROOM"})

# TWO_WING footprint rule: a genuinely rectangular footprint fills almost all of its own oriented
# bounding box; an L (two rectangular wings) fills markedly less of it. Measured on the ResPlan
# corpus (Villa/IndependentHouse/BuilderFloor, >=3 bedrooms, n=561): the fill-ratio distribution is
# continuous with a median around 0.82 and no natural gap (most ResPlan footprints have a nibbled
# corner or notch, not a genuine second wing) — 0.65 is this corpus's own ~10th percentile, so the
# rule isolates the most L-like tenth of footprints rather than claiming a universal geometric
# constant for "L-shaped".
L_FOOTPRINT_FILL_RATIO_MAX = 0.65
# FRONT_BAND rule: the public rooms touching the entrance side must cover most of the footprint's
# extent along that side to count as a "band", not just one room that happens to be at the front.
FRONT_BAND_COVERAGE_MIN = 0.6
# CENTRAL_PUBLIC zoning rule: the public centroid sits within this fraction of the footprint
# diagonal from the footprint's own centre to count as "central".
CENTRAL_PUBLIC_RADIUS_FRACTION = 0.15


@dataclass(frozen=True)
class ArchitecturalPattern:
    plan_id: str
    circulation_class: str
    zoning: str
    public_composition: str
    bedroom_grouping: float | None
    wet_core_strategy: str
    entrance_relationship: str
    exposure_pattern: float | None
    circulation_ratio: float
    corridor_length_m: float
    circulation_nodes: int
    topology_depth: int | None
    relationships: dict

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "circulation_class": self.circulation_class,
            "zoning": self.zoning,
            "public_composition": self.public_composition,
            "bedroom_grouping": self.bedroom_grouping,
            "wet_core_strategy": self.wet_core_strategy,
            "entrance_relationship": self.entrance_relationship,
            "exposure_pattern": self.exposure_pattern,
            "circulation_ratio": round(self.circulation_ratio, 4),
            "corridor_length_m": round(self.corridor_length_m, 4),
            "circulation_nodes": self.circulation_nodes,
            "topology_depth": self.topology_depth,
            "relationships": dict(self.relationships),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArchitecturalPattern":
        return cls(
            plan_id=d["plan_id"], circulation_class=d["circulation_class"], zoning=d["zoning"],
            public_composition=d["public_composition"], bedroom_grouping=d["bedroom_grouping"],
            wet_core_strategy=d["wet_core_strategy"], entrance_relationship=d["entrance_relationship"],
            exposure_pattern=d["exposure_pattern"], circulation_ratio=d["circulation_ratio"],
            corridor_length_m=d["corridor_length_m"], circulation_nodes=d["circulation_nodes"],
            topology_depth=d["topology_depth"], relationships=dict(d["relationships"]),
        )


def _poly(room: Room) -> Polygon:
    return Polygon(room.polygon)


def _bbox_center(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    minx, miny, maxx, maxy = bounds
    return (minx + maxx) / 2.0, (miny + maxy) / 2.0


def _minimum_rotated_rectangle(poly: Polygon) -> Polygon:
    """Shapely's oriented-envelope routine emits a benign numpy divide-by-zero/invalid-value
    warning for perfectly axis-aligned inputs (common here — ResPlan geometry is grid-aligned)
    while still returning the exact correct rectangle; the warning is suppressed locally rather
    than silencing it process-wide."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return poly.minimum_rotated_rectangle


def _oriented_long_short(poly: Polygon) -> tuple[float, float]:
    """Long/short side lengths of the polygon's minimum rotated rectangle (rotation-invariant)."""
    rect = _minimum_rotated_rectangle(poly)
    coords = list(rect.exterior.coords)[:-1] if hasattr(rect, "exterior") else []
    if len(coords) != 4:
        minx, miny, maxx, maxy = poly.bounds
        w, h = maxx - minx, maxy - miny
        return (max(w, h), min(w, h)) if min(w, h) > 0 else (max(w, h), 0.0)
    side_a = hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    side_b = hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    return (max(side_a, side_b), min(side_a, side_b))


def _side_of_bbox_center(center: tuple[float, float], ref_bounds: tuple[float, float, float, float]) -> str | None:
    cx, cy = center
    minx, miny, maxx, maxy = ref_bounds
    ref_cx, ref_cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    dx, dy = cx - ref_cx, cy - ref_cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W"
    return "S" if dy > 0 else "N"


def _build_access_graph(ref: PlanReference) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for r in ref.rooms:
        graph[r.id]  # ensure every room is a node, even isolated ones
    for e in ref.access_edges:
        graph[e.room_a].add(e.room_b)
        graph[e.room_b].add(e.room_a)
    return graph


def _bfs_depths(graph: dict[str, set[str]], start: str) -> dict[str, int]:
    depths = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nb in graph.get(node, ()):
            if nb not in depths:
                depths[nb] = depths[node] + 1
                queue.append(nb)
    return depths


def _connected_components(ids: list[str], edges: set[frozenset[str]]) -> list[set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        a, b = tuple(e)
        if a in ids and b in ids:
            adj[a].add(b)
            adj[b].add(a)
    seen: set[str] = set()
    components: list[set[str]] = []
    for i in ids:
        if i in seen:
            continue
        comp = {i}
        queue = deque([i])
        seen.add(i)
        while queue:
            node = queue.popleft()
            for nb in adj.get(node, ()):
                if nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    queue.append(nb)
        components.append(comp)
    return components


def _circulation_class(ref: PlanReference) -> str:
    rooms_by_id = {r.id: r for r in ref.rooms}
    circulation = [r for r in ref.rooms if r.type == "CIRCULATION"]
    doors_touching: dict[str, int] = Counter()
    for d in ref.doors:
        for rid in d.room_ids:
            doors_touching[rid] += 1
    adjacency_pairs = {frozenset((e.room_a, e.room_b)) for e in ref.adjacency_edges}

    if len(circulation) == 1:
        comp = circulation[0]
        poly = _poly(comp)
        long_side, short_side = _oriented_long_short(poly)
        aspect = long_side / short_side if short_side > 1e-6 else float("inf")
        n_doors = doors_touching.get(comp.id, 0)
        neighbour_sides = set()
        for pair in adjacency_pairs:
            if comp.id not in pair:
                continue
            other_id = next(iter(pair - {comp.id}))
            other = rooms_by_id.get(other_id)
            if other is None or other.type == "CIRCULATION":
                continue
            side = _side_of_bbox_center(_poly(other).centroid.coords[0], poly.bounds)
            if side:
                neighbour_sides.add(side)
        if aspect > 3.0 and n_doors >= 3:
            return "SPINE"
        if aspect <= 1.5 and n_doors >= 4 and len(neighbour_sides) >= 3:
            return "HUB_LOBBY"
    elif len(circulation) >= 2:
        circ_ids = {r.id for r in circulation}
        joined = any(
            pair <= circ_ids for pair in (adjacency_pairs | {frozenset((e.room_a, e.room_b)) for e in ref.access_edges})
        )
        if joined:
            return "BRANCHED"

    footprint_poly = Polygon(ref.footprint)
    mrr_area = _minimum_rotated_rectangle(footprint_poly).area
    fill_ratio = footprint_poly.area / mrr_area if mrr_area > 0 else 1.0
    if fill_ratio <= L_FOOTPRINT_FILL_RATIO_MAX:
        return "TWO_WING"

    if ref.entrance.side != UNKNOWN:
        side = ref.entrance.side
        axis_is_x = side in ("N", "S")
        minx, miny, maxx, maxy = footprint_poly.bounds
        total_extent = (maxx - minx) if axis_is_x else (maxy - miny)
        tol = ref.derived.wall_thickness_m * 1.5
        intervals = []
        for r in ref.rooms:
            if r.type not in PUBLIC_TYPES:
                continue
            rminx, rminy, rmaxx, rmaxy = _poly(r).bounds
            near_side = (
                (side == "N" and abs(rminy - miny) <= tol)
                or (side == "S" and abs(rmaxy - maxy) <= tol)
                or (side == "W" and abs(rminx - minx) <= tol)
                or (side == "E" and abs(rmaxx - maxx) <= tol)
            )
            if near_side:
                intervals.append((rminx, rmaxx) if axis_is_x else (rminy, rmaxy))
        covered = _union_interval_length(intervals)
        if total_extent > 0 and covered / total_extent >= FRONT_BAND_COVERAGE_MIN:
            return "FRONT_BAND"

    if not ref.rooms:
        return UNKNOWN
    return "OTHER"


def _union_interval_length(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    intervals = sorted(intervals)
    total = 0.0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start > cur_end:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    total += cur_end - cur_start
    return total


def _zoning(ref: PlanReference) -> str:
    public_rooms = [r for r in ref.rooms if r.type in PUBLIC_TYPES]
    private_rooms = [r for r in ref.rooms if r.type in PRIVATE_TYPES]
    if not public_rooms or not private_rooms:
        return UNKNOWN

    footprint_poly = Polygon(ref.footprint)
    fminx, fminy, fmaxx, fmaxy = footprint_poly.bounds
    center = _bbox_center(footprint_poly.bounds)
    diag = hypot(fmaxx - fminx, fmaxy - fminy)

    def area_weighted_centroid(rooms: list[Room]) -> tuple[float, float]:
        total_area = sum(r.area_m2 for r in rooms)
        cx = sum(_poly(r).centroid.x * r.area_m2 for r in rooms) / total_area
        cy = sum(_poly(r).centroid.y * r.area_m2 for r in rooms) / total_area
        return cx, cy

    pub_c = area_weighted_centroid(public_rooms)
    priv_c = area_weighted_centroid(private_rooms)

    dist_pub_center = hypot(pub_c[0] - center[0], pub_c[1] - center[1])
    dist_priv_center = hypot(priv_c[0] - center[0], priv_c[1] - center[1])
    if diag > 0 and dist_pub_center <= CENTRAL_PUBLIC_RADIUS_FRACTION * diag and dist_priv_center > dist_pub_center:
        return "CENTRAL_PUBLIC"

    dx, dy = abs(pub_c[0] - priv_c[0]), abs(pub_c[1] - priv_c[1])
    if dx < 1e-6 and dy < 1e-6:
        return "OTHER"

    entrance_side = ref.entrance.side
    if entrance_side != UNKNOWN:
        entrance_axis_is_y = entrance_side in ("N", "S")
        separation_axis_is_y = dy >= dx
        if entrance_axis_is_y == separation_axis_is_y:
            pub_nearer = (
                (entrance_side == "N" and pub_c[1] < priv_c[1])
                or (entrance_side == "S" and pub_c[1] > priv_c[1])
                or (entrance_side == "W" and pub_c[0] < priv_c[0])
                or (entrance_side == "E" and pub_c[0] > priv_c[0])
            )
            if pub_nearer:
                return "PUBLIC_FRONT_PRIVATE_REAR"
        return "PUBLIC_PRIVATE_WINGS"

    return "PUBLIC_PRIVATE_WINGS" if (dx > 0 or dy > 0) else "OTHER"


def _public_composition(ref: PlanReference) -> str:
    living = [r for r in ref.rooms if r.type == "LIVING"]
    kitchen = [r for r in ref.rooms if r.type == "KITCHEN"]
    if not living:
        return UNKNOWN
    if not kitchen:
        # No standalone KITCHEN room: it was either merged into LIVING at ingest (open-plan
        # geometry artefact) or the plan has none at all — both read as an open public block.
        return "OPEN"
    access_pairs = {frozenset((e.room_a, e.room_b)) for e in ref.access_edges}
    living_ids = {r.id for r in living}
    kitchen_ids = {r.id for r in kitchen}
    if any(pair & living_ids and pair & kitchen_ids for pair in access_pairs):
        return "CLOSED_ADJACENT"
    return "CLOSED_SEPARATE"


def _bedroom_grouping(ref: PlanReference, graph: dict[str, set[str]]) -> float | None:
    bedroom_ids = [r.id for r in ref.rooms if r.type in BEDROOM_TYPES]
    if not bedroom_ids:
        return None
    gateway_counts: Counter = Counter()
    bedroom_set = set(bedroom_ids)
    for bid in bedroom_ids:
        gateways = sorted(nb for nb in graph.get(bid, ()) if nb not in bedroom_set)
        gateway_counts[gateways[0] if gateways else f"__ISOLATED__{bid}"] += 1
    best = max(gateway_counts.values())
    return best / len(bedroom_ids)


def _wet_core_strategy(ref: PlanReference) -> str:
    wet_ids = [r.id for r in ref.rooms if r.type in WET_TYPES]
    if not wet_ids:
        return UNKNOWN
    if len(wet_ids) == 1:
        return "SINGLE"
    adjacency_edges = {frozenset((e.room_a, e.room_b)) for e in ref.adjacency_edges}
    components = _connected_components(wet_ids, adjacency_edges)
    return "CLUSTERED" if len(components) == 1 else "DISPERSED"


def _entrance_relationship(ref: PlanReference) -> str:
    if ref.entrance.room_id is None:
        return UNKNOWN
    room = ref.room(ref.entrance.room_id)
    if room is None:
        return UNKNOWN
    if room.type == "LIVING":
        return "TO_LIVING"
    if room.type == "CIRCULATION":
        return "TO_HALL"
    if room.type == "KITCHEN":
        return "TO_KITCHEN"
    return "TO_OTHER"


def _exposure_pattern(ref: PlanReference) -> float | None:
    habitable = [r for r in ref.rooms if r.type in HABITABLE_TYPES]
    if not habitable:
        return None
    if not habitable[0].exposure_known:
        return None
    exposed = sum(1 for r in habitable if r.exterior_exposure)
    return exposed / len(habitable)


def _circulation_metrics(ref: PlanReference) -> tuple[float, float, int]:
    circulation = [r for r in ref.rooms if r.type == "CIRCULATION"]
    footprint_area = ref.derived.footprint_area_m2
    circ_area = sum(r.area_m2 for r in circulation)
    ratio = circ_area / footprint_area if footprint_area > 0 else 0.0
    corridor_length = max((_oriented_long_short(_poly(r))[0] for r in circulation), default=0.0)
    return ratio, corridor_length, len(circulation)


def _topology_depth(ref: PlanReference, graph: dict[str, set[str]]) -> int | None:
    if ref.entrance.room_id is None:
        return None
    depths = _bfs_depths(graph, ref.entrance.room_id)
    return max(depths.values()) if depths else 0


def _relationships(ref: PlanReference, graph: dict[str, set[str]]) -> dict:
    entrance_room_id = ref.entrance.room_id
    entrance_public: str
    if entrance_room_id is None:
        entrance_public = UNKNOWN
    else:
        depths = _bfs_depths(graph, entrance_room_id)
        public_ids = {r.id for r in ref.rooms if r.type in PUBLIC_TYPES}
        reachable_public_depths = [d for rid, d in depths.items() if rid in public_ids]
        if not reachable_public_depths:
            entrance_public = "NOT_CONNECTED"
        elif min(reachable_public_depths) == 0:
            entrance_public = "DIRECT"
        elif min(reachable_public_depths) == 1:
            entrance_public = "VIA_ONE_ROOM"
        else:
            entrance_public = "FAR"

    bedroom_ids = [r.id for r in ref.rooms if r.type in BEDROOM_TYPES]
    if not bedroom_ids:
        bedrooms_private_circulation = None
    else:
        rooms_by_id = {r.id: r for r in ref.rooms}
        via_circulation = sum(
            1 for bid in bedroom_ids
            if any(rooms_by_id[nb].type == "CIRCULATION" for nb in graph.get(bid, ()) if nb in rooms_by_id)
        )
        bedrooms_private_circulation = via_circulation / len(bedroom_ids)

    wet_ids = [r.id for r in ref.rooms if r.type in WET_TYPES]
    if not wet_ids:
        wet_bedrooms_public = None
    else:
        rooms_by_id = {r.id: r for r in ref.rooms}
        ensuite = sum(
            1 for wid in wet_ids
            if any(rooms_by_id[nb].type in BEDROOM_TYPES for nb in graph.get(wid, ()) if nb in rooms_by_id)
        )
        wet_bedrooms_public = ensuite / len(wet_ids)

    return {
        "living_dining": "NOT_PRESENT",
        "dining_kitchen": "NOT_PRESENT",
        "entrance_public": entrance_public,
        "bedrooms_private_circulation": bedrooms_private_circulation,
        "wet_bedrooms_public": wet_bedrooms_public,
    }


def derive_pattern(ref: PlanReference) -> ArchitecturalPattern:
    graph = _build_access_graph(ref)
    ratio, corridor_length, n_nodes = _circulation_metrics(ref)
    return ArchitecturalPattern(
        plan_id=ref.plan_id,
        circulation_class=_circulation_class(ref),
        zoning=_zoning(ref),
        public_composition=_public_composition(ref),
        bedroom_grouping=_bedroom_grouping(ref, graph),
        wet_core_strategy=_wet_core_strategy(ref),
        entrance_relationship=_entrance_relationship(ref),
        exposure_pattern=_exposure_pattern(ref),
        circulation_ratio=ratio,
        corridor_length_m=corridor_length,
        circulation_nodes=n_nodes,
        topology_depth=_topology_depth(ref, graph),
        relationships=_relationships(ref, graph),
    )
