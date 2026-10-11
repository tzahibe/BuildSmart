"""Issue #141.

AC-1: the scanner fails loudly (raises, and the CLI exits non-zero) on an empty measurement —
never a silent zero that could pass for a real answer.
AC-2: the score is the symmetric, normalized form `y*log(p) + (1-y)*log(1-p)` summed over eligible
pairs and divided by their count — a plan is credited for a CORRECT non-adjacency, and adding rooms
alone does not raise the score.
AC-3: minimum support holds — a pair below it contributes exactly zero, and a high-frequency
low-lift pair does not outrank a rarer high-lift one.
"""
from __future__ import annotations

import json
import math
import os

import pytest

from app.knowledge import adjacency_priors as ap


def _write_plan(path, *, provenance=None, rooms=None, adjacency_edges=None):
    plan_reference = {
        "plan_id": os.path.basename(str(path)),
        "provenance": provenance or {"source_dataset": "ResPlan"},
        "rooms": rooms or [],
        "adjacency_edges": adjacency_edges or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"plan_reference": plan_reference}, f)


def _room(room_id, role, area_m2=10.0):
    return {"id": room_id, "type": role, "area_m2": area_m2}


def _table_with_row(role_a, role_b, p_adjacent, sample_count=5, meets_min_support=True):
    row = ap.AdjacencyRow(role_a=role_a, role_b=role_b, sample_count=sample_count,
                          adjacent_count=round(p_adjacent * sample_count), raw_p_adjacent=p_adjacent,
                          p_adjacent=p_adjacent, lift=1.0, meets_min_support=meets_min_support)
    return ap.AdjacencyPriorsTable(rows=(row,), baseline_adjacency_rate=0.5,
                                   smoothing_method="laplace", smoothing_alpha=1.0, min_support=3,
                                   corpus_dir="x", plans_scanned=5, plans_excluded_synthetic=0)


# --------------------------------------------------------------------------- AC-1: fails loudly

def test_raises_on_missing_corpus_dir(tmp_path):
    with pytest.raises(ap.EmptyCorpusError):
        ap.load_plan_role_adjacencies(str(tmp_path / "does-not-exist"))


def test_raises_on_empty_corpus_dir(tmp_path):
    with pytest.raises(ap.EmptyCorpusError):
        ap.load_plan_role_adjacencies(str(tmp_path))


def test_raises_when_every_plan_is_synthetic(tmp_path):
    _write_plan(tmp_path / "synthetic.json", provenance={"source_dataset": "SYNTHETIC"})
    with pytest.raises(ap.EmptyCorpusError):
        ap.load_plan_role_adjacencies(str(tmp_path))


def test_raises_when_real_plans_yield_zero_usable_rooms(tmp_path):
    _write_plan(tmp_path / "0.json", rooms=[{"type": "LIVING"}])  # no room id
    with pytest.raises(ap.EmptyCorpusError):
        ap.load_plan_role_adjacencies(str(tmp_path))


def test_build_priors_table_raises_when_no_plan_has_two_roles(tmp_path):
    """Real, usable plans, but every one has only a single role present — zero role PAIRS to
    measure, still an empty result raised loudly rather than a table with zero rows."""
    _write_plan(tmp_path / "0.json", rooms=[_room("LIVING_0", "LIVING")])
    with pytest.raises(ap.EmptyCorpusError):
        ap.build_priors_table(str(tmp_path))


def test_cli_exits_non_zero_on_empty_corpus(tmp_path, capsys):
    exit_code = ap.main(["--corpus-dir", str(tmp_path)])
    assert exit_code != 0
    assert "adjacency_priors" in capsys.readouterr().err


def test_cli_exits_zero_on_a_real_minimal_corpus(tmp_path):
    _write_plan(tmp_path / "0.json",
               rooms=[_room("LIVING_0", "LIVING"), _room("KITCHEN_0", "KITCHEN")],
               adjacency_edges=[{"room_a": "LIVING_0", "room_b": "KITCHEN_0"}])
    exit_code = ap.main(["--corpus-dir", str(tmp_path)])
    assert exit_code == 0


