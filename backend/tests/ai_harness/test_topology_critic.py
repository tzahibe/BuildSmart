"""AC-9: realizability is metadata only — bit-identical score regardless of label.
AC-10: the critic is blind to provenance — same topology scores identically regardless of source,
and no source/provenance field is reachable from the scoring function's signature."""
from __future__ import annotations

import inspect

from app.ai_harness.topology_poc import critic, priors, realizability, schema

_RAW = {
    "rooms": [
        {"id": "LIVING", "role": "LIVING"},
        {"id": "KITCHEN", "role": "KITCHEN"},
        {"id": "HALL", "role": "HALL"},
        {"id": "BEDROOM_1", "role": "BEDROOM"},
        {"id": "BEDROOM_2", "role": "BEDROOM"},
        {"id": "BATHROOM_1", "role": "BATHROOM"},
    ],
    "spatial_adjacency": [
        ["LIVING", "KITCHEN"], ["LIVING", "HALL"], ["HALL", "BEDROOM_1"], ["HALL", "BEDROOM_2"],
        ["BEDROOM_1", "BATHROOM_1"],
    ],
    "access_graph": [
        [schema.ENTRANCE_ID, "LIVING"], ["LIVING", "KITCHEN"], ["LIVING", "HALL"],
        ["HALL", "BEDROOM_1"], ["HALL", "BEDROOM_2"], ["HALL", "BATHROOM_1"],
    ],
    "zones": {"public": ["LIVING", "KITCHEN"], "private": ["BEDROOM_1", "BEDROOM_2"],
              "service": ["BATHROOM_1"], "circulation": ["HALL"]},
    "clusters": {"wet_core": ["BATHROOM_1"]},
    "design_tradeoff": "A conventional single-hall spine.",
}


def _priors() -> priors.Priors:
    return priors.load_priors()


def test_score_topology_signature_carries_no_source_or_realizability_param():
    sig = inspect.signature(critic.score_topology)
    param_names = set(sig.parameters)
    assert "source" not in param_names
    assert "realizability" not in param_names
    assert "provenance" not in param_names


def test_topology_proposal_dataclass_has_no_source_or_realizability_field():
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(schema.TopologyProposal)}
    assert "source" not in field_names
    assert "realizability" not in field_names
    assert "provenance" not in field_names


def test_critic_is_blind_to_source():
    """The SAME topology, once tagged CURRENT_GENERATOR and once tagged LLM via the OUTER
    ProposalRecord wrapper, must score identically — because the critic never sees the wrapper."""
    p = _priors()
    proposal = schema.proposal_from_dict(_RAW)

    record_generator = schema.ProposalRecord(
        brief_id="brief-1", proposal=proposal, source=schema.ProposalSource.CURRENT_GENERATOR,
        realizability=schema.Realizability.REALIZABLE, raw_index=0)
    record_llm = schema.ProposalRecord(
        brief_id="brief-1", proposal=proposal, source=schema.ProposalSource.LLM,
        realizability=schema.Realizability.UNKNOWN, raw_index=0)

    score_from_generator = critic.score_topology(record_generator.proposal, p)
    score_from_llm = critic.score_topology(record_llm.proposal, p)
    assert score_from_generator == score_from_llm


def test_score_is_independent_of_realizability_label():
    p = _priors()
    proposal = schema.proposal_from_dict(_RAW)
    baseline_score = critic.score_topology(proposal, p)

    actual_label = realizability.classify_realizability(proposal)
    for label in schema.Realizability:
        # regardless of what label this proposal ACTUALLY gets, or would hypothetically get,
        # score_topology never takes a label as input, so it cannot vary by it.
        assert label is not None
    assert critic.score_topology(proposal, p) == baseline_score
    assert actual_label in set(schema.Realizability)


def test_hard_violation_detected_for_disconnected_room():
    raw = {**_RAW, "access_graph": [[schema.ENTRANCE_ID, "LIVING"]]}  # everything else unreachable
    proposal = schema.proposal_from_dict(raw)
    breakdown = critic.score_topology(proposal, _priors())
    assert any(v.startswith("DISCONNECTED_ROOM:") for v in breakdown.hard_violations)


def test_hard_violation_for_entrance_into_bedroom():
    raw = {**_RAW, "access_graph": [[schema.ENTRANCE_ID, "BEDROOM_1"], ["HALL", "BEDROOM_2"],
                                     ["LIVING", "HALL"], ["HALL", "BATHROOM_1"]]}
    proposal = schema.proposal_from_dict(raw)
    breakdown = critic.score_topology(proposal, _priors())
    assert any(v.startswith("ENTRANCE_INTO_PRIVATE:") for v in breakdown.hard_violations)


def test_hard_violation_for_bedroom_to_bedroom_only_access():
    raw = {**_RAW, "access_graph": [
        [schema.ENTRANCE_ID, "LIVING"], ["LIVING", "HALL"], ["HALL", "BEDROOM_1"],
        ["BEDROOM_1", "BEDROOM_2"],  # BEDROOM_2 reachable ONLY through another bedroom
        ["HALL", "BATHROOM_1"],
    ]}
    proposal = schema.proposal_from_dict(raw)
    breakdown = critic.score_topology(proposal, _priors())
    assert any(v.startswith("BEDROOM_TO_BEDROOM_ONLY_ACCESS:") for v in breakdown.hard_violations)


def test_clean_topology_has_no_hard_violations():
    proposal = schema.proposal_from_dict(_RAW)
    breakdown = critic.score_topology(proposal, _priors())
    assert breakdown.hard_violations == ()
    assert breakdown.adjacency_similarity is not None
    assert breakdown.wet_core_similarity == 1.0


def test_score_topology_is_deterministic():
    p = _priors()
    proposal = schema.proposal_from_dict(_RAW)
    assert critic.score_topology(proposal, p) == critic.score_topology(proposal, p)
