"""Local Test Assistant — an optional, advisory triage step for deterministic test failures.

Tests remain the sole source of truth. This module NEVER converts a failing test into a pass,
is NEVER merge/release evidence on its own, and never causes a golden expectation to change — it
only summarizes/groups already-known failures (from real pytest output) and suggests where an
agent should look next, via the SAME role-based local-model abstraction as the rest of the AI
harness (see config.py/factory.py). If all tests pass, `triage_failures` is never called — no
model call is made just to report success.

Workflow: code change -> focused deterministic tests -> IF failures -> triage_failures() ->
{failure_groups, likely_modules, knowledge_topics, investigation_areas} -> the agent retrieves
relevant project knowledge (Knowledge RAG) for those topics -> the agent investigates. See
docs/AI_TEST_HARNESS.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from tests.ai_harness.cache import ResponseCache
from tests.ai_harness.config import model_for_role, provider_for_role
from tests.ai_harness.factory import get_provider
from tests.ai_harness.golden_dataset import extract_json

PROMPT_VERSION = "failure-triage-v1"

SYSTEM_PROMPT = (
    "You triage a pytest failure report for a software agent. You do NOT decide whether any "
    "failure is acceptable, and you never claim a test passed if it did not — that is not your "
    "job and your opinion is not merge/release evidence either way. Given a bounded list of "
    "failing tests (name, short error), output ONLY a JSON object: "
    '{"failure_groups": [{"label": str, "test_names": [str, ...], "likely_cause": str}], '
    '"likely_modules": [str, ...], "knowledge_topics": [str, ...], '
    '"investigation_areas": [str, ...]}. '
    "Group failures that plausibly share a root cause. knowledge_topics should be short phrases "
    'suitable for a documentation search (e.g. "wet-room semantics", "multi-level phase 1").'
)

_FAILED_LINE_RE = re.compile(r"^FAILED\s+(?P<name>\S+)(?:\s+-\s+(?P<error>.*))?$", re.MULTILINE)
_MAX_TESTS_IN_REPORT = 30


@dataclass(frozen=True)
class FailingTest:
    name: str
    error_summary: str = ""  # a line or two — never a full traceback


@dataclass(frozen=True)
class TriageReport:
    failure_groups: list[dict]
    likely_modules: list[str]
    knowledge_topics: list[str]
    investigation_areas: list[str]
    provider: str
    model: str
    cache_hit: bool
    raw_text: str


def parse_pytest_short_summary(output: str) -> list[FailingTest]:
    """Extracts `FAILED <nodeid> - <error>` lines from real pytest `-q`/short-summary output."""
    return [
        FailingTest(name=m.group("name"), error_summary=(m.group("error") or "").strip())
        for m in _FAILED_LINE_RE.finditer(output)
    ]


def _bounded_report(failing_tests: list[FailingTest]) -> str:
    """Bounded, never a full dump — at most `_MAX_TESTS_IN_REPORT` tests, each error truncated."""
    truncated = failing_tests[:_MAX_TESTS_IN_REPORT]
    payload = {
        "failing_tests": [{"name": t.name, "error": t.error_summary[:300]} for t in truncated],
        "omitted_count": max(0, len(failing_tests) - _MAX_TESTS_IN_REPORT),
    }
    return json.dumps(payload, sort_keys=True)


def triage_failures(failing_tests: list[FailingTest], *, role: str = "local_fast") -> TriageReport | None:
    """Returns None when there are no failures — deliberately never calls a model just to
    announce success (see module docstring)."""
    if not failing_tests:
        return None

    provider_name = provider_for_role(role)
    model = model_for_role(role)
    cache = ResponseCache()
    input_text = _bounded_report(failing_tests)
    cache_key = dict(provider=provider_name, model=model, prompt_version=PROMPT_VERSION,
                      system_prompt=SYSTEM_PROMPT, input_text=input_text)

    cached = cache.get(**cache_key)
    if cached is not None:
        raw_text, cache_hit = cached["text"], True
    else:
        response = get_provider(role).complete(input_text, system_prompt=SYSTEM_PROMPT)
        raw_text, cache_hit = response.text, False
        cache.set(**cache_key, response={"text": raw_text})

    parsed = extract_json(raw_text) or {}
    return TriageReport(
        failure_groups=parsed.get("failure_groups", []),
        likely_modules=parsed.get("likely_modules", []),
        knowledge_topics=parsed.get("knowledge_topics", []),
        investigation_areas=parsed.get("investigation_areas", []),
        provider=provider_name, model=model, cache_hit=cache_hit, raw_text=raw_text,
    )
