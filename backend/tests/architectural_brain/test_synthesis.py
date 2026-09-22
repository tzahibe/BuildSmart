"""Verifies Issue #95 AC-2: synthesis produces 2-3 pairwise topologically distinct ConceptSpecs
per benchmark brief, each citing >= 2 references with pattern_used and why, and every
authoritative requirement of the brief is present in every candidate.
"""
from __future__ import annotations

import pytest

from tests.architectural_brain.benchmark_briefs import BENCHMARK_BRIEFS, BENCHMARK_SITE, load_fixture_corpus

from spikes.architectural_brain.retrieval import retrieve
from spikes.architectural_brain.synthesis import synthesize, topologically_distinct


def _synthesize_for(brief):
    corpus = load_fixture_corpus()
    references = retrieve(brief, BENCHMARK_SITE, corpus, k=8)
    return synthesize(brief, references)


@pytest.mark.parametrize("brief", BENCHMARK_BRIEFS, ids=["compact_family", "large_two_wing", "hub_lobby_open_plan"])
def test_two_or_three_pairwise_distinct_candidates(brief):
    candidates = _synthesize_for(brief)
    assert 2 <= len(candidates) <= 3

    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            assert topologically_distinct(a, b), (
                f"{a.concept_id} and {b.concept_id} are not topologically distinct: "
                f"both are ({a.circulation_class}, {a.zoning}, {a.wet_core_strategy})"
            )


@pytest.mark.parametrize("brief", BENCHMARK_BRIEFS, ids=["compact_family", "large_two_wing", "hub_lobby_open_plan"])
def test_every_candidate_cites_at_least_two_references_with_pattern_used_and_why(brief):
    candidates = _synthesize_for(brief)
    for candidate in candidates:
        plan_ids = {ref.plan_id for ref in candidate.references}
        assert len(plan_ids) >= 2, f"{candidate.concept_id} cites only {plan_ids}"
        for ref in candidate.references:
            assert ref.pattern_used
            assert ref.why


@pytest.mark.parametrize("brief", BENCHMARK_BRIEFS, ids=["compact_family", "large_two_wing", "hub_lobby_open_plan"])
def test_every_authoritative_requirement_present_in_every_candidate(brief):
    candidates = _synthesize_for(brief)
    expected_kinds = tuple(k.kind.value for k in brief.program.wet_room_kinds)
    for candidate in candidates:
        assert candidate.bedrooms == brief.program.bedrooms
        assert candidate.safe_room == brief.program.safe_room
        assert candidate.wet_rooms == brief.program.wet_rooms
        assert candidate.wet_room_kinds == expected_kinds
        assert candidate.stories == brief.stories


def test_a_synthesized_concept_is_never_a_single_references_pattern_set():
    """Every axis-donor citation in `references` must come from >= 2 distinct plan_ids -- i.e. no
    candidate's circulation_class/zoning/wet_core_strategy/entrance_relationship/bedroom_grouping
    are ALL sourced from the one primary reference."""
    for brief in BENCHMARK_BRIEFS:
        for candidate in _synthesize_for(brief):
            used_plan_ids = {ref.plan_id for ref in candidate.references}
            assert len(used_plan_ids) >= 2


def test_synthesize_requires_at_least_two_references():
    with pytest.raises(ValueError):
        synthesize(BENCHMARK_BRIEFS[0], [])
