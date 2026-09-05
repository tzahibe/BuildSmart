"""New design-generation pipeline:

    Project (parsed requirements) -> ArchitectModelGateway -> ArchitecturalSpec -> GeometrySolver
    -> GeneratedDesign

`GeneratedDesign` is the exact same shape `app/design/generator.py`'s old deterministic
`generate_design()` produces, so the router and the API's JSON response are unaffected by this swap —
see `backend/app/design/router.py`.

**V1 scope: single floor only.** `generate_design_via_solver` raises `MultiFloorNotSupportedError` for
any project with `floors > 1` — this pipeline does not attempt to distribute a program across multiple
floors (which room types belong on which floor, and how a hard relationship spanning two floors like
"safe room reachable from a bedroom" should even be interpreted, are open design questions, not
implementation details). `generator.py`'s old row-layout algorithm CAN handle multiple floors, but is
no longer part of the normal runtime path for this reason — see `backend/app/design/router.py`. It is
kept in the repository, untouched and still tested, purely for reference/tests; nothing here calls it,
and nothing silently falls back to it.

**V1 footprint strategy** (see `_derive_footprint`): `built_area_m2` is a program AREA BUDGET — how
much floor area the rooms should total — not a description of the building's physical outline. Treating
`sqrt(built_area_m2)` as the footprint's side (as an earlier version of this module did) would silently
assert that the building's footprint has exactly zero space beyond the sum of its rooms' areas, which
is not a real architectural fact this codebase has any basis for. Instead, the footprint's own gross
area is `built_area_m2 / _FOOTPRINT_EFFICIENCY` (still a square for V1 — this codebase has no real
parcel/setback geometry yet, same placeholder spirit as Feature 03's square-site assumption) — a
distinct, explicitly-labeled derived quantity, strictly larger than the program's area budget, leaving
headroom for circulation/walls the room program doesn't itself account for. `built_area_m2` itself
still flows through unchanged as `BuildingFootprintSpec.available_area_m2` — the solver's real area
budget is untouched by this change; only the footprint's own *shape* stopped pretending to equal it.
"""

import logging
import math
import os
import time

from app.architect.errors import ArchitectModelError
from app.architect.gateway import ArchitectModelGateway, get_architect_model_gateway
from app.architect.models import (
    ArchitectModelRequest,
    ConstraintSeverity,
    RequiredRoomConstraint,
    RequirementState,
    SiteSpec,
)
from app.design.generator import GeneratedDesign
from app.geometry.models import BuildingFootprintSpec, SolverStatus
from app.geometry.solver import GeometrySolver
from app.projects.models import Project, Room, SourceTag

logger = logging.getLogger("buildsmart.design_pipeline")

# Same Hebrew wording as the old generator.py, for continuity — these notes are user-facing.
_BEDROOMS_UNKNOWN_NOTE = "מספר חדרי השינה לא ידוע — לא נכללו חדרי שינה בפריסה."
_SAFE_ROOM_UNKNOWN_NOTE = 'האם מבוקש ממ"ד לא ידוע — לא נכלל ממ"ד בפריסה.'

# V1 placeholder, NOT a measured or regulatory figure: assumes the room program will occupy about 85%
# of the footprint's gross area, leaving ~15% for circulation/walls not modeled as their own rooms.
# See the module docstring's "V1 footprint strategy" section.
_FOOTPRINT_EFFICIENCY = 0.85


class DesignUnsatisfiableError(Exception):
    """Raised when the Geometry Solver cannot find a layout satisfying every hard constraint for this
    project. Carries the solver's own human-readable `unsatisfiable_reason`. This is the ONLY error
    this module raises for "no valid layout" — callers must not catch-and-substitute a fabricated
    result; see the module docstring."""

    code = "DESIGN_UNSATISFIABLE"


class MultiFloorNotSupportedError(Exception):
    """Raised for any project with `floors > 1` — see the module docstring's V1 scope note. Carries a
    machine-readable `code` so callers (e.g. the API router) can surface a distinguishable error
    rather than a generic message."""

    code = "MULTI_FLOOR_NOT_SUPPORTED"

    def __init__(self, floors: int) -> None:
        self.floors = floors
        super().__init__(
            f"BuildSmart's design solver currently supports single-floor projects only "
            f"(this project has floors={floors})"
        )


def _derive_footprint(project: Project) -> BuildingFootprintSpec:
    """See the module docstring's "V1 footprint strategy" — `built_area_m2` is the program's area
    BUDGET (passed through unchanged as `available_area_m2`); the footprint's own gross area is a
    separate, larger, explicitly-labeled derived quantity, never `built_area_m2` itself."""
    footprint_area_m2 = project.built_area_m2 / _FOOTPRINT_EFFICIENCY
    footprint_side_m = math.sqrt(footprint_area_m2)
    return BuildingFootprintSpec(
        width_m=footprint_side_m,
        depth_m=footprint_side_m,
        floor=1,
        available_area_m2=project.built_area_m2,
    )


