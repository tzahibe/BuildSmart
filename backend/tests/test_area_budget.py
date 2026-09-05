"""Tests for `app/architect/area_budget.py` — the authoritative area-reservation step that prevents
`authoritative_merge.py` injecting a safe_room from pushing the final program over `built_area_m2` (see
this milestone's real-model product validation, which found the model routinely spends the ENTIRE area
budget itself since it has no idea a safe room will be added afterward).
"""

import pytest

from app.architect.area_budget import AuthoritativeAreaExceedsBudgetError, compute_area_budget
from app.architect.gateway import TARGET_AREA_M2
from app.architect.models import ConstraintSeverity, RequiredRoomConstraint, RequirementState


def _bedroom(state=RequirementState.known, count=3) -> RequiredRoomConstraint:
    return RequiredRoomConstraint(room_type="bedroom", state=state, count=count, severity=ConstraintSeverity.hard)


def _safe_room(state=RequirementState.known, count=1) -> RequiredRoomConstraint:
    if state == RequirementState.unknown:
        count = None
    return RequiredRoomConstraint(room_type="safe_room", state=state, count=count, severity=ConstraintSeverity.hard)


def test_safe_room_area_is_reserved_out_of_the_total():
    budget = compute_area_budget(100.0, [_bedroom(), _safe_room()])

    assert budget.total_area_m2 == 100.0
    assert budget.reserved_authoritative_area_m2 == TARGET_AREA_M2["safe_room"]
    assert budget.model_available_area_m2 == 100.0 - TARGET_AREA_M2["safe_room"]
    assert budget.reserved_room_types == ("safe_room",)


def test_bedroom_is_never_reserved_the_model_already_has_vocabulary_for_it():
    # Reserving for bedroom too would double-count area the model already budgets for itself — see
    # module docstring's "no double-reservation" requirement.
    budget = compute_area_budget(100.0, [_bedroom(count=5), _safe_room(state=RequirementState.unknown)])

    assert budget.reserved_authoritative_area_m2 == 0.0
    assert budget.model_available_area_m2 == 100.0
    assert budget.reserved_room_types == ()


def test_unknown_safe_room_reserves_nothing():
    budget = compute_area_budget(100.0, [_bedroom(), _safe_room(state=RequirementState.unknown)])

    assert budget.reserved_authoritative_area_m2 == 0.0
    assert budget.model_available_area_m2 == 100.0


def test_safe_room_count_zero_reserves_nothing():
    budget = compute_area_budget(100.0, [_bedroom(), _safe_room(count=0)])

    assert budget.reserved_authoritative_area_m2 == 0.0


def test_multiple_safe_rooms_multiply_the_reservation():
    budget = compute_area_budget(100.0, [_bedroom(), _safe_room(count=2)])

    assert budget.reserved_authoritative_area_m2 == TARGET_AREA_M2["safe_room"] * 2


def test_reserved_area_exceeding_total_raises_before_any_model_call():
    with pytest.raises(AuthoritativeAreaExceedsBudgetError):
        compute_area_budget(8.0, [_bedroom(), _safe_room()])  # 9 m² reserved > 8 m² total


def test_reserved_area_exactly_equal_to_total_also_raises():
    # Leaves exactly 0 m² for the model — not a usable budget either.
    budget_area = TARGET_AREA_M2["safe_room"]
    with pytest.raises(AuthoritativeAreaExceedsBudgetError):
        compute_area_budget(budget_area, [_bedroom(), _safe_room()])
