---

description: "Task list template for feature implementation"
---

# Tasks: Natural Language Requirement Parser

**Input**: Design documents from `/specs/002-requirement-parser/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/requirements-api.md, quickstart.md

**Tests**: Included — plan.md's Technical Context specifies pytest + FastAPI `TestClient`, matching
Feature 01's pattern; a `FakeRequirementParser` stands in for the real OpenAI call in tests (research.md).

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

## Path Conventions

All paths are under `backend/`, per plan.md's Project Structure. This feature depends on Feature 01
(`backend/app/projects/`) for the `Project` entity and its repository — read-only from here.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization for the new `requirements` module and its OpenAI dependency

- [X] T001 Create `backend/app/requirements/__init__.py` (new package, per plan.md Project Structure)
- [X] T002 [P] Add `openai` and `python-dotenv` as dependencies in `backend/pyproject.toml`, then `uv sync --group dev` in `backend/` (per research.md's model-choice decision) — *(already done during planning, while verifying `gpt-5-nano` access)*
- [X] T003 [P] Create `backend/.env` (gitignored — confirmed via `git check-ignore`) with `OPENAI_API_KEY`, and `backend/.env.example` as a committed template with no real value — *(already done during planning)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared entity, parser, storage, and routing plumbing that every user story's endpoint depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Load `OPENAI_API_KEY` from `backend/.env` via `python-dotenv`'s `load_dotenv()` at the very top of `backend/app/main.py`, before any router that needs it is imported (per research.md — must run before `OpenAIRequirementParser` is constructed at router import time)
- [X] T005 [P] Define `SourceTag` enum (`requested`/`inferred`/`unknown`) and tagged-field models (`TaggedInt`, `TaggedFloat`, `TaggedBool` — each `{value, source}`), `PoolField`, and `StructuredRequirements` (per data-model.md: `project_id`, the 6 tagged fields, `source_description`, `parsed_at`, `missing_essential_fields`, `message`) in `backend/app/requirements/models.py`
- [X] T006 [P] Define a `RequirementExtraction` Pydantic model (the LLM-facing subset of `StructuredRequirements`: the 6 tagged fields only, no `project_id`/timestamps/message) and the `RequirementParser` abstract interface (`parse(description: str) -> RequirementExtraction`) in `backend/app/requirements/parser.py`
- [X] T007 [US1] Implement `OpenAIRequirementParser(RequirementParser)` in `backend/app/requirements/parser.py`: constructs `openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` lazily (no eager validation at `__init__`, per research.md's test-hermeticity decision), calls `client.chat.completions.parse(model="gpt-5-nano", response_format=RequirementExtraction, messages=[...])` with a system prompt that: (a) defines the `requested`/`inferred`/`unknown` semantics per spec.md FR-003, explicitly forbidding fabricated values (FR-004); (b) states the FR-011 floors rule verbatim — default to `{value: 1, source: "inferred"}` when floor count is unstated, but `{value: null, source: "unknown"}` when the text states conflicting floor counts; (c) covers the pool sub-object rule (dimensions stay `unknown` unless the pool itself is requested)
- [X] T008 [P] Define `RequirementsRepository` interface (`get`, `save`) and `JsonFileRequirementsRepository` implementation in `backend/app/requirements/repository.py`, reading/writing `backend/app/data/requirements.json` keyed by `project_id` — structurally identical to `backend/app/projects/repository.py`'s `JsonFileProjectRepository` (per research.md)
- [X] T009 Create `backend/app/requirements/router.py` with an `APIRouter(prefix="/projects", tags=["requirements"])`, a module-level `parser: RequirementParser = OpenAIRequirementParser()` and `repository: RequirementsRepository = JsonFileRequirementsRepository(...)` (mirroring `base_routes.py`'s module-level `repository` pattern so tests can monkeypatch both), and mount it in `backend/app/main.py` via `app.include_router(...)` (after T004's `load_dotenv()`)
- [X] T010 Add a `_compute_missing_essential(extraction: RequirementExtraction) -> tuple[list[str], str | None]` helper in `backend/app/requirements/router.py` (or `models.py`) implementing FR-010 deterministically: checks `target_built_area_m2.source` and `floors.source` for `"unknown"`, returns the missing field names and, if any, the Hebrew message from contracts/requirements-api.md's exact wording — computed in code, never asked of the LLM (per research.md)

**Checkpoint**: Foundation ready — user story endpoints can now be added

---

## Phase 3: User Story 1 - Parse a project's description into structured requirements (Priority: P1) 🎯 MVP

**Goal**: A user can trigger parsing of an existing project's description and get back structured,
source-tagged requirements, with no fabricated values and a clear message when essentials are missing.

**Independent Test**: `POST /projects/{project_id}/requirements` on a fully-specified description returns
all 6 fields correctly tagged `requested`; on an under-specified one, unmentioned fields come back
`unknown` (except `floors`, which defaults per FR-011) and `message` names only `target_built_area_m2`
when it's missing; a nonexistent `project_id` returns `404` (per contracts/requirements-api.md and
quickstart.md steps 1-4, 8).

### Tests for User Story 1

- [X] T011 [US1] Add a `FakeRequirementParser(RequirementParser)` test double to `backend/tests/test_requirements.py` — a small dict-driven fake returning canned `RequirementExtraction` values for a handful of fixed input strings (per research.md's hermeticity decision; no real OpenAI calls in tests)
- [X] T012 [US1] Write tests for `POST /projects/{project_id}/requirements` in `backend/tests/test_requirements.py`: (a) fully-specified description → `200`, all 6 fields `requested` with the exact stated values, `missing_essential_fields == []`, `message is None`; (b) description omitting `parking_spaces` → that field `unknown`, not guessed; (c) description mentioning a pool with no dimensions → `pool.requested` `requested`/`true`, `length_m`/`width_m` `unknown`; (d) nonexistent `project_id` → `404`, `{"detail": "Project not found"}`

### Implementation for User Story 1

- [X] T013 [US1] Implement `POST /projects/{project_id}/requirements` in `backend/app/requirements/router.py`: look up the project via the Feature 01 project repository (`from app.projects.routes.base_routes import repository as project_repository`), `404` if missing; call `parser.parse(project.description)`; build a `StructuredRequirements` with `project_id`, the extraction's 6 fields, `source_description=project.description`, `parsed_at=now`, and T010's `missing_essential_fields`/`message`; save via `repository.save(...)`; return it with `200`
- [X] T014 [US1] Write tests for the FR-010/FR-011 behavior specifically in `backend/tests/test_requirements.py`: (a) description stating no essential fields → `floors.value == 1`, `floors.source == "inferred"`, `target_built_area_m2.source == "unknown"`, `missing_essential_fields == ["target_built_area_m2"]`, `message` names only that field; (b) description with a conflicting floor count (via the fake parser) → `floors.source == "unknown"`, `"floors"` present in `missing_essential_fields`
- [X] T015 [US1] Run `backend/.venv/bin/pytest` and confirm the User Story 1 tests in T012/T014 pass

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP

---

## Phase 4: User Story 2 - View previously parsed requirements (Priority: P2)

**Goal**: A user can retrieve a project's already-parsed structured requirements without re-parsing, and
gets a clear signal if nothing has been parsed yet.

**Independent Test**: `GET /projects/{project_id}/requirements` after a `POST` returns the identical
stored result (same `parsed_at`); for a project that exists but was never parsed, returns `404` with a
message distinguishable from "project not found"; for a nonexistent project, `404` "Project not found"
(per contracts/requirements-api.md and quickstart.md steps 5-6).

### Tests for User Story 2

- [X] T016 [US2] Write tests for `GET /projects/{project_id}/requirements` in `backend/tests/test_requirements.py`: (a) after a `POST`, `GET` returns the same stored result (identical `parsed_at`, not a fresh parse); (b) a project that exists but was never parsed → `404`, `{"detail": "Requirements not yet parsed for this project"}`; (c) a nonexistent `project_id` → `404`, `{"detail": "Project not found"}`

### Implementation for User Story 2

- [X] T017 [US2] Implement `GET /projects/{project_id}/requirements` in `backend/app/requirements/router.py`: `404` "Project not found" if the project itself doesn't exist (via `project_repository`); else look up via `repository.get(project_id)`, `404` "Requirements not yet parsed for this project" if `None`; else return it with `200`

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Re-parse after updating the description (Priority: P3)

**Goal**: A user who updates a project's description (Feature 01's `PATCH /projects/{project_id}`) can
re-parse and see the structured result reflect the new text, replacing the old one.

**Independent Test**: Parse a project, `PATCH` its `description` to something different, `POST`
`.../requirements` again, and confirm the new result reflects the new text — not the original — with a
later `parsed_at` (per quickstart.md step 7).

### Tests for User Story 3

- [X] T018 [US3] Write a test in `backend/tests/test_requirements.py`: parse a project (via `POST`), `PATCH` its `description` (Feature 01's existing endpoint) to different content, `POST` `.../requirements` again, and assert the new result's fields reflect the new description (differ from the first parse) and `parsed_at` has advanced

### Implementation for User Story 3

- [X] T019 [US3] No new implementation — `POST /projects/{project_id}/requirements` (T013) already always re-parses from the project's *current* description and replaces the stored result (FR-006/FR-007); this story is validated by T018 alone

**Checkpoint**: All three user stories are independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Wrap-up validation and documentation, no new behavior

- [X] T020 Run the manual `curl` walkthrough in `specs/002-requirement-parser/quickstart.md` (all 8 steps, including the FR-011 default/conflict cases) against the running server with a real `OPENAI_API_KEY`, and confirm every step's expected result
- [X] T021 [P] Add a section to `backend/README.md` documenting the new `/projects/{project_id}/requirements` endpoints, the `OPENAI_API_KEY` requirement (pointing to `.env.example`), and the FR-010/FR-011 behavior (essential-fields message, floors default)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T002/T003 already done during planning; T001 trivial
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. T004 (dotenv) must land before T009 (router, which instantiates `OpenAIRequirementParser` at import time)
- **User Story 1 (Phase 3)**: Depends only on Foundational — this is the MVP
- **User Story 2 (Phase 4)**: Depends only on Foundational (reuses the entity/repository from Phase 2; can reuse a project parsed via US1 in tests, but does not require US1's endpoint code to exist)
- **User Story 3 (Phase 5)**: Depends on US1's `POST` implementation (T013) existing to re-parse against, and on Feature 01's existing `PATCH /projects/{id}` — no new implementation of its own
- **Polish (Phase 6)**: Depends on whichever user stories were completed (ideally all three)

### Within Each User Story

- Tests (T012/T014, T016, T018) are written before/alongside their story's implementation task
- T005/T006 (models) before T007 (parser, which returns `RequirementExtraction`) and T008 (repository, which stores `StructuredRequirements`) before T009 (router, which uses both)

### Parallel Opportunities

- T002 and T003 (Setup) — already done, but were independent
- T005, T006, T008 (Foundational: models, parser interface, repository) can be done in parallel — different files, and T006/T008 don't need T005's `StructuredRequirements` to be finished first (only `RequirementExtraction`/storage shape)
- T021 (Polish) can run in parallel with T020 — different files
- Because T009, T013, and T017 all edit `backend/app/requirements/router.py`, they are NOT marked `[P]` and should be done in sequence (T009 → T013 → T017)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (already done)
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (T011-T015)
4. **STOP and VALIDATE**: run `pytest` and the relevant `quickstart.md` curl steps (1-4, 8) for US1 only — including a real `OPENAI_API_KEY` call, since T011's fake parser only covers the test suite
5. Confirm with the user before continuing to US2/US3

### Incremental Delivery

1. Setup + Foundational → foundation ready, `OPENAI_API_KEY` wired end-to-end
2. User Story 1 → validate → this is the MVP (parsing works end-to-end, essentials-missing message works)
3. User Story 2 → validate → parsed results can now be retrieved without re-parsing
4. User Story 3 → validate → re-parsing after a description update reflects the new text
5. Polish → full `quickstart.md` walkthrough + README section

## Notes

- All tests share `backend/tests/test_requirements.py`; add new test functions rather than new files.
- No test calls the real OpenAI API — `FakeRequirementParser` (T011) stands in via the same
  monkeypatch-the-module-level-instance pattern Feature 01 used for `repository`. Only the manual
  `quickstart.md` walkthrough (T020) exercises the real API and needs a valid `OPENAI_API_KEY`.
- Stop at each checkpoint to validate that story independently before moving on, matching how Feature 01
  was built.

---

## Amendment (2026-09-03, later the same day, per follow-up request): consolidated into `Project`

Everything above (T001-T021) describes and reflects the feature as originally built: its own
`StructuredRequirements` entity, `RequirementsRepository`/`JsonFileRequirementsRepository`,
`app/requirements/models.py`, a dedicated `GET /projects/{project_id}/requirements`, and a
`target_built_area_m2` field with a "missing essentials" message (T010's `_compute_missing_essential`,
FR-010, SC-006). All of that was superseded the same day by consolidating this feature's output directly
into Feature 01's `Project` — see `specs/001-project-creation/research.md`'s "`Project` absorbs Feature
02's parsed fields" and this feature's own research.md for the full reasoning. The task descriptions above
were **not** rewritten to match (the historical record of what was originally built is more useful than a
misleading "as if it was always this way" rewrite) — treat this amendment as the authoritative statement
of current tasks; where it conflicts with wording above (e.g. T009's `RequirementsRepository`, T013's
`StructuredRequirements`, T016/T017's `GET` endpoint), this amendment wins.

- [X] *(consolidation)* Move `SourceTag`/`TaggedInt`/`TaggedFloat`/`TaggedBool`/`PoolField` from
  `app/requirements/models.py` to `app/projects/models.py`; add `floors`/`bedrooms`/`safe_room`/
  `parking_spaces`/`pool`/`requirements_parsed_at` (all nullable) to `Project` there. Delete
  `app/requirements/models.py` and `app/requirements/repository.py` entirely — no longer needed.
- [X] *(consolidation)* Add `ProjectRepository.set_parsed_requirements(...)` (`app/projects/repository.py`)
  — merges the 5 parsed fields into an existing project, sets `requirements_parsed_at`, leaves
  `updated_at` untouched. Implemented on `JsonFileProjectRepository`.
- [X] *(consolidation)* Remove `target_built_area_m2` from `RequirementExtraction`
  (`app/requirements/parser.py`) and the system prompt (explicitly tells the model built area is already
  known elsewhere and not to report one). Re-verified against the real API after the change.
- [X] *(consolidation)* Rewrite `app/requirements/router.py`: single `POST /projects/{project_id}/requirements`
  — loads the project, calls the parser, calls `set_parsed_requirements`, returns the updated `Project`.
  Removed `GET /projects/{project_id}/requirements`, the `_compute_missing_essential` helper, and all
  FR-010-related logic (no longer meaningful — see research.md).
- [X] *(consolidation)* Rewrite `backend/tests/test_requirements.py` for the new shape: assertions now
  check fields directly on the `Project`/`GET /projects/{id}` response rather than a separate resource; no
  more `missing_essential_fields`/`message` assertions; added a test confirming `updated_at` is untouched
  by parsing.
- [X] *(consolidation)* Rewrite `specs/002-requirement-parser/{spec,data-model,contracts/requirements-api,quickstart}.md`
  for the merged design; add the research.md decision entry cross-referencing Feature 01's fuller writeup.
- [X] *(consolidation)* Update `frontend/src/App.tsx`'s `Project` TypeScript interface to include the new
  nullable fields (type-accuracy only — no new UI added; Feature 02 still has no frontend screen).
- [X] *(consolidation)* Re-ran the full `pytest` suite and the rewritten `quickstart.md` (all 7 steps)
  against a live server with a real `OPENAI_API_KEY` — all passing.