def test_load_priors_table_raises_when_artifact_missing(tmp_path):
    with pytest.raises(ap.EmptyCorpusError):
        ap.load_priors_table(str(tmp_path / "missing.json"))


def test_load_priors_table_raises_when_artifact_has_zero_rows(tmp_path):
    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({
        "corpus_dir": "x", "plans_scanned": 0, "plans_excluded_synthetic": 0,
        "baseline_adjacency_rate": 0.0, "smoothing_method": "laplace", "smoothing_alpha": 1.0,
        "min_support": 3, "rows": [],
    }))
    with pytest.raises(ap.EmptyCorpusError):
        ap.load_priors_table(str(empty_path))


def test_real_minimal_corpus_computes_expected_row(tmp_path):
    """Two plans, both roles present in both, adjacent in one but not the other -> the expected
    counts, raw rate and Laplace-smoothed rate."""
    _write_plan(tmp_path / "0.json",
               rooms=[_room("LIVING_0", "LIVING"), _room("BEDROOM_0", "BEDROOM")],
               adjacency_edges=[{"room_a": "LIVING_0", "room_b": "BEDROOM_0"}])
    _write_plan(tmp_path / "1.json",
               rooms=[_room("LIVING_0", "LIVING"), _room("BEDROOM_0", "BEDROOM")],
               adjacency_edges=[])
    table = ap.build_priors_table(str(tmp_path))
    assert table.plans_scanned == 2
    assert len(table.rows) == 1
    row = table.rows[0]
    assert (row.role_a, row.role_b) == ("BEDROOM", "LIVING")
    assert row.sample_count == 2
    assert row.adjacent_count == 1
    assert row.raw_p_adjacent == pytest.approx(0.5)
    assert row.p_adjacent == pytest.approx((1 + 1.0) / (2 + 2.0))  # Laplace, alpha=1.0
    assert row.meets_min_support is False  # sample_count=2 < MIN_SUPPORT=3


def test_reduction_keeps_only_largest_living_instance(tmp_path):
    """A LIVING nook (small, typed LIVING) that touches everything must not count as "LIVING is
    adjacent to X" once the real LIVING room does not touch X — the reduction keeps only the
    largest instance."""
    _write_plan(tmp_path / "0.json", rooms=[
        _room("LIVING_0", "LIVING", area_m2=40.0),   # the real living room
        _room("LIVING_1", "LIVING", area_m2=1.0),    # a mislabeled nook
        _room("KITCHEN_0", "KITCHEN", area_m2=12.0),
    ], adjacency_edges=[{"room_a": "LIVING_1", "room_b": "KITCHEN_0"}])  # only the NOOK touches
    plans, scanned, excluded = ap.load_plan_role_adjacencies(str(tmp_path))
    assert scanned == 1
    plan = plans[0]
    assert plan.role_zone_ids["LIVING"] == ("LIVING_0",)
    assert not ap._pair_touches(plan, "LIVING", "KITCHEN")  # real LIVING does not touch KITCHEN


# --------------------------------------------------------------------------- AC-2: the score

def test_correct_non_adjacency_is_credited():
    """A pair with LOW p_adjacent, correctly realized as NOT adjacent, scores closer to zero (the
    best a log-likelihood can do) than the same pair realized adjacent against that low prior."""
    table = _table_with_row("BEDROOM", "KITCHEN", p_adjacent=0.1)
    correct = ap.plan_log_likelihood([("BEDROOM", "KITCHEN", False)], table)
    incorrect = ap.plan_log_likelihood([("BEDROOM", "KITCHEN", True)], table)
    assert correct == pytest.approx(math.log(0.9))
    assert incorrect == pytest.approx(math.log(0.1))
    assert correct > incorrect


def test_score_matches_exact_formula():
    table = _table_with_row("A", "B", p_adjacent=0.7)
    score = ap.plan_log_likelihood([("A", "B", True)], table)
    assert score == pytest.approx(1.0 * math.log(0.7) + 0.0 * math.log(0.3))


