---

description: "Task list template for feature implementation"
---

# Tasks: Design Viewer & Assistant Chat

**Input**: Design documents from `/specs/004-design-viewer-chat/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/chat-api.md, quickstart.md

**Tests**: Included for the backend (pytest, matching Features 01-03's pattern). No frontend tests —
`frontend/` has no test runner yet and plan.md's Technical Context deliberately doesn't add one for this
feature; frontend work is validated manually via quickstart.md instead.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)

## Path Conventions

Backend paths under `backend/`, frontend paths under `frontend/src/`, per plan.md's Project Structure.
This feature depends on Feature 01 (`backend/app/projects/`) and Feature 02 (`backend/app/requirements/`),
both already implemented. Feature 03 (`backend/app/design/`) has its `Project` fields and repository method
already implemented (`backend/app/projects/models.py`/`repository.py`) but its generator and router do not
exist yet — completing them is this feature's Foundational phase (research.md §1).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization for the new `chat` package

- [X] T001 Create `backend/app/chat/__init__.py` (new package, per plan.md Project Structure)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Finish Feature 03's backend (a hard prerequisite for US1/US2 — there is no sketch without a
generated design model) and stand up the shared frontend modules every screen in this feature reads from

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Implement `generate_design(project: Project) -> GeneratedDesign` in
  `backend/app/design/generator.py` — pure function, no I/O, per
  `specs/003-parametric-design-model/data-model.md`'s algorithm: square site from `plot_area_m2`;
  even floor-area split; ground-floor fixed rooms (kitchen 12/bathroom 5/safe room 9 if
  known-requested) with a typed footprint-too-small error; living room + same-floor bedrooms split the
  remainder evenly (`floors == 1`); bedroom distribution across upper floors (`floors > 1`); 1D row
  layout per floor; `design_notes` entries when `bedrooms`/`safe_room` source is `unknown`
- [X] T003 Create `backend/app/design/router.py` with `APIRouter(prefix="/projects", tags=["design"])`
  implementing `POST /projects/{project_id}/design` per
  `specs/003-parametric-design-model/contracts/design-api.md` (404 missing project, 422 unparsed
  project, 422 footprint-too-small, 200 merged `Project` via `set_design_model`), and mount it in
  `backend/app/main.py`
- [X] T004 [P] `backend/tests/test_design.py`: unit tests for `generate_design()` (single floor with
  known bedrooms/safe_room; floors=2 puts bedrooms upstairs; floors=3 odd bedroom count splits with
  remainder; unknown bedrooms/safe_room excluded with a `design_notes` entry; footprint-too-small
  raises) and endpoint tests for `POST /projects/{project_id}/design` (full create→parse→generate flow
  returns 200; unparsed project 422; nonexistent project 404; footprint-too-small 422)
- [X] T005 [P] `frontend/src/types.ts`: move `TaggedValue`/`PoolField`/`Project`/`Room`/`FormState`/
  `ValidationErrorDetail` out of `frontend/src/App.tsx` into this shared module (no behavior change)
- [X] T006 `frontend/src/api.ts`: extract the existing inline `POST /projects` call from `App.tsx` into
  `createProject(data)`, and add `parseRequirements(projectId)` (`POST /projects/{id}/requirements`) and
  `generateDesign(projectId)` (`POST /projects/{id}/design`) helpers, typed via `types.ts` (T005)

**Checkpoint**: Feature 03's design generation works end-to-end (verifiable via
`specs/003-parametric-design-model/quickstart.md`), and the frontend has shared types/API helpers ready —
user story work can begin

---

## Phase 3: User Story 1 - From project creation to seeing the design (Priority: P1) 🎯 MVP

**Goal**: After creating a project, the user watches a full-screen house-building loading animation while
parsing + design generation run, then is automatically taken to a Design page showing the sketch.

**Independent Test**: Create a project via the existing form and observe the full-screen animation play,
followed by automatic navigation to a Design page rendering that project's sketch — no chat or technical
details needed yet.

### Implementation for User Story 1

- [X] T007 [P] [US1] `frontend/src/design/LoadingScreen.tsx` + `LoadingScreen.css`: full-screen
  progressive "house being built" CSS/SVG keyframe animation (foundation → walls → roof → door/windows,
  per research.md §6) that loops indefinitely — no fixed duration, no generic spinner (FR-002)
- [X] T008 [P] [US1] `frontend/src/design/SketchSvg.tsx`: pure component rendering `Project.rooms` +
  `site_width_m`/`site_depth_m` as labeled SVG `<rect>`s scaled to its container (research.md §5), with a
  floor-tab selector shown only when rooms span more than one floor
- [X] T009 [US1] `frontend/src/design/DesignPage.tsx` + `DesignPage.css`: page shell rendering `SketchSvg`
  (T008) inside a bounded card over a static house-and-garden CSS/SVG backdrop (FR-005/FR-006); if the
  project has no generated design yet (`rooms === null`), render a clear "not available" state instead of
  a blank/broken card (spec.md Edge Cases)
- [X] T010 [US1] `frontend/src/App.tsx`: replace the current inline "project created" result panel with a
  `view: 'form' | 'loading' | 'design'` state; on successful `createProject` (T006), set `view =
  'loading'`; while `view === 'loading'`, render `LoadingScreen` (T007) and, in an effect, call
  `parseRequirements` then `generateDesign` (T006) in sequence, updating the held `project` after each; on
  success set `view = 'design'` (rendering `DesignPage`, T009) (FR-001/FR-003); on failure of either call,
  keep `LoadingScreen` mounted but show its clear explanatory error state instead of navigating (FR-004)
- [X] T011 [US1] Manual validation: quickstart.md frontend steps 1-3 (loading animation plays with no
  blank/frozen screen, automatic navigation, sketch card visible on the Design page)

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP

---

## Phase 4: User Story 2 - Inspect the sketch full-screen (Priority: P2)

**Goal**: Clicking the sketch card expands it to fill the screen; a visible X closes it back; stays
responsive across viewport/orientation changes.

**Independent Test**: On a project's Design page, click the sketch card, confirm it fills the screen,
click the X, confirm it returns to the card — independent of chat/menu.

### Implementation for User Story 2

- [X] T012 [US2] `frontend/src/design/SketchCard.tsx` + `SketchCard.css`: wraps `SketchSvg` (T008) with a
  bounded-card ↔ full-screen-overlay toggle — click/tap the card expands (FR-007), a visible X control in
  the full-screen view closes it back (FR-008), and the rendered scale recomputes on resize/orientation
  change so the full-screen view never needs reopening (FR-009 / spec.md Edge Cases)
- [X] T013 [US2] `frontend/src/design/DesignPage.tsx`: swap the direct `SketchSvg` usage from T009 for
  `SketchCard` (T012), so the sketch is now expandable
- [X] T014 [US2] Manual validation: quickstart.md frontend steps 4-6 (click to expand, X to close, resize
  while full-screen stays legible)

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Continue the conversation with the assistant (Priority: P3)

**Goal**: A chat panel on the Design page lets the user talk to an AI assistant about their project, with
the conversation persisted and resumable across visits.

**Independent Test**: Send a message in the chat panel, receive a reply, reload the Design page, confirm
the full prior conversation is shown and new messages can still be sent.

### Tests for User Story 3

- [X] T015 [P] [US3] `backend/tests/test_chat.py`: a `FakeChatAssistant` fixture (no real OpenAI calls,
  matching Feature 02's `FakeRequirementParser` convention) covering: `GET .../chat` on a project with no
  messages returns `{"project_id": ..., "messages": []}`; `POST .../chat/messages` appends both the user
  message and the assistant's reply and returns the full conversation; a second `GET` afterward shows the
  same messages in order; nonexistent project → 404 on both endpoints; empty/whitespace-only `content` →
  422; when the fake assistant raises, the endpoint returns 502 **and** the conversation is unchanged
  (nothing partially persisted — data-model.md's atomicity note)

### Implementation for User Story 3

- [X] T016 [P] [US3] `backend/app/chat/models.py`: `ChatRole` (`user`/`assistant`), `ChatMessage` (`role`,
  `content`, `created_at`), `Conversation` (`project_id`, `messages`), `ChatMessageCreate` (`content`,
  validated non-empty after trimming) — per data-model.md
- [X] T017 [P] [US3] `backend/app/chat/repository.py`: `ConversationRepository` ABC (`get(project_id) ->
  Conversation`, returning an empty `Conversation` when none stored; `append_messages(project_id, *,
  new_messages) -> Conversation`) and `JsonFileConversationRepository` storing at
  `backend/app/data/conversations.json`, mirroring `JsonFileProjectRepository`'s load/mutate/save pattern
  (`backend/app/projects/repository.py`)
- [X] T018 [US3] `backend/app/chat/assistant.py`: `ChatAssistant` ABC (`reply(project, history,
  new_message) -> str`) and `OpenAIChatAssistant` — builds a system prompt from the project's current
  data (entered fields, parsed requirements with source tags, design-model summary if present, per
  research.md §3) plus stored history, calls `chat.completions.create` with `gpt-5-nano` (same client
  pattern as `backend/app/requirements/parser.py`), returns the reply text; does not call any tool and
  cannot mutate `Project` (plan.md Design decisions)
- [X] T019 [US3] `backend/app/chat/router.py` with `APIRouter(prefix="/projects", tags=["chat"])`
  implementing `GET /projects/{project_id}/chat` and `POST /projects/{project_id}/chat/messages` per
  contracts/chat-api.md (404 missing project; 422 empty content; on assistant failure, catch it, persist
  nothing, return 502; on success, call `append_messages` once with both the user message and the reply
  and return the full `Conversation`), and mount it in `backend/app/main.py`
- [X] T020 [US3] Run `backend/.venv/bin/pytest` and confirm the User Story 3 tests (T015) pass
- [X] T021 [P] [US3] `frontend/src/types.ts`: add `ChatRole`/`ChatMessage`/`Conversation` types matching
  contracts/chat-api.md
- [X] T022 [P] [US3] `frontend/src/api.ts`: add `getChat(projectId)` (`GET .../chat`) and
  `sendChatMessage(projectId, content)` (`POST .../chat/messages`) helpers, typed via T021
- [X] T023 [US3] `frontend/src/design/ChatPanel.tsx` + `ChatPanel.css`: loads the conversation via
  `getChat` (T022) when opened; message list + input; sending calls `sendChatMessage`; on failure, shows a
  clear per-message error and lets the user retry without discarding the rest of the history (FR-013,
  matching contracts/chat-api.md's "nothing persisted on 502" — an optimistically-shown failed message is
  marked failed/removed, not silently kept as if it sent)
- [X] T024 [US3] `frontend/src/design/DesignPage.tsx`: mount `ChatPanel` (T023) as a panel/overlay that is
  mutually exclusive with the full-screen sketch (T012) — opening one closes the other (spec.md Edge
  Cases)
- [X] T025 [US3] Manual validation: quickstart.md backend steps 1-6 (chat API) and frontend step 7 (send,
  reload, conversation persists)

**Checkpoint**: User Stories 1, 2, AND 3 all work independently

---

## Phase 6: User Story 4 - Review the technical details behind the design (Priority: P4)

**Goal**: A menu on the Design page opens a Technical Details view listing entered and system-derived
data, then returns without losing sketch/chat state.

**Independent Test**: Open the menu, select Technical Details, confirm entered + derived data both appear,
navigate back, confirm the Design page is unchanged.

### Implementation for User Story 4

- [X] T026 [P] [US4] `frontend/src/design/Menu.tsx` + `Menu.css`: a menu control on the Design page
  offering navigation to Technical Details; mutually exclusive overlay with chat (T023) and full-screen
  sketch (T012), same pattern as T024 (FR-014, spec.md Edge Cases)
- [X] T027 [P] [US4] `frontend/src/design/TechnicalDetailsPage.tsx` + `TechnicalDetailsPage.css`:
  read-only view listing the project's entered fields (city/street/plot & built area/description, Feature
  01) and system-derived data (parsed requirements with `requested`/`inferred`/`unknown` source tags,
  Feature 02; generated design model — site dimensions, room list, `design_notes`, Feature 03) (FR-015)
- [X] T028 [US4] `frontend/src/App.tsx` / `frontend/src/design/DesignPage.tsx`: wire the Menu's (T026)
  Technical Details entry to `TechnicalDetailsPage` (T027) as an additional overlay/view that, when closed,
  returns to the Design page with its sketch and chat state exactly as they were (FR-016) — no remount of
  `DesignPage`'s existing state
- [X] T029 [US4] Manual validation: quickstart.md frontend steps 8-9 (technical details content, back
  preserves sketch/chat state, narrow-viewport pass across all overlays)

**Checkpoint**: All four user stories are independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Wrap-up validation and documentation, no new behavior

- [X] T030 [P] Responsive pass: verify `LoadingScreen`, `DesignPage`, `SketchCard`, `ChatPanel`, `Menu`,
  and `TechnicalDetailsPage` have no cut-off/overlapping controls from common phone widths (~360px) through
  desktop (FR-009 / SC-005)
- [X] T031 [P] Update `backend/README.md` documenting `POST /projects/{project_id}/design` (completing
  Feature 03's own documentation gap) and the new `GET`/`POST /projects/{project_id}/chat...` endpoints
  with their preconditions/error cases
- [X] T032 Run the full `specs/004-design-viewer-chat/quickstart.md` walkthrough (backend curl steps +
  frontend manual steps, all of them) end-to-end and confirm every step's expected result

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. T002 before T003 (router calls
  the generator) before T004 (tests exercise both); T005 before T006 (api.ts imports types.ts) — these two
  frontend tasks are independent of the backend ones
- **User Story 1 (Phase 3)**: Depends only on Foundational — this is the MVP. T007/T008 can proceed in
  parallel; T009 depends on T008; T010 depends on T006 (api helpers), T007, and T009
- **User Story 2 (Phase 4)**: Depends on US1's T008 (`SketchSvg`) and T009 (`DesignPage`) existing to wrap
  and swap into
- **User Story 3 (Phase 5)**: Backend (T015-T020) depends only on Foundational, independent of US1/US2.
  Frontend (T021-T024) depends on US1's T009 (`DesignPage` to mount into) and on T019 (the endpoints T022
  calls)
- **User Story 4 (Phase 6)**: Depends on US1's T009 (`DesignPage` to add a menu to) and reads the same
  `Project`/parsed-requirements/design-model data US1-US3 already have typed (T005) — independent of
  US2/US3's own UI otherwise, beyond the "mutually exclusive overlay" convention T024 established
- **Polish (Phase 7)**: Depends on whichever user stories were completed (ideally all four)

### Parallel Opportunities

- T002 (generator) [P] with T005/T006 (frontend shared modules) — different stacks entirely
- T007 and T008 (Loading animation vs. sketch renderer) [P] — different files, no shared dependency
- T015 (chat tests), T016 (chat models), T017 (chat repository) [P] — independent files; T018 (assistant)
  and T019 (router) depend on T016/T017's types existing, so land those first in practice
- T021 (chat types) and T022 (chat api helpers) [P] with each other once T019 (endpoints) exists
- T026 (Menu) and T027 (TechnicalDetailsPage) [P] — independent files, joined together only in T028
- T030 and T031 (Polish) [P] — different concerns/files

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (finishes Feature 03's backend + shared frontend modules)
3. Complete Phase 3: User Story 1 (T007-T011)
4. **STOP and VALIDATE**: run `backend/.venv/bin/pytest` and quickstart.md frontend steps 1-3
5. Confirm with the user before continuing to US2/US3/US4

### Incremental Delivery

1. Setup + Foundational → Feature 03's design generation works end-to-end; frontend has shared types/API
2. User Story 1 → validate → this is the MVP (loading animation → auto-navigate → sketch visible)
3. User Story 2 → validate → sketch expands/collapses full-screen, responsive
4. User Story 3 → validate → chat sends/receives/persists, survives reload, handles failures gracefully
5. User Story 4 → validate → technical details reachable from a menu, state preserved on return
6. Polish → full quickstart.md walkthrough + README section

## Notes

- Backend tests (T004, T015) don't call the real OpenAI API — same convention as Features 01-03 — using
  fake `RequirementParser`/`ChatAssistant` fixtures so the suite stays fast and deterministic.
- Frontend has no automated tests in this repository yet; every frontend task's correctness is checked via
  its story's quickstart.md manual-validation task instead.
- Stop at each checkpoint to validate that story independently before moving on, matching Features 01-03.
