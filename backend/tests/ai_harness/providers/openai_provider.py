"""OpenAI-backed test LLM provider — the production-model tier. Gated by OPENAI_API_KEY; never
hardcoded, never logged. Test infrastructure only."""

from __future__ import annotations

import os
import time

from tests.ai_harness.provider_base import LLMResponse, TestLLMProvider


class OpenAITestLLMProvider(TestLLMProvider):
    def __init__(self, model: str):
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("AI_TEST_PROVIDER=openai requires OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def complete(self, prompt: str, *, system_prompt: str = "") -> LLMResponse:
        start = time.monotonic()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(model=self.model, messages=messages)
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResponse(
            text=text, latency_ms=(time.monotonic() - start) * 1000,
            tokens_in=usage.prompt_tokens if usage else None,
            tokens_out=usage.completion_tokens if usage else None,
            model=self.model, provider="openai",
        )
