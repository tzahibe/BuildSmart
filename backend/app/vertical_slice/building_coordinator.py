"""Multi-level Phase 1 — the joint search: `ProgramSpec -> [Building]`.

    for each allocation candidate (A, C open, C closed — `level_program.allocate_levels`)
      for each ground outline
        plan ground with CoreLobbyForm.SHRUNK (and, when eligible, ABSORBED too)
        for each upper massing (same outline, or a west/east retreat)
          for each k (how many secondary bedrooms sit on the upper's strip column)
            plan upper with CoreLobbyForm.FULL, PINNED to the ground's realized seam
            validate both levels (C1-C22, unchanged, per level)
            assemble a Building; validate it (V1-V5, V7, V8)
            keep it if both levels and the building are valid

THE TWO LEVELS ARE NEVER PLANNED INDEPENDENTLY. The ground is planned first because it is the
only level with a footprint the site constrains; the upper level's seam is then PINNED to the
ground's REALIZED (not planned) stair rectangle — see `level_planner.py`'s module docstring and
`MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` §2 for why an independently-planned upper level
never lands its stair on the ground's (measured: 0/76).

WHAT THIS MODULE DOES NOT DO (approved Phase 1 scope): rank the candidates it returns against one
another (no A vs C ranking, no lobby-form ranking — every valid `Building` is returned, most
recently found last, for the CALLER to compare); search `V5`/upper lobby forms; consider an L
massing; run more than two levels; wire into `demo/*` or the frontend. `run_general` and every
single-storey code path are untouched — nothing here is imported by them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source

from . import doors as doors_stage
from . import door_clearance
from . import footprint as footprint_module
from . import furniture as furniture_stage
from . import general_pipeline as gp
from . import validation as validation_stage
from . import windows as windows_stage
from .building import (
    Building,
    Level,
    LevelEntry,
    LevelEntryKind,
    LevelKind,
    LevelPlan,
    Massing,
)
from .building_validation import BuildingValidationReport, LevelRealization, validate_building
from .concept_generator import ROOM_TEMPLATES, ConceptCandidate
from .design_output import assemble
from .doors import Door
from .geometry_core.engine import GeometryInfeasible, solve_fixture
from .geometry_core.model import ConnectionKind, ProgramRole, m_to_u, u_to_m
from .level_planner import (
    DEFAULT_SEAT,
    CoreLobbyForm,
    StairSeat,
    eligible_for_absorbed,
    plan_level,
)
from .level_program import LevelAllocation, allocate_levels, closed_fallback, with_upper_strip
from .site import EntranceWalk, SitePlan
from .spec import ArchitecturalSpec, HouseConcept, PlotSpec, ProgramSpec, PublicPrivateStrategy
from .vertical import VerticalCore

#: Sizing-tier fallback ladder `_build` itself uses — normal, then deficit-shrunk, then past-
#: preferred, then both — tried in this order per level, per candidate. Unchanged mechanism
#: (`_row_depths`'s own `allow_deficit`/`allow_hard`), just walked here instead of inside `_build`.
_TIERS = ((False, False), (True, False), (False, True), (True, True))

#: Ground outline proportions, nearest-target-area first — the SAME idea `site_geometry
#: .PREFERRED_RATIOS` uses for the single-storey demo path, reimplemented here (not imported: that
#: module works from a `Project`/`SiteGeometry`, a demo-layer type this backend capability does
#: not depend on). Widened with a couple of shallower/deeper options because the core band adds a
#: minimum-depth floor (`stair_len_m + 2.0`) single-storey outlines never had to clear.
_OUTLINE_RATIOS = (0.95, 1.15, 0.75, 1.45, 1.8)

#: Upper-massing retreats tried, nearest (no retreat) first — the only Phase-1 upper massing:
#: the same outline, or a single-side retreat (first report §6). A retreat's freed strip becomes
#: a roof terrace on the ground level below (`Massing.retreat_m2`); classifying it as one is a
#: later phase's work (first report §6, "not yet classified").
_RETREATS: tuple[tuple[str, float, float], ...] = (("same", 0.0, 0.0), ("W1", 1.0, 0.0),
                                                    ("W2", 2.0, 0.0), ("E1", 0.0, 1.0))


@dataclass(frozen=True)
class BuildingCandidate:
    """One complete, validated two-level building, with the search choices that produced it —
    diagnostic, not a ranking key. `family` names the allocation/lobby-form/massing combination
    for grouping (`MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` §10's "family before repeat").

    `ground_warnings`/`upper_warnings` are the REALIZED `LevelProgram.warnings` from the exact
    `LevelAllocation` that produced this candidate — carried here at construction time, never
    reconstructed afterward from `(strategy, ground_layout)` the way the ranking investigation
    had to (`MULTI_LEVEL_CANDIDATE_RANKING_INVESTIGATION_REPORT.md` §1: recomputing them by
    re-calling `allocate_levels` is lossless only because warnings are a pure function of the
    programme and the chosen strategy/layout — true today, not a property a caller should have to
    rely on). This is what lets `primary_selection.select_primary` read a candidate's explicit-
    preference and quality-warning signals directly, with no second source of truth.
    """

    building: Building
    strategy: str
    ground_layout: str
    ground_lobby_form: str
    outline_m: tuple[float, float]
    retreat: str
    upper_strip_bedrooms: int
    building_validation: BuildingValidationReport
    ground_warnings: tuple[str, ...] = ()
    upper_warnings: tuple[str, ...] = ()

    @property
    def family(self) -> str:
        return f"{self.strategy}/{self.ground_layout}/{self.ground_lobby_form}/{self.retreat}"

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.ground_warnings + self.upper_warnings


@dataclass(frozen=True)
class BuildingRefusal:
    """One search branch that did not produce a building, and why — reported the way
    `ConceptRejection` reports a single-level strategy's refusal, so a caller can explain a
    fully-empty result without re-running the search."""

    strategy: str
    stage: str          # "ground" | "upper" | "building"
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class CoordinatorResult:
    candidates: tuple[BuildingCandidate, ...]
    refusals: tuple[BuildingRefusal, ...]
    elapsed_s: float = 0.0

    @property
    def any(self) -> bool:
        return bool(self.candidates)


def plan_buildings(program: ProgramSpec, plot: PlotSpec, total_built_area_m2: float, *,
                   concept: HouseConcept | None = None, seat: StairSeat = DEFAULT_SEAT,
                   stop_at_first: bool = False, outline_count: int = 4) -> CoordinatorResult:
    """The bounded joint search described in the module docstring.

    `stop_at_first=True` is the fast path a production caller wants (the first valid building,
    in the search order below — allocation A before C, SHRUNK before ABSORBED, nearest outline
    first, no retreat before a retreat, k=0 upward); `False` (the default) is the survey a
    measurement or a "show every valid candidate" caller wants.

    `concept` is the SAME `HouseConcept` a single-storey house already carries
    (`ArchitecturalSpec.concept`, `spec.py`) — not a second, multi-level-only preference type.
    `concept=None` (the default) reproduces exactly today's behaviour: every allocation is tried,
    nothing is filtered, `primary_selection.select_primary` sees no explicit strategy preference
    to honour. When `concept.public_private_strategy` is bound and `concept.is_binding
    ("public_private_strategy")` (i.e. the person's own `hard_fields` made it HARD, the same
    grammar `CorridorRequirement`/`RelationStrength` already use), the OTHER allocation is not
    even generated — a HARD preference is a real constraint, gated here exactly where every other
    hard constraint in this search is gated, not a ranking bonus (`primary_selection.py` never
    sees the excluded allocation at all). A PREFERENCE-strength `public_private_strategy` changes
    nothing here — both allocations are still generated, and the preference is read in ranking.
    """
    started = time.perf_counter()
    candidates: list[BuildingCandidate] = []
    refusals: list[BuildingRefusal] = []
    spec = ArchitecturalSpec(plot=plot, program=program)
    bx, by = plot.buildable_origin_m()
    bw, bd = plot.buildable_size_m()
    x0_u, y0_u = m_to_u(bx), m_to_u(by)
    hard_strategy = (concept.public_private_strategy
                     if concept is not None and concept.is_binding("public_private_strategy")
                     and concept.public_private_strategy is not PublicPrivateStrategy.ENGINE
                     else None)

    for allocation in allocate_levels(program):
        if hard_strategy is not None and allocation.strategy is not hard_strategy:
            refusals.append(BuildingRefusal(
                allocation.strategy.value, "allocation", "HARD_PREFERENCE_EXCLUDED",
                f"the person's public_private_strategy is HARD-bound to {hard_strategy.value}"))
            continue
        ground_target, upper_target = _split_target(total_built_area_m2, allocation)
        outlines = _ground_outlines(bw, bd, ground_target, outline_count)
        if not outlines:
            refusals.append(BuildingRefusal(allocation.strategy.value, "ground", "NO_GROUND_OUTLINE",
                                            f"target {ground_target:.1f} m2 does not fit {bw:.2f}x{bd:.2f} m"))
            continue

        ground_forms = [(allocation, CoreLobbyForm.SHRUNK)]
        if eligible_for_absorbed(allocation.ground):
            ground_forms.append((allocation, CoreLobbyForm.ABSORBED))
        closed = closed_fallback(allocation, program)
        if closed is not None:
            ground_forms.append((closed, CoreLobbyForm.SHRUNK))

        for ground_alloc, ground_form in ground_forms:
            for fw, fh in outlines:
                ground_result = _plan_and_realize_ground(spec, ground_alloc, fw, fh, x0_u, y0_u,
                                                         seat, ground_form, bx, by)
                if isinstance(ground_result, BuildingRefusal):
                    refusals.append(ground_result)
                    continue
                ground_plan, ground_solve, ground_cand = ground_result
                west_seam_m = u_to_m(ground_solve.rects["STAIR"].x - x0_u)

                secondary_upstairs = [r for r in ground_alloc.upper.rooms
                                      if r.role.value == "BEDROOM"]
                k_values = range(0, len(secondary_upstairs) + 1) or (0,)
                found_for_ground = False
                for retreat_name, dw, de in _RETREATS:
                    ufw, ufh = round(fw - dw - de, 2), fh
                    ux0 = x0_u + m_to_u(dw)
                    for k in k_values:
                        upper_alloc = with_upper_strip(ground_alloc, k)
                        if not upper_alloc.upper.corridor_rooms:
                            continue
                        upper_result = _plan_and_realize_upper(
                            spec, upper_alloc, ufw, ufh, ux0, y0_u, seat,
                            round(west_seam_m - dw, 2), bx + dw, by)
                        if isinstance(upper_result, BuildingRefusal):
                            refusals.append(upper_result)
                            continue
                        upper_plan, upper_solve, upper_cand = upper_result

                        building, v_report = _assemble_building(
                            ground_alloc, ground_plan, ground_solve, ground_cand,
                            upper_plan, upper_solve, upper_cand, program)
                        if not v_report.ok:
                            refusals.append(BuildingRefusal(
                                ground_alloc.strategy.value, "building", "V_FAILED",
                                "; ".join(f"{c.check_id}: {c.detail}" for c in v_report.failures())))
                            continue

                        candidates.append(BuildingCandidate(
                            building, ground_alloc.strategy.value,
                            ground_alloc.ground.ground_layout.value if ground_alloc.ground.ground_layout else "-",
                            ground_form.value, (fw, fh), retreat_name, k, v_report,
                            ground_warnings=tuple(ground_alloc.ground.warnings),
                            upper_warnings=tuple(upper_alloc.upper.warnings)))
                        found_for_ground = True
                        if stop_at_first:
                            return CoordinatorResult(tuple(candidates), tuple(refusals),
                                                     time.perf_counter() - started)
                    if found_for_ground and stop_at_first:
                        break
    return CoordinatorResult(tuple(candidates), tuple(refusals), time.perf_counter() - started)


#: Every level's target gross carries the core band's own target area TOO — `LevelProgram
#: .target_gross_m2` is a room count over `level_program.py`'s output, which never includes
#: `HALL`/`HALL_2`/`STAIR` (`level_planner.py` adds those at plan-time, per band form). Splitting
#: on room-only targets alone skews toward the level with the bigger room list — the ground's
#: LDK+safe room dwarfs the upper's bedrooms — and understates BOTH levels by the same ~18-25 m2
#: the follow-up report measured (§1.1) as the actual circulation cost. Adding a FIXED estimate
#: to both sides, from the SAME templates `_band_rooms` draws from, pulls the ratio toward what
#: is actually planned without hardcoding the ratio itself.
_CIRCULATION_ESTIMATE_M2 = 2 * ROOM_TEMPLATES[ProgramRole.HALL].target_area_m2 + \
    ROOM_TEMPLATES[ProgramRole.STAIRWELL].target_area_m2


def _split_target(total_m2: float, allocation: LevelAllocation) -> tuple[float, float]:
    """The total requested area, split between levels by each level's OWN target gross — the
    allocation's own programme arithmetic, not an engine guess (first report §7) — plus the
    circulation estimate both levels' core band actually costs (`_CIRCULATION_ESTIMATE_M2`)."""
    g = allocation.ground.target_gross_m2 + _CIRCULATION_ESTIMATE_M2
    u = allocation.upper.target_gross_m2 + _CIRCULATION_ESTIMATE_M2
    total_target = max(g + u, 1e-6)
    return round(total_m2 * g / total_target, 1), round(total_m2 * u / total_target, 1)


def _ground_outlines(bw: float, bd: float, area: float, count: int) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for ratio in _OUTLINE_RATIOS[:count]:
        w = round(min(max((area * ratio) ** 0.5, area / bd), bw) / 0.05) * 0.05
        d = round(area / max(w, 1e-6) / 0.05) * 0.05
        if w > bw + 1e-9 or d > bd + 1e-9 or w <= 0 or d <= 0:
            continue
        if any(abs(w - existing) < 0.05 for existing, _ in out):
            continue
        out.append((round(w, 2), round(d, 2)))
        if len(out) == count:
            break
    return out


def _buildable(x: float, y: float, w: float, d: float) -> BuildableRegion:
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(x, y, w, d))),
        Provenance(Source.USER, Authority.AUTHORITATIVE, ref="multi-level coordinator"))