def _required_room_constraint(
    room_type: str, *, source: SourceTag | None, value: int | bool | None
) -> RequiredRoomConstraint:
    """Always returns an EXPLICIT constraint — never omits it — so `MockArchitectModelGateway`'s own
    generic default can never silently apply in place of this project's actual (or actually-unknown)
    data. UNKNOWN != ZERO: an unknown source produces `state="unknown"` (no count at all, and the
    gateway is required to exclude the type rather than guess), which is a different constraint from
    `state="known", count=0` (a real, deliberate "none of this type")."""
    if source is None or source == SourceTag.unknown:
        return RequiredRoomConstraint(
            room_type=room_type, state=RequirementState.unknown, severity=ConstraintSeverity.hard
        )
    count = (1 if value else 0) if isinstance(value, bool) else (value or 0)
    return RequiredRoomConstraint(
        room_type=room_type, state=RequirementState.known, count=count, severity=ConstraintSeverity.hard
    )


def _build_request(project: Project, site_side_m: float) -> ArchitectModelRequest:
    hard_constraints = [
        _required_room_constraint(
            "bedroom",
            source=project.bedrooms.source if project.bedrooms is not None else None,
            value=project.bedrooms.value if project.bedrooms is not None else None,
        ),
        _required_room_constraint(
            "safe_room",
            source=project.safe_room.source if project.safe_room is not None else None,
            value=project.safe_room.value if project.safe_room is not None else None,
        ),
    ]

    return ArchitectModelRequest(
        brief=project.description,
        site=SiteSpec(width_m=site_side_m, depth_m=site_side_m),
        hard_constraints=hard_constraints,
    )


def _design_notes(incomplete_requirements: list[str]) -> list[str]:
    """Driven by `ArchitecturalSpec.incomplete_requirements` — the gateway's own explicit "I excluded
    this because it was unknown" signal — rather than re-deriving the same fact independently from
    `project`, so there is exactly one source of truth for which requirements were incomplete."""
    notes = []
    if "bedroom" in incomplete_requirements:
        notes.append(_BEDROOMS_UNKNOWN_NOTE)
    if "safe_room" in incomplete_requirements:
        notes.append(_SAFE_ROOM_UNKNOWN_NOTE)
    return notes


def generate_design_via_solver(
    project: Project, gateway: ArchitectModelGateway | None = None
) -> GeneratedDesign:
    """The new pipeline. `gateway` defaults to whatever `get_architect_model_gateway()` selects per
    `ARCHITECT_MODEL_PROVIDER` (mock by default) — callers that want a specific gateway (tests, or a
    caller with its own reason to override) should keep passing one explicitly; this default only
    applies when none is given.

    Raises `MultiFloorNotSupportedError` for `floors > 1` (see the module docstring's V1 scope note);
    an `app.architect.errors.ArchitectModelError` subclass if the gateway call itself fails (unreachable,
    timed out, or returned something that didn't validate — see that module); and
    `DesignUnsatisfiableError` — never a partial or fabricated layout — when the solver reports
    `SolverStatus.unsatisfiable`. All three are let through to the caller (see
    `backend/app/design/router.py`) rather than caught and collapsed into one generic failure.
    """
    floors = project.floors.value if project.floors is not None else 1
    floors = floors or 1
    if floors > 1:
        raise MultiFloorNotSupportedError(floors)

    gateway = gateway or get_architect_model_gateway()
    provider_name = type(gateway).__name__

    site_side_m = math.sqrt(project.plot_area_m2)  # same square-plot placeholder as Feature 03
    request = _build_request(project, site_side_m)

    if os.environ.get("BUILDSMART_DEBUG_LOGGING") == "1":
        # Full request content (includes the user's free-text description) — off by default; never
        # logged at normal verbosity. Never includes secrets (the gateway config itself isn't logged).
        logger.debug("architect_model_request project_id=%s payload=%r", project.project_id, request.model_dump())

    started = time.monotonic()
    try:
        spec = gateway.generate(request)
    except ArchitectModelError as error:
        duration_s = time.monotonic() - started
        logger.warning(
            "architect_model_call project_id=%s provider=%s duration_s=%.2f parse_success=false "
            "error_code=%s",
            project.project_id,
            provider_name,
            duration_s,
            error.code,
        )
        raise
    duration_s = time.monotonic() - started
    logger.info(
        "architect_model_call project_id=%s provider=%s duration_s=%.2f parse_success=true "
        "spec_valid=true incomplete_requirements=%s",
        project.project_id,
        provider_name,
        duration_s,
        spec.incomplete_requirements,
    )

    footprint = _derive_footprint(project)

    result = GeometrySolver().solve(spec, footprint)
    logger.info("geometry_solve project_id=%s status=%s", project.project_id, result.status.value)

    if result.status == SolverStatus.unsatisfiable:
        raise DesignUnsatisfiableError(
            result.unsatisfiable_reason or "No layout satisfies every hard constraint for this project"
        )

    rooms = [
        Room(
            type=instance.type,
            floor=instance.floor,
            area_m2=instance.area_m2,
            x=instance.x,
            y=instance.y,
            width_m=instance.width,
            depth_m=instance.height,
        )
        for instance in result.instances
    ]

    return GeneratedDesign(
        site_width_m=site_side_m,
        site_depth_m=site_side_m,
        rooms=rooms,
        design_notes=_design_notes(spec.incomplete_requirements),
    )
