# Project State

A high-level index, not a growing history document. **Detailed current truth for each subsystem
lives in the [Project Wiki](wiki/INDEX.md)** — this file exists to say what major capabilities
exist, their current status at a glance, and where to read more. Historical detail stays in raw
reports (`docs/*.md`, `specs/*/`), retrievable through the Project Knowledge RAG
(`docs/PROJECT_KNOWLEDGE_RAG.md`) but deliberately not repeated here.

**Current main HEAD at last verification: `1d648c3`.**

## Major capabilities and current status

| Subsystem | Status | Wiki page |
|---|---|---|
| Requirements / parsing semantics | IMPLEMENTED_MERGED | [wiki/architecture/requirements-parsing.md](wiki/architecture/requirements-parsing.md) |
| Geometry / validation | IMPLEMENTED_MERGED | [wiki/architecture/geometry-validation.md](wiki/architecture/geometry-validation.md) |
| L-Massing | IMPLEMENTED_MERGED | [wiki/features/l-massing.md](wiki/features/l-massing.md) |
| Wet Rooms | IMPLEMENTED_MERGED | [wiki/features/wet-rooms.md](wiki/features/wet-rooms.md) |
| Room Proportion / Quality Tier | IMPLEMENTED_MERGED | [wiki/features/room-proportion-quality-tier.md](wiki/features/room-proportion-quality-tier.md) |
| Multi-Level | IMPLEMENTED_MERGED (backend), not wired to product | [wiki/features/multi-level.md](wiki/features/multi-level.md) |
| Laundry | NOT_IMPLEMENTED on `main` (active unmerged work exists) | [wiki/features/laundry.md](wiki/features/laundry.md) |
| Knowledge System (this RAG + Wiki + AI test harness) | IMPLEMENTED_MERGED | [wiki/architecture/knowledge-system.md](wiki/architecture/knowledge-system.md) |
| Private House V1 scope | APPROVED (decision) | [wiki/decisions/private-house-v1-scope.md](wiki/decisions/private-house-v1-scope.md) |

Backend: FastAPI (`backend/app`), Python 3.11, `uv`-managed, `[tool.uv] package = false` — CLIs
run as `python -m app.<module>.cli`, not via `[project.scripts]`.

## Active branches / work in progress

- `integration/laundry-into-main` — active, unmerged; see the Laundry Wiki page.
- `worktree-015-laundry-room-option` (locked) — a separate, older, also-unmerged laundry design.
- `specs/009-guest-wc-placement` — spec committed, nothing implemented yet.
- `specs/005-hub-private-wing` — spec/plan/results committed, implementation not merged
  ("two hard acceptance gates failed") — `decision_status = REJECTED`.

## Open investigations (no code changed)

- Room capacity constraint, plan-not-realizable root cause — no successor doc yet.
- Layout-selection UX research — partially realized via `specs/006-engine-chosen-outline`.

## Guardrails / do-not-change rules

- **ReviewPage Generate guardrail**: preserve the blocking priority order and commit `8c4cdba`'s
  `disabledReason`/pending-message behavior. Don't change without a reproducible regression.
- **Never mutate git in the main checkout** from an agent session — the user runs git in the IDE
  on the same checkout concurrently, and other agent sessions may be working here too. No
  stash/checkout/reset from a session.
- **Corridor opening** (hall↔LDK) is a contract-level post-process (`app/demo/contract.py`), not
  an engine change.
- **Do not treat the production OpenAI parser as a source of truth for AI-test expected
  behavior.** It is an implementation under test, exactly like local Ollama models. Authoritative
  expected behavior is: approved product/architecture semantics, versioned golden expected outputs,
  and deterministic validation/contracts.
- **Only completed/approved behavior updates a canonical Wiki page.** An investigation or
  in-progress report never does, no matter how confident its own wording sounds — see the Laundry
  Wiki page for why this rule exists.

## Next recommended work

1. Wire Multi-Level Phase 1 into the live product path — see its Wiki page's Known follow-ups.
2. Land `integration/laundry-into-main`, then rewrite the Laundry Wiki page from scratch.
3. Guest-WC placement (009) — spec exists, nothing implemented.
4. `BAAI/bge-m3` (opt-in) is the recommended path to real semantic embeddings — see the Knowledge
   System Wiki page.

## Keeping this file current

When a task changes a subsystem's top-level status, update the table above and the linked Wiki
page together, then run `python -m app.knowledge.cli index --changed`. Do not add per-feature
detail here — that belongs on the Wiki page.
