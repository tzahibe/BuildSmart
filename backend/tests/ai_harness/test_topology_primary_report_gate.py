"""Issue #151 review follow-up (2026-10-01): the GO/STOP gate's median/average IMPROVEMENT must be
measured on `adjacency_similarity` (built ONLY from `spatial_touching`, AC-12) — the metric the
0.137503 threshold is itself a holdout standard deviation OF — never on `total_score`, which mixes
four differently-scaled components and is not in the threshold's units."""
from __future__ import annotations

from app.ai_harness.topology_poc.primary_report import compute_go_stop_gate
from app.ai_harness.topology_poc.result_types import BriefResult, ScoredProposal

_GATE_SPEC = {
    "go_requires_all_three": {
        "wins_fraction_min": 0.7,
        "median_improvement_min": 0.137503,
        "diversity_min_fraction_of_briefs_with_3plus_distinct": 0.5,
    },
}


def _score(*, adjacency, total, violations=()):
    return {
        "adjacency_similarity": adjacency, "access_similarity": -1.0, "wet_core_similarity": 1.0,
        "entrance_relation_score": None, "hard_violations": list(violations), "total_score": total,
    }


def _scored(*, adjacency, total, violations=()):
    return ScoredProposal(
        source="LLM", raw_index=0, realizability="UNKNOWN",
        score=_score(adjacency=adjacency, total=total, violations=violations),
        canonical_hash="h")


def _brief(brief_id, *, gen_adjacency, gen_total, llm_adjacency, llm_total, distinct=3):
    generator = ScoredProposal(
        source="CURRENT_GENERATOR", raw_index=0, realizability="UNKNOWN",
        score=_score(adjacency=gen_adjacency, total=gen_total), canonical_hash="g")
    llm = _scored(adjacency=llm_adjacency, total=llm_total)
    return BriefResult(
        brief_id=brief_id, source_key="k", bedrooms=2, wet_rooms=1, safe_room=False,
        open_plan=False, size_tier="medium", aspect_tier="square", generator=generator,
        generator_error=None, llm_proposals=(llm,), llm_raw_generated=1, llm_schema_rejected=0,
        llm_exact_duplicates=0, materially_distinct_count=distinct, llm_call_latency_s=None,
        llm_model="m")


def test_gate_improvement_uses_adjacency_similarity_not_total_score():
    # total_score improvement is huge (~16x the threshold); adjacency_similarity improvement alone
    # is tiny and below the 0.137503 bar — a real POC scenario (large wet_core/access swing,
    # negligible adjacency swing). A gate keyed on total_score would wrongly clear the bar.
    results = {"B01": _brief(
        "B01", gen_adjacency=-1.0, gen_total=-3.0, llm_adjacency=-0.95, llm_total=2.0)}
    gate = compute_go_stop_gate(results, _GATE_SPEC)
    assert gate.median_improvement == 0.05
    assert gate.median_improvement < _GATE_SPEC["go_requires_all_three"]["median_improvement_min"]


def test_gate_win_still_uses_total_score():
    # the LLM proposal is worse on adjacency_similarity but better on total_score overall -> still
    # a win (win_definition is the full blind critic), even though its adjacency improvement < 0.
    results = {"B01": _brief(
        "B01", gen_adjacency=-0.5, gen_total=-3.0, llm_adjacency=-0.8, llm_total=2.0)}
    gate = compute_go_stop_gate(results, _GATE_SPEC)
    assert gate.wins == 1
    assert gate.median_improvement == -0.3


def test_gate_excludes_briefs_with_no_measurable_adjacency_on_either_side():
    results = {
        "B01": _brief("B01", gen_adjacency=None, gen_total=-1.0, llm_adjacency=-0.9, llm_total=1.0),
        "B02": _brief("B02", gen_adjacency=-1.0, gen_total=-1.0, llm_adjacency=-0.8, llm_total=1.0),
    }
    gate = compute_go_stop_gate(results, _GATE_SPEC)
    # both briefs count as wins (total_score-based); only B02 contributes an improvement sample
    assert gate.wins == 2
    assert gate.median_improvement == 0.2
