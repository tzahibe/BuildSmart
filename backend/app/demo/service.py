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
      -> contract.to_demo_building        the primary as a one-level Building, V-checks run (Phase 0)

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
from app.geometry_domain.walls import BoundaryContext
from app.vertical_slice import doors as doors_stage
from app.vertical_slice import l_massing_guard
from app.vertical_slice.hub_guard import proportions_of
from app.vertical_slice.spec import HouseConcept, LaundryDemand, PublicOpenSide, RelationStrength
from app.vertical_slice.general_pipeline import (
    ALTERNATIVE_PLAN_LIMIT,
    GeneralSliceResult,
    RealizedPlan,
    run_general,
)
from app.vertical_slice.safe_adapter import AdapterOutcome
from app.vertical_slice.site import PARKING_BAY_DEPTH_M, front_band_m
from app.vertical_slice.wet_privacy import candidate_privacy_key

from app.vertical_slice.building import Building

from .contract import (
    DemoBuilding,
    DemoDesign,
    DemoPlanSet,
    OutlineOut,
    OutlineTried,
    SearchSummary,
    to_demo_building,
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
    "ENTRANCE_NO_ARRIVAL_ROOM",
    "ENTRANCE_DEAD_END",
    "LAUNDRY_UNPLACEABLE",
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
    #: Multi-level Phase 0: `design` as the ground level of a one-level building, with the
    #: building-level checks (V2, V7) already run. `levels[0].design` is `design`.
    building: DemoBuilding | None = None


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


def _buildable_from(spec, project: Project, outline: "Outline | None" = None) -> BuildableRegion:
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
    if outline is not None and outline.massing is not None:
        # An L massing: the same placement rule applied to its bounding box, and the region is the
        # L itself — one ring — so the adapter finds the primary and the arm as two adjacent safe
        # rectangles, exactly as it does on an L-shaped site.
        ring = Ring.from_points(outline.massing.ring_points(origin_x, origin_y))
        return BuildableRegion.known(
            MultiRegion.of(Region(ring)),
            Provenance(Source.INFERRED, Authority.AUTHORITATIVE,
                       ref="engine L massing inside the supplied parcel"))
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

    selection = _select_plans(results, spec.program.target_built_area_m2, spec.concept)
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
    """One outline the brief is planned into, and who chose it.

    A rectangle — `width_m x depth_m` — or, when `massing` is set, an L of two wings whose bounding
    box those are (`site_geometry.LMassing`). An L is always the ENGINE's: it is one more massing
    the survey tries beside its rectangles, never something the person picked, and only a plan of
    two wings may come out of it (`_plan_outlines`).
    """

    width_m: float
    depth_m: float
    origin: OutlineOrigin
    #: 0 for the person's outline; the engine's in `site_geometry.PREFERRED_RATIOS` order after it,
    #: then the L massings.
    order: int
    massing: site_geometry.LMassing | None = None

    @property
    def area_m2(self) -> float:
        if self.massing is not None:
            return round(self.massing.area_m2, 4)
        return round(self.width_m * self.depth_m, 4)

    @property
    def shape(self) -> str:
        return "L" if self.massing is not None else "RECTANGLE"

    def as_out(self) -> OutlineOut:
        wings = ([] if self.massing is None else
                 [(self.massing.primary_w_m, self.massing.primary_d_m),
                  (self.massing.arm_w_m, self.massing.arm_d_m)])
        return OutlineOut(width_m=self.width_m, depth_m=self.depth_m, area_m2=self.area_m2,
                          origin=self.origin, shape=self.shape, wing_dims_m=wings)


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
    #: This engine outline was surveyed because the person's own outline planned but delivered
    #: under `OUTLINE_SHORTFALL_RATIO` of the request, and it delivers materially more — it is
    #: offered as the FIRST alternative, with a note on the primary (`_better_engine_outline`).
    offered_for_area: bool = False

    def as_tried(self) -> OutlineTried:
        return OutlineTried(width_m=self.outline.width_m, depth_m=self.outline.depth_m,
                            origin=self.outline.origin, planned=bool(self.plans),
                            plans_found=len(self.plans), latency_ms=round(self.latency_ms, 1),
                            shape=self.outline.shape)


#: How many plans the screen shows at most — the primary and two others (spec 006 FR-004). Fewer
#: is a real answer; the set is never padded. The POOL the screen chooses from is larger
#: (`ALTERNATIVE_PLAN_LIMIT` alternatives per outline, plus one when a second massing — an L — is
#: among them); this is how many of it are shown.
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
    # The engine's outlines are measured against the depth BEHIND the parking band — the person's
    # outline was checked against it in `scope.check_supported`, and an engine outline gets no
    # second look before it is planned.
    behind_band = site_geometry.behind_parking_band(
        site, _tagged_value(project.parking_spaces, 0), PARKING_BAY_DEPTH_M)
    for width_m, depth_m in site_geometry.feasible_options(behind_band, project.built_area_m2):
        add(width_m, depth_m, "ENGINE")
    # THE L MASSINGS, after the rectangles: two wings carved from the same buildable rectangle at
    # the same area (arm at the rear — public band on the street; arm at the front — band to the
    # garden). Surveyed like any engine outline; shown only when a two-wing plan validates, and
    # then beside the rectangles' plans, never instead of them (`_select_plans`, massing pass).
    for massing in site_geometry.l_massings(behind_band, project.built_area_m2):
        out.append(Outline(massing.bbox_w_m, massing.bbox_d_m, "ENGINE", len(out), massing))
    return out


def _tagged_value(tagged, default):
    return default if tagged is None or tagged.value is None else tagged.value


def _with_outline(project: Project, outline: Outline) -> Project:
    """The same project, planned into `outline` — exactly how the retired refusal-path search built
    its candidates, so an engine outline reaches the pipeline the way a chosen one always did."""
    # For an L massing this record carries the BOUNDING BOX (the placement `_buildable_from`
    # needs); the L's own area lives on the outline, and the record's validator wants w x d.
    footprint = SelectedFootprint(
        source="CUSTOM", shape_type="RECTANGLE", target_area_m2=project.built_area_m2,
        width_m=outline.width_m, depth_m=outline.depth_m,
        area_m2=round(outline.width_m * outline.depth_m, 4))
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
                       max_alternatives=max_alternatives, outline=outline)
        latency_ms = (time.perf_counter() - started) * 1000
        plans = (_chosen_as_realized(result), *result.alternatives) if result.ok else ()
        if outline.massing is not None:
            # An L massing exists to offer a TWO-WING house. The one-wing plans the pipeline also
            # makes on its primary rectangle are rectangles the rectangle outlines already cover —
            # offering them again would be the same house twice under two outlines.
            plans = tuple(plan for plan in plans if plan.massing_signature == "2W")
        out.append(OutlineResult(outline, result, tuple(plans), latency_ms))
    return out


