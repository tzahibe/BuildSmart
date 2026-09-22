"""Verifies Issue #95 AC-1: on the fixture corpus, retrieval for each of the 3 benchmark briefs
returns 5-10 references with per-term scores and WHY, deterministic across runs, and never orders
by area alone.
"""
from __future__ import annotations

from tests.architectural_brain.benchmark_briefs import (
    BENCHMARK_BRIEFS,
    BENCHMARK_SITE,
    COMPACT_FAMILY,
    LARGE_TWO_WING,
    load_fixture_corpus,
)

from spikes.architectural_brain.retrieval import WEIGHTS, retrieve


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_each_benchmark_brief_retrieves_five_to_ten_references_with_scores_and_why():
    corpus = load_fixture_corpus()
    assert len(corpus) >= 10

    for brief in BENCHMARK_BRIEFS:
        results = retrieve(brief, BENCHMARK_SITE, corpus, k=8)
        assert 5 <= len(results) <= 10, f"{len(results)} references for {brief}"

        seen_ids = set()
        for ref in results:
            assert ref.plan_id not in seen_ids, "duplicate plan retrieved"
            seen_ids.add(ref.plan_id)
            assert ref.why and isinstance(ref.why, str)
            assert len(ref.term_scores) == len(WEIGHTS)
            for term in ref.term_scores:
                assert 0.0 <= term.score <= 1.0
                assert term.term in WEIGHTS
                assert abs(term.contribution - term.weight * term.score) < 1e-9
            expected_total = sum(t.contribution for t in ref.term_scores)
            assert abs(ref.total_score - expected_total) < 1e-9

        # sorted best-first
        scores = [r.total_score for r in results]
        assert scores == sorted(scores, reverse=True)


def test_retrieval_is_deterministic_across_runs():
    corpus = load_fixture_corpus()
    for brief in BENCHMARK_BRIEFS:
        first = retrieve(brief, BENCHMARK_SITE, corpus, k=8)
        second = retrieve(brief, BENCHMARK_SITE, corpus, k=8)
        assert [r.plan_id for r in first] == [r.plan_id for r in second]
        assert [r.total_score for r in first] == [r.total_score for r in second]


def test_same_area_different_programme_retrieves_a_different_top_three():
    """COMPACT_FAMILY and LARGE_TWO_WING both ask for target_built_area_m2=140 but differ in
    bedroom count, outline preference and circulation preference -- if retrieval only ordered by
    area, the two briefs would retrieve the identical top-3. They must not."""
    corpus = load_fixture_corpus()
    assert COMPACT_FAMILY.program.target_built_area_m2 == LARGE_TWO_WING.program.target_built_area_m2

    top_a = [r.plan_id for r in retrieve(COMPACT_FAMILY, BENCHMARK_SITE, corpus, k=8)[:3]]
    top_b = [r.plan_id for r in retrieve(LARGE_TWO_WING, BENCHMARK_SITE, corpus, k=8)[:3]]
    assert top_a != top_b


def test_area_only_ranking_would_disagree_with_actual_ranking():
    """A stronger version of the "not area alone" claim: rank the same corpus purely by closeness
    of footprint_area_m2 to the brief's target, and show retrieval's actual top-3 is not that
    ranking -- i.e. the other 8 terms genuinely move the outcome, not just tiebreak it."""
    corpus = load_fixture_corpus()
    brief = LARGE_TWO_WING
    target = brief.program.target_built_area_m2

    area_only_ranked = sorted(
        corpus, key=lambda e: (abs(e.plan_reference.derived.footprint_area_m2 - target),
                               e.plan_reference.plan_id)
    )
    area_only_top3 = [e.plan_reference.plan_id for e in area_only_ranked[:3]]

    actual_top3 = [r.plan_id for r in retrieve(brief, BENCHMARK_SITE, corpus, k=8)[:3]]
    assert actual_top3 != area_only_top3


def test_L_outline_brief_scores_two_wing_plans_higher_on_footprint_term():
    corpus = load_fixture_corpus()
    results = retrieve(LARGE_TWO_WING, BENCHMARK_SITE, corpus, k=10)
    two_wing_scores = [
        next(t for t in r.term_scores if t.term == "footprint_aspect_shape").score
        for r in results if r.pattern.circulation_class == "TWO_WING"
    ]
    other_scores = [
        next(t for t in r.term_scores if t.term == "footprint_aspect_shape").score
        for r in results if r.pattern.circulation_class != "TWO_WING"
    ]
    assert two_wing_scores, "expected at least one TWO_WING plan in the top 10"
    assert all(s >= 0.5 for s in two_wing_scores)
    if other_scores:
        assert sum(two_wing_scores) / len(two_wing_scores) > sum(other_scores) / len(other_scores)
