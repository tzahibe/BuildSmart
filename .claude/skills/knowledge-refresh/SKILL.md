---
name: "knowledge-refresh"
description: "Mandatory preflight before architecture, behavioral, planning, debugging, or feature work on this repo: refresh the Project Knowledge RAG index (cheap no-op if nothing changed), read docs/PROJECT_STATE.md, then retrieve targeted, status-ranked evidence for the task. Skip only for trivial work (typo, formatting, isolated CSS, mechanical rename, generated timing-noise cleanup)."
argument-hint: "The task/question to retrieve knowledge for"
compatibility: "Requires backend/app/knowledge (Project Knowledge RAG) to be present"
metadata:
  author: "project-knowledge-rag"
user-invocable: true
disable-model-invocation: false
---

## User Input

```text
$ARGUMENTS
```

## What this skill does

This repo has a derived retrieval layer (`backend/app/knowledge/`) over `docs/**/*.md` and
`specs/*/{spec,plan,research}.md` — see `docs/PROJECT_KNOWLEDGE_RAG.md`. Git/Markdown remains the
source of truth; this index is only a cache on top of it, and it can go stale the moment someone
edits a doc without re-indexing, or the moment a doc's own prose lags what actually got merged
(this has happened for real in this repo more than once — see `docs/PROJECT_STATE.md`'s
corrected-facts history). Treating a stale index or a stale doc's own wording as current is
exactly the mistake this skill exists to prevent.

**When to run this**: before architecture, behavioral, planning, debugging, or feature work.
**When to skip it**: trivial work — a typo, formatting, isolated CSS, a mechanical rename,
generated timing-noise cleanup. Nobody needs a knowledge preflight to fix a typo.

Run Steps A–D below, from `backend/`, in order.

## Step A — Incremental refresh

```
uv run python -m app.knowledge.cli index --changed
```

This is a sha256 checksum diff: it detects changed/new documents, re-indexes only those (updating
embeddings only for their chunks), and leaves every unchanged document's index entry exactly as it
was. When nothing changed, this costs one filesystem stat + hash per source file and does zero
embedding work — a genuinely cheap no-op, never a full rebuild. **Never skip this step and never
replace it with a full `index` (no `--changed`)** — a full rebuild is for `EmbeddingConfigMismatch`
recovery (see below), not routine use.

Multiple agents may run against this same shared index concurrently. `index --changed` is
single-writer safe (`app/knowledge/lock.py`): if another agent is already refreshing it, this
call waits briefly, and if that other refresh is still running past a bounded timeout, it reports
`deferred` and proceeds using the last known-good index rather than starting a second concurrent
writer or forcing a rebuild. A deferred refresh is not a failure — retrieval below is unaffected
either way (reads never block on a writer).

If this reports `EmbeddingConfigMismatch`, that's the safety check working (the embedding
provider/model/dimension changed since the index was built) — run `uv run python -m
app.knowledge.cli clear && uv run python -m app.knowledge.cli index` to rebuild, then continue.

### Embedding provider for this step

Prefer real multilingual semantic embeddings when available in your environment:

```
KNOWLEDGE_EMBEDDING_PROVIDER=huggingface KNOWLEDGE_EMBEDDING_MODEL=BAAI/bge-m3 \
  uv run python -m app.knowledge.cli index --changed
```

`BAAI/bge-m3` is the evaluated, recommended semantic model (best of 3 multilingual candidates
tested on this repo's corpus — see `docs/PROJECT_KNOWLEDGE_RAG.md`'s embedding evaluation). This
requires the `knowledge-embeddings` extra (`sentence-transformers` + `torch`), which is **not**
installed in the shared dev `.venv` by policy (installing it there once already pruned unrelated
packages another session needed — see that doc's isolated-environment guidance). **Do not run
`uv sync --extra knowledge-embeddings` against the shared main checkout.** If you need it, use an
isolated environment (a `git worktree` with its own `.venv`, or a scratch clone) — never mutate
another active session's environment to get it.

**If the command above fails** (extra not installed, model unavailable in this environment): that
failure is the intended, honest behavior — `huggingface` never silently falls back and pretends
semantic retrieval happened. Re-run the same command **without** `KNOWLEDGE_EMBEDDING_PROVIDER` set
(auto-detect: an embedding-capable Ollama model if one is installed, else the deterministic
hash+FTS5 fallback). The hash+FTS5 default is fully supported and this preflight remains valuable
and mandatory either way — bge-m3 is a strictly-better-when-available upgrade, not a requirement.

## Step B — Read current project state

Always read `docs/PROJECT_STATE.md` in full before architecture/planning/behavioral work. It is
deliberately compact (current state only, not history) and is the first source of current
implementation status — read it before retrieving anything else.

## Step C — Retrieve relevant knowledge

Before modifying behavior, run a targeted query or context-pack request for the task at hand
instead of manually opening many documents:

```
uv run python -m app.knowledge.cli context "<task description>"     # bounded, PROJECT_STATE-first
uv run python -m app.knowledge.cli search "<specific term>" --json  # a narrow lookup
```

Example task shapes this handles well: multi-level, massing/L-massing, wet rooms, laundry,
geometry, validation constraints, `public_open_side`, requirements semantics, historical
architecture decisions, feature implementation status, "why does this code behave this way?".

Add `--historical` (context) or `--status HISTORICAL --status SUPERSEDED` (search) only when the
task explicitly needs superseded/historical material (e.g. "why did we reject X").

## Step D — Respect document status

Inspect the `status`/`capability_status` metadata on every retrieved result. Priority, highest
first: `IMPLEMENTED_MERGED` > `IMPLEMENTED` (branch-only or not-yet-wired — check the doc's own
text for which) > `ACTIVE_RESEARCH` > `SUPERSEDED`/historical investigation docs. **Never treat an
`ACTIVE_RESEARCH` or `SUPERSEDED` report as current production truth when an `IMPLEMENTED`/
`IMPLEMENTED_MERGED` source exists** — the retrieval ranking already down-weights
historical/superseded material for this reason, but the final judgment call is yours: `docs/
PROJECT_STATE.md` plus the actual current git state (a quick `git log`/`git branch --contains` if
anything looks uncertain) remain authoritative for feature status, above any single doc's own
prose. A doc can say "not yet built" and be wrong the moment someone else merges — this has
happened for real in this repo.

## Reporting (for substantive tasks)

Record briefly in your working report — never dump the whole context pack:

```
Knowledge preflight:
- index refresh: changed / unchanged / deferred
- active embedding provider/model: e.g. huggingface/BAAI/bge-m3, or hash (fallback, and why)
- knowledge topics queried: e.g. "multi-level phase 1 status", "laundry room allocation"
- highest-priority docs/context used: path + status, e.g.
  docs/MULTI_LEVEL_PHASE_1_IMPLEMENTATION_REPORT.md (IMPLEMENTED, commit 4bdebd4)
```
