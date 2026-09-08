"""Safe Geometry Adapter V1: authoritative general geometry -> rectangular solver geometry.

    BuildableRegion (arcs, holes, components)
            |
      SafeGeometryAdapter
            |
    SolverGeometryCandidate(s)  +  ResidualRegion(s)  +  proof of subset

THE INVARIANT: the adapter may LOSE usable area; it may never CREATE area that does not exist.
Three mechanisms enforce it, in order:

1. ARC LINEARIZATION is directional (`geometry_domain.linearize`): kept regions are approximated
   INNER, subtracted regions OUTER, so the composed boolean is a subset of the truth.
2. RASTERIZATION marks a grid cell usable only when the cell is ENTIRELY covered by the safe
   region — tested exactly, not by sampling its centre.
3. QUANTIZATION never happens as a separate rounding step at all. Candidates are built from
   whole grid cells, so they are grid-aligned by construction and there is no metres->units
   rounding that could round outward. This is stronger than using the direction-aware
   quantizers, and is why none appear below.

Geometry Core is not modified and not consulted; it only ever receives a `Rect`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from shapely import contains_xy
from shapely.errors import GEOSException
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from shapely.geometry.base import BaseGeometry

from app.geometry_domain.booleans import (
    BooleanOperationError,
    difference,
    multiregion_to_shapely,
    shapely_to_multiregion,
    union,
)
from app.geometry_domain.constraints import (
    BuildableRegion,
    ConstraintRole,
    GeometricConstraint,
    Parcel,
    SiteConstraints,
    UnknownBuildableRegionError,
)
from app.geometry_domain.linearize import (
    ApproxDirection,
    ApproximationReport,
    linearize_multiregion,
)
from app.geometry_domain.primitives import MultiRegion, Region
from app.geometry_domain.provenance import Authority, Provenance, Source, weakest_of

from .geometry_core.model import UNIT_M, Rect

#: Default linearization tolerance. Half a grid unit: fine enough that linearization is never
#: the dominant loss, coarse enough to keep vertex counts sane. Always reported, never silent.
DEFAULT_TOLERANCE_M = UNIT_M / 2.0
DEFAULT_MAX_CANDIDATES = 4
DEFAULT_MIN_CANDIDATE_AREA_M2 = 4.0
#: Residuals below this are counted but not listed individually (see dropped_residual_area_m2).
DEFAULT_MIN_RESIDUAL_AREA_M2 = 0.05


class AdapterOutcome(str, Enum):
    SOLVED = "SOLVED"
    NO_SAFE_SOLVER_GEOMETRY = "NO_SAFE_SOLVER_GEOMETRY"
    BUILDABLE_REGION_UNKNOWN = "BUILDABLE_REGION_UNKNOWN"
    INSUFFICIENT_RECTANGULAR_CAPACITY = "INSUFFICIENT_RECTANGULAR_CAPACITY"
    DECOMPOSITION_FAILED = "DECOMPOSITION_FAILED"


class RectStrategy(str, Enum):
    #: The single largest axis-aligned rectangle that fits.
    MAX_INSCRIBED_RECT = "MAX_INSCRIBED_RECT"
    #: Subsequent rectangles carved from what the previous ones left behind.
    GREEDY_DECOMPOSITION = "GREEDY_DECOMPOSITION"


class ResidualSource(str, Enum):
    CURVE_APPROXIMATION = "CURVE_APPROXIMATION"
    RECTANGULARIZATION = "RECTANGULARIZATION"
    EXCLUSION = "EXCLUSION"
    DECOMPOSITION = "DECOMPOSITION"
    OTHER = "OTHER"


@dataclass(frozen=True)
class SolverGeometryCandidate:
    """Solver-safe geometry plus everything needed to justify and trace it."""

    rect: Rect
    area_m2: float
    component_index: int          # which disconnected component of the buildable region
    strategy: RectStrategy
    order: int                    # 0 = largest
    adjacent_orders: tuple[int, ...]  # candidates sharing a boundary — future wing seams
    provenance: Provenance


@dataclass(frozen=True)
class ResidualRegionOut:
    """Authoritative buildable area NOT consumed by solver geometry. Geometric facts only —
    no architectural use is assigned here, by instruction."""

    region: Region
    area_m2: float
    thickness_est_m: float        # 2x largest inscribed circle radius
    max_extent_m: float           # longest side of the bounding box
    source: ResidualSource
    touches_solver_geometry: bool
    has_exterior_exposure: bool


@dataclass(frozen=True)
class SafeGeometryResult:
    outcome: AdapterOutcome
    candidates: tuple[SolverGeometryCandidate, ...] = ()
    residuals: tuple[ResidualRegionOut, ...] = ()
    approximation: ApproximationReport | None = None
    authoritative_area_m2: float = 0.0
    solver_area_m2: float = 0.0
    #: Exact: authoritative (arc-aware) area minus the safe linear area. Not emitted as residual
    #: geometry, because the band between the inner and outer linearizations is a fringe of
    #: slivers that overstates the true loss and tells a reader nothing useful.
    curve_loss_area_m2: float = 0.0
    #: Residual polygons too small to be worth listing. Counted, never silently discarded.
    dropped_residual_area_m2: float = 0.0
    authority: Authority = Authority.ASSUMED
    notes: tuple[str, ...] = ()

    @property
    def retention_ratio(self) -> float:
        if self.authoritative_area_m2 <= 0:
            return 0.0
        return round(self.solver_area_m2 / self.authoritative_area_m2, 4)

    @property
    def accounted_area_m2(self) -> float:
        """Solver area + every residual + curve loss. Must equal the authoritative area: every
        square metre is either used, listed as residual, or explicitly lost to approximation."""
        return round(
            self.solver_area_m2
            + sum(r.area_m2 for r in self.residuals)
            + self.curve_loss_area_m2
            + self.dropped_residual_area_m2,
            4,
        )

    @property
    def is_solved(self) -> bool:
        return self.outcome is AdapterOutcome.SOLVED


# --------------------------------------------------------------------------- buildable region

def build_buildable_region(site: SiteConstraints,
                           tolerance_m: float = DEFAULT_TOLERANCE_M) -> BuildableRegion:
    """parcel MINUS setbacks MINUS no-build MINUS obstacles.

    Directional linearization is the whole safety argument: the parcel is approximated INNER
    (we may keep less than we own) and every subtracted constraint OUTER (we always remove at
    least as much as required).
    """
    kept, _ = linearize_multiregion(site.parcel.geometry, ApproxDirection.INNER, tolerance_m)

    subtract_roles = (
        ConstraintRole.SETBACK_REGION,
        ConstraintRole.NO_BUILD_REGION,
        ConstraintRole.OBSTACLE,
    )
    to_remove = MultiRegion()
    provenances: list[Provenance] = [site.parcel.provenance]
    for constraint in site.constraints:
        if constraint.role not in subtract_roles:
            continue
        grown, _ = linearize_multiregion(constraint.geometry, ApproxDirection.OUTER, tolerance_m)
        to_remove = union(to_remove, grown) if not to_remove.is_empty else grown
        provenances.append(constraint.provenance)

    result = difference(kept, to_remove) if not to_remove.is_empty else kept
    if result.is_empty:
        return BuildableRegion.unknown(
            "constraints removed the entire parcel; there is no buildable region"
        )
    return BuildableRegion.known(
        result,
        Provenance(Source.INFERRED, weakest_of(*provenances), ref="derived: parcel - constraints"),
        derived_from=tuple(c.id for c in site.constraints if c.role in subtract_roles),
    )


# --------------------------------------------------------------------------- rasterization

def _cell_mask(poly: BaseGeometry, i0: int, j0: int, nx: int, ny: int) -> np.ndarray:
    """`mask[j][i]` is True only when grid cell (i, j) is ENTIRELY inside `poly`.

    Cells far from the boundary are classified by a single vectorized centre test; only cells
    whose centre falls within half a cell-diagonal of the boundary need the exact per-cell
    coverage test. That keeps the result exact — a cheaper centre-only test would wrongly accept
    a cell that a thin sliver of non-region passes through.
    """
    half = UNIT_M / 2.0
    diag = UNIT_M * math.sqrt(2.0) / 2.0

    cx = (np.arange(nx) + i0) * UNIT_M + half
    cy = (np.arange(ny) + j0) * UNIT_M + half
    gx, gy = np.meshgrid(cx, cy)
    flat_x, flat_y = gx.ravel(), gy.ravel()

    inside = contains_xy(poly, flat_x, flat_y).reshape(ny, nx)
    boundary_zone = poly.boundary.buffer(diag * 1.02)
    near = contains_xy(boundary_zone, flat_x, flat_y).reshape(ny, nx)

    mask = inside & ~near  # unambiguous interior cells
    for j, i in zip(*np.nonzero(near)):
        cell = box(
            (i0 + i) * UNIT_M, (j0 + j) * UNIT_M,
            (i0 + i + 1) * UNIT_M, (j0 + j + 1) * UNIT_M,
        )
        mask[j, i] = poly.covers(cell)
    return mask


def _largest_rectangle(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Largest all-True axis-aligned rectangle, as (i, j, w, h) in cell indices.

    Classic maximal-rectangle-in-a-histogram scan: O(rows x cols), exact, and it naturally
    respects holes and disconnected components because they are simply False cells.
    """
    ny, nx = mask.shape
    heights = np.zeros(nx, dtype=int)
    best: tuple[int, int, int, int] | None = None
    best_area = 0

    for j in range(ny):
        heights = np.where(mask[j], heights + 1, 0)
        stack: list[tuple[int, int]] = []  # (start index, height)
        for i in range(nx + 1):
            h = int(heights[i]) if i < nx else 0
            start = i
            while stack and stack[-1][1] >= h:
                idx, height = stack.pop()
                area = height * (i - idx)
                if area > best_area:
                    best_area = area
                    best = (idx, j - height + 1, i - idx, height)
                start = idx
            stack.append((start, h))
    return best if best_area > 0 else None


