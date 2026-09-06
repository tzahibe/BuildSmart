"""Spatial V2 orchestration (Phases 5-6): generate candidates (candidates.py, reusing Spatial V1's
hard-feasibility search unmodified), score every one (scoring.py), and return the best-scoring
hard-valid layout. Never returns the first valid candidate found -- always evaluates the full pool
and picks by total_score.
"""
from dataclasses import dataclass, field

from app.architect.models import ArchitecturalSpec
from app.geometry.geometric_design import GeometricDesign, build_geometric_design
from app.geometry.models import (
    BuildingFootprintSpec,
    GeometrySolverResult,
    RoomInstance,
    SolverStatus,
)
from app.geometry.solver import _find_pre_solver_contradiction
from app.geometry.spatial_v2.candidates import generate_candidates
from app.geometry.spatial_v2.scoring import ArchitecturalScore, score_layout


@dataclass(frozen=True)
class SpatialV2Result:
    status: SolverStatus
    instances: list[RoomInstance] = field(default_factory=list)
    score: ArchitecturalScore | None = None
    candidate_count: int = 0
    all_scores: list[ArchitecturalScore] = field(default_factory=list)
    unsatisfiable_reason: str | None = None


def plan_v2(spec: ArchitecturalSpec, footprint: BuildingFootprintSpec) -> SpatialV2Result:
    contradiction = _find_pre_solver_contradiction(spec, footprint)
    if contradiction is not None:
        return SpatialV2Result(status=SolverStatus.unsatisfiable, unsatisfiable_reason=contradiction)

    candidates = generate_candidates(spec, footprint)
    if not candidates:
        return SpatialV2Result(
            status=SolverStatus.unsatisfiable,
            unsatisfiable_reason="Spatial V2 found no hard-feasible layout (same search Spatial V1 uses)",
        )

    scored = [(candidate, score_layout(spec, footprint, candidate)) for candidate in candidates]
    scored.sort(key=lambda entry: entry[1].total_score, reverse=True)
    best_candidate, best_score = scored[0]

    return SpatialV2Result(
        status=SolverStatus.satisfied,
        instances=best_candidate,
        score=best_score,
        candidate_count=len(candidates),
        all_scores=[s for _c, s in scored],
    )


def build_geometric_design_v2(spec: ArchitecturalSpec, footprint: BuildingFootprintSpec, result: SpatialV2Result) -> GeometricDesign:
    """Reuses `build_geometric_design` (app.geometry.geometric_design, unmodified) -- Spatial V2
    changes WHICH layout is chosen, never how a chosen layout is turned into the GeometricDesign
    contract, so the output shape is byte-for-byte the same contract Spatial V1 already produces."""
    if result.status != SolverStatus.satisfied:
        raise ValueError("build_geometric_design_v2 requires a satisfied SpatialV2Result")
    synthetic_result = GeometrySolverResult(status=SolverStatus.satisfied, instances=result.instances)
    return build_geometric_design(spec, footprint, synthetic_result)
