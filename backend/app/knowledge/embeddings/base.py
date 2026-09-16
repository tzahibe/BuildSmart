from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    provider_name: str
    model_name: str
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """One embedding vector per input text, same order, length == self.dim."""
