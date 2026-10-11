"""Issue #151 review follow-up (2026-10-01): the GO/STOP gate's median/average IMPROVEMENT must be
measured on `adjacency_similarity` (built ONLY from `spatial_touching`, AC-12) — the metric the
0.137503 threshold is itself a holdout standard deviation OF — never on `total_score`, which mixes
four differently-scaled components and is not in the threshold's units.

AC-26: a test proves `touching_without_door`'s 0.058796 cannot be substituted anywhere in the gate
computation. It loads the REAL committed `baseline.json` (never a hand-rolled fixture) and runs
`compute_go_stop_gate` against its real `primary_go_stop_gate` spec."""
from __future__ import annotations

import json

from app.ai_harness.topology_poc.build_primary_report import DEFAULT_BASELINE_JSON
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


def test_real_baseline_json_median_threshold_is_the_spatial_touching_stdev_not_the_forbidden_one():
    """Loads the REAL `docs/reports/llm-topology-poc/baseline.json` (not a fixture) and proves the
    gate it describes enforces `spatial_touching`'s holdout stdev (0.137503), never
    `touching_without_door`'s (0.058796, explicitly named `forbidden_substitute` in that same
    file)."""
    with open(DEFAULT_BASELINE_JSON, encoding="utf-8") as f:
        baseline = json.load(f)
    gate_spec = baseline["primary_go_stop_gate"]
    holdout_source = gate_spec["holdout_stdev_source"]

    assert gate_spec["go_requires_all_three"]["median_improvement_min"] == 0.137503
    assert holdout_source["holdout_stdev"] == 0.137503
    forbidden = holdout_source["forbidden_substitute"]
    assert forbidden["table"] == "touching_without_door"
    assert forbidden["stdev"] == 0.058796
    assert gate_spec["go_requires_all_three"]["median_improvement_min"] != forbidden["stdev"]


def test_real_baseline_json_gate_rejects_an_improvement_that_only_clears_the_forbidden_stdev():
    """An adjacency improvement of 0.08 clears `touching_without_door`'s forbidden 0.058796 but
    not `spatial_touching`'s real 0.137503. Running the REAL `baseline.json` gate_spec against it
    must still fail the median condition — proving the committed file's actual threshold, not the
    forbidden substitute, is what `compute_go_stop_gate` enforces end to end."""
    with open(DEFAULT_BASELINE_JSON, encoding="utf-8") as f:
        baseline = json.load(f)
    gate_spec = baseline["primary_go_stop_gate"]
    forbidden_stdev = gate_spec["holdout_stdev_source"]["forbidden_substitute"]["stdev"]
    real_stdev = gate_spec["go_requires_all_three"]["median_improvement_min"]
    improvement_above_forbidden_below_real = 0.08
    assert forbidden_stdev < improvement_above_forbidden_below_real < real_stdev

    results = {
        f"B{i:02d}": _brief(
            f"B{i:02d}", gen_adjacency=-1.0, gen_total=-1.0,
            llm_adjacency=-1.0 + improvement_above_forbidden_below_real, llm_total=1.0)
        for i in range(20)
    }
    gate = compute_go_stop_gate(results, gate_spec)
    assert gate.median_improvement == improvement_above_forbidden_below_real
    assert gate.verdict != "GO"
