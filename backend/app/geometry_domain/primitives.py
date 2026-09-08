"""Authoritative geometry primitives: Vertex / BoundaryEdge / Ring / Region / MultiRegion.

Implements the representation recommended by `GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md` §2.

WHY BULGE, restated at the point of use (it is the single most consequential choice here):

  * `bulge = tan(theta/4)`, one signed scalar per edge, where theta is the arc's included angle.
  * `bulge == 0` IS a straight line. LINE and ARC are one primitive with a parameter, not two
    cases with a branch, so no algorithm below needs `if edge.is_arc`.
  * The ENDPOINTS ARE AUTHORITATIVE. Curvature never competes with them as a source of endpoint
    truth. A center+radius+start_angle+end_angle form derives its endpoints, so a vertex edit or
    a snap silently desynchronizes it from the ring and opens a sub-millimetre gap — which
    destroys point-in-region, area, and every boolean, non-reproducibly.
  * Edges reference vertex IDs, they never store their own coordinates. A gap between adjacent
    edges is therefore unrepresentable rather than merely discouraged.
  * Bulge is INVARIANT under translation, rotation and uniform scale (see transforms.py), so a
    transform touches only the vertex list. There is no second place holding curvature that a
    transform could forget to update. Mirroring negates it, and that is the entire story.

Coordinates are METRES (float). Grid units belong to the solver, not here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .provenance import Provenance

_EPS = 1e-9
#: Angular tolerance when testing whether an extreme point lies on an arc.
_ANG_EPS = 1e-9

Point = tuple[float, float]


class GeometryValidationError(ValueError):
    """Raised when geometry is structurally invalid. Always names the offending element."""


# --------------------------------------------------------------------------- vertices & edges

@dataclass(frozen=True)
class Vertex:
    id: str
    x: float
    y: float

    def as_point(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class BoundaryEdge:
    """One boundary element. `bulge == 0` -> straight segment; otherwise a circular arc.

    Provenance is per edge (report §5): a boundary may be part surveyed, part user-drawn.
    """

    start: str  # vertex id
    end: str    # vertex id
    bulge: float = 0.0
    provenance: Provenance | None = None

    @property
    def is_line(self) -> bool:
        return abs(self.bulge) <= _EPS

    @property
    def is_major_arc(self) -> bool:
        """|bulge| > 1 means the arc exceeds 180 degrees. Report §2 requires such arcs to be
        split before any simplification or offsetting; this flag is how a future adapter finds
        them."""
        return abs(self.bulge) > 1.0 + _EPS


# --------------------------------------------------------------------------- arc mathematics
#
# Everything below is derived from (p0, p1, bulge) alone. Note in particular that sagitta and
# segment area — the two quantities a conservative simplifier needs in order to decide what a
# chord substitution would cost — are available WITHOUT computing the centre, which is
# ill-conditioned for shallow arcs (the centre flies to infinity as bulge -> 0).


def chord_length(p0: Point, p1: Point) -> float:
    return math.hypot(p1[0] - p0[0], p1[1] - p0[1])


def _unit_and_left_normal(p0: Point, p1: Point) -> tuple[Point, Point, float]:
    d = chord_length(p0, p1)
    if d <= _EPS:
        raise GeometryValidationError(f"degenerate edge: endpoints coincide at {p0}")
    ux, uy = (p1[0] - p0[0]) / d, (p1[1] - p0[1]) / d
    return (ux, uy), (-uy, ux), d


def included_angle(bulge: float) -> float:
    """Signed included angle theta = 4*atan(bulge). Positive = counter-clockwise."""
    return 4.0 * math.atan(bulge)


def arc_radius(p0: Point, p1: Point, bulge: float) -> float:
    if abs(bulge) <= _EPS:
        return math.inf
    d = chord_length(p0, p1)
    return d * (1.0 + bulge * bulge) / (4.0 * abs(bulge))


def arc_sagitta(p0: Point, p1: Point, bulge: float) -> float:
    """Maximum deviation of the arc from its chord: s = |bulge| * d / 2.

    This is exactly the depth a chord substitution would lose (report §3). No trigonometry, no
    centre, well-conditioned at every bulge including ~0.
    """
    return abs(bulge) * chord_length(p0, p1) / 2.0


def arc_apex(p0: Point, p1: Point, bulge: float) -> Point:
    """The arc's midpoint — the point furthest from the chord."""
    (ux, uy), (nx, ny), d = _unit_and_left_normal(p0, p1)
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    off = bulge * d / 2.0
    return (mx - off * nx, my - off * ny)


