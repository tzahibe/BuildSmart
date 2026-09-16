"""Role-based provider selection — mirrors `app/architect/gateway.py`'s lazy-import factory
pattern. `role` is one of "local_fast" | "local_strong" | "production"."""

from __future__ import annotations

from tests.ai_harness.config import model_for_role, ollama_base_url_from_env, provider_for_role
from tests.ai_harness.provider_base import TestLLMProvider


def get_provider(role: str) -> TestLLMProvider:
    provider_name = provider_for_role(role)
    model = model_for_role(role)

    if provider_name == "mock":
        from tests.ai_harness.providers.mock_provider import MockTestLLMProvider

        return MockTestLLMProvider(model)
    if provider_name == "ollama":
        from tests.ai_harness.providers.ollama_provider import OllamaTestLLMProvider

        return OllamaTestLLMProvider(model, ollama_base_url_from_env())
    if provider_name == "openai":
        from tests.ai_harness.providers.openai_provider import OpenAITestLLMProvider

        return OpenAITestLLMProvider(model)
    raise RuntimeError(f"Unknown provider {provider_name!r} for role {role!r}")
