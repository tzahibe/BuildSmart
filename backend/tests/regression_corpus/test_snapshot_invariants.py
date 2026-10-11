"""Issue #66: gate-4's third corpus replay is removed by letting the frozen outcome test read its
two facts (`status`, and for refusals `code`) from the head snapshot instead of calling
`generate_demo_design` again. These tests pin the snapshot-mode contract of
`test_frozen_context_reproduces_expected_outcome` (AC-1, AC-2) plus the shared comparison logic in
`spikes/failure_log_sweep/snapshot_invariants.py` (AC-3). Runs in every tier — no `regression`
marker, no real corpus replay.
"""
from __future__ import annotations

import json

import pytest

from spikes.failure_log_sweep import snapshot_invariants
from tests.regression_corpus import test_frozen_regression_corpus as tfrc

_FAKE_CASES = [
    {"source_key": "ctx-a", "context": {}, "expected_outcome": "PLANNED", "expected_code": None},
    {"source_key": "ctx-b", "context": {}, "expected_outcome": "REFUSED", "expected_code": "CODE_B"},
]
_FAKE_SNAPSHOT = {
    "sha": "deadbeef",
    "results": {
        "ctx-a": {"status": "PLANNED"},
        "ctx-b": {"status": "REFUSED", "code": "CODE_B"},
    },
}


def _write_snapshot(tmp_path, doc):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------ AC-1


def test_snapshot_mode_never_regenerates(tmp_path, monkeypatch):
    monkeypatch.setattr(tfrc, "_CORPUS", {"cases": _FAKE_CASES})
    monkeypatch.setattr(snapshot_invariants, "current_head_sha", lambda: "deadbeef")
    monkeypatch.setenv("CORPUS_SNAPSHOT", _write_snapshot(tmp_path, _FAKE_SNAPSHOT))

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("generate_demo_design was called even though CORPUS_SNAPSHOT was set")

    monkeypatch.setattr(tfrc, "generate_demo_design", _must_not_be_called)
    monkeypatch.setattr(tfrc, "project_from_context", _must_not_be_called)

    for case in _FAKE_CASES:
        tfrc.test_frozen_context_reproduces_expected_outcome(case)  # must not raise


# ------------------------------------------------------------------ AC-2


def test_stale_or_short_snapshot_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(tfrc, "_CORPUS", {"cases": _FAKE_CASES})

    # stale sha
    monkeypatch.setattr(snapshot_invariants, "current_head_sha", lambda: "current-sha")
    monkeypatch.setenv("CORPUS_SNAPSHOT", _write_snapshot(tmp_path, _FAKE_SNAPSHOT))
    with pytest.raises(pytest.fail.Exception) as exc_info:
        tfrc.test_frozen_context_reproduces_expected_outcome(_FAKE_CASES[0])
    assert "head_sha" in str(exc_info.value)

    # short snapshot (missing a context) at the right sha
    monkeypatch.setattr(snapshot_invariants, "current_head_sha", lambda: "deadbeef")
    short = {"sha": "deadbeef", "results": {"ctx-a": {"status": "PLANNED"}}}
    monkeypatch.setenv("CORPUS_SNAPSHOT", _write_snapshot(tmp_path, short))
    with pytest.raises(pytest.fail.Exception) as exc_info:
        tfrc.test_frozen_context_reproduces_expected_outcome(_FAKE_CASES[0])
    assert "context(s)" in str(exc_info.value)


# ------------------------------------------------------------------ AC-3


def test_evaluate_matches_replay_verdict_on_fixture():
    corpus = [
        {"source_key": "planned-ok", "expected_outcome": "PLANNED", "expected_code": None},
        {"source_key": "refused-ok", "expected_outcome": "REFUSED", "expected_code": "CODE_A"},
        {"source_key": "refused-code-mismatch", "expected_outcome": "REFUSED", "expected_code": "CODE_B"},
        {"source_key": "crashed", "expected_outcome": "PLANNED", "expected_code": None},
        {"source_key": "missing", "expected_outcome": "PLANNED", "expected_code": None},
    ]
    snapshot = {"sha": "x", "results": {
        "planned-ok": {"status": "PLANNED"},
        "refused-ok": {"status": "REFUSED", "code": "CODE_A"},
        "refused-code-mismatch": {"status": "REFUSED", "code": "WRONG_CODE"},
        "crashed": {"status": "CRASH", "code": "RuntimeError: boom"},
    }}

    report = snapshot_invariants.evaluate(corpus, snapshot)

    assert report.total == 5
    assert not report.ok
    assert report.failing_keys() == ["crashed", "missing", "refused-code-mismatch"]
    reasons = {m.key: m.reason for m in report.mismatches}
    assert reasons["refused-code-mismatch"] == "refusal code mismatch"
    assert reasons["crashed"] == "status mismatch"
    assert reasons["missing"] == "missing from snapshot"


def test_compare_verdicts_agrees_on_a_clean_match():
    from_snapshot = {"ok": True, "mismatches": []}
    from_replay = {"ok": True, "failing_keys": []}
    assert snapshot_invariants.compare_verdicts(from_snapshot, from_replay) == []


def test_compare_verdicts_flags_a_pass_fail_divergence():
    from_snapshot = {"ok": True, "mismatches": []}
    from_replay = {"ok": False, "failing_keys": ["ctx-a"]}
    diffs = snapshot_invariants.compare_verdicts(from_snapshot, from_replay)
    assert any("pass/fail differs" in d for d in diffs)
    assert any("failing-context sets differ" in d for d in diffs)


def test_compare_verdicts_flags_a_differing_failing_set_even_if_both_failed():
    from_snapshot = {"ok": False, "mismatches": [{"key": "ctx-a"}]}
    from_replay = {"ok": False, "failing_keys": ["ctx-b"]}
    diffs = snapshot_invariants.compare_verdicts(from_snapshot, from_replay)
    assert len(diffs) == 1 and "failing-context sets differ" in diffs[0]