#: Delivery policy: a person's outline that plans is the primary, always — but when it delivers
#: less than this share of the EFFECTIVE target, the engine's outlines are surveyed as well and the
#: best of them is offered beside it. Measured on the failure log (431 briefs, 2026-09-14): the 16
#: within-capacity plans delivered under 80 % were ALL a person's extreme outline (10 x 20, 20 x 10,
#: 12 x 18, 18 x 12) planning at 56-80 %, while the engine's own outline for the same brief and
#: plot delivered 87-100 % in every one of them — and was never tried, because the person's outline
#: had planned. The person's choice stays authoritative; the alternative and the note are new.
#:
#: The effective target is `min(request, programme capacity)` (`effective_target_m2`): a request
#: the rooms cannot fill is measured against what they CAN fill, so a brief already carrying the
#: capacity note is not surveyed for an alternative that would fall equally short. Measured with
#: the request as the bar: 88 briefs triggered, 38 of them were surveyed for nothing (over-capacity
#: requests whose engine outlines deliver about the same), and 12 offers were 40 % -> 45 % of a
#: request neither outline could approach.
OUTLINE_SHORTFALL_RATIO = 0.80
#: An engine outline is offered only when it delivers at least this much MORE than the person's
#: outline did — an alternative that is a few m² larger is noise, not a way forward — AND itself
#: reaches `OUTLINE_SHORTFALL_RATIO` of the effective target: an offer must be a way out of the
#: shortfall, not a smaller shortfall.
OUTLINE_ALTERNATIVE_MIN_GAIN = 0.10


def effective_target_m2(spec) -> float | None:
    """What a delivered plan is measured against: the request, or the programme's capacity when
    the request exceeds it (the same figure `capacity_note` reports). None without a request."""
    target_m2 = spec.program.target_built_area_m2
    if target_m2 is None:
        return None
    return min(target_m2, program_capacity_gross_m2(build_room_program(spec)))


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
        offer = _better_engine_outline(spec, project, engine, results[0], target_m2, on_stage)
        return results + ([offer] if offer is not None else [])

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


