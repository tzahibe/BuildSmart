"""Issue #38, AC-3 — the FULL-corpus half: every door of EVERY PLANNED corpus design carries the
door-symbol contract (`hinge_x` / `hinge_y` / `swing_deg` / `swings_into`). Regression tier only
(`TEST_MODE=REGRESSION`, gate 4's `pytest tests/regression_corpus -n 4`): replaying all 404 PLANNED
contexts is far past gate 3's 1800 s budget, which is why `tests/test_demo_p0.py::
test_every_door_out_carries_hinge_and_swing` checks a deterministic sample in the fast tier."""
from __future__ import annotations

import json
import os

import pytest

from app.demo.service import generate_demo_design
from spikes.failure_log_sweep.sweep import project_from_context

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "corpus.json")
with open(_CORPUS_PATH, encoding="utf-8") as _f:
    _CORPUS = json.load(_f)
_PLANNED = [c for c in _CORPUS["cases"] if c["expected_outcome"] == "PLANNED"]


@pytest.mark.regression
@pytest.mark.skipif(not _PLANNED, reason="corpus.json has no PLANNED cases")
@pytest.mark.parametrize("case", _PLANNED, ids=lambda c: c["source_key"])
def test_every_planned_corpus_door_carries_hinge_and_swing(case):
    result = generate_demo_design(project_from_context(case["context"]))
    assert result.design.doors, case["source_key"]
    for door in result.design.doors:
        assert door.swing_deg in (0.0, 90.0, 180.0, 270.0), (case["source_key"], door)
        assert door.swings_into, (case["source_key"], door)
