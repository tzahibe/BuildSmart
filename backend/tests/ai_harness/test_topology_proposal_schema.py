"""AC-1: room IDENTITY vs ProgramRole, no geometry fields, dangling/duplicate id rejection."""
from __future__ import annotations

import pytest

from app.ai_harness.topology_poc.schema import (
    ENTRANCE_ID,
    SchemaViolationError,
    proposal_from_dict,
    validate_no_geometry,
)

_TWO_BEDROOMS_TWO_BATHROOMS = {
    "rooms": [
        {"id": "LIVING", "role": "LIVING"},
        {"id": "BEDROOM_1", "role": "BEDROOM"},
        {"id": "BEDROOM_2", "role": "BEDROOM"},
        {"id": "BATHROOM_1", "role": "BATHROOM"},
        {"id": "BATHROOM_2", "role": "BATHROOM"},
    ],
    "spatial_adjacency": [["BEDROOM_1", "BATHROOM_1"], ["BEDROOM_2", "BATHROOM_2"], ["LIVING", "BEDROOM_1"]],
    "access_graph": [[ENTRANCE_ID, "LIVING"], ["LIVING", "BEDROOM_1"], ["LIVING", "BEDROOM_2"],
                      ["BEDROOM_1", "BATHROOM_1"], ["BEDROOM_2", "BATHROOM_2"]],
    "zones": {"public": ["LIVING"], "private": ["BEDROOM_1", "BEDROOM_2"],
              "service": ["BATHROOM_1", "BATHROOM_2"], "circulation": []},
    "clusters": {"wet_core": ["BATHROOM_1", "BATHROOM_2"]},
    "design_tradeoff": "Two ensuite pairs, symmetric plan.",
}


def test_two_bedrooms_two_bathrooms_stay_distinct_end_to_end():
    proposal = proposal_from_dict(_TWO_BEDROOMS_TWO_BATHROOMS)
    assert {r.id for r in proposal.rooms} == {"LIVING", "BEDROOM_1", "BEDROOM_2", "BATHROOM_1", "BATHROOM_2"}
    assert proposal.role_by_id["BEDROOM_1"] == proposal.role_by_id["BEDROOM_2"] == "BEDROOM"
    assert proposal.role_by_id["BATHROOM_1"] == proposal.role_by_id["BATHROOM_2"] == "BATHROOM"
    # the two bedroom/bathroom pairs remain distinct EDGES, never collapsed to one role-pair node
    assert frozenset(("BEDROOM_1", "BATHROOM_1")) in proposal.spatial_adjacency
    assert frozenset(("BEDROOM_2", "BATHROOM_2")) in proposal.spatial_adjacency
    assert frozenset(("BEDROOM_1", "BATHROOM_2")) not in proposal.spatial_adjacency
    assert len(proposal.rooms) == 5


def test_no_geometry_field_anywhere_is_rejected():
    for bad_key in ("x", "width_m", "area_m2", "polygon", "wall"):
        raw = {**_TWO_BEDROOMS_TWO_BATHROOMS, "rooms": [
            {"id": "LIVING", "role": "LIVING", bad_key: 1.0},
        ]}
        with pytest.raises(SchemaViolationError):
            proposal_from_dict(raw)


def test_nested_geometry_field_is_rejected():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS,
           "relative_position": [{"room_id": "BEDROOM_1", "relation": "NORTH_OF",
                                   "reference_room_id": "BEDROOM_2", "coordinates": [1, 2]}]}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)


def test_validate_no_geometry_allows_the_legitimate_schema_fields():
    validate_no_geometry(_TWO_BEDROOMS_TWO_BATHROOMS)  # must not raise


def test_duplicate_room_id_rejected():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS,
           "rooms": [{"id": "BEDROOM_1", "role": "BEDROOM"}, {"id": "BEDROOM_1", "role": "BEDROOM"}]}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)


def test_invalid_role_rejected():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS,
           "rooms": [{"id": "BEDROOM_1", "role": "NOT_A_ROLE"}]}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)


def test_entrance_id_reserved_not_a_room():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS,
           "rooms": [{"id": ENTRANCE_ID, "role": "LIVING"}]}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)


def test_entrance_not_valid_in_spatial_adjacency():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS,
           "spatial_adjacency": [[ENTRANCE_ID, "LIVING"]]}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)


def test_dangling_room_id_in_access_graph_rejected():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS,
           "access_graph": [["LIVING", "GHOST_ROOM"]]}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)


def test_zones_key_must_be_valid():
    raw = {**_TWO_BEDROOMS_TWO_BATHROOMS, "zones": {"not_a_zone": ["LIVING"]}}
    with pytest.raises(SchemaViolationError):
        proposal_from_dict(raw)
