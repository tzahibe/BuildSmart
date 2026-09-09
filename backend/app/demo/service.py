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
from app.vertical_slice.general_pipeline import run_general
from app.vertical_slice.safe_adapter import AdapterOutcome

from .contract import DemoDesign, to_demo_design
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


class DemoGenerationError(Exception):
    """A product-level failure. Carries a message meant for a person."""

    def __init__(self, code: str, message: str, detail: str = "") -> None:
        if code in _FEASIBILITY_CODES:
            message = f"{message} {site_geometry.NOT_FEASIBLE_HE}"
            detail = f"{detail} [{site_geometry.NOT_FEASIBLE_PHRASE}]".strip()
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class DemoResult:
    design: DemoDesign


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


def generate_demo_design(project: Project) -> DemoResult:
    rejection: ScopeRejection | None = check_supported(project)
    if rejection is not None:
        raise DemoGenerationError(rejection.code.value, rejection.message, rejection.detail)

    spec = spec_for(project)
    corridor = spec.program.corridor

    result = _plan(spec, project)

    # A PREFERRED width may be dropped when the programme cannot fit it; a required one may not.
    # The retry happens once, without the corridor, and the plan says plainly that the preference
    # was not met — the person is never quietly given a narrower corridor than they asked for.
    preference_dropped = False
    if (result.outcome is not AdapterOutcome.SOLVED and corridor is not None
            and not corridor.is_binding):
        without = replace(spec, program=replace(spec.program, corridor=None))
        retry = _plan(without, project)
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


def _plan(spec, project: Project):
    return run_general(
        _buildable_from(spec, project),
        plot_size_m=(spec.plot.width_m, spec.plot.depth_m),
        program=spec.program,
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
        if RejectionReason.TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY.value in reasons:
            rooms = build_room_program(spec)
            capacity = program_capacity_gross_m2(rooms)
            raise DemoGenerationError(
                "TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY",
                f"התוכנית שביקשת יכולה למלא עד כ-{capacity:.0f} מ\"ר בצורה סבירה, "
                f"והיעד שהוזן הוא {spec.program.target_built_area_m2:.0f} מ\"ר. "
                f"אפשר להוסיף חדרים או להקטין את שטח הבנייה — הדרישות שלך נשמרו כפי שהזנת.",
                reasons)

        raise DemoGenerationError(
            "PLAN_NOT_REALIZABLE",
            "לא הצלחנו לייצר תוכנית תקינה עבור הדרישות והמתאר שנבחרו.",
            reasons,
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
        raise DemoGenerationError(
            "PLAN_FAILED_VALIDATION",
            "התוכנית שנוצרה לא עברה את בדיקות התכנון ולכן לא הוצגה.",
            failures)

    if result.safety is not None and not result.safety.ok:
        raise DemoGenerationError(
            "PLAN_OUTSIDE_BUILDABLE",
            "התוכנית שנוצרה חרגה משטח הבנייה המותר ולכן לא הוצגה.",
            ", ".join(result.safety.offending_rooms))

    return DemoResult(design=to_demo_design(
        result.design, result.validation,
        # Only PREFERENCES can reach a plan: `check_supported` refuses outright on a hard
        # requirement or an unclear one, so anything still here was explicitly optional.
        unsupported=_set_aside(project, spec, preference_dropped),
        corridor=spec.program.corridor,
        relationships=result.relationships))