def _plan_and_realize_ground(spec, ground_alloc: LevelAllocation, fw: float, fh: float,
                             x0_u: int, y0_u: int, seat: StairSeat, lobby_form: CoreLobbyForm,
                             bx: float, by: float):
    """The ground level: planned with the core band and realized through the UNCHANGED single-
    storey `general_pipeline._realize` (a real street entrance, a real site plan) — the ground
    level of a two-storey house is entered exactly like a one-storey house's only level."""
    buildable = _buildable(bx, by, fw, fh)
    last = ""
    for allow_deficit, allow_hard in _TIERS:
        candidates, failure = plan_level(ground_alloc.ground, fw, fh, x0_u, y0_u, seat, lobby_form,
                                         kind="ground", allow_deficit=allow_deficit,
                                         allow_hard=allow_hard)
        if failure is not None:
            last = f"{failure.reason}: {failure.detail}"
            continue
        for index, candidate in enumerate(candidates):
            try:
                solve = solve_fixture(candidate.concept.fixture)
            except GeometryInfeasible as exc:
                last = f"GEOMETRY_INFEASIBLE: {exc}"
                continue
            plan = gp._realize(spec, buildable, None, candidate, index, solve, ())
            if plan.ok:
                return plan, solve, candidate
            last = "ground C-checks: " + ", ".join(c.check_id for c in plan.validation.failures())
    return BuildingRefusal(ground_alloc.strategy.value, "ground", "GROUND_FAILED", last)


