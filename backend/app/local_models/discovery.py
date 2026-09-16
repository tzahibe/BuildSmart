"""Read-only Ollama discovery.

Confirmed live against this machine's Ollama (`/api/tags`): `llama3.2:latest` reports
`capabilities=["completion", "tools"]` and `gemma4:26b` reports
`capabilities=["completion", "vision", "tools", "thinking"]` — **neither declares "embedding"**.
Capabilities are always read from Ollama's own response, never assumed from a model's name or
size; a name like "embed" or "nomic" proves nothing on its own.

This module never downloads, pulls, or loads a model. It only calls `GET /api/tags` (and, as a
fallback for older Ollama versions that omit capabilities there, `POST /api/show` per model).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "http://localhost:11434"

#: Rough size threshold above which a model is flagged for 32GB-RAM caution. This is a flag for
#: the benchmark to report, never a reason to exclude a model — the measured benchmark decides
#: suitability, not this heuristic.
RAM_CAUTION_BYTES = 8 * 1024 ** 3


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size_bytes: int
    parameter_size: str
    quantization: str
    capabilities: tuple[str, ...]

    @property
    def has_embedding_capability(self) -> bool:
        return "embedding" in self.capabilities

    @property
    def ram_caution(self) -> bool:
        return self.size_bytes >= RAM_CAUTION_BYTES


@dataclass(frozen=True)
class OllamaStatus:
    available: bool
    base_url: str
    models: tuple[OllamaModel, ...] = ()
    error: str | None = None

    @property
    def embedding_capable_models(self) -> tuple[OllamaModel, ...]:
        return tuple(m for m in self.models if m.has_embedding_capability)

    @property
    def completion_capable_models(self) -> tuple[OllamaModel, ...]:
        return tuple(m for m in self.models if "completion" in m.capabilities)


def _capabilities_via_show(client: httpx.Client, base_url: str, name: str) -> tuple[str, ...]:
    try:
        resp = client.post(f"{base_url}/api/show", json={"model": name}, timeout=5.0)
        resp.raise_for_status()
        return tuple(resp.json().get("capabilities") or ())
    except httpx.HTTPError:
        return ()


def discover_ollama(base_url: str | None = None, *, timeout: float = 2.0) -> OllamaStatus:
    """Read-only discovery. Never raises — an unreachable Ollama is a normal, reportable state,
    not an error the caller must handle specially."""
    base_url = base_url or DEFAULT_BASE_URL
    try:
        with httpx.Client() as client:
            resp = client.get(f"{base_url}/api/tags", timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()

            models = []
            for entry in payload.get("models", []):
                details = entry.get("details", {})
                capabilities = tuple(entry.get("capabilities") or ())
                if not capabilities:
                    capabilities = _capabilities_via_show(client, base_url, entry["name"])
                models.append(OllamaModel(
                    name=entry["name"],
                    size_bytes=int(entry.get("size", 0)),
                    parameter_size=details.get("parameter_size", "?"),
                    quantization=details.get("quantization_level", "?"),
                    capabilities=capabilities,
                ))
            return OllamaStatus(available=True, base_url=base_url, models=tuple(models))
    except httpx.HTTPError as e:
        return OllamaStatus(available=False, base_url=base_url, error=str(e))


def recommend_candidates(status: OllamaStatus) -> dict:
    """A heuristic starting point only — the real LOCAL_FAST/LOCAL_STRONG/NOT_SUITABLE decision is
    made by `tests.ai_harness.bench`'s measured benchmark, never by this function alone."""
    if not status.available:
        return {"available": False, "candidates": [], "note": "Ollama unreachable at " + status.base_url}

    completion_models = sorted(status.completion_capable_models, key=lambda m: m.size_bytes)
    candidates = [{
        "name": m.name,
        "size_bytes": m.size_bytes,
        "parameter_size": m.parameter_size,
        "ram_caution": m.ram_caution,
        "heuristic_role_guess": "LOCAL_FAST" if i == 0 else "LOCAL_STRONG",
    } for i, m in enumerate(completion_models)]

    return {
        "available": True,
        "candidates": candidates,
        "embedding_capable_models": [m.name for m in status.embedding_capable_models],
        "note": (
            "no installed model declares embedding capability — Knowledge RAG will use the "
            "deterministic hash embedder until a dedicated embedding model is pulled (not done "
            "automatically)"
            if not status.embedding_capable_models else None
        ),
    }
