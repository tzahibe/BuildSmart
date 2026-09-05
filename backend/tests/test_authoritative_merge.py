"""Tests for `app/architect/authoritative_merge.py` — covers the required scenarios B/C/D from this
milestone's brief:

B/C. Model output lacks SAFE_ROOM (confirmed: the real model has no such room type at all) but
     BuildSmart's request authoritatively requires one -> the final spec must contain it, tagged
     traceable to BuildSmart, never to the model.
D.   Bedroom count was UNKNOWN upstream, but the (real or mock) gateway's spec contains a model-invented
     bedroom count anyway -> the merge must strip it, never let it reach the solver.

Uses the same real captured Architect Model V1 output as `test_adapter.py` (already adapted into an
`ArchitecturalSpec` via `adapt_model_spec`), run through the merge with a request that mirrors what
`app/design/pipeline.py::_build_request` actually sends.
"""

import json

from app.architect.adapter import adapt_model_spec
from app.architect.authoritative_merge import merge_authoritative_requirements
from app.architect.model_schema import ModelArchitecturalSpec
from app.architect.models import (
    ArchitectModelRequest,
    ConstraintSeverity,
    DirectAccessConstraint,
    RequiredRoomConstraint,
    RequirementState,
    SiteSpec,
)

# Real raw output for a "3 bedrooms + explicit safe room" request — the model was asked for a safe room
# (via a REQUIRED_ROOM constraint targeting "SAFE_ROOM") and silently produced none at all; this is
# exactly what was captured, unedited.
_REAL_CASE_2_RAW_JSON = """
{"program": [{"type": "BALCONY", "count": 1, "area_per_room_m2": 4.5, "zone": "OUTDOOR"}, {"type": "BATHROOM", "count": 2, "area_per_room_m2": 4.0, "zone": "SERVICE"}, {"type": "BEDROOM", "count": 3, "area_per_room_m2": 16.0, "zone": "PRIVATE"}, {"type": "KITCHEN", "count": 1, "area_per_room_m2": 7.0, "zone": "SERVICE"}, {"type": "LIVING", "count": 1, "area_per_room_m2": 32.5, "zone": "PUBLIC"}], "zones": [{"type": "OUTDOOR", "room_types": ["BALCONY"]}, {"type": "SERVICE", "room_types": ["BATHROOM", "KITCHEN"]}, {"type": "PRIVATE", "room_types": ["BEDROOM"]}, {"type": "PUBLIC", "room_types": ["LIVING"]}], "relationships": [{"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BALCONY", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "KITCHEN", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "KITCHEN", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}], "circulation": []}
"""


def _adapted_case_2():
    model_spec = ModelArchitecturalSpec.model_validate(json.loads(_REAL_CASE_2_RAW_JSON))
    return adapt_model_spec(model_spec).spec


def _request(*, bedroom_state, bedroom_count=None, safe_room_state=None, safe_room_count=None) -> ArchitectModelRequest:
    hard_constraints = [
        RequiredRoomConstraint(room_type="bedroom", state=bedroom_state, count=bedroom_count, severity=ConstraintSeverity.hard)
    ]
    if safe_room_state is not None:
        hard_constraints.append(
            RequiredRoomConstraint(room_type="safe_room", state=safe_room_state, count=safe_room_count, severity=ConstraintSeverity.hard)
        )
    return ArchitectModelRequest(brief="test", site=SiteSpec(width_m=10, depth_m=10), hard_constraints=hard_constraints)


# --- B/C: SAFE_ROOM has no model equivalent, but BuildSmart's own requirement must still be honored ---


def test_safe_room_is_injected_when_authoritatively_required_but_absent_from_model_output():
    spec = _adapted_case_2()
    assert not any(item.room_type == "safe_room" for item in spec.program)  # sanity: model really omitted it

    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=1)
    merged = merge_authoritative_requirements(spec, request)

    safe_room_items = [item for item in merged.program if item.room_type == "safe_room"]
    assert len(safe_room_items) == 1
    assert safe_room_items[0].source == "USER_REQUIREMENT"
    assert safe_room_items[0].source != "MODEL_INFERENCE"