def _plan_and_realize_upper(spec, upper_alloc: LevelAllocation, fw: float, fh: float,
                            x0_u: int, y0_u: int, seat: StairSeat, fixed_seam_m: float,
                            bx: float, by: float):
    """The upper level: planned with the core band PINNED to the ground's realized seam, and
    realized by `_realize_upper` — the SAME per-level stages (`doors`, `windows`, `furniture`,
    `validate`, `assemble`), called directly rather than through `general_pipeline._realize`
    because that function always resolves a STREET entrance and a real site plan, neither of
    which the upper level has (first report §5, `LevelContext`)."""
    buildable = _buildable(bx, by, fw, fh)
    last = ""
    for allow_deficit, allow_hard in _TIERS:
        candidates, failure = plan_level(upper_alloc.upper, fw, fh, x0_u, y0_u, seat,
                                         CoreLobbyForm.FULL, kind="upper",
                                         allow_deficit=allow_deficit, allow_hard=allow_hard,
                                         fixed_seam_m=fixed_seam_m)
        if failure is not None:
            last = f"{failure.reason}: {failure.detail}"
            continue
        for index, candidate in enumerate(candidates):
            try:
                solve = solve_fixture(candidate.concept.fixture)
            except GeometryInfeasible as exc:
                last = f"GEOMETRY_INFEASIBLE: {exc}"
                continue
            plan = _realize_upper(spec, candidate, solve, buildable)
            if plan.ok:
                return plan, solve, candidate
            last = "upper C-checks: " + ", ".join(c.check_id for c in plan.validation.failures())
    return BuildingRefusal(upper_alloc.strategy.value, "upper", "UPPER_FAILED", last)


