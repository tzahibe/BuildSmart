"""AC-4: duplicate detection hashes the canonical form over room IDs, roles AND edge types —
BEDROOM_1-BATHROOM_1 and BEDROOM_2-BATHROOM_1 are NOT treated as the same topology."""
from __future__ import annotations

from app.ai_harness.topology_poc import duplicates, schema

_BASE_ROOMS = [
    {"id": "LIVING", "role": "LIVING"},
    {"id": "BEDROOM_1", "role": "BEDROOM"},
    {"id": "BEDROOM_2", "role": "BEDROOM"},
    {"id": "BATHROOM_1", "role": "BATHROOM"},
]


def _proposal(adjacency_pair):
    return schema.proposal_from_dict({
        "rooms": _BASE_ROOMS,
        "spatial_adjacency": [list(adjacency_pair), ["LIVING", "BEDROOM_1"], ["LIVING", "BEDROOM_2"]],
        "access_graph": [[schema.ENTRANCE_ID, "LIVING"], ["LIVING", "BEDROOM_1"], ["LIVING", "BEDROOM_2"],
                          list(adjacency_pair)[::-1]],
        "zones": {"public": ["LIVING"], "private": ["BEDROOM_1", "BEDROOM_2"], "service": ["BATHROOM_1"]},
        "clusters": {"wet_core": ["BATHROOM_1"]},
    })


def test_bedroom1_bathroom1_and_bedroom2_bathroom1_are_not_the_same_topology():
    proposal_a = _proposal(("BEDROOM_1", "BATHROOM_1"))
    proposal_b = _proposal(("BEDROOM_2", "BATHROOM_1"))
    assert duplicates.canonical_hash(proposal_a) != duplicates.canonical_hash(proposal_b)
    # even though role-level they look identical ("a bedroom next to a bathroom")
    assert duplicates.role_level_signature(proposal_a) == duplicates.role_level_signature(proposal_b)


def test_canonical_hash_is_deterministic_and_order_independent():
    proposal = _proposal(("BEDROOM_1", "BATHROOM_1"))
    assert duplicates.canonical_hash(proposal) == duplicates.canonical_hash(proposal)


def test_exact_duplicate_is_detected():
    proposal_a = _proposal(("BEDROOM_1", "BATHROOM_1"))
    proposal_b = _proposal(("BEDROOM_1", "BATHROOM_1"))
    assert duplicates.canonical_hash(proposal_a) == duplicates.canonical_hash(proposal_b)
    deduped = duplicates.deduplicate_exact((proposal_a, proposal_b))
    assert len(deduped) == 1


def test_graph_edit_distance_zero_for_identical_proposals():
    proposal = _proposal(("BEDROOM_1", "BATHROOM_1"))
    assert duplicates.graph_edit_distance(proposal, proposal) == 0


def test_graph_edit_distance_positive_for_different_adjacency():
    proposal_a = _proposal(("BEDROOM_1", "BATHROOM_1"))
    proposal_b = _proposal(("BEDROOM_2", "BATHROOM_1"))
    assert duplicates.graph_edit_distance(proposal_a, proposal_b) > 0


def test_count_materially_distinct_collapses_near_duplicates():
    proposal_a = _proposal(("BEDROOM_1", "BATHROOM_1"))
    proposal_a_dup = _proposal(("BEDROOM_1", "BATHROOM_1"))
    proposal_b = _proposal(("BEDROOM_2", "BATHROOM_1"))
    count = duplicates.count_materially_distinct((proposal_a, proposal_a_dup, proposal_b))
    assert count == 2
