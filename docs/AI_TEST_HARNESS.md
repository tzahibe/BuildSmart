# Cheap AI Test Harness

## Source of truth (read this first)

**The production OpenAI parser is not authoritative.** It is an implementation under test,
exactly like the local Ollama models. Authoritative expected behavior is: approved product /
architecture semantics, versioned golden expected outputs
(`tests/wet_room_corpus/corpus.json`, `tests/ai_harness/golden/semantic_cases.json`), and
deterministic validation/contracts. The production golden suite exists to catch when the
production implementation drifts from those — never to define them. A local model disagreeing
with the golden set never redefines the golden set; it gets surfaced for human review.

## The pyramid

```
FAST         deterministic only                         — plain `pytest`, zero LLM/network
REGRESSION   + the frozen 432-context corpus             — zero LLM/network, larger runtime
LOCAL_AI     + local Ollama golden semantic tests         — free, real Ollama calls, cached
FULL_AI      + the production OpenAI golden suite         — costs money, small set, cached
NIGHTLY      full corpus + larger semantic evaluation      — scheduled, not per-commit
```

Select with `TEST_MODE` (default `FAST`); the gating hook lives in `backend/tests/conftest.py`
(shared — it governs `tests/ai_harness/` **and** `tests/regression_corpus/` from one place, so the
regression corpus can never be left accidentally ungated by a hook scoped only under
`tests/ai_harness/`). A plain `pytest` run collects zero AI/regression tests — no flags to
remember for normal development.

```
uv run pytest                                             # FAST
TEST_MODE=REGRESSION uv run pytest -m regression -q       # + frozen corpus
TEST_MODE=LOCAL_AI   uv run pytest -m local_ai -q          # + local Ollama semantic
TEST_MODE=FULL_AI    uv run pytest -m "local_ai or production_ai" -q   # + production (needs OPENAI_API_KEY)
```

### Why a separate REGRESSION tier from FAST

`tests/regression_corpus/` replays the real, historically-used 432-context corpus
(`app/data/failures.json`'s distinct contexts, via `spikes/failure_log_sweep/sweep.py`) through
the full `project_from_context -> generate_demo_design` pipeline — deterministic, zero LLM/network
calls, but a few hundred real planner/geometry runs is genuinely slower than the FAST unit suite.
Keeping it a separate opt-in tier keeps `pytest` fast for routine development while still making
the full corpus one flag away. **A geometry/planner change requires zero external-model calls to
verify against this corpus.**

## Model roles

| role | used for | chosen by |
|---|---|---|
| `local_fast` | routine parser/JSON/classification regressions | the **measured** benchmark (`bench.py`), never hardcoded |
| `local_strong` | harder semantic tests, failure-cluster summarization | same — measured, not assumed |
| `production` | the small authoritative golden suite; release/prompt/parser changes | fixed to match `app/requirements/parser.py`'s own default (`gpt-5-nano`) unless overridden |

`AI_TEST_LOCAL_FAST_MODEL`/`AI_TEST_LOCAL_STRONG_MODEL` are **unset by default** — `config.py`
reads `tests/ai_harness/reports/model_recommendation.json`, which `bench.py` writes after actually
measuring the installed models. An explicit env var always overrides the recommendation. Routine
regression work never consumes the strong local model or the production model — see `bench.py`'s
recommendation for which installed model plays which role today.

**A `local_fast` verdict can be `LOCAL_FAST_LIMITED`.** An aggregate score above the suitability
threshold does not by itself mean a model is generally reliable — `bench.py` also applies the same
threshold *per topic* (see `_topic_split`/`_verdict`), and if most individual topics fall below it
while the aggregate happens to clear it, the verdict is `LOCAL_FAST_LIMITED` with explicit
`reliable_topics`/`weak_topics` evidence rather than a blanket `LOCAL_FAST`. Measured on this
machine: `llama3.2` is `LOCAL_FAST_LIMITED` — reliable on `room_count`, `safe_room_semantics`,
`multi_level_request`, `wet_room_interpretation`, weak on `floor_count`,
`unsupported_hard_requirement`, `laundry_wording` (aggregate 55.3% masks that 3/7 topics are
~33%). `config.py`'s `model_for_role` still resolves a `LOCAL_FAST_LIMITED` model (it's still the
right choice for its reliable topics) but emits a `UserWarning` naming the split, so the caveat is
visible at test-run time, not just in the report file. A failure on a `weak_topics` entry is
expected model limitation, not necessarily a regression — this is a model-selection signal, not a
verdict on the golden expectations, which are never adjusted to make a model score better.