def _better_engine_outline(spec, project: Project, engine: list[Outline], person: OutlineResult,
                           target_m2: float | None, on_stage=None) -> OutlineResult | None:
    """The engine outline to offer beside a person's outline that planned SHORT, or None.

    Surveys the engine's outlines (fast path, exactly as the refusal path does) only when the
    person's primary delivers under `OUTLINE_SHORTFALL_RATIO` of the EFFECTIVE target
    (`effective_target_m2`), and returns the outline whose primary is nearest the request if it
    delivers at least `OUTLINE_ALTERNATIVE_MIN_GAIN` more than the person's AND reaches that same
    share of the effective target itself. The survey's cost is carried on the offered result so
    the search summary stays honest. Nothing here touches which plan is the primary: that is the
    person's, as `_select_plans` has always held.
    """
    effective = effective_target_m2(spec)
    if effective is None or not person.plans or not engine:
        return None
    delivered = person.plans[0].design.gross_area_m2
    if delivered >= OUTLINE_SHORTFALL_RATIO * effective:
        return None
    surveyed = _plan_outlines(spec, project, engine, on_stage, max_alternatives=0)
    chosen = _nearest_primary(surveyed, target_m2)
    if chosen is None:
        return None
    chosen_result, chosen_plan = chosen
    offered_m2 = chosen_plan.design.gross_area_m2
    if (offered_m2 < delivered * (1.0 + OUTLINE_ALTERNATIVE_MIN_GAIN)
            or offered_m2 < OUTLINE_SHORTFALL_RATIO * effective):
        return None
    return replace(chosen_result, offered_for_area=True,
                   latency_ms=sum(r.latency_ms for r in surveyed))


def outline_note(person: OutlineResult, offered: OutlineResult) -> str:
    """The sentence on the primary when a better engine outline is offered beside it."""
    return (f"המתאר שבחרת ({person.outline.width_m:.2f}×{person.outline.depth_m:.2f}) מאפשר "
            f"{person.plans[0].design.gross_area_m2:.0f} מ\"ר; במתאר "
            f"{offered.outline.width_m:.2f}×{offered.outline.depth_m:.2f} באותו מגרש ניתן להגיע "
            f"ל-{offered.plans[0].design.gross_area_m2:.0f} מ\"ר.")


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


# ------------------------------------------------------------------ L orientation tiebreak
#
# The two L massings (arm at the rear: public band on the street; arm at the front: band to the
# garden) are the same dimensions by construction and the parti sizes them symmetrically, so the
# two-wing plans they produce tie EXACTLY on the pool's area criterion — measured on the five
# real briefs where both validated (161.5/161.5, 167.87/167.87, …). Left to the pool's own
# determinism (`outline.order`), the rear-arm L won every time and a "living to the garden" L was
# never shown. This tiebreak applies only to valid plans of one non-rectangle massing that are
# otherwise tied by the existing criteria: the person's `public_open_side` first, then the
# realized quality of the tied peers alone, then `outline.order` for determinism. It is not a
# ranking rule — an L gets nothing for being an L, and the primary is never touched.

_HABITABLE_ROLES = frozenset({"LIVING", "DINING", "KITCHEN", "BEDROOM", "MASTER_BEDROOM",
                              "SAFE_ROOM", "STUDY", "FAMILY_ROOM"})


@dataclass(frozen=True)
class LQuality:
    """The realized measures two tied L plans are compared on — all existing ones."""

    bedroom_class_aspect: float | None   # worst of the bedrooms' and the master's long/short; lower is better
    wet_share: float                     # wet rooms touching a wet room or the kitchen; higher is better
    two_sided: float                     # habitable rooms with two exterior walls; higher is better


def l_quality_of(design) -> LQuality:
    proportions = proportions_of(design)
    aspects = [a for a in (proportions.bedroom_max, proportions.master) if a is not None]
    habitable = [r for r in design.rooms if set(r.roles) & _HABITABLE_ROLES]
    two_sided = (sum(1 for r in habitable
                     if sum(1 for f in r.wall_facts.values()
                            if f.boundary_context is BoundaryContext.EXTERIOR) >= 2)
                 / len(habitable)) if habitable else 0.0
    return LQuality(max(aspects) if aspects else None, proportions.wet_share, two_sided)


def _l_quality_of_plan(plan) -> LQuality:
    return l_quality_of(plan.design)


