"""End-to-end integration tests for this milestone's required scenarios (A-F), run through the FULL
real chain:

    real captured Architect Model V1 output (raw JSON, byte-for-byte from this integration's own live
    inference run against the actual base model + accepted LoRA adapter)
      -> ModelArchitecturalSpec (the model's own schema)
      -> adapt_model_spec (app/architect/adapter.py)
      -> merge_authoritative_requirements (app/architect/authoritative_merge.py)
      -> GeometrySolver (app/geometry/solver.py, completely unmodified)

No stub/mock gateway is involved — the raw JSON strings below are exactly what the real model produced;
only the request context (what BuildSmart authoritatively required) varies per scenario. This is the
same real data used by test_adapter.py/test_authoritative_merge.py, exercised here all the way through
to a solved (or deliberately unsolved) floor plan.
"""

import json
import math

from app.architect.adapter import adapt_model_spec
from app.architect.authoritative_merge import merge_authoritative_requirements
from app.architect.model_schema import ModelArchitecturalSpec
from app.architect.models import ArchitectModelRequest, ConstraintSeverity, RequiredRoomConstraint, RequirementState, SiteSpec
from app.geometry.models import BuildingFootprintSpec, SolverStatus
from app.geometry.solver import GeometrySolver

# Real raw outputs captured from the actual accepted model (base Qwen2.5-Coder-7B-Instruct + the
# accepted LoRA adapter) during this integration's live-inference verification run.

_RAW_2BR = """
{"program": [{"type": "BALCONY", "count": 1, "area_per_room_m2": 3.5, "zone": "OUTDOOR"}, {"type": "BATHROOM", "count": 1, "area_per_room_m2": 9.0, "zone": "SERVICE"}, {"type": "BEDROOM", "count": 2, "area_per_room_m2": 14.0, "zone": "PRIVATE"}, {"type": "KITCHEN", "count": 1, "area_per_room_m2": 6.0, "zone": "SERVICE"}, {"type": "LIVING", "count": 1, "area_per_room_m2": 23.0, "zone": "PUBLIC"}], "zones": [{"type": "OUTDOOR", "room_types": ["BALCONY"]}, {"type": "SERVICE", "room_types": ["BATHROOM", "KITCHEN"]}, {"type": "PRIVATE", "room_types": ["BEDROOM"]}, {"type": "PUBLIC", "room_types": ["LIVING"]}], "relationships": [{"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "KITCHEN", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "KITCHEN", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}], "circulation": []}
"""

_RAW_3BR_SAFEROOM_REQUESTED = """
{"program": [{"type": "BALCONY", "count": 1, "area_per_room_m2": 4.5, "zone": "OUTDOOR"}, {"type": "BATHROOM", "count": 2, "area_per_room_m2": 4.0, "zone": "SERVICE"}, {"type": "BEDROOM", "count": 3, "area_per_room_m2": 16.0, "zone": "PRIVATE"}, {"type": "KITCHEN", "count": 1, "area_per_room_m2": 7.0, "zone": "SERVICE"}, {"type": "LIVING", "count": 1, "area_per_room_m2": 32.5, "zone": "PUBLIC"}], "zones": [{"type": "OUTDOOR", "room_types": ["BALCONY"]}, {"type": "SERVICE", "room_types": ["BATHROOM", "KITCHEN"]}, {"type": "PRIVATE", "room_types": ["BEDROOM"]}, {"type": "PUBLIC", "room_types": ["LIVING"]}], "relationships": [{"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BALCONY", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "KITCHEN", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "KITCHEN", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}], "circulation": []}
"""

