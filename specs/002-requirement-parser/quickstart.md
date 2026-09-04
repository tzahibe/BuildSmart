# Quickstart: Natural Language Requirement Parser

Validates the feature end-to-end via the running backend, per the acceptance scenarios in `spec.md`.
Assumes Feature 01 (`specs/001-project-creation/`) is already implemented — this feature parses a
project's `description` and merges the result directly into that same project, so a project must exist
first.

> **2026-09-03 amendment**: earlier versions of this file exercised a dedicated `GET
> /projects/{project_id}/requirements` and asserted `target_built_area_m2`/`missing_essential_fields`.
> That endpoint and those fields no longer exist — see spec.md's amendment note. This version reflects the
> current behavior: results live on the `Project` itself, retrieved via Feature 01's `GET
> /projects/{project_id}`.

## Prerequisites

- Python 3.11+, with `backend/.venv` set up (`uv sync --group dev` from `backend/` if dependencies changed).
- `backend/.env` with a valid `OPENAI_API_KEY` (see `backend/.env.example` for the variable name — not
  required to run `pytest`, since tests use a fake parser; required only for the manual `curl` steps below,
  which call the real OpenAI API).
- Run from `backend/`.

## Run the server

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

## Run the tests

```bash
cd backend
.venv/bin/pytest
```

Expected: all tests pass, including `tests/test_requirements.py`.

## Manual validation (matches spec.md acceptance scenarios)

1. **Create a project with a fully-specified description** (setup, reuses Feature 01):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 500, "built_area_m2": 220, "description": "אני רוצה בית בן קומתיים בשטח 220 מ\"ר, 4 חדרי שינה, ממ\"ד, חניה ל-2 עם בריכה 8 על 4 בחצר האחורית"}'
   ```

   Note the returned `project_id`. Its `floors`/`bedrooms`/`safe_room`/`parking_spaces`/`pool`/
   `requirements_parsed_at` are all `null` at this point (User Story 2, Scenario 2) — not yet parsed.

2. **Parse it** (User Story 1, Scenario 1):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/requirements
   ```

   Expected: `200`, the **full project** with `floors.value == 2`, `bedrooms.value == 4`,
   `safe_room.value == true`, `parking_spaces.value == 2`, `pool.requested.value == true`,
   `pool.length_m.value == 8`, `pool.width_m.value == 4` — every one of those tagged `"requested"`.
   `city`/`street`/`plot_area_m2`/`built_area_m2`/`description` are unchanged from step 1.
   `requirements_parsed_at` is now set; `updated_at` is unchanged from step 1 (parsing doesn't touch it).

3. **Parse a project whose description omits fields** (User Story 1, Scenario 2 & 3):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 500, "built_area_m2": 220, "description": "בית עם בריכה"}'
   # then, with the new project_id:
   curl -s -X POST http://127.0.0.1:8000/projects/<new_project_id>/requirements
   ```

   Expected: `200`, `parking_spaces.source == "unknown"` (never mentioned), `pool.requested.value == true`
   but `pool.length_m.source == "unknown"` and `pool.width_m.source == "unknown"` (pool wanted, no
   dimensions given). `bedrooms.source == "unknown"` too. `built_area_m2` is still `220` — this endpoint
   never touches it (FR-012).

4. **Parse a nonexistent project** (User Story 1, Scenario 4):

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects/00000000-0000-0000-0000-000000000000/requirements
   ```

   Expected: `404`.

5. **Retrieve without re-parsing** (User Story 2, Scenario 1):

   ```bash
   curl -s http://127.0.0.1:8000/projects/<project_id from step 1>
   ```

   Expected: `200`, identical to step 2's result (same `requirements_parsed_at`, not a fresh timestamp) —
   this is Feature 01's plain `GET`, no separate endpoint needed.

6. **Re-parse after updating the description** (User Story 3, Scenario 1):

   ```bash
   curl -s -X PATCH http://127.0.0.1:8000/projects/<project_id from step 1> \
     -H "Content-Type: application/json" \
     -d '{"description": "בית בן 3 קומות, 5 חדרי שינה"}'
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id from step 1>/requirements
   ```

   Expected: `200`, `floors.value == 3` and `bedrooms.value == 5` — reflecting the *new* text, not step
   2's original `2`/`4`, and `pool.requested.source == "unknown"` (the new description doesn't mention a
   pool at all). `built_area_m2` is still `220`, untouched by either the `PATCH` (which didn't include it)
   or the re-parse (which never looks at it).

7. **Floors defaults to 1 when unstated, but stays unknown on a real conflict** (FR-011):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 300, "built_area_m2": 150, "description": "בית עם ממ\"ד"}'
   # then, with this project_id:
   curl -s -X POST http://127.0.0.1:8000/projects/<this_project_id>/requirements
   ```

   Expected: `200`, `floors.value == 1`, `floors.source == "inferred"` (never stated, so defaulted — not
   `unknown`), `safe_room.value == true`.

   Now try a description with a stated conflict:

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 300, "built_area_m2": 150, "description": "בית בן 2 קומות, למעשה יש בו 3 קומות"}'
   # then, with this project_id:
   curl -s -X POST http://127.0.0.1:8000/projects/<this_project_id>/requirements
   ```

   Expected: `200`, `floors.source == "unknown"` (the conflicting statement is not the same as "unstated,"
   so the FR-011 default does not apply).

## Interactive exploration

With the server running, open `http://127.0.0.1:8000/docs` for the auto-generated Swagger UI.
