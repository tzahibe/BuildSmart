from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    latency_ms: float
    tokens_in: int | None
    tokens_out: int | None
    model: str
    provider: str


class TestLLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, system_prompt: str = "") -> LLMResponse: ...
