"""The buildable envelope as an ORTHOGONAL POLYGON — the one input the shape-agnostic realizer
needs that nothing in the pipeline had (ADR-001, #197).

Every stage after placement already consumes a footprint as a union of rectangles
(`footprint.py`); what was missing is the OTHER side of that fact — a description of where the
building MAY be that is not itself a rectangle. `site_geometry.py` produces a rectangle (setbacks
on a rectangular parcel); this type takes that rectangle as its degenerate case and any orthogonal
polygon otherwise. Coordinates follow the plan frame the whole pipeline uses: metres, origin at the
north-west corner, x east, y toward the garden, the street along y = 0.

Only one question is asked of it, and it is asked in grid units: *over this range of depths,
which horizontal intervals lie inside the envelope?* The answer is CONSERVATIVE over the range —
the intersection of the cross-sections, so a band whose exact depth is not yet known is never
allowed where some depth in its range would leave the envelope — and exact when the range is a
single band at a fixed depth. More than one interval (a court, a north/south-opening U) is reported
as such, never silently collapsed to the widest one: whether a solver can use a split extent is the
solver's declared limit, not this module's to hide.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Polygon, box

from .geometry_core.model import UNIT_M, Rect, m_to_u, u_to_m

#: Sampling step, in units, when intersecting cross-sections over a depth range. Orthogonal
#: polygon edges lie on vertex y's, so sampling every vertex y inside the range plus both ends is
#: exact; this step is only a guard for a range that contains no vertex.
_EPS_M = 1e-6


@dataclass(frozen=True)
class Envelope:
    """An orthogonal polygon in metres (vertices in order, no holes), with the facts the sizer
    asks for pre-computed in grid units."""

    vertices_m: tuple[tuple[float, float], ...]

    @staticmethod
    def rectangle(width_m: float, depth_m: float) -> "Envelope":
        return Envelope(((0.0, 0.0), (width_m, 0.0), (width_m, depth_m), (0.0, depth_m)))

    @property
    def polygon(self) -> Polygon:
        return Polygon(self.vertices_m)

    @property
    def is_orthogonal(self) -> bool:
        vs = list(self.vertices_m)
        n = len(vs)
        for i in range(n):
            (x0, y0), (x1, y1) = vs[i], vs[(i + 1) % n]
            if abs(x0 - x1) > _EPS_M and abs(y0 - y1) > _EPS_M:
                return False
        return True

    @property
    def bbox_u(self) -> Rect:
        minx, miny, maxx, maxy = self.polygon.bounds
        return Rect(m_to_u(minx), m_to_u(miny), m_to_u(maxx - minx), m_to_u(maxy - miny))

    @property
    def depth_u(self) -> int:
        return self.bbox_u.h

    @property
    def width_u(self) -> int:
        return self.bbox_u.w

    @property
    def area_m2(self) -> float:
        return float(self.polygon.area)

    def _cross_section_u(self, y_u: int) -> list[tuple[int, int]]:
        """Horizontal intervals inside the polygon at depth `y_u` (a horizontal line), in units,
        relative to the bbox's west edge. Taken a hair inside the line so an edge lying exactly on
        `y_u` counts for the band that contains it, not for the one that merely touches it."""
        minx, miny, maxx, _ = self.polygon.bounds
        y = miny + y_u * UNIT_M + _EPS_M
        line = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
        cut = self.polygon.intersection(line)
        parts = [cut] if cut.geom_type == "LineString" else list(getattr(cut, "geoms", ()))
        out = []
        for p in parts:
            if p.is_empty or p.geom_type != "LineString":
                continue
            xs = [c[0] for c in p.coords]
            lo, hi = min(xs), max(xs)
            out.append((m_to_u(lo - minx), m_to_u(hi - minx)))
        return sorted(out)

    def extent_u(self, y0_u: int, y1_u: int) -> list[tuple[int, int]]:
        """Horizontal intervals inside the envelope for EVERY depth in [y0_u, y1_u): the
        intersection of the cross-sections over the range, as disjoint sorted intervals in units.
        Empty when some depth in the range has no interior; several when the envelope is split at
        some depth in the range (a court, a U opening north or south)."""
        if y1_u <= y0_u:
            y1_u = y0_u + 1
        _, miny, _, _ = self.polygon.bounds
        ys = {y0_u, y1_u - 1}
        for _, vy in self.vertices_m:
            vu = m_to_u(vy - miny)
            if y0_u <= vu < y1_u:
                ys.add(vu)
                if vu - 1 >= y0_u:
                    ys.add(vu - 1)
        current: list[tuple[int, int]] | None = None
        for y in sorted(ys):
            section = self._cross_section_u(y)
            if current is None:
                current = section
            else:
                current = _intersect_intervals(current, section)
            if not current:
                return []
        return current or []

    def split_depth_windows_u(self) -> list[tuple[int, int]]:
        """Depth ranges [y0, y1) over which the cross-section is NOT a single interval — a court,
        a U opening north or south. Empty for a horizontally convex envelope."""
        _, miny, _, _ = self.polygon.bounds
        ys = sorted({0, self.depth_u} | {m_to_u(vy - miny) for _, vy in self.vertices_m})
        out: list[tuple[int, int]] = []
        for y0, y1 in zip(ys, ys[1:]):
            if y1 <= y0:
                continue
            if len(self._cross_section_u(y0)) != 1:
                if out and out[-1][1] == y0:
                    out[-1] = (out[-1][0], y1)
                else:
                    out.append((y0, y1))
        return out

    def contains_rect_u(self, r: Rect) -> bool:
        minx, miny, _, _ = self.polygon.bounds
        b = box(minx + u_to_m(r.x), miny + u_to_m(r.y), minx + u_to_m(r.x2), miny + u_to_m(r.y2))
        return bool(self.polygon.buffer(_EPS_M).contains(b))


def _intersect_intervals(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for lo1, hi1 in a:
        for lo2, hi2 in b:
            lo, hi = max(lo1, lo2), min(hi1, hi2)
            if hi - lo >= 1:
                out.append((lo, hi))
    return sorted(out)
