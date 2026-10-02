"""AC-15: the frozen generation dataset carries the full artifact field set, proven over the REAL
committed file. AC-16: the preflight raises and exits non-zero on a missing file, a dataset_sha256
mismatch, a local/Ollama model, wrong brief ids, or a missing required field — and no regeneration,
local-model or network fallback path exists."""
from __future__ import annotations

import copy
import json

import pytest

from app.ai_harness.topology_poc import generation_dataset as gd

_REAL_DATASET_JSON = gd.DEFAULT_GENERATION_DATASET_JSON


def _load_real() -> dict:
    with open(_REAL_DATASET_JSON, encoding="utf-8") as f:
        return json.load(f)


def _write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _minimal_valid_dataset() -> dict:
    attempt = {
        "attempt": 0, "model": "gpt-5", "parameters": {"temperature": 1.0},
        "raw_response": "[]", "raw_sha256": "x" * 64, "parsed_json": {"proposals": []},
        "usage": {}, "cost_usd": 0.01, "response_id": "resp-1", "timestamp": "2026-09-30T00:00:00Z",
    }
    records = [
        {"brief_id": bid, "brief": {}, "system_prompt": "sys", "user_prompt": "usr",
         "n_proposals_requested": 8, "retry_count": 0, "attempts": [dict(attempt)]}
        for bid in gd.FROZEN_BRIEF_IDS
    ]
    data = {"experiment": "test", "model": "gpt-5", "n_briefs": 20, "records": records}
    data["dataset_sha256"] = gd._canonical_sha256(data)
    return data


# --- AC-15: the REAL committed file carries the full artifact field set ---

def test_real_dataset_file_exists_and_passes_preflight():
    import os

    assert os.path.exists(_REAL_DATASET_JSON), (
        "the frozen generation dataset must exist before the primary run may score anything")
    data = gd.preflight(_REAL_DATASET_JSON)
    assert data["records"], "the real dataset must carry at least one record"


def test_real_dataset_brief_ids_are_exactly_the_frozen_20_in_order():
    data = _load_real()
    brief_ids = tuple(r["brief_id"] for r in data["records"])
    assert brief_ids == gd.FROZEN_BRIEF_IDS


@pytest.mark.parametrize("field", gd.REQUIRED_RECORD_FIELDS)
def test_real_dataset_every_record_carries_every_required_field(field):
    data = _load_real()
    for record in data["records"]:
        assert field in record, f"record {record.get('brief_id')!r} is missing {field!r}"


@pytest.mark.parametrize("field", gd.REQUIRED_ATTEMPT_FIELDS)
def test_real_dataset_every_attempt_carries_every_required_field(field):
    data = _load_real()
    for record in data["records"]:
        for attempt in record["attempts"]:
            assert field in attempt, (
                f"record {record['brief_id']!r} attempt {attempt.get('attempt')!r} is missing "
                f"{field!r}")


def test_real_dataset_no_attempt_uses_a_local_or_ollama_model():
    data = _load_real()
    for record in data["records"]:
        for attempt in record["attempts"]:
            assert not gd.is_local_model(attempt["model"]), (
                f"record {record['brief_id']!r} uses local/Ollama model {attempt['model']!r} — "
                "the primary dataset must never carry a local model")


def test_real_dataset_every_raw_sha256_matches_its_own_raw_response():
    import hashlib

    data = _load_real()
    for record in data["records"]:
        for attempt in record["attempts"]:
            expected = hashlib.sha256(attempt["raw_response"].encode("utf-8")).hexdigest()
            assert expected == attempt["raw_sha256"]


# --- AC-16: preflight raises loudly, never falls back ---

def test_preflight_raises_on_missing_file(tmp_path):
    missing = str(tmp_path / "does-not-exist.json")
    with pytest.raises(gd.GenerationDatasetError):
        gd.preflight(missing)


def test_load_dataset_raises_on_missing_file_too(tmp_path):
    missing = str(tmp_path / "does-not-exist.json")
    with pytest.raises(gd.GenerationDatasetError):
        gd.load_dataset(missing)


def test_preflight_raises_on_dataset_sha256_mismatch(tmp_path):
    data = _minimal_valid_dataset()
    data["dataset_sha256"] = "0" * 64  # deliberately wrong
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError, match="dataset_sha256"):
        gd.preflight(path)


def test_preflight_raises_when_dataset_sha256_is_absent(tmp_path):
    data = _minimal_valid_dataset()
    del data["dataset_sha256"]
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError):
        gd.preflight(path)


@pytest.mark.parametrize("local_model", ["llama3.2:latest", "llama3.2", "gemma4:26b", "mistral:7b"])
def test_preflight_raises_when_any_attempt_uses_a_local_model(tmp_path, local_model):
    data = _minimal_valid_dataset()
    data["records"][0]["attempts"][0]["model"] = local_model
    data["dataset_sha256"] = gd._canonical_sha256(data)
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError, match="local"):
        gd.preflight(path)


def test_preflight_raises_when_brief_ids_are_not_exactly_the_frozen_20(tmp_path):
    data = _minimal_valid_dataset()
    data["records"] = data["records"][:19]  # drop B20
    data["dataset_sha256"] = gd._canonical_sha256(data)
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError, match="frozen"):
        gd.preflight(path)


def test_preflight_raises_when_brief_ids_are_out_of_order(tmp_path):
    data = _minimal_valid_dataset()
    data["records"][0], data["records"][1] = data["records"][1], data["records"][0]
    data["dataset_sha256"] = gd._canonical_sha256(data)
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError, match="frozen"):
        gd.preflight(path)


@pytest.mark.parametrize("missing_field", gd.REQUIRED_RECORD_FIELDS)
def test_preflight_raises_when_a_record_is_missing_a_required_field(tmp_path, missing_field):
    data = _minimal_valid_dataset()
    del data["records"][0][missing_field]
    data["dataset_sha256"] = gd._canonical_sha256(data)
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError):
        gd.preflight(path)


@pytest.mark.parametrize("missing_field", gd.REQUIRED_ATTEMPT_FIELDS)
def test_preflight_raises_when_an_attempt_is_missing_a_required_field(tmp_path, missing_field):
    data = _minimal_valid_dataset()
    del data["records"][0]["attempts"][0][missing_field]
    data["dataset_sha256"] = gd._canonical_sha256(data)
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    with pytest.raises(gd.GenerationDatasetError):
        gd.preflight(path)


def test_valid_minimal_dataset_passes_preflight(tmp_path):
    data = _minimal_valid_dataset()
    path = str(tmp_path / "dataset.json")
    _write(path, data)
    loaded = gd.preflight(path)
    assert loaded["dataset_sha256"] == data["dataset_sha256"]


def test_no_regeneration_local_model_or_network_fallback_path_exists():
    """`preflight`/`load_dataset` never widen a failure into a substitute value — every branch that
    detects a problem raises `GenerationDatasetError` (there is no `except` around the checks that
    could swallow one and fall through to a default/local-model/network path)."""
    import ast
    import inspect

    source = inspect.getsource(gd)
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Try), (
            "generation_dataset.py must never catch its own preflight failures to fall back — "
            "found a try/except block")
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
    forbidden = {"requests", "urllib", "urllib.request", "urllib3", "socket", "http", "httpx",
                "llm_client"}
    assert not (imported_names & forbidden), imported_names & forbidden
