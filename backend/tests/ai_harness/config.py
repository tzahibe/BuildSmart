"""Runtime configuration for the AI test harness — env vars only.

TEST_MODE=FAST|REGRESSION|LOCAL_AI|FULL_AI|NIGHTLY   (default: FAST)
AI_TEST_PROVIDER=mock|ollama|openai                  (default: role-dependent — see provider_for_role)
AI_TEST_LOCAL_FAST_MODEL / AI_TEST_LOCAL_STRONG_MODEL / AI_TEST_PRODUCTION_MODEL
    — all unset by default. If unset, `model_for_role` reads `reports/model_recommendation.json`,
    the file `bench.py` writes after actually measuring the installed Ollama models — never a
    hardcoded default model name for a local role. An explicit env var always overrides it.
OLLAMA_BASE_URL                                      (default: http://localhost:11434, shared with
                                                       the Knowledge RAG's Ollama embedding provider)
"""

from __future__ import annotations

import json
import os

VALID_TEST_MODES = ("FAST", "REGRESSION", "LOCAL_AI", "FULL_AI", "NIGHTLY")

_ROLE_ENV_VAR = {
    "local_fast": "AI_TEST_LOCAL_FAST_MODEL",
    "local_strong": "AI_TEST_LOCAL_STRONG_MODEL",
    "production": "AI_TEST_PRODUCTION_MODEL",
}

_RECOMMENDATION_PATH = os.path.join(os.path.dirname(__file__), "reports", "model_recommendation.json")


def test_mode_from_env() -> str:
    mode = os.environ.get("TEST_MODE", "FAST").strip().upper()
    if mode not in VALID_TEST_MODES:
        raise RuntimeError(f"Unknown TEST_MODE: {mode!r} (expected one of {VALID_TEST_MODES})")
    return mode


def ollama_base_url_from_env() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _recommendation_for(role: str) -> dict | None:
    if not os.path.exists(_RECOMMENDATION_PATH):
        return None
    with open(_RECOMMENDATION_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get(role)


def provider_for_role(role: str) -> str:
    override = os.environ.get("AI_TEST_PROVIDER")
    if override:
        return override
    return "openai" if role == "production" else "ollama"


def model_for_role(role: str) -> str:
    """Never a hardcoded default for local_fast/local_strong — those come from the measured
    benchmark's recommendation, or an explicit env override. production defaults to the same
    model app/requirements/parser.py itself defaults to, since that's genuinely fixed today."""
    env_var = _ROLE_ENV_VAR[role]
    override = os.environ.get(env_var)
    if override:
        return override

    recommendation = _recommendation_for(role)
    if recommendation and recommendation.get("verdict") != "NOT_SUITABLE":
        if recommendation["verdict"] == "LOCAL_FAST_LIMITED":
            import warnings

            warnings.warn(
                f"{recommendation['model']} is LOCAL_FAST_LIMITED, not a generally reliable "
                f"LOCAL_FAST model — reliable on {sorted(recommendation.get('reliable_topics', {}))}, "
                f"weak on {sorted(recommendation.get('weak_topics', {}))}. A failure on a weak "
                f"topic is expected model limitation, not necessarily a regression.",
                stacklevel=2,
            )
        return recommendation["model"]

    if role == "production":
        return "gpt-5-nano"

    reason = f" ({recommendation['verdict']}: {recommendation.get('reason', '')})" if recommendation else ""
    raise RuntimeError(
        f"No model configured for role={role!r}{reason}. Set {env_var}, or run "
        f"`uv run python -m tests.ai_harness.bench` to generate a measured recommendation."
    )
