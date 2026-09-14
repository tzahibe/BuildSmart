# PR: feat: Engine-chosen building outline (006)

Open at: https://github.com/tzahibe/BuildSmart/compare/main...006-engine-chosen-outline?expand=1

## Summary

The building outline used to be a required input on its own screen ("בחר/י את מתאר הבניין"). Measured over the production refusal log, the person's choice planned in **30 %** of briefs while each of the engine's own four preferred shapes planned in **35–45 %**. This PR moves the outline search the service already ran *after* a refusal to *before* planning, makes the person's outline optional, and selects the plans shown across outlines by architectural family instead of by footprint proportion.

- **Backend** (`app/demo/service.py`, `scope.py`, `contract.py`, `router.py`): `selected_footprint` is optional; engine outlines are surveyed on the fast path, the primary outline is chosen by the existing area-only rule among outline primaries, only that outline is re-run for alternatives; alternatives are de-duplicated by family (display key only). The refusal sentence "מתאר של X×Y … כן מתאפשר" is gone — a shape that works is now a plan on the screen. `run_general` and everything below it are **unchanged**; the one addition in `general_pipeline.py` is the read-only `RealizedPlan.family_signature`.
- **Frontend**: the form creates the project directly; the cards live under "מתקדם — קביעת מתאר ידנית" (an explicit outline is authoritative); the review page and the workspace state the outline each plan occupies; one note when the person's outline could not be planned.
- **Harness**: `spikes/failure_log_sweep/outline_ab.py` (advanced vs main flow) and the frozen `before.json`.

## Measured (426-brief log, base `main` @ `855a977`)

| Gate | Result |
|---|---|
| Advanced-path primaries byte-identical to before (SC-005) | **117/117**, LOST 0 |
| Briefs receiving a plan, main flow (SC-001) | **257 / 426** (before 117) — 142 rescued at a median 97 % of the requested area |
| Main-flow non-regression | 2 lost, both predicted person-only briefs (named in RESULTS.md) |
| First-plan gross ÷ requested (SC-002) | median **0.975** |
| Briefs with ≥ 2 distinct families shown (SC-003, restated ≥ 48 on `main`) | **50 / 117** |
| Same-family + same-outline pairs shown (SC-006) | **0** (was 456) |
| Shown plans failing validation (SC-004) | **0** |
| Refusals naming an outline (SC-007) | **0**; 142/142 capacity diagnoses kept |
| Latency, median (SC-008) | briefs that planned before: advanced 1.20 s, main flow **4.11 s**; refused before: 3.05 s / 2.80 s |

Full detail: `specs/006-engine-chosen-outline/RESULTS.md`.

## Test plan

- [x] Backend `pytest`: 797 passed, 6 skipped (main: 764 / 7)
- [x] Frontend `vitest`: 118 passed (main: 109); `vite build` OK
- [x] Live E2E through the real backend + Chrome: `frontend/e2e/engine-outline.spec.ts` 3/3
- [x] `outline_ab.py --before before.json` — table above
- [ ] Reviewer: open the form, submit without touching "מתקדם", confirm the plan's outline label reads "מתאר אוטומטי"; then pick a preset under "מתקדם" and confirm "המתאר שהזנת" (or the replacement note when that preset does not plan)

## Deliberately out of scope

- **SSE provisional preview** (Part C) — deferred to a follow-up feature with its own contract and tests.
- The older Playwright specs (`footprint-selection`, `spatial-edit`) were already stale on `main` and are not repaired here; `tsc -b` reports the same 6 pre-existing errors as `main`.
- Quality-aware ranking, concurrency, more outline shapes, generator changes — see spec §6.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