_RAW_4BR_SAFEROOM_REQUESTED = """
{"program": [{"type": "BALCONY", "count": 1, "area_per_room_m2": 5.0, "zone": "OUTDOOR"}, {"type": "BATHROOM", "count": 2, "area_per_room_m2": 6.0, "zone": "SERVICE"}, {"type": "BEDROOM", "count": 4, "area_per_room_m2": 15.0, "zone": "PRIVATE"}, {"type": "KITCHEN", "count": 1, "area_per_room_m2": 9.0, "zone": "SERVICE"}, {"type": "LIVING", "count": 1, "area_per_room_m2": 47.5, "zone": "PUBLIC"}], "zones": [{"type": "OUTDOOR", "room_types": ["BALCONY"]}, {"type": "SERVICE", "room_types": ["BATHROOM", "KITCHEN"]}, {"type": "PRIVATE", "room_types": ["BEDROOM"]}, {"type": "PUBLIC", "room_types": ["LIVING"]}], "relationships": [{"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BALCONY", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "KITCHEN", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "KITCHEN", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}], "circulation": []}
"""


def _adapt(raw_json: str):
    model_spec = ModelArchitecturalSpec.model_validate(json.loads(raw_json))
    return adapt_model_spec(model_spec).spec


def _request(*, bedroom_state, bedroom_count=None, safe_room_state=None, safe_room_count=None) -> ArchitectModelRequest:
    hard_constraints = [
        RequiredRoomConstraint(room_type="bedroom", state=bedroom_state, count=bedroom_count, severity=ConstraintSeverity.hard)
    ]
    if safe_room_state is not None:
        hard_constraints.append(
            RequiredRoomConstraint(room_type="safe_room", state=safe_room_state, count=safe_room_count, severity=ConstraintSeverity.hard)
        )
    return ArchitectModelRequest(brief="test", site=SiteSpec(width_m=12, depth_m=12), hard_constraints=hard_constraints)


def _generous_footprint(total_program_area_m2: float) -> BuildingFootprintSpec:
    # Same spirit as app/design/pipeline.py's own _derive_footprint (85% efficiency placeholder), with
    # extra headroom on top so these tests aren't sensitive to the solver's exact packing behavior.
    footprint_area = (total_program_area_m2 * 1.4) / 0.85
    side = math.sqrt(footprint_area)
    return BuildingFootprintSpec(width_m=side, depth_m=side, floor=1, available_area_m2=total_program_area_m2 * 1.4)


# --- A: 2 bedrooms, no safe room requested ---------------------------------------------------------


def test_a_2_bedrooms_model_output_through_adapter_and_merge_to_a_solved_layout():
    spec = _adapt(_RAW_2BR)
    request = _request(bedroom_state=RequirementState.known, bedroom_count=2)
    merged = merge_authoritative_requirements(spec, request)

    total_area = sum((item.target_area_m2 or 0) * item.count for item in merged.program)
    result = GeometrySolver().solve(merged, _generous_footprint(total_area))

    assert result.status == SolverStatus.satisfied
    bedroom_instances = [instance for instance in result.instances if instance.type.startswith("bedroom")]
    assert len(bedroom_instances) == 2
    assert not any(instance.type.startswith("safe_room") for instance in result.instances)


# --- B/C: SAFE_ROOM requested, model never produces it -> authoritative merge must still deliver it ---


def test_b_3_bedrooms_plus_safe_room_reaches_final_geometry_even_though_the_model_omitted_it():
    spec = _adapt(_RAW_3BR_SAFEROOM_REQUESTED)
    assert not any(item.room_type == "safe_room" for item in spec.program)  # confirm the model really omitted it

    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=1)
    merged = merge_authoritative_requirements(spec, request)
    assert any(item.room_type == "safe_room" for item in merged.program)  # confirmed in the SOLVER INPUT

    total_area = sum((item.target_area_m2 or 0) * item.count for item in merged.program)
    result = GeometrySolver().solve(merged, _generous_footprint(total_area))

    assert result.status == SolverStatus.satisfied
    safe_room_instances = [instance for instance in result.instances if instance.type.startswith("safe_room")]
    assert len(safe_room_instances) == 1  # confirmed in the FINAL GEOMETRY
    bedroom_instances = [instance for instance in result.instances if instance.type.startswith("bedroom")]
    assert len(bedroom_instances) == 3


