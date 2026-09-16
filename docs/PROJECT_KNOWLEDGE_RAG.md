# Project Knowledge RAG

A derived retrieval layer over this repo's Markdown documentation. **Git/Markdown remains the
source of truth.** This index is rebuildable from the repo at any time; it is never edited
directly, and it is never authoritative over the `.md` files it's built from.

## Architecture

```
docs/**/*.md, specs/*/{spec,plan,research}.md
        │  (chunking.py: heading-hierarchy split, then paragraph split if oversized)
        ▼
   chunks (heading_path, text)
        │  (embeddings/factory.py: capability-checked Ollama, else hash, else openai)
        ▼
SQLite store (app/knowledge/store/sqlite_store.py)
   - chunks table + embedding column
   - FTS5 virtual table for keyword search
   - index_meta (embedding provider/model/dim, for rebuild-on-change detection)
        │
        ▼
retrieval.py: hybrid search, status-aware reranking
        │
        ▼
context_pack.py: PROJECT_STATE.md + top current chunks + (optional) historical, token-bounded
        │
        ▼
tool.py / cli.py: what an agent actually calls
```

## Source-of-truth policy

Documentation status is **checked against git**, not trusted from a report's own prose. A report
can say "PARTIAL" or omit a status line entirely after the feature it describes has since merged —
this happened for real during this delivery (see `docs/PROJECT_STATE.md`'s corrected facts around
`007-wet-room-semantics`, `ROOM_PROPORTION_QUALITY_TIER_REPORT.md`, and `016-l-massing-outlines`,
all of which an earlier pass mis-classified from doc wording alone). `backend/app/knowledge/
doc_status.json` is the authoritative, hand-curated table; it is **not** an LLM guess.

## Metadata schema

Every entry in `doc_status.json` carries:

| field | meaning |
|---|---|
| `doc_status` | `IMPLEMENTED` \| `APPROVED` \| `ACTIVE_RESEARCH` \| `HISTORICAL` \| `SUPERSEDED` — the doc's own currency |
| `capability_status` | `IMPLEMENTED_MERGED` \| `PARTIAL` \| `NOT_IMPLEMENTED` \| `UNKNOWN` \| `N/A` — does the described capability exist in `main` today |
| `decision_status` | `APPROVED` \| `APPROVED_FOR_IMPLEMENTATION` \| `PROPOSED` \| `REJECTED` \| `N/A` |
| `commit`, `branch`, `merged_to_main` | git evidence, where discoverable |
| `supersedes` / `superseded_by` | the chain |
| `confidence` | `high` (checked against git this round) \| `medium` \| `low` (heuristic, not yet spot-checked) |
| `last_verified_at` | when the entry was last checked against git — not when the doc was written |

Any doc not yet in the table gets a conservative fallback (`ACTIVE_RESEARCH` /
`capability_status=UNKNOWN` / `confidence=low`) plus a content-grep hint (`SUPERSEDED`,
`STATUS=DONE`, `REJECTED`) — never assumed current, never assumed dead.
`python -m app.knowledge.cli doctor` lists every entry below `confidence: high`, as a worklist for
the next person who touches that area to spot-check against git.

## Chunking

Markdown-structural: split on heading hierarchy (`#`–`####`) first, then on paragraph boundaries
only if a section exceeds `DEFAULT_MAX_CHARS` (1800). Never a blind N-character split — a chunk
boundary always falls at a heading or a blank line, so an architectural decision or invariant is
never cut mid-sentence.

## Storage

**SQLite is the only backend implemented and tested this round** (`sqlite_store.py`, stdlib
`sqlite3` + an FTS5 virtual table for keyword search; vector search is brute-force cosine in
Python, which is more than fast enough for this corpus — ~1,100 chunks over 63 source files,
indexed in ~1.3s on this machine).