def _privacy_key_of_plan(plan) -> tuple[float, float]:
    """`plan`'s wet-room privacy, as a sortable key — LOWER IS BETTER (Issue #37,
    `wet_privacy.candidate_privacy_key`). A thin, one-line seam over `.design`-reading logic, the
    same role `_l_quality_of_plan` already plays: a test can stand in for it without building
    full geometry."""
    return candidate_privacy_key(plan.design.wet_privacy)


def _l_massing_eligible(rect_plan, l_plan) -> str | None:
    """Whether `l_plan` (an engine-generated non-rectangle massing) earns a representation slot
    against `rect_plan` (the best rectangle plan available) — `None` if it may take the slot,
    else why not (`l_massing_guard.l_earns_representation_slot`). A thin, one-line seam over
    `.design`-reading logic, the same role `_l_quality_of_plan` already plays for the orientation
    tiebreak: a test can stand in for it without building full geometry."""
    return l_massing_guard.eligible_for_slot(rect_plan, l_plan)


def _pareto_better(a: LQuality, b: LQuality, eps: float = 1e-6) -> bool:
    """`a` better than `b` on at least one measure and worse on none."""
    def cmp(x, y, lower_is_better):
        if x is None or y is None:
            return 0
        if abs(x - y) <= eps:
            return 0
        return (1 if x < y else -1) if lower_is_better else (1 if x > y else -1)
    verdicts = (cmp(a.bedroom_class_aspect, b.bedroom_class_aspect, True),
                cmp(a.wet_share, b.wet_share, False),
                cmp(a.two_sided, b.two_sided, False))
    return any(v > 0 for v in verdicts) and not any(v < 0 for v in verdicts)


def _band_faces_garden(orr: OutlineResult) -> bool | None:
    """Where an L massing's public band faces: the arm at the FRONT leaves the band at the rear
    (garden); at the REAR, the band is on the street. None for a rectangle."""
    massing = orr.outline.massing
    if massing is None:
        return None
    return massing.arm_end == "front"


def _break_l_tie(peers: list, concept: HouseConcept):
    """Which of several otherwise-tied plans of one L massing is shown. `peers` in pool order.

    THE PRIVACY TIEBREAK (Issue #37, the last step before pool order): peers already tied on the
    person's garden/street preference AND on `LQuality`'s Pareto comparison are compared once
    more on their wet rooms' privacy — `_privacy_key_of_plan`, lower is better. Strictly a further
    refinement of an already-arbitrary tie, never a first-order ranking signal: it can only choose
    between peers `_pareto_better` already found neither better nor worse than the other."""
    if len(peers) == 1:
        return peers[0]
    if concept.public_open_side is not PublicOpenSide.ENGINE:
        want_garden = concept.public_open_side is PublicOpenSide.GARDEN
        matching = [item for item in peers if _band_faces_garden(item[0]) is want_garden]
        if matching:
            peers = matching
            if len(peers) == 1:
                return peers[0]
    qualities = [(item, _l_quality_of_plan(item[1])) for item in peers]
    undominated = [item for item, q in qualities
                   if not any(_pareto_better(other, q) for other_item, other in qualities
                              if other_item is not item)]
    if len(undominated) == 1:
        return undominated[0]
    if undominated:
        best_key = min(_privacy_key_of_plan(item[1]) for item in undominated)
        by_privacy = [item for item in undominated if _privacy_key_of_plan(item[1]) == best_key]
        if len(by_privacy) == 1:
            return by_privacy[0]
        undominated = by_privacy
    return (undominated or peers)[0]      # exact tie: pool order (outline.order, index) decides


