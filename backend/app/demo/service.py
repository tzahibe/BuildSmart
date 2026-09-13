"""The demo generation service — the ONE place the validated pipeline is driven from.

    Project (parsed, user-corrected requirements)
      -> scope.check_supported            explicit refusal, never a silent downgrade
      -> requirements_view.spec_for       Project -> vertical_slice.ArchitecturalSpec
      -> concept_generator                DesiredAccessTopology + concept candidates
      -> safe_adapter                     BuildableRegion -> safe solver rectangles
      -> geometry_core                    realization
      -> doors / windows / furniture
      -> validation                       C1-C13, hard gate
      -> contract.to_demo_design          authoritative API payload

No canonical fixture is reachable from here: `concept.py`'s hand-authored concept and
`geometry_fixtures.py` are never imported. The old `app.geometry.solver` path is not used.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.projects.models import Project
from app.vertical_slice.concept_generator import (
    RejectionReason,
    build_room_program,
    program_capacity_gross_m2,
)
from app.vertical_slice.relationships import describe
from app.vertical_slice.spec import RelationStrength
from app.vertical_slice.general_pipeline import ALTERNATIVE_PLAN_LIMIT, run_general
from app.vertical_slice.safe_adapter import AdapterOutcome

from .contract import DemoDesign, DemoPlanSet, to_demo_design
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


def _diagnostics(result, spec=None) -> dict:
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

    Centred across the plot and flush to the street-side edge of the buildable rectangle, matching
    the convention the site stage already uses for parking and the entrance walk.
    """
    site = site_geometry.derive(project)
    footprint = project.selected_footprint
    if site is None or footprint is None:  # both guaranteed by scope.check_supported
        raise ValueError("_buildable_from requires an authoritative site and a footprint")

    origin_x, origin_y = site.buildable_origin_m()
    origin_x += max(0.0, (site.buildable_width_m - footprint.width_m) / 2)
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

    result = _plan(spec, project, on_stage)

    # A PREFERRED width may be dropped when the programme cannot fit it; a required one may not.
    # The retry happens once, without the corridor, and the plan says plainly that the preference
    # was not met — the person is never quietly given a narrower corridor than they asked for.
    preference_dropped = False
    if (result.outcome is not AdapterOutcome.SOLVED and corridor is not None
            and not corridor.is_binding):
        without = replace(spec, program=replace(spec.program, corridor=None))
        retry = _plan(without, project, on_stage)
        if retry.outcome is AdapterOutcome.SOLVED:
            result, preference_dropped = retry, True

    # Only claim the corridor is the problem when it plausibly is. A target area the programme
    # cannot fill is its own, already-diagnosed outcome; blaming the corridor for it would send the
    # person to shrink a corridor that was never the obstacle.
    reasons_so_far = "; ".join(result.metrics.rejection_reasons or result.notes)
    misattributed = (RejectionReason.TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY.value
                     in reasons_so_far)

    if (result.outcome is not AdapterOutcome.SOLVED and corridor is not None
            and corridor.is_binding and not misattributed):
        raise DemoGenerationError(
            "CORRIDOR_WIDTH_NOT_FEASIBLE",
            f"מסדרון ברוחב {corridor.width_m:.2f} מ׳ לא נכנס יחד עם החדרים שביקשת במתאר שנבחר. "
            f"אפשר להגדיל את שטח הבנייה, להוריד חדר, או לצמצם את רוחב המסדרון — "
            f"לא נצר תוכנית עם מסדרון צר ממה שביקשת.",
            reasons_so_far or result.outcome.value)

    return _finish(project, spec, result, preference_dropped)


def realized_corridor_width_m_of(design) -> float:
    """The narrowest realized circulation zone, in metres — measured, not assumed."""
    widths = [min(r.net_w_m, r.net_h_m) for r in design.rooms
              if {"HALL", "CIRCULATION"} & {str(getattr(role, "value", role)) for role in r.roles}]
    return round(min(widths), 2) if widths else 0.0


#: How many alternative outlines a refusal may plan before it gives up and stays generic. Each one
#: is a full solve, so this is a latency budget, not a search depth. Measured over all 331 refusals
#: in the failure log: about +1.7 s each on average (0.09 s -> 0.54 s at the median, ~2.7 s worst
#: case), and the cost falls hardest on the refusals that end up with nothing to offer, since those
#: are the ones that try every option. Lowering this trades suggestions for latency; it buys
#: nothing on the happy path, which never reaches here.
_MAX_ALTERNATIVE_OUTLINES = 4


