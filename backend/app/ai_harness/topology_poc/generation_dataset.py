"""Preflight and loader for the FROZEN generation dataset (Issue #151, AC-14, AC-15, AC-16).

`docs/reports/llm-topology-poc/generation-dataset.json` is the immutable experiment input for the
PRIMARY run: every LLM call was already made, once, in an owner-controlled environment outside this
worker (out of scope: "Calling an LLM from the worker"). This module's `load_dataset()` is the ONLY
way the primary scoring path may obtain a generation record — it never calls `llm_client`, never
opens a socket, and never regenerates anything (AC-14, proven by
`tests/ai_harness/test_topology_no_llm_on_scoring_path.py`).

`preflight()` raises `GenerationDatasetError` — never a silent fallback, never a regeneration, never
a switch to a local model — when (AC-16):
  - the file is missing;
  - its `dataset_sha256` does not match a canonical re-hash of its own body (the exact method used
    when the file was committed: `json.dumps(body, indent=2, ensure_ascii=False)` over every key
    except `dataset_sha256` itself, in the file's own insertion order, sha256-hexdigested);
  - any attempt's `model` is a local/Ollama model (that belongs only to the forced control run,
    AC-17 — never the primary path);
  - the record `brief_id`s are not exactly the frozen `FROZEN_BRIEF_IDS`, in order;
  - a record or one of its attempts is missing a required field (AC-15's full artifact field set).
"""
from __future__ import annotations

import hashlib
import json
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)

DEFAULT_GENERATION_DATASET_JSON = os.path.join(
    _REPO_ROOT, "docs", "reports", "llm-topology-poc", "generation-dataset.json")

#: The frozen 20 briefs (Issue #151, AC-3), B01..B20 in order — the ONLY ids a valid PRIMARY
#: dataset may carry (AC-16).
FROZEN_BRIEF_IDS = tuple(f"B{i:02d}" for i in range(1, 21))

#: AC-15's full artifact field set, split across the record and each of its attempts (a record may
#: carry more than one attempt when `retry_count` > 0).
REQUIRED_RECORD_FIELDS = (
    "brief_id", "brief", "system_prompt", "user_prompt", "n_proposals_requested",
    "retry_count", "attempts")
REQUIRED_ATTEMPT_FIELDS = (
    "attempt", "model", "parameters", "raw_response", "raw_sha256", "parsed_json",
    "usage", "cost_usd", "response_id", "timestamp")

#: Explicit local/Ollama model names known in this repo's sandbox (`llm_client.py`,
#: `tests/ai_harness/bench.py`) — any of these, or ANY `name:tag` Ollama-style identifier, is
#: rejected on the primary path (AC-16).
LOCAL_MODEL_NAMES = frozenset({"llama3.2:latest", "llama3.2", "gemma4:26b", "gemma4"})


class GenerationDatasetError(RuntimeError):
    """Raised by `preflight()`/`load_dataset()` — never caught and hidden, never a trigger to
    regenerate, fall back to a local model, or proceed on partial data (AC-16)."""


def is_local_model(model: str) -> bool:
    return model in LOCAL_MODEL_NAMES or ":" in model


def _canonical_sha256(data: dict) -> str:
    body = {k: v for k, v in data.items() if k != "dataset_sha256"}
    blob = json.dumps(body, indent=2, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def preflight(path: str = DEFAULT_GENERATION_DATASET_JSON) -> dict:
    """Verifies `path` is a trustworthy, complete, non-local-model, exactly-20-brief primary
    dataset. Returns the parsed JSON on success. Raises `GenerationDatasetError` otherwise."""
    if not os.path.exists(path):
        raise GenerationDatasetError(
            f"frozen generation dataset missing at {path} — the primary path never calls an LLM, "
            "regenerates it, or falls back to a local model (AC-14, AC-16).")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "dataset_sha256" not in data:
        raise GenerationDatasetError(f"{path} carries no dataset_sha256 — cannot verify integrity.")
    recomputed = _canonical_sha256(data)
    if recomputed != data["dataset_sha256"]:
        raise GenerationDatasetError(
            f"{path}'s dataset_sha256 ({data['dataset_sha256']!r}) does not match its own content "
            f"(recomputed {recomputed!r}) — refusing to trust a tampered or corrupted dataset.")

    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise GenerationDatasetError(f"{path} carries no records.")

    brief_ids = tuple(r.get("brief_id") for r in records)
    if brief_ids != FROZEN_BRIEF_IDS:
        raise GenerationDatasetError(
            f"{path}'s brief ids {brief_ids} are not exactly the frozen {FROZEN_BRIEF_IDS}.")

    for record in records:
        missing = [f for f in REQUIRED_RECORD_FIELDS if f not in record]
        if missing:
            raise GenerationDatasetError(
                f"record {record.get('brief_id')!r} is missing required field(s) {missing} "
                "(AC-15's full artifact field set).")
        attempts = record["attempts"]
        if not isinstance(attempts, list) or not attempts:
            raise GenerationDatasetError(f"record {record['brief_id']!r} carries no attempts.")
        for attempt in attempts:
            missing_a = [f for f in REQUIRED_ATTEMPT_FIELDS if f not in attempt]
            if missing_a:
                raise GenerationDatasetError(
                    f"record {record['brief_id']!r} attempt {attempt.get('attempt')!r} is missing "
                    f"required field(s) {missing_a} (AC-15's full artifact field set).")
            if is_local_model(attempt["model"]):
                raise GenerationDatasetError(
                    f"record {record['brief_id']!r} attempt {attempt.get('attempt')!r} used local/"
                    f"Ollama model {attempt['model']!r} — the primary dataset must use a non-local "
                    "strong model; a local model belongs only in the forced control run (AC-17), "
                    "never the primary path.")

    return data


def load_dataset(path: str = DEFAULT_GENERATION_DATASET_JSON) -> dict:
    """Runs `preflight()` and returns the verified dataset dict. The only entrypoint the primary
    scoring path may use to obtain generation records (AC-14) — never `llm_client`, never a socket."""
    return preflight(path)


__all__ = [
    "GenerationDatasetError", "FROZEN_BRIEF_IDS", "REQUIRED_RECORD_FIELDS",
    "REQUIRED_ATTEMPT_FIELDS", "LOCAL_MODEL_NAMES", "is_local_model", "preflight", "load_dataset",
    "DEFAULT_GENERATION_DATASET_JSON",
]
