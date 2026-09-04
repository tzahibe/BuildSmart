---

description: "Task list template for feature implementation"
---

# Tasks: Project Creation (Basic Intake)

**Input**: Design documents from `/specs/001-project-creation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/projects-api.md, quickstart.md

**Tests**: Included — plan.md's Technical Context specifies pytest + FastAPI `TestClient`, so each user
story includes writing its tests before its endpoint implementation.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

## Path Conventions

All paths are under `backend/`, per plan.md's Project Structure (Web app: `backend/`, `frontend/`
untouched by this feature).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization for the new `projects` module

- [X] T001 Create `backend/app/projects/__init__.py` and `backend/tests/__init__.py` (new packages, per plan.md Project Structure)
- [X] T002 [P] Add `pytest` and `httpx` as dev dependencies in `backend/pyproject.toml`, then run `uv sync` in `backend/` (per research.md "pytest + TestClient" decision)
- [X] T003 [P] Add `backend/app/data/` to `.gitignore` — it will hold the runtime `projects.json` file, which must not be committed

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared entity, storage, and routing plumbing that every user story's endpoint depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Define `ProjectCreate`, `ProjectUpdate`, and `Project` Pydantic schemas in `backend/app/projects/models.py`, matching the fields and validation rules in data-model.md (`address`/`description` non-empty, `plot_area_m2 > 0`, server-generated `project_id`/`status`/`created_at`/`updated_at`)
- [X] T005 Define the `ProjectRepository` abstract interface (`get`, `create`, `update`) and a `JsonFileProjectRepository` implementation in `backend/app/projects/repository.py`, reading/writing `backend/app/data/projects.json` as a whole on each call, per research.md's "JSON-file storage behind a repository interface" decision — include a code comment noting this is temporary and will be replaced by a Postgres-backed implementation of the same interface once real persistence needs arrive
- [X] T006 Create `backend/app/projects/routes/base_routes.py` with an `APIRouter(prefix="/projects")` instance backed by a module-level `JsonFileProjectRepository`, and mount it in `backend/app/main.py` via `app.include_router(...)`

**Checkpoint**: Foundation ready — user story endpoints can now be added

---

## Phase 3: User Story 1 - Create a new project (Priority: P1) 🎯 MVP

**Goal**: A user can submit an address, plot area, and description and receive a project_id back; invalid submissions are rejected and create nothing.

**Independent Test**: `POST /projects` with valid data returns `201` with a generated `project_id` and the description stored verbatim; `POST /projects` with a missing address, empty description, or non-positive plot area returns `422` and creates no project (per contracts/projects-api.md and quickstart.md steps 1-2).

### Tests for User Story 1

- [X] T007 [US1] Write tests for `POST /projects` (valid creation returns 201 with generated fields and verbatim description; missing/empty/invalid fields return 422 and create nothing) in `backend/tests/test_projects.py`, using FastAPI `TestClient` against a temp-file-backed repository

### Implementation for User Story 1

- [X] T008 [US1] Implement the `POST /projects` endpoint in `backend/app/projects/routes/base_routes.py`: validate via `ProjectCreate`, create via the repository, return `201` with the full `Project`
- [X] T009 [US1] Run `backend/.venv/bin/pytest` and confirm the User Story 1 tests in T007 pass
- [X] T009a [US1] *(added after MVP validation — not in the original plan, which scoped this feature as backend-only)* Add a minimal "New Project" form to `frontend/src/App.tsx` (address, plot area, description) that calls `POST /projects` and displays the result or validation errors; add a dev-only proxy for `/projects` in `frontend/vite.config.ts` so the frontend can call the backend without CORS setup

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP, now reachable from both the API and a basic UI

---

## Phase 4: User Story 2 - Load an existing project (Priority: P2)

**Goal**: A user can retrieve a previously created project by its id and see everything they submitted; a nonexistent id returns a clear not-found error.

**Independent Test**: `GET /projects/{project_id}` for a project created in US1 returns `200` with all fields unchanged; `GET /projects/{random-uuid}` returns `404` (per contracts/projects-api.md and quickstart.md steps 3-4).

### Tests for User Story 2

- [X] T010 [US2] Write tests for `GET /projects/{project_id}` (existing id returns 200 with the exact stored fields; nonexistent id returns 404 with a clear error body) in `backend/tests/test_projects.py`

### Implementation for User Story 2

- [X] T011 [US2] Implement the `GET /projects/{project_id}` endpoint in `backend/app/projects/routes/base_routes.py`: return `200` with the `Project` on hit, raise `HTTPException(404, "Project not found")` on miss
- [X] T011a *(added on request — not in the original plan)* Split the single `router.py` into `backend/app/projects/routes/{__init__.py, base_routes.py, media_routes.py, analytics_routes.py}`: `base_routes.py` keeps the real CRUD endpoints, `media_routes.py`/`analytics_routes.py` are empty placeholders (no feature specifies that behavior yet), `__init__.py` aggregates all three into one `router` mounted in `main.py`
- [X] T011b [US1] *(added on request — not in the original plan)* Split `address` into `city` + `street` across `models.py`/`repository.py`/`base_routes.py`/tests; add `backend/app/localities/` (`data.py` with a sourced-not-invented list of Israeli local authorities, `router.py` exposing `GET /localities`) and wire it into `main.py`; update `frontend/src/App.tsx` to two fields with a `<datalist>` autocomplete fed by `GET /localities`, plus the matching `vite.config.ts` proxy entry
- [X] T011c [US1] *(added on request, same day, supersedes part of T011b — not in the original plan)* Restrict `city` to an exact match against `ISRAELI_LOCALITIES`: `field_validator` in `models.py` (`ProjectCreate`/`ProjectUpdate`) rejects any non-matching value with `422`; `App.tsx` mirrors the check client-side before submitting (falling back to server validation if the `/localities` fetch failed) — see research.md for the trade-off this accepts
- [X] T011d [US1] *(added on request, same day, supersedes T011b/T011c's data source — not in the original plan)* City-scoped street autocomplete: replace the Wikipedia-sourced `ISRAELI_LOCALITIES` with a snapshot of an official data.gov.il address registry (`backend/app/localities/streets_by_city.json`, fetched via paginated `datastore_search`, 1,314 cities/63,575 streets), loaded by a rewritten `data.py` (`CITIES`, `KNOWN_CITIES`, `CITY_STREETS`); add `GET /localities/{city}/streets` in `router.py` (404 for an unrecognized city); update `models.py`'s `city` validator to check `KNOWN_CITIES` from the new source; in `App.tsx`, gate the street `<input>` (`disabled` + a `streets-datalist`) on the selected city being recognized and its streets having loaded, resetting `street` whenever `city` changes — see research.md for why this is a static snapshot rather than a live call
- [X] T011e [US1] *(added on request, same day — not in the original plan)* Restrict `street` to an exact match within its city's `CITY_STREETS` entry: `model_validator(mode="after")` on `ProjectCreate` in `models.py` rejects any non-matching pair (including a real street from a *different* city) with `422`; `ProjectUpdate` gets the same check but only applied when both `city` and `street` are supplied together in one request (documented gap for `PATCH`/T013 — see research.md); `App.tsx` mirrors the check client-side before submitting, and cleans up the FastAPI cross-field error's generic `["body"]` location before displaying it

- [X] T011f [US1] *(added 2026-09-03 on request, well after this feature originally shipped — not in the original plan)* Add a required `built_area_m2` field (the desired built house size, distinct from the existing `plot_area_m2`): `Field(gt=0)` on `ProjectCreate`/`Project`, optional on `ProjectUpdate`, plus a `model_validator` requiring `built_area_m2 < plot_area_m2` (strict) — on `ProjectCreate` always, on `ProjectUpdate` only when both fields are supplied together (same "not-both-provided" gap as T011e, closed the same way: `base_routes.py`'s `PATCH` handler re-checks the merged final pair against whichever value the existing project already has). `App.tsx` gets a new "שטח הבנייה" input plus a matching client-side check before submitting. Motivated by realizing a project could be created with a real plot size but a meaningless/empty-of-content `description` — this guarantees every project has real, validated numeric planning data (size and footprint) regardless of description quality; see research.md for how this relates to Feature 02's own `target_built_area_m2`.

- [X] T011g [US1] *(added 2026-09-03, later the same day, per follow-up request — not in the original plan)* Absorb Feature 02's `StructuredRequirements` into `Project`: add `floors`/`bedrooms`/`safe_room`/`parking_spaces`/`pool`/`requirements_parsed_at` (all nullable, default `None`) to `Project` in `models.py` (and the shared `SourceTag`/`TaggedInt`/`TaggedFloat`/`TaggedBool`/`PoolField` types, moved here from `app/requirements/models.py`); add `ProjectRepository.set_parsed_requirements(...)` (`repository.py`) — merges those fields into an existing project without touching `updated_at`. Drop Feature 02's now-redundant `target_built_area_m2`. See research.md for the full decision and this task's counterpart in Feature 02's tasks.md.

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Update an existing project's requirements (Priority: P3)

**Goal**: A user can correct one or more fields of an existing project; unspecified fields are left unchanged, invalid updates are rejected in full, and updating a nonexistent project returns a clear not-found error.

**Independent Test**: `PATCH /projects/{project_id}` with one field (e.g. `plot_area_m2`) changes only that field and leaves the rest untouched on a subsequent `GET`; a `PATCH` with an invalid value (e.g. negative plot area) returns `422` and leaves the stored project unchanged; a `PATCH` on a nonexistent id returns `404` (per contracts/projects-api.md and quickstart.md step 5, and spec.md's edge cases).

### Tests for User Story 3

- [X] T012 [US3] Write tests for `PATCH /projects/{project_id}` (partial update changes only given fields and bumps `updated_at`; invalid field value returns 422 with no changes applied; nonexistent id returns 404) in `backend/tests/test_projects.py`

### Implementation for User Story 3

- [X] T013 [US3] Implement the `PATCH /projects/{project_id}` endpoint in `backend/app/projects/routes/base_routes.py`: validate via `ProjectUpdate`, merge only the provided fields through the repository's `update`, refresh `updated_at`, return `200` with the updated `Project`, or `404`/`422` as applicable. *(Extended beyond the original description, closing the gap noted in T011e/research.md: also re-checks the merged final `city`+`street` pair — existing values overlaid with whatever the update provides — against `CITY_STREETS` before saving, covering the case where only one of the two is updated.)*

**Checkpoint**: All three user stories are independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Wrap-up validation and documentation, no new behavior

- [X] T014 Run the manual `curl` walkthrough in `specs/001-project-creation/quickstart.md` against the running server and confirm every step's expected result
- [X] T015 [P] Add a short section to `backend/README.md` documenting the new `/projects` endpoints and noting that storage is a temporary JSON file, to be replaced by a database-backed repository later

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends only on Foundational — this is the MVP
- **User Story 2 (Phase 4)**: Depends only on Foundational (reuses the entity/repository from Phase 2, and can reuse a project created via US1 in tests, but does not require US1's endpoint code to exist)
- **User Story 3 (Phase 5)**: Depends only on Foundational (same note as US2)
- **Polish (Phase 6)**: Depends on whichever user stories were completed (ideally all three)

### Within Each User Story

- Tests (T007/T010/T012) are written before their story's implementation task, and should fail until that task is done
- Each story's implementation task edits `router.py` directly, so stories are implemented sequentially within that shared file even though they are logically independent

### Parallel Opportunities

- T002 and T003 (Setup) can run in parallel — different files
- T015 (Polish) can run in parallel with T014 — different files
- Because T006, T008, T011, and T013 all edit `backend/app/projects/routes/base_routes.py`, they are NOT marked `[P]` and should be done in sequence (T006 → T008 → T011 → T013) even though the user stories they belong to are independent in principle

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (T007-T009)
4. **STOP and VALIDATE**: run `pytest` and the relevant `quickstart.md` curl steps for US1 only
5. Confirm with the user before continuing to US2/US3

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. User Story 1 → validate → this is the MVP (project creation works end-to-end)
3. User Story 2 → validate → projects can now be retrieved
4. User Story 3 → validate → projects can now be corrected
5. Polish → full `quickstart.md` walkthrough + README note

## Notes

- All tests share `backend/tests/test_projects.py`; add new test functions rather than new files, keeping the file's existing tests intact.
- Verify each story's tests fail before writing its implementation task, per the "tests first" ordering above.
- Stop at each checkpoint to validate that story independently before moving on — this matches the "start basic, then stop" approach already agreed with the user.
