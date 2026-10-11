"""Deterministic room/envelope shape measurement for Issue #102 (non-rectangular geometry
investigation). See docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md for the report this feeds.

Reads ``*.json`` files shaped ``{"plan_reference": {...}, "architectural_pattern": {...}}`` -- the
same schema ``spikes.architectural_brain.plan_reference.PlanReference.to_dict()`` produces on
branch ``integration/poc-architectural-brain`` (docs/reports/poc-architectural-brain/dataset.md).
This module has NO import dependency on that branch's code -- it reads the JSON directly, so it
runs standalone on this branch.

Default corpus directory is the 20-plan fixture committed at
``tests/spikes/fixtures/geometry_shapes/plans/`` (19 real ResPlan plans + 1 hand-built synthetic
"SPINE" plan, CC BY 4.0 -- see the ATTRIBUTION.md next to it): a real, reproducible, licensed
sample drawn from the POC's 199-plan corpus, small enough to commit directly into this branch
without depending on the (unmerged) POC branches. Point ``--corpus-dir`` at a larger corpus (e.g.
the POC's own ``backend/spikes/architectural_brain/corpus/``, once that work is integrated with
this branch) for a fuller remeasurement -- every share is reported with its own sample size so a
reader never mistakes a 19-plan measurement for the full 199/17,107-plan corpus.

Room-shape classification (per room, after 10 cm Douglas-Peucker vertex simplification):
    RECTANGLE  -- 4 vertices, fills >=97% of its own minimum rotated rectangle.
    L_SHAPED   -- 6 vertices, orthogonal edges, exactly one reflex (concave) vertex -- a single
                  notch removed from a rectangle.
    OTHER      -- everything else (more notches, non-orthogonal, or a degenerate ring).
    DEGENERATE -- zero-area or fewer than 3 vertices after simplification (reported, not silently
                  dropped).

Guillotine-separability (per plan's room layout): a room set is guillotine-separable when a
straight full-length cut (horizontal or vertical) exists that crosses no room's interior and
splits the rooms into two non-empty groups, recursively, down to singletons -- the standard
"slicing tree" recognition test. Cut candidates are every room's own bounding-box edge coordinate;
a room's own interior is tested via the *original* (non-simplified) polygon with a small negative
buffer, so digitisation noise in a wall run never manufactures a false "clean" cut.

Nothing here guesses: a plan/room a rule cannot evaluate (no rooms, a degenerate footprint) is
counted separately as UNKNOWN, never folded into RECTANGLE/OTHER by default.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import warnings
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient

SIMPLIFY_TOLERANCE_M = 0.10
RECTANGLE_FILL_RATIO_MIN = 0.97
ORTHOGONAL_ANGLE_TOLERANCE_DEG = 5.0
MIN_POLYGON_AREA_M2 = 1e-4
GUILLOTINE_CUT_EPS_M = 1e-6
INTERIOR_CROSS_BUFFER_M = 0.01

# A room polygon under this area is a digitisation artefact, not a real navigable room -- measured
# on the fixture corpus: 20/179 rooms are un-filtered LIVING fragments under 0.5 m^2 (the POC
# ingest only floors CIRCULATION components at 2.0 m^2 -- see resplan_ingest.py's
# MIN_CIRCULATION_AREA_M2 comment -- LIVING/KITCHEN/BEDROOM/BATHROOM carry no equivalent floor).
# Reported as its own category (ARTIFACT) rather than silently dropped or folded into OTHER, and
# every headline share is reported both with and without this filter -- see the investigation
# report's Measurement section for why this floor is necessary to read the guillotine result at
# all (an unfiltered sliver almost always defeats every candidate cut in its plan).
DIGITIZATION_ARTIFACT_AREA_M2 = 1.0

DEFAULT_CORPUS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests", "spikes", "fixtures", "geometry_shapes", "plans",
)

SYNTHETIC_PLAN_IDS = frozenset({"synthetic-spine-01"})

RECTANGLE = "RECTANGLE"
L_SHAPED = "L_SHAPED"
OTHER = "OTHER"
DEGENERATE = "DEGENERATE"
ARTIFACT = "ARTIFACT"


def _dedupe_closing_point(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(coords) >= 2 and coords[0] == coords[-1]:
        return coords[:-1]
    return coords


def _polygon_from_ring(ring: list) -> Polygon | None:
    pts = _dedupe_closing_point([(float(x), float(y)) for x, y in ring])
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.geom_type != "Polygon":
        # A self-intersecting (bowtie) ring's buffer(0) repair can split into several pieces
        # (MultiPolygon/GeometryCollection) -- not exercised by the 19-plan fixture, first seen on
        # the full 199-plan corpus (resplan_3728's BATHROOM_2). Keep the largest polygonal piece,
        # the standard repair for a self-intersecting digitisation ring, so area/shape
        # classification still runs on a single simple polygon.
        candidates = [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]
        if not candidates:
            return None
        poly = max(candidates, key=lambda g: g.area)
    if poly.is_empty or poly.area < MIN_POLYGON_AREA_M2:
        return None
    return poly


def _simplify(poly: Polygon, tolerance: float = SIMPLIFY_TOLERANCE_M) -> Polygon:
    simplified = poly.simplify(tolerance, preserve_topology=True)
    if simplified.geom_type != "Polygon" or simplified.is_empty:
        return poly
    return simplified


def _edge_is_axis_aligned(p0: tuple[float, float], p1: tuple[float, float],
                           tol_deg: float = ORTHOGONAL_ANGLE_TOLERANCE_DEG) -> bool:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-9:
        return True
    angle = math.degrees(math.atan2(abs(dy), abs(dx)))
    return angle <= tol_deg or angle >= (90.0 - tol_deg)


def classify_room_shape(ring: list, tolerance: float = SIMPLIFY_TOLERANCE_M) -> str:
    """Classify one room polygon (a raw ``Room.polygon`` ring) into RECTANGLE / L_SHAPED / OTHER /
    DEGENERATE after 10 cm vertex simplification. Pure and deterministic."""
    poly = _polygon_from_ring(ring)
    if poly is None:
        return DEGENERATE
    simplified = _simplify(poly, tolerance)
    if simplified.area < MIN_POLYGON_AREA_M2:
        return DEGENERATE

    oriented = orient(simplified, sign=1.0)
    coords = _dedupe_closing_point(list(oriented.exterior.coords))
    n = len(coords)
    if n < 3:
        return DEGENERATE

    if n == 4:
        with warnings.catch_warnings():
            # Shapely's oriented-envelope routine emits a benign divide-by-zero/invalid-value
            # numpy warning for perfectly axis-aligned inputs (the common case here) while still
            # returning the correct rectangle -- see patterns.py's _minimum_rotated_rectangle on
            # the POC branch for the same, independently-discovered workaround.
            warnings.simplefilter("ignore", RuntimeWarning)
            mrr = oriented.minimum_rotated_rectangle
        fill = oriented.area / mrr.area if mrr.area > 0 else 0.0
        return RECTANGLE if fill >= RECTANGLE_FILL_RATIO_MIN else OTHER

    if n == 6:
        edges_orthogonal = all(
            _edge_is_axis_aligned(coords[i], coords[(i + 1) % n]) for i in range(n)
        )
        if not edges_orthogonal:
            return OTHER
        reflex_count = 0
        for i in range(n):
            p0, p1, p2 = coords[i - 1], coords[i], coords[(i + 1) % n]
            v1 = (p1[0] - p0[0], p1[1] - p0[1])
            v2 = (p2[0] - p1[0], p2[1] - p1[1])
            cross = v1[0] * v2[1] - v1[1] * v2[0]
            if cross < -1e-9:
                reflex_count += 1
        return L_SHAPED if reflex_count == 1 else OTHER

    return OTHER


@dataclass
class RoomShapeResult:
    room_id: str
    room_type: str
    shape: str
    vertex_count_raw: int
    area_m2: float
    is_artifact: bool


@dataclass
class PlanShapeResult:
    plan_id: str
    is_synthetic: bool
    bedroom_count: int
    room_results: list[RoomShapeResult]
    envelope_shape: str
    guillotine_separable: bool | None  # None = UNKNOWN (fewer than 1 room with geometry)


def _room_polygons_for_guillotine(rooms: list[dict], min_area_m2: float) -> list[Polygon]:
    polys = []
    for room in rooms:
        if room["area_m2"] < min_area_m2:
            continue
        poly = _polygon_from_ring(room["polygon"])
        if poly is not None:
            polys.append(poly)
    return polys


def _crosses_interior(poly: Polygon, line: LineString) -> bool:
    shrunk = poly.buffer(-INTERIOR_CROSS_BUFFER_M)
    if shrunk.is_empty:
        return False
    return shrunk.intersects(line)


def _try_split(rooms: list[Polygon]) -> bool:
    if len(rooms) <= 1:
        return True

    minx = min(r.bounds[0] for r in rooms)
    maxx = max(r.bounds[2] for r in rooms)
    miny = min(r.bounds[1] for r in rooms)
    maxy = max(r.bounds[3] for r in rooms)
    pad = 1.0

    xs = sorted({round(r.bounds[0], 6) for r in rooms} | {round(r.bounds[2], 6) for r in rooms})
    ys = sorted({round(r.bounds[1], 6) for r in rooms} | {round(r.bounds[3], 6) for r in rooms})

    for x in xs:
        if x <= minx + GUILLOTINE_CUT_EPS_M or x >= maxx - GUILLOTINE_CUT_EPS_M:
            continue
        line = LineString([(x, miny - pad), (x, maxy + pad)])
        if any(_crosses_interior(r, line) for r in rooms):
            continue
        left = [r for r in rooms if r.bounds[2] <= x + GUILLOTINE_CUT_EPS_M]
        right = [r for r in rooms if r.bounds[0] >= x - GUILLOTINE_CUT_EPS_M]
        if left and right and len(left) + len(right) == len(rooms):
            if _try_split(left) and _try_split(right):
                return True

    for y in ys:
        if y <= miny + GUILLOTINE_CUT_EPS_M or y >= maxy - GUILLOTINE_CUT_EPS_M:
            continue
        line = LineString([(minx - pad, y), (maxx + pad, y)])
        if any(_crosses_interior(r, line) for r in rooms):
            continue
        below = [r for r in rooms if r.bounds[3] <= y + GUILLOTINE_CUT_EPS_M]
        above = [r for r in rooms if r.bounds[1] >= y - GUILLOTINE_CUT_EPS_M]
        if below and above and len(below) + len(above) == len(rooms):
            if _try_split(below) and _try_split(above):
                return True

    return False


def is_guillotine_separable(room_polygons: list[Polygon]) -> bool:
    """Whether a recursive sequence of straight, full-length cuts exists that never crosses a
    room's interior and reduces the room set to singletons -- the standard guillotine/slicing-tree
    recognition test, evaluated against each room's own (non-simplified) polygon."""
    return _try_split(room_polygons)


