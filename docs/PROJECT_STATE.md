# Project State

A high-level index, not a growing history document. **Detailed current truth for each subsystem
lives in the [Project Wiki](wiki/INDEX.md)** — this file exists to say what major capabilities
exist, their current status at a glance, and where to read more. Historical detail stays in raw
reports (`docs/*.md`, `specs/*/`), retrievable through the Project Knowledge RAG
(`docs/PROJECT_KNOWLEDGE_RAG.md`) but deliberately not repeated here.

**Current main HEAD at last verification: `7814dc1` (agent-team follow-ups merged 2026-09-17).**

## Major capabilities and current status

| Subsystem | Status | Wiki page |
|---|---|---|
| Requirements / parsing semantics | IMPLEMENTED_MERGED | [wiki/architecture/requirements-parsing.md](wiki/architecture/requirements-parsing.md) |
| Geometry / validation | IMPLEMENTED_MERGED | [wiki/architecture/geometry-validation.md](wiki/architecture/geometry-validation.md) |
| L-Massing | IMPLEMENTED_MERGED | [wiki/features/l-massing.md](wiki/features/l-massing.md) |
| Wet Rooms | IMPLEMENTED_MERGED | [wiki/features/wet-rooms.md](wiki/features/wet-rooms.md) |
| Room Proportion / Quality Tier | IMPLEMENTED_MERGED | [wiki/features/room-proportion-quality-tier.md](wiki/features/room-proportion-quality-tier.md) |
| Multi-Level | IMPLEMENTED_MERGED (backend), not wired to product | [wiki/features/multi-level.md](wiki/features/multi-level.md) |
| Laundry | IMPLEMENTED_MERGED | [wiki/features/laundry.md](wiki/features/laundry.md) |
| Knowledge System (this RAG + Wiki + AI test harness) | IMPLEMENTED_MERGED | [wiki/architecture/knowledge-system.md](wiki/architecture/knowledge-system.md) |
| Review Page — Quality Panel, Room Details, Refusal Notice | IMPLEMENTED_MERGED | [wiki/features/review-page.md](wiki/features/review-page.md) |
| Interior Layout (engine-placed semantic furniture objects) | IMPLEMENTED_MERGED | [wiki/features/interior-layout.md](wiki/features/interior-layout.md) |
| Private House V1 scope | APPROVED (decision) | [wiki/decisions/private-house-v1-scope.md](wiki/decisions/private-house-v1-scope.md) |
| Autonomous Engineering Workflow (Agent Team) | LIVE — pilot passed 2026-09-17; governance since 2026-09-18: owner approves ROOT Issues and merges, the Team Lead executes everything else (child Issues, parallel workers); Telegram control plane; on `infra/telegram-control-plane` (PR #16, owner merges) | [wiki/architecture/agent-team-workflow.md](wiki/architecture/agent-team-workflow.md) |
| Product roadmap (owner-maintained, proposed only) | PROPOSED | [ROADMAP.md](ROADMAP.md) |

Backend: FastAPI (`backend/app`), Python 3.11, `uv`-managed, `[tool.uv] package = false` — CLIs
run as `python -m app.<module>.cli`, not via `[project.scripts]`.

## Active branches / work in progress

- `infra/telegram-control-plane` — owner-controlled governance (owner:approved, READY_FOR_OWNER,
  no auto-merge) + the Telegram owner control plane; running from the orchestrator home worktree;
  **PR #16 awaits the owner's merge.** Draft Issues #17–#21 (first five P0 roadmap topics) exist
  on GitHub as `agent:draft`, contracts under `.agent/proposals/p0/`; #17 was approved and queued
  by the owner on 2026-09-17 (first roadmap Issue in execution). Same branch, 2026-09-17 evening:
  subscription usage guard (auto-pause at 98 %, auto-resume after the reset, rate-limit requeue),
  3 concurrent workers, Telegram `answer()` fix; the owner's new P0 topic "Entrance-to-Circulation
  Integration / no entrance dead-end walls" added to `docs/ROADMAP.md` and drafted as Issue #22 (`agent:draft`, depends on #20).
  2026-09-18 (owner governance message): ROOT/child authorization model (`### Authorization`,
  `agent:child`, `agent:decomposed`, `agent:hold`), root-aware scheduler (work stealing, locks
  released at READY, READY never blocks unrelated work), graceful drain on SIGTERM, Team Lead
  status view; 18 governance tests (`tests/test_governance_parallel.py`). #17 merged (PR #23).
  2026-09-18 (Fri): weekend/holiday integration mode live — first period Yom Kippur 2026
  (`integration/holiday-yom-kippur-2026`); unified owner-approved roadmap (`docs/ROADMAP.md`, ROOTs
  #28–#46 + #18–#22); 7 Issues integrated on day one; one rollup PR to main follows the period.

- `integration/laundry-into-main` — landed: fast-forwarded onto `main` at `6499604`. No longer
  active work; kept for history. See the Laundry Wiki page.
- `worktree-015-laundry-room-option` (locked) — not a separate/rival laundry design; it is the
  source branch the Laundry capability was implemented on, merged whole into
  `integration/laundry-into-main` (`b678967`), which is now itself on `main`. Kept checked
  out/locked as a historical artifact, not for further changes.
- `specs/009-guest-wc-placement` — spec committed, nothing implemented yet.
- `specs/005-hub-private-wing` — spec/plan/results committed, implementation not merged
  ("two hard acceptance gates failed") — `decision_status = REJECTED`.

## Open investigations (no code changed)

- Room capacity constraint, plan-not-realizable root cause — no successor doc yet.
- Layout-selection UX research — partially realized via `specs/006-engine-chosen-outline`.
- **Non-rectangular geometry** (Issue #102, 2026-09-22) —
  `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`: the Geometry Core is a guillotine (slicing-tree)
  partition of rectangular rooms; module-by-module rectangle-assumption inventory for Geometry
  Core/validators C1-C29/M1-M6/hub-l-massing-wet-core guards/the demo contract/both renderers/the
  corpus signature; measured on a 20-plan real-ResPlan fixture
  (`backend/spikes/geometry_shapes/measure_real_plan_shapes.py`): 41.9% of real rooms are
  rectangles, 19.6% simple L-shapes, and **0/19 real plans' room layouts are guillotine-separable**;
  three candidate architectures (A — slicing tree + room merging, B — non-guillotine rectangular
  layout, C — polygonal layout) each scoped with effort/risk/a 2-week spike; recommends A first (in
  parallel with a spike proving/killing B), C deferred; proposed ROOT + children under
  `.agent/proposals/roadmap/`, not yet scheduled.

## Agent-team Issues

- **#24 Work reports and structured failure records** — every failure transition (worker
  failed/blocked, publish failed, CI red, review rejected, owner reject/change-request, a rate
  limit, `agentctl block`) emits one structured `failure_record` event and a fixed-template
  failure milestone comment; a per-Issue Markdown work report (`.agent/logs/reports/<issue>.md`,
  `agentctl report N`) is regenerated on every state change with a "What was done" section per
  attempt and a "Failure history" table; `agentctl audit N` shows the failure history before raw
  events; the Telegram compact status (`status.render_compact`) appends the short root cause next
  to a BLOCKED/repair-pending class. See the agent-team-workflow Wiki page's Observability section
  (`work_reports.py`).

## Guardrails / do-not-change rules

- **Agent PRs only through the workflow**: branches `agent/<issue>-<slug>` are owned by the
  orchestrator (`scripts/agentctl`); never push to them by hand, never merge them outside the
  merge policy. `.worktrees/` and `.agent/{state,logs,contracts}/` are local runtime state.
- **Agent Issue titles carry their own number**: `[agent] #N Title` on every open Issue, kept
  current with `agentctl issue renumber-titles` (see [wiki/agent-team.md](wiki/agent-team.md)).

- **ReviewPage Generate guardrail**: preserve the blocking priority order and commit `8c4cdba`'s
  `disabledReason`/pending-message behavior. Don't change without a reproducible regression.
- **Never mutate git in the main checkout** from an agent session — the user runs git in the IDE
  on the same checkout concurrently, and other agent sessions may be working here too. No
  stash/checkout/reset from a session.
- **Corridor opening** (hall↔LDK) is a contract-level post-process (`app/demo/contract.py`), not
  an engine change.
- **`INCONSISTENT_GEOMETRY`** (Issue #34) is a `DemoGenerationError` refusal code raised when
  validation check C27 finds a `RoomOut`'s displayed width×depth disagreeing with its own area (or
  the building's `gross_area_m2` disagreeing with the sum of its rooms') — see the Geometry /
  Validation Wiki page. It is a data-integrity refusal, not a feasibility one (not in
  `_FEASIBILITY_CODES`); on a real solved design it never fires.
- **Do not treat the production OpenAI parser as a source of truth for AI-test expected
  behavior.** It is an implementation under test, exactly like local Ollama models. Authoritative
  expected behavior is: approved product/architecture semantics, versioned golden expected outputs,
  and deterministic validation/contracts.
- **Only completed/approved behavior updates a canonical Wiki page.** An investigation or
  in-progress report never does, no matter how confident its own wording sounds — see the Laundry
  Wiki page for why this rule exists.

## Next recommended work

The owner's prioritized list is `docs/ROADMAP.md` (P0 first: planning quality, entrance,
doors, windows, laundry — drafted as Issues #17–#21). The items below predate it and stay valid:

1. Wire Multi-Level Phase 1 into the live product path — see its Wiki page's Known follow-ups.
2. Guest-WC placement (009) — spec exists, nothing implemented.
3. `BAAI/bge-m3` (opt-in) is the recommended path to real semantic embeddings — see the Knowledge
   System Wiki page.
4. Wire `laundry_notice`/a laundry toggle into the ReviewPage product surface — see the Laundry
   Wiki page's Known follow-ups.

## Keeping this file current

When a task changes a subsystem's top-level status, update the table above and the linked Wiki
page together, then run `python -m app.knowledge.cli index --changed`. Do not add per-feature
detail here — that belongs on the Wiki page.
