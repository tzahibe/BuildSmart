# Implementation Plan: Design Viewer & Assistant Chat

**Branch**: `004-design-viewer-chat` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-design-viewer-chat/spec.md`

## Summary

After a project is created, drive the existing parse (Feature 02) and design-generation (Feature 03)
endpoints from the frontend behind a full-screen "house being built" loading animation, then land on a new
Design page: the generated room layout rendered as an SVG sketch inside a card (over a decorative
house-and-garden backdrop), expandable to full screen with an X to close; a chat panel backed by a new
project-scoped conversation stored server-side and replied to by an OpenAI-backed assistant; and a menu
leading to a read-only Technical Details view of everything entered and derived for the project. Feature
03's backend (`generate_design` + `POST /projects/{id}/design`) is speced but not yet implemented — this
plan treats finishing it as an in-scope prerequisite, reusing its own documented algorithm rather than
redesigning it here.

## Technical Context

**Language/Version**: Python 3.11 (`backend/`, existing), TypeScript 5.x / React 19 (`frontend/`, existing)

**Primary Dependencies**: FastAPI, Pydantic, `openai` (existing, reused for the chat assistant — same
provider/pattern as Feature 02's parser). Frontend: React 19, no new runtime dependency — no router library
is added; the three screens (form, loading, design) are plain state in `App.tsx`, matching the project's
current all-in-`App.tsx` structure and its "small composable modules" principle over pulling in
infrastructure for a 3-screen flow.

**Storage**: Conversations persisted the same way `Project` already is — one JSON file
(`backend/app/data/conversations.json`), keyed by `project_id`, via a new `ConversationRepository` mirroring
`ProjectRepository`'s shape (see `backend/app/projects/repository.py`).

**Testing**: pytest for the new/completed backend modules (`app/design/`, `app/chat/`), matching Features
01-03's pattern — a fake `ChatAssistant` for endpoint tests, no real OpenAI calls in tests (same convention
as Feature 02's `FakeRequirementParser`). No frontend test runner exists in this project yet
(`frontend/package.json` has none); this feature does not introduce one — frontend verification is manual,
via `quickstart.md`, consistent with Features 01-03's frontend work to date.

**Target Platform**: Same FastAPI backend service + Vite/React SPA; no new deployment target.

**Project Type**: Web application (existing `backend/` + `frontend/` split).

**Performance Goals**: Chat replies and the parse+design pipeline are dominated by the LLM call latency
(same order as Feature 02's parse call); spec.md's SC-001/SC-003 don't set a hard number beyond "the
loading animation never appears frozen" and "no page-leaving wait for a chat reply" — both satisfied by an
always-visible animation/typing state rather than a numeric budget.

**Constraints**: The assistant chat MUST NOT be presented as directly, silently mutating the project's
stored requirements — see Design decisions below for why automatic re-parsing from chat is deliberately
out of scope for this slice. The sketch MUST be rendered purely from already-generated `Project` data
(`site_width_m`/`site_depth_m`/`rooms`) — no new geometry invented client-side beyond meters→pixels scaling.

**Scale/Scope**: One new backend module (`backend/app/chat/`), completion of the already-speced
`backend/app/design/` module, and a frontend restructuring of `App.tsx` into a small set of page/component
files under `frontend/src/`.

## Constitution Check

`.specify/memory/constitution.md` is still the unfilled template — no project-specific gates exist (same
note as Features 01-03). No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/004-design-viewer-chat/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── chat-api.md      # Phase 1 output (design-api.md already exists under specs/003/contracts/)
└── tasks.md              # Phase 2 output (/speckit-tasks — not created by this command)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                     # + mounts chat router (design router already planned by 003)
│   ├── design/                     # completing Feature 03 (prerequisite for this feature's US1/US2)
│   │   ├── __init__.py             # exists
│   │   ├── generator.py            # new — pure function, per specs/003/data-model.md
│   │   └── router.py               # new — POST /projects/{id}/design, per specs/003/contracts/design-api.md
│   └── chat/                       # new
│       ├── __init__.py
│       ├── models.py               # ChatRole, ChatMessage, Conversation, ChatMessageCreate
│       ├── repository.py           # ConversationRepository (ABC) + JsonFileConversationRepository
│       ├── assistant.py            # ChatAssistant (ABC) + OpenAIChatAssistant
│       └── router.py               # GET/POST /projects/{id}/chat...
└── tests/
    ├── test_design.py              # new — completes 003's planned tests
    └── test_chat.py                # new

frontend/
└── src/
    ├── types.ts                    # new — Project/Room/TaggedValue etc. moved out of App.tsx, + chat types
    ├── api.ts                      # new — fetch helpers for projects/requirements/design/chat endpoints
    ├── App.tsx                     # trimmed to a small view-state switch: form | loading | design
    ├── App.css                     # existing, split as needed
    └── design/                     # new
        ├── LoadingScreen.tsx       # + .css — full-screen house-building animation
        ├── DesignPage.tsx          # + .css — composes SketchCard, ChatPanel, Menu
        ├── SketchSvg.tsx           # pure component: Room[] + site dims -> SVG floor sketch
        ├── SketchCard.tsx          # + .css — bounded card <-> full-screen (X) toggle, wraps SketchSvg
        ├── ChatPanel.tsx           # + .css — message list + input, calls chat API
        ├── Menu.tsx                # + .css — reveals nav to Technical Details
        └── TechnicalDetailsPage.tsx # + .css — read-only entered + derived data view
```

