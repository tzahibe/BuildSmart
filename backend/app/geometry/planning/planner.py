"""Concept-first planning: decide the architectural concept BEFORE geometry, then realize it.

    generate_concepts(spec)                      -- graph-only, bounded, tier-scored
      -> for each concept (bounded):
           generate_valid_candidate_pool(required_edges=concept.edges)   -- GeometrySolver's own
                                                     backtracking, with the concept's edges as HARD
                                                     pruning constraints (legacy behavior untouched
                                                     when required_edges is None)
           generate_tagged_candidates(base_solutions=pool, hard_filter=concept edges)
                                                  -- Spatial V2.1 refinement, unable to break a
                                                     concept edge
           score_layout(...)                      -- Spatial V2 scoring, unchanged
      -> tiered selection: concept tier first (banded), geometry score second
      -> if NO concept realizes: fall back to plan_v2() exactly as before (regression-safe)

Hard structural correctness is never traded for cosmetic score: a concept edge is a hard geometry
constraint, and every candidate still passes `_layout_satisfies_hard_requirements`.
"""
import time
from dataclasses import dataclass, field

from app.architect.models import ArchitecturalSpec
from app.geometry.geometric_design import GeometricDesign, build_geometric_design
from app.geometry.models import BuildingFootprintSpec, GeometrySolverResult, RoomInstance, SolverStatus
from app.geometry.planning.concept import ArchitecturalConcept, edges_satisfied, realized_concept_signature, unsatisfied_edges
from app.geometry.planning.concept_generation import MAX_CIRCULATION_SEGMENTS, generate_concepts
from app.geometry.solver import _find_pre_solver_contradiction, generate_valid_candidate_pool
from app.geometry.spatial_v2.candidates import generate_tagged_candidates
from app.geometry.spatial_v2.planner import plan_v2
from app.geometry.spatial_v2.scoring import ArchitecturalScore, score_layout

MAX_REALIZED_CONCEPTS = 4     # concepts sent to geometry (bounded runtime)
# DENSE_CONCEPT_REALIZATION: a dense concept's required-degree instance now gets the corrected
# ordering + elongated shape candidates (see solver.py's generate_valid_candidate_pool docstring),
# but even correctly configured, finding ONE complete layout for a genuinely realizable dense
# concept can need far more than the legacy `_MAX_BACKTRACK_STEPS` (20,000) -- measured directly at
# ~260,000-300,000 steps (~2.5-2.9s) for the real 3BR+safe_room concept this investigation traced.
# That per-call cost is real and roughly fixed regardless of budget headroom (a call that fails
# still burns close to its full budget proving there is no solution) -- so this larger budget is
# spent AT MOST ONCE per plan_with_concepts() call (see `_last_chance_retry` below), never once per
# concept or once per circulation-segment escalation level, which is what would turn this into the
# unbounded multi-concept x multi-segment blowup the task explicitly warns against (measured: doing
# that made two genuinely-infeasible scenarios take 38-45s). The escalation ladder in
# plan_with_concepts keeps using the original legacy budget throughout, exactly as before this
# fix -- this budget only ever applies to the single extra last-chance attempt.
CONCEPT_REALIZATION_STEP_BUDGET = 300_000
MAX_REFINED_CONCEPTS = 2      # concepts that also get the (costlier) Spatial V2.1 refinement pass
CONCEPT_TIER_BAND = 0.05      # concepts within this tier-score band compete on geometry score


@dataclass(frozen=True)
class ConceptOutcome:
    concept: ArchitecturalConcept
    realized: bool
    pool_size: int = 0
    candidate_count: int = 0
    best_geometry_score: ArchitecturalScore | None = None
    best_instances: list[RoomInstance] = field(default_factory=list)
    selected_strategy: str | None = None
    refined: bool = False


