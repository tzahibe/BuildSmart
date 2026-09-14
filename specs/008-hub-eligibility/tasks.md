# Tasks: Hub Eligibility by Computed Feasibility

**Input**: specs/008-hub-eligibility/{spec,plan,research,data-model,quickstart}.md
**Branch**: `008-hub-eligibility` off `30e2312`, worked in a frozen worktree (the shared tree is edited concurrently)

## Phase 1: Setup

- [ ] T001 Create the worktree/branch `008-hub-eligibility` at `30e2312` with `app/data/failures.json` and `.env` copied in (measurement needs both)

## Phase 2: Foundational

- [ ] T002 Add `HUB_GATES` (bedroom 1.35, master 1.40, wet 0.80 — §6's numbers, one place) and the `HubBound` / `HubEligibility` values to backend/app/vertical_slice/concept_generator.py per data-model.md
- [ ] T003 Add `hub_bound(spec, hub_rooms, fw, fh, widths)` to backend/app/vertical_slice/concept_generator.py: for each lobby width, `_hub_allocation` → enumerate lobby depth, west flank width, stack split, foot boundary, foot depth on a 0.25 m grid; build rectangles; seats (≥ 1.10 m shared edge with the lobby), ensuite beside master, wet adjacency (M5 rule, kitchen ignored — conservative), bedroom-class aspects; early exit once a sizing passes the gates (research R3/R5)

## Phase 3: User Story 1 — hub delivered only where it can be good (P1)

- [ ] T004 [US1] In `generate_concepts` (backend/app/vertical_slice/concept_generator.py) compute the bound for each hub candidate, decide eligibility, and append the rationale suffix (research R6)
- [ ] T005 [US1] Test in backend/tests/vertical_slice/test_concept_generator.py: 12 × 18 outline, 3BR + safe + 2 wet → `ELIGIBLE`, candidate order identical to v2; 14.25 × 12.35 → `LAST_RESORT`
- [ ] T006 [US1] Test: 3-wet brief → `LAST_RESORT` with the wet gate unreachable (`gated_bedroom_aspect is None`)
- [ ] T007 [US1] Cost test: `hub_bound` on 18 × 12 (the slowest, fails late) within FR-007's budget

## Phase 4: User Story 2 — a rescued plan never becomes a refusal (P1)

- [ ] T008 [US2] In `generate_concepts`, after the twin extension, stable-move `LAST_RESORT` hub candidates (forced then twin) to the end of the list (research R4)
- [ ] T009 [US2] Test: on the wide outline the last two candidates are the hub's forced tree then its twin, and every other parti's twin precedes them; on the narrow outline nothing moved

## Phase 5: User Story 3 — explainable (P2)

- [ ] T010 [US3] Test: the wide outline's hub rationale names the failing gate and the bound value; the narrow one says "eligible" with its value

## Phase 6: Polish & measurement

- [ ] T011 Replace the T1 generator in backend/spikes/failure_log_sweep/hub_topology_bound.py with an import of the engine's `hub_bound` (research R2) and re-run `--only T1 --grid 0.25`: 1.65 / 2.38 / 1.32 / 1.27 / 1.27 / 1.42 expected
- [ ] T012 Measure per quickstart.md §3 in two frozen worktrees (baseline `30e2312` vs feature): snapshot compare, `ab.py --toggle hub`, `quality_metrics.py --split-by-strategy`, `hub_rooms.py`, full test suite
- [ ] T013 Write specs/005-hub-private-wing/RESULTS.md §8 with the SC-001…SC-006 table; update backend/spikes/failure_log_sweep/README.md; stop for review (no merge)

## Dependencies

T001 → T002 → T003 → T004 → T005–T007; T008 (needs T004) → T009; T010 needs T004; T011 needs T003; T012 needs T004 + T008; T013 needs T012.

## Parallel opportunities

T005/T006/T007/T009/T010 are independent tests once T004 + T008 exist; T011 can run alongside the tests.

## MVP

US1 + US2 together (T002–T009) — one without the other is either a regression (US1 alone refuses 7 rescues) or a no-op (US2 alone).
