# Tasks: Hub Eligibility by Computed Feasibility

**Input**: specs/008-hub-eligibility/{spec,plan,research,data-model,quickstart}.md
**Branch**: `008-hub-eligibility` off `30e2312`, worked in a frozen worktree (the shared tree is edited concurrently)

## Phase 1: Setup

- [x] T001 Create the worktree/branch `008-hub-eligibility` at `30e2312` with `app/data/failures.json` and `.env` copied in

## Phase 2: Foundational

- [x] T002 Add `HUB_GATES`, `HubBound`, `HubEligibility`, `hub_eligibility()` to backend/app/vertical_slice/concept_generator.py per data-model.md
- [x] T003 Add `hub_bound(rooms, fw, fh, widths)` to backend/app/vertical_slice/concept_generator.py: per lobby width, `_hub_allocation` → grid over lobby depth, flank width, stack splits, foot boundary, ensuite share, foot depth; rectangles; seats, ensuite beside master, wet adjacency; early exit at the gates (research R3/R5); extract `_hub_widths()` from `_hub_concept`

## Phase 3: User Story 1 — hub delivered only where it can be good (P1)

- [x] T004 [US1] In `generate_concepts` compute the bound per hub candidate, decide eligibility, append the rationale suffix (research R6)
- [x] T005 [US1] Test `test_hub_bound_passes_narrow_deep_outlines_and_fails_wide_ones` in backend/tests/vertical_slice/test_concept_generator.py
- [x] T006 [US1] Test `test_hub_bound_never_reaches_the_wet_gate_with_three_wet_rooms`
- [x] T007 [US1] Test `test_hub_bound_is_cheap` (FR-007)

## Phase 4: User Story 2 — a rescued plan never becomes a refusal (P1)

- [x] T008 [US2] In `generate_concepts`, after the twin extension, stable-move `LAST_RESORT` hub candidates (forced then twin) to the end (research R4)
- [x] T009 [US2] Test `test_a_demoted_hub_is_the_last_resort`; ordering invariants in `test_generator_produces_a_bounded_candidate_set` and `test_hub_is_offered_only_for_three_or_more_bedrooms` restated for the last-resort block

## Phase 5: User Story 3 — explainable (P2)

- [x] T010 [US3] Test `test_an_eligible_hub_keeps_its_v2_place` (rationale carries the bound; eligible order unchanged)

## Phase 6: Polish & measurement

- [x] T011 Route T1 in backend/spikes/failure_log_sweep/hub_topology_bound.py through the engine's `hub_bound` (research R2); `--only T1` reproduces 1.65 / 2.38 / 1.32 / 1.28 / 1.27 / 1.42
- [x] T012 Measure per quickstart.md §3 in frozen worktrees (baseline `30e2312` vs feature): snapshot compare, `ab.py --toggle hub`, `quality_metrics.py --split-by-strategy`, `hub_rooms.py` (split by eligibility — `StrategyRecorder.chosen_rationale`), full test suite
- [x] T013 Write specs/005-hub-private-wing/RESULTS.md §8 with the SC-001…SC-006 table; update backend/spikes/failure_log_sweep/README.md; stop for review (no merge)

## Dependencies

T001 → T002 → T003 → T004 → T005–T007; T008 (needs T004) → T009; T010 needs T004; T011 needs T003; T012 needs T004 + T008; T013 needs T012.

## MVP

US1 + US2 together (T002–T009) — one without the other is either a regression (US1 alone refuses 7 rescues) or a no-op (US2 alone).

## Phase 7: Follow-up — eligible hubs take the witness (approved 2026-09-14)

- [x] T014 `HubSizing`; `hub_bound` returns the passing sizing as `HubBound.witness`; the bound honours the front band's width feasibility and depth cap (engine rules) so the witness is plannable
- [x] T015 `_plan_hub_wing(…, witness=…)` → `_plan_hub_wing_from_witness` (same checks) and `_hub_plan_tail` shared with v2's path; `_hub_public_widths` factored out and shared with the bound
- [x] T016 `generate_concepts`: ELIGIBLE hubs rebuilt from the witness via `_hub_from_witness` (same footprint/tree/access); LAST_RESORT untouched; failure reported in the rationale, never adjusted
- [x] T017 Tests updated (narrow case on the planned footprint 12 × 14.4; witness plans; wide case has no witness)
- [x] T018 Measured (RESULTS.md §9): 4/4 eligible pass all gates; 9/9 last resort and 95/95 non-hub byte-identical; LOST 0; rescues kept; 0 new test failures
