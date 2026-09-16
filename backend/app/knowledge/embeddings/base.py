from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    provider_name: str
    model_name: str
    dim: int

    @abstractmethod
    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """One embedding vector per input text, same order, length == self.dim.

        `is_query` distinguishes a search query from a stored document/chunk — some models (e.g.
        the E5 family) are trained with different "query: "/"passage: " instruction prefixes and
        score measurably worse without them. Providers that don't need the distinction ignore it;
        it defaults to False (a document/chunk) since that's the far more common call site
        (indexing), and retrieval.py explicitly passes `is_query=True` for the query side."""
