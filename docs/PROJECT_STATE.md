# Project State

Current state only — not history. Historical/superseded material is retrievable through the
Project Knowledge RAG (`docs/PROJECT_KNOWLEDGE_RAG.md`) but is deliberately not repeated here.
Statuses below are drawn from `backend/app/knowledge/doc_status.json`, whose entries are checked
against `git log`/`git branch --contains` where marked `confidence: high` — not from report prose
alone. Last refreshed: 2026-09-16.

## Current architecture

- **Backend**: FastAPI (`backend/app`), Python 3.11, `uv`-managed, `[tool.uv] package = false`
  (the project is not installed as a package — CLIs run as `python -m app.<module>.cli`, not via
  `[project.scripts]`).
- **Domain model**: `SPATIAL_ENGINE_SPEC_V2_1.md` is the frozen domain-model foundation
  (`PRIVATE_HOUSE_V1_ENGINE_DECISION.md` froze scope on top of it — no redesign without a new
  decision doc).
- **Planning pipeline**: `app/vertical_slice/` — `ProgramSpec`/`ArchitecturalSpec`/`HouseConcept`
  (`spec.py`) → `concept_generator.py` (room program, outline search) → `general_pipeline.py`
  (`run_general`/`run_general_from_site`, the realized plan) → `app/demo/service.py:
  generate_demo_design(project)` as the single deterministic entry point (no LLM in this chain).
- **Requirements parsing**: `app/requirements/parser.py`'s `OpenAIRequirementParser` is the only
  LLM in the product path — it extracts structured fields (floors, bedrooms, safe_room,
  wet_room_demand, other_requests, ...) from free-text Hebrew/English briefs.
  `wet_room_normalizer.py` (deterministic, rules R1–R5) turns that extraction into concrete wet
  rooms. `public_open_side` is **not** LLM-extracted — it's a structured `Project` field set
  directly from the UI/API (`app/demo/requirements_view.py::_public_open_side_of`).
- **Geometry**: `app/geometry_domain/` (Shapely-backed booleans/offsetting), `app/geometry/spatial_v2/`.
- **Massing**: the engine surveys rectangles plus, since 016, two L massings per requested area on
  any rectangular plot (not just L-shaped sites); a later refinement (commit `9ae6893`) gates an
  engine-generated L on realized quality instead of always taking the slot.
- **Multi-level**: Phase 0 (types/contracts, still single-storey behavior) is implemented. Phase 1
  (an actual second storey: core-band coordinator, allocations A/C, building-level V-checks,
  lexicographic candidate primary selection) is **implemented and merged to `main`** (commits
  `4bdebd4`, `3270063`) — but, per its own implementation report, **not yet wired to the live
  product**: `concept_generator.py`, `general_pipeline.py`, `demo/*` and the frontend have zero
  diff, and the new modules are reached only by calling them directly (as in their own tests),
  never through the ordinary single-level request path.
- **Project Knowledge RAG** (this delivery): `backend/app/knowledge/` — hybrid (FTS5 keyword +
  hash-embedding vector) retrieval over `docs/**/*.md` and `specs/*/{spec,plan,research}.md`, SQLite
  storage, status-aware reranking. CLI: `python -m app.knowledge.cli {index,search,context,stats,
  local-models,doctor}`.
- **Cheap AI Test Harness** (this delivery): `backend/tests/ai_harness/` — deterministic / local
  Ollama / production OpenAI tiers, plus `backend/tests/regression_corpus/` (the frozen 432-context
  corpus, zero LLM calls).

## Merged / implemented features (capability_status = IMPLEMENTED_MERGED, git-confirmed)

- L massings on a rectangular plot + the L-orientation tiebreak (016; commit `5195368`).
- Massing representation / display fix (013).
- L-massing representation quality gate — an engine-generated L only takes its representation
  slot on realized-quality eligibility, not merely for being an L (commit `9ae6893`).
