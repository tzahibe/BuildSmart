"""Ollama-backed test LLM provider. Test infrastructure only — application code must never import
this or depend directly on Ollama."""

from __future__ import annotations

import time

import httpx

from tests.ai_harness.provider_base import LLMResponse, TestLLMProvider


class OllamaTestLLMProvider(TestLLMProvider):
    def __init__(self, model: str, base_url: str):
        self.model = model
        self._base_url = base_url

    def complete(self, prompt: str, *, system_prompt: str = "") -> LLMResponse:
        start = time.monotonic()
        with httpx.Client() as client:
            resp = client.post(
                f"{self._base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "system": system_prompt, "stream": False},
                timeout=180.0,
            )
            resp.raise_for_status()
            data = resp.json()
        return LLMResponse(
            text=data.get("response", ""), latency_ms=(time.monotonic() - start) * 1000,
            tokens_in=data.get("prompt_eval_count"), tokens_out=data.get("eval_count"),
            model=self.model, provider="ollama",
        )
