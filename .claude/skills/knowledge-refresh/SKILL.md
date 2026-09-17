---
name: "knowledge-refresh"
description: "Mandatory preflight before architecture, behavioral, planning, debugging, or feature work on this repo: refresh the index (cheap no-op if nothing changed), read PROJECT_STATE.md/the Wiki index, read the relevant canonical Wiki page, then use RAG only for deeper evidence/history — and verify against code/tests before changing behavior. Skip only for trivial work (typo, formatting, isolated CSS, mechanical rename, generated timing-noise cleanup)."
argument-hint: "The task/question to retrieve knowledge for"
compatibility: "Requires backend/app/knowledge (Project Knowledge RAG) and docs/wiki/ to be present"
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

This repo has a **Wiki-first + RAG-hybrid** knowledge system. Authority, highest first:

1. **Code + tests + current git state** — final truth about what is actually implemented. Always
   outranks documentation, including this Wiki.
2. **`docs/wiki/`** — canonical, compact, human-readable "what is true now," one page per major
   subsystem/feature. Built only from already-approved/closed work.
3. **Raw reports/specs/investigations** (`docs/*.md`, `specs/*/`) — history, rationale, evidence,
   experiments. Not current truth once a Wiki page or newer report supersedes them.
4. **RAG** (`backend/app/knowledge/`, `docs/PROJECT_KNOWLEDGE_RAG.md`) — the discovery/search layer
   across both the Wiki and raw sources. A supporting layer, not the mandatory first source.

Git/Markdown remains the source of truth; the RAG index and even a Wiki page can go stale the
moment something merges without the corresponding page being updated — this has happened for real
in this repo more than once (see the Laundry and Multi-Level Wiki pages' own histories). Treating
a stale index, a stale Wiki page, or a stale report's own wording as current is exactly the
mistake this skill exists to prevent — Step 5 below exists specifically to catch it.

**When to run this**: before architecture, behavioral, planning, debugging, or feature work.
**When to skip it**: trivial work — a typo, formatting, isolated CSS, a mechanical rename,
generated timing-noise cleanup. Nobody needs a Wiki/RAG preflight to fix a typo. **Do not make
every task perform broad vector search** — most substantive tasks are answered by Step 3 alone.

Run Steps 1–5 below, from `backend/`, in order.

## Step 1 — Incremental refresh

```
uv run python -m app.knowledge.cli index --changed
```

A sha256 checksum diff: detects changed/new documents (Wiki pages included — they're indexed like
any other source), re-indexes only those, leaves every unchanged document exactly as it was. When
nothing changed, this costs one filesystem stat + hash per file and zero embedding work — a
genuinely cheap no-op, never a full rebuild.

**Concurrency**: multiple agents may run against this same shared index. `index --changed` is
single-writer safe (`app/knowledge/lock.py`): if another agent is already refreshing it, this
waits briefly; past a bounded timeout it reports `deferred` and proceeds using the last
known-good index rather than starting a second writer or forcing a rebuild. **If refresh is
deferred, report it explicitly** (see Reporting below) — it is not a failure, and retrieval stays
available throughout (WAL mode) either way.

If this reports `EmbeddingConfigMismatch`, that's the safety check working — run `uv run python -m
app.knowledge.cli clear && uv run python -m app.knowledge.cli index` to rebuild, then continue.

### Embedding provider for this step

Prefer real multilingual semantic embeddings when available:

```
KNOWLEDGE_EMBEDDING_PROVIDER=huggingface KNOWLEDGE_EMBEDDING_MODEL=BAAI/bge-m3 \
  uv run python -m app.knowledge.cli index --changed
```

`BAAI/bge-m3` is the evaluated, recommended semantic model (best of 3 multilingual candidates
tested on this corpus — see `docs/PROJECT_KNOWLEDGE_RAG.md`). Requires the `knowledge-embeddings`
extra, **not** installed in the shared dev `.venv` by policy — never run `uv sync --extra
knowledge-embeddings` against the shared main checkout; use an isolated environment (a `git
worktree` with its own `.venv`, or a scratch clone). Agents never call Hugging Face or
sentence-transformers directly — only through this CLI/the `KnowledgeStore` abstraction.

**If the command above fails**: that is the intended, honest behavior — `huggingface` never
silently falls back and pretends semantic retrieval happened. Re-run **without**
`KNOWLEDGE_EMBEDDING_PROVIDER` set (auto-detect: an embedding-capable Ollama model if installed,
else the hash+FTS5 fallback). Hash+FTS5 is fully supported and this preflight remains mandatory
either way — bge-m3 is a strictly-better-when-available upgrade, not a requirement.

## Step 2 — Read PROJECT_STATE.md / the Wiki index

Read `docs/PROJECT_STATE.md` (a compact, high-level index — capability list + links, not a
history) and `docs/wiki/INDEX.md` (the Wiki's own topic index). Together these answer "what
subsystems exist and what's their status" before you read anything else.

## Step 3 — Identify the relevant canonical Wiki page(s)

For the task at hand, open the specific page(s) under `docs/wiki/{architecture,features,decisions}/`
that PROJECT_STATE/the Wiki index pointed at. Each page is compact and answers: current behavior,
authoritative implementation (modules/commits/tests), current constraints, what it supersedes,
known follow-ups, and evidence/history pointers — everything a substantive task needs to start
from, without opening raw reports. **Most tasks stop here.**

## Step 4 — Retrieve raw evidence with RAG only when needed

Only when the task genuinely needs deeper history, rationale, or evidence beyond what the Wiki
page states (a "why", "history", or "investigation" question; or the Wiki page itself says "check
X for detail"):

```
uv run python -m app.knowledge.cli context "<task description>"     # bounded, PROJECT_STATE-first
uv run python -m app.knowledge.cli search "<specific term>" --json  # a narrow lookup
```

Retrieved results carry a `source_type` (`WIKI_CANONICAL` > `PROJECT_STATE` > `IMPLEMENTATION_REPORT`
> `SPEC` > `INVESTIGATION`/`HISTORICAL`) alongside `status`/`capability_status`. Canonical Wiki
material is preferred for "what is true now" questions — a semantically-similar old investigation
does not outrank it on relevance score alone — but it is a bounded rerank, never a hard filter:
add `--historical`/`--status HISTORICAL --status SUPERSEDED` to explicitly pull historical
material for a "why"/history question; it is down-weighted by default, never hidden.

## Step 5 — Verify against current code/tests before changing behavior

Before actually changing behavior, verify the implementation claims you're relying on — a Wiki
page or a report can be wrong the moment someone else merges something, and code+tests+current
git state always outrank documentation (Step... 0, really, at the top of the authority list). A
quick `git log`/`git branch --contains`/opening the cited module is enough for most tasks; don't
skip this because the Wiki page sounded confident.

## Reporting (for substantive tasks)

Record briefly in your working report — never dump the whole context pack:

```
Knowledge preflight:
- index refresh: changed / unchanged / deferred
- active embedding provider/model: e.g. huggingface/BAAI/bge-m3, or hash (fallback, and why)
- canonical Wiki page(s) used: e.g. docs/wiki/features/multi-level.md
- RAG used for deeper evidence: yes/no — topics queried if yes
- verified against code/tests: what you checked
```
