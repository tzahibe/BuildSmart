# Implementation Plan: Engine-Chosen Building Outline

**Branch**: `006-engine-chosen-outline` (not yet created; `main` at `5fd9474`) | **Date**: 2026-09-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-engine-chosen-outline/spec.md`

## Summary

Move the outline search the service already performs on the refusal path (`_outline_that_plans`)
to *before* planning, make the person's outline optional, and select the plans shown across all
outlines by architectural family instead of by footprint proportion. Concretely: `check_supported`
accepts a project with no `selected_footprint`; `generate_demo_design` plans a list of outlines —
the person's (if given) first, then the de-duplicated `feasible_options` shapes — each through the
unchanged `run_general`; a new cross-outline selection picks the primary (nearest requested area)
and up to two alternatives that exhaust distinct families before repeating one; every plan carries
its outline and origin; the streaming endpoint emits the first plan as soon as it exists and
reports per-outline progress. The frontend drops the footprint screen from the main path and folds
the existing `FootprintSelection` component into a collapsed "advanced" disclosure on the form.
Nothing inside one outline's planning changes (FR-012): `concept_generator`, `geometry_core`,
`validation`, `doors/windows/furniture`, `general_pipeline.run_general` are byte-identical.

## Technical Context

**Language/Version**: Python 3.11 (`backend/`, venv `backend/.venv`); TypeScript / React (`frontend/`, Vite + Vitest).

**Primary Dependencies**: none new. Backend: `app.demo.service` (orchestration — the only place with
new logic), `app.demo.scope` (footprint becomes optional), `app.demo.site_geometry.feasible_options`
(outline candidates — unchanged), `app.demo.contract` (additive fields), `app.demo.router` (SSE
events — additive), `app.vertical_slice.general_pipeline` (one read-only property, `family_signature`,
on `RealizedPlan`). Frontend: `App.tsx` (view sequence), `FootprintSelection.tsx` (reused under a
disclosure), `DemoPlan.tsx` (outline label per plan), `api.ts` (new SSE event, new fields).

**Storage**: N/A. `Project.selected_footprint` is already `Optional`; stored projects are unaffected.

**Testing**: pytest (`backend/tests`; baseline **773 passed, 6 skipped** at `5fd9474`);
Vitest (`frontend/src/**/*.test.tsx`); the failure-log sweep harness `backend/spikes/failure_log_sweep/`
extended with an outline A/B (`outline_ab.py`) that is the acceptance instrument for SC-001…SC-008.

**Target Platform**: backend service (macOS/Linux) + browser SPA.

**Project Type**: web application (backend + frontend).

**Performance Goals**: SC-008 — median request time ≤ 4× today's median over the 424-brief log; the
first plan is delivered to the screen as soon as the first outline validates, so perceived latency
stays close to today's for the outline that succeeds first.

**Constraints**: additive contract only (existing `DemoPlanSet` consumers keep working); the
per-outline pipeline is byte-identical (gate: 127/127 primary designs identical through the
advanced path); deterministic outline order (`PREFERRED_RATIOS` order, de-duplicated); no concurrency
in v1 (research R4); every plan shown passes the same gate as today's primary (no new code path
produces a `DemoDesign` except through `_finish`'s existing checks).

**Scale/Scope**: 4 outlines + optional explicit one per request; ≤ 3 plans shown; 424-brief log as the
measurement population.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the unfilled template — no principles or gates are defined.
The project's de-facto rules (its memory, applied in features 004–005) are used as gates:

| De-facto rule | How this plan satisfies it |
|---|---|
| Diagnose before patching the planner | The planner is not patched. Every number in the spec came from a full per-candidate trace of all outlines on the 424-brief log; the change is confined to orchestration and presentation. |
| Planner gains must be quality-checked (built area vs requested) | SC-002 measures built ÷ requested for the first plan; a rescued brief counts only at ≥ 80 % of the ask in the A/B script, as in `ab.py`. |
| Additive; existing behaviour byte-identical | `run_general` and everything below it untouched; the advanced path reproduces today's request exactly (SC-005). Contract fields are additive with defaults. |
| Stop at the reported scope | No quality ranking (R2), no concurrency (R4), no new outline shapes, no generator change. Each is named as deferred. |

Post-design re-check: unchanged. Phase 1 adds one property on `RealizedPlan`, one selection
function in the service, additive contract fields and one SSE event type. No module below the
service is modified.

## Project Structure

### Documentation (this feature)

```text
specs/006-engine-chosen-outline/
├── spec.md              # feature specification
├── plan.md              # this file
├── research.md          # Phase 0: decisions taken against the actual code
├── data-model.md        # Phase 1: Outline, OutlineResult, PlanSelection, contract additions
├── quickstart.md        # Phase 1: how to prove the feature end to end
├── contracts/
│   └── demo-plan-set.md # Phase 1: additive changes to DemoPlanSet / DemoDesign / SSE stream
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
backend/
├── app/demo/
│   ├── service.py            # CHANGED: outline loop before planning; cross-outline selection;
│   │                         #   refusal without outline suggestion; _outline_that_plans retired
│   ├── scope.py              # CHANGED: selected_footprint optional; fit check only when given
│   ├── contract.py           # CHANGED (additive): DemoDesign.outline / .family; DemoPlanSet.search
│   ├── router.py             # CHANGED (additive): SSE `plan` event + outline-major progress;
│   │                         #   failure context records outlines tried
│   └── site_geometry.py      # unchanged (feasible_options is the candidate source)
├── app/vertical_slice/
│   └── general_pipeline.py   # CHANGED (additive): RealizedPlan.family_signature (read-only)
├── spikes/failure_log_sweep/
│   ├── outline_ab.py         # NEW: main-flow vs advanced-path sweep; SC-001…SC-008
│   └── sweep.py              # CHANGED: project_from_context(ctx, with_footprint=True)
└── tests/
    ├── test_demo_p0.py               # CHANGED: footprint-optional scope; selection tests
    ├── test_demo_outline_selection.py # NEW: cross-outline selection rules (FR-004/006/007/008)
    └── vertical_slice/test_general_pipeline.py  # CHANGED: family_signature invariants