## `knowledge local-models` / Ollama discovery

`app/local_models/discovery.py` calls Ollama's own `/api/tags` (falling back to `/api/show` per
model on older Ollama versions that omit capabilities there) — **never** downloads or pulls a
model, and never assumes a capability from a model's name or size. Run `uv run python -m
app.knowledge.cli local-models` to see what's installed, its real capabilities, and a heuristic
role-guess (the actual role assignment comes from `bench.py`'s measurement, not this heuristic).

## 32GB RAM policy

This dev machine has 32GB RAM, running the IDE, the backend, and tests concurrently. `gemma4:26b`
is ~17GB on disk and a real memory-pressure risk under that load. Policy:

- The benchmark runs installed models **sequentially**, never two loaded/queried at once.
- Never run a heavy local model alongside a planner sweep (`REGRESSION` tier or a
  `spikes/failure_log_sweep` run) — the sweep is already CPU/memory-heavy on its own.
- Prefer the smaller model for routine `LOCAL_AI` runs; reserve the larger one for targeted
  `local_strong` evaluation, exactly as `bench.py`'s role split does.
- `bench.py` samples best-effort RSS (`ps`) around each model's run and reports it — not a hard
  gate, an observation to inform judgment.

## Golden dataset

`tests/ai_harness/golden/semantic_cases.json` — versioned (`version`, `prompt_version` fields),
tagged by topic: `wet_room_interpretation`, `room_count`, `floor_count`, `safe_room_semantics`,
`unsupported_hard_requirement`, `laundry_wording`, `multi_level_request`. `wet_room_interpretation`
cases are reused (with attribution, `source` field) from the existing, hand-labelled
`tests/wet_room_corpus/corpus.json` rather than re-invented.

**`public_open_side` is deliberately absent from this dataset.** Tracing `app/requirements/
parser.py`'s `RequirementExtraction` schema and `app/demo/requirements_view.py::
_public_open_side_of` confirmed it is set from a structured `Project.public_open_side` field (a
UI/API value), never extracted by the LLM parser — testing it with an LLM would violate this
harness's own first principle ("don't use an LLM where deterministic code can test the behavior").
Its test lives in `tests/ai_harness/test_deterministic_examples.py` instead, Tier A.

The extraction prompt (`golden_dataset.py`'s `SYSTEM_PROMPT`) is **harness-owned**, not a
byte-identical copy of `parser.py`'s production prompt — a deliberate scoping choice so comparing
local-vs-production models doesn't require refactoring production code. It asks for a small,
stable JSON schema (`floors`, `bedrooms`, `safe_room`, `wet_rooms`, `unsupported_topics`), enough
to exercise the same category of extraction task without depending on the production prompt's
exact wording.

## Local-model abstraction

One `TestLLMProvider` ABC (`provider_base.py`), three implementations (`mock`/`ollama`/`openai`),
selected by role via `factory.py` — mirrors `app/architect/gateway.py`'s provider-switch pattern.
**Application code must never import from `tests/ai_harness/`** — this is test infrastructure only.

## Caching

`cache.py`: `sha256(provider + model + prompt_version + system_prompt + input + relevant_config)`,
JSON files under `tests/ai_harness/.cache/` (gitignored). Changing the model, the prompt version,
or the input invalidates the cache automatically (different key); `ResponseCache.clear()` is the
explicit invalidation path.

## Observability

`report.py` mirrors `app/observability/failure_log.py`'s conventions (atomic write,
path-overridable, never raises): one record per AI-test case run — model, provider, latency,
tokens (when available), cache hit/miss, pass/fail, per-field diff. `report.summary()` aggregates
by provider.

## Failure policy

Local-model disagreement with the golden set is **surfaced, never used to silently redefine
expected behavior**. A failing `local_ai` test means "this local model doesn't reliably do this
extraction," not "the golden expectation is wrong." If local and production genuinely disagree,
that disagreement is a case for human review — the golden set changes only through an approved
product-rule change, never through a model's output.

## Local failure-cluster analysis

`failure_analysis.py` — optional, manually invoked (never automatic inside `pytest`). Feeds
structured failure/refusal records to the `local_strong` role for **clustering and summarization
only**; the prompt and the code both forbid it from judging whether a regression is acceptable.
The compact structured output is what a human/Claude reviewer reads instead of raw logs — the
accept/reject decision stays human.

## Local Test Assistant (`failure_triage.py`)

A distinct, narrower sibling of the failure-cluster analysis above: `failure_analysis.py` triages
the **product's** failure log (real refusals/crashes from `app/observability/failure_log.py`);
`failure_triage.py` triages a **pytest run's own failing tests**, for an agent mid-task.

```
code change -> focused deterministic tests -> IF failures ->
    parse_pytest_short_summary(pytest output) -> triage_failures() ->
    {failure_groups, likely_modules, knowledge_topics, investigation_areas} ->
    agent retrieves those knowledge_topics via the Knowledge RAG -> agent investigates
