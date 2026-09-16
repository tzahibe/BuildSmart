"""Deterministic stub — tests the harness itself (provider selection, caching) with zero external
dependency. Application code must never import this; only test code does."""

from __future__ import annotations

import hashlib
import time

from tests.ai_harness.provider_base import LLMResponse, TestLLMProvider


class MockTestLLMProvider(TestLLMProvider):
    def __init__(self, model: str = "mock-v1"):
        self.model = model

    def complete(self, prompt: str, *, system_prompt: str = "") -> LLMResponse:
        start = time.monotonic()
        digest = hashlib.sha256(f"{system_prompt}|{prompt}".encode()).hexdigest()[:8]
        text = f'{{"mock_digest": "{digest}"}}'
        return LLMResponse(
            text=text, latency_ms=(time.monotonic() - start) * 1000,
            tokens_in=len(prompt.split()), tokens_out=len(text.split()),
            model=self.model, provider="mock",
        )
