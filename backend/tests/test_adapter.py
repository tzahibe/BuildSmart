"""Tests for `app/architect/adapter.py` — using REAL captured Architect Model V1 output (not synthetic
text) wherever possible: `_REAL_CASE_1_RAW_JSON` is byte-for-byte what the actual accepted model (base
Qwen2.5-Coder-7B-Instruct + the accepted LoRA adapter) generated for a real "2 bedroom" request during
this integration's own verification run — not hand-written, not from the fine-tuning project's holdout
set. Synthetic `ModelRelationship` objects are used only for the two relationship kinds (WINDOW_CONNECTION,
NEAR) that didn't happen to appear in the real traces captured so far, but are part of the model's own
documented vocabulary (`app/architect/model_schema.py`'s `ModelRelationshipType`).
"""

import json

from app.architect.adapter import adapt_model_spec, model_room_type_for
from app.architect.model_schema import (
    ModelArchitecturalSpec,
    ModelRelationship,
    ModelRelationshipType,
    ModelRoomType,
)
from app.architect.models import AdjacencyConstraint, ConstraintSeverity, DirectAccessConstraint

# Real raw output captured from the actual accepted model for a "2 bedroom, 70 m2, residential" request.
_REAL_CASE_1_RAW_JSON = """
{"program": [{"type": "BALCONY", "count": 1, "area_per_room_m2": 3.5, "zone": "OUTDOOR"}, {"type": "BATHROOM", "count": 1, "area_per_room_m2": 9.0, "zone": "SERVICE"}, {"type": "BEDROOM", "count": 2, "area_per_room_m2": 14.0, "zone": "PRIVATE"}, {"type": "KITCHEN", "count": 1, "area_per_room_m2": 6.0, "zone": "SERVICE"}, {"type": "LIVING", "count": 1, "area_per_room_m2": 23.0, "zone": "PUBLIC"}], "zones": [{"type": "OUTDOOR", "room_types": ["BALCONY"]}, {"type": "SERVICE", "room_types": ["BATHROOM", "KITCHEN"]}, {"type": "PRIVATE", "room_types": ["BEDROOM"]}, {"type": "PUBLIC", "room_types": ["LIVING"]}], "relationships": [{"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BALCONY", "b_type": "BEDROOM", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BATHROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "BEDROOM", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "KITCHEN", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "BEDROOM", "b_type": "LIVING", "relationship": "DOOR_CONNECTION", "source_type": "OBSERVED_GEOMETRY"}, {"a_type": "KITCHEN", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}], "circulation": []}
"""


def _real_case_1() -> ModelArchitecturalSpec:
    return ModelArchitecturalSpec.model_validate(json.loads(_REAL_CASE_1_RAW_JSON))


def test_room_types_are_renamed_into_buildsmarts_snake_case_vocabulary():
    result = adapt_model_spec(_real_case_1())

    room_types = {item.room_type for item in result.spec.program}
    assert room_types == {"balcony", "bathroom", "bedroom", "kitchen", "living_room"}


def test_living_maps_to_exactly_living_room_not_living():
    # frontend/src/design/SketchSvg.tsx hardcodes `room.type === 'living_room'` to find the ground-floor
    # entry-door anchor room — any other casing/naming would silently break that.
    assert model_room_type_for("living_room") == ModelRoomType.LIVING


def test_program_items_and_relationships_are_tagged_model_inference():
    result = adapt_model_spec(_real_case_1())

    assert all(item.source == "MODEL_INFERENCE" for item in result.spec.program)
    assert all(rel.source == "MODEL_INFERENCE" for rel in result.spec.relationships)


def test_area_per_room_m2_is_renamed_to_target_area_m2():
    result = adapt_model_spec(_real_case_1())

    bedroom = next(item for item in result.spec.program if item.room_type == "bedroom")
    assert bedroom.target_area_m2 == 14.0
    assert bedroom.min_area_m2 is None
    assert bedroom.max_area_m2 is None
    assert bedroom.min_width_m is None


def test_zones_are_renamed_from_the_zone_type_enum():
    result = adapt_model_spec(_real_case_1())

    zone_names = {zone.name for zone in result.spec.zones}
    assert zone_names == {"outdoor", "service", "private", "public"}
    private_zone = next(zone for zone in result.spec.zones if zone.name == "private")
    assert private_zone.room_types == ["bedroom"]


def test_adjacent_relationships_become_soft_adjacency_constraints():
    result = adapt_model_spec(_real_case_1())

    kitchen_living = [
        rel
        for rel in result.spec.relationships
        if isinstance(rel, AdjacencyConstraint) and {rel.room_type_a, rel.room_type_b} == {"kitchen", "living_room"}
    ]
    assert len(kitchen_living) == 1
    assert kitchen_living[0].severity == ConstraintSeverity.soft


def test_door_connection_relationships_are_dropped_with_a_diagnostic_never_mistranslated():
    result = adapt_model_spec(_real_case_1())

    # The real trace has 3 DOOR_CONNECTION entries — none should survive as any BuildSmart kind.
    assert not any(isinstance(rel, DirectAccessConstraint) for rel in result.spec.relationships)
    door_connection_diagnostics = [d for d in result.diagnostics if "DOOR_CONNECTION" in d]
    assert len(door_connection_diagnostics) == 3


def test_self_relationship_is_dropped_with_a_diagnostic():
    # The real trace includes {"a_type": "BEDROOM", "b_type": "BEDROOM", "relationship": "ADJACENT"} —
    # BuildSmart's relational constraints require two distinct room types (there's no single "bedroom"
    # instance a type-to-type relationship could refer to when there are multiple).
    result = adapt_model_spec(_real_case_1())

    assert not any(rel.room_type_a == rel.room_type_b for rel in result.spec.relationships)
    assert any("self-relationship" in d for d in result.diagnostics)


def test_window_connection_and_near_are_also_dropped_with_diagnostics():
    # Real captures so far never happened to include these, but they're part of the model's own
    # documented vocabulary (model_schema.py's ModelRelationshipType) and must be handled the same way.
    model_spec = ModelArchitecturalSpec(
        program=_real_case_1().program,
        zones=_real_case_1().zones,
        relationships=[
            ModelRelationship(a_type=ModelRoomType.KITCHEN, b_type=ModelRoomType.LIVING, relationship=ModelRelationshipType.WINDOW_CONNECTION),
            ModelRelationship(a_type=ModelRoomType.KITCHEN, b_type=ModelRoomType.LIVING, relationship=ModelRelationshipType.NEAR),
        ],
        circulation=[],
    )

    result = adapt_model_spec(model_spec)

    assert result.spec.relationships == []
    assert any("WINDOW_CONNECTION" in d for d in result.diagnostics)
    assert any("NEAR" in d for d in result.diagnostics)


def test_circulation_is_always_none_never_derived_from_the_models_circulation_list():
    model_spec = ModelArchitecturalSpec(
        program=_real_case_1().program,
        zones=_real_case_1().zones,
        relationships=[],
        circulation=[ModelRoomType.STAIRCASE],
    )

    result = adapt_model_spec(model_spec)

    assert result.spec.circulation is None
    assert any("circulation list" in d for d in result.diagnostics)


def test_empty_circulation_list_produces_no_diagnostic_about_it():
    result = adapt_model_spec(_real_case_1())  # real trace's circulation is []

    assert result.spec.circulation is None
    assert not any("circulation list" in d for d in result.diagnostics)


def test_safe_room_has_no_model_room_type_at_all():
    assert model_room_type_for("safe_room") is None
