---
name: "knowledge-refresh"
description: "Before doing repo-architecture or historical-decision work, refresh the Project Knowledge RAG index (cheap no-op if nothing changed) and read docs/PROJECT_STATE.md first, then retrieve only the specific evidence needed."
argument-hint: "Optional task description to build a context pack for"
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
edits a doc without re-indexing. Read stale search results as if they were current is exactly the
mistake this skill exists to prevent.

Run these steps, from `backend/`:

1. **Refresh the index** — `uv run python -m app.knowledge.cli index --changed`. This is a
   sha256-checksum diff: if nothing changed since the last index, it costs a filesystem stat + hash
   per source file and does no embedding work at all. Never skip this step to "save time" — it is
   already cheap when there is nothing to do, and expensive to skip when there is.

2. **Read `docs/PROJECT_STATE.md` in full.** It is deliberately compact (current state only, not
   history) and is the first context every coding agent on this repo should have, before anything
   else.

3. **If `$ARGUMENTS` names a specific task**, build a bounded context pack for it instead of
   reading raw docs end-to-end:
   `uv run python -m app.knowledge.cli context "$ARGUMENTS"` — this returns `PROJECT_STATE.md` plus
   the top current-status-ranked evidence, respecting a token budget. Add `--historical` only if
   the task explicitly needs superseded/historical context (e.g. "why did we reject X").

4. **For a narrow lookup** (a specific term, a specific decision, a specific commit), prefer
   `uv run python -m app.knowledge.cli search "<query>" --json` over re-reading whole documents.

5. If `knowledge index` reports an `EmbeddingConfigMismatch`, that is the safety check working
   (the embedding model changed since the index was built) — run `uv run python -m app.knowledge.cli
   clear && uv run python -m app.knowledge.cli index` to rebuild, then continue from step 2.

Do not report a retrieval result as current without having run step 1 first in the same session —
a result from a stale index is exactly as unreliable as trusting a report's own prose over git
(see `docs/PROJECT_STATE.md`'s corrected-facts section for why that distinction matters here).
