# API Contract: Design

Base path: `/projects/{project_id}/design` (mounted on the existing FastAPI app in `backend/app/main.py`;
nested under a project from Feature 01, same shape-of-response pattern as Feature 02).

## POST /projects/{project_id}/design

Generate (or regenerate) a deterministic parametric design model for the project, merging the result
directly into the project itself (User Stories 1 & 3).

**Request body**: none.

**Responses**:

- `200 OK` → `Project` (Feature 01's full shape — see
  `specs/001-project-creation/contracts/projects-api.md`), with `site_width_m`, `site_depth_m`, `rooms`,
  `design_notes`, and `design_generated_at` freshly set. `updated_at` and `requirements_parsed_at` are
  unchanged by this call.
- `404 Not Found` → `{"detail": "Project not found"}` when `project_id` does not exist.
- `422 Unprocessable Entity` → `{"detail": "Project has not been parsed yet — call POST
  /projects/{project_id}/requirements first"}` when the project exists but has never been parsed
  (`requirements_parsed_at is None`) (FR-002).
- `422 Unprocessable Entity` → `{"detail": "Built area per floor is too small to fit the required rooms"}`
  when the fixed-size rooms don't fit a floor's available area (FR-012).

```json
{
  "project_id": "uuid-string",
  "city": "string",
  "street": "string",
  "plot_area_m2": 500.0,
  "built_area_m2": 220.0,
  "description": "...",
  "status": "created",
  "created_at": "2026-09-03T12:00:00Z",
  "updated_at": "2026-09-03T12:00:00Z",
  "floors": { "value": 2, "source": "requested" },
  "bedrooms": { "value": 4, "source": "requested" },
  "safe_room": { "value": true, "source": "requested" },
  "parking_spaces": { "value": 2, "source": "requested" },
  "pool": { "requested": { "value": true, "source": "requested" }, "length_m": { "value": 8.0, "source": "requested" }, "width_m": { "value": 4.0, "source": "requested" } },
  "requirements_parsed_at": "2026-09-03T12:00:05Z",
  "site_width_m": 22.36,
  "site_depth_m": 22.36,
  "rooms": [
    { "type": "kitchen", "floor": 1, "area_m2": 12.0, "x": 0.0, "y": 0.0, "width_m": 3.46, "depth_m": 3.46 },
    { "type": "bathroom", "floor": 1, "area_m2": 5.0, "x": 3.46, "y": 0.0, "width_m": 1.44, "depth_m": 3.46 },
    { "type": "living_room", "floor": 1, "area_m2": 93.0, "x": 4.9, "y": 0.0, "width_m": 26.88, "depth_m": 3.46 },
    { "type": "bedroom", "floor": 2, "area_m2": 27.5, "x": 0.0, "y": 0.0, "width_m": 7.95, "depth_m": 3.46 },
    { "type": "bedroom", "floor": 2, "area_m2": 27.5, "x": 7.95, "y": 0.0, "width_m": 7.95, "depth_m": 3.46 }
  ],
  "design_notes": [],
  "design_generated_at": "2026-09-03T12:00:10Z"
}
```

*(Numbers above are illustrative, not a worked example matching every other field's values in this
document exactly.)*

### Before any generation

`GET /projects/{project_id}` (Feature 01) on a project that has never had `POST .../design` called returns
`site_width_m`/`site_depth_m`/`rooms`/`design_notes`/`design_generated_at` all `null` — not an error, and
not fabricated placeholder geometry (User Story 2, Scenario 2).

### When input was incomplete

If `bedrooms` or `safe_room` was `unknown` at generation time, `design_notes` is a non-empty list of
human-readable Hebrew sentences explaining what was omitted and why, e.g.:

```json
"design_notes": ["מספר חדרי השינה לא ידוע — לא נכללו חדרי שינה בפריסה."]
```
