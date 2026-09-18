"""The architectural-quality REGRESSION tier (Issue #17): the M1–M6 corpus summary over the
frozen PLANNED contexts, checked against a committed baseline (`quality_baseline.json`, produced
by `freeze_quality_baseline.py`). A NO-REGRESSION bar, not a new absolute one — the measured gaps
against 21 professional plans (hall spine aspect, wet adjacency, strip-shaped public rooms) are
real and unresolved; this test only catches a FUTURE change quietly making them worse. See
`docs/wiki/architecture/geometry-validation.md` for the tolerances and the proposed follow-ups.

Gated behind the `regression` marker exactly like `test_frozen_regression_corpus.py` (same
TEST_MODE gating, `tests/conftest.py`); `test_degraded_summary_fails_with_the_metric_named` below
is a pure unit test of the comparison function and runs in every tier.

**CI cost (Issue #17 repair)**: gate-4 already replays the corpus twice (merge-base + head, via
`spikes/failure_log_sweep/corpus_snapshot.py`) to check outcome/signature invariants; a third,
sequential pass just for M1–M6 blew CI's 120-minute budget. When the `CORPUS_SNAPSHOT` env var is
set (CI sets it to gate-4's own head snapshot), this test reads each PLANNED context's `"metrics"`
straight off that snapshot instead of calling `generate_demo_design` again — `corpus_snapshot.py`
now records `measure_design`'s output there for exactly this reason. Without the env var
(developer runs), it replays the corpus as before — unchanged from pre-repair behaviour.
"""
from __future__ import annotations

import json
import os

import pytest

from app.demo.service import generate_demo_design
from app.vertical_slice.quality_metrics import (
    baseline_summary,
    baseline_summary_from_metrics,
    find_regressions,
    summarize,
)
from spikes.failure_log_sweep.sweep import project_from_context

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "corpus.json")
_BASELINE_PATH = os.path.join(os.path.dirname(__file__), "quality_baseline.json")


