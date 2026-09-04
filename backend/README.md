# Backend

FastAPI backend for BuildSmart.

## Setup

```bash
uv sync --group dev
```

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` — required for `POST
/projects/{project_id}/requirements` (see below), not required to run `pytest` (tests use a fake
parser, no real OpenAI calls).

## Run

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://127.0.0.1:8000/docs`

## Tests

```bash
.venv/bin/pytest
```

## Endpoints

- `GET /health` — liveness check.
- `POST /projects` — create a project (`city`, `street`, `plot_area_m2`, `built_area_m2`, `description`).
  `built_area_m2` must be strictly smaller than `plot_area_m2`.
- `GET /projects/{project_id}` — retrieve a project.
- `PATCH /projects/{project_id}` — partially update a project.
- `GET /localities` — city suggestions/whitelist for the `city` field.
- `GET /localities/{city}/streets` — street suggestions/whitelist for `street`, scoped to `city`.
- `POST /projects/{project_id}/requirements` — parse the project's `description` into structured,
  source-tagged requirements (floors, target built area, bedrooms, safe room, parking, pool) via OpenAI's
  `gpt-5-nano`. Floors defaults to 1 (single story) when unstated. Flags a message when target built area
  (or, rarely, floors) can't be determined from the text.
- `GET /projects/{project_id}/requirements` — retrieve the last parsed result without re-parsing.
- `POST /projects/{project_id}/design` — generate (or regenerate) a deterministic parametric design model
  (site dimensions, per-floor room layout) from the project's parsed requirements — no LLM involved.
  Requires the project to have been parsed first (`404` if the project doesn't exist, `422` if it hasn't
  been parsed yet or its built area is too small to fit the required rooms).
- `GET /projects/{project_id}/chat` — retrieve the project's full chat conversation with the AI assistant
  (`{"project_id", "messages": [...]}`, empty `messages` if nothing sent yet). `404` if the project doesn't
  exist.
- `POST /projects/{project_id}/chat/messages` — send a message (`{"content": "..."}`) and receive the
  assistant's reply, both persisted; returns the full updated conversation. The assistant is grounded in
  the project's current data (entered fields, parsed requirements, generated design model) via OpenAI's
  `gpt-5-nano`, but cannot itself change stored project data. `404` if the project doesn't exist, `422` for
  empty content, `502` if the assistant call fails (nothing is persisted on that path).

Full request/response shapes: `specs/001-project-creation/contracts/projects-api.md`,
`specs/002-requirement-parser/contracts/requirements-api.md`,
`specs/003-parametric-design-model/contracts/design-api.md`, and
`specs/004-design-viewer-chat/contracts/chat-api.md`.

## Storage

Projects are stored in a single JSON file (`app/data/projects.json`, gitignored, created at runtime) —
not a database. This is intentional and temporary: it's the smallest thing that works for one small
feature, kept behind a `ProjectRepository` interface (`app/projects/repository.py`) specifically so it can
be swapped for a real database (PostgreSQL, per the project's long-term stack) later without touching the
API layer. See `specs/001-project-creation/research.md` for the full reasoning.

City/street data (`app/localities/`) is a separate, static snapshot of an official data.gov.il address
registry — see `app/localities/data.py` for sourcing and refresh instructions.

Parsed requirements (`app/requirements/`) are stored the same way, in `app/data/requirements.json`, behind
a `RequirementsRepository` interface. The OpenAI call itself is behind a `RequirementParser` interface
(`app/requirements/parser.py`) — see `specs/002-requirement-parser/research.md` for the model choice and
its accepted trade-offs.

The generated design model (`app/design/`) has no storage of its own — its fields (`site_width_m`,
`rooms`, `design_notes`, ...) are merged directly into `Project` and saved in `app/data/projects.json`
alongside everything else, the same way parsed requirements are.

Chat conversations (`app/chat/`) are stored separately, in `app/data/conversations.json`, keyed by
`project_id`, behind a `ConversationRepository` interface (`app/chat/repository.py`) — kept out of
`projects.json` since a chat log grows independently and unboundedly, unlike the small fixed-shape fields
Features 02/03 merge in. The OpenAI call is behind a `ChatAssistant` interface (`app/chat/assistant.py`).
See `specs/004-design-viewer-chat/research.md` for the reasoning.