def _select_plans(results: list[OutlineResult],
                  requested_m2: float | None,
                  concept: HouseConcept | None = None) -> PlanSelection | None:
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
    display de-duplication key; it is not an input to the primary and must not become one. The
    same holds for massing (`RealizedPlan.massing_signature`, one wing or two), which is taken
    before family: a plan of another massing is shown before a second organisation of the same.
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

    # An engine outline offered because the person's own planned short is the FIRST alternative
    # (`_better_engine_outline`); the passes below fill the remaining places as they always did.
    for orr in results:
        if orr.offered_for_area and orr.plans and orr is not primary_orr:
            take((orr, orr.plans[0]))

    # Pass 0: MASSINGS not yet shown — a two-wing (L) plan beside one-wing ones, or the reverse.
    # A massing is a coarser difference than an organisation family, and the one a person sees
    # first; a valid plan of another massing is shown before a second organisation of the same
    # one. Display de-duplication only, like family: never an input to the primary.
    #
    # ELIGIBILITY (2026-09-17, docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md): an
    # ENGINE-generated non-rectangle massing is no longer taken here unconditionally — it must
    # clear `l_massing_guard.l_earns_representation_slot` against the best "1W" plan anywhere in
    # the pool first (mirrors the same gate `general_pipeline._alternative_plans` already applies
    # before such a plan is even offered as an alternative; this is the belt to that suspenders,
    # protecting the screen even if a caller bypassed that layer). No rectangle in the pool at all
    # means nothing to gate against, so the candidate is taken as before.
    concept = concept or HouseConcept()
    for item in pool:
        if len(shown) >= _SHOWN_LIMIT:
            break
        massings = {plan.massing_signature for _, plan in shown}
        if unseen_drawing(item) and item[1].massing_signature not in massings:
            if item[1].massing_signature != "1W":
                # Several valid plans of this massing tied on the area criterion (the two L
                # orientations): the tiebreak decides which one is shown, not the pool order.
                area_key = round(abs(item[1].concept.used_area_m2 - target), 4)
                peers = [other for other in pool
                         if other[1].massing_signature == item[1].massing_signature
                         and round(abs(other[1].concept.used_area_m2 - target), 4) == area_key
                         and unseen_drawing(other)]
                item = _break_l_tie(peers, concept)
                rect_plans = ([p for _, p in shown if p.massing_signature == "1W"]
                             + [p for _, p in pool if p.massing_signature == "1W"])
                if rect_plans:
                    best_rect = max(rect_plans, key=lambda p: p.concept.used_area_m2)
                    if _l_massing_eligible(best_rect, item[1]) is not None:
                        continue
            take(item)
    # Pass 1: families not yet shown. Pass 2: outlines not yet shown (a different house size or
    # shape of a family already on screen). Never the same outline re-proportioned.
    for item in pool:
        if len(shown) >= _SHOWN_LIMIT:
            break
        families = {plan.family_signature for _, plan in shown}
        massings_shown = {plan.massing_signature for _, plan in shown}
        # One plan per non-rectangle massing in the shown set: the two L massings (arm at the rear,
        # arm at the front) are different families — the band is above or below the seam — and
        # both would take a slot here, leaving no room for a rectangle alternative. With three
        # slots the person sees the rectangle that won, one L, and another rectangle; the second
        # L orientation waits for a wider shown set, not for a rectangle's place.
        if (unseen_drawing(item) and item[1].family_signature not in families
                and (item[1].massing_signature == "1W"
                     or item[1].massing_signature not in massings_shown)):
            take(item)
    for item in pool:
        if len(shown) >= _SHOWN_LIMIT:
            break
        outlines_shown = {orr.outline.order for orr, _ in shown}
        massings_shown = {plan.massing_signature for _, plan in shown}
        # A repeat FAMILY from another outline is worth showing when the outlines differ in size
        # or shape — rectangles. The two L massings (arm at the rear, arm at the front) are the
        # same area by construction, and a second L of the family already on screen would take
        # the slot a rectangle alternative should have (measured: two 141.5 m² L's beside one
        # rectangle). A non-rectangle massing already shown is not repeated here.
        if (unseen_drawing(item) and item[0].outline.order not in outlines_shown
                and (item[1].massing_signature == "1W"
                     or item[1].massing_signature not in massings_shown)):
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
    offered = next((orr for orr in results if orr.offered_for_area and orr.plans), None)

    def design_of(item: tuple[OutlineResult, RealizedPlan]) -> DemoDesign:
        orr, plan = item
        notes = [n for n in (capacity_note(spec, plan.design.gross_area_m2),) if n]
        if item is selection.primary and offered is not None and person is not None:
            notes.append(outline_note(person, offered))
        return to_demo_design(plan.design, plan.validation, unsupported=unsupported,
                              corridor=spec.program.corridor, relationships=plan.relationships,
                              outline=orr.outline.as_out(), family=plan.family_signature,
                              notes=notes or None)

    primary = design_of(selection.primary)
    _, primary_plan = selection.primary
    # THE BUILDING is the primary as its own ground level — one level, no stair — carrying the
    # SAME `DemoDesign` object the screen draws, so the two cannot disagree. Building it here,
    # after every gate, means the V-checks run on a plan that already passed C1–C21.
    building = to_demo_building(
        Building.single_level(primary_plan.design, primary_plan.validation,
                              concept=primary_plan.concept, safety=primary_plan.safety),
        [primary])
    return DemoResult(
        design=primary,
        # Each alternative reports its OWN validation statements and its OWN relationship
        # outcomes, because the panel beside the drawing must describe the drawing on screen.
        alternatives=tuple(design_of(item) for item in selection.alternatives),
        search=SearchSummary(outlines=[r.as_tried() for r in results],
                             total_latency_ms=round(sum(r.latency_ms for r in results), 1)),
        building=building,
    )


