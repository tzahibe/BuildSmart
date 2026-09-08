"""Authoritative geometry domain.

The product's geometry language. Deliberately independent of the solver: nothing in this
package imports `geometry_core` (or anything else from `app.vertical_slice`), so the
rectangular engine is one realization engine behind an adapter rather than the authoritative
representation (report §11, task §11).

The dependency direction is the point:

    geometry_domain            <- knows no solver, no law, no units-of-the-grid
        ^
        |  app/vertical_slice/geometry_adapter.py   (the only place Rect meets Region)
        |
    vertical_slice / geometry_core
"""
from .constraints import (
    BuildableRegion,
    ConstraintRole,
    GeometricConstraint,
    Knowledge,
    Parcel,
    SiteConstraints,
    UnknownBuildableRegionError,
)
from .primitives import (
    BoundaryEdge,
    GeometryValidationError,
    MultiRegion,
    Region,
    Ring,
    Vertex,
    arc_apex,
    arc_center,
    arc_radius,
    arc_sagitta,
    arc_segment_area,
    bulge_from_three_points,
    included_angle,
)
from .provenance import Authority, Provenance, Source, weakest_of
from .transforms import mirror_x, mirror_y, rotate, scale_uniform, translate
from .units import (
    Rounding,
    clearance_units_no_understate,
    length_units_no_overstate,
    lower_bound_units,
    quantize_m,
    upper_bound_units,
)
from .walls import BoundaryContext, Construction, OpeningPolicy, WallFacts

__all__ = [
    "Vertex", "BoundaryEdge", "Ring", "Region", "MultiRegion", "GeometryValidationError",
    "arc_apex", "arc_center", "arc_radius", "arc_sagitta", "arc_segment_area",
    "bulge_from_three_points", "included_angle",
    "translate", "rotate", "scale_uniform", "mirror_x", "mirror_y",
    "Provenance", "Source", "Authority", "weakest_of",
    "Parcel", "BuildableRegion", "Knowledge", "UnknownBuildableRegionError",
    "GeometricConstraint", "ConstraintRole", "SiteConstraints",
    "BoundaryContext", "Construction", "WallFacts", "OpeningPolicy",
    "Rounding", "quantize_m", "lower_bound_units", "upper_bound_units",
    "length_units_no_overstate", "clearance_units_no_understate",
]