@dataclass(frozen=True)
class ConceptPlanResult:
    status: SolverStatus
    instances: list[RoomInstance] = field(default_factory=list)
    concept: ArchitecturalConcept | None = None
    geometry_score: ArchitecturalScore | None = None
    outcomes: list[ConceptOutcome] = field(default_factory=list)
    concepts_considered: int = 0
    concepts_realized: int = 0
    fallback_used: bool = False
    selected_strategy: str | None = None
    runtime_s: float = 0.0
    unsatisfiable_reason: str | None = None
    effective_spec: ArchitecturalSpec | None = None  # spec actually realized (may include
    # SYSTEM_POLICY-tagged circulation added by concept_generation -- callers building
    # GeometricDesign from the result must use THIS spec, not the original, or door-relationship
    # derivation for the added corridor would look up an item that isn't in the original program

    @property
    def realized_signature(self) -> frozenset:
        return realized_concept_signature(self.instances) if self.instances else frozenset()


def _attempt_concept(
    effective_spec: ArchitecturalSpec,
    footprint: BuildingFootprintSpec,
    concept: ArchitecturalConcept,
    refine: bool,
    max_backtrack_steps: int | None = None,
) -> ConceptOutcome:
    pool = generate_valid_candidate_pool(
        effective_spec, footprint, required_edges=concept.edges, max_backtrack_steps=max_backtrack_steps
    )
    if not pool:
        return ConceptOutcome(concept=concept, realized=False)
    if refine:
        tagged = generate_tagged_candidates(
            effective_spec, footprint, base_solutions=pool, hard_filter=lambda cand, c=concept: edges_satisfied(c.edges, cand)
        )
    else:
        tagged = [(candidate, "base_pool") for candidate in pool]
    scored = [(candidate, strategy, score_layout(effective_spec, footprint, candidate)) for candidate, strategy in tagged]
    scored.sort(key=lambda entry: entry[2].total_score, reverse=True)
    best_candidate, best_strategy, best_score = scored[0]
    assert edges_satisfied(concept.edges, best_candidate)  # concept edges are HARD -- never silently lost
    return ConceptOutcome(
        concept=concept, realized=True, pool_size=len(pool), candidate_count=len(tagged),
        best_geometry_score=best_score, best_instances=best_candidate, selected_strategy=best_strategy, refined=refine,
    )


def _attempt(spec: ArchitecturalSpec, footprint: BuildingFootprintSpec, min_circulation_segments: int):
    effective_spec, concepts = generate_concepts(spec, min_circulation_segments=min_circulation_segments)
    outcomes = [
        _attempt_concept(effective_spec, footprint, concept, refine=rank < MAX_REFINED_CONCEPTS)
        for rank, concept in enumerate(concepts[:MAX_REALIZED_CONCEPTS])
    ]
    return effective_spec, concepts, outcomes


