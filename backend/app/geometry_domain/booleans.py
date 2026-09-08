"""Region boolean operations, backed by Shapely (GEOS).

WHY A LIBRARY. Robust polygon booleans are a genuinely hard numerical problem — self-
intersection, collinear overlap, near-degenerate slivers and the resulting topology repair are
where hand-rolled implementations fail, usually silently and non-reproducibly. GEOS is decades-
mature and is the standard engine underneath PostGIS. Writing a Weiler-Atherton by hand here
would have been the single riskiest thing in this task, and it is not the problem BuildSmart is
trying to solve. Shapely 2.x is used, with numpy for vectorized point classification.

WHAT THIS MODULE GUARANTEES. Shapely has no concept of arcs, so everything crossing this
boundary must already be linear. `_require_linear` enforces that rather than silently dropping
curvature — the caller is responsible for having linearized in the correct DIRECTION first
(`linearize.ApproxDirection`), which is where conservatism is decided.

WHAT DOES NOT ESCAPE. No Shapely type appears in this module's public signatures; everything is
converted back to domain `Region`/`MultiRegion`. Library errors are raised as
`BooleanOperationError` so product-level callers never see GEOS internals.
"""
from __future__ import annotations

from shapely.errors import GEOSException
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .primitives import GeometryValidationError, MultiRegion, Region, Ring

_EPS = 1e-12


class BooleanOperationError(RuntimeError):
    """A geometry operation failed. Carries a readable cause, never a GEOS stack trace."""


def _require_linear(region: Region) -> None:
    for ring in (region.outer, *region.holes):
        for edge in ring.edges:
            if not edge.is_line:
                raise GeometryValidationError(
                    "boolean operations require linear geometry: linearize the region first "
                    "(and choose INNER for kept regions / OUTER for subtracted regions — the "
                    "direction is what makes the result conservative)"
                )


# --------------------------------------------------------------------------- conversion

def region_to_shapely(region: Region) -> Polygon:
    _require_linear(region)
    norm = region.normalized()
    return Polygon(
        [v.as_point() for v in norm.outer.vertices],
        [[v.as_point() for v in hole.vertices] for hole in norm.holes],
    )


def multiregion_to_shapely(multi: MultiRegion) -> BaseGeometry:
    if multi.is_empty:
        return Polygon()
    return unary_union([region_to_shapely(r) for r in multi.regions])


def shapely_to_multiregion(geom: BaseGeometry) -> MultiRegion:
    if geom.is_empty:
        return MultiRegion()
    polygons: list[Polygon]
    if isinstance(geom, Polygon):
        polygons = [geom]
    elif isinstance(geom, MultiPolygon):
        polygons = list(geom.geoms)
    else:
        # A difference can yield lines/points where regions merely touch; those carry no area
        # and are dropped rather than surfaced as degenerate regions.
        polygons = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]

    regions = []
    for poly in polygons:
        if poly.is_empty or poly.area <= _EPS:
            continue
        try:
            outer = Ring.from_points(_ring_points(poly.exterior.coords), prefix="s")
            holes = tuple(
                Ring.from_points(_ring_points(interior.coords), prefix="h")
                for interior in poly.interiors
                if Polygon(interior).area > _EPS
            )
        except GeometryValidationError:
            continue  # degenerate sliver from the boolean; carries no usable area
        regions.append(Region(outer, holes))
    return MultiRegion(tuple(regions))


def _ring_points(coords) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in coords]
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-12 and abs(pts[0][1] - pts[-1][1]) < 1e-12:
        pts.pop()  # shapely closes rings explicitly; the domain model closes them implicitly
    return pts


# --------------------------------------------------------------------------- operations

def difference(keep: MultiRegion, remove: MultiRegion) -> MultiRegion:
    """`keep` minus `remove`. Both must already be linearized in their correct directions."""
    try:
        result = multiregion_to_shapely(keep).difference(multiregion_to_shapely(remove))
    except GeometryValidationError:
        raise  # caller error (un-linearized input): keep the actionable message intact
    except (GEOSException, ValueError) as exc:
        raise BooleanOperationError(f"region difference failed: {exc}") from exc
    return shapely_to_multiregion(result)


def union(a: MultiRegion, b: MultiRegion) -> MultiRegion:
    try:
        result = multiregion_to_shapely(a).union(multiregion_to_shapely(b))
    except GeometryValidationError:
        raise  # caller error (un-linearized input): keep the actionable message intact
    except (GEOSException, ValueError) as exc:
        raise BooleanOperationError(f"region union failed: {exc}") from exc
    return shapely_to_multiregion(result)


def intersection(a: MultiRegion, b: MultiRegion) -> MultiRegion:
    try:
        result = multiregion_to_shapely(a).intersection(multiregion_to_shapely(b))
    except GeometryValidationError:
        raise  # caller error (un-linearized input): keep the actionable message intact
    except (GEOSException, ValueError) as exc:
        raise BooleanOperationError(f"region intersection failed: {exc}") from exc
    return shapely_to_multiregion(result)


def offset_inward(multi: MultiRegion, distance_m: float) -> MultiRegion:
    """Shrink by `distance_m` — the geometric form of a uniform setback.

    Returns a MultiRegion because an inward offset can DISCONNECT a pinched region, and can
    empty it entirely. Round joins are used deliberately: on a reflex corner a rounded join
    removes at least as much as a mitred one, so it is the conservative choice.
    """
    if distance_m < 0:
        raise ValueError("offset_inward distance must be >= 0; use offset_outward to grow")
    if distance_m == 0:
        return multi
    try:
        result = multiregion_to_shapely(multi).buffer(-distance_m, join_style="round")
    except GeometryValidationError:
        raise  # caller error (un-linearized input): keep the actionable message intact
    except (GEOSException, ValueError) as exc:
        raise BooleanOperationError(f"inward offset failed: {exc}") from exc
    return shapely_to_multiregion(result)


def offset_outward(multi: MultiRegion, distance_m: float) -> MultiRegion:
    """Grow by `distance_m` — used to turn a point/line feature into a clearance region."""
    if distance_m < 0:
        raise ValueError("offset_outward distance must be >= 0")
    try:
        result = multiregion_to_shapely(multi).buffer(distance_m, join_style="round")
    except GeometryValidationError:
        raise  # caller error (un-linearized input): keep the actionable message intact
    except (GEOSException, ValueError) as exc:
        raise BooleanOperationError(f"outward offset failed: {exc}") from exc
    return shapely_to_multiregion(result)


def contains_region(outer: MultiRegion, inner: MultiRegion, tolerance_m: float = 1e-9) -> bool:
    """Is `inner` entirely within `outer`? The subset check the whole adapter rests on.

    A tiny positive tolerance absorbs float noise from the boolean engine; it is applied by
    growing `outer`, never by shrinking `inner`, so the check can only be made STRICTER than
    reality in the direction that matters.
    """
    try:
        outer_geom = multiregion_to_shapely(outer)
        if tolerance_m > 0:
            outer_geom = outer_geom.buffer(tolerance_m)
        return bool(outer_geom.covers(multiregion_to_shapely(inner)))
    except GeometryValidationError:
        raise  # caller error (un-linearized input): keep the actionable message intact
    except (GEOSException, ValueError) as exc:
        raise BooleanOperationError(f"containment test failed: {exc}") from exc


def area_of(multi: MultiRegion) -> float:
    return float(multiregion_to_shapely(multi).area)
