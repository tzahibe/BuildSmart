"""Hermetic unit tests for HuggingFaceEmbeddingProvider — a FAKE model is injected via the same
test seam app/architect/local_gateway.py established (constructor-injectable model), so these
never download a real model or require the 'knowledge-embeddings' extra to be installed. Real
model quality is measured separately and manually via tests/knowledge/eval/run_eval.py — these
tests only prove the provider's mechanics (dims, batching, prefixing, error handling, wiring into
retrieval/indexing), never semantic quality, so a passing hermetic test is never mistaken for
evidence a model retrieves well.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from app.knowledge import doc_status
from app.knowledge.config import KnowledgeConfig
from app.knowledge.embeddings.huggingface_provider import HuggingFaceEmbeddingProvider
from app.knowledge.indexer import EmbeddingConfigMismatch, KnowledgeIndexer
from app.knowledge.retrieval import search
from app.knowledge.store.base import ChunkRecord
from app.knowledge.store.sqlite_store import SqliteKnowledgeStore


class _FakeModel:
    """Deterministic hashed bag-of-words — enough to prove wiring, never semantic understanding."""

    def __init__(self, dim: int = 8):
        self._dim = dim
        self.eval_called = False
        self.encode_calls: list[list[str]] = []

    def eval(self):
        self.eval_called = True

    def get_sentence_embedding_dimension(self):
        return self._dim

    def encode(self, texts, **kwargs):
        self.encode_calls.append(list(texts))
        vectors = []
        for t in texts:
            v = [0.0] * self._dim
            for word in t.lower().split():
                idx = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self._dim
                v[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors  # plain list of lists — exercises the no-.tolist() fallback path


def test_provider_creation_calls_eval_mode():
    fake = _FakeModel()
    provider = HuggingFaceEmbeddingProvider("some/model", model=fake)
    assert fake.eval_called, "must call .eval() for deterministic inference"
    assert provider.provider_name == "huggingface"
    assert provider.model_name == "some/model"


def test_embedding_dimension_reported_from_model():
    provider = HuggingFaceEmbeddingProvider("some/model", model=_FakeModel(dim=16))
    assert provider.dim == 16


def test_batch_embedding_shape_and_type():
    provider = HuggingFaceEmbeddingProvider("some/model", model=_FakeModel(dim=8))
    vectors = provider.embed(["one two", "three four five"])
    assert len(vectors) == 2
    assert all(len(v) == 8 for v in vectors)
    assert all(isinstance(x, float) for v in vectors for x in v)


def test_deterministic_output_shape_across_calls():
    provider = HuggingFaceEmbeddingProvider("some/model", model=_FakeModel(dim=8))
    a = provider.embed(["repeat this text"])
    b = provider.embed(["repeat this text"])
    assert a == b


def test_e5_model_gets_query_and_passage_prefixes():
    fake = _FakeModel()
    provider = HuggingFaceEmbeddingProvider("intfloat/multilingual-e5-base", model=fake)
    provider.embed(["find me a house"], is_query=True)
    provider.embed(["a document about houses"], is_query=False)
    assert fake.encode_calls[0] == ["query: find me a house"]
    assert fake.encode_calls[1] == ["passage: a document about houses"]


def test_non_e5_model_gets_no_prefix():
    fake = _FakeModel()
    provider = HuggingFaceEmbeddingProvider("sentence-transformers/paraphrase-multilingual-mpnet-base-v2", model=fake)
    provider.embed(["a query"], is_query=True)
    assert fake.encode_calls[0] == ["a query"]


def test_dimension_mismatch_from_model_raises():
    class _BadDimModel(_FakeModel):
        def encode(self, texts, **kwargs):
            return [[0.0] * (self._dim + 1) for _ in texts]  # lies about its own dim

    provider = HuggingFaceEmbeddingProvider("some/model", model=_BadDimModel(dim=8))
    with pytest.raises(RuntimeError, match="dimension mismatch"):
        provider.embed(["text"])


def test_factory_never_auto_selects_huggingface(monkeypatch):
    """Safe-fallback requirement: huggingface only activates on explicit request, never via
    auto-detect — even if Ollama is unavailable, auto-detect must land on hash, not huggingface."""
    from app.knowledge.embeddings.factory import get_embedding_provider
    from app.local_models import discovery

    monkeypatch.setattr(discovery, "discover_ollama", lambda *a, **k: discovery.OllamaStatus(available=False, base_url="x"))
    cfg = KnowledgeConfig(embedding_provider_override=None, embedding_model=None, sqlite_path=":memory:")
    provider = get_embedding_provider(cfg)
    assert provider.provider_name == "hash"


def test_explicit_huggingface_without_model_raises_not_silently_falls_back():
    from app.knowledge.embeddings.factory import get_embedding_provider

    cfg = KnowledgeConfig(embedding_provider_override="huggingface", embedding_model=None, sqlite_path=":memory:")
    with pytest.raises(RuntimeError, match="KNOWLEDGE_EMBEDDING_MODEL"):
        get_embedding_provider(cfg)


def test_index_rebuild_required_when_embedding_dim_changes(tmp_path):
    cfg = KnowledgeConfig(embedding_provider_override="huggingface", embedding_model="model-a",
                           sqlite_path=str(tmp_path / "index.db"), source_globs=("docs/**/*.md",))
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n\nsome content\n")

    small_model = HuggingFaceEmbeddingProvider("model-a", model=_FakeModel(dim=8))
    idx = KnowledgeIndexer(cfg, store, small_model, repo_root=str(tmp_path))
    idx.index_all()

    # Same provider/model NAME, but a model whose actual dimension differs (e.g. a version bump
    # that changed output size without a name change) — the dim comparison must still catch it.
    bigger_model = HuggingFaceEmbeddingProvider("model-a", model=_FakeModel(dim=16))
    idx2 = KnowledgeIndexer(cfg, store, bigger_model, repo_root=str(tmp_path))
    with pytest.raises(EmbeddingConfigMismatch, match="dim="):
        idx2.index_changed()


def test_hybrid_retrieval_wiring_with_injected_model(tmp_path):
    """Proves the provider wires correctly into hybrid retrieval — NOT a semantic-quality claim
    (the fake model is hashed bag-of-words, same class of signal as the hash provider)."""
    doc_status.set_table_for_testing({
        "docs/HE.md": {"topic": "t", "doc_status": "IMPLEMENTED_MERGED", "confidence": "high"},
        "docs/EN.md": {"topic": "t", "doc_status": "IMPLEMENTED_MERGED", "confidence": "high"},
    })
    store = SqliteKnowledgeStore(str(tmp_path / "index.db"))
    embedder = HuggingFaceEmbeddingProvider("some/model", model=_FakeModel(dim=64))

    texts = {"docs/HE.md": "מסדרון ברוחב מינימלי בין החדרים", "docs/EN.md": "corridor width between rooms"}
    for doc_path, text in texts.items():
        record = ChunkRecord(chunk_id=f"{doc_path}::h::0", doc_path=doc_path, heading_path="h",
                              ordinal=0, text=text, embedding=embedder.embed([text])[0])
        store.upsert_document(doc_path, checksum=doc_path, chunks=[record])

    en_hits = search(store, embedder, "corridor width between rooms", top_k=2)
    he_hits = search(store, embedder, "מסדרון ברוחב מינימלי בין החדרים", top_k=2)
    assert en_hits[0].doc_path == "docs/EN.md"
    assert he_hits[0].doc_path == "docs/HE.md"
