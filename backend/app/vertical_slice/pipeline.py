"""Stage 11 — Pipeline. Orchestrates the full path this vertical slice was built to prove:

    ArchitecturalSpec -> Concept/DesiredAccessTopology -> Site+parking+entrance
    -> Geometry Core -> Doors -> Windows -> Furniture feasibility -> Validation
    -> GeometricDesign -> Renderer

One call, one candidate, no scoring, no repair — exactly the frozen scope. Each stage is a
plain function import from its own module, so any stage can be swapped or extended later
without touching the others (e.g. a future multi-candidate loop would call `run_once` N times
and score the `GeometricDesign`s, without changing anything inside this module).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import concept as concept_stage
from . import doors as doors_stage
from . import door_clearance
from . import furniture as furniture_stage
from . import site as site_stage
from . import validation as validation_stage
from .wet_rooms import resolve_wet_rooms
from . import windows as windows_stage
from .design_output import GeometricDesign, assemble
from .geometry_core.engine import solve_fixture
from .renderer import render
from .spec import ArchitecturalSpec, demo_spec
from .validation import ValidationReport


@dataclass(frozen=True)
class VerticalSliceResult:
    design: GeometricDesign
    validation: ValidationReport
    render_path: str


def run_once(spec: ArchitecturalSpec, render_path: str) -> VerticalSliceResult:
    concept = concept_stage.build_concept(spec)

    solve = solve_fixture(concept.fixture)

    entrance_local_x = (
        solve.rects[concept.entrance_zone_id].x + solve.rects[concept.entrance_zone_id].w // 2
    )
    site = site_stage.build_site_plan(spec, concept.footprint_width_m, concept.footprint_depth_m,
                                       entrance_local_x)
    rects = site_stage.translate_rects(solve.rects, site.footprint_offset_u)

    interior_doors = doors_stage.generate_interior_doors(concept.fixture, rects)
    # ENTRANCE POLICY (Issue #20): the frozen baseline used to hardcode `HALL_MAIN` as the
    # entrance zone regardless of the realized geometry — the same defect `resolve_entrance` was
    # built to close in the general pipeline. Reading it off the realized rooms here too means
    # every path that draws a front door is held to the same arrival-room policy, and C23 is a
    # true defense-in-depth check rather than one this call site could never actually trip.
    resolved = doors_stage.resolve_entrance(concept.fixture, rects, site.footprint)
    entrance_zone_id = resolved[0] if resolved else concept.entrance_zone_id
    entrance_door = doors_stage.build_entrance_door(site.entrance, site.footprint, entrance_zone_id)
    resolved_doors = door_clearance.resolve_swings(
        concept.fixture, rects, solve.walls, [*interior_doors, entrance_door])
    *interior_doors, entrance_door = resolved_doors
    windows = windows_stage.generate_windows(concept.fixture, rects, site.footprint)
    furniture = furniture_stage.check_furniture_feasibility(concept.fixture, rects, solve.walls)

    report = validation_stage.validate(
        concept.fixture, rects, solve.walls, interior_doors, entrance_door, windows, furniture, site,
        wet_rooms=resolve_wet_rooms(spec.program),
    )

    design = assemble(concept.fixture, rects, solve.walls, solve.wall_iterations,
                       interior_doors, entrance_door, windows, furniture, site,
                       wet_rooms=resolve_wet_rooms(spec.program))

    render(design, render_path)

    return VerticalSliceResult(design, report, render_path)


def run_demo(render_path: str) -> VerticalSliceResult:
    return run_once(demo_spec(), render_path)
