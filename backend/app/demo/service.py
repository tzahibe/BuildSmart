"""The demo generation service — the ONE place the validated pipeline is driven from.

    Project (parsed, user-corrected requirements)
      -> scope.check_supported            explicit refusal, never a silent downgrade
      -> requirements_view.spec_for       Project -> vertical_slice.ArchitecturalSpec
      -> _outlines_for                    the person's outline (if any), then the engine's shapes
      -> run_general, once per outline    unchanged below this line:
           -> concept_generator             DesiredAccessTopology + concept candidates
           -> safe_adapter                  BuildableRegion -> safe solver rectangles
           -> geometry_core                 realization
           -> doors / windows / furniture
           -> validation                    C1-C16, hard gate
      -> _select_plans                    primary nearest the requested area; alternatives by family
      -> contract.to_demo_design          authoritative API payload, each plan with its outline

Feature 006: the outline is the engine's to choose unless the person fixed one under "advanced";
see `_plan_outlines_until_one_plans` and `_select_plans` for the two rules, and
specs/006-engine-chosen-outline/RESULTS.md for what they measured.

No canonical fixture is reachable from here: `concept.py`'s hand-authored concept and
`geometry_fixtures.py` are never imported. The old `app.geometry.solver` path is not used.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.projects.models import Project, SelectedFootprint
from app.vertical_slice.concept_generator import (
    RejectionReason,
    build_room_program,
    program_capacity_gross_m2,
)
from app.vertical_slice.relationships import describe
from app.vertical_slice.spec import RelationStrength
from app.vertical_slice.general_pipeline import (
    ALTERNATIVE_PLAN_LIMIT,
    GeneralSliceResult,
    RealizedPlan,
    run_general,
)
from app.vertical_slice.safe_adapter import AdapterOutcome
from app.vertical_slice.site import front_band_m

from .contract import (
    DemoDesign,
    DemoPlanSet,
    OutlineOut,
    OutlineTried,
    SearchSummary,
    to_demo_design,
)
from .requirements_view import spec_for
from . import site_geometry
from .scope import ScopeRejection, check_supported


#: Refusals that are about FEASIBILITY — this brief, this parcel, these assumptions — rather than
#: about a malformed request. Each carries the scoping sentence so no refusal can be read as
#: "this house cannot be designed".
_FEASIBILITY_CODES = frozenset({
    "PLAN_NOT_REALIZABLE",
    "PLAN_FAILED_VALIDATION",
    "PLAN_OUTSIDE_BUILDABLE",
    "TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY",
    "CORRIDOR_WIDTH_NOT_FEASIBLE",
    "ROOM_RELATIONSHIP_NOT_FEASIBLE",
    "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION",
    "FOOTPRINT_LEAVES_NO_ROOM_FOR_PARKING",
    "SITE_GEOMETRY_REQUIRED",
})
#: NO_BUILDABLE_AREA is deliberately NOT in that set. It is a feasibility refusal, but it already
#: carries a stronger version of the scoping sentence in its own text — the house was never weighed
#: against anything, so nothing about it was decided — and appending the generic one would say the
#: same thing twice. See site_geometry.no_buildable_area_message.


class DemoGenerationError(Exception):
    """A product-level failure. Carries a message meant for a person — and, separately, what the
    ENGINE actually did.

    `message` is written to be read by whoever asked for the house. It deliberately says nothing
    about slicing candidates or check IDs, which means that on its own it is useless for fixing
    anything: "we could not produce a valid plan" names no cause. `diagnostics` is the other half —
    every candidate the generator produced and why each was rejected, which validation checks
    failed, how many solver attempts it took. It never reaches the screen and always reaches the
    failure log.
    """

    def __init__(self, code: str, message: str, detail: str = "",
                 diagnostics: dict | None = None) -> None:
        if code in _FEASIBILITY_CODES:
            message = f"{message} {site_geometry.NOT_FEASIBLE_HE}"
            detail = f"{detail} [{site_geometry.NOT_FEASIBLE_PHRASE}]".strip()
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.diagnostics = diagnostics or {}


def _diagnostics(result, spec=None, outlines=None) -> dict:
    """Everything the engine knows about why this run did not produce a plan.

    Written for whoever reads the log later, not for the person at the screen: the concept
    candidates tried, the reason each was rejected, the validation checks that failed, and the
    programme that was being solved for. Without this an entry says only that somebody was refused.
    """
    diagnostics: dict = {}
    metrics = getattr(result, "metrics", None)
    if metrics is not None:
        diagnostics["engine"] = {
            "outcome": getattr(getattr(result, "outcome", None), "value", None),
            "concept_candidates_generated": metrics.concept_candidates_generated,
            "candidates_rejected_pre_solver": metrics.candidates_rejected_pre_solver,
            "solver_attempts": metrics.solver_attempts,
            "first_valid_candidate_index": metrics.first_valid_candidate_index,
            "latency_ms": metrics.latency_ms,
            "room_count": metrics.room_count,
            "residual_area_m2": metrics.residual_area_m2,
            # THE ACTUAL CAUSE, one line per rejected candidate.
            "rejection_reasons": list(metrics.rejection_reasons),
        }
    notes = getattr(result, "notes", None)
    if notes:
        diagnostics["notes"] = list(notes)
    validation = getattr(result, "validation", None)
    if validation is not None:
        diagnostics["validation"] = {
            "ok": validation.ok,
            "failed_checks": [{"check": c.check_id, "name": c.name, "detail": c.detail}
                              for c in validation.failures()],
            "checks_run": [c.check_id for c in validation.checks],
        }
    safety = getattr(result, "safety", None)
    if safety is not None and not safety.ok:
        diagnostics["safety"] = {"offending_rooms": list(safety.offending_rooms)}
    if outlines:
        # EVERY OUTLINE TRIED (feature 006), each with the engine block a single run used to carry.
        diagnostics["outlines"] = [{
            "width_m": o.outline.width_m, "depth_m": o.outline.depth_m,
            "origin": o.outline.origin, "planned": bool(o.plans),
            "latency_ms": round(o.latency_ms, 1),
            "engine": _diagnostics(o.result).get("engine"),
            "notes": list(o.result.notes or ()),
        } for o in outlines]
    if spec is not None:
        program = spec.program
        diagnostics["programme"] = {
            "bedrooms": program.bedrooms, "wet_rooms": program.wet_rooms,
            "safe_room": program.safe_room, "open_plan_living": program.open_plan_living,
            "parking_spaces": program.parking_spaces,
            "target_built_area_m2": program.target_built_area_m2,
            "corridor_m": getattr(program.corridor, "width_m", None) if program.corridor else None,
        }
    return diagnostics


@dataclass(frozen=True)
class DemoResult:
    design: DemoDesign
    #: Other plans the engine could equally have chosen, each already past every gate `design`
    #: passed. Empty when this brief and this land produce only one distinct plan.
    alternatives: tuple[DemoDesign, ...] = ()
    #: Feature 006: every outline the engine planned for this request and what it cost.
    search: SearchSummary | None = None


def _set_aside(project: Project, spec, preference_dropped: bool) -> list[str]:
    """Everything the plan did NOT honour, in the person's own terms.

    Only PREFERENCES can reach a plan: `check_supported` refuses outright on a hard requirement or
    an unclear one, so anything still here was explicitly optional — including a preferred corridor
    width the programme could not fit.
    """
    notes = [r.text for r in project.unsupported_requests if r.severity == "preference"]
    if preference_dropped and spec.program.corridor is not None:
        notes.append(f"מסדרון ברוחב {spec.program.corridor.width_m:.2f} מ׳ (העדפה)")
    return notes


def _buildable_from(spec, project: Project) -> BuildableRegion:
    """The land the planner may use: the chosen footprint, PLACED INSIDE the real buildable area.

    Both containments are real — footprint inside buildable, buildable inside the parcel — so the
    region handed to the engine is a subset of land the person actually owns. It used to be the
    footprint rectangle at an origin derived from a plot that had itself been computed from that
    same footprint, which made the containment vacuous.

    Centred across the plot and flush to the street-side band — the front setback, or the
    parking bays' depth when that is deeper (`site.front_band_m`). The bays are drawn in that
    band by the site stage, so a house placed any nearer the street would be drawn over them;
    that the band still leaves room for this footprint is `scope.check_supported`'s job, decided
    before anything is planned.
    """
    site = site_geometry.derive(project)
    footprint = project.selected_footprint
    if site is None or footprint is None:  # both guaranteed by scope.check_supported
        raise ValueError("_buildable_from requires an authoritative site and a footprint")

    origin_x, origin_y = site.buildable_origin_m()
    origin_x += max(0.0, (site.buildable_width_m - footprint.width_m) / 2)
    origin_y = max(origin_y, front_band_m(spec))
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(origin_x, origin_y,
                                            footprint.width_m, footprint.depth_m))),
        Provenance(Source.USER, Authority.AUTHORITATIVE,
                   ref="selected footprint inside the supplied parcel"),
    )


def generate_demo_design(project: Project,
                         on_stage: Callable[[str], None] | None = None) -> DemoResult:
    rejection: ScopeRejection | None = check_supported(project)
    if rejection is not None:
        raise DemoGenerationError(rejection.code.value, rejection.message, rejection.detail)

    spec = spec_for(project)
    corridor = spec.program.corridor
    outlines = _outlines_for(project)

    target_m2 = spec.program.target_built_area_m2
    results = _plan_outlines_until_one_plans(spec, project, outlines, target_m2, on_stage)

    # A PREFERRED width may be dropped when the programme cannot fit it; a required one may not.
    # The retry happens once, without the corridor, and the plan says plainly that the preference
    # was not met — the person is never quietly given a narrower corridor than they asked for.
    preference_dropped = False
    if not _any_plan(results) and corridor is not None and not corridor.is_binding:
        without = replace(spec, program=replace(spec.program, corridor=None))
        retry = _plan_outlines_until_one_plans(without, project, outlines, target_m2, on_stage)
        if _any_plan(retry):
            results, preference_dropped = retry, True

    # The refusal diagnosis is read off the FIRST outline tried — the person's own when they gave
    # one — so a refusal talks about the rectangle they can see.
    head = results[0].result

    # Only claim the corridor is the problem when it plausibly is. A target area the programme
    # cannot fill is its own, already-diagnosed outcome; blaming the corridor for it would send the
    # person to shrink a corridor that was never the obstacle.
    reasons_so_far = "; ".join(head.metrics.rejection_reasons or head.notes)
    misattributed = (RejectionReason.TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY.value
                     in reasons_so_far)

    if (not _any_plan(results) and corridor is not None
            and corridor.is_binding and not misattributed):
        raise DemoGenerationError(
            "CORRIDOR_WIDTH_NOT_FEASIBLE",
            f"מסדרון ברוחב {corridor.width_m:.2f} מ׳ לא נכנס יחד עם החדרים שביקשת במתאר שנבחר. "
            f"אפשר להגדיל את שטח הבנייה, להוריד חדר, או לצמצם את רוחב המסדרון — "
            f"לא נצר תוכנית עם מסדרון צר ממה שביקשת.",
            reasons_so_far or head.outcome.value)

    selection = _select_plans(results, spec.program.target_built_area_m2)
    if selection is None:
        return _finish(project, spec, head, preference_dropped, outlines=results)
    return _result_from(project, spec, selection, results, preference_dropped)


# ------------------------------------------------------------------ 006: the engine's outlines
#
# The building outline used to be an input the person had to choose on its own screen. Measured
# over the production refusal log (424 briefs): their choice planned in 30 % of briefs, while each
# of the engine's own four preferred shapes planned in 35–45 %; 133 of the 297 refused briefs plan
# at one of those shapes at a median 97 % of the requested area. So the search this service used to
# run only AFTER a refusal — `_outline_that_plans`, now retired — runs before planning instead, and
# the person's outline becomes optional. What happens INSIDE one outline is unchanged: every outline
# goes through the same `run_general` call the person's outline always went through.

OutlineOrigin = Literal["ENGINE", "PERSON"]


@dataclass(frozen=True)
class Outline:
    """One rectangle the brief is planned into, and who chose it."""

    width_m: float
    depth_m: float
    origin: OutlineOrigin
    #: 0 for the person's outline; the engine's in `site_geometry.PREFERRED_RATIOS` order after it.
    order: int

    @property
    def area_m2(self) -> float:
        return round(self.width_m * self.depth_m, 4)

    def as_out(self) -> OutlineOut:
        return OutlineOut(width_m=self.width_m, depth_m=self.depth_m, area_m2=self.area_m2,
                          origin=self.origin)


@dataclass(frozen=True)
class OutlineResult:
    """What one outline produced: the pipeline's own result, and its validated plans, if any.

    `plans` is non-empty ONLY when the run is `ok` — outcome SOLVED, every validation check passed,
    every room inside the buildable region. A plan that fails a check never enters the pool the
    screen is chosen from, which is the same bar `_alternative_plans` holds every alternative to.
    """

    outline: Outline
    result: GeneralSliceResult
    plans: tuple[RealizedPlan, ...]
    latency_ms: float

    def as_tried(self) -> OutlineTried:
        return OutlineTried(width_m=self.outline.width_m, depth_m=self.outline.depth_m,
                            origin=self.outline.origin, planned=bool(self.plans),
                            plans_found=len(self.plans), latency_ms=round(self.latency_ms, 1))


#: How many plans the screen shows at most — the primary and two others (spec 006 FR-004). Fewer
#: is a real answer; the set is never padded.
_SHOWN_LIMIT = 3


@dataclass(frozen=True)
class PlanSelection:
    """The plans the screen shows, each with the outline it came from."""

    primary: tuple[OutlineResult, RealizedPlan]
    alternatives: tuple[tuple[OutlineResult, RealizedPlan], ...]


def _outlines_for(project: Project) -> list[Outline]:
    """The person's outline first, when they gave one; then the engine's preferred shapes for the
    requested area, de-duplicated. Deterministic: the same project always yields the same list."""
    site = site_geometry.derive(project)
    if site is None:  # guaranteed by scope.check_supported
        raise ValueError("_outlines_for requires authoritative site dimensions")
    out: list[Outline] = []
    seen: set[tuple[float, float]] = set()

    def add(width_m: float, depth_m: float, origin: OutlineOrigin) -> None:
        key = (round(width_m, 2), round(depth_m, 2))
        if key in seen:
            return
        seen.add(key)
        out.append(Outline(width_m, depth_m, origin, len(out)))

    chosen = project.selected_footprint
    if chosen is not None:
        add(chosen.width_m, chosen.depth_m, "PERSON")
    for width_m, depth_m in site_geometry.feasible_options(site, project.built_area_m2):
        add(width_m, depth_m, "ENGINE")
    return out


def _with_outline(project: Project, outline: Outline) -> Project:
    """The same project, planned into `outline` — exactly how the retired refusal-path search built
    its candidates, so an engine outline reaches the pipeline the way a chosen one always did."""
    footprint = SelectedFootprint(
        source="CUSTOM", shape_type="RECTANGLE", target_area_m2=project.built_area_m2,
        width_m=outline.width_m, depth_m=outline.depth_m, area_m2=outline.area_m2)
    return project.model_copy(update={"selected_footprint": footprint})


def _chosen_as_realized(result: GeneralSliceResult) -> RealizedPlan:
    """The pipeline's chosen plan in the same shape as its alternatives, so one pool holds both."""
    return RealizedPlan(
        index=result.metrics.first_valid_candidate_index or 0,
        concept=result.concept, design=result.design, validation=result.validation,
        safety=result.safety, relationships=result.relationships)


