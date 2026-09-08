"""Conservative linearization of bulge arcs.

THE CENTRAL SAFETY RULE OF THE WHOLE ADAPTER LIVES HERE.

A `Ring` is normalized before use so that the MATERIAL IS ALWAYS ON THE LEFT of travel (outer
rings counter-clockwise, holes clockwise). That single convention makes the arc classification
uniform, because the apex of an edge sits at offset `-bulge*d/2` along the left normal:

    bulge > 0  ->  apex on the RIGHT  ->  arc bulges AWAY from the material  (convex)
    bulge < 0  ->  apex on the LEFT   ->  arc bites INTO the material        (concave)

This is why the architecture report insisted safety cannot be read off the bulge sign alone: the
sign is only meaningful AFTER orientation is normalized. A hole ring authored counter-clockwise
carries the opposite meaning until it is flipped, which is exactly how an exclusion disc would
otherwise be mistaken for a convex façade.

Given that, the conservative construction is a two-by-two table with no exceptions:

                    | convex arc (b>0)     | concave arc (b<0)
    ----------------+----------------------+----------------------
    INNER (subset)  | inscribed chords     | circumscribing tangents
    OUTER (superset)| circumscribing tangents | inscribed chords

INNER is what a KEPT region needs (parcel, buildable envelope). OUTER is what a SUBTRACTED
region needs (setback, exclusion, obstacle), because subtracting a superset removes at least as
much as the truth. Composing them keeps the whole boolean expression conservative:

    P_inner \\ (S_outer u E_outer)  =  subset of  P \\ (S u E)

Note on major arcs: the architecture report recommended splitting arcs at |bulge| = 1 before
simplification. That recommendation is unnecessary here and was NOT implemented, because this
module parameterizes by ANGLE rather than by chord — a 300-degree arc is subdivided by angular
span like any other, with no special case. The split rule was an artifact of chord-based
reasoning.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .primitives import (
    BoundaryEdge,
    MultiRegion,
    Region,
    Ring,
    Vertex,
    arc_center,
    arc_radius,
    included_angle,
)

_EPS = 1e-12
#: Hard cap so a pathological tolerance cannot explode the vertex count.
MAX_SEGMENTS_PER_ARC = 256
#: Keep each subdivision under a right angle: the tangent-chain vertex sits at R/cos(delta/2),
#: which diverges as delta approaches pi.
_MAX_DELTA = math.pi / 2


class ApproxDirection(str, Enum):
    #: Result is a SUBSET of the source. Use for regions being KEPT.
    INNER = "INNER"
    #: Result is a SUPERSET of the source. Use for regions being SUBTRACTED.
    OUTER = "OUTER"


@dataclass(frozen=True)
class ApproximationReport:
    tolerance_m: float
    arcs_linearized: int
    segments_generated: int
    max_deviation_m: float
    area_before_m2: float
    area_after_m2: float

    @property
    def area_delta_m2(self) -> float:
        """Negative when area was given up (INNER), positive when added (OUTER)."""
        return round(self.area_after_m2 - self.area_before_m2, 6)


def _segment_count(span: float, radius: float, tolerance_m: float, inscribe: bool) -> int:
    """Smallest n whose maximum deviation from the true arc is within tolerance."""
    if tolerance_m <= 0:
        n = MAX_SEGMENTS_PER_ARC
    elif inscribe:
        # deviation = R * (1 - cos(delta/2))
        ratio = 1.0 - tolerance_m / radius
        delta_max = 2.0 * math.acos(max(-1.0, min(1.0, ratio))) if ratio > -1.0 else math.pi
        n = 1 if delta_max <= 0 else math.ceil(span / delta_max)
    else:
        # deviation = R * (1/cos(delta/2) - 1)
        ratio = radius / (radius + tolerance_m)
        delta_max = 2.0 * math.acos(max(-1.0, min(1.0, ratio)))
        n = 1 if delta_max <= 0 else math.ceil(span / delta_max)
    n = max(n, math.ceil(span / _MAX_DELTA))
    return max(1, min(int(n), MAX_SEGMENTS_PER_ARC))


def arc_polyline(p0: tuple[float, float], p1: tuple[float, float], bulge: float,
                 *, inscribe: bool, tolerance_m: float) -> tuple[list[tuple[float, float]], float]:
    """Points from p0 to p1 inclusive, plus the maximum deviation actually incurred.

    `inscribe=True` samples points ON the arc and joins them with chords (the polyline lies on
    the concave side of the arc). `inscribe=False` builds a chain of TANGENT segments whose
    vertices sit at radius R/cos(delta/2) (the polyline lies on the convex side, touching the
    arc only at the tangent points).
    """
    c = arc_center(p0, p1, bulge)
    r = arc_radius(p0, p1, bulge)
    theta = included_angle(bulge)
    span = abs(theta)
    sign = 1.0 if theta >= 0 else -1.0
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])

    n = _segment_count(span, r, tolerance_m, inscribe)
    delta = span / n

    if inscribe:
        pts = [
            (c[0] + r * math.cos(a0 + sign * span * i / n),
             c[1] + r * math.sin(a0 + sign * span * i / n))
            for i in range(n + 1)
        ]
        deviation = r * (1.0 - math.cos(delta / 2.0))
    else:
        out_r = r / math.cos(delta / 2.0)
        pts = [p0]
        for i in range(n):
            mid = a0 + sign * span * (i + 0.5) / n
            pts.append((c[0] + out_r * math.cos(mid), c[1] + out_r * math.sin(mid)))
        pts.append(p1)
        deviation = out_r - r

    # Pin the true endpoints: they are authoritative and must not drift by float error.
    pts[0] = p0
    pts[-1] = p1
    return pts, deviation


def linearize_ring(ring: Ring, direction: ApproxDirection, tolerance_m: float,
                   ) -> tuple[Ring, int, int, float]:
    """Returns (linear ring, arcs_linearized, segments_generated, max_deviation).

    The ring MUST already be oriented so the material is on the left; `linearize_region`
    guarantees that. Passing a mis-oriented ring silently inverts the safety rule, which is why
    this is not part of the public surface.
    """
    points: list[tuple[float, float]] = []
    arcs = 0
    segments = 0
    max_dev = 0.0

    for p0, p1, bulge in ring.edge_geometry():
        if abs(bulge) <= _EPS:
            points.append(p0)
            segments += 1
            continue
        convex = bulge > 0  # bulges away from the material (see module docstring)
        inscribe = (direction is ApproxDirection.INNER) == convex
        pts, dev = arc_polyline(p0, p1, bulge, inscribe=inscribe, tolerance_m=tolerance_m)
        points.extend(pts[:-1])  # p1 is contributed by the next edge's p0
        arcs += 1
        segments += len(pts) - 1
        max_dev = max(max_dev, dev)

    deduped = _dedupe(points)
    verts = tuple(Vertex(f"{id(ring):x}_{i}", x, y) for i, (x, y) in enumerate(deduped))
    edges = tuple(
        BoundaryEdge(verts[i].id, verts[(i + 1) % len(verts)].id, 0.0)
        for i in range(len(verts))
    )
    return Ring(verts, edges), arcs, segments, max_dev


def _dedupe(points: list[tuple[float, float]], tol: float = 1e-9) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(p)
    while len(out) > 3 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def linearize_region(region: Region, direction: ApproxDirection,
                     tolerance_m: float) -> tuple[Region, ApproximationReport]:
    normalized = region.normalized()  # material on the left for every ring
    outer, arcs, segs, dev = linearize_ring(normalized.outer, direction, tolerance_m)
    holes = []
    for hole in normalized.holes:
        h, a, s, d = linearize_ring(hole, direction, tolerance_m)
        holes.append(h)
        arcs += a
        segs += s
        dev = max(dev, d)
    result = Region(outer, tuple(holes))
    return result, ApproximationReport(
        tolerance_m=tolerance_m, arcs_linearized=arcs, segments_generated=segs,
        max_deviation_m=dev, area_before_m2=region.area(), area_after_m2=result.area(),
    )


def linearize_multiregion(multi: MultiRegion, direction: ApproxDirection,
                          tolerance_m: float) -> tuple[MultiRegion, ApproximationReport]:
    regions = []
    arcs = segs = 0
    dev = 0.0
    for region in multi.regions:
        linear, rep = linearize_region(region, direction, tolerance_m)
        regions.append(linear)
        arcs += rep.arcs_linearized
        segs += rep.segments_generated
        dev = max(dev, rep.max_deviation_m)
    out = MultiRegion(tuple(regions))
    return out, ApproximationReport(
        tolerance_m=tolerance_m, arcs_linearized=arcs, segments_generated=segs,
        max_deviation_m=dev, area_before_m2=multi.area(), area_after_m2=out.area(),
    )
