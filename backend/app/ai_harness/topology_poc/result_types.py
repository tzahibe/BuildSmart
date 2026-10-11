"""Shared result bookkeeping types for BOTH runners (`runner.py`, the live-Ollama control-run
driver, and `frozen_runner.py`, the primary frozen-dataset driver) — Issue #151.

Deliberately free of any LLM-call or network dependency (no `llm_client` import, directly or
transitively) so importing this module can never pull the primary scoring path anywhere near a
socket (AC-14). `source`/`realizability` live only on these result-bookkeeping types, never on
`schema.TopologyProposal` itself — see `schema.py`'s own docstring (AC-9, AC-10).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from app.ai_harness.topology_poc import critic


@dataclass(frozen=True)
class ScoredProposal:
    source: str  # "CURRENT_GENERATOR" | "LLM"
    raw_index: int
    realizability: str
    score: dict  # critic.ScoreBreakdown, as a dict
    canonical_hash: str


@dataclass(frozen=True)
class BriefResult:
    brief_id: str
    source_key: str
    bedrooms: int
    wet_rooms: int
    safe_room: bool
    open_plan: bool
    size_tier: str
    aspect_tier: str
    generator: "ScoredProposal | None"
    generator_error: "str | None"
    llm_proposals: tuple  # tuple[ScoredProposal, ...]
    llm_raw_generated: int
    llm_schema_rejected: int
    llm_exact_duplicates: int
    materially_distinct_count: int
    llm_call_latency_s: "float | None"
    llm_model: "str | None"


def score_to_dict(sb: critic.ScoreBreakdown) -> dict:
    return {
        "adjacency_similarity": sb.adjacency_similarity, "access_similarity": sb.access_similarity,
        "wet_core_similarity": sb.wet_core_similarity,
        "entrance_relation_score": sb.entrance_relation_score,
        "hard_violations": list(sb.hard_violations), "total_score": sb.total_score,
    }


def brief_result_to_dict(result: BriefResult) -> dict:
    return asdict(result)


def brief_result_from_dict(d: dict) -> BriefResult:
    generator = ScoredProposal(**d["generator"]) if d["generator"] is not None else None
    llm_proposals = tuple(ScoredProposal(**p) for p in d["llm_proposals"])
    d2 = {**d, "generator": generator, "llm_proposals": llm_proposals}
    return BriefResult(**d2)


def load_checkpoint(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {brief_id: brief_result_from_dict(d) for brief_id, d in raw.items()}


def save_checkpoint(path: str, results: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({bid: brief_result_to_dict(r) for bid, r in results.items()}, f, indent=2)


__all__ = [
    "ScoredProposal", "BriefResult", "score_to_dict", "brief_result_to_dict",
    "brief_result_from_dict", "load_checkpoint", "save_checkpoint",
]
