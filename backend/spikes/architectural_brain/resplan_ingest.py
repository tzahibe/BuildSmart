"""``normalise(plan_dict) -> PlanReference``: turn one raw ResPlan plan dict into a metric
``PlanReference``. See ``docs/reports/poc-architectural-brain/dataset.md`` for the rule-by-rule
description of every derivation this module performs.

ResPlan geometry is in PIXEL coordinates on a plan-specific grid; ``plan["area"]`` is the real
gross area in m². The metric scale is ``sqrt(area / inner.area_px)``, cross-checked against
``wall_depth`` (a plan whose implied wall thickness falls outside 8-45 cm is rejected — real
interior walls are never that thin or that thick, so a value outside that band means the scale
inference itself is wrong, not that the wall is unusual).

Nothing here guesses: a room/door/window/entrance that cannot be tied to geometry deterministically
is reported ``UNKNOWN`` (or dropped, for edges — an edge is a positive claim, never a default).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from spikes.architectural_brain.plan_reference import (
    AccessEdge,
    AdjacencyEdge,
    Derived,
    Door,
    Entrance,
    PlanReference,
    Provenance,
    Room,
    WallSegment,
    Window,
)

RESPLAN_LICENCE = "CC BY 4.0"
RESPLAN_CITATION = "ResPlan, Abouagour & Garyfallidis 2025, arXiv 2508.14006"
UNKNOWN_UNIT_TYPE = "UNKNOWN"

MIN_WALL_THICKNESS_M = 0.08
MAX_WALL_THICKNESS_M = 0.45

# A full wet room ("bathroom") vs a WC-only wet room ("toilet") by net area — matches the
# BATHROOM/TOILET target-area boundary already in use for room sizing
# (`app/vertical_slice/concept_generator.py`: TOILET target 2.2-4.0 m², BATHROOM target 4.5-6.5 m²).
BATHROOM_VS_TOILET_AREA_M2 = 4.0

# A kitchen polygon whose area lies at least this fraction inside a living polygon is a geometry
# artefact of the source data (the "kitchen" is really an unlabelled nook of the living room), not
# a second room — it is merged into the LIVING room rather than double-counted.
KITCHEN_CONTAINMENT_RATIO = 0.9

# Residual (circulation) components smaller than this are digitisation slivers (imperfect tiling
# between rooms/walls, not a real navigable space) — a real minimal hallway is at least a door
# width by a body-width deep (~0.9 x 1.2 m); measured on this corpus the real corridors cluster
# above 2 m^2 while the tiling artefacts cluster under 1 m^2 (see dataset.md).
MIN_CIRCULATION_AREA_M2 = 2.0

# A room/door/window side is "on the footprint boundary" within this many wall thicknesses.
BOUNDARY_TOLERANCE_WALLS = 1.5

# How far (in wall thicknesses) a door/window/front_door polygon may sit from a room polygon and
# still count as touching it. A door centred in its wall sits roughly half a wall thickness from
# each room face; measured on this corpus, matching a residual CIRCULATION room (whose boundary
# has been eroded by several successive subtractions) needs a wider margin — 1.5x reliably bridges
# that gap on real plans without ever being large enough to falsely reach a second, unrelated room.
CONNECTOR_MATCH_BUFFER_WALLS = 1.5


class PlanRejected(Exception):
    """Raised by ``normalise`` when a plan cannot be honestly normalised. ``reason`` is a short,
    stable machine-checkable string for corpus-building statistics."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _valid(geom: BaseGeometry | None) -> BaseGeometry | None:
    if geom is None:
        return None
    if geom.is_empty:
        return geom
    return geom if geom.is_valid else make_valid(geom)


