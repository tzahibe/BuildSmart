"""Direct coverage of `classify_realizability` (Issue #151 review follow-up, 2026-10-01).

The owner correction in `realizability.py` removed the rule that labelled a proposal
NOT_REALIZABLE whenever its wet rooms were not all in one `wet_core` cluster — multi-cluster wet
rooms are a normal engine outcome, not a realization blocker. These tests prove the NEW behaviour
directly (nothing previously exercised this rule at all, `test_topology_critic.py`'s own test only
proves the SCORE is independent of whatever label is assigned, never what label classification
assigns)."""
from __future__ import annotations

from app.ai_harness.topology_poc import realizability, schema

_BASE_ROOMS = [
    {"id": "LIVING", "role": "LIVING"},
    {"id": "HALL", "role": "HALL"},
    {"id": "BEDROOM_1", "role": "BEDROOM"},
    {"id": "BATHROOM_1", "role": "BATHROOM"},
    {"id": "BATHROOM_2", "role": "BATHROOM"},
]

#: Wet rooms (BATHROOM_1, BATHROOM_2) deliberately split into two separate clusters — the exact
#: shape the removed rule used to reject. Circulation is a single HALL serving the one private
#: room, and the entrance opens into the public LIVING room, so no OTHER rule in
#: `classify_realizability` fires either.
_RAW_TWO_WET_CLUSTERS = {
    "rooms": _BASE_ROOMS,
    "spatial_adjacency": [
        ["LIVING", "HALL"], ["HALL", "BEDROOM_1"], ["BEDROOM_1", "BATHROOM_1"],
        ["LIVING", "BATHROOM_2"],
    ],
    "access_graph": [
        [schema.ENTRANCE_ID, "LIVING"], ["LIVING", "HALL"], ["HALL", "BEDROOM_1"],
        ["BEDROOM_1", "BATHROOM_1"], ["LIVING", "BATHROOM_2"],
    ],
    "zones": {"public": ["LIVING"], "private": ["BEDROOM_1"],
              "service": ["BATHROOM_1", "BATHROOM_2"], "circulation": ["HALL"]},
    "clusters": {"wet_core_1": ["BATHROOM_1"], "wet_core_2": ["BATHROOM_2"]},
    "design_tradeoff": "Two wet rooms in two separate clusters, nowhere near the hall.",
}


def test_wet_rooms_in_two_clusters_is_realizable_not_a_blocker():
    proposal = schema.proposal_from_dict(_RAW_TWO_WET_CLUSTERS)
    assert proposal.clusters["wet_core_1"] != proposal.clusters["wet_core_2"]
    assert realizability.classify_realizability(proposal) == schema.Realizability.REALIZABLE


def test_classification_does_not_read_clusters_at_all():
    """The fix is a removal, not a relaxation: swapping the wet-room cluster assignment around
    (merging them into one cluster, or deleting `clusters` entirely) must not change the verdict —
    `clusters` is simply never consulted by this function any more."""
    proposal = schema.proposal_from_dict(_RAW_TWO_WET_CLUSTERS)
    merged = {**_RAW_TWO_WET_CLUSTERS, "clusters": {"wet_core": ["BATHROOM_1", "BATHROOM_2"]}}
    merged_proposal = schema.proposal_from_dict(merged)
    no_clusters = {**_RAW_TWO_WET_CLUSTERS, "clusters": {}}
    no_clusters_proposal = schema.proposal_from_dict(no_clusters)

    verdict = realizability.classify_realizability(proposal)
    assert realizability.classify_realizability(merged_proposal) == verdict
    assert realizability.classify_realizability(no_clusters_proposal) == verdict


def test_still_not_realizable_when_circulation_serves_more_than_one_hub():
    raw = {**_RAW_TWO_WET_CLUSTERS, "rooms": _BASE_ROOMS + [{"id": "HALL_2", "role": "HALL"}]}
    proposal = schema.proposal_from_dict(raw)
    assert realizability.classify_realizability(proposal) == schema.Realizability.NOT_REALIZABLE


def test_still_not_realizable_when_entrance_opens_directly_into_a_private_room():
    raw = {
        **_RAW_TWO_WET_CLUSTERS,
        "access_graph": [
            [schema.ENTRANCE_ID, "BEDROOM_1"], ["LIVING", "HALL"], ["HALL", "BEDROOM_1"],
            ["BEDROOM_1", "BATHROOM_1"], ["LIVING", "BATHROOM_2"],
        ],
    }
    proposal = schema.proposal_from_dict(raw)
    assert realizability.classify_realizability(proposal) == schema.Realizability.NOT_REALIZABLE


def test_still_not_realizable_when_a_private_room_is_unserved_by_the_hub():
    raw = {
        **_RAW_TWO_WET_CLUSTERS,
        "rooms": _BASE_ROOMS + [{"id": "BEDROOM_2", "role": "BEDROOM"}],
        "spatial_adjacency": _RAW_TWO_WET_CLUSTERS["spatial_adjacency"] + [["LIVING", "BEDROOM_2"]],
        "access_graph": _RAW_TWO_WET_CLUSTERS["access_graph"],
        "zones": {**_RAW_TWO_WET_CLUSTERS["zones"], "private": ["BEDROOM_1", "BEDROOM_2"]},
    }
    proposal = schema.proposal_from_dict(raw)
    # BEDROOM_2 is a declared room but never reachable from HALL in access_graph.
    assert realizability.classify_realizability(proposal) == schema.Realizability.NOT_REALIZABLE


def test_unknown_when_no_circulation_role_but_private_rooms_exist():
    raw = {
        "rooms": [{"id": "LIVING", "role": "LIVING"}, {"id": "BEDROOM_1", "role": "BEDROOM"}],
        "spatial_adjacency": [["LIVING", "BEDROOM_1"]],
        "access_graph": [[schema.ENTRANCE_ID, "LIVING"], ["LIVING", "BEDROOM_1"]],
        "zones": {"public": ["LIVING"], "private": ["BEDROOM_1"]},
        "clusters": {},
        "design_tradeoff": "No HALL/CIRCULATION room at all.",
    }
    proposal = schema.proposal_from_dict(raw)
    assert realizability.classify_realizability(proposal) == schema.Realizability.UNKNOWN
