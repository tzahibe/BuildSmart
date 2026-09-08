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

from dataclasses import dataclass

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.projects.models import Project
from app.vertical_slice.general_pipeline import run_general
from app.vertical_slice.safe_adapter import AdapterOutcome

from .contract import DemoDesign, to_demo_design
from .requirements_view import spec_for
from .scope import ScopeRejection, check_supported


class DemoGenerationError(Exception):
    """A product-level failure. Carries a message meant for a person."""

    def __init__(self, code: str, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class DemoResult:
    design: DemoDesign


def _buildable_from(spec) -> BuildableRegion:
    """The user's selected rectangle IS the buildable region, placed inside its setbacks."""
    origin_x, origin_y = spec.plot.buildable_origin_m()
    width, depth = spec.plot.buildable_size_m()
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(origin_x, origin_y, width, depth))),
        Provenance(Source.USER, Authority.ASSUMED, ref="selected building footprint"),
    )


def generate_demo_design(project: Project) -> DemoResult:
    rejection: ScopeRejection | None = check_supported(project)
    if rejection is not None:
        raise DemoGenerationError(rejection.code.value, rejection.message, rejection.detail)

    spec = spec_for(project)
    result = run_general(
        _buildable_from(spec),
        plot_size_m=(spec.plot.width_m, spec.plot.depth_m),
        program=spec.program,
    )

    if result.outcome is not AdapterOutcome.SOLVED or result.design is None:
        raise DemoGenerationError(
            "PLAN_NOT_REALIZABLE",
            "לא הצלחנו לייצר תוכנית תקינה עבור הדרישות והמתאר שנבחרו.",
            "; ".join(result.metrics.rejection_reasons or result.notes) or result.outcome.value,
        )

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

    return DemoResult(design=to_demo_design(result.design, result.validation))