**Postgres+pgvector is documented as the future production adapter, not implemented here.** The
`KnowledgeStore` ABC (`store/base.py`) is exactly what a `postgres_store.py` would implement:
`upsert_document`/`delete_document`/`search_vector` (via pgvector's `<=>` distance operator)/
`search_keyword` (via `tsvector`)/`get_index_meta`/`set_index_meta`. This was a deliberate scoping
decision from review: this environment has no live Postgres to test against, and a ~40-doc corpus
does not need production-scale vector infrastructure — shipping untested pgvector SQL would be
worse than not shipping it. When a real Postgres is available, implement `postgres_store.py`
against the same ABC and switch `KNOWLEDGE_DB_BACKEND=postgres`; nothing else in the pipeline
changes.

## Embeddings

Four providers behind one `EmbeddingProvider` ABC (`embeddings/base.py`), selected by
`embeddings/factory.py`:

1. **`ollama`** — only usable for a model whose capabilities were *verified* (via
   `app.local_models.discovery`, which calls Ollama's own `/api/tags`/`/api/show`) to actually
   include `"embedding"`. Constructing this provider for a non-embedding-capable model raises
   immediately — it never silently repurposes a completion model as an embedder.
2. **`hash`** — a dependency-free deterministic hashed n-gram vectorizer. The safe fallback.
3. **`openai`** — `text-embedding-3-small`, gated by `OPENAI_API_KEY`.
4. **`huggingface`** — local `sentence-transformers` inference (CPU by default, MPS opt-in on
   Apple Silicon, never required). **Never part of auto-detect** — only activates when
   `KNOWLEDGE_EMBEDDING_PROVIDER=huggingface` is explicitly set, and any failure (missing the
   `knowledge-embeddings` extra, a model that fails to load) raises immediately rather than
   silently falling back to `hash` — a silent fallback would make an evaluation run look semantic
   when it actually wasn't. Requires `uv sync --extra knowledge-embeddings`
   (`sentence-transformers` + `torch`, not installed by default).

**Measured fact about this machine**: neither installed Ollama model declares embedding
capability (`llama3.2:latest` → `[completion, tools]`; `gemma4:26b` → `[completion, vision, tools,
thinking]`). So today, `KNOWLEDGE_EMBEDDING_PROVIDER` auto-detects to **`hash`**, and the CLI logs
this plainly on every index/search. Three ways to get real semantic embeddings, in order of
recommendation: (1) `KNOWLEDGE_EMBEDDING_PROVIDER=huggingface` + `KNOWLEDGE_EMBEDDING_MODEL=
BAAI/bge-m3` (evaluated below — the strongest option measured), (2) `ollama pull
nomic-embed-text` then leave `KNOWLEDGE_EMBEDDING_PROVIDER` unset, (3) `KNOWLEDGE_EMBEDDING_
PROVIDER=openai`. None of these happen automatically.

### Embedding-model evaluation (2026-09-17)

Compared 3 Hugging Face multilingual candidates against the existing hash+FTS5 baseline, on this
repo's real doc corpus (72 tracked files, ~1,100 chunks) and a 30-query bilingual (20 EN / 10 HE)
evaluation set manually grounded via `git grep` on tracked content
(`backend/tests/knowledge/eval/queries.json` — never generated from a model's own output).
Methodology and raw per-model reports: `backend/tests/knowledge/eval/run_eval.py` +
`baseline_hash.json`/`e5_base.json`/`bge_m3.json`/`mpnet.json` in the same directory.

| model | dim | index time (72 files) | peak RSS | hybrid Top-1 | Recall@3 | Recall@5 | MRR | HE Top-1 | EN Top-1 | query latency |
|---|---|---|---|---|---|---|---|---|---|---|
| hash (baseline) | 512 | 1.3s | 34 MB | 43.3% | 53.3% | 63.3% | 0.513 | 20% | 55% | 167 ms |
| paraphrase-multilingual-mpnet-base-v2 | 768 | 26s | 1.73 GB | 43.3% | 70.0% | 83.3% | 0.587 | 40% | 45% | 373 ms |
| intfloat/multilingual-e5-base | 768 | 105s | 2.53 GB | 46.7% | 70.0% | 83.3% | 0.601 | 40% | 50% | 390 ms |
| **BAAI/bge-m3** | 1024 | 618s | 3.67 GB | **56.7%** | **86.7%** | **90.0%** | **0.703** | **50%** | **60%** | 572 ms |

**Semantic-only vs. FTS-only vs. hybrid** (proving the semantic channel adds value rather than
replacing keyword search — full breakdown in the per-model JSON reports): FTS-only alone already
gets 26.7% Top-1 / 0.444 MRR (driven by literal term overlap — exact terms like `C22` retrieve via
this channel regardless of embedding quality). `bge-m3` semantic-only alone reaches 46.7% Top-1 /
0.627 MRR — genuinely strong standalone semantic performance, unlike `e5-base` and `mpnet`, whose
semantic-only channels underperformed FTS-only on English (their value only appeared once
combined with FTS in the hybrid score). **Hybrid consistently beats both channels alone for every
model** — FTS5 was not removed, and should not be: `bge-m3`'s hybrid MRR (0.703) beats its own
semantic-only MRR (0.627) and FTS-only's (0.444).

**Selected: `BAAI/bge-m3`.** It is not the fastest or the lightest — it is the only candidate that
improved **both** languages simultaneously (`e5-base` traded English Top-1 for Hebrew gains;
`mpnet` matched baseline English at best) and won on every single retrieval-quality metric
measured, not one cherry-picked number. The cost is real (618s to fully reindex vs. 1.3s for hash;
3.67 GB peak RSS vs. 34 MB) but bounded and one-time-ish: `knowledge index --changed` only
re-embeds changed files, so the 618s is a full-rebuild cost, not a per-edit one, and 3.67 GB is
comfortable headroom on the 32 GB target machine. Per-query latency (572ms) stays sub-second for
an interactive CLI tool. This is an evidence-based choice, not a "pick the biggest" default —
`mpnet` (26s indexing, 1.73 GB) remains a documented lighter-weight alternative for anyone who
wants faster reindexing at a real quality cost, and `e5-base` sits in between.
**`huggingface` remains opt-in** — the auto-detected default (`hash`, or `ollama` once a
capability-verified model is pulled) is unchanged; nothing switches automatically.

Not measured this round (explicitly, not fabricated): `KNOWLEDGE_EMBEDDING_DEVICE=mps`
acceleration (available, untested); a 4th/5th HF candidate; production-scale corpora larger than
this repo's ~1,100 chunks.

**Index versioning**: the store's `index_meta` row records `(embedding_provider, embedding_model,
embedding_dim)`. `index_changed()` refuses to run incrementally if the active config no longer
matches what's recorded on **any** of those three fields — it raises `EmbeddingConfigMismatch`
telling you to run `knowledge clear && knowledge index`, rather than silently mixing vectors from
two different models (or two versions of the same model that changed dimensionality without a
name change).

## Retrieval

Hybrid, with normalization done **before** any status reranking (raw FTS5 `bm25()` scores and raw
cosine scores are on incomparable scales):

1. Vector search and FTS5 keyword search each run independently over the same candidate pool.
2. Each channel's raw scores are min-max normalized to `[0, 1]` independently.
3. `combined = 0.5 * norm_vector + 0.5 * norm_keyword`.
4. A **bounded** status multiplier reranks on top of `combined`: `IMPLEMENTED_MERGED = 1.15`,
   `APPROVED = 1.10`, `ACTIVE_RESEARCH (+APPROVED_FOR_IMPLEMENTATION) = 1.05`, `ACTIVE_RESEARCH =
   1.00`, `HISTORICAL = 0.90`, `SUPERSEDED = 0.75`. The ~1.53× max spread is deliberately narrow —
   enough to break a near-tie between equally-relevant docs of different status, never enough to
   flip a real relevance gap (a highly-relevant historical chunk always outranks an irrelevant
   current one). See `tests/knowledge/test_retrieval_priority.py` for the four invariants this is
   tested against.
5. `topics`/`status` filters apply before ranking. An explicit `status=("HISTORICAL",)` request
   bypasses the default down-weighting entirely — historical/superseded material is down-weighted
   by default, never hidden outright.

Because the keyword channel is normalized and weighted equally with the (currently weak, hash-based)
vector channel, exact technical terms — `C22`, `VerticalCore`, `public_open_side`, `V1/V0` —
retrieve reliably regardless of embedding quality.

## How coding agents should use it

1. Read `docs/PROJECT_STATE.md` first — it's the compact, current-state-only summary every session
   should start from.
2. For a specific task, call `python -m app.knowledge.cli context "<task description>"` (or the
   `app.knowledge.tool.retrieve(...)` function directly) to get a token-bounded pack of the most
   relevant current evidence, with historical material available on request
   (`--historical`/`status=("HISTORICAL","SUPERSEDED")`).
3. For a narrow lookup (a specific term, a specific decision), `python -m app.knowledge.cli search
   "<query>" --json` is faster than reading whole documents.

**Why not an MCP server**: this repo has no MCP tooling today, and adding one is more
infrastructure than a ~40-doc corpus warrants. The retrieval tool is exposed as (a) a plain
importable Python function (`app.knowledge.tool.retrieve`) and (b) `knowledge search --json` for
any agent that can shell out — both are trivially wrappable into an MCP tool later if that
infrastructure gets adopted for other reasons.

## Auto-refresh skill

`.claude/skills/knowledge-refresh/SKILL.md` — a Claude Code skill that runs `knowledge index
--changed` (a cheap no-op if nothing changed — see Incremental indexing below) before reading
`PROJECT_STATE.md`, so an agent's first look at the repo is never working off a stale index. It
can be invoked explicitly (`/knowledge-refresh`) or picked up automatically by the model when a
task's shape matches its description.

## Incremental indexing

- `knowledge index` — full rebuild, also removes rows for files no longer present.
- `knowledge index --changed` — sha256 checksum diff; skips unchanged files, reindexes changed
  ones, removes deleted ones. On this corpus (63 files), a no-op run costs a filesystem stat + hash
  per file — no embedding calls at all when nothing changed.
- `knowledge clear` — drops everything (the documented recovery path after an embedding config change).
- `knowledge stats` — document/chunk counts, current embedding provider/model/dim.

## Troubleshooting stale retrieval

1. `knowledge stats` — check `updated_at` and the recorded embedding provider/model.
2. `knowledge index --changed` — cheap; run it before trusting a search result.
3. If a doc's status looks wrong, check `backend/app/knowledge/doc_status.json` — is the entry
   missing (falls back to a low-confidence heuristic) or stale (`confidence` below `high`)? Fix the
   table directly; it's the authoritative source, not something retrieval infers on its own.
4. `knowledge doctor` — lists every below-`high`-confidence entry, as a checklist.
5. If embeddings look wrong after installing/removing an Ollama model, `knowledge index` will
   refuse with `EmbeddingConfigMismatch` if the recorded config no longer matches — that's the
   safety check working, not a bug. Run `knowledge clear && knowledge index` to rebuild.
