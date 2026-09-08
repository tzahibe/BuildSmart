"""The ONLY place the solver's `Rect` meets the authoritative `Region` (task §11).

Everything the rectangular engine assumes about geometry is isolated here, so that the future
Safe Geometry Adapter has exactly one seam to grow into rather than a diffuse set of
assumptions spread across the slice.

Scope discipline (task §10): this module performs only EXACT conversions. It does NOT do curve
simplification, chord substitution, tangent-chain approximation, or polygon decomposition —
those belong to the Safe Geometry Adapter stage and must not be started here. `region_to_rect`
therefore REFUSES anything that is not already exactly an axis-aligned rectangle, rather than
approximating it, because a silent approximation in this direction is precisely the class of
bug (handing the solver space that does not exist) that the whole architecture exists to
prevent.
"""
from __future__ import annotations

from app.geometry_domain.primitives import Region, Ring
from app.geometry_domain.provenance import Provenance
from app.geometry_domain.units import UNIT_M as DOMAIN_UNIT_M
from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts

from .geometry_core.model import UNIT_M as SOLVER_UNIT_M
from .geometry_core.model import Rect, Side, WallType, u_to_m

_EPS = 1e-9

#: Construction facts are program/regulation facts; the solver's WallType happens to encode
#: them alongside exposure, so this map extracts the construction half of each value.
_CONSTRUCTION_OF_WALL_TYPE = {
    WallType.OPEN: Construction.NONE,
    WallType.PARTITION: Construction.STANDARD_PARTITION,
    WallType.RC_SAFE_ROOM: Construction.RC_SAFE_ROOM,
    #: The solver's EXTERIOR value carries no construction information at all — it says only
    #: "on the envelope". An ordinary exterior wall is a standard partition-grade wall here;
    #: when structural walls are modelled this is the entry that will need revisiting.
    WallType.EXTERIOR: Construction.STANDARD_PARTITION,
}


def rect_to_ring(rect: Rect, provenance: Provenance | None = None, prefix: str = "r") -> Ring:
    """Exact. A rectangle is one representable special case of general geometry."""
    return Ring.rectangle(
        u_to_m(rect.x), u_to_m(rect.y), u_to_m(rect.w), u_to_m(rect.h),
        prefix=prefix, provenance=provenance,
    )


def rect_to_region(rect: Rect, provenance: Provenance | None = None) -> Region:
    return Region(rect_to_ring(rect, provenance))


def region_to_rect(region: Region) -> Rect | None:
    """Exact inverse, or None. Never approximates.

    Returns None (rather than a best-fit rectangle) when the region has holes, curved edges, or
    is not axis-aligned — a caller that needs solver geometry for such a region must go through
    the future Safe Geometry Adapter, which is required to be conservative. Returning an
    approximation from here would be the silent-area-gain bug in its purest form.
    """
    if region.holes:
        return None
    ring = region.outer
    if len(ring.edges) != 4 or any(not e.is_line for e in ring.edges):
        return None
    xs = sorted({v.x for v in ring.vertices})
    ys = sorted({v.y for v in ring.vertices})
    if len(xs) != 2 or len(ys) != 2:
        return None
    for v in ring.vertices:
        if v.x not in (xs[0], xs[1]) or v.y not in (ys[0], ys[1]):
            return None
    x0_u, y0_u = _exact_units(xs[0]), _exact_units(ys[0])
    x1_u, y1_u = _exact_units(xs[1]), _exact_units(ys[1])
    if None in (x0_u, y0_u, x1_u, y1_u):
        return None
    return Rect(x0_u, y0_u, x1_u - x0_u, y1_u - y0_u)


def _exact_units(value_m: float) -> int | None:
    """Grid units, or None if the value does not land exactly on the grid.

    Deliberately refuses to round: this is the exact-conversion path. Anything needing a
    rounding decision must state its intent through `geometry_domain.units`.
    """
    raw = value_m / SOLVER_UNIT_M
    nearest = round(raw)
    return int(nearest) if abs(raw - nearest) <= 1e-6 else None


def envelope_sides(rect: Rect, footprint: Rect) -> list[Side]:
    """Which of `rect`'s sides lie on the building envelope — a GEOMETRIC fact.

    Moved here from `windows.py` unchanged (same comparisons, same result) because it is a
    Rect-dependent geometric computation and this module is where those now live. It is the
    working half of the fix for the safe-room window defect: exposure must be derived from
    geometry, never read off a `WallType` whose precedence rule may have overwritten it.
    """
    sides = []
    if rect.x == footprint.x:
        sides.append(Side.W)
    if rect.x2 == footprint.x2:
        sides.append(Side.E)
    if rect.y == footprint.y:
        sides.append(Side.N)
    if rect.y2 == footprint.y2:
        sides.append(Side.S)
    return sides


def wall_facts_for_side(wall_type: WallType, on_envelope: bool) -> WallFacts:
    """Recover the two orthogonal facts the solver's single enum collapsed (report §8).

    `on_envelope` MUST come from geometry (`envelope_sides`), not from `wall_type` — that is the
    entire point. `WallType.EXTERIOR` implies exposure, but the converse fails exactly where it
    matters: RC_SAFE_ROOM on an outer wall is exposed and does not say so.
    """
    context = BoundaryContext.EXTERIOR if on_envelope else BoundaryContext.INTERIOR
    return WallFacts(
        boundary_context=context,
        construction=_CONSTRUCTION_OF_WALL_TYPE[wall_type],
    )


def wall_facts_for_room(zone_id: str, rect: Rect, footprint: Rect,
                        walls: dict[tuple[str, Side], WallType]) -> dict[Side, WallFacts]:
    exposed = set(envelope_sides(rect, footprint))
    return {
        side: wall_facts_for_side(walls[(zone_id, side)], side in exposed)
        for side in Side
    }


def assert_units_agree() -> None:
    """The domain layer duplicates the grid constant rather than importing the solver's. This
    module is allowed to see both, so it is the right place to hold them equal."""
    if abs(DOMAIN_UNIT_M - SOLVER_UNIT_M) > _EPS:
        raise AssertionError(
            f"grid unit drift: geometry_domain={DOMAIN_UNIT_M} vs geometry_core={SOLVER_UNIT_M}"
        )