```

Hard rules, enforced by construction, not just convention:
- **`triage_failures([])` returns `None`** — never calls a model just to report that everything
  passed.
- **`TriageReport` has no pass/fail/verdict field** (`test_triage_never_produces_a_pass_fail_
  verdict_field` guards this) — a local model can summarize and group already-known failures; it
  can never redefine what passed. Tests remain the sole source of truth, and a model's opinion is
  never merge/release evidence, exactly like `failure_analysis.py`.
- Golden expectations are never adjusted based on triage output.
- Bounded input only — at most 30 failing tests, each error truncated to 300 chars, never a full
  traceback dump — and every raw failing-test name plus the deterministic pass/fail result belongs
  in the agent's own report regardless of what triage says.

Role selection follows the same measured roles as the rest of the harness (§Model roles): default
to `local_fast` (`LOCAL_FAST_LIMITED`/`llama3.2` today) for routine grouping — summarization,
duplicate-failure grouping, extracting names/modules is well within what a `LOCAL_FAST_LIMITED`
model reliably does. Escalate to `role="local_strong"` (`gemma4:26b`) only when the fast pass
wasn't useful enough, and never concurrently with a heavy regression sweep (§32GB RAM policy) —
this is a per-invocation judgment call for the agent, not an automatic heuristic in the code.
Identical failure reports are cached (`ResponseCache`, same key formula as everywhere else in this
harness) so re-triaging the same failures costs nothing on a retry.

## CI strategy (recommendation only — no workflow file added this round)

- **Per commit/PR**: `TEST_MODE=FAST` (deterministic only). Optionally `REGRESSION` on PRs that
  touch the planner/geometry stack.
- **Nightly or semantic-change PR**: `LOCAL_AI` — the local Ollama golden suite, free.
- **Release, or a parser/prompt/production-model change**: `FULL_AI` — the small production golden
  suite. Never on every commit; it costs real money and the local tiers already catch most
  regressions for free.

## Benchmark

Run `uv run python -m tests.ai_harness.bench` to (re)generate `reports/benchmark_latest.json` and
`reports/model_recommendation.json` from the currently-installed Ollama models. See this delivery's
final report for the numbers measured on this machine on 2026-09-16.
