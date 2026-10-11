"""The REGRESSION tier: `Frozen context -> project_from_context -> generate_demo_design`, zero
LLM/network calls. Gated behind the `regression` marker (TEST_MODE=REGRESSION/FULL_AI/NIGHTLY) —
this is the full ~432-context corpus, bigger than the FAST unit suite, but still fully
deterministic; see tests/conftest.py's shared gating hook.

Assertions are structural/quality invariants, not brittle full-payload byte-equality — the point
is "does this context still reproduce the expected kind of outcome," not "is the JSON
byte-identical to some frozen snapshot" (which would break on any legitimate improvement).

**Snapshot mode (Issue #66)**: when `CORPUS_SNAPSHOT` names a file, the same two facts (`status`,
and for refusals `code`) are asserted from that snapshot's own recorded entry instead of calling
`generate_demo_design` again — see `spikes/failure_log_sweep/snapshot_invariants.py`. A stale or
short snapshot FAILS loudly (never silently skipped). Without the env var this replays exactly as
before. CI runs this file in its own pytest invocation with `CORPUS_SNAPSHOT` unset, so it keeps
genuinely replaying as the shadow-mode ground truth; a separate step evaluates the same head
snapshot independently and the two verdicts are compared — see the gate-4 section of
docs/wiki/architecture/agent-team-workflow.md. `test_quality_baseline.py`'s own, separately-existing
`CORPUS_SNAPSHOT` usage (Issue #17) is unaffected — it runs in a second invocation in the same CI
step, scoped to just that command.
"""

import json
import os

import pytest

from app.demo.service import DemoGenerationError, generate_demo_design
from spikes.failure_log_sweep import snapshot_invariants
from spikes.failure_log_sweep.sweep import project_from_context

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "corpus.json")


def _load_corpus() -> dict:
    if not os.path.exists(_CORPUS_PATH):
        return {"cases": [], "source_context_count": 0, "frozen_count": 0, "skipped_count": 0}
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


_CORPUS = _load_corpus()


@pytest.mark.regression
@pytest.mark.skipif(not _CORPUS["cases"], reason="corpus.json not yet generated — run freeze_corpus.py")
@pytest.mark.parametrize("case", _CORPUS["cases"], ids=lambda c: c["source_key"])
def test_frozen_context_reproduces_expected_outcome(case):
    snapshot_path = os.environ.get("CORPUS_SNAPSHOT")
    if snapshot_path:
        with open(snapshot_path, encoding="utf-8") as f:
            snapshot = json.load(f)
        try:
            snapshot_invariants.validate_snapshot(
                snapshot, _CORPUS["cases"], expected_sha=snapshot_invariants.current_head_sha(),
            )
        except snapshot_invariants.SnapshotError as exc:
            pytest.fail(str(exc))
        report = snapshot_invariants.evaluate([case], snapshot)
        if not report.ok:
            m = report.mismatches[0]
            pytest.fail(f"{m.reason} for {m.key}: expected={m.expected} actual={m.actual}")
        return

    project = project_from_context(case["context"])

    if case["expected_outcome"] == "REFUSED":
        with pytest.raises(DemoGenerationError) as exc_info:
            generate_demo_design(project)
        assert exc_info.value.code == case["expected_code"]
        return

    result = generate_demo_design(project)
    assert result.design is not None
    assert len(result.design.rooms) > 0


@pytest.mark.regression
def test_corpus_size_matches_documented_source():
    """Guards against silently freezing a smaller convenience set instead of the real corpus."""
    if _CORPUS["frozen_count"] == 0:
        pytest.skip("corpus.json not yet generated")
    assert _CORPUS["source_context_count"] == 432
    assert _CORPUS["frozen_count"] + _CORPUS["skipped_count"] == _CORPUS["source_context_count"]
