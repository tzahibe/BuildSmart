"""End-to-end: general authoritative geometry -> the EXISTING vertical slice, unchanged.

    BuildableRegion -> SafeGeometryAdapter -> Geometry Core -> Doors -> Windows
                    -> Furniture -> Validation -> GeometricDesign -> Renderer

Nothing in `concept.py`, `geometry_core/`, `doors.py`, `windows.py`, `furniture.py`,
`validation.py`, `design_output.py` or `renderer.py` was changed to make this work. This module
only chooses WHERE the existing concept's footprint is placed, using a candidate the adapter
has already proven safe, and then adds the safety checks the general-geometry case needs on top
of the slice's own 12:

  * every room lies inside the authoritative buildable region (checked against the exact
    arc-aware containment, not the linearization the candidate came from);
  * no room overlaps any exclusion/obstacle constraint.

The canonical `pipeline.run_demo` is untouched and still produces the frozen baseline.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.geometry_domain.constraints import (
    BuildableRegion,
    ConstraintRole,
    GeometricConstraint,
    SiteConstraints,
)
from app.geometry_domain.primitives import MultiRegion

from . import concept_generator as generator
from . import doors as doors_stage
from . import relationships as relationships_stage
from . import furniture as furniture_stage
from . import site as site_stage
from . import validation as validation_stage
from . import windows as windows_stage
from .design_output import GeometricDesign, assemble
from .geometry_core.engine import GeometryInfeasible, solve_fixture
from .geometry_core.model import UNIT_M, Rect
from .renderer import render
from .safe_adapter import (
    AdapterOutcome,
    SafeGeometryResult,
    SolverGeometryCandidate,
    adapt,
    build_buildable_region,
)
from .site import EntranceWalk, SitePlan
from .spec import ArchitecturalSpec, PlotSpec, ProgramSpec


@dataclass(frozen=True)
class SafetyReport:
    """The general-geometry checks, separate from the slice's own validation."""

    rooms_inside_buildable: bool
    rooms_clear_of_exclusions: bool
    offending_rooms: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.rooms_inside_buildable and self.rooms_clear_of_exclusions


@dataclass(frozen=True)
class RunMetrics:
    """Per-scenario metrics (task section 11)."""

    concept_candidates_generated: int = 0
    candidates_rejected_pre_solver: int = 0
    solver_attempts: int = 0
    first_valid_candidate_index: int | None = None
    latency_ms: float = 0.0
    room_count: int = 0
    wing_count_offered: int = 0
    wings_used: int = 0
    unused_safe_wing_area_m2: float = 0.0
    residual_area_m2: float = 0.0
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneralSliceResult:
    outcome: AdapterOutcome
    adapter: SafeGeometryResult
    design: GeometricDesign | None = None
    validation: validation_stage.ValidationReport | None = None
    safety: SafetyReport | None = None
    render_path: str | None = None
    chosen_candidate: SolverGeometryCandidate | None = None
    concept: generator.ConceptCandidate | None = None
    metrics: RunMetrics = field(default_factory=RunMetrics)
    notes: tuple[str, ...] = ()
    #: Every requested room relationship, measured on the plan that was actually built.
    relationships: tuple = ()

    @property
    def ok(self) -> bool:
        return (
            self.outcome is AdapterOutcome.SOLVED
            and self.validation is not None and self.validation.ok
            and self.safety is not None and self.safety.ok
        )


def _place_footprint(candidate: Rect, w_m: float, h_m: float) -> tuple[int, int]:
    """Centre the footprint in the candidate horizontally, flush to its street side — the same
    convention `site.place_footprint` uses, so case A reproduces the canonical layout."""
    w_u, h_u = round(w_m / UNIT_M), round(h_m / UNIT_M)
    return candidate.x + (candidate.w - w_u) // 2, candidate.y


def _site_plan_for(spec: ArchitecturalSpec, footprint: Rect) -> SitePlan:
    """Reuse the existing site stage's parking/entrance/garden logic with an externally chosen
    footprint placement (the one piece `place_footprint` would otherwise decide)."""
    plot = Rect(0, 0, round(spec.plot.width_m / UNIT_M), round(spec.plot.depth_m / UNIT_M))
    parking = site_stage.build_parking(spec)
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    garden = site_stage.classify_garden(spec, plot, footprint, parking)
    return SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance, garden)