def _plan_outlines(spec, project: Project, outlines: list[Outline], on_stage=None, *,
                   max_alternatives: int = ALTERNATIVE_PLAN_LIMIT) -> list[OutlineResult]:
    """Plan each outline, in order, one after the other — never concurrently (research R4)."""
    out: list[OutlineResult] = []
    for outline in outlines:
        started = time.perf_counter()
        result = _plan(spec, _with_outline(project, outline), on_stage,
                       max_alternatives=max_alternatives)
        latency_ms = (time.perf_counter() - started) * 1000
        plans = (_chosen_as_realized(result), *result.alternatives) if result.ok else ()
        out.append(OutlineResult(outline, result, tuple(plans), latency_ms))
    return out


def _plan_outlines_until_one_plans(spec, project: Project, outlines: list[Outline],
                                   target_m2: float | None,
                                   on_stage=None) -> list[OutlineResult]:
    """The person's outline is authoritative: when they gave one and it plans, the engine's
    outlines are not run at all — the request costs exactly what it cost before this feature.

    Otherwise the engine's outlines are SURVEYED on the fast path (no alternatives: each run stops
    at the first plan that validates), the primary outline is chosen among their primaries by the
    area-only rule, and ONLY that outline is planned again with alternatives. Measured before this
    split, running every outline with alternatives cost the person whose brief already planned
    ~6 s against ~1.5 s; the survey costs about a third of a full run per outline.
    """
    person = [o for o in outlines if o.origin == "PERSON"]
    engine = [o for o in outlines if o.origin == "ENGINE"]
    results = _plan_outlines(spec, project, person, on_stage)
    if _any_plan(results):
        return results

    surveyed = _plan_outlines(spec, project, engine, on_stage, max_alternatives=0)
    chosen = _nearest_primary(surveyed, target_m2)
    if chosen is None:
        return results + surveyed
    chosen_result, chosen_plan = chosen
    full = _plan_outlines(spec, project, [chosen_result.outline], on_stage)[0]
    # The pipeline is deterministic: the re-run's primary IS the surveyed primary. Alternatives
    # were gathered on top of it, never instead of it.
    assert full.plans and full.plans[0].layout_signature == chosen_plan.layout_signature, (
        "re-running the chosen outline changed its primary")
    full = replace(full, latency_ms=full.latency_ms + chosen_result.latency_ms)
    return results + [full if r.outline == chosen_result.outline else r for r in surveyed]


