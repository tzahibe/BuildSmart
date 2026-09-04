---

description: "Task list template for feature implementation"
---

# Tasks: Parametric Design Model

**Input**: Design documents from `/specs/003-parametric-design-model/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/design-api.md, quickstart.md

**Tests**: Included — the generation algorithm is pure logic with many edge cases (research.md), so it
gets direct unit tests in addition to endpoint-level tests, matching Features 01/02's pattern.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

## Path Conventions

All paths are under `backend/`, per plan.md's Project Structure. This feature depends on Feature 01
(`backend/app/projects/`) for `Project` and its repository, and Feature 02 (`requirements_parsed_at`) as a
precondition — both read-only from here except the new repository method (below).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization for the new `design` module

- [ ] T001 Create `backend/app/design/__init__.py` (new package, per plan.md Project Structure)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared entity fields, storage, and the pure generation algorithm every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 [P] Add `Room` model (`type`, `floor`, `area_m2`, `x`, `y`, `width_m`, `depth_m`) and new nullable `Project` fields (`site_width_m`, `site_depth_m`, `rooms: list[Room] | None`, `design_notes: list[str] | None`, `design_generated_at: datetime | None`) to `backend/app/projects/models.py`, per data-model.md
- [ ] T003 [P] Add `ProjectRepository.set_design_model(project_id, *, site_width_m, site_depth_m, rooms, design_notes) -> Project | None` (abstract + `JsonFileProjectRepository` impl) to `backend/app/projects/repository.py` — merges the fields in, sets `design_generated_at` to now, leaves `updated_at`/`requirements_parsed_at` untouched (mirrors `set_parsed_requirements`)
- [ ] T004 Implement `generate_design(project: Project) -> GeneratedDesign` in `backend/app/design/generator.py` — pure function, no I/O, per data-model.md's algorithm: square site from `plot_area_m2` (FR-004); even floor-area split (FR-005); ground-floor fixed rooms (kitchen 12/bathroom 5/safe room 9 if known-requested) + footprint-too-small check raising a typed error (FR-012); living room + same-floor bedrooms split the remainder evenly (`floors == 1` case); bedroom distribution across upper floors, split evenly with remainder to lower-numbered floors first (`floors > 1` case); 1D row layout per floor (x accumulates, y=0, depth = floor's own footprint depth); `design_notes` entries when `bedrooms`/`safe_room` source is `unknown` (FR-007/FR-008) — bedrooms/safe_room excluded from the layout in that case, never a guessed count
- [ ] T005 Create `backend/app/design/router.py` with an `APIRouter(prefix="/projects", tags=["design"])`, and mount it in `backend/app/main.py` via `app.include_router(...)`

**Checkpoint**: Foundation ready — user story endpoint can now be added

---

## Phase 3: User Story 1 - Generate a design model for a project (Priority: P1) 🎯 MVP

**Goal**: A user can generate a deterministic room layout for a parsed project, merged into the project
itself, with unknown inputs excluded (never guessed) and explicitly recorded.

**Independent Test**: `POST /projects/{project_id}/design` on a fully-parsed single-floor project returns
the expected fixed rooms + bedrooms, all fitting the floor's footprint; a multi-floor project puts
bedrooms upstairs; an un-parsed or nonexistent project is rejected; a too-small footprint is rejected; a
project with unknown `bedrooms`/`safe_room` still generates, minus those rooms, with a note (per
contracts/design-api.md and quickstart.md steps 1-7).

### Tests for User Story 1

- [ ] T006 [P] [US1] Unit tests for `generate_design()` in `backend/tests/test_design.py`: single floor with known bedrooms/safe_room produces the right room set and every room's area/position is internally consistent (rooms on a floor don't overlap in `x`, widths sum to the floor's available area); floors=2 puts all bedrooms on floor 2 and none on floor 1; floors=3 with an odd bedroom count splits them across floors 2-3 with the remainder on floor 2; `bedrooms`/`safe_room` `unknown` → excluded with a matching `design_notes` entry; footprint too small → raises the typed error, no partial result
- [ ] T007 [US1] Endpoint tests for `POST /projects/{project_id}/design` in `backend/tests/test_design.py`: full flow (create → parse via Feature 02 → generate) returns `200` with the merged `Project`; un-parsed project → `422`; nonexistent project → `404`; footprint-too-small project → `422`

### Implementation for User Story 1

- [ ] T008 [US1] Implement `POST /projects/{project_id}/design` in `backend/app/design/router.py`: look up the project via Feature 01's repository, `404` if missing; `422` if `requirements_parsed_at is None` (FR-002); call `generate_design(project)`, catching its typed footprint-too-small error and returning `422` (FR-012); persist via `set_design_model(...)`; return the updated `Project` with `200`
- [ ] T009 [US1] Run `backend/.venv/bin/pytest` and confirm the User Story 1 tests in T006/T007 pass

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP

---

## Phase 4: User Story 2 - View a previously generated design model (Priority: P2)

**Goal**: A user can see an already-generated design model by loading the project, without regenerating.

**Independent Test**: `GET /projects/{project_id}` (Feature 01, unchanged) after a `POST .../design`
returns the same site/room data; before any generation, those fields are `null` (per quickstart.md step 2
vs. a fresh project).

### Tests for User Story 2

- [ ] T010 [US2] Tests in `backend/tests/test_design.py`: a freshly created (parsed) project has `site_width_m`/`rooms`/`design_notes`/`design_generated_at` all `null` via `GET /projects/{project_id}`; after `POST .../design`, `GET` returns the identical result (same `design_generated_at`, not regenerated)

### Implementation for User Story 2

- [ ] T011 [US2] No new implementation — Feature 01's existing `GET /projects/{project_id}` already returns every field on `Project`, including the ones T002 added; this story is validated by T010 alone

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Regenerate after requirements change (Priority: P3)

**Goal**: A user can update a project's built area (or re-parse a new description) and regenerate to get
an updated design model that replaces the old one.

**Independent Test**: Generate, change `built_area_m2` via `PATCH` (Feature 01), regenerate, and confirm
room areas reflect the new number and `design_generated_at` has advanced (quickstart.md step 8).

### Tests for User Story 3

- [ ] T012 [US3] Test in `backend/tests/test_design.py`: generate a design model, `PATCH` the project's `built_area_m2` to a different value, `POST .../design` again, and assert the new result's room areas differ from the first (reflecting the new built area) and `design_generated_at` has advanced

### Implementation for User Story 3

- [ ] T013 [US3] No new implementation — `POST /projects/{project_id}/design` (T008) already always regenerates from the project's *current* data and replaces the stored result (FR-010); this story is validated by T012 alone

**Checkpoint**: All three user stories are independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Wrap-up validation and documentation, no new behavior

- [ ] T014 Run the manual `curl` walkthrough in `specs/003-parametric-design-model/quickstart.md` (all 8 steps) against the running server, and confirm every step's expected result
- [ ] T015 [P] Add a section to `backend/README.md` documenting the new `POST /projects/{project_id}/design` endpoint and its preconditions/error cases

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. T002/T003 (models/repository) before T004 (generator, which constructs `Room`/reads `Project` fields) before T005 (router, which will call both)
- **User Story 1 (Phase 3)**: Depends only on Foundational — this is the MVP
- **User Story 2 (Phase 4)**: Depends only on Foundational (no new code — validated via existing `GET`)
- **User Story 3 (Phase 5)**: Depends on US1's `POST` implementation (T008) existing to regenerate against, and on Feature 01's existing `PATCH` — no new implementation of its own
- **Polish (Phase 6)**: Depends on whichever user stories were completed (ideally all three)

### Parallel Opportunities

- T002 and T003 (Foundational: `Project` fields vs. repository method) can be done in parallel — different
  files, though T003's type hints reference T002's new types, so land T002 first in practice even if not
  strictly blocking
- T006 (unit tests) can be written in parallel with T004 itself being finished, or right after — either
  way, land before T007 per the "tests before implementation" ordering
- T015 (Polish) can run in parallel with T014 — different files

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (T006-T009)
4. **STOP and VALIDATE**: run `pytest` and the relevant `quickstart.md` curl steps (1-4, 6-7) for US1 only
5. Confirm with the user before continuing to US2/US3

### Incremental Delivery

1. Setup + Foundational → foundation ready, generation algorithm unit-tested in isolation
2. User Story 1 → validate → this is the MVP (generation works end-to-end, all edge cases covered)
3. User Story 2 → validate → generated models retrievable without regenerating (already true, just confirm)
4. User Story 3 → validate → regeneration after a change reflects the new numbers
5. Polish → full `quickstart.md` walkthrough + README section

## Notes

- All tests share `backend/tests/test_design.py`; unit tests for `generate_design()` (T006) don't need
  `TestClient`/HTTP — they call the pure function directly with hand-built `Project` instances.
- No test calls the real OpenAI API — this feature makes no LLM calls at all, but T007's endpoint tests
  still need a parsed project, so they reuse Feature 02's `FakeRequirementParser` fixture pattern (or
  simpler: construct a `Project` directly via the repository fixture with `requirements_parsed_at`
  pre-set, bypassing the parse endpoint entirely, since this feature only cares that parsing *happened*,
  not what was parsed).
- Stop at each checkpoint to validate that story independently before moving on, matching Features 01/02.