def arc_center(p0: Point, p1: Point, bulge: float) -> Point:
    """Derived on demand, never stored (report §2). Ill-conditioned as bulge -> 0, which is why
    nothing in this module routes a shallow-arc computation through it."""
    if abs(bulge) <= _EPS:
        raise GeometryValidationError("a straight edge (bulge == 0) has no arc centre")
    (ux, uy), (nx, ny), d = _unit_and_left_normal(p0, p1)
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    h = d * (1.0 - bulge * bulge) / (4.0 * bulge)
    return (mx + h * nx, my + h * ny)


def arc_segment_area(p0: Point, p1: Point, bulge: float) -> float:
    """Signed area between the chord and the arc.

    Sign convention: on a counter-clockwise ring a positive bulge bulges OUTWARD and therefore
    ADDS area. (Checked in tests against a full circle built from two bulge=+1 edges.)
    """
    if abs(bulge) <= _EPS:
        return 0.0
    theta = included_angle(bulge)
    r = arc_radius(p0, p1, bulge)
    return 0.5 * r * r * (theta - math.sin(theta))


def bulge_from_three_points(p0: Point, mid: Point, p1: Point) -> float:
    """INGEST ONLY. Surveyors and CAD exports often give start/mid/end; convert immediately and
    store bulge (report §2 — three-point is a fine input form and a poor storage form).

    `mid` is taken to be the arc's midpoint (its apex). Collinear input yields bulge 0, i.e. a
    straight edge, with no special case needed by the caller.
    """
    (ux, uy), (nx, ny), d = _unit_and_left_normal(p0, p1)
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    proj = (mid[0] - mx) * nx + (mid[1] - my) * ny
    return -2.0 * proj / d


def _angle_of(center: Point, p: Point) -> float:
    return math.atan2(p[1] - center[1], p[0] - center[0])


def _arc_contains_angle(a0: float, theta: float, phi: float) -> bool:
    """Is angle `phi` on the arc that starts at `a0` and sweeps by signed `theta`?"""
    two_pi = 2.0 * math.pi
    if theta >= 0:
        delta = (phi - a0) % two_pi
        return delta <= theta + _ANG_EPS
    delta = (a0 - phi) % two_pi
    return delta <= -theta + _ANG_EPS


