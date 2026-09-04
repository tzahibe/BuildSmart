# API Contract: Requirements

Base path: `/projects/{project_id}/requirements` (mounted on the existing FastAPI app in
`backend/app/main.py`; nested under a project from Feature 01).

> **2026-09-03, later the same day — amendment**: this used to be a resource with its own `GET` endpoint
> and response shape (`StructuredRequirements`). It now has a single endpoint — `POST` — that parses and
> merges its result directly into Feature 01's `Project`, and returns that `Project`. To retrieve
> previously parsed data, use Feature 01's `GET /projects/{project_id}`
> (`specs/001-project-creation/contracts/projects-api.md`) — the same fields are already there. See
> research.md for why.

## POST /projects/{project_id}/requirements

Parse (or re-parse) the project's current `description` into structured requirements, merging the result
into the project itself and replacing any previously merged values (User Stories 1 & 3).

**Request body**: none.

**Responses**:

- `200 OK` → `Project` (Feature 01's full shape — see
  `specs/001-project-creation/contracts/projects-api.md`), with `floors`, `bedrooms`, `safe_room`,
  `parking_spaces`, `pool`, and `requirements_parsed_at` freshly set. `updated_at` is unchanged by this
  call.
- `404 Not Found` → `{"detail": "Project not found"}` when `project_id` does not exist.

A tagged field is `{"value": <type> | null, "source": "requested" | "inferred" | "unknown"}`.

```json
{
  "project_id": "uuid-string",
  "city": "string",
  "street": "string",
  "plot_area_m2": 500.0,
  "built_area_m2": 220.0,
  "description": "אני רוצה בית בן קומתיים בשטח 220 מ\"ר, 4 חדרי שינה, ממ\"ד, חניה ל-2 עם בריכה 8 על 4 בחצר האחורית",
  "status": "created",
  "created_at": "2026-09-03T12:00:00Z",
  "updated_at": "2026-09-03T12:00:00Z",
  "floors": { "value": 2, "source": "requested" },
  "bedrooms": { "value": 4, "source": "requested" },
  "safe_room": { "value": true, "source": "requested" },
  "parking_spaces": { "value": 2, "source": "requested" },
  "pool": {
    "requested": { "value": true, "source": "requested" },
    "length_m": { "value": 8.0, "source": "requested" },
    "width_m": { "value": 4.0, "source": "requested" }
  },
  "requirements_parsed_at": "2026-09-03T12:00:05Z"
}
```

Note there is no `target_built_area_m2` here — `built_area_m2` above (Feature 01, structured, validated)
is the single source of truth for built area; this endpoint never extracts or reports one (FR-012).

### Before any parse

`GET /projects/{project_id}` (Feature 01) on a project that has never had `POST
.../requirements` called returns the same shape with `floors`, `bedrooms`, `safe_room`, `parking_spaces`,
`pool`, and `requirements_parsed_at` all `null` — not an error, and not fabricated placeholder values.
There is no dedicated "not yet parsed" endpoint or error; `null` *is* the "not yet parsed" signal (FR-009).
