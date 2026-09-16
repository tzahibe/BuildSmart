"""The versioned golden semantic dataset — see golden/semantic_cases.json's `_note` for why its
schema is a harness-owned simplification of the real production extraction task, and why
`public_open_side` is deliberately absent (it's deterministic, not LLM-extracted — see
test_deterministic_examples.py).

Expected values come from approved product rules and the existing tests/wet_room_corpus/corpus.json
labels, never from "whatever a model happened to say" — that would make the golden set circular.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

_DATASET_PATH = os.path.join(os.path.dirname(__file__), "golden", "semantic_cases.json")

SYSTEM_PROMPT = (
    "You are a structured data extractor for architectural house-design briefs written in Hebrew, "
    "English, or a mix of both. Given a free-text brief, output ONLY a JSON object with exactly "
    "these fields:\n"
    '  "floors": integer or null,\n'
    '  "bedrooms": integer or null,\n'
    '  "safe_room": boolean or null (true if a protected safe room / mamad / ממ"ד is required),\n'
    '  "wet_rooms": integer or null (count of bathrooms/wet rooms mentioned or implied),\n'
    '  "unsupported_topics": array of short lowercase topic tags for any request this brief makes '
    "that a single-family home floor-plan generator cannot support (e.g. \"pool\", \"elevator\", "
    '"laundry"), or an empty array if none.\n'
    "Output strict JSON only — no prose, no markdown code fences."
)


@dataclass(frozen=True)
class GoldenCase:
    id: str
    topic: str
    source: str
    input_text: str
    expected: dict


def load_cases(topics: tuple[str, ...] | None = None) -> list[GoldenCase]:
    with open(_DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cases = [GoldenCase(**c) for c in data["cases"]]
    if topics is not None:
        cases = [c for c in cases if c.topic in topics]
    return cases


def prompt_version() -> str:
    with open(_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)["prompt_version"]


def build_prompt(case: GoldenCase) -> str:
    return case.input_text


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)


def extract_json(raw_text: str) -> dict | None:
    """Best-effort JSON extraction — local models frequently wrap the answer in prose or markdown
    fences despite instructions not to."""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(raw_text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


@dataclass(frozen=True)
class ScoreResult:
    case_id: str
    invalid_json: bool
    exact_match: bool
    field_results: dict[str, bool]

    @property
    def field_accuracy(self) -> float:
        if not self.field_results:
            return 0.0
        return sum(self.field_results.values()) / len(self.field_results)


def score_response(case: GoldenCase, parsed: dict | None) -> ScoreResult:
    if parsed is None:
        return ScoreResult(case_id=case.id, invalid_json=True, exact_match=False,
                            field_results={k: False for k in case.expected})

    field_results = {}
    for field, expected_value in case.expected.items():
        if field == "unsupported_topics":
            actual = [str(t).lower() for t in (parsed.get(field) or [])]
            if not expected_value:
                field_results[field] = actual == []
            else:
                field_results[field] = all(
                    any(exp.lower() in a for a in actual) for exp in expected_value
                )
        else:
            field_results[field] = parsed.get(field) == expected_value

    return ScoreResult(
        case_id=case.id, invalid_json=False,
        exact_match=all(field_results.values()),
        field_results=field_results,
    )