def arc_bounds(p0: Point, p1: Point, bulge: float) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) of one edge, INCLUDING the arc's own extremes.

    An arc can reach beyond both of its endpoints, so a bounding box taken over vertices alone
    is wrong — for a circle expressed as two arcs it would be a degenerate line.
    """
    xs = [p0[0], p1[0]]
    ys = [p0[1], p1[1]]
    if abs(bulge) > _EPS:
        c = arc_center(p0, p1, bulge)
        r = arc_radius(p0, p1, bulge)
        a0 = _angle_of(c, p0)
        theta = included_angle(bulge)
        for phi, (dx, dy) in (
            (0.0, (1.0, 0.0)),
            (math.pi / 2, (0.0, 1.0)),
            (math.pi, (-1.0, 0.0)),
            (-math.pi / 2, (0.0, -1.0)),
        ):
            if _arc_contains_angle(a0, theta, phi):
                xs.append(c[0] + r * dx)
                ys.append(c[1] + r * dy)
    return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------- ring

@dataclass(frozen=True)
class Ring:
    """A closed chain of boundary edges over a shared vertex table.

    Orientation carries meaning: counter-clockwise (positive signed area) = material, clockwise
    = hole. `Region` normalizes this rather than trusting callers.
    """

    vertices: tuple[Vertex, ...]
    edges: tuple[BoundaryEdge, ...]

    def __post_init__(self) -> None:
        self.validate()

    # -- construction helpers -------------------------------------------------------------

    @staticmethod
    def from_points(points: list[Point], bulges: list[float] | None = None,
                    prefix: str = "v", provenance: Provenance | None = None) -> "Ring":
        """Closed ring through `points`; `bulges[i]` applies to the edge leaving `points[i]`."""
        if bulges is None:
            bulges = [0.0] * len(points)
        if len(bulges) != len(points):
            raise GeometryValidationError(
                f"got {len(points)} points but {len(bulges)} bulges — one bulge per edge is required"
            )
        verts = tuple(Vertex(f"{prefix}{i}", x, y) for i, (x, y) in enumerate(points))
        edges = tuple(
            BoundaryEdge(verts[i].id, verts[(i + 1) % len(verts)].id, bulges[i], provenance)
            for i in range(len(verts))
        )
        return Ring(verts, edges)

    @staticmethod
    def rectangle(x: float, y: float, w: float, h: float, prefix: str = "v",
                  provenance: Provenance | None = None) -> "Ring":
        """A rectangle is one representable special case of general geometry, not a separate
        language (report §11 / task §11)."""
        return Ring.from_points(
            [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], prefix=prefix, provenance=provenance
        )

    @staticmethod
    def circle(cx: float, cy: float, r: float, prefix: str = "v",
               provenance: Provenance | None = None) -> "Ring":
        """Two bulge=+1 semicircles. A clearance disc needs no new primitive — a direct payoff
        of putting arcs in the edge model (report §4)."""
        return Ring.from_points([(cx + r, cy), (cx - r, cy)], [1.0, 1.0], prefix, provenance)

    # -- access ---------------------------------------------------------------------------

    def vertex(self, vertex_id: str) -> Vertex:
        for v in self.vertices:
            if v.id == vertex_id:
                return v
        raise GeometryValidationError(f"edge references unknown vertex id {vertex_id!r}")

    def edge_geometry(self) -> list[tuple[Point, Point, float]]:
        return [
            (self.vertex(e.start).as_point(), self.vertex(e.end).as_point(), e.bulge)
            for e in self.edges
        ]

    def chord_points(self) -> list[Point]:
        return [self.vertex(e.start).as_point() for e in self.edges]

    # -- validation -----------------------------------------------------------------------

    def validate(self) -> None:
        if len(self.edges) < 2:
            raise GeometryValidationError(
                f"a ring needs at least 2 edges, got {len(self.edges)} — a closed boundary "
                f"cannot be formed from fewer"
            )
        ids = [v.id for v in self.vertices]
        if len(set(ids)) != len(ids):
            raise GeometryValidationError(f"duplicate vertex ids in ring: {ids}")
        for i, e in enumerate(self.edges):
            self.vertex(e.start)
            self.vertex(e.end)
            nxt = self.edges[(i + 1) % len(self.edges)]
            if e.end != nxt.start:
                raise GeometryValidationError(
                    f"ring is not closed: edge {i} ends at {e.end!r} but edge "
                    f"{(i + 1) % len(self.edges)} starts at {nxt.start!r}"
                )
            if chord_length(self.vertex(e.start).as_point(), self.vertex(e.end).as_point()) <= _EPS:
                raise GeometryValidationError(f"edge {i} is degenerate: {e.start!r} == {e.end!r}")
        if len(self.edges) == 2 and all(e.is_line for e in self.edges):
            raise GeometryValidationError(
                "a 2-edge ring of straight lines encloses no area; at least one edge must be an arc"
            )

    # -- measurement ----------------------------------------------------------------------

    def signed_area(self) -> float:
        """Shoelace over the chord polygon, plus each arc's signed circular-segment area."""
        pts = self.chord_points()
        acc = 0.0
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            acc += x1 * y2 - x2 * y1
        area = acc / 2.0
        for p0, p1, bulge in self.edge_geometry():
            area += arc_segment_area(p0, p1, bulge)
        return area

    def area(self) -> float:
        return abs(self.signed_area())

    def is_ccw(self) -> bool:
        return self.signed_area() > 0

    def bounds(self) -> tuple[float, float, float, float]:
        boxes = [arc_bounds(p0, p1, b) for p0, p1, b in self.edge_geometry()]
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )

    def reversed(self) -> "Ring":
        """Flip traversal direction. Bulge negates because the arc now sweeps the other way."""
        new_edges = tuple(
            BoundaryEdge(e.end, e.start, -e.bulge, e.provenance) for e in reversed(self.edges)
        )
        return Ring(self.vertices, new_edges)

    def oriented(self, ccw: bool) -> "Ring":
        return self if self.is_ccw() == ccw else self.reversed()

    def contains_point(self, p: Point) -> bool:
        """Even-odd ray cast against the TRUE boundary, arcs included.

        An earlier implementation cast against the chord polygon and then flipped once per
        circular segment. That is wrong for any point lying exactly on a chord: a circle
        expressed as two semicircles puts its own centre on both chords, so the two flips
        cancelled and the centre of a circle reported as outside it. Casting against the real
        boundary has no such degenerate case.

        Each arc is split at its y-extremes into y-monotone pieces, and every piece then obeys
        exactly the same half-open crossing rule as a straight edge — which is what keeps
        vertices shared between adjacent edges from being counted twice.
        """
        crossings = 0
        for p0, p1, bulge in self.edge_geometry():
            if abs(bulge) <= _EPS:
                crossings += _line_ray_crossings(p0, p1, p)
            else:
                crossings += _arc_ray_crossings(p0, p1, bulge, p)
        return crossings % 2 == 1