def measure_plan(plan_json: dict, min_room_area_m2: float = DIGITIZATION_ARTIFACT_AREA_M2) -> PlanShapeResult:
    ref = plan_json["plan_reference"]
    plan_id = ref["plan_id"]
    rooms = ref["rooms"]
    bedroom_count = int(ref["derived"]["room_type_counts"].get("BEDROOM", 0))

    room_results = [
        RoomShapeResult(
            room_id=room["id"], room_type=room["type"],
            shape=(ARTIFACT if room["area_m2"] < min_room_area_m2 else classify_room_shape(room["polygon"])),
            vertex_count_raw=len(_dedupe_closing_point([tuple(p) for p in room["polygon"]])),
            area_m2=room["area_m2"], is_artifact=room["area_m2"] < min_room_area_m2,
        )
        for room in rooms
    ]

    envelope_shape = classify_room_shape(ref["footprint"])

    room_polys = _room_polygons_for_guillotine(rooms, min_room_area_m2)
    guillotine = is_guillotine_separable(room_polys) if room_polys else None

    return PlanShapeResult(
        plan_id=plan_id,
        is_synthetic=plan_id in SYNTHETIC_PLAN_IDS
        or ref.get("provenance", {}).get("source_dataset") == "SYNTHETIC",
        bedroom_count=bedroom_count,
        room_results=room_results,
        envelope_shape=envelope_shape,
        guillotine_separable=guillotine,
    )