frontend/src/
├── App.tsx                   # CHANGED: 'footprint' view leaves the main sequence; advanced disclosure
├── design/FootprintSelection.tsx  # CHANGED: usable inline under a disclosure (no confirm gate)
├── design/DemoPlan.tsx       # CHANGED: outline label + origin per plan
├── api.ts / design/demoDesign.ts  # CHANGED: new fields, `plan` SSE event
└── App.test.tsx, design/*.test.tsx  # CHANGED accordingly
```

**Structure Decision**: web application, existing layout. All backend logic lands in `app/demo/`
(the orchestration layer that already owns the outline search); the one addition below it is a
pure, read-only signature property on `RealizedPlan`, next to the existing `layout_signature`.

## Phase 0 — Research (see [research.md](./research.md))

Nine decisions taken against the code: R1 where the loop lives · R2 selection rule across outlines ·
R3 family signature definition and placement · R4 sequential vs concurrent · R5 progressive delivery
over SSE · R6 scope changes for an optional footprint · R7 refusal semantics once all outlines are
tried · R8 contract additions · R9 non-regression instrument. No `NEEDS CLARIFICATION` remained.

## Phase 1 — Design

- [data-model.md](./data-model.md): `Outline`, `OutlineResult`, `PlanSelection`, family signature
  invariants, contract additions and their defaults.
- [contracts/demo-plan-set.md](./contracts/demo-plan-set.md): additive JSON fields and the SSE
  event sequence (`progress` → `plan` → `done` | `error`).
- [quickstart.md](./quickstart.md): run the two sweeps, the tests and the UI walk-through; the
  expected numbers for every SC.

## Complexity Tracking

No constitution violations. One design choice deserves the note: the cross-outline selection is a
second selection layer on top of `run_general`'s own (candidate order within one outline). It is kept
in the service, not pushed into `run_general`, so that the per-outline pipeline stays byte-identical
and the advanced path can reproduce today's output by construction (R1).
