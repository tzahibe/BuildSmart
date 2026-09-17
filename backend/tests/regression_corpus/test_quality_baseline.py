"""The architectural-quality REGRESSION tier (Issue #17): the M1–M6 corpus summary over the
frozen PLANNED contexts, checked against a committed baseline (`quality_baseline.json`, produced
by `freeze_quality_baseline.py`). A NO-REGRESSION bar, not a new absolute one — the measured gaps
against 21 professional plans (hall spine aspect, wet adjacency, strip-shaped public rooms) are
real and unresolved; this test only catches a FUTURE change quietly making them worse. See
`docs/wiki/architecture/geometry-validation.md` for the tolerances and the proposed follow-ups.

Gated behind the `regression` marker exactly like `test_frozen_regression_corpus.py` (same
TEST_MODE gating, `tests/conftest.py`); `test_degraded_summary_fails_with_the_metric_named` below
is a pure unit test of the comparison function and runs in every tier.
"""
from __future__ import annotations

import json
import os

import pytest

from app.demo.service import generate_demo_design
from app.vertical_slice.quality_metrics import baseline_summary, find_regressions, summarize
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


@pytest.mark.regression
@pytest.mark.skipif(
    not _CORPUS["cases"] or _BASELINE is None,
    reason="corpus.json/quality_baseline.json not yet generated — run freeze_corpus.py and "
           "freeze_quality_baseline.py",
)
def test_corpus_quality_summary_matches_the_frozen_baseline():
    designs = []
    for case in _CORPUS["cases"]:
        if case["expected_outcome"] != "PLANNED":
            continue
        project = project_from_context(case["context"])
        result = generate_demo_design(project)
        designs.append(result.design)

    current = baseline_summary(summarize(designs))
    regressions = find_regressions(_BASELINE, current)
    assert not regressions, (
        f"architectural-quality regression on {', '.join(regressions)} — "
        f"baseline={ {k: _BASELINE.get(k) for k in regressions} }, "
        f"current={ {k: current.get(k) for k in regressions} }"
    )


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
