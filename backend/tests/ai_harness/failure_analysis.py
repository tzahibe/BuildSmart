"""Optional, manually-invoked local failure clustering for large sweeps. Feeds structured
failures/refusals to the LOCAL_STRONG role for SUMMARIZATION ONLY — root-cause label, count,
representative examples. Never runs automatically inside `pytest`, and the prompt explicitly
forbids the model from judging whether a regression is acceptable: that decision stays with a
human/Claude reviewer reading the compact structured output, not with the local model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from tests.ai_harness.factory import get_provider
from tests.ai_harness.golden_dataset import extract_json

_CLUSTER_SYSTEM_PROMPT = (
    "You cluster and summarize a list of structured failure/refusal records from an architectural "
    "floor-plan generator. You do NOT decide whether any failure is acceptable or represents a "
    "real regression — that is a human decision. Output ONLY a JSON object: "
    '{"clusters": [{"root_cause_label": str, "count": int, "example_codes": [str, ...]}]}. '
    "Group records that plausibly share a root cause (same code, or same message pattern)."
)


@dataclass(frozen=True)
class ClusterReport:
    clusters: list[dict]
    raw_text: str


def analyze_failures(entries: list[dict], *, role: str = "local_strong") -> ClusterReport:
    if not entries:
        return ClusterReport(clusters=[], raw_text="")

    provider = get_provider(role)
    payload = json.dumps([
        {"code": e.get("code"), "message": e.get("message"), "kind": e.get("kind")}
        for e in entries
    ], ensure_ascii=False)
    response = provider.complete(payload, system_prompt=_CLUSTER_SYSTEM_PROMPT)
    parsed = extract_json(response.text) or {}
    return ClusterReport(clusters=parsed.get("clusters", []), raw_text=response.text)