def plan_with_concepts(spec: ArchitecturalSpec, footprint: BuildingFootprintSpec) -> ConceptPlanResult:
    started = time.monotonic()
    contradiction = _find_pre_solver_contradiction(spec, footprint)
    if contradiction is not None:
        return ConceptPlanResult(status=SolverStatus.unsatisfiable, unsatisfiable_reason=contradiction, runtime_s=time.monotonic() - started)

    # Bounded geometry-probe escalation (same principle validated earlier for Spatial V1's own
    # circulation sizing): the capacity estimate is a precheck, not a feasibility guarantee. If the
    # smallest analytically-sufficient circulation size doesn't realize ANY concept geometrically,
    # retry with one more segment before giving up -- never unbounded, capped by
    # concept_generation.MAX_CIRCULATION_SEGMENTS.
    effective_spec, concepts, outcomes = _attempt(spec, footprint, min_circulation_segments=0)
    base_effective_spec, base_concepts, base_outcomes = effective_spec, concepts, outcomes
    attempt_segments = 0
    while not any(o.realized for o in outcomes) and attempt_segments < MAX_CIRCULATION_SEGMENTS:
        attempt_segments += 1
        effective_spec, concepts, outcomes = _attempt(spec, footprint, min_circulation_segments=attempt_segments)

    # DENSE_CONCEPT_REALIZATION last-chance retry: nothing realized at the legacy budget across
    # every circulation-segment level. Before falling back, spend the larger (but still fixed and
    # bounded) CONCEPT_REALIZATION_STEP_BUDGET on exactly ONE concept -- the single best-tier
    # candidate from the BASE (min_circulation_segments=0) attempt, never a more-escalated one --
    # rather than on every concept at every segment level. Escalating circulation segments changes
    # WHICH concepts get generated (a bigger corridor reshapes the whole candidate set), so the
    # concept that is actually geometrically realizable at the larger budget is only guaranteed to
    # still be `concepts[0]` at the segment level it was measured at; retrying whatever concept the
    # ladder happened to end on last (traced directly: escalation is driven by a capacity precheck
    # that these dense scenarios already pass at segment 0, so it walks all the way to
    # MAX_CIRCULATION_SEGMENTS regardless, ending on an unrelated, larger-corridor concept set) would
    # retry the wrong candidate entirely. This costs the large budget AT MOST ONCE per call: a call
    # that fails still burns close to its full budget, so repeating it across concepts or segments is
    # exactly the multiplicative blowup the task warns against (measured: doing that made two
    # genuinely-infeasible scenarios take 38-45s).
    if not any(o.realized for o in outcomes) and base_concepts:
        retried = _attempt_concept(base_effective_spec, footprint, base_concepts[0], refine=True, max_backtrack_steps=CONCEPT_REALIZATION_STEP_BUDGET)
        if retried.realized:
            effective_spec, concepts = base_effective_spec, base_concepts
            outcomes = [retried] + base_outcomes[1:]

    realized = [o for o in outcomes if o.realized]
    if realized:
        # Tiered selection: the concept tier decides first (banded so a hair's-breadth tier
        # difference can't override a clearly better geometry), geometry score breaks ties.
        best_tier = max(o.concept.tier_score for o in realized)
        contenders = [o for o in realized if o.concept.tier_score >= best_tier - CONCEPT_TIER_BAND]
        winner = max(contenders, key=lambda o: (o.best_geometry_score.total_score, o.concept.tier_score))
        return ConceptPlanResult(
            status=SolverStatus.satisfied, instances=winner.best_instances, concept=winner.concept,
            geometry_score=winner.best_geometry_score, outcomes=outcomes, concepts_considered=len(concepts),
            concepts_realized=len(realized), fallback_used=False, selected_strategy=winner.selected_strategy,
            runtime_s=time.monotonic() - started, effective_spec=effective_spec,
        )

    legacy = plan_v2(spec, footprint)
    return ConceptPlanResult(
        status=legacy.status, instances=list(legacy.instances), concept=None, geometry_score=legacy.score,
        outcomes=outcomes, concepts_considered=len(concepts), concepts_realized=0, fallback_used=True,
        selected_strategy=legacy.selected_strategy, runtime_s=time.monotonic() - started,
        unsatisfiable_reason=legacy.unsatisfiable_reason, effective_spec=spec,
    )


def build_geometric_design_from_plan(spec: ArchitecturalSpec, footprint: BuildingFootprintSpec, result: ConceptPlanResult) -> GeometricDesign:
    if result.status != SolverStatus.satisfied:
        raise ValueError("build_geometric_design_from_plan requires a satisfied ConceptPlanResult")
    if result.concept is not None:
        missing = unsatisfied_edges(result.concept.edges, result.instances)
        if missing:
            raise ValueError(f"selected concept has unrealized edges: {missing}")
    synthetic = GeometrySolverResult(status=SolverStatus.satisfied, instances=result.instances)
    # Use effective_spec (may include SYSTEM_POLICY circulation concept_generation added) so
    # source/relationship derivation for those instances resolves correctly -- falls back to the
    # caller's `spec` only for a legacy-fallback result that never went through concept generation.
    return build_geometric_design(result.effective_spec or spec, footprint, synthetic)
