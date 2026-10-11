# Review Page — Quality Panel, Room Details, Refusal Notice

Status: IMPLEMENTED_MERGED

## Current behavior

The frontend plan workspace (`DemoWorkspace`, screen D) now renders the architectural-quality
data the backend already computes and returns on `DemoDesign.quality` (Issues #17/#19/#37), which
until Issue #63 reached zero frontend files.

- **`QualityPanel`** (`frontend/src/components/review/QualityPanel.tsx`): a `<details>` element,
  collapsed by default, under the plan's room list. Shows the six M1–M6 metrics with a one-line
  meaning each, `dead_space_m2`, and `wasted_circulation_share` — every value read verbatim off
  `quality.metrics` (`QualityMetricsOut`), never computed in the browser. Renders nothing when
  `quality.metrics` is `null`. A per-metric corpus median (M3/M4/M5/M6) is shown beside the plan's
  own value when the contract carries one under `quality.metrics.corpus_median` — an optional,
  forward-compatible field; today's backend does not attach it, so this line is currently always
  absent in production, and the type/UI exist so a future backend addition needs no frontend change.
- **`RoomDetails`** (`frontend/src/components/review/RoomDetails.tsx`): hovering, focusing or
  clicking a room in the sidebar's room list (`DemoWorkspace`) selects it; `RoomDetails` then shows
  that room's exposure (`quality.exposure`: exterior sides, the window's side/width, or the reason
  none was placed), its wet-room privacy summary when present (`quality.wet_privacy`: entered-from
  room and zone class, which room the open door faces, privacy score), and every door touching the
  room (`design.doors`, matched by `a`/`b` against the room id) with its kind and width.
- **`RefusalNotice`** (`frontend/src/components/review/RefusalNotice.tsx`): replaces the old
  generic `demo-error` block in `App.tsx`. Shows the backend's own `code` (e.g.
  `CORRIDOR_WIDTH_NOT_FEASIBLE`, `LAUNDRY_UNPLACEABLE`) alongside its human sentence (`message`)
  and, when present, the support-facing `detail` — all three already carried by `DemoPipelineError`
  (`api.ts`); no new backend field.

Nothing here changes the plan drawing itself (`DemoPlan.tsx`, untouched) or `DemoWorkspace`'s
existing validation/warnings/legend sections.

- **`ConceptLabel`** (`frontend/src/design/ConceptLabel.tsx`, Issue #78): a small badge beside a
  plan's title — the large plan's title in the side panel, and each thumbnail's label in the
  options strip — read verbatim off `design.concept` (`DemoDesign.concept`, a Hebrew label and a
  one-sentence rationale as the badge's hover title). Renders nothing when `concept` is absent,
  which is every payload today: the backend only attaches it when
  `general_pipeline.CONCEPT_ENGINE_V2_ENABLED` is on, and that flag currently defaults to `False`
  (see [Concept Engine v2](concept-engine-v2.md)).

## Authoritative implementation

- `frontend/src/components/review/{QualityPanel,RoomDetails,RefusalNotice}.tsx` (+ `.css`).
- `frontend/src/design/ConceptLabel.tsx` (+ `.css`), wired into `DemoWorkspace.tsx` (Issue #78).
- `frontend/src/design/demoDesign.ts`: `DemoQualityMetrics`, `DemoExposure`, `DemoWetPrivacy`
  types and the corresponding fields added to `DemoQuality` — mirror `app.demo.contract`'s
  `QualityMetricsOut`/`ExposureOut`/`WetPrivacyOut`/`QualityOut`.
- Wiring: `frontend/src/design/DemoWorkspace.tsx` (room selection state, `QualityPanel`/
  `RoomDetails` placement), `frontend/src/App.tsx` (`RefusalNotice` replaces the inline error div).
- Tests: `frontend/src/components/review/{QualityPanel,RoomDetails,RefusalNotice}.test.tsx`;
  regression guard for the untouched plan drawing: `frontend/src/design/DemoPlan.test.tsx`
  (pre-existing, 55 tests over `DemoPlan`/`DemoWorkspace`/`PlanLegend`/`ReviewPage`) stays green.

## Current constraints/invariants

- Read-only: no client-side geometry or area arithmetic. Every number is read off a contract
  field; the one derived display (`PERCENT`/`RATIO` formatting) formats an already-computed ratio,
  it does not compute one.
- `quality.metrics.corpus_median` is an optional, additive field the frontend type supports but
  the live backend does not populate yet — see Known follow-ups.
- Selecting a room is a lightweight, additive affordance (a button per room-list row) — it does
  not touch `DemoPlan`'s SVG rendering, per this Issue's scope.

## Known follow-ups

- Wire an actual `quality.metrics.corpus_median` (or an equivalent baseline snapshot) from the
  backend, from `tests/regression_corpus/quality_baseline.json`'s four stats, so the panel's
  corpus-median line is populated in production rather than only in its fixture test.
- Selecting a room from the SVG drawing itself (not just the sidebar list) is future work — the
  layout-objects work (Issue #39) is the more natural place to add direct-on-drawing interaction.

## Last verified against git

Branch `agent/63-63-reviewpage-shows-the-quality-data-the`, based on
`origin/integration/holiday-yom-kippur-2026` at `1031418`.
