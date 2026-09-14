---

description: "Task list for feature 006 — Engine-Chosen Building Outline"
---

# Tasks: Engine-Chosen Building Outline

**Input**: Design documents from `/specs/006-engine-chosen-outline/` — [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/demo-plan-set.md](./contracts/demo-plan-set.md), [quickstart.md](./quickstart.md)

**Tests**: included, written first within each story (project convention since 004; the spec's acceptance is numeric and every data-model invariant is one test).

**Organization**: three parts, so the streaming work can be isolated or deferred without touching the core:

- **Part A — core outline selection semantics** (Phases 3–7, backend only; ships through the plain `POST /design/demo`)
- **Part B — frontend main flow** (Phase 8; no streaming changes)
- **Part C — SSE / preview UX** (Phase 9; isolatable — Parts A+B are complete and shippable without it)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 engine chooses · US2 distinct families shown · US3 advanced explicit outline · US4 honest refusal

## Hard constraints carried into every task (owner-approved 2026-09-13)

1. **R4** — outlines are planned **sequentially**; no threads, no process pool.
2. **R5** — the streamed provisional plan is a clearly labelled **preview**; `done` is the only authoritative result.
3. **R7** — the refusal sentence "מתאר של X×Y מ׳ … כן מתאפשר" is **removed**.
4. `family_signature` is **read-only metadata**: it is used **only** to de-duplicate which alternatives are *shown* (FR-004). It is **never** an input to the primary choice or to any ordering. The primary is chosen by `(|gross − requested|, outline.order, candidate index)` only.
5. The advanced explicit outline is **authoritative**: if it plans, its own primary is the first plan, byte-identical to today.
6. `run_general` and everything below it (`concept_generator`, `geometry_core`, `validation`, `doors`, `windows`, `furniture`, `safe_adapter`, `site`) are **unchanged**; the single addition in `general_pipeline.py` is a pure property that no code path below the service reads.
7. **No validator bypass**: every `DemoDesign` produced passes `validation.ok and safety.ok` — the same predicate `_alternative_plans` uses today. No new code path constructs a `DemoDesign` from an unvalidated plan.
8. **No brief loses an existing valid plan**: through the advanced path, 127/127 primary designs byte-identical to the frozen snapshot; through the main flow, every brief that plans today still plans (gate in T034).

---

## Phase 1: Setup — freeze the "before"

**Purpose**: the numbers every later gate compares against, taken on `main` at `5fd9474` before any change.

- [X] T001 Create branch `006-engine-chosen-outline` from `main` (`5fd9474`); confirm `.specify/feature.json` points at `specs/006-engine-chosen-outline`
- [X] T002 Run `backend/.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --save specs/006-engine-chosen-outline/before.json` from `backend/` — expected `saved 424 scenarios: planned 127`; commit the file (it is the SC-005 reference)
- [X] T003 [P] Run `backend/.venv/bin/python3 -m pytest -q --no-header -p no:warnings` — record the count in `specs/006-engine-chosen-outline/RESULTS.md` §0 (expected 773 passed, 6 skipped); run `npm test` in `frontend/` and record its count beside it
- [X] T004 [P] Add `with_footprint: bool = True` to `project_from_context` in `backend/spikes/failure_log_sweep/sweep.py`; when `False`, `selected_footprint=None`. Add `family_of(design)`-free helper `plans_shown(result)` returning `[result.design, *result.alternatives]`. No behaviour change for existing callers

**Checkpoint**: `before.json` and RESULTS §0 committed; baseline test counts recorded.

---

## Phase 2: Foundational — additive vocabulary (blocking)

**Purpose**: the read-only signature, the optional footprint in scope, and the additive contract fields. Nothing here changes any existing output.

### Tests (write first; must fail before T009–T012)

- [X] T005 [P] Add `tests/vertical_slice/test_family_signature.py` in `backend/`: for the four `PROGRAMS` × `GEOMETRIES` fixtures used by `test_demo_p0.py`, realize every candidate of `generate_concepts` that solves and assert (a) `family_signature` of a forced tree equals its unforced twin's; (b) two candidates whose `fixture.wings[0].tree` differ only in `fixed_at_u` share a signature; (c) a hand-built tree and its left/right mirror (swap `first`/`second` of every V `Split`) share a signature; (d) `SPINE_DOUBLE_LOADED` and `SPINE_SERVICE_CLUSTER` candidates with identical `leaves_of` order share a signature; (e) a `HUB_PRIVATE_WING` candidate's signature starts with `HUB:`; (f) the signature never contains a digit (dimension-free)
- [X] T006 [P] In `backend/tests/test_demo_p0.py` replace the assertion at line ≈1347 (`FOOTPRINT_REQUIRED` for a missing footprint) with: a project without `selected_footprint` but with plot dimensions passes `check_supported` (returns `None`); a project with `shape_type != "RECTANGLE"` still returns `FOOTPRINT_REQUIRED`; a project whose `built_area_m2` fits no outline inside the setbacks returns `FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` whose message names the *area*, not a rectangle
- [X] T007 [P] Add `tests/test_demo_contract_additive.py` in `backend/`: `DemoDesign(**existing_payload)` still validates with `outline=None, family=None`; `DemoPlanSet(plan=..., alternatives=[])` serialises with `search=None`; `OutlineOut.origin` accepts only `"ENGINE" | "PERSON"`; `SearchSummary.outlines[*]` carries `width_m, depth_m, origin, planned, plans_found, latency_ms`
- [X] T008 Run `pytest tests/vertical_slice/test_family_signature.py tests/test_demo_contract_additive.py -q` — must FAIL (nothing implemented yet); T006 must fail on the `check_supported` case

### Implementation

- [X] T009 Add `RealizedPlan.family_signature -> str` property in `backend/app/vertical_slice/general_pipeline.py` directly below `layout_signature`, implemented by a private module function `_family_signature(fixture, strategy)`: zone→letter map from `fixture.zones[*].primary_role` (H/P/F/M/B/S) and, for BATHROOM/TOILET/LAUNDRY, `W` if a `ConnectionKind.DOOR` edge in `fixture.access` joins it to `HALL` (or it has no door edge) else `E`; flatten nested same-direction `Split`s; mirror-normalise every V node by `min(kids, reversed(kids))` on rendered strings; ignore `fixed_at_u`; render `V[...]`/`H[...]`; prefix `HUB:` when `strategy is ConceptStrategy.HUB_PRIVATE_WING`. Docstring states: metadata only, never read by `run_general` or `_alternative_plans`
- [X] T010 In `backend/app/demo/scope.py`: remove the `selected_footprint is None` refusal; keep `FOOTPRINT_REQUIRED` for a non-RECTANGLE shape; when a footprint is given run `check_footprint_fits` exactly as today; when none is given, compute `site_geometry.feasible_options(site, project.built_area_m2)` and, if empty, return `NO_BUILDABLE_AREA` (via `no_buildable_area_message`) or `FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` with the text "בניין של {area:.0f} מ"ר אינו נכנס בשטח שנותר לבנייה בשום צורה …" carrying the same plot/setback numbers the existing message prints
- [X] T011 In `backend/app/demo/contract.py` add `class OutlineOut(BaseModel)` (`width_m, depth_m, area_m2, origin: Literal["ENGINE","PERSON"]`), `class OutlineTried(BaseModel)` (`width_m, depth_m, origin, planned: bool, plans_found: int, latency_ms: float`), `class SearchSummary(BaseModel)` (`outlines: list[OutlineTried]`, `total_latency_ms: float`); add `outline: OutlineOut | None = None` and `family: str | None = None` to `DemoDesign`; add `search: SearchSummary | None = None` to `DemoPlanSet`; extend `to_demo_design(..., outline: OutlineOut | None = None, family: str | None = None)` passing them through unchanged
- [X] T012 Mirror the additive fields in `frontend/src/design/demoDesign.ts` (`DemoOutline`, `OutlineTried`, `SearchSummary`, optional `outline`/`family` on `DemoDesign`, optional `search` on `DemoPlanSet`) — types only
- [X] T013 Run the full backend suite — expected 773 + new tests passed, 0 failed; run `snapshot.py --compare specs/006-engine-chosen-outline/before.json` — expected `127/127 identical, LOST 0` (Phase 2 must not move any plan)

**Checkpoint**: signature, optional footprint and contract fields exist; every existing output byte-identical.

---

# Part A — Core outline selection semantics (backend)

## Phase 3: User Story 1 — the engine chooses the outline (Priority: P1) 🎯 MVP

**Goal**: a project with no `selected_footprint` is planned at the de-duplicated `feasible_options` outlines, sequentially, each through the unchanged `run_general`; the primary is the validated plan nearest the requested area across outlines; every plan carries its outline and origin.

**Independent Test**: `outline_ab.py` (T021) mode B: planned ≥ 250 of 424, first-plan gross ÷ requested median ≥ 0.95, 0 shown plans failing validation.

### Tests (write first; must fail before T017–T020)

- [X] T014 [P] [US1] Add `tests/test_demo_outline_selection.py` in `backend/` with a fixture that builds `OutlineResult`s from stub `RealizedPlan`-like objects (`used_area_m2`, `family_signature`, `layout_signature`, `index`, `ok`) and tests for `_select_plans(outline_results, requested_m2)`: (a) primary is the entry minimising `(|gross − requested|, outline.order, index)`; (b) an entry with `ok=False` never appears in the selection (raise if one is passed — the pool must be built from validated plans only); (c) `len(shown) ≤ 3`; (d) the pool is empty → `None`
- [X] T015 [P] [US1] Add `test_outlines_for` in the same file: for a project with `selected_footprint=None`, `_outlines_for(project)` returns the `feasible_options` shapes in `PREFERRED_RATIOS` order with `origin=ENGINE`, de-duplicated on `(round(w,2), round(d,2))`, `order` 0..n-1; for a project with a footprint, entry 0 is that footprint with `origin=PERSON`, `order=0`, and an engine shape equal to it is dropped
- [X] T016 [P] [US1] Add `test_engine_outline_end_to_end` in `backend/tests/test_demo_p0.py`: the quickstart §5 brief (plot 15×15 N, 3 bd, 2 wet, safe, 176 m²) created **without** `selected_footprint` returns 200 from `POST /projects/{id}/design/demo`; `plan.outline.origin == "ENGINE"`; `plan.outline.area_m2` within 0.5 % of 176; `search.outlines` has ≥ 1 entry with `planned=True`; `plan.validation` reports every check passed; every alternative has `outline` and `family` set

### Implementation

- [X] T017 [US1] In `backend/app/demo/service.py` add `@dataclass(frozen=True) class Outline(width_m, depth_m, origin: Literal["ENGINE","PERSON"], order: int)` with `area_m2` property, and `_outlines_for(project) -> list[Outline]` per data-model.md (person's first if present; then `site_geometry.feasible_options(site, built_area_m2)` in order; de-dup; person wins ties)
- [X] T018 [US1] Add `@dataclass(frozen=True) class OutlineResult(outline, result: GeneralSliceResult, plans: tuple[RealizedPlan, ...], latency_ms: float)` and `_plan_outlines(spec, project, outlines, on_stage=None) -> list[OutlineResult]` in `backend/app/demo/service.py`: for each outline **in order, sequentially (R4)**, `project.model_copy(update={"selected_footprint": …})` exactly as `_outline_that_plans` does today, call the existing `_plan(spec, candidate_project, on_stage)` (which calls `run_general(..., max_alternatives=ALTERNATIVE_PLAN_LIMIT)` unchanged), time it, and set `plans = (RealizedPlan-of-chosen, *result.alternatives)` **only if** `result.ok` (i.e. `outcome is SOLVED and validation.ok and safety.ok`), else `()`. The chosen plan must be wrapped from `result.design/validation/safety/concept` into the same `RealizedPlan` shape as alternatives so the pool is homogeneous — add a small `_chosen_as_realized(result)` helper; do not modify `run_general`
- [X] T019 [US1] Add `_select_plans(outline_results, requested_m2) -> PlanSelection | None` in `backend/app/demo/service.py`: pool = `[(orr, plan) for orr in outline_results for plan in orr.plans]` sorted by `(round(abs(plan.concept.used_area_m2 − requested_m2), 4), orr.outline.order, plan.index)`; primary = the person's outline's `plans[0]` if such an `OutlineResult` has plans, else `pool[0]`; alternatives left **empty in this phase** (US2 fills them); return `PlanSelection(primary, alternatives=(), pool)`. Assert every pool member's `plan.ok` (defensive — constraint 7)
- [X] T020 [US1] Rewire `generate_demo_design` in `backend/app/demo/service.py`: after `check_supported` and `spec_for`, `outlines = _outlines_for(project)`; `results = _plan_outlines(spec, project, outlines, on_stage)`; keep the existing corridor-preference retry by re-running `_plan_outlines` once with `corridor=None` when no outline planned and the corridor is non-binding; `selection = _select_plans(results, spec.program.target_built_area_m2)`; when `selection` is not None, build `DemoResult` through the **existing** `_finish` checks applied to the primary's `GeneralSliceResult` (so C14/C15/safety/unsupported logic stays in one place — refactor `_finish` into `_refuse_if_not_ok(project, spec, result)` + `_result_from(selection, spec, unsupported)`), passing `outline=OutlineOut(...)` and `family=plan.family_signature` into `to_demo_design` for the primary and each alternative, and `search=SearchSummary(...)` from `results`. When `selection` is None, fall through to the refusal path (US4 rewrites it; for now keep today's messages minus nothing)
- [X] T021 [US1] Create `backend/spikes/failure_log_sweep/outline_ab.py`: runs all `distinct_contexts()` twice through `svc.generate_demo_design` — A: `project_from_context(ctx)` (advanced), B: `project_from_context(ctx, with_footprint=False)` (main flow); per run records status, code, `plans_shown` signatures, `plan.outline`, `plan.family`, `search`, seconds. Prints: planned A/B; A primaries identical to `--before before.json` (count, LOST list); B first-plan gross÷requested median and ≥ 0.95 count; B briefs (among A-planned) with ≥ 2 distinct `family` among shown; same-family+same-outline pairs shown; refusal texts containing "מתאר של"; over-capacity refusals carrying `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`; every shown plan's `validation` all-passed count; latency medians A/B and vs `before.json` if it carries seconds; writes `outline_ab.json`
- [X] T022 [US1] Run `pytest -q` — T014–T016 green, full suite green; run `outline_ab.py --before specs/006-engine-chosen-outline/before.json`; record in RESULTS.md §1: A identical (must be 127/127), B planned (target ≥ 250), B area median (target ≥ 0.95), validation failures shown (must be 0)

**Checkpoint**: main flow works through the plain endpoint with one plan per request; advanced path byte-identical.

---

## Phase 4: User Story 2 — plans shown are different houses (Priority: P1)

**Goal**: fill the two alternative slots across outlines so distinct families are exhausted before any family repeats, and a repeat comes only from a different outline. `family_signature` is used here **and only here**.

**Independent Test**: `outline_ab.py` mode B: briefs (among today's 127) with ≥ 2 distinct families shown ≥ 60; same-family+same-outline pairs = 0.

### Tests (write first)

- [X] T023 [P] [US2] Extend `backend/tests/test_demo_outline_selection.py`: (a) pool with 3 families → 3 distinct families shown; (b) exactly 2 families → both shown, third slot filled only by an entry from an outline not yet shown, else left empty; (c) 1 family, 1 outline → exactly 1 plan shown; (d) never two entries with the same `(outline, layout_signature)`; (e) family never changes the primary — construct a pool where a rarer family is nearer the requested area than the primary's family and assert the primary is still the area-nearest entry; (f) with a `PERSON` outline that planned, `shown[0]` is its `plans[0]` even when an `ENGINE` entry is nearer the requested area

### Implementation

- [X] T023a [US2] Latency fast-path (owner instruction 2026-09-14): in `backend/app/demo/service.py`, `_plan` gains `max_alternatives` (passed straight to `run_general`, unchanged); `_plan_outlines_until_one_plans` surveys the engine outlines with `max_alternatives=0`, picks the primary outline with `_nearest_primary` (area-only, primaries only, ties → earlier outline), and re-runs ONLY that outline with alternatives, asserting the re-run's primary equals the surveyed one; the advanced path is untouched
- [X] T024 [US2] Complete `_select_plans` in `backend/app/demo/service.py`: after the primary, walk the pool in its existing order; first pass takes entries whose `family_signature` is not in `shown_families`; second pass (if slots remain) takes entries whose `outline` is not in `shown_outlines`; skip any `(outline, layout_signature)` already shown; stop at 3. Comment: "family is a display de-duplication key only (owner constraint 2026-09-13); it does not reorder the pool"
- [X] T025 [US2] Run T023 and the full suite — green; re-run `outline_ab.py`; record in RESULTS.md §2: B briefs with ≥ 2 families shown (target ≥ 60), same-family-same-outline pairs (must be 0), A identical (must still be 127/127 — alternatives may legitimately differ; the gate is the primary)

**Checkpoint**: up to three plans, different families first, no re-proportioned duplicates.

---

## Phase 5: User Story 3 — advanced explicit outline is authoritative (Priority: P2, backend part)

**Goal**: a request carrying `selected_footprint` plans that outline first; if it plans, it is the first plan, byte-identical to today; if not, the engine outlines are still shown and the response says the entered outline could not be planned.

**Independent Test**: `snapshot.py --compare before.json` → 127/127; a brief whose explicit outline fails but an engine outline plans returns 200 with `plan.outline.origin == "ENGINE"` and `search.outlines[0].planned == False`.

### Tests (write first)

- [ ] T026 [P] [US3] Add `test_explicit_outline_is_first_and_identical` in `backend/tests/test_demo_p0.py`: the same brief created with and without `selected_footprint` = the option the engine would rank first; with it, `plan.outline.origin == "PERSON"` and the room signature equals the response at `5fd9474` (use the frozen fixture the test already keeps for this brief, or `before.json`)
- [ ] T027 [P] [US3] Add `test_explicit_outline_that_fails_still_returns_engine_plan`: `selected_footprint` = 10.00 × 17.60 for the 176 m² quickstart brief (known non-planning shape); expect 200, `plan.outline.origin == "ENGINE"`, `search.outlines[0] == {origin: "PERSON", planned: False}`, and `plan.unsupported`/notes contain the sentence "המתאר שהזנת ({w}×{d} מ׳) לא אפשר לסדר את החדרים; מוצג מתאר אחר באותו שטח"

### Implementation

- [ ] T028 [US3] In `backend/app/demo/service.py` `_result_from`, when `outlines[0].origin == "PERSON"` and its `OutlineResult.plans` is empty while the selection is non-empty, add the sentence from T027 to the `unsupported` notes passed to `to_demo_design` for every shown plan (it describes the request, like the existing preference notes — see `_set_aside`)
- [ ] T029 [US3] Run T026–T027, full suite, `snapshot.py --compare` (127/127) — record in RESULTS.md §3

**Checkpoint**: advanced path reproduces today exactly and degrades gracefully.

---

## Phase 6: User Story 4 — a refusal is final and honest (Priority: P2)

**Goal**: when no outline yields a validated plan, one refusal with the applicable diagnosis, no outline suggestion (R7); diagnostics carry every outline's metrics.

**Independent Test**: `outline_ab.py` mode B: 0 refusal messages containing "מתאר של"; 67/67 over-capacity briefs carry `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`.

### Tests (write first)

- [ ] T030 [P] [US4] Add `test_refusal_names_no_outline` in `backend/tests/test_demo_p0.py`: a brief that plans at no outline (1 bd, 1 wet, 440 m² on 22 × 22) returns `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` and the message does not contain "מתאר של"; a non-over-capacity brief that plans nowhere (pick one from `before.json` with code `PLAN_NOT_REALIZABLE` and no `+outline`) returns `PLAN_NOT_REALIZABLE` with the generic text and `diagnostics["outlines"]` listing every outline tried with its `engine` block
- [ ] T031 [P] [US4] Add `test_failure_context_records_outlines` in `backend/tests/test_demo_p0.py` (or the router test file that exercises `_failure_context`): on a refusal, the logged context has `outlines_tried: [{width_m, depth_m, origin, planned}]` and `footprint_width_m is None` in the main flow

### Implementation

- [ ] T032 [US4] In `backend/app/demo/service.py`: delete `_outline_that_plans` and `_MAX_ALTERNATIVE_OUTLINES` (move their measured notes into research.md R1 if not already there); rewrite the no-plan branch of `_refuse_if_not_ok` to evaluate on `results[0].result` (the person's outline if given, else the first engine outline) with precedence: capacity (numbers-based, as today) → `ROOM_RELATIONSHIP_NOT_FEASIBLE` if any outline's notes/validation show a broken hard relationship → `CORRIDOR_WIDTH_NOT_FEASIBLE` when the corridor is binding and every outline's only failure is C14 → generic `PLAN_NOT_REALIZABLE`. Remove the "מתאר של … כן מתאפשר" `raise`. Extend `_diagnostics(result, spec, outlines=results)` to add `"outlines": [{"width_m","depth_m","origin","planned","latency_ms","engine": {...as today...}}]`
- [ ] T033 [US4] In `backend/app/demo/router.py` `_failure_context`, add `outlines_tried` from `error.diagnostics.get("outlines", [])`; keep the existing `footprint_*` keys
- [ ] T034 [US4] Run T030–T031 and the full suite; run `outline_ab.py`; record in RESULTS.md §4: refusals mentioning an outline (must be 0), over-capacity diagnosis coverage (must be 67/67), and the **main-flow non-regression**: every brief `PLANNED` in `before.json` must be `PLANNED` in mode B (the 2 person-only briefs are expected exceptions — list them by context; any other loss STOPS the feature until diagnosed)

**Checkpoint**: Part A complete. `POST /design/demo` delivers the full feature to any client; the frontend still works unchanged (it sends a footprint → advanced path).

---

## Phase 7: Gate A — measurements and results

- [ ] T035 Run `outline_ab.py --before specs/006-engine-chosen-outline/before.json` on the final Part A code and write `specs/006-engine-chosen-outline/RESULTS.md` §1–§4 with the SC table: SC-001 (≥ 250), SC-002 (≥ 0.95), SC-003 (≥ 60), SC-004 (0), SC-005 (127/127), SC-006 (0), SC-007 (0 · 67/67), SC-008 (median A, median B, before; B ≤ 4× before; worst case listed). If any gate fails: STOP, diagnose the exact briefs, record, do not add a heuristic
- [ ] T036 [P] Update `backend/spikes/failure_log_sweep/README.md` with `outline_ab.py` (modes, flags, what each printed line is the gate for)

---

# Part B — Frontend main flow (no streaming changes)

## Phase 8: User Story 1 + 3 — the screen (Priority: P1 / P2)

**Goal**: the footprint screen leaves the main sequence; an "advanced" disclosure on the form hosts the existing `FootprintSelection`; plan cards show their outline and origin; the review page states the outline is automatic when none was entered.

**Independent Test**: `npm test` — form submit goes straight to loading; advanced disclosure sends `selected_footprint`; cards show outline labels.

### Tests (write first)

- [X] T037 [P] [US1] Update `frontend/src/App.test.tsx`: submitting the form with valid plot/programme/area calls `createProject` **without** `selected_footprint` and moves to the loading view — the `'footprint'` view is never rendered in that path; `fetchFootprintOptions` is not called until the advanced disclosure is opened
- [X] T038 [P] [US3] Add to `frontend/src/App.test.tsx`: opening "מתקדם — קביעת מתאר ידנית" calls `fetchFootprintOptions`, renders the four cards + custom inputs; confirming a card then submitting sends `selected_footprint` via `toSelectedFootprintPayload`; closing the disclosure clears it
- [X] T039 [P] [US1] Update `frontend/src/design/DemoPlan.test.tsx`: a plan with `outline: {width_m: 12.35, depth_m: 14.25, area_m2: 175.99, origin: "ENGINE"}` renders "12.35 × 14.25 מ׳ · 176 מ"ר · מתאר אוטומטי"; `origin: "PERSON"` renders "המתאר שהזנת"; `outline: null` renders nothing extra
- [X] T040 [P] [US3] Update `frontend/src/design/FootprintSelection.test.tsx` for the inline mode: no "continue" button when `inline` is set; selection reports upward immediately; the explanatory paragraph is shortened to the advanced context

### Implementation

- [X] T041 [US1] In `frontend/src/App.tsx`: rename `handleContinueToFootprint` → `handleSubmitBrief`; it validates as today, then calls `createProject` directly with `selected_footprint: footprint ? toSelectedFootprintPayload(footprint) : undefined` and proceeds to `'loading'`; remove `'footprint'` from the main `View` sequence (keep the type member only if the disclosure reuses the component inline; otherwise delete it and its render branch)
- [X] T042 [US3] In `frontend/src/App.tsx` add a collapsed `<details>`-style disclosure at the bottom of the form, "מתקדם — קביעת מתאר ידנית", with a one-line note "כברירת מחדל המערכת בוחרת את צורת הבניין בעצמה ומציגה כמה אפשרויות"; on open, call `fetchFootprintOptions` (existing) and render `<FootprintSelection inline …/>`; on close, `setFootprint(null)`
- [X] T043 [US3] In `frontend/src/design/FootprintSelection.tsx` add an `inline?: boolean` prop: hides the page title and the confirm button, keeps the cards + custom card + site facts block, reports selection through `onChange` only
- [X] T044 [US1] In `frontend/src/design/DemoPlan.tsx` render the outline label under each plan title from `design.outline` (format per T039); origin `PERSON` → "המתאר שהזנת", `ENGINE` → "מתאר אוטומטי"; when the plan set's `search.outlines[0]` is `PERSON` with `planned=false`, render the note from T027 once above the cards
- [X] T045 [P] [US1] In `frontend/src/design/ReviewPage.tsx`, where `site.footprint_width_m` is null, render "מתאר הבניין: ייקבע אוטומטית לפי השטח המבוקש" instead of nothing
- [X] T046 Run `npm test` and `npm run build` in `frontend/` — green; manual walk-through quickstart §5 steps 1, 2, 4 (step 3 needs Part A's T028, already in) — record observations in RESULTS.md §5

**Checkpoint**: Parts A+B ship the feature end to end over the plain endpoint with today's loading screen (percent per outline is coarse until Part C).

---

# Part C — SSE / preview UX (isolatable)

## Phase 9: streaming progress and the labelled preview (Priority: P1 UX, technically optional)

**Goal**: outline-major progress and one provisional `plan` event so the person sees a first plan while the remaining outlines run. `done` remains the only authoritative result (R5).

**Independent Test**: router test — the event sequence is `progress*`, at most one `plan`, exactly one `done|error`; the `plan` payload's design equals one of `done`'s shown plans or is superseded; `LoadingScreen` renders the preview with the label "תצוגה מקדימה — עוד N מתארים בבדיקה".

### Tests (write first)

- [ ] T047 [P] Add `test_stream_emits_outline_major_progress_and_one_preview` in `backend/tests/test_demo_p0.py` (beside the existing stream test): for the quickstart brief without footprint, collect SSE events; assert every `progress` has `outline ≤ outlines` and `percent` monotonic non-decreasing; at most one `plan` event, with `provisional: true` and a `design.outline`; exactly one `done`; `done.plan` passes validation; if a `plan` event was emitted, its `design.family`/`outline` appears in `done` or `done.plan` is nearer the requested area than it
- [ ] T048 [P] Update `frontend/src/design/LoadingScreen.test.tsx`: given `preview={design, remainingOutlines: 2}`, renders the plan drawing with the label "תצוגה מקדימה — עוד 2 מתארים בבדיקה" and the progress bar; `done` (parent swaps view) is not this component's concern

### Implementation

- [ ] T049 In `backend/app/demo/service.py` extend `_plan_outlines(..., on_stage=None, on_plan=None)`: call `on_plan(outline, chosen_realized_plan)` the **first** time an outline's `plans` is non-empty; `generate_demo_design` gains the same optional `on_plan` and passes it through. `on_stage` calls are wrapped so each carries `(outline_index, outline_count, stage_name)` — implement by passing a closure `lambda name: on_stage((k, n, name))` when `on_stage` is given; the non-streaming path passes `None` and is unaffected
- [ ] T050 In `backend/app/demo/router.py` `generate_demo_plan_streaming`: the queue now carries either a `("stage", k, n, name)` or a `("plan", DemoDesign)` item; emit `progress` with `outline=k, outlines=n, step, total, label, percent=round(((k-1)*total+step)*100/(n*total))`; emit `plan` with `{"provisional": true, "design": <DemoDesign incl. outline/family>}` — built through `to_demo_design` from a plan that already passed `validation.ok and safety.ok` (constraint 7); `done` unchanged. Keep `PIPELINE_STAGES` untouched
- [ ] T051 In `frontend/src/api.ts` `generateDemoDesignStreaming`: accept `onPreview?: (design: DemoDesign, remainingOutlines: number) => void`; handle `event === 'plan'`; `DemoProgress` gains optional `outline`/`outlines`; `done` still resolves the promise with the authoritative `DemoPlanSet`
- [ ] T052 In `frontend/src/design/LoadingScreen.tsx` add an optional `preview?: { design: DemoDesign; remainingOutlines: number }` prop: renders the existing plan SVG (reuse `ArchitecturalFloorPlan`/`SketchSvg` read-only) under the progress bar with the label "תצוגה מקדימה — עוד {N} מתארים בבדיקה · התוצאה הסופית עשויה להשתנות"; in `App.tsx` wire `onPreview` to state and pass it; on `done` the view switches to `'plan'` exactly as today
- [ ] T053 Run backend + frontend suites; run `outline_ab.py` once more (Part C must not change any A/B number — assert equality with §1–§4 and record in RESULTS.md §6 together with the time-to-first-preview median measured from the stream test harness)

**Checkpoint**: full feature with progressive delivery; Part C can be reverted independently (T049–T052) without touching Parts A/B.

---

## Phase 10: Polish & cross-cutting

- [ ] T054 [P] Finalise `specs/006-engine-chosen-outline/RESULTS.md`: SC table with measured values, the 2 person-only briefs named, latency A/B/before, decision (accept / what failed), and the memory note update (`repetition-root-and-outline-sweep`)
- [ ] T055 [P] Update `backend/app/demo/service.py` module docstring (the flow now lists "outlines → run_general per outline → cross-outline selection") and `backend/spikes/failure_log_sweep/README.md`; remove the now-stale sentence in `frontend/src/design/FootprintSelection.tsx`'s header comment describing it as a mandatory step
- [ ] T056 Run quickstart.md §1–§5 end to end on the final code; commit `before.json`, `outline_ab.json`, RESULTS.md; open the PR with the SC table in its body

---

## Dependencies & execution order

- **Phase 1 → Phase 2 → Part A (3 → 4 → 5 → 6 → 7)** strictly in order: US2 fills the slots US1 leaves empty; US3 and US4 edit the same `service.py` functions US1 creates.
- **Part B (Phase 8)** depends on Phase 2 (types) and Phase 3 (`outline` field populated); it does **not** depend on Phases 4–7 to be testable, but ship it after Gate A.
- **Part C (Phase 9)** depends on Phase 3 (`_plan_outlines`) and Phase 8 (`LoadingScreen` wiring); it is the only part that touches the stream and can be deferred or reverted alone.
- **Phase 10** after everything.

### Parallel opportunities

- Phase 1: T003 ∥ T004. Phase 2: T005 ∥ T006 ∥ T007; T011 ∥ T012.
- Within each story the test tasks are [P] with each other; implementation tasks in `service.py` are sequential.
- Phase 8 tests T037–T040 ∥; T045 ∥ T041–T044.
- Phase 9 tests T047 ∥ T048.

### Parallel example — Phase 2

```
T005 tests/vertical_slice/test_family_signature.py
T006 tests/test_demo_p0.py (scope cases)
T007 tests/test_demo_contract_additive.py
→ then T009 (general_pipeline.py) ∥ T010 (scope.py) ∥ T011 (contract.py) ∥ T012 (demoDesign.ts)
```

## Implementation strategy

1. **MVP = Phase 1 + 2 + 3** (US1 over the plain endpoint): one plan per request, engine-chosen outline, advanced path byte-identical. Measurable with `outline_ab.py` immediately.
2. Add US2 (families), US3 (explicit-outline note), US4 (refusal) — each one small and gated by the same script.
3. Gate A (T035) decides whether the backend is accepted before any UI changes.
4. Part B changes the screens; Part C adds the preview last and can be dropped without loss of function.
