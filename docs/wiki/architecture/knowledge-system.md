# Knowledge System

Status: IMPLEMENTED_MERGED

## Current behavior

A three-layer knowledge system, Wiki-first as of this page:

1. **Code + tests + current git state** — final truth about what is actually implemented. Always
   outranks documentation of any kind.
2. **This Wiki** (`docs/wiki/`) — canonical, compact, human-readable "what is true now," one page
   per major subsystem/feature, built only from already-approved/closed work.
3. **Raw reports/specs/investigations** (`docs/*.md`, `specs/*/`) — history, rationale, evidence,
   experiments. Never treated as current truth once a Wiki page or newer report supersedes them.
4. **RAG** (`backend/app/knowledge/`) — the discovery/search layer across both the Wiki and raw
   sources. Hybrid retrieval: FTS5 keyword search + vector search (hash-embedding fallback, or
   `BAAI/bge-m3` via the opt-in `huggingface` provider — evaluated best of 3 multilingual
   candidates on this corpus, real Hebrew+English improvement, never auto-selected), independently
   normalized before a bounded status/source-type rerank. SQLite storage (`KnowledgeStore` ABC),
   WAL mode, a single-writer `flock`-based lock (`app/knowledge/lock.py`) so concurrent agents
   never race a shared index — a deferred refresh reads the last known-good index rather than
   forcing a rebuild.

Agents are never required to run vector search first — the mandatory preflight
(`.claude/skills/knowledge-refresh/SKILL.md`) is: refresh incrementally, read `PROJECT_STATE.md`/
Wiki index, read the relevant canonical Wiki page, then use RAG only when deeper evidence/history
is actually needed, then verify against code/tests before changing behavior.

A parallel, narrower system, the **Cheap AI Test Harness** (`backend/tests/ai_harness/`), is test
infrastructure, not part of this knowledge layer: deterministic/local-Ollama/production-OpenAI
tiers for testing semantic behavior cheaply, plus an optional local-model failure-triage assistant
for a pytest run's own failures. Neither ever redefines expected behavior — a local model's
opinion is advisory only.

## Authoritative implementation

- `backend/app/knowledge/{config,chunking,doc_status,indexer,retrieval,tokens,context_pack,tool,
  cli,lock}.py`, `embeddings/{base,hash_provider,ollama_provider,openai_provider,
  huggingface_provider,factory}.py`, `store/{base,sqlite_store,factory}.py`.
- `backend/app/local_models/discovery.py` (read-only Ollama capability discovery).
- `backend/tests/ai_harness/` (harness), `backend/tests/regression_corpus/` (the real, frozen
  432-context regression corpus, zero LLM calls).
- `.claude/skills/knowledge-refresh/SKILL.md`, root `CLAUDE.md`.
- This Wiki: `docs/wiki/`.

## Current constraints/invariants

- `huggingface`/`bge-m3` is opt-in only, never auto-selected, and never silently falls back —
  initialization failure raises clearly. `uv sync --extra knowledge-embeddings` must never run
  against the shared main `.venv`; use an isolated environment.
- Index-compatibility metadata (`embedding_provider`, `embedding_model`, `embedding_dim`) is
  checked on every incremental refresh; a mismatch forces an explicit `knowledge clear && knowledge
  index`, never a silent vector mix.
- Only one writer may hold the index-refresh lock at a time; a deferred agent must never force a
  rebuild. Reads remain available throughout (WAL mode).
- Only completed/approved behavior updates canonical Wiki pages — an investigation report never
  automatically rewrites one.
- A local test-triage model can never convert a failing test into a pass, and its output is never
  merge/release evidence.

## Supersedes

The original "RAG-first" framing (retrieval as the mandatory first source for every substantive
task) — this Wiki-first + RAG-hybrid model replaces it. The underlying RAG stack itself
(hybrid retrieval, `KnowledgeStore`, metadata/status reranking, evaluation harness, incremental
indexing, CLI) is preserved unchanged in mechanism; only its role in the agent workflow changed.

## Known follow-ups

- A dedicated Postgres+pgvector `KnowledgeStore` implementation (documented, not built — SQLite
  remains sufficient for this corpus size).
- Pulling a dedicated Ollama embedding model as a lighter alternative to `bge-m3`.
- `KNOWLEDGE_EMBEDDING_DEVICE=mps` acceleration (wired, not benchmarked).

## Evidence/history

`docs/PROJECT_KNOWLEDGE_RAG.md` (full RAG architecture + the 3-candidate embedding evaluation),
`docs/AI_TEST_HARNESS.md` (the test harness + local test-triage assistant).

## Last verified against git

`1d648c3` (main HEAD at authoring time; this page and the Wiki pivot land in a later commit on
top of it).