def _exclusion_geometry(site: SiteConstraints | None) -> MultiRegion:
    if site is None:
        return MultiRegion()
    from app.geometry_domain.booleans import union

    out = MultiRegion()
    for constraint in site.constraints:
        if constraint.role in (ConstraintRole.OBSTACLE, ConstraintRole.NO_BUILD_REGION):
            out = union(out, constraint.geometry) if not out.is_empty else constraint.geometry
    return out


def _check_safety(design: GeometricDesign, authoritative: MultiRegion,
                  exclusions: MultiRegion) -> SafetyReport:
    from app.geometry_domain.booleans import multiregion_to_shapely
    from shapely.geometry import box

    offenders: list[str] = []
    inside_all = True
    clear_all = True
    exclusion_geom = None if exclusions.is_empty else multiregion_to_shapely(exclusions)

    for room in design.rooms:
        x, y, w, h = room.rect_m
        # Exact arc-aware containment, sampled across the room including its corners.
        for i in range(9):
            for j in range(9):
                px = x + 1e-6 + (w - 2e-6) * i / 8
                py = y + 1e-6 + (h - 2e-6) * j / 8
                if not authoritative.contains_point((px, py)):
                    inside_all = False
                    offenders.append(room.zone_id)
                    break
            else:
                continue
            break
        if exclusion_geom is not None:
            if box(x, y, x + w, y + h).intersection(exclusion_geom).area > 1e-9:
                clear_all = False
                if room.zone_id not in offenders:
                    offenders.append(room.zone_id)

    return SafetyReport(inside_all, clear_all, tuple(dict.fromkeys(offenders)))


def _relationship_outcomes(concept_candidate, solve, relationships):
    """Measure one realized candidate. Doors are generated here because DIRECT_ACCESS and NEAR are
    defined over the REALIZED access graph, which does not exist until they are."""
    fixture = concept_candidate.concept.fixture
    doors = doors_stage.generate_interior_doors(fixture, solve.rects)
    connections = validation_stage.realized_connections(solve.rects, solve.walls, doors)
    return relationships_stage.evaluate(fixture, solve.rects, connections, relationships)