- Wet-room quality tier extended to `SHARED_BATHROOM`/`GUEST_WC` (commit `f2092af`, follows
  `be8c0ca`'s bedroom-class original) — a soft objective only, no hard-gate or row-rescue changes.
  **Laundry is explicitly excluded and does not exist on `main` at all**: `LAUNDRY_ROOM_ENABLED`
  is not present anywhere in this branch's code. A laundry-room implementation exists only on the
  separate, never-merged, locked `worktree-015-laundry-room-option` (see Known limitations) —
  treat any doc describing a "gated off but implemented" laundry capability as describing that
  separate worktree, not `main`'s current state.
- Multi-Level Phase 1 (core-band coordinator, allocations A/C, building V-checks, lexicographic
  candidate primary selection) — implemented and merged (commits `4bdebd4`, `3270063`), not yet
  wired to the live product (see Current architecture above).
- Room-proportion quality tier — bounded `preferred_aspect_ratio` on bedroom-class rooms, a lone
  row may take the master's corridor-facing slot beside its ensuite (commit `be8c0ca`). This
  **supersedes** `ROOM_PROPORTION_REPARTITION_REPORT.md`, which is investigation-only now.
- Wet-room semantics (007): `FixtureDemand`, deterministic normalization (R1–R5), toilet-vs-room
  policy, questions/proposals UI. Extensively implemented across 6 phases (PRs #2, #4; fix commits
  `a166777`, `8c4cdba`). **Supersedes** `docs/WET_ROOM_SEMANTICS_PROPOSAL.md`.
- Multi-level Phase 0 — domain and contracts, no behavior change yet (branch `010-multi-level-phase0`).
- Footprint-as-wings representation (011), the first production L parti (branch `012`, only fires
  on L-shaped sites — see 016 above for the rectangular-plot generalization).
- Hub eligibility by computed feasibility + demotion guard (008; landed via a differently-named
  local branch than the spec folder, confirmed present in `git log main`).
- Engine-chosen outline as the first alternative when the person's own outline plans short (006).
- Built-area target fix (gap −37% → −2.7%), corridor width, room relationships, unsupported-request
  classification, site-aware footprint options, authoritative site geometry P0, general geometry
  domain V1 + derived open interfaces (636 tests) — all `STATUS=DONE` reports, not individually
  re-verified against git this round (`confidence: medium` in `doc_status.json`).
- ReviewPage Generate disabled-reason fix — strict priority order, one reason shown at a time
  (commit `8c4cdba`) — **guardrail**, see below.

## Approved decisions

- `PRIVATE_HOUSE_V1_ENGINE_DECISION.md` — scope frozen on `SPATIAL_ENGINE_SPEC_V2_1.md`'s domain
  model; no redesign without a new decision doc.
- `BUILDING_SHAPE_MASSING_FAMILIES_REPORT.md` — the massing-family plan the L-parti/L-massing work
  implements.
- `MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md` — the multi-level architecture (Phase 0
  and Phase 1 both implemented against it now; Phase 1 not yet wired to the live product).
- Multi-level Phase 1's circulation approach (`MULTI_LEVEL_PHASE_1_IMPLEMENTATION_REPORT.md`):
  `decision_status = APPROVED`, implemented and merged (commits `4bdebd4`, `3270063`) — this
  **supersedes** the two earlier `MULTI_LEVEL_PHASE_1_{INVESTIGATION,FOLLOWUP}_REPORT.md` research
  docs, which described the design baseline before it was built.

## Active branches / work in progress (confirmed via `git worktree list` / `git branch -a`)

- `integration/laundry-into-main` (checked-out worktree) — active, uncommitted work bringing a
  laundry-room capability into `main` for the first time; nothing merged yet as of this writing.
- `worktree-015-laundry-room-option` (locked worktree) — a separate, never-merged laundry-room
  design; see Known limitations below. Not the same code as `integration/laundry-into-main` above.
- `specs/009-guest-wc-placement` — spec committed (`c3b1c96`), nothing implemented yet.
- `specs/005-hub-private-wing` — spec + plan + results committed to `main`, but the implementation
  itself was **not merged** ("two hard acceptance gates failed" per its own results doc) —
  `decision_status = REJECTED`.

## Open investigations (ACTIVE_RESEARCH, no code changed)

- Room capacity constraint, plan-not-realizable root cause — standalone diagnostics, no successor
  doc yet.
- Layout-selection UX research — partially realized via `specs/006-engine-chosen-outline`.

## Known limitations

- **Row-sharing topology limit**: a shared row in every parti has exactly one corridor-facing slot;
  at most ~16% of lone private/service rows can ever be paired (measured over the 432-context
  corpus — see `ROOM_PROPORTION_REPARTITION_REPORT.md`). This is a topology ceiling, not a search
  ceiling — the quality-tier work (`be8c0ca`) picks up as much of that ceiling as the existing
  access model allows, and nothing further is available "for free."
  Also, an ensuite pairing is limited to whichever wet room happens to be a `SERVICE`-zone member,
  which today is only ever one ensuite per programme (149 of 432 briefs have none at all).
- **Laundry room**: does **not exist on `main`** — `LAUNDRY_ROOM_ENABLED` is absent from this
  branch's code entirely (confirmed via `git grep` on `main`), and `WET_ROOM_QUALITY_TIER_
  IMPLEMENTATION_REPORT.md` explicitly excludes it from the wet/service quality-tier extension for
  exactly this reason. A prior design (`LAUNDRY_ROOM_ENABLED=False`, gated off, row-sharing
  generalized to `ZoneGroup.SERVICE`) exists only on the separate, never-merged, locked
  `worktree-015-laundry-room-option` — that recommendation was never about `main`. Active,
  uncommitted work to bring laundry into `main` for the first time is underway on
  `integration/laundry-into-main` as of this writing; nothing merged yet.
- **Multi-level Phase 1 is implemented and merged but not wired to the live product** (see Current
  architecture above) — the only seat proven to work on both levels is the core-band seat; the
  two-storey ground floor needs the kitchen across the corridor from it. Only 27/36 hand-built
  briefs and 0/76 independently-generated briefs aligned on a shared stair seat during the
  pre-implementation investigation — check the implementation report itself for whether that gap
  was closed or remains open.
- **Knowledge RAG embeddings**: neither installed Ollama model (`llama3.2`, `gemma4:26b`) declares
  `embedding` capability (confirmed live via `/api/tags`/`/api/show`) — the auto-detected default
  index still runs on the deterministic hash embedder, not real semantic vectors. A real
  multilingual semantic option now exists (`KNOWLEDGE_EMBEDDING_PROVIDER=huggingface`,
  `KNOWLEDGE_EMBEDDING_MODEL=BAAI/bge-m3` — evaluated best-of-3 candidates on this corpus,
  improves both Hebrew and English retrieval) but is **opt-in only**, never auto-selected; needs
  `uv sync --extra knowledge-embeddings`. Hybrid keyword search (FTS5) still retrieves exact
  technical terms reliably either way; see `docs/PROJECT_KNOWLEDGE_RAG.md`.

## Guardrails / do-not-change rules

- **ReviewPage Generate guardrail**: preserve the blocking priority order and commit `8c4cdba`'s
  `disabledReason`/pending-message behavior — a wet-room symptom can be an unrelated blocker
  further up the chain. Don't change without a reproducible regression.
- **Never mutate git in the main checkout** from an agent session — the user runs git in the IDE on
  the same checkout concurrently. No stash/checkout/reset from a session.
- **Corridor opening** (hall↔LDK) is a contract-level post-process in `app/demo/contract.py`, at
  the segment level — the engine itself is untouched. Don't move this into the engine without a
  reason.
- **Toilet vs. WC room policy**: toilets absorb into bathrooms; `GUEST_WC` is created only when
  explicit. The parser — not the engine — counts each שירותים mention as a room.
- **Row-sharing quality tier** (commit `be8c0ca`): one ensuite = one pairable row. The next levers
  here are semantic (what counts as pairable), not search — don't attempt another search-side fix
  for the topology ceiling above.
- **Do not treat the production OpenAI parser as a source of truth for AI-test expected behavior.**
  It is an implementation under test, exactly like the local Ollama models. Authoritative expected
  behavior is: approved product/architecture semantics, versioned golden expected outputs
  (`tests/wet_room_corpus/`, `tests/ai_harness/golden/`), and deterministic validation/contracts.

## Next recommended work

1. Wire Multi-Level Phase 1 into the live product path (`concept_generator.py`/`general_pipeline.py`/
   `demo/*` currently have zero diff from it) — check the implementation report for whether the
   stair-seat alignment gap (27/36 hand-built, 0/76 independently-generated) was closed.
2. Land `integration/laundry-into-main` — the first laundry capability actually merged to `main`.
3. `BAAI/bge-m3` (opt-in) is the recommended path to real semantic embeddings — see
   `docs/PROJECT_KNOWLEDGE_RAG.md`; `ollama pull nomic-embed-text` remains a lighter alternative.
4. Guest-WC placement (009) — spec exists, nothing implemented.
5. Extend `tests/ai_harness/golden/semantic_cases.json` as new semantic behaviors are approved —
   expected values must come from approved rules, never from "whatever a model said."

## Important current commits

- `5195368` — Merge '016-l-massing-outlines': L massings on a rectangular plot, L-orientation tiebreak.
- `9ae6893` — feat(selection): gate engine-generated L massings on realized quality.
- `be8c0ca` — feat(planner): prefer bounded room-proportion quality peers.
- `f2092af` — feat(planner): extend the room-proportion quality tier to wet/service rooms.
- `8c4cdba` — fix(review): clarify wet-room edits and disabled generate reason.
- `a235c37` / `b5c74fa` — multi-level Phase 0 (domain/contracts, no behavior change).
- `4bdebd4` / `3270063` — multi-level Phase 1: core-band coordinator + candidate primary selection.
- `e513d91`, `ae6e1b8` — wet-room semantics (007) PRs #2 and #4.
