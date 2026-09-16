"""Runtime configuration for the Project Knowledge RAG index — read from environment variables
only; nothing here is hardcoded or committed to source control.

KNOWLEDGE_EMBEDDING_PROVIDER=ollama|hash|openai   (default: auto-detect, see embeddings/factory.py)

    Left unset, the factory asks `app.local_models.discovery` for an installed Ollama model whose
    `/api/show` response actually lists "embedding" in its capabilities, and uses it if found.
    Today neither installed model (`llama3.2`, `gemma4:26b`) declares that capability, so the
    factory falls back to `hash` and logs that semantic embeddings are not enabled — it never
    silently repurposes a completion model as an embedder.

KNOWLEDGE_EMBEDDING_MODEL     — which Ollama model to embed with (only read if the resolved
                                 provider is "ollama"; no default — must name a capability-verified
                                 model)
KNOWLEDGE_SQLITE_PATH         — path to the SQLite index file (default: app/knowledge/data/index.db)
KNOWLEDGE_SOURCE_GLOBS        — comma-separated glob list, relative to the repo root (default below)
OLLAMA_BASE_URL               — shared with the AI test harness (default: http://localhost:11434)

See `backend/.env.example` for a template.
"""

import os
from dataclasses import dataclass, field

DEFAULT_SOURCE_GLOBS = (
    "docs/**/*.md",
    "specs/*/spec.md",
    "specs/*/plan.md",
    "specs/*/research.md",
)

#: Globs that must never be indexed even if a broader KNOWLEDGE_SOURCE_GLOBS would match them —
#: images, task checklists (timing noise, not documentation), and stale worktree copies of docs.
EXCLUDED_GLOBS = (
    "docs/images/**",
    "**/tasks.md",
    ".claude/worktrees/**",
)


@dataclass(frozen=True)
class KnowledgeConfig:
    embedding_provider_override: str | None
    embedding_model: str | None
    sqlite_path: str
    source_globs: tuple[str, ...] = field(default_factory=lambda: DEFAULT_SOURCE_GLOBS)
    ollama_base_url: str = "http://localhost:11434"


def config_from_env(repo_root: str) -> KnowledgeConfig:
    globs_raw = os.environ.get("KNOWLEDGE_SOURCE_GLOBS")
    globs = tuple(g.strip() for g in globs_raw.split(",") if g.strip()) if globs_raw else DEFAULT_SOURCE_GLOBS

    default_db = os.path.join(repo_root, "backend", "app", "knowledge", "data", "index.db")
    return KnowledgeConfig(
        embedding_provider_override=(os.environ.get("KNOWLEDGE_EMBEDDING_PROVIDER") or "").strip().lower() or None,
        embedding_model=os.environ.get("KNOWLEDGE_EMBEDDING_MODEL") or None,
        sqlite_path=os.environ.get("KNOWLEDGE_SQLITE_PATH", default_db),
        source_globs=globs,
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