def capacity_note(spec, delivered_m2: float) -> str | None:
    """The sentence a delivered plan carries when the request exceeds what its rooms can fill.

    Measured on the failure log (431 briefs, 2026-09-14): 117 of 261 delivered plans come in under
    80 % of the requested area, and 85+ of them are requests ABOVE the programme's own capacity —
    the plans fill a median 96 % of that capacity. The house is right; the silence was wrong: the
    person asked for 312 m², got 196, and nothing said why. This is the same diagnosis the refusal
    path gives (`TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`, same comparison as `generate_concepts`
    uses to inject FLEX), said on the plan instead of in place of it. No plan is refused or ranked by
    this; a floor on delivered area, if one is ever wanted, is a separate decision.
    """
    target_m2 = spec.program.target_built_area_m2
    if target_m2 is None:
        return None
    capacity = program_capacity_gross_m2(build_room_program(spec))
    if target_m2 <= capacity:
        return None
    return (f"התוכנית ממלאת {delivered_m2:.0f} מ\"ר מתוך כ-{capacity:.0f} מ\"ר שהחדרים שביקשת יכולים "
            f"למלא בצורה סבירה; היעד שהוזן הוא {target_m2:.0f} מ\"ר. "
            f"אפשר להוסיף חדרים או להקטין את שטח הבנייה — הדרישות שלך נשמרו כפי שהזנת.")


def realized_corridor_width_m_of(design) -> float:
    """The narrowest realized circulation zone, in metres — measured, not assumed."""
    widths = [min(r.net_w_m, r.net_h_m) for r in design.rooms
              if {"HALL", "CIRCULATION"} & {str(getattr(role, "value", role)) for role in r.roles}]
    return round(min(widths), 2) if widths else 0.0


def _street_fronting_roles(design) -> frozenset[str]:
    """Every role of a room whose rectangle touches the building's own street-facing wall (the
    footprint's y = min line) — used only to name what a refused entrance found on the street, so
    `ENTRANCE_NO_ARRIVAL_ROOM` can say "the street only reaches the kitchen" instead of nothing.

    DELIBERATELY SEPARATE from `doors.street_fronting_roles`, not a missed sharing opportunity:
    that one reads the ENGINE's pre-realization grid-unit types (`Fixture`/`Rect` in plot units)
    and exists to GATE a decision (`resolve_entrance`'s own frontage-for-a-door test, in
    `ENTRANCE_DOOR_WIDTH_M` units), so it must require enough frontage to actually place a door.
    This one reads the PRODUCT's post-realization metre-scale `DemoDesign` and only NAMES rooms
    for a message that is already gated elsewhere (`ENTRANCE_NO_ARRIVAL_ROOM` only fires when an
    entrance-related check has already failed) — a coarser "touches the street at all" test here
    can only make the message list an EXTRA room a real door could not fit on, never omit one that
    matters, and never changes whether the refusal fires. Unifying the two would mean threading
    grid-unit wing geometry through the product layer for a message-text nicety; not worth it.
    """
    street_y = design.footprint_m[1]
    return frozenset(str(getattr(role, "value", role)) for room in design.rooms
                     if abs(room.rect_m[1] - street_y) < 1e-6 for role in room.roles)


def _plan(spec, project: Project, on_stage=None, *,
          max_alternatives: int = ALTERNATIVE_PLAN_LIMIT, outline: "Outline | None" = None):
    # The demo screen SHOWS the other plans, so the demo is what asks for them to be computed.
    # Every other caller of the pipeline still gets one plan at one plan's cost. `max_alternatives`
    # is `run_general`'s own argument: 0 is the fast path (stop at the first plan that validates),
    # which is how the engine's outlines are surveyed before one is chosen (feature 006 phase 4).
    return run_general(
        _buildable_from(spec, project, outline),
        plot_size_m=(spec.plot.width_m, spec.plot.depth_m),
        program=spec.program,
        max_alternatives=max_alternatives,
        on_stage=on_stage,
    )


