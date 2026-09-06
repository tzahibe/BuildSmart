from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.architect.models import ConstraintSeverity


class Edge(str, Enum):
    """One side of a rectangular `BuildingFootprintSpec`, in this module's OWN fixed local coordinate
    convention — north=`y=0`, south=`y=depth_m`, west=`x=0`, east=`x=width_m`. This is purely a naming
    convention for this module's math; it is NOT a claim about real geographic/compass orientation
    (this codebase has no site-orientation data — see Feature 03's location-resolution gap)."""

    north = "north"
    south = "south"
    east = "east"
    west = "west"


class BuildingFootprintSpec(BaseModel):
    """The actual buildable/building-placement boundary the Geometry Solver enforces as its hard
    room-placement boundary — deliberately independent of `app.architect.models.SiteSpec`. Deciding
    how much of a site becomes a building footprint (setbacks, coverage ratio, other regulatory/design
    decisions) is out of this module's scope; callers must supply this explicitly rather than the
    solver ever deriving it from `plot_area_m2` or any other site figure.

    V1 assumes a simple rectangle (`width_m` x `depth_m`), same placeholder spirit as Feature 03's
    square-site assumption. `available_area_m2` is independent of `width_m * depth_m` (it can never
    exceed that bounding rectangle, but may be smaller) — set it equal to the full rectangle for a
    simple usable footprint, or smaller to model a knockout/irregular usable area without yet modeling
    the irregular shape itself. The solver treats it as an additional hard budget: total placed room
    area must never exceed it, even when the geometric rectangle alone would allow more.

    `allowed_entry_edges`: which of the four edges may serve as the entry room's perimeter-facing
    side — e.g. because only that edge actually faces a street/access path (not modeled here; no
    roads, gates, doors, or site-access geometry exist in this codebase yet, only the abstract notion
    "this edge is allowed"). `None` (the default) preserves the original, simpler behavior from before
    this field existed: any of the four edges counts, i.e. equivalent to allowing all of them — fully
    backward compatible with specs written before entry-edge restriction existed.

    Candidate placement generation (`app/geometry/solver.py`'s `_candidate_positions`) always offers
    all four footprint-corner alignments for whichever room is placed first (typically the entry
    room), so any single edge — or combination — can be satisfied on its own merits, not just
    north/west.
    """

    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    floor: int = Field(ge=1, default=1)
    available_area_m2: float = Field(gt=0)
    allowed_entry_edges: list[Edge] | None = Field(default=None)

    @model_validator(mode="after")
    def _available_area_fits_the_rectangle(self) -> "BuildingFootprintSpec":
        bounding_area = self.width_m * self.depth_m
        if self.available_area_m2 > bounding_area + 1e-6:
            raise ValueError(
                f"available_area_m2 ({self.available_area_m2}) cannot exceed the "
                f"{self.width_m}x{self.depth_m} m bounding rectangle's area ({bounding_area})"
            )
        return self


class RoomInstance(BaseModel):
    """One placed room — a concrete instance of an `ArchitecturalSpec.program` room type (see
    `app/geometry/instances.py`), with real, solved geometry within a `BuildingFootprintSpec`."""

    id: str
    type: str
    floor: int
    x: float
    y: float
    width: float
    height: float
    area_m2: float


class SolverStatus(str, Enum):
    satisfied = "satisfied"
    unsatisfiable = "unsatisfiable"


class ConstraintCheckResult(BaseModel):
    """One evaluated relationship-level constraint, for diagnostics — human-readable and free of
    internal search mechanics (no step counts, no backtracking-tree details).

    `note` carries caveats about *how* satisfaction was determined when that matters — currently used
    for `direct_access`: satisfying it only proves a wide-enough shared wall exists (a V1 proxy), never
    that a real door/opening does. `None` when there's nothing to caveat.
    """

    description: str
    kind: str
    severity: ConstraintSeverity
    satisfied: bool
    note: str | None = None


class LayoutQualityReport(BaseModel):
    """Geometric quality metrics for one valid layout — see app/geometry/quality.py. Distinct from
    `hard_constraints_checked`/soft relationship reports above: those are about the ArchitecturalSpec's
    own relationship/zone/circulation requirements, this is purely about the resulting geometry's shape
    (footprint utilization, unused-space fragmentation, compactness) that no per-relationship check
    captures on its own."""

    programmed_area_m2: float
    footprint_area_m2: float
    utilization_ratio: float
    unused_area_m2: float
    largest_contiguous_unused_region_m2: float
    unused_region_fragmentation_ratio: float
    compactness: float
    zone_cohesion_ratio: float
    circulation_quality_ratio: float


class ObjectiveBreakdown(BaseModel):
    """Explains the winning candidate's `objective_score` as an explicit, weighted sum — see
    app/geometry/solver.py's `_OBJECTIVE_WEIGHTS` for the named, documented weight for each term. Lets a
    caller see exactly why candidate A outscored candidate B instead of a single opaque number."""

    soft_relationships_satisfied: float
    zone_cohesion_score: float
    circulation_reach_score: float
    utilization_term: float
    compactness_term: float
    fragmentation_term: float
    total: float


class GeometrySolverResult(BaseModel):
    """OUTPUT of `GeometrySolver.solve()`. Always returned — the solver does not raise for the
    "expected" outcome of no valid layout existing within its search budget; that case is represented
    by `status=unsatisfiable`, empty `instances`, and a human-readable `unsatisfiable_reason`, so a
    caller can report/debug it without exception handling. `instances` is only ever fully populated
    (never partial) when `status=satisfied` — every hard constraint reported in
    `hard_constraints_checked` holds for that layout, by construction.
    """

    status: SolverStatus
    instances: list[RoomInstance] = Field(default_factory=list)
    hard_constraints_checked: list[ConstraintCheckResult] = Field(default_factory=list)
    soft_constraints_satisfied: list[ConstraintCheckResult] = Field(default_factory=list)
    soft_constraints_not_satisfied: list[ConstraintCheckResult] = Field(default_factory=list)
    # Breakdown of objective_score's components — see app/geometry/solver.py's module docstring for
    # exactly what each measures (both are V1 approximations, documented there).
    zone_cohesion_score: float = 0.0
    circulation_reach_score: float = 0.0
    objective_score: float = 0.0
    unsatisfiable_reason: str | None = None
    # Populated only when status=satisfied. `quality` is the winning layout's own geometric report;
    # `objective_breakdown` explains how `objective_score` was actually computed from it plus the
    # relationship/zone/circulation terms above; `candidate_count`/`candidate_summaries` expose how many
    # valid layouts were found and ranked (see app/geometry/solver.py's module docstring, Step 3).
    quality: LayoutQualityReport | None = None
    objective_breakdown: ObjectiveBreakdown | None = None
    candidate_count: int = 0
    candidate_summaries: list[ObjectiveBreakdown] = Field(default_factory=list)