def _outline_that_plans(project: Project) -> tuple[float, float] | None:
    """An outline of the SAME built area this programme CAN be planned into, or None.

    `site_geometry.feasible_options` answers a weaker question than the one a refused person is
    asking: it filters on whether the area fits inside the setbacks, not on whether the planner can
    tile this programme into that shape. The gap between those two is large and, crucially, is not
    the person's mistake to fix by guessing — measured over the refusals left after the column-seam
    search, 35% have an offered outline that yields a real design at the SAME area, with the same
    rooms. A 200 m2 brief refused at 10.00 x 20.00 m plans at 13.80 x 14.49 m.

    Every option is planned END TO END here — concepts, Geometry Core, validation — so an outline
    is named only after it has actually produced a design. Naming one the concept stage merely
    liked would send the person to a second dead end, which is worse than saying nothing: of the
    outlines that pass the concept stage, roughly a quarter still fail downstream.
    """
    site = site_geometry.derive(project)
    chosen = project.selected_footprint
    if site is None or chosen is None:
        return None

    for width_m, depth_m in site_geometry.feasible_options(site, chosen.area_m2)[
            :_MAX_ALTERNATIVE_OUTLINES]:
        if (abs(width_m - chosen.width_m) < 0.05 and abs(depth_m - chosen.depth_m) < 0.05):
            continue
        candidate = project.model_copy(update={"selected_footprint": chosen.model_copy(
            update={"width_m": width_m, "depth_m": depth_m,
                    "area_m2": round(width_m * depth_m, 4)})})
        try:
            candidate_spec = spec_for(candidate)
            # Deliberately NOT `_plan`: that asks for the demo screen's alternative plans too,
            # which is three more full solves per option for an answer this only needs once —
            # does a design exist at this outline, yes or no.
            attempt = run_general(
                _buildable_from(candidate_spec, candidate),
                plot_size_m=(candidate_spec.plot.width_m, candidate_spec.plot.depth_m),
                program=candidate_spec.program,
            )
        except Exception:  # noqa: BLE001
            # An alternative that cannot even be set up is simply not offered. This runs while a
            # refusal is already being raised, and must never replace that refusal with a crash.
            continue
        # The SAME bar `_finish` holds a plan to, deliberately duplicated rather than approximated:
        # a design that exists but fails validation is one this service refuses, so offering it
        # would send the person to a second dead end. Checking only `design is not None` named an
        # outline the service then rejected with PLAN_FAILED_VALIDATION in 7.5% of a sampled 40.
        if attempt.design is not None and attempt.validation is not None and attempt.validation.ok:
            return width_m, depth_m
    return None


def _plan(spec, project: Project, on_stage=None):
    # The demo screen SHOWS the other plans, so the demo is what asks for them to be computed.
    # Every other caller of the pipeline still gets one plan at one plan's cost.
    return run_general(
        _buildable_from(spec, project),
        plot_size_m=(spec.plot.width_m, spec.plot.depth_m),
        program=spec.program,
        max_alternatives=ALTERNATIVE_PLAN_LIMIT,
        on_stage=on_stage,
    )


def _finish(project: Project, spec, result, preference_dropped: bool) -> DemoResult:
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
                reasons, diagnostics=_diagnostics(result, spec))

        # A refusal that can name a footprint which DOES work is worth the extra solves: the
        # obstacle here is usually the outline's proportion, not the brief, and "this shape of the
        # same area works" is something the person can act on. Where no offered outline plans, the
        # message stays as it was rather than inventing a suggestion it has not verified.
        alternative = _outline_that_plans(project)
        if alternative is not None:
            width_m, depth_m = alternative
            chosen = project.selected_footprint
            raise DemoGenerationError(
                "PLAN_NOT_REALIZABLE",
                f"המתאר שנבחר ({chosen.width_m:.2f}×{chosen.depth_m:.2f} מ׳) לא מאפשר לסדר את "
                f"החדרים שביקשת. מתאר של {width_m:.2f}×{depth_m:.2f} מ׳ — באותו שטח בנייה "
                f"ובאותן דרישות — כן מתאפשר. הדרישות שלך נשמרו כפי שהזנת.",
                reasons,
                diagnostics=_diagnostics(result, spec),
            )

        raise DemoGenerationError(
            "PLAN_NOT_REALIZABLE",
            "לא הצלחנו לייצר תוכנית תקינה עבור הדרישות והמתאר שנבחרו.",
            reasons,
            diagnostics=_diagnostics(result, spec),
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
                failures, diagnostics=_diagnostics(result, spec))
        raise DemoGenerationError(
            "PLAN_FAILED_VALIDATION",
            "התוכנית שנוצרה לא עברה את בדיקות התכנון ולכן לא הוצגה.",
            failures, diagnostics=_diagnostics(result, spec))

    if result.safety is not None and not result.safety.ok:
        raise DemoGenerationError(
            "PLAN_OUTSIDE_BUILDABLE",
            "התוכנית שנוצרה חרגה משטח הבנייה המותר ולכן לא הוצגה.",
            ", ".join(result.safety.offending_rooms),
            diagnostics=_diagnostics(result, spec))

    # Only PREFERENCES can reach a plan: `check_supported` refuses outright on a hard requirement
    # or an unclear one, so anything still here was explicitly optional. It describes the BRIEF,
    # not the drawing, so every alternative carries the same note.
    unsupported = _set_aside(project, spec, preference_dropped)
    return DemoResult(
        design=to_demo_design(result.design, result.validation, unsupported=unsupported,
                              corridor=spec.program.corridor,
                              relationships=result.relationships),
        # Each alternative reports its OWN validation statements and its OWN relationship
        # outcomes, because the panel beside the drawing must describe the drawing on screen.
        alternatives=tuple(
            to_demo_design(plan.design, plan.validation, unsupported=unsupported,
                           corridor=spec.program.corridor, relationships=plan.relationships)
            for plan in result.alternatives))