def _nearest_primary(results: list[OutlineResult],
                     target_m2: float | None) -> tuple[OutlineResult, RealizedPlan] | None:
    """Among the outlines that planned, the one whose OWN primary is nearest the requested area;
    ties fall to the earlier outline. Only primaries compete — an outline's alternatives never
    displace its primary, exactly as within one outline today."""
    target = target_m2 or 0.0
    primaries = [(orr, orr.plans[0]) for orr in results if orr.plans]
    if not primaries:
        return None
    return min(primaries, key=lambda item: (round(abs(item[1].concept.used_area_m2 - target), 4),
                                            item[0].outline.order))


def _any_plan(results: list[OutlineResult]) -> bool:
    return any(r.plans for r in results)


def _select_plans(results: list[OutlineResult],
                  requested_m2: float | None) -> PlanSelection | None:
    """Which plans the screen shows, chosen across every outline that produced any.

    THE PRIMARY is the outline primary whose gross area is nearest the requested area — today's
    rule (the generator sorts candidates by |area − target| and the pipeline takes the first that
    validates), applied across outlines instead of within one; ties fall to the earlier outline.
    When the person gave an outline and it planned, its own primary is the primary, whatever the
    engine's outlines produced: their choice is authoritative.

    THE ALTERNATIVES are chosen from everything else that validated — the primary outline's own
    alternatives and the other outlines' primaries — nearest the requested area first, but taking a
    plan of a family not yet shown before any repeat, and a repeat only from an outline not yet
    shown. Measured before this rule, 142 of the 178 alternatives the demo showed were the primary's
    own family re-proportioned. Family (`RealizedPlan.family_signature`) is used HERE ONLY, as a
    display de-duplication key; it is not an input to the primary and must not become one.
    """
    target = requested_m2 or 0.0
    person = next((orr for orr in results if orr.outline.origin == "PERSON" and orr.plans), None)
    primary = (person, person.plans[0]) if person is not None else _nearest_primary(results, target)
    if primary is None:
        return None
    primary_orr, primary_plan = primary

    pool = sorted(
        ((orr, plan) for orr in results for plan in orr.plans
         if not (orr is primary_orr and plan is primary_plan)),
        key=lambda item: (round(abs(item[1].concept.used_area_m2 - target), 4),
                          item[0].outline.order, item[1].index))
    assert primary_plan.ok and all(plan.ok for _, plan in pool), (
        "an unvalidated plan reached the selection pool")

    shown: list[tuple[OutlineResult, RealizedPlan]] = [primary]
    drawings = {(primary_orr.outline.order, primary_plan.layout_signature)}

    def take(item: tuple[OutlineResult, RealizedPlan]) -> None:
        shown.append(item)
        drawings.add((item[0].outline.order, item[1].layout_signature))

    def unseen_drawing(item: tuple[OutlineResult, RealizedPlan]) -> bool:
        return (item[0].outline.order, item[1].layout_signature) not in drawings

    # Pass 1: families not yet shown. Pass 2: outlines not yet shown (a different house size or
    # shape of a family already on screen). Never the same outline re-proportioned.
    for item in pool:
        if len(shown) >= _SHOWN_LIMIT:
            break
        families = {plan.family_signature for _, plan in shown}
        if unseen_drawing(item) and item[1].family_signature not in families:
            take(item)
    for item in pool:
        if len(shown) >= _SHOWN_LIMIT:
            break
        outlines_shown = {orr.outline.order for orr, _ in shown}
        if unseen_drawing(item) and item[0].outline.order not in outlines_shown:
            take(item)
    return PlanSelection(primary, tuple(shown[1:]))


