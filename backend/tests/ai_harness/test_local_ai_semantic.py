"""Tier B: local Ollama semantic regression against the golden dataset. Gated behind the
`local_ai` marker (needs TEST_MODE=LOCAL_AI/FULL_AI/NIGHTLY) — a plain `pytest` run never reaches
this file. Uses whichever model the measured benchmark recommended for LOCAL_FAST (see
tests/ai_harness/bench.py) unless AI_TEST_LOCAL_FAST_MODEL overrides it.

Failure policy: a failing case here means "the local model didn't reliably extract this," not
"the golden expectation is wrong." Local-model disagreement is surfaced, never used to silently
redefine expected behavior.
"""

import pytest

from tests.ai_harness import report
from tests.ai_harness.cache import ResponseCache
from tests.ai_harness.config import model_for_role, provider_for_role
from tests.ai_harness.factory import get_provider
from tests.ai_harness.golden_dataset import SYSTEM_PROMPT, build_prompt, extract_json, load_cases, prompt_version, score_response

_cache = ResponseCache()
_ROLE = "local_fast"


@pytest.mark.local_ai
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.id)
def test_local_fast_model_matches_golden_case(case):
    provider_name = provider_for_role(_ROLE)
    model = model_for_role(_ROLE)
    cache_key = dict(provider=provider_name, model=model, prompt_version=prompt_version(),
                      system_prompt=SYSTEM_PROMPT, input_text=case.input_text)

    cached = _cache.get(**cache_key)
    if cached is not None:
        raw_text, latency_ms, cache_hit = cached["text"], cached.get("latency_ms", 0.0), True
    else:
        response = get_provider(_ROLE).complete(build_prompt(case), system_prompt=SYSTEM_PROMPT)
        raw_text, latency_ms, cache_hit = response.text, response.latency_ms, False
        _cache.set(**cache_key, response={"text": raw_text, "latency_ms": latency_ms})

    result = score_response(case, extract_json(raw_text))
    report.record(case_id=case.id, topic=case.topic, provider=provider_name, model=model,
                  latency_ms=latency_ms, tokens_in=None, tokens_out=None, cache_hit=cache_hit,
                  passed=result.exact_match, field_results=result.field_results,
                  invalid_json=result.invalid_json)

    assert result.field_accuracy >= 0.5, f"{case.id}: field_results={result.field_results} raw={raw_text!r}"
