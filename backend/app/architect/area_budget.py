"""Authoritative area budgeting — reserves area for HARD room requirements the model has no vocabulary
for (today: only `safe_room`) BEFORE the model is ever asked to allocate the rest of the program, so
`app/architect/authoritative_merge.py` injecting that room afterwards doesn't push the total over
`built_area_m2`.

    total_area_m2  -  reserved_authoritative_area_m2  =  model_available_area_m2

Generic on purpose (per this milestone's brief: "keep this generic enough for future authoritative
program requirements rather than scattering special-case arithmetic through the pipeline") — it walks
whatever `RequiredRoomConstraint`s the caller built, not a hardcoded `"safe_room"` check. A room type is
reserved only when `app.architect.adapter.model_room_type_for` says the model has NO vocabulary for it
at all — the moment a future model version adds e.g. a native SAFE_ROOM type, this stops reserving for
it automatically (no double-reservation), since the model would then be expected to budget for it itself
exactly like it already does for bedrooms/bathrooms/etc.

This intentionally never touches `BuildingFootprintSpec.available_area_m2` (still `built_area_m2`
exactly, no headroom) or the Geometry Solver — it only changes what the MODEL is told its budget is.
"""

from dataclasses import dataclass

from app.architect.adapter import model_room_type_for
from app.architect.gateway import TARGET_AREA_M2
from app.architect.models import ArchitectConstraint, RequiredRoomConstraint, RequirementState


class AuthoritativeAreaExceedsBudgetError(Exception):
    """Raised before any model call when authoritative reserved area alone consumes (or exceeds) the
    entire built-area budget — there would be nothing left to even ask the model for."""

    code = "AUTHORITATIVE_AREA_EXCEEDS_BUDGET"


@dataclass(frozen=True)
class AreaBudget:
    total_area_m2: float
    reserved_authoritative_area_m2: float
    model_available_area_m2: float
    reserved_room_types: tuple[str, ...]


def compute_area_budget(total_area_m2: float, hard_constraints: list[ArchitectConstraint]) -> AreaBudget:
    reserved = 0.0
    reserved_room_types: list[str] = []

    for constraint in hard_constraints:
        if not isinstance(constraint, RequiredRoomConstraint):
            continue
        if constraint.state != RequirementState.known:
            continue
        count = constraint.count or 0
        if count <= 0:
            continue
        if model_room_type_for(constraint.room_type) is not None:
            # The model already has vocabulary for this room type and budgets for it itself as part of
            # its own program (like it does for bedrooms) — reserving again here would double-count.
            continue
        per_room_area = TARGET_AREA_M2.get(constraint.room_type)
        if per_room_area is None:
            # No known placeholder size for this room type — nothing to reserve; not fabricating a
            # number we don't have.
            continue
        reserved += per_room_area * count
        reserved_room_types.append(constraint.room_type)

    model_available = total_area_m2 - reserved
    if model_available <= 0:
        raise AuthoritativeAreaExceedsBudgetError(
            f"Authoritative reserved area ({reserved:.1f} m² for {reserved_room_types}) leaves no "
            f"budget for the model within the total built area ({total_area_m2:.1f} m²)"
        )

    return AreaBudget(
        total_area_m2=total_area_m2,
        reserved_authoritative_area_m2=reserved,
        model_available_area_m2=model_available,
        reserved_room_types=tuple(reserved_room_types),
    )
