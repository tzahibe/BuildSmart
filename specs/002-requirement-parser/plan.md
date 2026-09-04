# Implementation Plan: Natural Language Requirement Parser

**Branch**: `002-requirement-parser` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-requirement-parser/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

> **2026-09-03, later the same day — amendment**: this plan (and the Project Structure below) describes
> the feature as originally built, with its own `StructuredRequirements` entity/repository/`GET` endpoint.
> That was consolidated into Feature 01's `Project` the same day — see research.md and
> `specs/001-project-creation/research.md`. The single surviving endpoint is `POST
> /projects/{project_id}/requirements`, returning the updated `Project`; `app/requirements/` now holds
> only `parser.py` and `router.py`.

Add an endpoint pair that parses an existing project's free-text `description` (from Feature 01) into
structured requirements — floors, built area, bedrooms, safe room, parking spaces, pool — each tagged
`requested`/`inferred`/`unknown`, and persists the latest result per project. Per explicit request, the
parser calls OpenAI's cheapest model (`gpt-5-nano`) from the backend, using structured outputs so the
model's response conforms directly to the tagged-field schema — kept behind a `RequirementParser`
interface so the provider/model can be swapped later without touching the API or storage layers. (An
earlier plan draft recommended a regex-based extractor instead; see research.md for both decisions and
why the LLM-based one is now in force.)

Two fields get special handling, both refined into the spec via follow-up requests: only `target_built_area_m2`
and `floors` are treated as essential for planning (bedrooms, safe room, parking, and pool are optional
extras a response `message` may suggest, never require — FR-010); and `floors` specifically defaults to 1
story (tagged `inferred`) whenever the text doesn't state a count, rather than being left `unknown` like
every other unstated field (FR-011).

## Technical Context

**Language/Version**: Python 3.11 (matches the existing `backend/` package)

**Primary Dependencies**: FastAPI, Pydantic (existing); `openai` (new, official Python SDK, `chat.completions.parse`
with a Pydantic `response_format` for structured outputs) and `python-dotenv` (new, loads `OPENAI_API_KEY`
from `backend/.env` at startup)

**Storage**: JSON file (`backend/app/data/requirements.json`) behind a `RequirementsRepository` interface —
same temporary-snapshot pattern as `backend/app/projects/repository.py` (see that feature's research.md for
the rationale; unchanged here). Keyed by `project_id`, one entry per project (latest parse only, per
spec.md's Assumptions).

**Testing**: pytest + FastAPI `TestClient` (existing pattern from Feature 01)

**Target Platform**: Same backend web service as Feature 01; no new deployment target

**Project Type**: Web service, backend only for this slice — no frontend UI is added in this plan (Feature
01's UI already covers project creation; a "parse requirements" screen can be requested as a follow-up the
same way Feature 01's UI was, rather than assumed here)

**Performance Goals**: A single `gpt-5-nano` call over a short paragraph is expected to complete in low
single-digit seconds — comfortably inside spec.md's SC-001/SC-004 10-second budget, verified during
planning with a real test call. No specific target beyond that budget.

**Constraints**: MUST NOT fabricate a value for any field the source text doesn't support (FR-004). Unlike
a rule-based extractor, this is enforced only via prompt instructions to the model, not structurally — an
accepted, explicitly-documented risk (see research.md). `OPENAI_API_KEY` MUST be loaded from environment
configuration (`backend/.env`, gitignored), never hardcoded or committed.

**Scale/Scope**: One backend feature: 2 endpoints (parse/store, retrieve), 1 new entity
(`StructuredRequirements`), one parser implementation. Operates on data Feature 01 already owns; adds no
new user-facing entity beyond what spec.md defines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template — no project-specific gates exist yet
(same situation as Feature 01; see that feature's plan.md for the same note and recommendation to run
`/speckit-constitution` once more of the system exists). This plan follows the same general engineering
guidance from `docs/AI_Home_Planner_SPEC.md` §30 as Feature 01 did: smallest working version, typed
schemas first, deterministic logic preferred over LLM output where possible, no invented data, replaceable
providers. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/002-requirement-parser/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                    # existing — mounts the new requirements router
│   ├── projects/                  # existing (Feature 01), untouched
│   ├── localities/                # existing (Feature 01), untouched
│   └── requirements/              # new
│       ├── __init__.py
│       ├── models.py              # SourceTag enum; IntField/FloatField/BoolField (value + source);
│       │                          # PoolField; StructuredRequirements
│       ├── parser.py              # RequirementParser interface + OpenAIRequirementParser
│       │                          # (gpt-5-nano via chat.completions.parse, structured outputs)
│       └── repository.py          # RequirementsRepository interface + JsonFileRequirementsRepository
│                                   # (same temporary-JSON-file pattern as projects/repository.py)
├── app/requirements/router.py     # (grouped above) — POST/GET /projects/{project_id}/requirements
├── .env                           # gitignored — OPENAI_API_KEY (loaded via python-dotenv in main.py)
├── .env.example                   # committed template, no real value
└── tests/
    └── test_requirements.py       # new — pytest + TestClient coverage, using a fake RequirementParser
                                    # (no real OpenAI calls in tests — see research.md's hermeticity note)

frontend/                          # untouched in this feature
```

**Structure Decision**: New `backend/app/requirements/` module, mirroring the existing `backend/app/projects/`
and `backend/app/localities/` module shapes (models / parser-or-repository / router) rather than nesting
under `app/projects/` — this feature has its own entity (`StructuredRequirements`) and its own storage, and
only *reads* project data (via the existing project repository) rather than owning it. Endpoints are nested
under `/projects/{project_id}/requirements` to reflect that a requirements result always belongs to exactly
one project.

## Complexity Tracking

*No constitution violations to justify — table intentionally omitted.*