def _load(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_CORPUS = _load(_CORPUS_PATH) or {"cases": []}
_BASELINE = _load(_BASELINE_PATH)


def _metrics_from_snapshot(snapshot_path: str) -> list[dict]:
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    return [row["metrics"] for row in snapshot["results"].values() if row.get("status") == "PLANNED"]


def _current_quality_summary() -> dict:
    """The current corpus's four gated stats — from the CI head snapshot if `CORPUS_SNAPSHOT` is
    set (no corpus replay), otherwise by replaying the corpus like every other regression test."""
    snapshot_path = os.environ.get("CORPUS_SNAPSHOT")
    if snapshot_path:
        return baseline_summary_from_metrics(_metrics_from_snapshot(snapshot_path))

    designs = []
    for case in _CORPUS["cases"]:
        if case["expected_outcome"] != "PLANNED":
            continue
        project = project_from_context(case["context"])
        result = generate_demo_design(project)
        designs.append(result.design)
    return baseline_summary(summarize(designs))


@pytest.mark.regression
@pytest.mark.skipif(
    not _CORPUS["cases"] or _BASELINE is None,
    reason="corpus.json/quality_baseline.json not yet generated — run freeze_corpus.py and "
           "freeze_quality_baseline.py",
)
def test_corpus_quality_summary_matches_the_frozen_baseline():
    current = _current_quality_summary()
    regressions = find_regressions(_BASELINE, current)
    assert not regressions, (
        f"architectural-quality regression on {', '.join(regressions)} — "
        f"baseline={ {k: _BASELINE.get(k) for k in regressions} }, "
        f"current={ {k: current.get(k) for k in regressions} }"
    )


# ------------------------------------------------------------------ AC-7: the snapshot path


def test_snapshot_metrics_are_used_without_regenerating_designs(tmp_path, monkeypatch):
    """With `CORPUS_SNAPSHOT` set, the corpus summary comes from the snapshot's own stored
    `"metrics"` — `generate_demo_design` is never called (a `REFUSED` entry, which never carries
    `"metrics"`, must not break this either)."""
    def _fake_metrics(m3, m4, wet_adjacent, wet_total, contiguous):
        return {
            "m1_habitable_aspect_median": 1.3, "m1_habitable_aspect_max": 2.0,
            "m2_habitable_on_envelope_ratio": 1.0, "m3_circulation_share": m3,
            "m4_hall_door_count": 3, "m4_hall_aspect_median": m4,
            "m5_wet_adjacency_ratio": (wet_adjacent / wet_total) if wet_total else None,
            "m5_wet_adjacent_count": wet_adjacent, "m5_wet_total_count": wet_total,
            "m6_public_zone_contiguous": contiguous,
            "dead_space_m2": 0.0, "wasted_circulation_share": 0.0,
        }

    fake_snapshot = {
        "version": 1,
        "results": {
            # Two wet rooms, 1 of 2 adjacent (ratio 0.5, weight 2)
            "ctx-a": {"status": "PLANNED", "metrics": _fake_metrics(0.10, 1.6, 1, 2, True)},
            # One wet room, adjacent (ratio 1.0, weight 1) — a naive mean of ratios would give
            # (0.5 + 1.0) / 2 = 0.75; the correct pooled share is (1 + 1) / (2 + 1) = 0.667.
            "ctx-b": {"status": "PLANNED", "metrics": _fake_metrics(0.14, 2.0, 1, 1, False)},
            "ctx-c": {"status": "REFUSED", "code": "SOME_CODE"},
        },
    }
    snapshot_path = tmp_path / "fake_snapshot.json"
    snapshot_path.write_text(json.dumps(fake_snapshot), encoding="utf-8")
    monkeypatch.setenv("CORPUS_SNAPSHOT", str(snapshot_path))

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("generate_demo_design was called even though CORPUS_SNAPSHOT was set")

    monkeypatch.setattr(
        "tests.regression_corpus.test_quality_baseline.generate_demo_design", _must_not_be_called
    )

    current = _current_quality_summary()
    assert current == pytest.approx({
        "n": 2,
        "m3_circulation_share_median": 0.12,
        "m4_hall_aspect_median": 1.8,
        "m5_wet_adjacency_share": 2 / 3,
        "m6_public_contiguous_share": 0.5,
    })


# ------------------------------------------------------------------ AC-3: the comparison itself

_BASELINE_FIXTURE = {
    "n": 400,
    "m3_circulation_share_median": 0.18,
    "m4_hall_aspect_median": 1.8,
    "m5_wet_adjacency_share": 0.42,
    "m6_public_contiguous_share": 0.61,
}


def test_degraded_summary_fails_with_the_metric_named():
    degraded = dict(_BASELINE_FIXTURE, m3_circulation_share_median=0.18 + 0.05)
    regressions = find_regressions(_BASELINE_FIXTURE, degraded)
    assert regressions == ["m3_circulation_share_median"]


def test_every_gated_metric_can_regress_on_its_own():
    for key, delta in (
        ("m3_circulation_share_median", 0.05),      # up = worse (more circulation)
        ("m4_hall_aspect_median", 0.5),              # up = worse (longer spine)
        ("m5_wet_adjacency_share", -0.05),           # down = worse (less adjacency)
        ("m6_public_contiguous_share", -0.05),       # down = worse (less contiguity)
    ):
        degraded = dict(_BASELINE_FIXTURE, **{key: _BASELINE_FIXTURE[key] + delta})
        assert find_regressions(_BASELINE_FIXTURE, degraded) == [key], key


def test_a_move_within_tolerance_is_not_a_regression():
    within = dict(_BASELINE_FIXTURE, m3_circulation_share_median=0.18 + 0.019,
                  m4_hall_aspect_median=1.8 + 0.19)
    assert find_regressions(_BASELINE_FIXTURE, within) == []


def test_an_improving_metric_never_regresses_regardless_of_size():
    improved = dict(_BASELINE_FIXTURE, m3_circulation_share_median=0.05, m4_hall_aspect_median=1.0,
                    m5_wet_adjacency_share=0.95, m6_public_contiguous_share=0.99)
    assert find_regressions(_BASELINE_FIXTURE, improved) == []


def test_a_missing_metric_on_either_side_is_never_claimed_as_a_regression():
    missing_current = dict(_BASELINE_FIXTURE)
    del missing_current["m5_wet_adjacency_share"]
    assert find_regressions(_BASELINE_FIXTURE, missing_current) == []