def load_corpus(corpus_dir: str) -> list[dict]:
    plans = []
    for name in sorted(os.listdir(corpus_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(corpus_dir, name)) as f:
            plans.append(json.load(f))
    return plans


@dataclass
class Summary:
    n_plans_total: int
    n_plans_real: int
    n_plans_3_5br: int
    room_shape_counts: dict[str, int] = field(default_factory=dict)
    room_shape_counts_3_5br: dict[str, int] = field(default_factory=dict)
    envelope_shape_counts: dict[str, int] = field(default_factory=dict)
    guillotine_counts: dict[str, int] = field(default_factory=dict)
    n_rooms_total: int = 0
    n_rooms_3_5br: int = 0


def summarize(results: list[PlanShapeResult]) -> Summary:
    real_results = [r for r in results if not r.is_synthetic]
    subset_3_5 = [r for r in real_results if 3 <= r.bedroom_count <= 5]

    summary = Summary(
        n_plans_total=len(results), n_plans_real=len(real_results),
        n_plans_3_5br=len(subset_3_5),
    )

    for r in real_results:
        for room in r.room_results:
            summary.room_shape_counts[room.shape] = summary.room_shape_counts.get(room.shape, 0) + 1
            summary.n_rooms_total += 1
        summary.envelope_shape_counts[r.envelope_shape] = (
            summary.envelope_shape_counts.get(r.envelope_shape, 0) + 1
        )
        key = "UNKNOWN" if r.guillotine_separable is None else str(r.guillotine_separable)
        summary.guillotine_counts[key] = summary.guillotine_counts.get(key, 0) + 1

    for r in subset_3_5:
        for room in r.room_results:
            summary.room_shape_counts_3_5br[room.shape] = (
                summary.room_shape_counts_3_5br.get(room.shape, 0) + 1
            )
            summary.n_rooms_3_5br += 1

    return summary


def _share(counts: dict[str, int], key: str, total: int) -> str:
    if total == 0:
        return "UNKNOWN (n=0)"
    n = counts.get(key, 0)
    return f"{n}/{total} ({100.0 * n / total:.1f}%)"


def format_report(summary: Summary) -> str:
    lines = [
        f"plans measured: {summary.n_plans_total} total "
        f"({summary.n_plans_real} real ResPlan, "
        f"{summary.n_plans_total - summary.n_plans_real} synthetic, excluded from shape stats)",
        f"3-5 bedroom subset (real plans only): {summary.n_plans_3_5br}/{summary.n_plans_real}",
        "",
        "room shapes (all real plans, n=%d rooms):" % summary.n_rooms_total,
        f"  RECTANGLE: {_share(summary.room_shape_counts, RECTANGLE, summary.n_rooms_total)}",
        f"  L_SHAPED:  {_share(summary.room_shape_counts, L_SHAPED, summary.n_rooms_total)}",
        f"  OTHER:     {_share(summary.room_shape_counts, OTHER, summary.n_rooms_total)}",
        f"  DEGENERATE:{_share(summary.room_shape_counts, DEGENERATE, summary.n_rooms_total)}",
        f"  ARTIFACT:  {_share(summary.room_shape_counts, ARTIFACT, summary.n_rooms_total)}"
        f" (area < {DIGITIZATION_ARTIFACT_AREA_M2} m2, excluded from the guillotine test)",
        "",
        "room shapes (3-5 bedroom subset, n=%d rooms):" % summary.n_rooms_3_5br,
        f"  RECTANGLE: {_share(summary.room_shape_counts_3_5br, RECTANGLE, summary.n_rooms_3_5br)}",
        f"  L_SHAPED:  {_share(summary.room_shape_counts_3_5br, L_SHAPED, summary.n_rooms_3_5br)}",
        f"  OTHER:     {_share(summary.room_shape_counts_3_5br, OTHER, summary.n_rooms_3_5br)}",
        f"  ARTIFACT:  {_share(summary.room_shape_counts_3_5br, ARTIFACT, summary.n_rooms_3_5br)}",
        "",
        "envelope shapes (n=%d plans):" % summary.n_plans_real,
        f"  RECTANGLE: {_share(summary.envelope_shape_counts, RECTANGLE, summary.n_plans_real)}",
        f"  L_SHAPED:  {_share(summary.envelope_shape_counts, L_SHAPED, summary.n_plans_real)}",
        f"  OTHER:     {_share(summary.envelope_shape_counts, OTHER, summary.n_plans_real)}",
        "",
        "guillotine-separable room layout (n=%d plans):" % summary.n_plans_real,
        f"  True:    {_share(summary.guillotine_counts, 'True', summary.n_plans_real)}",
        f"  False:   {_share(summary.guillotine_counts, 'False', summary.n_plans_real)}",
        f"  UNKNOWN: {_share(summary.guillotine_counts, 'UNKNOWN', summary.n_plans_real)}",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--json", action="store_true", help="print per-plan JSON instead of the summary table")
    parser.add_argument("--min-room-area-m2", type=float, default=DIGITIZATION_ARTIFACT_AREA_M2,
                         help="rooms below this area are reported as ARTIFACT and excluded from "
                              "the guillotine test (0 disables the filter)")
    args = parser.parse_args()

    plans = load_corpus(args.corpus_dir)
    results = [measure_plan(p, min_room_area_m2=args.min_room_area_m2) for p in plans]

    if args.json:
        print(json.dumps(
            [
                {
                    "plan_id": r.plan_id, "is_synthetic": r.is_synthetic,
                    "bedroom_count": r.bedroom_count, "envelope_shape": r.envelope_shape,
                    "guillotine_separable": r.guillotine_separable,
                    "rooms": [
                        {"room_id": rr.room_id, "room_type": rr.room_type, "shape": rr.shape,
                         "vertex_count_raw": rr.vertex_count_raw}
                        for rr in r.room_results
                    ],
                }
                for r in results
            ],
            indent=2,
        ))
        return

    summary = summarize(results)
    print(format_report(summary))


if __name__ == "__main__":
    main()