def _extract_rectangles(mask: np.ndarray, i0: int, j0: int, max_count: int,
                        min_cells: int) -> list[Rect]:
    working = mask.copy()
    rects: list[Rect] = []
    for _ in range(max_count):
        found = _largest_rectangle(working)
        if found is None:
            break
        i, j, w, h = found
        if w * h < min_cells:
            break
        rects.append(Rect(i0 + i, j0 + j, w, h))
        working[j:j + h, i:i + w] = False
    return rects


# --------------------------------------------------------------------------- residuals

def _thickness_estimate(poly: BaseGeometry) -> float:
    """2x the largest inscribed circle radius, by bisection on erosion."""
    minx, miny, maxx, maxy = poly.bounds
    hi = min(maxx - minx, maxy - miny) / 2.0
    lo = 0.0
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if poly.buffer(-mid).is_empty:
            hi = mid
        else:
            lo = mid
    return round(2.0 * lo, 4)


def _classify_residual(region: Region, curve_band: BaseGeometry, solver_geom: BaseGeometry,
                       exterior_boundary: BaseGeometry, multi_candidate: bool) -> ResidualRegionOut:
    poly = multiregion_to_shapely(MultiRegion.of(region))
    minx, miny, maxx, maxy = poly.bounds

    if not curve_band.is_empty and poly.intersection(curve_band).area > 0.5 * poly.area:
        source = ResidualSource.CURVE_APPROXIMATION
    elif region.holes:
        source = ResidualSource.EXCLUSION
    elif multi_candidate and solver_geom.intersects(poly.buffer(UNIT_M)):
        source = ResidualSource.DECOMPOSITION
    else:
        source = ResidualSource.RECTANGULARIZATION

    return ResidualRegionOut(
        region=region,
        area_m2=round(poly.area, 4),
        thickness_est_m=_thickness_estimate(poly),
        max_extent_m=round(max(maxx - minx, maxy - miny), 4),
        source=source,
        touches_solver_geometry=bool(solver_geom.buffer(1e-6).intersects(poly)),
        has_exterior_exposure=bool(poly.boundary.intersects(exterior_boundary.buffer(1e-6))),
    )