#: The three validation checks that can name the LAUNDRY room's own guarantee — exterior wall
#: (C19), window (C8), machine bay (C3, where a too-narrow short side shows up). Issue #21,
#: AC-3: `LAUNDRY_UNPLACEABLE` fires only when every outline this brief tried failed for one of
#: these reasons, naming the LAUNDRY zone specifically — never when an unrelated room or the
#: footprint itself was in the mix, so the refusal never blames laundry for someone else's defect.
_LAUNDRY_REQUIREMENT_CHECKS = ("C19", "C8", "C3")

_LAUNDRY_ZONE_ID = "LAUNDRY"


def _laundry_failed_requirement(check_id: str) -> str:
    if check_id == "C19":
        return "קיר חיצוני (החדר תוכנן ללא גישה לקיר חיצוני)"
    if check_id == "C8":
        return "חלון (הקיר החיצוני הפנוי קצר מדי לחלון שירות של 0.6 מ׳)"
    return "מרחב למכונת הכביסה (0.6 מ׳ מכונה + 0.6 מ׳ מייבש אופציונלי + 0.5 מ׳ מעבר = 1.7 מ׳)"


def _check_detail_zone_ids(detail: str) -> set[str]:
    """The zone id each `'; '`-separated clause of a C19/C8/C3 failure `detail` leads with.

    All three checks format `detail` as one clause per offending zone — `f"{zone_id} ..."` for
    C19/C3, the bare `zone_id` for C8 (`validation.py`) — joined by `'; '`. A single check can
    fail for SEVERAL zones at once in the same outline (e.g. a BEDROOM and LAUNDRY both losing
    their exterior wall to the same parti), and `detail` then names all of them in one string.
    Extracting the leading zone id from each clause is what lets the caller tell "this check named
    LAUNDRY and ONLY LAUNDRY" from "this check named LAUNDRY among others" — a plain substring
    check on the whole joined string cannot make that distinction and mis-fires on the second
    case, wrongly refusing LAUNDRY_UNPLACEABLE for a defect that also hits another room.
    """
    return {clause.strip().split(" ", 1)[0] for clause in detail.split("; ") if clause.strip()}


def _rejection_reason_names_only_laundry_shape(reason: str) -> bool:
    """Whether a pre-solve `rejection_reasons` entry (`f"{strategy}/{reason}: {detail}"`, built in
    `general_pipeline.run_general`) diagnoses the LAUNDRY room's own shape and nothing else.

    Only `ROOM_SHAPE_INFEASIBLE`'s `detail` (`concept_generator._shape_failure`) always names
    exactly the ONE room whose width leaves no depth satisfying its template — every other reason
    this generator emits (`COLUMN_DEPTH_EXCEEDED`, `ROW_WIDTH_EXCEEDED`, …) can list SEVERAL rooms
    in its own `detail` (e.g. "west column needs 15.97 m ... [LIVING ...; KITCHEN ...; LAUNDRY
    ...]"), and a substring check there would misattribute a whole-column capacity defect to
    LAUNDRY alone the same way a joined C19/C8/C3 `detail` can (see `_check_detail_zone_ids`).
    """
    head, _, detail = reason.partition(": ")
    _, _, reason_name = head.partition("/")
    if reason_name != RejectionReason.ROOM_SHAPE_INFEASIBLE.value:
        return False
    detail = detail.strip()
    return bool(detail) and detail.split(" ", 1)[0] == _LAUNDRY_ZONE_ID