def _parts(geom: BaseGeometry | None) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
    # A GeometryCollection can appear after make_valid on a degenerate input; keep polygon parts.
    if hasattr(geom, "geoms"):
        return [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
    return []


def _scale_ring(poly: Polygon, scale: float) -> tuple[tuple[float, float], ...]:
    return tuple((x * scale, y * scale) for x, y in poly.exterior.coords)


def _scale_poly(poly: Polygon, scale: float) -> Polygon:
    return Polygon([(x * scale, y * scale) for x, y in poly.exterior.coords])


def _bbox(poly: Polygon) -> tuple[float, float, float, float]:
    return poly.bounds  # (minx, miny, maxx, maxy)


@dataclass
class _RoomCandidate:
    type: str
    polygon: Polygon  # already in metric coordinates


def _build_room_candidates(scaled: dict[str, list[Polygon]]) -> list[_RoomCandidate]:
    candidates: list[_RoomCandidate] = []

    living_polys = list(scaled.get("living", ()))
    kitchen_polys = list(scaled.get("kitchen", ()))

    # Merge a kitchen polygon into LIVING when it is (near-)contained in a living polygon: this is
    # a geometry artefact (an unlabelled living-room nook), not a genuine second room — see
    # KITCHEN_CONTAINMENT_RATIO. Everything else stays a distinct KITCHEN room; whether it is open
    # or closed to the living room is a derived architectural PATTERN (patterns.py), not a ingest
    # rule — it is read off the resulting adjacency/access edges, not baked into the room type.
    merged_kitchen_idx: set[int] = set()
    living_merged: list[Polygon] = list(living_polys)
    for ki, kpoly in enumerate(kitchen_polys):
        if kpoly.area <= 0:
            continue
        for li, lpoly in enumerate(living_merged):
            inter = kpoly.intersection(lpoly).area
            if inter >= KITCHEN_CONTAINMENT_RATIO * kpoly.area:
                living_merged[li] = lpoly.union(kpoly)
                merged_kitchen_idx.add(ki)
                break

    for lpoly in living_merged:
        if lpoly.area > 0:
            candidates.append(_RoomCandidate("LIVING", lpoly))

    for ki, kpoly in enumerate(kitchen_polys):
        if ki in merged_kitchen_idx or kpoly.area <= 0:
            continue
        candidates.append(_RoomCandidate("KITCHEN", kpoly))

    for bpoly in scaled.get("bedroom", ()):
        if bpoly.area > 0:
            candidates.append(_RoomCandidate("BEDROOM", bpoly))

    for bpoly in scaled.get("bathroom", ()):
        if bpoly.area <= 0:
            continue
        role = "TOILET" if bpoly.area < BATHROOM_VS_TOILET_AREA_M2 else "BATHROOM"
        candidates.append(_RoomCandidate(role, bpoly))

    for spoly in scaled.get("storage", ()):
        if spoly.area > 0:
            candidates.append(_RoomCandidate("STORAGE", spoly))

    for stpoly in scaled.get("stair", ()):
        if stpoly.area > 0:
            candidates.append(_RoomCandidate("STAIRWELL", stpoly))

    return candidates


def _footprint_side(point: tuple[float, float], fbounds: tuple[float, float, float, float],
                     tol: float) -> str:
    x, y = point
    minx, miny, maxx, maxy = fbounds
    dists = {"W": abs(x - minx), "E": abs(x - maxx), "N": abs(y - miny), "S": abs(y - maxy)}
    side, dist = min(dists.items(), key=lambda kv: kv[1])
    return side if dist <= tol else "UNKNOWN"


def _contact_length(geom: BaseGeometry, room_poly: Polygon, buf: float) -> float:
    try:
        return geom.boundary.intersection(room_poly.buffer(buf)).length
    except Exception:
        return 0.0


def _match_rooms_for_connector(conn: Polygon, rooms: list[Room], buf: float) -> list[str]:
    """Rooms touching a door/window/front_door polygon, ordered by contact length (best first) so
    a caller that wants a single "primary" room (front_door -> entrance room, window -> the room a
    window belongs to) can always take element 0, not whichever room happened to be added to
    ``rooms`` first."""
    room_polys = {r.id: Polygon(r.polygon) for r in rooms}
    touching = [rid for rid, poly in room_polys.items() if conn.buffer(buf).intersects(poly)]
    if len(touching) <= 1:
        return touching
    scored = sorted(
        ((rid, _contact_length(conn, room_polys[rid], buf)) for rid in touching),
        key=lambda kv: kv[1], reverse=True,
    )
    if len(touching) == 2:
        return [rid for rid, _ in scored]
    best = scored[0][1]
    kept = [scored[0][0], scored[1][0]]
    for rid, score in scored[2:]:
        if score >= 0.25 * best and score >= buf:
            kept.append(rid)
    return kept


def normalise(plan: dict) -> PlanReference:
    plan_id = str(plan.get("id"))
    unit_type = plan.get("unitType") or UNKNOWN_UNIT_TYPE

    inner = _valid(plan.get("inner"))
    inner_parts = _parts(inner)
    if not inner_parts:
        raise PlanRejected("no_inner_footprint")

    area_m2 = plan.get("area")
    if not area_m2 or area_m2 <= 0:
        raise PlanRejected("missing_gross_area")

    inner_area_px = sum(p.area for p in inner_parts)
    if inner_area_px <= 0:
        raise PlanRejected("degenerate_inner_footprint")
    scale = sqrt(float(area_m2) / inner_area_px)

    wall_depth_px = plan.get("wall_depth")
    if not wall_depth_px or wall_depth_px <= 0:
        raise PlanRejected("missing_wall_depth")
    wall_thickness_m = float(wall_depth_px) * scale
    if not (MIN_WALL_THICKNESS_M <= wall_thickness_m <= MAX_WALL_THICKNESS_M):
        raise PlanRejected(
            f"implied_wall_thickness_out_of_range:{wall_thickness_m:.3f}m"
        )

    footprint_poly = max(inner_parts, key=lambda p: p.area)
    footprint_ring = _scale_ring(footprint_poly, scale)
    footprint_bounds = _bbox(_scale_poly(footprint_poly, scale))

    scaled: dict[str, list[Polygon]] = {}
    for key in ("living", "kitchen", "bedroom", "bathroom", "storage", "stair", "wall"):
        geom = _valid(plan.get(key))
        scaled[key] = [_scale_poly(p, scale) for p in _parts(geom)]

    candidates = _build_room_candidates(scaled)

    # Residual circulation: inner minus every mapped room minus walls, connected components.
    all_inner_scaled = MultiPolygon([_scale_poly(p, scale) for p in inner_parts])
    mask_polys = scaled["wall"] + [c.polygon for c in candidates]
    mask = MultiPolygon(mask_polys) if mask_polys else None
    residual = all_inner_scaled.difference(mask.buffer(0)) if mask is not None else all_inner_scaled
    residual_parts = [p for p in _parts(_valid(residual)) if p.area >= MIN_CIRCULATION_AREA_M2]

    type_counts: Counter = Counter()
    rooms: list[Room] = []

    def _room_from_poly(rtype: str, poly: Polygon) -> Room:
        idx = type_counts[rtype]
        type_counts[rtype] += 1
        minx, miny, maxx, maxy = poly.bounds
        return Room(
            id=f"{rtype}_{idx}", type=rtype,
            polygon=tuple((x, y) for x, y in poly.exterior.coords),
            area_m2=poly.area, width_m=maxx - minx, depth_m=maxy - miny,
            exterior_exposure=(), exposure_known=False,  # filled in once window data is known
        )

    for cand in candidates:
        rooms.append(_room_from_poly(cand.type, cand.polygon))
    for poly in residual_parts:
        rooms.append(_room_from_poly("CIRCULATION", poly))

    # ---- windows: room + footprint side, or UNKNOWN -------------------------------------------
    window_geom = _valid(plan.get("window"))
    window_polys = [_scale_poly(p, scale) for p in _parts(window_geom)]
    has_window_data = len(window_polys) > 0
    buf = wall_thickness_m * CONNECTOR_MATCH_BUFFER_WALLS
    side_tol = wall_thickness_m * BOUNDARY_TOLERANCE_WALLS

    windows: list[Window] = []
    exposure_by_room: dict[str, set[str]] = {r.id: set() for r in rooms}
    for i, wpoly in enumerate(window_polys):
        matched = _match_rooms_for_connector(wpoly, rooms, buf)
        room_id = matched[0] if len(matched) == 1 else (matched[0] if matched else None)
        side = _footprint_side(wpoly.centroid.coords[0], footprint_bounds, side_tol)
        windows.append(Window(id=f"WINDOW_{i}", polygon=tuple((x, y) for x, y in wpoly.exterior.coords),
                               room_id=room_id, side=side))
        if room_id is not None and side != "UNKNOWN":
            exposure_by_room[room_id].add(side)

    if has_window_data:
        rooms = [
            Room(id=r.id, type=r.type, polygon=r.polygon, area_m2=r.area_m2,
                 width_m=r.width_m, depth_m=r.depth_m,
                 exterior_exposure=tuple(sorted(exposure_by_room.get(r.id, ()))),
                 exposure_known=True)
            for r in rooms
        ]
    # else: leave exposure_known=False / exterior_exposure=() — UNKNOWN, no window data at all.

    # ---- doors: access edges between the rooms they touch -------------------------------------
    door_geom = _valid(plan.get("door"))
    door_polys = [_scale_poly(p, scale) for p in _parts(door_geom)]
    doors: list[Door] = []
    access_pairs: set[frozenset[str]] = set()
    for i, dpoly in enumerate(door_polys):
        matched = _match_rooms_for_connector(dpoly, rooms, buf)
        doors.append(Door(id=f"DOOR_{i}", polygon=tuple((x, y) for x, y in dpoly.exterior.coords),
                           room_ids=tuple(matched), is_exterior=len(matched) == 1))
        if len(matched) == 2:
            access_pairs.add(frozenset(matched))

    access_edges = tuple(
        AccessEdge(room_a=sorted(pair)[0], room_b=sorted(pair)[1], kind="DOOR")
        for pair in sorted(access_pairs, key=lambda s: sorted(s))
    )

    # ---- entrance: front_door -> room + footprint side, or UNKNOWN ----------------------------
    front_door = _valid(plan.get("front_door"))
    front_door_parts = _parts(front_door)
    if not front_door_parts:
        entrance = Entrance(room_id=None, side="UNKNOWN")
    else:
        fd_poly = _scale_poly(max(front_door_parts, key=lambda p: p.area), scale)
        fd_matched = _match_rooms_for_connector(fd_poly, rooms, buf)
        entrance_room = fd_matched[0] if fd_matched else None
        entrance_side = _footprint_side(fd_poly.centroid.coords[0], footprint_bounds, side_tol)
        entrance = Entrance(room_id=entrance_room, side=entrance_side)

    # ---- walls (as geometric components, for downstream use) ----------------------------------
    walls = tuple(
        WallSegment(id=f"WALL_{i}", polygon=tuple((x, y) for x, y in wp.exterior.coords))
        for i, wp in enumerate(scaled["wall"])
    )

    # ---- adjacency edges: rooms whose polygons are within ~one wall of each other -------------
    adjacency_pairs: set[frozenset[str]] = set()
    room_polys = {r.id: Polygon(r.polygon) for r in rooms}
    ids = list(room_polys.keys())
    gap = wall_thickness_m * 1.2
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if room_polys[a].distance(room_polys[b]) <= gap:
                adjacency_pairs.add(frozenset((a, b)))
    adjacency_edges = tuple(
        AdjacencyEdge(room_a=sorted(pair)[0], room_b=sorted(pair)[1])
        for pair in sorted(adjacency_pairs, key=lambda s: sorted(s))
    )

    room_type_counts = dict(Counter(r.type for r in rooms))
    derived = Derived(
        scale_m_per_px=scale, wall_thickness_m=wall_thickness_m,
        footprint_area_m2=all_inner_scaled.area, room_type_counts=room_type_counts,
    )
    provenance = Provenance(
        source_dataset="ResPlan", source_plan_id=plan_id, unit_type=str(unit_type),
        licence=RESPLAN_LICENCE, citation=RESPLAN_CITATION,
    )

    return PlanReference(
        plan_id=plan_id, footprint=footprint_ring, rooms=tuple(rooms), walls=walls,
        doors=tuple(doors), windows=tuple(windows), entrance=entrance,
        adjacency_edges=adjacency_edges, access_edges=access_edges,
        derived=derived, provenance=provenance,
    )
