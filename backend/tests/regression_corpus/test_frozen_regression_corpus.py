"""The REGRESSION tier: `Frozen context -> project_from_context -> generate_demo_design`, zero
LLM/network calls. Gated behind the `regression` marker (TEST_MODE=REGRESSION/FULL_AI/NIGHTLY) —
this is the full ~432-context corpus, bigger than the FAST unit suite, but still fully
deterministic; see tests/conftest.py's shared gating hook.

Assertions are structural/quality invariants, not brittle full-payload byte-equality — the point
is "does this context still reproduce the expected kind of outcome," not "is the JSON
byte-identical to some frozen snapshot" (which would break on any legitimate improvement).
"""

import json
import os

import pytest

from app.demo.service import DemoGenerationError, generate_demo_design
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