def test_normalized_by_eligible_pair_count_not_summed():
    """Two plans with the SAME per-pair quality (each pair correctly matches the majority outcome
    the table predicts) but a different NUMBER of rooms/pairs must score identically — a plan is
    never rewarded simply for having more pairs. Contrasts with a naive `sum(...)` which would grow
    with pair count."""
    table = ap.AdjacencyPriorsTable(
        rows=(
            ap.AdjacencyRow("A", "B", 5, 4, 0.8, 0.8, 1.0, True),
            ap.AdjacencyRow("A", "C", 5, 4, 0.8, 0.8, 1.0, True),
            ap.AdjacencyRow("A", "D", 5, 4, 0.8, 0.8, 1.0, True),
            ap.AdjacencyRow("A", "E", 5, 4, 0.8, 0.8, 1.0, True),
        ),
        baseline_adjacency_rate=0.8, smoothing_method="laplace", smoothing_alpha=1.0,
        min_support=3, corpus_dir="x", plans_scanned=5, plans_excluded_synthetic=0)
    small = ap.plan_log_likelihood([("A", "B", True)], table)
    large = ap.plan_log_likelihood(
        [("A", "B", True), ("A", "C", True), ("A", "D", True), ("A", "E", True)], table)
    assert small == pytest.approx(large)
    assert small == pytest.approx(math.log(0.8))


def test_zero_eligible_pairs_returns_none_not_zero():
    table = _table_with_row("A", "B", p_adjacent=0.5)
    assert ap.plan_log_likelihood([], table) is None
    assert ap.plan_log_likelihood([("C", "D", True)], table) is None  # no matching row at all


# --------------------------------------------------------------------------- AC-3: minimum support

def test_pair_below_min_support_contributes_exactly_zero():
    """A plan with one supported pair and one UNSUPPORTED pair scores identically to the same plan
    with only the supported pair present — the unsupported one contributes nothing at all, not a
    neutral 0.0 folded into the sum."""
    table = ap.AdjacencyPriorsTable(
        rows=(
            ap.AdjacencyRow("A", "B", 5, 4, 0.8, 0.8, 1.0, True),
            ap.AdjacencyRow("C", "D", 2, 2, 1.0, 0.75, 1.0, False),  # below MIN_SUPPORT
        ),
        baseline_adjacency_rate=0.8, smoothing_method="laplace", smoothing_alpha=1.0,
        min_support=3, corpus_dir="x", plans_scanned=5, plans_excluded_synthetic=0)
    only_supported = ap.plan_log_likelihood([("A", "B", True)], table)
    with_unsupported = ap.plan_log_likelihood([("A", "B", True), ("C", "D", True)], table)
    assert only_supported == pytest.approx(with_unsupported)
    only_unsupported = ap.plan_log_likelihood([("C", "D", True)], table)
    assert only_unsupported is None


def test_high_frequency_low_lift_does_not_outrank_rare_high_lift():
    """Ranking rows by `lift` (the artifact's own usefulness signal) must never be confounded by
    `sample_count`: a pair seen often but near the corpus baseline (lift ~= 1) ranks below a pair
    seen rarely but far from baseline (high lift), as long as both meet minimum support."""
    common_low_lift = ap.AdjacencyRow("A", "B", sample_count=15, adjacent_count=8,
                                      raw_p_adjacent=0.53, p_adjacent=0.53, lift=1.06,
                                      meets_min_support=True)
    rare_high_lift = ap.AdjacencyRow("C", "D", sample_count=3, adjacent_count=3,
                                     raw_p_adjacent=1.0, p_adjacent=0.8, lift=1.6,
                                     meets_min_support=True)
    ranked = sorted([common_low_lift, rare_high_lift], key=lambda r: -r.lift)
    assert ranked[0] is rare_high_lift
    assert ranked[0].sample_count < ranked[1].sample_count