def test_c_4_bedrooms_plus_safe_room_reaches_final_geometry_even_though_the_model_omitted_it():
    spec = _adapt(_RAW_4BR_SAFEROOM_REQUESTED)
    assert not any(item.room_type == "safe_room" for item in spec.program)

    request = _request(bedroom_state=RequirementState.known, bedroom_count=4, safe_room_state=RequirementState.known, safe_room_count=1)
    merged = merge_authoritative_requirements(spec, request)
    assert any(item.room_type == "safe_room" for item in merged.program)

    total_area = sum((item.target_area_m2 or 0) * item.count for item in merged.program)
    result = GeometrySolver().solve(merged, _generous_footprint(total_area))

    assert result.status == SolverStatus.satisfied
    safe_room_instances = [instance for instance in result.instances if instance.type.startswith("safe_room")]
    assert len(safe_room_instances) == 1
    bedroom_instances = [instance for instance in result.instances if instance.type.startswith("bedroom")]
    assert len(bedroom_instances) == 4


# --- D: bedrooms UNKNOWN upstream -> the model's invented count must never reach final geometry -------


def test_d_unknown_bedrooms_upstream_means_no_bedroom_in_final_geometry_despite_the_models_guess():
    spec = _adapt(_RAW_2BR)  # the model confidently predicted 2 bedrooms, unprompted about count
    assert any(item.room_type == "bedroom" and item.count == 2 for item in spec.program)

    request = _request(bedroom_state=RequirementState.unknown)
    merged = merge_authoritative_requirements(spec, request)
    assert not any(item.room_type == "bedroom" for item in merged.program)
    assert "bedroom" in merged.incomplete_requirements

    total_area = sum((item.target_area_m2 or 0) * item.count for item in merged.program)
    result = GeometrySolver().solve(merged, _generous_footprint(total_area))

    assert result.status == SolverStatus.satisfied
    assert not any(instance.type.startswith("bedroom") for instance in result.instances)


# --- E: model's circulation=[] must never fabricate an entry_room_type ------------------------------


def test_e_empty_model_circulation_never_fabricates_an_entry_room_and_solver_still_succeeds():
    spec = _adapt(_RAW_2BR)  # real trace's circulation is genuinely []
    request = _request(bedroom_state=RequirementState.known, bedroom_count=2)
    merged = merge_authoritative_requirements(spec, request)

    assert merged.circulation is None

    total_area = sum((item.target_area_m2 or 0) * item.count for item in merged.program)
    result = GeometrySolver().solve(merged, _generous_footprint(total_area))

    assert result.status == SolverStatus.satisfied
    assert not any(check.kind == "entry_perimeter_access" for check in result.hard_constraints_checked)


# --- F: unsupported relationship types are dropped end-to-end, never mistranslated -------------------


def test_f_door_connection_relationships_never_become_direct_access_in_the_final_merged_spec():
    spec = _adapt(_RAW_3BR_SAFEROOM_REQUESTED)  # real trace has 3 DOOR_CONNECTION relationships
    request = _request(bedroom_state=RequirementState.known, bedroom_count=3, safe_room_state=RequirementState.known, safe_room_count=1)
    merged = merge_authoritative_requirements(spec, request)

    from app.architect.models import DirectAccessConstraint

    # The ONLY direct_access relationship allowed to exist is the authoritative safe_room<->bedroom one
    # the merge itself adds — none may have come from a mistranslated DOOR_CONNECTION.
    direct_access_rels = [rel for rel in merged.relationships if isinstance(rel, DirectAccessConstraint)]
    assert len(direct_access_rels) == 1
    assert {direct_access_rels[0].room_type_a, direct_access_rels[0].room_type_b} == {"safe_room", "bedroom"}
    assert direct_access_rels[0].source == "USER_REQUIREMENT"
