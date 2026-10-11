"""Issue #142L — guards for the offline quality evaluator (experiment code, wired into nothing).

Pins the two properties the investigation depends on: every computed metric is documented with a
direction and an availability, and the evaluator is deterministic on a fixed plan record.
"""
from __future__ import annotations

import json
import os

import pytest

from app.ai_harness.quality_142l.metrics import DIMENSIONS, METRICS, MISSING_INFORMATION, evaluate

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
POOL = os.path.join(_REPO, "docs", "reports", "142l-quality-ranking", "data", "baseline_pool.json")
pytestmark = pytest.mark.skipif(not os.path.exists(POOL), reason="#142L baseline pool not present")


@pytest.fixture(scope="module")
def plans():
    pool = json.load(open(POOL))
    return [p for b in pool["briefs"].values() for p in b["plans"]]


def test_every_metric_is_documented_and_every_definition_is_computed(plans):
    v = evaluate(plans[0])
    assert set(v) == set(METRICS), (set(v) ^ set(METRICS))
    for name, d in METRICS.items():
        assert d.dimension in DIMENSIONS, name
        assert d.direction in ("up", "down", "info"), name
        assert d.availability in ("PRODUCTION", "DERIVED"), name
        assert d.unit, name                                   # units are short on purpose ("m", "m2")
        assert d.inputs, name                                  # where the number comes from
        assert d.limitations and len(d.limitations) > 10, name  # an honest caveat, however short
        for field in (d.definition, d.rationale):
            assert field and len(field) > 30, (name, field)     # a real sentence, not a label


def test_the_vector_is_complete_and_numeric_for_every_plan(plans):
    keys = None
    for p in plans:
        v = evaluate(p)
        assert all(isinstance(x, (int, float)) for x in v.values()), p["brief"]
        keys = keys or sorted(v)
        assert sorted(v) == keys, p["brief"]


def test_evaluation_is_deterministic(plans):
    assert evaluate(plans[0]) == evaluate(plans[0])


def test_missing_information_is_declared_and_never_computed():
    assert len(MISSING_INFORMATION) >= 5
    for k, why in MISSING_INFORMATION.items():
        assert k not in METRICS, k
        assert len(why) > 80, k
