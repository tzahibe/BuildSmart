# Tasks: Hub-Organised Private Wing

**Input**: Design documents from `/specs/005-hub-private-wing/` (spec.md, plan.md, research.md, data-model.md, quickstart.md)

**Tests**: Included — spec §2 and §7 require one pinned test per user story, each verified to fail with the parti disabled, plus the sweep/quality gates in §6.

**Organization**: Phases 1–2 promote the measurement harness and add the additive vocabulary; phases 3–6 are the four user stories from spec §2; phase 7 runs the acceptance gates and freezes the baseline.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 (hub wing, P1), US2 (wet cluster, P2), US3 (master suite, P2), US4 (non-regression, P1)
- All paths are repository-relative; the engine work is in `backend/app/vertical_slice/concept_generator.py` unless stated

## Hard constraints carried into every task

Additive only: no existing `ROOM_TEMPLATES` row, no existing parti, `plan_layout`, `_plan_front_band`,
`_seam_options`, `_build_access` rules or any Geometry Core module may change. Hub candidates are
returned to `generate_concepts` like every other candidate, so they receive the forced-first /
unforced-twin fallback (`_free_twin`) without hub-specific code. Eligibility ≥ 3 bedrooms. FLEX refused.
Deterministic, bounded search. Corridor rectangle = root→`HALL` path stays forced in the twin.

---

## Phase 1: Setup — promote the measurement harness

**Purpose**: the acceptance gates in spec §6 are numbers produced by scripts that today live only in a session scratch directory; make them part of the repo before any implementation so every later phase can be measured the same way.

- [ ] T001 Create `backend/spikes/failure_log_sweep/__init__.py` and `README.md` explaining the 418-scenario sweep (source: `backend/app/data/failures.json`, de-duplicated by request context) and the three gates it measures (byte-identical primaries, ≥80 % area rule, latency)
- [ ] T002 [P] Port `sweep.py` (`project_from_context`, `NEEDED`, `run_one`) to `backend/spikes/failure_log_sweep/sweep.py`; it must import only from `app.*`
- [ ] T003 [P] Port the service-level A/B to `backend/spikes/failure_log_sweep/ab.py` with a `--toggle {twins,hub}` argument: OFF wraps `concept_generator.generate_concepts` to drop candidates by strategy/rationale; report planned OFF/ON, full-signature `primary design identical` count, LOST, GAINED with requested/delivered/% and validators, refusal-code table, per-scenario latency median and worst regression split by "already planned" vs "not"; write `gained.json`
- [ ] T004 [P] Port `quality_metrics.py` to `backend/spikes/failure_log_sweep/quality_metrics.py` with `--split-by-strategy` (M1 aspect by room type, M2 exposure, M3 circulation share, M4 hall doors + hall long/short, M5 wet adjacency, M6 public contiguity), reading `DemoDesign` walls/doors/open_interfaces as today
- [ ] T005 Run the ported `ab.py --toggle twins` once and record its output in `backend/spikes/failure_log_sweep/BASELINE.md` (expected: 85 → 111, 85/85 identical, 17/26 counted) so the hub phases have a frozen "before"

**Checkpoint**: `BASELINE.md` exists and matches the numbers in spec §1 and quickstart.

---

## Phase 2: Foundational — additive vocabulary (blocking)

**Purpose**: the enum members, template row and role mapping every user story needs. No behaviour change: nothing produces a hub yet.

