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
  any rectangular plot (not just L-shaped sites).
- **Multi-level**: Phase 0 (types/contracts, still single-storey behavior) is implemented; Phase 1
  (an actual second storey) is approved-for-implementation research, not yet built (see below).
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
  implemented against it; Phase 1 approved-for-implementation, not yet built).
- Multi-level Phase 1's circulation approach (`MULTI_LEVEL_PHASE_1_FOLLOWUP_REPORT.md`):
  `decision_status = APPROVED_FOR_IMPLEMENTATION` — a real, currently-checked-out branch
  (`017-multi-level-phase1`) exists for this, alongside a sibling `017-public-open-side` branch.

## Active branches / work in progress (confirmed via `git worktree list` / `git branch -a`)

- `017-multi-level-phase1` — Multi-Level Phase 1 (an actual second storey). Not merged.
- `017-public-open-side` — a sibling branch, not merged.
- `worktree-015-laundry-room-option` (locked worktree) — laundry-room option review; see Known
  limitations below (feature is implemented but gated off).
- `specs/009-guest-wc-placement` — spec committed (`c3b1c96`), nothing implemented yet.
- `specs/005-hub-private-wing` — spec + plan + results committed to `main`, but the implementation
  itself was **not merged** ("two hard acceptance gates failed" per its own results doc) —
  `decision_status = REJECTED`.

## Open investigations (ACTIVE_RESEARCH, no code changed)

- Multi-Level Phase 1 follow-up — circulation efficiency, open-plan ground, bathroom semantics
  (builds on the Phase 1 investigation report, which it supersedes).
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
- **Laundry room**: `LAUNDRY_ROOM_ENABLED=False` — implemented (Phase 1) but gated off. Wiring it
  live reopens the TOILET-only strip-room gap; row-sharing generalized to `ZoneGroup.SERVICE`
  already accounts for it, at a 1/404 real-corpus deviation, but area-budget crowding is an open
  decision. Recommendation on file: keep gated.
- **Multi-level, if/when Phase 1 lands**: the only seat proven to work on both levels is the
  core-band seat; the two-storey ground floor needs the kitchen across the corridor from it. Only
  27/36 hand-built briefs and 0/76 independently-generated briefs currently align on a shared stair
  seat — this is the open problem Phase 1's follow-up work targets.
- **Knowledge RAG embeddings**: neither installed Ollama model (`llama3.2`, `gemma4:26b`) declares
  `embedding` capability (confirmed live via `/api/tags`/`/api/show`) — the index currently runs on
  the deterministic hash embedder, not real semantic vectors. Hybrid keyword search (FTS5) still
  retrieves exact technical terms reliably; see `docs/PROJECT_KNOWLEDGE_RAG.md`.

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

1. Multi-level Phase 1 implementation, informed by the follow-up report's core-band-seat findings.
2. Pull a dedicated Ollama embedding model (e.g. `nomic-embed-text`) and switch
   `KNOWLEDGE_EMBEDDING_PROVIDER=ollama` to get real semantic retrieval — not done automatically,
   see `docs/PROJECT_KNOWLEDGE_RAG.md`.
3. Guest-WC placement (009) — spec exists, nothing implemented.
4. Extend `tests/ai_harness/golden/semantic_cases.json` as new semantic behaviors are approved —
   expected values must come from approved rules, never from "whatever a model said."

## Important current commits

- `5195368` — Merge '016-l-massing-outlines': L massings on a rectangular plot, L-orientation tiebreak.
- `be8c0ca` — feat(planner): prefer bounded room-proportion quality peers.
- `8c4cdba` — fix(review): clarify wet-room edits and disabled generate reason.
- `a235c37` / `b5c74fa` — multi-level Phase 0 (domain/contracts, no behavior change).
- `e513d91`, `ae6e1b8` — wet-room semantics (007) PRs #2 and #4.
