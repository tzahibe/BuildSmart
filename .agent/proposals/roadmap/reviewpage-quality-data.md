# [agent] ReviewPage shows the quality data the engine already produces: M1–M6 metrics, exposure report, wet-room privacy, door/window facts

### Goal

The owner can SEE the architectural-quality work in the app: the ReviewPage renders the quality data the
backend already returns (per-plan M1–M6 metrics, the window/exposure report per room, the wet-room privacy
record, service-door widths, refusal reasons) — read-only, from the contract, no client-side computation.

### Current behavior

Since #17, #19, #37 the demo contract carries `quality.metrics` (M1–M6, dead_space_m2, wasted_circulation_share),
`quality.exposure` (per room: exterior sides, window side/width or the reason none was placed) and the wet-room
privacy record; `DoorOut.width_m` distinguishes 0.8 m service doors. The frontend renders none of it: 0 frontend
files changed in the whole P0 wave, so a plan looks identical to the owner even though its validation, policies
and reports changed.

### Required behavior

1. A `QualityPanel` on the ReviewPage (collapsed by default under the plan): the six M-values with a one-line
   meaning each and the corpus median for context (from the contract when present), `dead_space_m2`,
   `wasted_circulation_share`.
2. Per-room details on hover/selection: exposure (exterior walls, window side and width, or why no window),
   wet-room privacy summary (entered from, faces, exposure score) where present, door kind and width.
3. Refusals: the ReviewPage shows the refusal code and the human sentence the backend returns (C19/C24/C23…)
   instead of a generic failure.
4. Everything is rendered from the contract fields; the audit test that forbids client-side geometry/area math
   stays green; the existing plan drawing is unchanged.

### Acceptance Criteria

- AC-1: the QualityPanel renders the six metrics, dead space and wasted circulation from a fixture contract (component test) and is absent when `quality.metrics` is null
- AC-2: selecting a room shows its exposure and, for wet rooms, its privacy summary, from the contract (component test)
- AC-3: a refused design shows the backend's refusal code and sentence (component test)
- AC-4: frontend lint, types and unit tests are green and the plan drawing snapshot is unchanged

### Out of scope

Editing the plan, new backend fields, restyling the ReviewPage beyond the panel, the layout objects (Issue #39 adds them later).

### Affected domains

frontend, knowledge

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

none

### Required locks

frontend-review (exclusive)

### Verification plan

- AC-1 -> vitest:frontend/src/components/review/QualityPanel.test.tsx
- AC-2 -> vitest:frontend/src/components/review/RoomDetails.test.tsx
- AC-3 -> vitest:frontend/src/components/review/RefusalNotice.test.tsx
- AC-4 -> static:frontend-lint ; static:frontend-types ; vitest:frontend/src/components/plan/PlanCanvas.test.tsx

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/features/review-page.md (new: what the panel shows and where each number comes from), docs/PROJECT_STATE.md.

### Knowledge check

Consulted: `backend/app/demo/contract.py` (QualityOut.metrics / exposure, DoorOut), the frontend `src/components`
tree (no consumer of these fields), roadmap topic "ReviewPage completion" (P2) — pulled forward on the owner's
approval of 2026-09-19 because the P0 quality wave is invisible without it. Nothing of this exists yet.
