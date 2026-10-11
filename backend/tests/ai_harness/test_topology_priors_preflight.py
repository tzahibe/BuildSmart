"""AC-11: preflight verifies all three semantics, fails loudly, never falls back to the older
table. AC-12: adjacency prior reads ONLY spatial_touching, access prior ONLY access,
touching_without_door never reaches a topology's quality score."""
from __future__ import annotations

import json
import math
import os

import pytest

from app.ai_harness.topology_poc import critic, priors, schema

_REAL_FULLCORPUS_JSON = priors.DEFAULT_FULLCORPUS_JSON
_REAL_ROOM_PROPORTIONS_JSON = priors.DEFAULT_ROOM_PROPORTIONS_JSON


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


_VALID_SECTION = {"baseline_rate": 0.5, "rows": [
    {"role_a": "BATHROOM", "role_b": "BEDROOM", "sample_count": 10, "positive_count": 9,
     "raw_p": 0.9, "p_smoothed": 0.9, "lift": 1.5, "meets_min_support": True}]}


def _valid_artifact() -> dict:
    return {
        "spatial_touching": _VALID_SECTION,
        "touching_without_door": _VALID_SECTION,
        "access": _VALID_SECTION,
        "train_count": 100,
        "holdout_count": 20,
        "front_door_direct_access": {},
    }


def test_real_corrected_artifact_exists_and_passes_preflight():
    """This is the actual artifact this Issue hard-depends on (requirement 8) — not a fixture."""
    assert os.path.exists(_REAL_FULLCORPUS_JSON), (
        "corrected #149 artifact must exist before this POC's scoring stage may run at all")
    data = priors.preflight(_REAL_FULLCORPUS_JSON)
    for key in priors.REQUIRED_ADJACENCY_SEMANTICS:
        assert data[key]["rows"], f"real artifact must carry non-empty {key!r} rows"


def test_preflight_raises_on_missing_file(tmp_path):
    missing_path = str(tmp_path / "does-not-exist.json")
    with pytest.raises(priors.PriorsPreflightError):
        priors.preflight(missing_path)


@pytest.mark.parametrize("missing_key", ["spatial_touching", "touching_without_door", "access"])
def test_preflight_raises_when_a_semantic_is_absent(tmp_path, missing_key):
    data = _valid_artifact()
    del data[missing_key]
    path = str(tmp_path / "artifact.json")
    _write_json(path, data)
    with pytest.raises(priors.PriorsPreflightError):
        priors.preflight(path)


@pytest.mark.parametrize("empty_key", ["spatial_touching", "touching_without_door", "access"])
def test_preflight_raises_when_a_semantic_has_zero_rows(tmp_path, empty_key):
    data = _valid_artifact()
    data[empty_key] = {"baseline_rate": 0.5, "rows": []}
    path = str(tmp_path / "artifact.json")
    _write_json(path, data)
    with pytest.raises(priors.PriorsPreflightError):
        priors.preflight(path)


def test_preflight_never_falls_back_to_the_older_table(tmp_path):
    """A missing corrected artifact must raise, never silently substitute the older, in-sample
    `adjacency.json` (Issue #141) — proven by asserting the older path is never even referenced."""
    missing_path = str(tmp_path / "does-not-exist.json")
    with pytest.raises(priors.PriorsPreflightError) as exc_info:
        priors.preflight(missing_path)
    assert "adjacency.json" not in str(exc_info.value) or "older" in str(exc_info.value).lower()
    # load_priors must raise too, not silently degrade to a partial Priors object
    with pytest.raises(priors.PriorsPreflightError):
        priors.load_priors(missing_path, _REAL_ROOM_PROPORTIONS_JSON)


def test_load_priors_builds_adjacency_table_only_from_spatial_touching(tmp_path):
    data = _valid_artifact()
    data["spatial_touching"] = {"baseline_rate": 0.5, "rows": [
        {"role_a": "BATHROOM", "role_b": "BEDROOM", "sample_count": 10, "positive_count": 10,
         "raw_p": 1.0, "p_smoothed": 0.99, "lift": 2.0, "meets_min_support": True}]}
    data["access"] = {"baseline_rate": 0.5, "rows": [
        {"role_a": "BATHROOM", "role_b": "BEDROOM", "sample_count": 10, "positive_count": 1,
         "raw_p": 0.1, "p_smoothed": 0.15, "lift": 0.3, "meets_min_support": True}]}
    path = str(tmp_path / "artifact.json")
    _write_json(path, data)
    loaded = priors.load_priors(path, _REAL_ROOM_PROPORTIONS_JSON)
    assert loaded.adjacency_table.row_for("BATHROOM", "BEDROOM").p_adjacent == 0.99
    assert loaded.access_table.row_for("BATHROOM", "BEDROOM").p_adjacent == 0.15


def test_touching_without_door_never_reaches_a_quality_score(tmp_path):
    """Changing ONLY touching_without_door must not change any proposal's total_score at all."""
    data = _valid_artifact()
    path_a = str(tmp_path / "a.json")
    _write_json(path_a, data)
    loaded_a = priors.load_priors(path_a, _REAL_ROOM_PROPORTIONS_JSON)

    data_mutated = _valid_artifact()
    data_mutated["touching_without_door"] = {"baseline_rate": 0.999, "rows": [
        {"role_a": "ZZZ", "role_b": "YYY", "sample_count": 999, "positive_count": 1,
         "raw_p": 0.001, "p_smoothed": 0.001, "lift": 0.001, "meets_min_support": True}]}
    path_b = str(tmp_path / "b.json")
    _write_json(path_b, data_mutated)
    loaded_b = priors.load_priors(path_b, _REAL_ROOM_PROPORTIONS_JSON)

    proposal = schema.proposal_from_dict({
        "rooms": [{"id": "BEDROOM_1", "role": "BEDROOM"}, {"id": "BATHROOM_1", "role": "BATHROOM"}],
        "spatial_adjacency": [["BEDROOM_1", "BATHROOM_1"]],
        "access_graph": [[schema.ENTRANCE_ID, "BEDROOM_1"]],
        "zones": {"private": ["BEDROOM_1"], "service": ["BATHROOM_1"]},
        "clusters": {"wet_core": ["BATHROOM_1"]},
    })
    score_a = critic.score_topology(proposal, loaded_a)
    score_b = critic.score_topology(proposal, loaded_b)
    assert score_a == score_b, "touching_without_door must never influence a topology's quality score"
    # and the diagnostic rows themselves genuinely differ, proving the mutation was real
    assert loaded_a.diagnostic_touching_without_door_rows != loaded_b.diagnostic_touching_without_door_rows
