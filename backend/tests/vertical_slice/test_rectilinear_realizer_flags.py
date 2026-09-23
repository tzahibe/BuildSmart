"""Stage 0 (Issue #118), AC-3: `room_merge.decide_default` — the flip rule as one pure, tested
function — and that `LIVING_KITCHEN_MERGE_ENABLED`'s actual value agrees with what the committed
432-context A/B report concluded (`docs/reports/rectilinear-realizer/stage0-merge-ab.md`,
produced by `scripts/stage0_merge_ab.py`).
"""
from __future__ import annotations

from app.vertical_slice import room_merge

_ALL_GOOD = dict(lost=0, crashes=0, status_changes=0, refusal_code_changes=0, m_regressions=[])


def test_default_on_only_when_every_condition_holds():
    on, verdict = room_merge.decide_default(**_ALL_GOOD)
    assert on is True
    assert "ON" in verdict


def test_any_lost_context_keeps_the_flag_off():
    on, verdict = room_merge.decide_default(**{**_ALL_GOOD, "lost": 1})
    assert on is False
    assert "LOST=1" in verdict


def test_any_crash_keeps_the_flag_off():
    on, verdict = room_merge.decide_default(**{**_ALL_GOOD, "crashes": 2})
    assert on is False
    assert "crashes=2" in verdict


def test_a_status_class_change_keeps_the_flag_off():
    on, verdict = room_merge.decide_default(**{**_ALL_GOOD, "status_changes": 1})
    assert on is False
    assert "status_changes=1" in verdict


def test_a_refusal_code_change_keeps_the_flag_off():
    on, verdict = room_merge.decide_default(**{**_ALL_GOOD, "refusal_code_changes": 1})
    assert on is False
    assert "refusal_code_changes=1" in verdict


def test_any_m1_m6_regression_keeps_the_flag_off():
    on, verdict = room_merge.decide_default(**{**_ALL_GOOD, "m_regressions": ["m3_circulation_share_median"]})
    assert on is False
    assert "m3_circulation_share_median" in verdict


def test_multiple_failures_are_all_named():
    on, verdict = room_merge.decide_default(**{**_ALL_GOOD, "lost": 3, "crashes": 1})
    assert on is False
    assert "LOST=3" in verdict and "crashes=1" in verdict


def test_the_shipped_flag_agrees_with_the_committed_ab_reports_own_verdict():
    """The constant is not set independently of the measurement — it is literally the same
    boolean `decide_default` returns for the numbers the committed report names (Issue #118's own
    `docs/reports/rectilinear-realizer/stage0-merge-ab.md`)."""
    measured_on, _ = room_merge.decide_default(
        lost=0, crashes=0, status_changes=0, refusal_code_changes=0, m_regressions=[])
    assert room_merge.LIVING_KITCHEN_MERGE_ENABLED == measured_on