def _laundry_unplaceable_message(spec, outlines: list["OutlineResult"] | None) -> str | None:
    """None unless EVERY outline this brief tried failed for a reason that names the LAUNDRY
    room's own exterior-wall/window/bay guarantee specifically (see `_LAUNDRY_REQUIREMENT_CHECKS`)
    and NOTHING ELSE — a check or a pre-solve rejection that also names a different room never
    counts, so this never blames laundry for a defect that hit another room too.
    A brief with no explicit laundry-room request never reaches here."""
    if spec.program.laundry.demand is not LaundryDemand.ROOM or not outlines:
        return None
    failed: set[str] = set()
    for outline in outlines:
        r = outline.result
        if r.validation is not None:
            failing = r.validation.failures()
            if not failing or any(c.check_id not in _LAUNDRY_REQUIREMENT_CHECKS
                                  or _check_detail_zone_ids(c.detail) != {_LAUNDRY_ZONE_ID}
                                  for c in failing):
                return None
            failed.update(_laundry_failed_requirement(c.check_id) for c in failing)
        else:
            reasons = r.metrics.rejection_reasons or r.notes
            if not reasons or not all(_rejection_reason_names_only_laundry_shape(reason)
                                      for reason in reasons):
                return None
            failed.add(_laundry_failed_requirement("C3"))
    if not failed:
        return None
    return (
        "לא הצלחנו למקם את חדר הכביסה כחדר סגור עם דלת, מרחב מתאים למכונת כביסה וחלון בקיר "
        f"חיצוני — הדרישה שלא התקיימה: {'; '.join(sorted(failed))}. "
        "אפשר להגדיל את שטח הבנייה, לשנות את המתאר שנבחר, או לוותר על חדר כביסה נפרד — "
        "לא נציג תוכנית עם חדר כביסה חסר חלון או צר מדי למכונה.")


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

        # Issue #21, AC-3: the LAUNDRY room's own guarantee (exterior wall / window / bay) is a
        # more specific, more actionable diagnosis than the generic message below — fires only
        # when it genuinely was the ONLY thing every outline failed on.
        laundry_message = _laundry_unplaceable_message(spec, outlines)
        if laundry_message is not None:
            raise DemoGenerationError("LAUNDRY_UNPLACEABLE", laundry_message, reasons,
                                      diagnostics=_diagnostics(result, spec, outlines))

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

    # ENTRANCE POLICY (Issue #20). A plan whose front door has nowhere legitimate to open into —
    # the street fronts a kitchen or a dining room, but nothing allowed — is refused with this
    # specific reason instead of the generic "did not pass planning checks". Gated on an
    # ENTRANCE-related check actually failing (C16/C23, and C7/C11 which the entrance door itself
    # can also fail) so an unrelated validation failure (furniture, corridor, ...) is never
    # misdiagnosed as an entrance problem, AND on the street genuinely fronting something
    # (disallowed) — a plan where NOTHING fronts the street at all is a different, pre-existing
    # geometry defect, not this Issue's policy, and must keep whatever code it already had.
    if result.design is not None and result.validation is not None and not result.validation.ok:
        failing_ids = {c.check_id for c in result.validation.failures()}
        if failing_ids & {"C16", "C23", "C7", "C11"}:
            fronting = _street_fronting_roles(result.design)
            allowed = {r.value for r in doors_stage.ENTRANCE_ZONE_PRIORITY}
            if fronting and not (fronting & allowed):
                named = ", ".join(sorted(fronting))
                raise DemoGenerationError(
                    "ENTRANCE_NO_ARRIVAL_ROOM",
                    f"הכניסה לבית חייבת להיפתח למסדרון, הול או סלון — חדר שאפשר להגיע אליו "
                    f"ישירות מהרחוב. בתצורה שנוצרה עבור הבקשה הזו, הרחוב פונה רק אל: {named}.",
                    "; ".join(f"{c.check_id}: {c.detail}" for c in result.validation.failures()),
                    diagnostics=_diagnostics(result, spec, outlines))

    # ENTRANCE-TO-CIRCULATION INTEGRATION (Issue #22). C25 alone failing means the front door
    # lands in a dead-space pocket — an unserved corridor stub directly beyond the door, or an
    # arrival zone with no path onward to a public room — rather than a generic planning defect.
    # Gated on C25 being the ONLY failure so an unrelated defect (furniture, corridor width, ...)
    # is never misdiagnosed as an entrance problem.
    if (result.design is not None and result.validation is not None and not result.validation.ok
            and [c.check_id for c in result.validation.failures()] == ["C25"]):
        detail = next(c.detail for c in result.validation.failures() if c.check_id == "C25")
        raise DemoGenerationError(
            "ENTRANCE_DEAD_END",
            "הכניסה לבית נפתחת אל מרחב תנועה ללא המשך — קטע מסדרון סתום ליד הדלת, או הול כניסה "
            "שאין ממנו מעבר לחלל ציבורי. אפשר להגדיל את שטח הבנייה או לשנות את המתאר שנבחר — לא "
            "נציג תוכנית עם כניסה שמובילה למבוי סתום.",
            f"C25: {detail}",
            diagnostics=_diagnostics(result, spec, outlines))

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

        laundry_message = _laundry_unplaceable_message(spec, outlines)
        if laundry_message is not None:
            raise DemoGenerationError("LAUNDRY_UNPLACEABLE", laundry_message, failures,
                                      diagnostics=_diagnostics(result, spec, outlines))

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