def _realize_upper(spec: ArchitecturalSpec, candidate: ConceptCandidate, solve, buildable: BuildableRegion):
    """The upper level's own realize: no street, no parking, no garden — `LevelEntry
    .STAIR_ARRIVAL`'s zone is the core, so `validate` seeds C5 from it (`entry_seed="STAIR"`) and
    skips the site checks entirely (`skip_site_checks=True`) instead of trusting a synthetic site
    plan to pass them. Every other stage — doors, windows, furniture, C1-C9/C13/C17/C20-22 — is
    the SAME code the ground level and every single-storey plan already run."""
    concept = candidate.concept
    wings = tuple(w.rect() for w in concept.fixture.wings)
    footprint = footprint_module.bounding_box(wings)
    rects = solve.rects
    interior_doors = doors_stage.generate_interior_doors(concept.fixture, rects)
    interior_doors = door_clearance.resolve_swings(concept.fixture, rects, solve.walls, interior_doors)
    windows = windows_stage.generate_windows(concept.fixture, rects, footprint, wings)
    furniture = furniture_stage.check_furniture_feasibility(concept.fixture, rects, solve.walls)

    # A degenerate site: no parking, an entrance walk collapsed to a point, arriving at the
    # core's own zone (the level's `LevelEntry`, not a street door — see the docstring above).
    stair_rect = rects["STAIR"]
    site_plan = SitePlan(plot=footprint, footprint=footprint, footprint_offset_u=(footprint.x, footprint.y),
                         parking=(), entrance=EntranceWalk((stair_rect.x, stair_rect.y), stair_rect),
                         garden=(), wings=wings)
    # width_m=0.0: a placeholder, no real leaf — `door_clearance` skips every zero-width door.
    entrance_door = Door("STAIR", "STAIR", ConnectionKind.DOOR, 0.0, (stair_rect.x, stair_rect.y),
                         "horizontal", placeable=True, shared_length_m=0.0)

    validation = validation_stage.validate(
        concept.fixture, rects, solve.walls, interior_doors, entrance_door, windows, furniture,
        site_plan, corridor=spec.program.corridor, wet_rooms=candidate.wet_rooms,
        entry_seed="STAIR", skip_site_checks=True)
    design = assemble(concept.fixture, rects, solve.walls, solve.wall_iterations, interior_doors,
                      entrance_door, windows, furniture, site_plan,
                      over_preferred=candidate.over_preferred, wet_rooms=candidate.wet_rooms)
    safety = gp._check_safety(design, buildable.require_known(), buildable.require_known().__class__())
    return gp.RealizedPlan(index=0, concept=candidate, design=design, validation=validation, safety=safety)