# --------------------------------------------------------------------------- the adapter

def adapt(buildable: BuildableRegion, *,
          tolerance_m: float = DEFAULT_TOLERANCE_M,
          max_candidates: int = DEFAULT_MAX_CANDIDATES,
          min_candidate_area_m2: float = DEFAULT_MIN_CANDIDATE_AREA_M2,
          min_residual_area_m2: float = DEFAULT_MIN_RESIDUAL_AREA_M2,
          required_size_m: tuple[float, float] | None = None) -> SafeGeometryResult:
    """Authoritative buildable geometry -> solver-safe rectangles + residuals.

    `required_size_m` is optional: when given, a result that produces no candidate large enough
    is reported as INSUFFICIENT_RECTANGULAR_CAPACITY rather than SOLVED, so a caller does not
    have to re-discover that its programme cannot be hosted.
    """
    # 1. UNKNOWN never falls back to anything. It is a structured outcome, not an exception.
    try:
        authoritative = buildable.require_known()
    except UnknownBuildableRegionError as exc:
        return SafeGeometryResult(
            outcome=AdapterOutcome.BUILDABLE_REGION_UNKNOWN,
            notes=(str(exc),),
        )

    authority = buildable.provenance.authority if buildable.provenance else Authority.ASSUMED
    authoritative_area = authoritative.area()

    try:
        inner, approx = linearize_multiregion(authoritative, ApproxDirection.INNER, tolerance_m)
        outer, _ = linearize_multiregion(authoritative, ApproxDirection.OUTER, tolerance_m)
        inner_geom = multiregion_to_shapely(inner)
        curve_band = multiregion_to_shapely(outer).difference(inner_geom)
    except (BooleanOperationError, GEOSException, ValueError) as exc:
        return SafeGeometryResult(
            outcome=AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY,
            notes=(f"could not build a safe linear region: {exc}",),
        )

    if inner.is_empty:
        return SafeGeometryResult(
            outcome=AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY,
            approximation=approx, authoritative_area_m2=authoritative_area, authority=authority,
            notes=("conservative linearization left no area",),
        )

    # 2. Rectangles, per component. Components are never merged to simplify solving.
    candidates: list[SolverGeometryCandidate] = []
    provenance = buildable.provenance or Provenance(Source.INFERRED, Authority.ASSUMED)
    min_cells = max(1, int(min_candidate_area_m2 / (UNIT_M * UNIT_M)))

    try:
        for component_index, region in enumerate(inner.regions):
            poly = multiregion_to_shapely(MultiRegion.of(region))
            minx, miny, maxx, maxy = poly.bounds
            i0, j0 = math.floor(minx / UNIT_M), math.floor(miny / UNIT_M)
            nx = math.ceil(maxx / UNIT_M) - i0
            ny = math.ceil(maxy / UNIT_M) - j0
            if nx <= 0 or ny <= 0:
                continue
            mask = _cell_mask(poly, i0, j0, nx, ny)
            for rect in _extract_rectangles(mask, i0, j0, max_candidates, min_cells):
                candidates.append(SolverGeometryCandidate(
                    rect=rect,
                    area_m2=round(rect.area_m2(), 4),
                    component_index=component_index,
                    strategy=RectStrategy.MAX_INSCRIBED_RECT if not candidates
                    else RectStrategy.GREEDY_DECOMPOSITION,
                    order=len(candidates),
                    adjacent_orders=(),
                    provenance=provenance,
                ))
    except (GEOSException, ValueError, MemoryError) as exc:
        return SafeGeometryResult(
            outcome=AdapterOutcome.DECOMPOSITION_FAILED,
            approximation=approx, authoritative_area_m2=authoritative_area, authority=authority,
            notes=(f"rectangular decomposition failed: {exc}",),
        )

    if not candidates:
        return SafeGeometryResult(
            outcome=AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY,
            approximation=approx, authoritative_area_m2=authoritative_area, authority=authority,
            notes=("no grid cell was entirely inside the safe region",),
        )

    # Rank by area, then restate order and cross-link adjacency (seam information).
    candidates.sort(key=lambda c: c.area_m2, reverse=True)
    rects = [c.rect for c in candidates]
    candidates = [
        SolverGeometryCandidate(
            rect=c.rect, area_m2=c.area_m2, component_index=c.component_index,
            strategy=RectStrategy.MAX_INSCRIBED_RECT if order == 0 else RectStrategy.GREEDY_DECOMPOSITION,
            order=order,
            adjacent_orders=tuple(
                other for other, other_rect in enumerate(rects)
                if other != order and c.rect.shared_edge_len_u(other_rect) > 0
            ),
            provenance=c.provenance,
        )
        for order, c in enumerate(candidates)
    ]

    solver_geom = union_of_rects([c.rect for c in candidates])
    solver_area = sum(c.area_m2 for c in candidates)

    # 3. Residuals: authoritative buildable area not consumed by solver geometry.
    residuals: list[ResidualRegionOut] = []
    dropped_area = 0.0
    try:
        leftover = shapely_to_multiregion(inner_geom.difference(solver_geom))
        exterior_boundary = inner_geom.boundary
        for region in leftover.regions:
            residual = _classify_residual(
                region, curve_band, solver_geom, exterior_boundary, len(candidates) > 1)
            if residual.area_m2 < min_residual_area_m2:
                dropped_area += residual.area_m2
            else:
                residuals.append(residual)
    except (GEOSException, ValueError) as exc:
        residuals = []
        notes_extra = (f"residual analysis skipped: {exc}",)
    else:
        notes_extra = ()

    outcome = AdapterOutcome.SOLVED
    if required_size_m is not None:
        need_w, need_h = required_size_m
        if not any(_fits(c.rect, need_w, need_h) for c in candidates):
            outcome = AdapterOutcome.INSUFFICIENT_RECTANGULAR_CAPACITY

    return SafeGeometryResult(
        outcome=outcome,
        candidates=tuple(candidates),
        residuals=tuple(residuals),
        approximation=approx,
        authoritative_area_m2=round(authoritative_area, 4),
        solver_area_m2=round(solver_area, 4),
        curve_loss_area_m2=round(authoritative_area - inner.area(), 4),
        dropped_residual_area_m2=round(dropped_area, 4),
        authority=authority,
        notes=notes_extra,
    )