def _result_from(project: Project, spec, selection: PlanSelection,
                 results: list[OutlineResult], preference_dropped: bool) -> DemoResult:
    """A plan set from plans that have ALREADY passed every gate — the pool is built from `ok`
    results only, so nothing here re-litigates validation, and nothing here can lower it."""
    unsupported = _set_aside(project, spec, preference_dropped)
    person = next((orr for orr in results if orr.outline.origin == "PERSON"), None)
    if person is not None and not person.plans:
        unsupported.append(
            f"המתאר שהזנת ({person.outline.width_m:.2f}×{person.outline.depth_m:.2f} מ׳) לא אפשר "
            f"לסדר את החדרים; מוצג מתאר אחר באותו שטח")

    def design_of(item: tuple[OutlineResult, RealizedPlan]) -> DemoDesign:
        orr, plan = item
        return to_demo_design(plan.design, plan.validation, unsupported=unsupported,
                              corridor=spec.program.corridor, relationships=plan.relationships,
                              outline=orr.outline.as_out(), family=plan.family_signature)

    return DemoResult(
        design=design_of(selection.primary),
        # Each alternative reports its OWN validation statements and its OWN relationship
        # outcomes, because the panel beside the drawing must describe the drawing on screen.
        alternatives=tuple(design_of(item) for item in selection.alternatives),
        search=SearchSummary(outlines=[r.as_tried() for r in results],
                             total_latency_ms=round(sum(r.latency_ms for r in results), 1)),
    )