def _assemble_building(ground_alloc: LevelAllocation, ground_plan, ground_solve, ground_cand,
                       upper_plan, upper_solve, upper_cand, program: ProgramSpec,
                       ) -> tuple[Building, BuildingValidationReport]:
    ground_level = Level("L0", 0, LevelKind.GROUND)
    upper_level = Level("L1", 1, LevelKind.UPPER)
    ground_entry = LevelEntry(LevelEntryKind.STREET_DOOR, zone_id=ground_plan.design.entrance_door.b)
    core_id = "STAIR_1"
    upper_entry = LevelEntry(LevelEntryKind.STAIR_ARRIVAL, zone_id="STAIR", core_id=core_id)

    ground_lp = LevelPlan(ground_level, ground_entry, ground_plan.design, ground_plan.validation,
                          concept=ground_cand, safety=ground_plan.safety)
    upper_lp = LevelPlan(upper_level, upper_entry, upper_plan.design, upper_plan.validation,
                         concept=upper_cand, safety=upper_plan.safety)

    massing = Massing(ground_plan.design.plot_m, (ground_plan.design.footprints_m, upper_plan.design.footprints_m))
    core = VerticalCore.realize(core_id, "L0", "L1", ground_solve.rects, upper_solve.rects,
                                ground_cand.concept.fixture.zones, upper_cand.concept.fixture.zones,
                                floor_to_floor_m=DEFAULT_SEAT.floor_to_floor_m)
    building = Building(levels=(ground_lp, upper_lp), massing=massing, cores=(core,))

    # V1/V3/V4/V5 need the RAW realized geometry (`building_validation.LevelRealization`'s own
    # docstring says why `GeometricDesign` cannot supply it) — `interior_doors` is recomputed
    # here rather than threaded out of `_realize`/`_realize_upper`: `generate_interior_doors` is
    # PURE (fixture + solved rects only), so calling it again returns the IDENTICAL list, not an
    # approximation of one. `entrance_door` for V4's OUTSIDE seed only needs `.b`/`.placeable`,
    # which `GeometricDesign.entrance_door` (a `DoorOut`) already carries — the upper level has
    # none (`_realize_upper`'s is a placeholder for the DTO's sake, never meant to seed anything).
    ground_realization = LevelRealization(
        "L0", ground_solve.rects, ground_solve.walls,
        tuple(doors_stage.generate_interior_doors(ground_cand.concept.fixture, ground_solve.rects)),
        ground_plan.design.entrance_door, ground_cand.concept.fixture.zones, ground_entry.zone_id)
    upper_realization = LevelRealization(
        "L1", upper_solve.rects, upper_solve.walls,
        tuple(doors_stage.generate_interior_doors(upper_cand.concept.fixture, upper_solve.rects)),
        None, upper_cand.concept.fixture.zones, upper_entry.zone_id)

    v_report = validate_building(building, (ground_realization, upper_realization), program)
    return building, v_report
