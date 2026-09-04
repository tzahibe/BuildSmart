# Quickstart: Parametric Design Model

Validates the feature end-to-end via the running backend, per the acceptance scenarios in `spec.md`.
Assumes Features 01 and 02 are already implemented — a project must exist and have been parsed at least
once before a design model can be generated.

## Prerequisites

- Python 3.11+, with `backend/.venv` set up (`uv sync --group dev` from `backend/` if dependencies changed).
- `backend/.env` with a valid `OPENAI_API_KEY` — needed for step 1's parse call (Feature 02), not for
  design generation itself (this feature makes no external calls).
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

Expected: all tests pass, including `tests/test_design.py`.

## Manual validation (matches spec.md acceptance scenarios)

1. **Create and parse a single-floor project** (setup, reuses Features 01 & 02):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 500, "built_area_m2": 120, "description": "בית עם 3 חדרי שינה, ממ\"ד"}'
   # note the project_id, then:
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/requirements
   ```

2. **Generate a design model** (User Story 1, Scenario 1):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/design
   ```

   Expected: `200`. `site_width_m == site_depth_m == sqrt(500) ≈ 22.36`. `rooms` contains exactly one
   `kitchen`, one `bathroom`, one `safe_room`, one `living_room`, and 3 `bedroom` entries, all on
   `floor: 1`. Every room's `area_m2 > 0` and the fixed rooms match the constants in research.md (kitchen
   12, bathroom 5, safe room 9). `design_notes == []`. `design_generated_at` is set.

3. **Generate for an un-parsed project** (User Story 1, Scenario 3):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 300, "built_area_m2": 90, "description": "בית קטן"}'
   # WITHOUT calling POST .../requirements first:
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects/<new_project_id>/design
   ```

   Expected: `422` — project hasn't been parsed yet.

4. **Generate a nonexistent project**:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects/00000000-0000-0000-0000-000000000000/design
   ```

   Expected: `404`.

5. **Multi-floor project — bedrooms on upper floor(s)** (User Story 1, Scenario 2):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 500, "built_area_m2": 200, "description": "בית בן 2 קומות, 4 חדרי שינה"}'
   # note the project_id, then:
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/requirements
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/design
   ```

   Expected: `200`. Floor 1 has `kitchen`/`bathroom`/`living_room` (and `safe_room` if requested) and no
   `bedroom` entries. Floor 2 has all 4 `bedroom` entries and no other room types.

6. **Unknown bedrooms → excluded with a recorded note** (User Story 1, Scenario 4):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 300, "built_area_m2": 80, "description": "בית קטן"}'
   # note the project_id, then:
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/requirements
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/design
   ```

   Expected: `200`. `rooms` has no `bedroom` entries (and no `safe_room`, since that's also unmentioned).
   `design_notes` is non-empty, naming both omissions.

7. **Footprint too small for fixed rooms** (User Story 1, Scenario 5):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 100, "built_area_m2": 10, "description": "בית זעיר עם ממ\"ד"}'
   # note the project_id, then:
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/requirements
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects/<project_id>/design
   ```

   Expected: `422` — 10 m² can't fit a 12 m² kitchen + 5 m² bathroom + 9 m² safe room.

8. **Regenerate after a change** (User Story 3):

   ```bash
   curl -s -X PATCH http://127.0.0.1:8000/projects/<project_id from step 2> \
     -H "Content-Type: application/json" \
     -d '{"built_area_m2": 150}'
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id from step 2>/design
   ```

   Expected: `200`, room areas reflect the new `built_area_m2` (150, not the original 120).

## Interactive exploration

With the server running, open `http://127.0.0.1:8000/docs` for the auto-generated Swagger UI.