def run_general(buildable: BuildableRegion, *,
                render_path: str | None = None,
                site_constraints: SiteConstraints | None = None,
                plot_size_m: tuple[float, float] = (24.0, 28.0),
                program: ProgramSpec | None = None,
                fast_path: bool = True) -> GeneralSliceResult:
    """Run one authoritative buildable region all the way through the existing slice.

    The concept now comes from the GENERATOR, not from a hard-coded fixture: the adapter's safe
    candidates and the ArchitecturalSpec go in, a small bounded set of concepts comes out, and
    they are tried in order until Geometry Core realizes one. `fast_path` stops at the first
    valid candidate (the default); set it False to measure every candidate.
    """
    started = time.perf_counter()
    spec = ArchitecturalSpec(
        plot=PlotSpec(width_m=plot_size_m[0], depth_m=plot_size_m[1]),
        program=program or ProgramSpec(),
    )

    adapter_result = adapt(buildable)
    if adapter_result.outcome is not AdapterOutcome.SOLVED:
        return GeneralSliceResult(adapter_result.outcome, adapter_result,
                                  notes=adapter_result.notes)

    generated = generator.generate_concepts(spec, list(adapter_result.candidates))
    base_metrics = dict(
        concept_candidates_generated=len(generated.candidates),
        candidates_rejected_pre_solver=len(generated.rejections),
        wing_count_offered=len(adapter_result.candidates),
        room_count=len(generated.program),
        residual_area_m2=round(sum(r.area_m2 for r in adapter_result.residuals), 2),
        rejection_reasons=tuple(f"{r.strategy.value}/{r.reason.value}: {r.detail}"
                                for r in generated.rejections),
    )
    if not generated.candidates:
        return GeneralSliceResult(
            AdapterOutcome.INSUFFICIENT_RECTANGULAR_CAPACITY, adapter_result,
            metrics=RunMetrics(latency_ms=round((time.perf_counter() - started) * 1000, 1),
                               **base_metrics),
            notes=base_metrics["rejection_reasons"])

    attempts = 0
    chosen: generator.ConceptCandidate | None = None
    solve = None
    failures: list[str] = []
    relationships = spec.program.relationships
    # Room relationships are honoured by CHOOSING between candidates the generator already
    # produces, not by rebuilding how it produces them — the smallest extension compatible with the
    # current architecture. Each realized candidate is measured on its actual geometry (the same
    # function C15 uses), a candidate that breaks a HARD relationship is passed over, and among
    # those that survive the one satisfying the most PREFERENCES wins. Without relationships this
    # loop behaves exactly as before, including the fast path.
    best_score: tuple[int, int] | None = None
    best_solve = None
    for index, concept_candidate in enumerate(generated.candidates):
        attempts += 1
        try:
            candidate_solve = solve_fixture(concept_candidate.concept.fixture)
        except GeometryInfeasible as exc:
            failures.append(f"candidate {index} ({concept_candidate.strategy.value}): {exc}")
            continue

        if not relationships:
            chosen, solve, chosen_index = concept_candidate, candidate_solve, index
            if fast_path:
                break
            continue

        outcomes = _relationship_outcomes(concept_candidate, candidate_solve, relationships)
        broken = [o for o in outcomes if o.is_hard and not o.satisfied]
        if broken:
            failures.append(
                f"candidate {index} ({concept_candidate.strategy.value}) breaks a required "
                f"relationship: " + "; ".join(f"{o.statement} — {o.detail}" for o in broken))
            continue

        # Preferences only ever break a TIE between candidates that already satisfy every hard
        # relationship; `-index` keeps the generator's own ordering as the tiebreak, so a preference
        # can never promote a candidate the generator ranked lower on its own merits by more than
        # the preference it actually delivers.
        score = (sum(1 for o in outcomes if o.satisfied), -index)
        if best_score is None or score > best_score:
            best_score, best_solve = score, candidate_solve
            chosen, chosen_index = concept_candidate, index
        if best_score[0] == len(outcomes):
            break

    if relationships and best_solve is not None:
        # `solve` must always be the solve of the CHOSEN candidate. Assigning it inside the loop
        # left the two out of step whenever a later candidate was rejected, and the pipeline then
        # measured one fixture against another's rectangles — C2 reported thousands of unassigned
        # units. Set it once, here, from the candidate that actually won.
        solve = best_solve

    if chosen is None or solve is None:
        return GeneralSliceResult(
            AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY, adapter_result,
            metrics=RunMetrics(solver_attempts=attempts,
                               latency_ms=round((time.perf_counter() - started) * 1000, 1),
                               **base_metrics),
            notes=tuple(failures))

    concept = chosen.concept
    wing = concept.fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    rects = solve.rects  # the generator positions the wing in plot coordinates already
    site_plan = _site_plan_for(spec, footprint)

    interior_doors = doors_stage.generate_interior_doors(concept.fixture, rects)
    entrance_door = doors_stage.build_entrance_door(site_plan.entrance, footprint,
                                                    concept.entrance_zone_id)
    windows = windows_stage.generate_windows(concept.fixture, rects, footprint)
    furniture = furniture_stage.check_furniture_feasibility(concept.fixture, rects, solve.walls)

    validation = validation_stage.validate(
        concept.fixture, rects, solve.walls, interior_doors, entrance_door,
        windows, furniture, site_plan,
        corridor=spec.program.corridor,
        relationships=relationships,
    )
    design = assemble(concept.fixture, rects, solve.walls, solve.wall_iterations,
                      interior_doors, entrance_door, windows, furniture, site_plan)

    safety = _check_safety(design, buildable.require_known(), _exclusion_geometry(site_constraints))
    path = render(design, render_path) if render_path else None

    used_wings = {c.order for c in adapter_result.candidates
                  if c.order in chosen.wing_orders}
    unused = sum(c.area_m2 for c in adapter_result.candidates if c.order not in used_wings)
    metrics = RunMetrics(
        solver_attempts=attempts,
        first_valid_candidate_index=chosen_index,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        wings_used=len(chosen.wing_orders),
        unused_safe_wing_area_m2=round(unused, 2),
        **base_metrics,
    )
    return GeneralSliceResult(
        AdapterOutcome.SOLVED, adapter_result, design, validation, safety, path,
        adapter_result.candidates[0], chosen, metrics, tuple(failures),
        # Measured on the CHOSEN plan, so the summary the person reads and the plan they see are
        # the same thing.
        relationships=tuple(relationships_stage.evaluate(
            concept.fixture, rects,
            validation_stage.realized_connections(rects, solve.walls, interior_doors),
            relationships)) if relationships else ())


def run_general_from_site(site: SiteConstraints, *, render_path: str | None = None,
                          plot_size_m: tuple[float, float] = (24.0, 28.0),
                          program: ProgramSpec | None = None,
                          fast_path: bool = True) -> GeneralSliceResult:
    """parcel + constraints -> buildable region -> the full run."""
    buildable = build_buildable_region(site)
    return run_general(buildable, render_path=render_path, site_constraints=site,
                       plot_size_m=plot_size_m, program=program, fast_path=fast_path)
