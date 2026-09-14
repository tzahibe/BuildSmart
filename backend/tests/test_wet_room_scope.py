"""Decision A of specs/007: a wet-room programme that leaves a bedroom without a bathroom is a
question asked BEFORE planning — `NEEDS_CLARIFICATION` from `scope.check_supported` — and the
question does not choose the answer."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.demo import scope, service
from app.demo.scope import ScopeCode, check_supported
from app.projects.models import (
    Project, SelectedFootprint, SourceTag, StreetSide, TaggedBool, TaggedInt, WetRoomKindRecord,
)


def _project(*, bedrooms: int, wet_rooms: int, kinds: list[WetRoomKindRecord] | None = None) -> Project:
    """A 15 x 15 m parcel with a 15.00 x 11.73 m footprint — the reported product scenario."""
    now = datetime.now(timezone.utc)
    return Project(
        project_id="TEST", city="TLV", street="S", plot_area_m2=225.0,
        plot_width_m=15.0, plot_depth_m=15.0, street_facing_side=StreetSide("NORTH"),
        built_area_m2=176.0, description="", status="active", created_at=now, updated_at=now,
        selected_footprint=SelectedFootprint(source="CUSTOM", shape_type="RECTANGLE",
                                             target_area_m2=176.0, width_m=15.0, depth_m=11.73,
                                             area_m2=175.95),
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=bedrooms, source=SourceTag.requested),
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
        parking_spaces=TaggedInt(value=0, source=SourceTag.requested),
        wet_rooms=TaggedInt(value=wet_rooms, source=SourceTag.requested),
        open_plan=TaggedBool(value=True, source=SourceTag.requested),
        wet_room_kinds=kinds or [],
        requirements_parsed_at=now,
    )


def _record(kind: str, host: str | None = None, strength: str = "required") -> WetRoomKindRecord:
    return WetRoomKindRecord(kind=kind, host=host, strength=strength, source=SourceTag.requested)


DECISION_A = [_record("ensuite", "MASTER_BEDROOM"), _record("guest_wc")]


def test_a_legacy_project_with_no_kinds_is_not_refused_on_wet_rooms():
    assert check_supported(_project(bedrooms=2, wet_rooms=2)) is None


def test_ensuite_plus_guest_wc_with_a_second_bedroom_needs_clarification():
    rejection = check_supported(_project(bedrooms=2, wet_rooms=2, kinds=DECISION_A))
    assert rejection is not None and rejection.code is ScopeCode.NEEDS_CLARIFICATION
    assert "I4" in rejection.detail and "BEDROOM_1" in rejection.detail
    # The message names the room and what is missing — and says it will not decide.
    assert "חדר שינה 1" in rejection.message
    assert "לא נכריע" in rejection.message


def test_the_same_brief_in_a_one_bedroom_house_is_not_a_question():
    assert check_supported(_project(bedrooms=1, wet_rooms=2, kinds=DECISION_A)) is None


def test_the_question_is_asked_before_anything_is_planned(monkeypatch):
    """`generate_demo_design` must refuse from scope, never reach the engine."""
    def never(*args, **kwargs):
        raise AssertionError("run_general was called for a programme that needs clarification")
    monkeypatch.setattr(service, "run_general", never)
    with pytest.raises(service.DemoGenerationError) as exc:
        service.generate_demo_design(_project(bedrooms=2, wet_rooms=2, kinds=DECISION_A))
    assert exc.value.code == ScopeCode.NEEDS_CLARIFICATION.value


def test_a_record_this_build_cannot_read_is_a_question_not_a_default():
    rejection = check_supported(_project(bedrooms=2, wet_rooms=1, kinds=[_record("sauna")]))
    assert rejection is not None and rejection.code is ScopeCode.NEEDS_CLARIFICATION
    assert "sauna" in rejection.detail


def test_more_kinds_than_wet_rooms_is_a_question():
    rejection = check_supported(_project(bedrooms=2, wet_rooms=1,
                                         kinds=[_record("shared_bathroom"), _record("guest_wc")]))
    assert rejection is not None and rejection.code is ScopeCode.NEEDS_CLARIFICATION


def test_scope_order_wet_room_check_comes_after_count_limits():
    """A count outside scope is still the count refusal, not a wet-room one."""
    rejection = check_supported(_project(bedrooms=2, wet_rooms=max(scope.SUPPORTED_WET_ROOMS) + 1,
                                         kinds=DECISION_A))
    assert rejection is not None and rejection.code is ScopeCode.WET_ROOMS_UNSUPPORTED
