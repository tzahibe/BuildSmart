# Quickstart: Project Creation (Basic Intake)

Validates the feature end-to-end via the running backend, per the acceptance scenarios in `spec.md`.

## Prerequisites

- Python 3.11+, with `backend/.venv` set up (`uv sync` from `backend/` if dependencies changed).
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

Expected: all tests in `tests/test_projects.py` pass, covering create/get/update happy paths and the
validation + not-found edge cases from `spec.md`.

## Manual validation (matches spec.md acceptance scenarios)

1. **Create a project** (User Story 1, Scenario 1 & 2):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 500, "description": "בית בן קומתיים 220 מ\"ר, 4 חדרי שינה"}'
   ```

   (`street` must be a real street for the chosen `city` — check `GET
   /localities/{city}/streets` first if trying a different city than this example.)

   Expected: `201`, a JSON body with a generated `project_id`, `status: "created"`, and `description`
   returned byte-for-byte identical to what was sent.

2. **Reject an invalid submission** (User Story 1, Scenario 3):

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "", "street": "", "plot_area_m2": -10, "description": ""}'
   ```

   Expected: `422`, and a subsequent list/count of projects shows nothing was created.

3. **Load an existing project** (User Story 2):

   ```bash
   curl -s http://127.0.0.1:8000/projects/<project_id from step 1>
   ```

   Expected: `200`, all fields match what was submitted in step 1 exactly.

4. **Load a nonexistent project** (User Story 2, Scenario 2):

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/projects/00000000-0000-0000-0000-000000000000
   ```

   Expected: `404`.

5. **Update a project** (User Story 3):

   ```bash
   curl -s -X PATCH http://127.0.0.1:8000/projects/<project_id from step 1> \
     -H "Content-Type: application/json" \
     -d '{"plot_area_m2": 250}'
   ```

   Expected: `200`, `plot_area_m2` is now `250`, `city`/`street`/`description` are unchanged from step 1.

6. **City must come from the localities list**:

   ```bash
   curl -s http://127.0.0.1:8000/localities | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"
   ```

   Expected: a number > 100 (step 1 already used a city from this list). Now try a city that is not in
   it:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "עיר בדויה", "street": "רחוב כלשהו", "plot_area_m2": 100, "description": "בדיקה"}'
   ```

   Expected: `422` — `city` must exactly match a value from `GET /localities` (see research.md for why).

7. **Street suggestions are scoped to a city**:

   ```bash
   curl -s "http://127.0.0.1:8000/localities/מודיעין-מכבים-רעות/streets" \
     | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"
   ```

   Expected: a number > 0 (streets known for that city). Now try an unrecognized city:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/localities/עיר%20בדויה/streets"
   ```

   Expected: `404`. This list also powers the frontend's autocomplete and gating (the street field stays
   disabled until a valid city's streets have loaded).

8. **Street must belong to the chosen city**:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "רחוב שלא קיים בעיר הזו", "plot_area_m2": 100, "description": "בדיקה"}'
   ```

   Expected: `422`. Now try a street that is real, but for a *different* city than the one submitted
   (e.g. reuse step 1's `"אגוז מכבים רעות"` with `"city": "ירושלים"`) — also expected: `422`.

## Interactive exploration

With the server running, open `http://127.0.0.1:8000/docs` for the auto-generated Swagger UI covering all
endpoints — useful for ad-hoc testing without `curl`.