def realized_corridor_width_m_of(design) -> float:
    """The narrowest realized circulation zone, in metres — measured, not assumed."""
    widths = [min(r.net_w_m, r.net_h_m) for r in design.rooms
              if {"HALL", "CIRCULATION"} & {str(getattr(role, "value", role)) for role in r.roles}]
    return round(min(widths), 2) if widths else 0.0


def _plan(spec, project: Project, on_stage=None, *,
          max_alternatives: int = ALTERNATIVE_PLAN_LIMIT):
    # The demo screen SHOWS the other plans, so the demo is what asks for them to be computed.
    # Every other caller of the pipeline still gets one plan at one plan's cost. `max_alternatives`
    # is `run_general`'s own argument: 0 is the fast path (stop at the first plan that validates),
    # which is how the engine's outlines are surveyed before one is chosen (feature 006 phase 4).
    return run_general(
        _buildable_from(spec, project),
        plot_size_m=(spec.plot.width_m, spec.plot.depth_m),
        program=spec.program,
        max_alternatives=max_alternatives,
        on_stage=on_stage,
    )


def _finish(project: Project, spec, result, preference_dropped: bool,
            outlines: list[OutlineResult] | None = None) -> DemoResult:
    """The refusal path: every outline was planned and none produced a validated plan. `result`
    is the first outline's run — the person's own when they gave one — and `outlines` is all of
    them, for the diagnostics."""
    # A hard relationship that no candidate could realize is its own outcome: the geometry could
    # not be arranged that way with this programme, which is NOT a claim that no such house exists.
    if (result.outcome is not AdapterOutcome.SOLVED
            or (result.validation is not None and not result.validation.ok
                and any(c.check_id == "C15" for c in result.validation.failures()))):
        hard = [r for r in spec.program.relationships
                if r.strength is RelationStrength.HARD_REQUIREMENT]
        # `notes` carries the per-candidate rejections, which is where a relationship failure is
        # recorded when NO candidate survives; `rejection_reasons` carries the generator's own.
        # Both have to be read, or a relationship that nothing could realize surfaces as a generic
        # "could not plan" and the person is never told which requirement was the obstacle.
        reasons = "; ".join(tuple(result.metrics.rejection_reasons) + tuple(result.notes))
        broke_relationship = (
            "breaks a required relationship" in reasons
            or (result.validation is not None
                and any(c.check_id == "C15" for c in result.validation.failures())))
        if hard and broke_relationship:
            wanted = "; ".join(describe(r) for r in hard)
            raise DemoGenerationError(
                "ROOM_RELATIONSHIP_NOT_FEASIBLE",
                f"לא הצלחנו לסדר את החדרים כך ש{wanted}, יחד עם שאר הדרישות והמתאר שנבחר. "
                f"אפשר להגדיל את שטח הבנייה, לוותר על אחת הדרישות, או לנסח אותה כהעדפה — "
                f"לא נציג תוכנית שלא מקיימת מה שביקשת.",
                reasons or "; ".join(f"{c.check_id}: {c.detail}"
                                     for c in (result.validation.failures()
                                               if result.validation else [])))

    if result.outcome is not AdapterOutcome.SOLVED or result.design is None:
        reasons = "; ".join(result.metrics.rejection_reasons or result.notes) or result.outcome.value

        # A target the current room programme cannot responsibly fill is its OWN outcome, kept
        # separate from "this could not be planned". Nothing here is physically impossible: the
        # rooms this brief asks for simply cannot consume that much area without being inflated
        # past their own maximums. The user's requested area is left exactly as they set it.
        #
        # Asked of the NUMBERS, not of a reason code. This used to key on
        # `RejectionReason.TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` appearing in `reasons`,
        # which the generator stopped emitting when the FLEX zone was introduced to absorb exactly
        # this surplus — so the branch became unreachable and 164 refusals whose whole diagnosis is
        # "you asked for more than these rooms can fill" got the generic message instead. The
        # comparison below is the same one `generate_concepts` itself uses to decide to inject FLEX,
        # so the product message and the engine agree on what "over capacity" means.
        target_m2 = spec.program.target_built_area_m2
        rooms = build_room_program(spec)
        capacity = program_capacity_gross_m2(rooms)
        if target_m2 is not None and target_m2 > capacity:
            raise DemoGenerationError(
                "TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY",
                f"התוכנית שביקשת יכולה למלא עד כ-{capacity:.0f} מ\"ר בצורה סבירה, "
                f"והיעד שהוזן הוא {spec.program.target_built_area_m2:.0f} מ\"ר. "
                f"אפשר להוסיף חדרים או להקטין את שטח הבנייה — הדרישות שלך נשמרו כפי שהזנת.",
                reasons, diagnostics=_diagnostics(result, spec, outlines))

        # No "try X×Y instead": every feasible outline of this area has already been planned
        # (feature 006), so a shape that worked would be a plan on the screen, not a hint.
        raise DemoGenerationError(
            "PLAN_NOT_REALIZABLE",
            "לא הצלחנו לייצר תוכנית תקינה עבור הדרישות שביקשת, באף אחת מצורות הבניין "
            "האפשריות במגרש הזה.",
            reasons,
            diagnostics=_diagnostics(result, spec, outlines),
        )

    # A plan that fails ONLY on the corridor width is a corridor problem, and saying so beats a
    # generic "did not pass planning checks" — the person can act on the first and not the second.
    corridor = spec.program.corridor
    if (corridor is not None and result.validation is not None and not result.validation.ok
            and [c.check_id for c in result.validation.failures()] == ["C14"]):
        realized = realized_corridor_width_m_of(result.design)
        raise DemoGenerationError(
            "CORRIDOR_WIDTH_NOT_FEASIBLE",
            f"ביקשת מסדרון ברוחב {corridor.width_m:.2f} מ׳, והתוכנית שנוצרה מגיעה ל-"
            f"{realized:.2f} מ׳ בלבד. אפשר להגדיל את שטח הבנייה, להוריד חדר, או לצמצם את רוחב "
            f"המסדרון — לא נציג תוכנית שלא עומדת בדרישה שביקשת.",
            "; ".join(f"{c.check_id}: {c.detail}" for c in result.validation.failures()))

    # HARD GATE. A plan is never returned as successful while a validation check is failing —
    # including C13, the realized-connectivity invariant.
    if result.validation is None or not result.validation.ok:
        failures = "; ".join(f"{c.check_id}: {c.detail}"
                             for c in (result.validation.failures() if result.validation else []))
        # A brief over its programme's capacity that also fails validation is refused for the
        # capacity, which the person can act on, not for the check — the same diagnosis the
        # not-realizable path gives. Without this, a candidate that solved and then failed C8
        # replaced the capacity message with a raw check id in 8 of 420 logged scenarios.
        target_m2 = spec.program.target_built_area_m2
        capacity = program_capacity_gross_m2(build_room_program(spec))
        if target_m2 is not None and target_m2 > capacity:
            raise DemoGenerationError(
                "TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY",
                f"התוכנית שביקשת יכולה למלא עד כ-{capacity:.0f} מ\"ר בצורה סבירה, "
                f"והיעד שהוזן הוא {target_m2:.0f} מ\"ר. "
                f"אפשר להוסיף חדרים או להקטין את שטח הבנייה — הדרישות שלך נשמרו כפי שהזנת.",
                failures, diagnostics=_diagnostics(result, spec, outlines))
        raise DemoGenerationError(
            "PLAN_FAILED_VALIDATION",
            "התוכנית שנוצרה לא עברה את בדיקות התכנון ולכן לא הוצגה.",
            failures, diagnostics=_diagnostics(result, spec, outlines))

    if result.safety is not None and not result.safety.ok:
        raise DemoGenerationError(
            "PLAN_OUTSIDE_BUILDABLE",
            "התוכנית שנוצרה חרגה משטח הבנייה המותר ולכן לא הוצגה.",
            ", ".join(result.safety.offending_rooms),
            diagnostics=_diagnostics(result, spec, outlines))

    # Unreachable: a result that passed every gate above is `ok`, and an `ok` result puts its plans
    # in the selection pool, which returns through `_result_from` instead. Kept as a hard stop so
    # a future edit cannot turn this path into a second, drifting way of producing a plan.
    raise AssertionError("_finish reached with a validated result; selection should have handled it")