def _line_ray_crossings(p0: Point, p1: Point, p: Point) -> int:
    """Half-open rule: the edge counts when it spans `p.y` in [lower, upper)."""
    px, py = p
    (x0, y0), (x1, y1) = p0, p1
    if (y0 > py) == (y1 > py):
        return 0
    x_int = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
    return 1 if x_int > px else 0


def _arc_ray_crossings(p0: Point, p1: Point, bulge: float, p: Point) -> int:
    px, py = p
    c = arc_center(p0, p1, bulge)
    r = arc_radius(p0, p1, bulge)
    dy = py - c[1]
    if abs(dy) > r:
        return 0  # the ray's line misses the circle entirely

    a0 = _angle_of(c, p0)
    theta = included_angle(bulge)
    direction = 1.0 if theta >= 0 else -1.0
    span = abs(theta)

    # Split offsets: the ends, plus any y-extreme of the circle that the arc actually reaches.
    offsets = [0.0, span]
    for phi in (math.pi / 2, -math.pi / 2):
        t = ((phi - a0) * direction) % (2 * math.pi)
        if _EPS < t < span - _EPS:
            offsets.append(t)
    offsets.sort()

    dx = math.sqrt(max(0.0, r * r - dy * dy))
    candidates = (c[0] + dx, c[0] - dx)

    crossings = 0
    for t_start, t_end in zip(offsets, offsets[1:]):
        ys = c[1] + r * math.sin(a0 + direction * t_start)
        ye = c[1] + r * math.sin(a0 + direction * t_end)
        if (ys > py) == (ye > py):
            continue  # this monotone piece does not span the ray
        for x_cand in candidates:
            phi = math.atan2(py - c[1], x_cand - c[0])
            t = ((phi - a0) * direction) % (2 * math.pi)
            if t_start - _EPS <= t <= t_end + _EPS:
                if x_cand > px:
                    crossings += 1
                break
    return crossings


# --------------------------------------------------------------------------- region

@dataclass(frozen=True)
class Region:
    """One outer boundary with zero or more holes.

    Holes are first-class because they are not an edge case: a protected tree with a clearance
    radius, a shaft, or an easement crossing a parcel all punch a hole (report §1/§4).
    """

    outer: Ring
    holes: tuple[Ring, ...] = ()

    def normalized(self) -> "Region":
        """Outer counter-clockwise, holes clockwise, so `area()` is simply the sum."""
        return Region(self.outer.oriented(True), tuple(h.oriented(False) for h in self.holes))

    def area(self) -> float:
        norm = self.normalized()
        return norm.outer.signed_area() + sum(h.signed_area() for h in norm.holes)

    def bounds(self) -> tuple[float, float, float, float]:
        return self.outer.bounds()

    def contains_point(self, p: Point) -> bool:
        if not self.outer.contains_point(p):
            return False
        return not any(h.contains_point(p) for h in self.holes)

    def validate(self) -> None:
        self.outer.validate()
        for i, hole in enumerate(self.holes):
            hole.validate()
            for v in hole.vertices:
                if not self.outer.contains_point(v.as_point()):
                    raise GeometryValidationError(
                        f"hole {i} has vertex {v.id!r} at ({v.x}, {v.y}) outside the outer boundary"
                    )


@dataclass(frozen=True)
class MultiRegion:
    """One or more disjoint regions.

    Every boolean result is a MultiRegion, never "usually a Region" — an inward setback offset
    routinely SPLITS a pinched parcel into two components, and an obstacle can do the same. If
    the return type could not express that, the disconnection case would be silently handled by
    whichever caller happened to notice first (report §1, §7 cases 5 and 7).
    """

    regions: tuple[Region, ...] = ()

    @staticmethod
    def of(*regions: Region) -> "MultiRegion":
        return MultiRegion(tuple(regions))

    @property
    def is_empty(self) -> bool:
        return len(self.regions) == 0

    @property
    def component_count(self) -> int:
        return len(self.regions)

    @property
    def is_connected(self) -> bool:
        return len(self.regions) == 1

    def area(self) -> float:
        return sum(r.area() for r in self.regions)

    def bounds(self) -> tuple[float, float, float, float]:
        if not self.regions:
            raise GeometryValidationError("an empty MultiRegion has no bounds")
        boxes = [r.bounds() for r in self.regions]
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )

    def contains_point(self, p: Point) -> bool:
        return any(r.contains_point(p) for r in self.regions)

    def validate(self) -> None:
        for r in self.regions:
            r.validate()
