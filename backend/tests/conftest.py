"""Test-wide fixtures and collection hooks.

The failure-log isolation below is a hard separation between the test suite and the PRODUCT's
failure log. The TEST_MODE gating below that governs BOTH tests/ai_harness/ AND
tests/regression_corpus/ from one shared place — deliberately not a hook scoped only under
tests/ai_harness/, which would leave the regression corpus ungated and defeat the point of keeping
a plain `pytest` run fast (see docs/AI_TEST_HARNESS.md).
"""
from __future__ import annotations

import pytest

from app.observability import failure_log
from tests.ai_harness.config import test_mode_from_env


@pytest.fixture(autouse=True)
def _isolate_failure_log(tmp_path, monkeypatch):
    """Never let a test write into `app/data/failures.json`.

    That file is a diagnostic about REAL people who did not get a drawing. A suite that deliberately
    provokes refusals — a 200 x 3 m plot, six bedrooms, a footprint that cannot fit — was writing
    hundreds of entries into it, and the handful of genuine failures were buried underneath: 280
    entries, of which 5 were a person. A log nobody can read is not a log.
    """
    monkeypatch.setattr(failure_log, "_path", tmp_path / "failures.json")


#: Which TEST_MODE values enable each marker. A plain `pytest` run (TEST_MODE unset -> FAST)
#: collects none of these — deterministic stays fast with zero flags to remember.
_MARKER_MODES = {
    "local_ai": {"LOCAL_AI", "FULL_AI", "NIGHTLY"},
    "production_ai": {"FULL_AI", "NIGHTLY"},
    "regression": {"REGRESSION", "FULL_AI", "NIGHTLY"},
    "nightly": {"NIGHTLY"},
}


def pytest_collection_modifyitems(config, items):
    import os

    mode = test_mode_from_env()
    skip_local_ai = pytest.mark.skip(reason=f"needs TEST_MODE in {_MARKER_MODES['local_ai']}, got {mode!r}")
    skip_production_ai = pytest.mark.skip(reason="needs OPENAI_API_KEY set")
    skip_production_mode = pytest.mark.skip(reason=f"needs TEST_MODE in {_MARKER_MODES['production_ai']}, got {mode!r}")
    skip_regression = pytest.mark.skip(reason=f"needs TEST_MODE in {_MARKER_MODES['regression']}, got {mode!r}")
    skip_nightly = pytest.mark.skip(reason=f"needs TEST_MODE in {_MARKER_MODES['nightly']}, got {mode!r}")

    for item in items:
        if "local_ai" in item.keywords and mode not in _MARKER_MODES["local_ai"]:
            item.add_marker(skip_local_ai)
        if "production_ai" in item.keywords:
            if mode not in _MARKER_MODES["production_ai"]:
                item.add_marker(skip_production_mode)
            elif not os.environ.get("OPENAI_API_KEY"):
                item.add_marker(skip_production_ai)
        if "regression" in item.keywords and mode not in _MARKER_MODES["regression"]:
            item.add_marker(skip_regression)
        if "nightly" in item.keywords and mode not in _MARKER_MODES["nightly"]:
            item.add_marker(skip_nightly)