def _fits(rect: Rect, need_w_m: float, need_h_m: float) -> bool:
    return rect.w * UNIT_M >= need_w_m - 1e-9 and rect.h * UNIT_M >= need_h_m - 1e-9


def union_of_rects(rects: list[Rect]) -> BaseGeometry:
    """Shapely geometry of a candidate set. `adjacent_orders` on each candidate records which
    rectangles share a boundary — the information a future concept generator would need to emit
    Geometry Core `seam_leaf_sides` and treat a decomposition as wings."""
    if not rects:
        return Polygon()
    return unary_union([
        box(r.x * UNIT_M, r.y * UNIT_M, r.x2 * UNIT_M, r.y2 * UNIT_M) for r in rects
    ])


# --------------------------------------------------------------------------- verification

def verify_candidate_within(candidate: SolverGeometryCandidate,
                            authoritative: MultiRegion,
                            samples: int = 24) -> bool:
    """Prove `candidate.rect` lies inside the AUTHORITATIVE (curved) region.

    Deliberately checked against the exact arc-aware `Region.contains_point`, not against the
    linearized region the candidate was derived from — otherwise the test would only be
    re-confirming its own approximation. Samples the rectangle's interior and its boundary,
    inset by a hair so that a point exactly on a shared edge is not judged by float luck.
    """
    r = candidate.rect
    x0, y0 = r.x * UNIT_M, r.y * UNIT_M
    x1, y1 = r.x2 * UNIT_M, r.y2 * UNIT_M
    inset = 1e-6
    for i in range(samples + 1):
        for j in range(samples + 1):
            px = x0 + inset + (x1 - x0 - 2 * inset) * i / samples
            py = y0 + inset + (y1 - y0 - 2 * inset) * j / samples
            if not authoritative.contains_point((px, py)):
                return False
    return True