- [ ] T006 (dropped — no new `ProgramRole`; the hub keeps role HALL, research R1; `geometry_core/` is not touched)
- [ ] T007 Add `ConceptStrategy.HUB_PRIVATE_WING = "HUB_PRIVATE_WING"` in `backend/app/vertical_slice/concept_generator.py`
- [ ] T008 Add module constant `HUB_TEMPLATE = RoomTemplate(6.0, 8.5, 12.0, 2.4, 1.5, elasticity=0.1)` in `backend/app/vertical_slice/concept_generator.py` next to `ROOM_TEMPLATES`, with a PRODUCT-POLICY comment citing the census (hub 2.5–3.5 m, aspect ≤ 1.5, 4–7 doors); `ROOM_TEMPLATES` itself is not modified
- [ ] T009 (dropped — `_roles_of` unchanged because the hub's role is HALL)
- [ ] T010 Add `test_vocabulary_is_additive` in `backend/tests/vertical_slice/test_concept_generator.py`: every pre-existing `ROOM_TEMPLATES` row equals a literal snapshot of its current values (all 16 roles); `ConceptStrategy` contains `HUB_PRIVATE_WING`; `HUB_TEMPLATE.min_short_side_m == 2.4` and `max_aspect_ratio == 1.5`
- [ ] T011 Run `backend/.venv/bin/python3 -m pytest tests/ -q` — must be 764 passed (763 + T010), 7 skipped, 0 failed

**Checkpoint**: vocabulary in place, suite green, no plan changed (re-run `ab.py --toggle twins` if in doubt: identical to BASELINE.md).

---

## Phase 3: User Story 1 — a ≥ 3-bedroom brief gets a hub-organised private wing (Priority: P1) 🎯 MVP

**Goal**: `HUB_PRIVATE_WING` produces a plan whose private wing is a compact room lobby (long/short ≤ 1.5, short side ≥ 2.4 m) with 4–5 realised doors, every habitable room on the envelope, all existing validators passing.

**Independent Test**: quickstart §2 — `run_general_from_site(F.exact_rectangle(), (20, 24), ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2, open_plan_living=True, target_built_area_m2=170))` returns a validated design whose strategy is `HUB_PRIVATE_WING`.

### Tests for User Story 1 (write first; must fail before T016–T021)

- [ ] T012 [P] [US1] Add `test_hub_wing_is_a_compact_lobby_with_four_to_five_doors` in `backend/tests/vertical_slice/test_concept_generator.py`: the quickstart §2 brief yields `strategy == HUB_PRIVATE_WING`, hall net short side ≥ 2.4, long/short ≤ 1.5, 4 ≤ interior doors on `HALL` ≤ 5, `validation.ok`
- [ ] T013 [P] [US1] Add `test_hub_is_offered_only_for_three_or_more_bedrooms`: `generate_concepts` for a 2-bedroom programme contains no `HUB_PRIVATE_WING` candidate; for 3 bedrooms it contains at least one, and every hub candidate has an unforced twin after all forced trees (rationale ends with `FREE_TWIN_RATIONALE`)
- [ ] T014 [P] [US1] Add `test_hub_refuses_flex_like_the_front_band`: a brief with `target_built_area_m2` above `program_capacity_gross_m2` yields a `HUB_PRIVATE_WING` rejection with reason `INSUFFICIENT_WING_AREA` and no hub candidate
- [ ] T015 [P] [US1] Add `test_hub_root_to_hall_cuts_stay_forced_in_the_twin`: for the hub candidate's twin, walk the tree — every `Split` on the path to `Leaf("HALL")` has `fixed_at_u is not None`, every other `Split` has `None`

### Implementation for User Story 1

- [ ] T016 [US1] Implement `_hub_allocation(rooms) -> HubAllocation | ConceptRejection` per data-model.md: flanks = first two bedrooms/safe room; foot slots = master(+ensuite as a nested slot, bedroom nearest the hub's x-range), then safe room, then wet rooms in consecutive slots; `needs_door = 2 + len(foot)`; reject `ACCESS_DEGREE_EXCEEDED` when `needs_door > 5` or `len(foot) < 2`
- [ ] T017 [US1] Implement `_plan_hub_wing(rooms, allocation, fw, fh, hub_w) -> tuple[HubPlan | None, PlanFailure | None]` per data-model.md: areas from `scale_program(rooms, Σ target)`; `hub_d`; flank widths via `_row_widths` semantics with the hub width fixed; foot depth via the `_row_depths` rule; foot widths via `_row_widths`; band depth = remainder capped by the binding public room (reuse `_plan_front_band`'s cap logic); every failure returns the existing precise `RejectionReason` with `shortfall_m` where measurable; check each foot slot's and `public[0]`'s x-overlap with the hub ≥ 1.10 m (`INTERIOR_DOOR_WIDTH_M + 2*DOOR_MARGIN_M`, imported from `doors.py`, not re-typed)
- [ ] T018 [US1] Implement `_hub_concept(spec, rooms, candidate) -> tuple[ConceptCandidate | None, ConceptRejection | None]`: eligibility (`bedrooms ≥ 3`), FLEX refusal (research R7); build the working room list by replacing the variant's HALL room with `ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION, HUB_TEMPLATE)` so sizing, `minimum_footprint_width_m` and access all see the hub's template (research R1); loop `_proportions(...)` × `hub_w ∈ (3.0, 2.7, 3.3, 2.4, 3.6)` nearest-target-first, first plan wins; keep the nearest miss via `_nearest_miss`; build the tree exactly as data-model.md shows (band `_forced_v_chain`, hub band with `Leaf("HALL")`, foot `_forced_v_chain` with a nested V for a master+ensuite slot) with `m_to_u` forced positions; access via `_build_access(rooms, ["HALL"], public_ids, open_plan, hall_for, hall_borders_only_first_public=True)`; `Concept(fixture, "HALL", Side.N, fw, fh)`; rationale names the hub size and door count
- [ ] T019 [US1] Wire `_hub_concept` into `generate_concepts` immediately after the `_front_band_concept` call for each variant: append the candidate to `accepted`, append the rejection to `rejections` when `variant is rooms`; touch nothing else in the loop (the area sort and the twin append already handle ordering and fallback — research R2)
- [ ] T020 [US1] Run T012–T015 (`pytest -k hub`) — all pass; then run the full suite — 768 passed, 7 skipped, 0 failed
- [ ] T021 [US1] Run `backend/.venv/bin/python3 spikes/failure_log_sweep/ab.py --toggle hub` and `quality_metrics.py --split-by-strategy`; record in `specs/005-hub-private-wing/RESULTS.md`: primaries identical (must be 111/111), gained with area %, hub selected count, "hub candidate but another parti won" count, hub rejections by reason, hub-vs-non-hub metrics, latency delta

**Checkpoint**: US1 delivers a validated hub plan; every pre-existing primary plan byte-identical.

---

## Phase 4: User Story 2 — wet rooms cluster in the foot band (Priority: P2)

**Goal**: with ≥ 2 shared wet rooms they sit side by side in the foot band sharing an interior wall, each with a hub door; a single shared wet room pairs with the laundry when one exists.

**Independent Test**: a 3BR + 3-wet brief on 20 × 24 yields a hub plan in which `BATH_2` and `TOILET_1` (the shared wet rooms) share an INTERIOR wall segment and both have a door to `HALL`.

- [ ] T022 [P] [US2] Add `test_hub_wet_rooms_are_back_to_back_at_the_foot` in `backend/tests/vertical_slice/test_concept_generator.py` (assert via `DemoDesign`/design walls: a wall segment with `boundary_context == "INTERIOR"` whose `room_ids` are exactly the two shared wet rooms; both have a placeable door to HALL)
- [ ] T023 [US2] In `_hub_allocation`, order the foot slots so shared wet rooms (and LAUNDRY, when a future programme adds it) occupy consecutive slots at the hub-facing end, with the master slot at the other end; document the rule in the docstring with the census figure (~20/21 plans)
- [ ] T024 [US2] Extend T021's quality run: wet-room adjacency on hub plans must be ≥ 80 %; record in RESULTS.md

**Checkpoint**: wet adjacency on hub plans ≥ 80 % without touching non-hub plans.

---

## Phase 5: User Story 3 — the master suite is one block (Priority: P2)

**Goal**: master + ensuite share one foot slot; the ensuite is entered from the master (existing `entered_from`), the master's door opens onto the hub, the ensuite has none.

**Independent Test**: a 3BR + 2-wet brief yields a hub plan where `BATH_1.entered_from == "MASTER"`, there is a `MASTER→BATH_1` door and no `HALL→BATH_1` door, and MASTER's x-range overlaps the hub by ≥ 1.10 m.

- [ ] T025 [P] [US3] Add `test_hub_master_suite_shares_one_slot` in `backend/tests/vertical_slice/test_concept_generator.py`
- [ ] T026 [US3] In `_hub_allocation`/`_plan_hub_wing`, realise the `[master, ensuite]` slot as a nested V split inside the foot `_forced_v_chain` (widths from `_row_widths` on the slot's net width), oriented so the master is the member overlapping the hub (adapt `_orient_row`'s rule to the x-axis); the ensuite may be interior (research R5)
- [ ] T027 [US3] Re-run T012/T022/T025 and the full suite — green

**Checkpoint**: master aspect on hub plans measured; target median ≤ 1.40.

---

## Phase 6: User Story 4 — nothing that plans today stops planning (Priority: P1)

**Goal**: the parti is purely additive; every scenario that produced a plan before produces the identical primary plan; refusal codes elsewhere unchanged or improved.

**Independent Test**: `ab.py --toggle hub` reports `primary design identical = 111/111`, `LOST = 0`, `crashes = 0`.

- [ ] T028 [P] [US4] Add `test_existing_partis_are_byte_identical_with_the_hub_present`: for the four `PROGRAMS` fixtures and the four `GEOMETRIES`, compare the full room signature of the delivered design with the hub strategy filtered out of `generate_concepts` vs present — identical whenever the hub does not win, and when the hub wins, the forced-only ordering still contains the previous winner at the same index
- [ ] T029 [US4] Run `ab.py --toggle hub` on the final code; if `primary design identical < 111/111` or `LOST > 0`, STOP — diagnose the exact scenario and reason, write it into RESULTS.md, do not add a heuristic
- [ ] T030 [US4] Run the latency comparison from `ab.py` (already-planned median OFF vs ON; worst regression); NFR-2 requires the added cost ≤ one strategy's worth — record in RESULTS.md

**Checkpoint**: gates in spec §6 rows "Scenarios that planned before", "Test suite" and "Newly planning" all satisfied.

---

## Phase 7: Polish & acceptance freeze

- [ ] T031 Update spec §6 with the measured values (hub long/short, doors, wet adjacency, bedroom/master aspect medians, exposure, circulation share) and §9 Q5 with the actual hub-selected / other-parti-won / rejected counts
- [ ] T032 [P] Update `.claude` project memory (`architectural-quality-gaps-measured.md`) with the hub result — what closed, what did not, and the measured hub-vs-non-hub metrics
- [ ] T033 Restore any test-regenerated `backend/tests/**/**_report.json` timing noise (`git checkout -- "*_report.json"`), then commit `concept_generator.py`, the tests, `backend/spikes/failure_log_sweep/` and `specs/005-hub-private-wing/` as one commit whose message carries the before/after table; record the hash in RESULTS.md

---

## Dependencies & execution order

- Phase 1 (T001–T005) → Phase 2 (T006–T011) → US1 (T012–T021) → US2 (T022–T024) and US3 (T025–T027) may proceed in parallel after US1 → US4 (T028–T030) last, on the final code → Phase 7.
- US2 and US3 both edit `_hub_allocation`; run them sequentially in one branch of work even though their tests are independent.
- T029 is a STOP gate: no Phase 7 work if it fails.

## Parallel opportunities

- Phase 1: T002, T003, T004 (separate new files).
- Phase 3 tests: T012–T015 (same file, but independent test functions — write in one edit).
- Phase 7: T032 alongside T031.

## Implementation strategy

MVP = Phase 1 + Phase 2 + US1 (T001–T021): a validated hub plan for the quickstart brief, measured
against the frozen baseline. US2/US3 refine allocation inside the same functions; US4 is the
non-regression gate that must be green before anything is committed. Hub is a quality feature: if
US1 delivers hub plans that meet the §6 shape/door/exposure targets but rescues few refusals, that is
success, not a reason to widen eligibility.
