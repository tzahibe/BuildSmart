"""Hugging Face sentence-transformers embedding provider — local inference, no external API,
CPU-by-default (Apple Silicon MPS may be used but is never required). Only constructed when
`KNOWLEDGE_EMBEDDING_PROVIDER=huggingface` is explicitly set (never part of the auto-detect
chain), and any failure here (missing dependency, model that fails to load/download) raises
immediately rather than silently degrading to the hash fallback — see factory.py's docstring for
why: silently downgrading would make an evaluation run look semantic when it actually used hash
embeddings.

See docs/PROJECT_KNOWLEDGE_RAG.md's embedding-model evaluation for why the selected default model
was chosen over the other two multilingual candidates that were benchmarked (intfloat/
multilingual-e5-base, BAAI/bge-m3, sentence-transformers/paraphrase-multilingual-mpnet-base-v2).
"""

from __future__ import annotations

from typing import Any

from app.knowledge.embeddings.base import EmbeddingProvider

#: Model families trained with an instruction prefix distinguishing a search query from a stored
#: passage — a real correctness requirement for these models, not a style choice. E5-family
#: models score measurably worse without "query: "/"passage: " prefixes. Matched by substring
#: against the model name so both "intfloat/multilingual-e5-base" and any future e5 variant match.
_PREFIX_BY_FAMILY = {
    "e5": ("query: ", "passage: "),
}


def _prefixes_for(model_name: str) -> tuple[str, str]:
    lowered = model_name.lower()
    for family, prefixes in _PREFIX_BY_FAMILY.items():
        if family in lowered:
            return prefixes
    return ("", "")


def _embedding_dim(model: Any) -> int:
    # sentence-transformers 6.x renamed this; support both so we don't chase every release.
    getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
    return getter()


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str, *, device: str = "cpu", model: Any = None):
        """`model` is a test seam — mirrors `LocalArchitectModelGateway`'s injectable
        tokenizer/model pattern (app/architect/local_gateway.py) so hermetic tests never need the
        real 'knowledge-embeddings' extra installed or a model downloaded. Production callers
        never pass it; `factory.py` never passes it either."""
        if model is not None:
            self._model = model
        else:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "KNOWLEDGE_EMBEDDING_PROVIDER=huggingface requires the 'knowledge-embeddings' "
                    "extra: `uv sync --extra knowledge-embeddings`."
                ) from e
            self._model = SentenceTransformer(model_name, device=device)

        self._model.eval()  # deterministic inference — no dropout/train-mode randomness
        self._query_prefix, self._passage_prefix = _prefixes_for(model_name)
        self.provider_name = "huggingface"
        self.model_name = model_name
        self.dim = _embedding_dim(self._model)

    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        prefix = self._query_prefix if is_query else self._passage_prefix
        prefixed = [f"{prefix}{t}" for t in texts] if prefix else list(texts)

        try:
            import torch

            no_grad = torch.no_grad
        except ImportError:
            from contextlib import nullcontext as no_grad

        with no_grad():
            vectors = self._model.encode(
                prefixed,
                batch_size=32,
                normalize_embeddings=True,  # cosine similarity assumes unit-normalized vectors
                convert_to_numpy=True,
                show_progress_bar=False,
            )

        if len(vectors) and len(vectors[0]) != self.dim:
            raise RuntimeError(
                f"{self.model_name} produced {len(vectors[0])}-dim vectors but the model reported "
                f"{self.dim} at construction — refusing to silently index a dimension mismatch."
            )
        # .tolist() (numpy arrays, torch tensors) also converts nested numpy scalars to native
        # Python floats, which plain JSON serialization elsewhere requires; a fake test model
        # returning plain lists already has native floats, so a plain copy is enough there.
        return vectors.tolist() if hasattr(vectors, "tolist") else [list(v) for v in vectors]