**Structure Decision**: Backend follows the existing per-feature-module pattern (`app/design/`, `app/
chat/`), each with its own router mounted in `main.py`, mirroring `app/requirements/`. Frontend moves off
a single 290-line `App.tsx` into a `design/` folder of small page/components once a second real "page"
(beyond the existing creation form) is added — still no router library, since three view states don't
justify one.

## Design decisions (implementation detail, deliberately not in spec.md)

- **Pipeline orchestration lives in the frontend, not a new backend endpoint**: after `POST /projects`
  succeeds, the loading screen itself calls `POST /projects/{id}/requirements` then `POST /projects/{id}/
  design` in sequence, updating local state after each, before navigating to the Design page. This reuses
  Features 02/03's endpoints exactly as specced instead of adding a redundant combined endpoint, at the
  cost of the frontend owning a two-step sequence — acceptable since it only has one caller.
- **Chat does not auto-edit stored requirements in this slice**: spec.md's Assumptions leave this as a
  "may" (not a functional requirement — see FR-010/FR-011, which only require sending/receiving/persisting
  messages). Wiring chat replies into automatic re-parsing would mean the assistant silently mutating
  project data with no user confirmation step, which cuts against the source spec's Principle C ("no
  deciding in place of the user") and Principle E ("MVP before multi-agent complexity"). The assistant is
  grounded in the project's current data (description, parsed requirements, design model) so it can discuss
  and suggest changes in its replies; a user who wants to actually change something still uses the existing
  create/update flow. This is a deliberate scope cut, documented here so it isn't mistaken for an oversight.
- **Sketch rendering is a plain SVG built from `Room[]`**: each room becomes a labeled `<rect>` positioned
  via `x`/`y`/`width_m`/`depth_m` scaled to pixels by a fixed meters-to-pixels factor derived from
  `site_width_m`/`site_depth_m` and the container size; when `floors > 1`, a small tab control switches
  which floor's rooms are drawn. No canvas/charting library is introduced — the geometry is already
  axis-aligned rectangles, which plain SVG renders directly.
- **House-building loading animation and house-and-garden backdrop are original CSS/SVG, not image
  assets**: keeps the feature dependency-free (no image hosting/licensing) and matches the project's
  current asset-free frontend. The backdrop is decorative only (per spec.md's Assumptions) — a static
  illustrated scene, not data-driven.
- **Chat assistant model**: reuses Feature 02's `gpt-5-nano` choice for consistency and cost (same
  provider/client already in `backend/app/requirements/parser.py`); this is revisitable independently of
  this feature if reply quality proves insufficient.