def test_safe_room_is_placed_in_a_zone():
    spec = _adapted_case_2()
    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=1)

    merged = merge_authoritative_requirements(spec, request)

    assert any("safe_room" in zone.room_types for zone in merged.zones)


def test_safe_room_gets_a_hard_direct_access_link_to_bedroom_tagged_user_requirement():
    spec = _adapted_case_2()
    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=1)

    merged = merge_authoritative_requirements(spec, request)

    links = [
        rel
        for rel in merged.relationships
        if isinstance(rel, DirectAccessConstraint) and {rel.room_type_a, rel.room_type_b} == {"safe_room", "bedroom"}
    ]
    assert len(links) == 1
    assert links[0].severity == ConstraintSeverity.hard
    assert links[0].source == "USER_REQUIREMENT"


def test_no_safe_room_link_is_added_when_bedroom_is_not_present():
    # Defensive: the merge must never reference a room type absent from the final program (the spec's
    # own cross-reference validator would reject that anyway).
    spec = _adapted_case_2()
    request = _request(bedroom_state=RequirementState.unknown, safe_room_state=RequirementState.known, safe_room_count=1)

    merged = merge_authoritative_requirements(spec, request)

    assert not any(item.room_type == "bedroom" for item in merged.program)
    assert not any(
        isinstance(rel, DirectAccessConstraint) and "safe_room" in (rel.room_type_a, rel.room_type_b)
        for rel in merged.relationships
    )


def test_safe_room_not_wanted_stays_absent():
    spec = _adapted_case_2()
    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=0)

    merged = merge_authoritative_requirements(spec, request)

    assert not any(item.room_type == "safe_room" for item in merged.program)
    assert "safe_room" not in merged.incomplete_requirements  # a real "none wanted", not an unknown


# --- D: bedroom count UNKNOWN upstream must win over whatever the model invented -----------------------


def test_unknown_bedroom_strips_a_model_invented_bedroom_count():
    spec = _adapted_case_2()
    assert any(item.room_type == "bedroom" and item.count == 3 for item in spec.program)  # model did invent 3

    request = _request(bedroom_state=RequirementState.unknown)
    merged = merge_authoritative_requirements(spec, request)

    assert not any(item.room_type == "bedroom" for item in merged.program)
    assert not any("bedroom" in zone.room_types for zone in merged.zones)
    assert not any("bedroom" in (rel.room_type_a, rel.room_type_b) for rel in merged.relationships)
    assert "bedroom" in merged.incomplete_requirements


def test_known_bedroom_count_mismatching_the_model_is_corrected_not_trusted():
    spec = _adapted_case_2()  # model said 3
    request = _request(bedroom_state=RequirementState.known, bedroom_count=5)  # BuildSmart authoritatively says 5

    merged = merge_authoritative_requirements(spec, request)

    bedroom_items = [item for item in merged.program if item.room_type == "bedroom"]
    assert len(bedroom_items) == 1
    assert bedroom_items[0].count == 5
    assert bedroom_items[0].source == "USER_REQUIREMENT"


def test_known_bedroom_count_matching_the_model_is_still_stamped_authoritative():
    spec = _adapted_case_2()  # model said 3
    request = _request(bedroom_state=RequirementState.known, bedroom_count=3)

    merged = merge_authoritative_requirements(spec, request)

    bedroom_items = [item for item in merged.program if item.room_type == "bedroom"]
    assert len(bedroom_items) == 1
    assert bedroom_items[0].count == 3
    assert bedroom_items[0].source == "USER_REQUIREMENT"


def test_merge_is_a_no_op_for_a_spec_that_already_satisfies_every_authoritative_requirement():
    # MockArchitectModelGateway already honors its own request's hard constraints — the merge running
    # after it too should not change program/zone/relationship counts.
    spec = _adapted_case_2()
    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=0)

    merged = merge_authoritative_requirements(spec, request)

    assert len(merged.program) == len(spec.program)
    assert sorted(item.room_type for item in merged.program) == sorted(item.room_type for item in spec.program)
