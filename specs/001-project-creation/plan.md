# Implementation Plan: Project Creation (Basic Intake)

**Branch**: `001-project-creation` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-project-creation/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a minimal, self-contained `Project` API to the existing FastAPI backend: create a project (address,
plot area, free-text description), retrieve it by id, and partially update it. No parsing, location
resolution, retrieval, or compliance logic is included — this is the intake/persistence foundation that
every later AI Home Planner feature will build on. Storage is in-memory behind a repository interface so
it can be swapped for a real database later without touching the API layer.

## Technical Context

**Language/Version**: Python 3.11 (matches `backend/pyproject.toml` `requires-python = ">=3.11"`)

**Primary Dependencies**: FastAPI (existing), Pydantic v2 (ships with FastAPI), uvicorn (existing, dev server)

**Storage**: JSON file on disk (`backend/app/data/projects.json`) behind a `ProjectRepository` interface.
No database in this slice — a flat file is enough to survive process restarts during local testing, with
no new infrastructure. This is explicitly temporary: swapping in PostgreSQL (per the long-term tech stack
in the source spec) is a later, isolated change because the API layer only depends on the repository
interface, not the file itself.

**Testing**: pytest + FastAPI's `TestClient` (httpx-based). Both need to be added as dev dependencies —
neither exists in `backend/pyproject.toml` yet.

**Target Platform**: Local backend web service (same as the existing `backend/app` FastAPI app); no new
deployment target.

**Project Type**: Web service. Originally scoped backend-only (exercised via `/docs` or `curl`/`httpx`), but
after the MVP (User Story 1) was validated, a minimal form was added to the existing `frontend/` app on the
user's request (see tasks.md T009a) so project creation is also reachable from a real UI, not just the API.

**Performance Goals**: Not a concern at this scale (single-location MVP, dozens of projects). No explicit
target beyond "responsive for interactive use" (see SC-001: under 5 seconds).

**Constraints**: Must not introduce parsing, location resolution, retrieval, or compliance logic (explicitly
out of scope per FR-010). Must not require any new external service or infrastructure.

**Scale/Scope**: Single backend feature: 3 endpoints (create, get, update), 1 entity (`Project`), in-memory
storage. Matches the MVP scope in the source spec (`docs/AI_Home_Planner_SPEC.md`, section 3).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template (no project-specific principles have been
ratified yet) — there are no concrete gates to evaluate against. This plan instead follows the general
engineering guidance already given in `docs/AI_Home_Planner_SPEC.md` (section 30 "Instructions for Claude
Code"): smallest working version, typed schemas first, tests before/with implementation, no invented data,
no unnecessary abstractions, provider interfaces kept replaceable. No violations to justify.

**Recommendation**: run `/speckit-constitution` before the next feature (once more of the system exists) so
future plans have real gates to check against.

## Project Structure

### Documentation (this feature)

```text
specs/001-project-creation/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                # existing FastAPI app — mounts the aggregated projects router
│   ├── data/                  # new — gitignored, runtime JSON storage
│   │   └── projects.json      # created at runtime by JsonFileProjectRepository, not committed
│   └── projects/               # new
│       ├── __init__.py
│       ├── models.py          # Pydantic schemas: ProjectCreate, ProjectUpdate, Project
│       ├── repository.py      # ProjectRepository interface + JsonFileProjectRepository (temporary — see research.md)
│       └── routes/            # split per user request (2026-09-03), replacing a single router.py
│           ├── __init__.py            # aggregates base/media/analytics routers into one `router`
│           ├── base_routes.py         # POST/GET(/PATCH) /projects — this feature's actual endpoints
│           ├── media_routes.py        # placeholder — no feature specifies project file/media endpoints yet
│           └── analytics_routes.py    # placeholder — no feature specifies reports/statistics yet
└── tests/                     # new
    ├── __init__.py
    └── test_projects.py       # pytest + TestClient coverage, using a temp file per test

frontend/                      # basic form added post-MVP, see T009a in tasks.md
```

**Structure Decision**: Reuse the existing `backend/` package as-is (single FastAPI app, no new services or
processes). Everything for this feature lives under a new `backend/app/projects/` module plus
`backend/tests/`, following the existing `backend/app/` layout rather than introducing the monorepo
`apps/`/`packages/` structure suggested for the full product — that restructuring is not justified for one
small feature and can be revisited once more features exist. The `frontend/` app is untouched; this feature
is API-only.

## Complexity Tracking

*No constitution violations to justify — table intentionally omitted.*
