# API Contract: Projects

Base path: `/projects` (mounted on the existing FastAPI app in `backend/app/main.py`).

> **2026-09-03 amendments**: the original single `address` field was split into `city` + `street`, with
> `GET /localities` and `GET /localities/{city}/streets` added to power cascading city→street autocomplete
> (see below and research.md). `city` was initially free text, then tightened to a strict whitelist against
> `GET /localities`; that list's source then moved from a Wikipedia scrape to an official government
> address registry (the same one `GET /localities/{city}/streets` now serves from); finally `street` was
> also tightened to require an exact match within the chosen `city`'s street list. See research.md for the
> full decision trail.

## POST /projects

Create a new project (User Story 1).

**Request body**:

```json
{
  "city": "string, required — must exactly match one of the values from GET /localities",
  "street": "string, required — must exactly match one of the values from GET /localities/{city}/streets for the submitted city",
  "plot_area_m2": "number, required, > 0",
  "description": "string, required, non-empty"
}
```

**Responses**:

- `201 Created` → `Project` (see below), including the generated `project_id` and `status`.
- `422 Unprocessable Entity` → validation error (missing/empty `street` or `description`, `city` not in
  the `GET /localities` list, `street` not in `city`'s street list — including a street that's real but
  belongs to a *different* city, non-positive or non-numeric `plot_area_m2`). The city/street pairing
  error is a cross-field (`model_validator`) error, so its `loc` is `["body"]` rather than a specific
  field — see research.md. No project is created.

## GET /projects/{project_id}

Retrieve a previously created project (User Story 2).

**Responses**:

- `200 OK` → `Project`, exactly as stored.
- `404 Not Found` → `{"detail": "Project not found"}` when `project_id` does not exist.

## PATCH /projects/{project_id}

Partially update an existing project (User Story 3).

**Request body** (all fields optional; only provided fields are changed):

```json
{
  "city": "string, optional — if provided, must exactly match one of the values from GET /localities",
  "street": "string, optional, non-empty if provided; if BOTH city and street are provided together, street must belong to that city (see research.md for the street-only/city-only gap)",
  "plot_area_m2": "number, optional, > 0 if provided",
  "description": "string, optional, non-empty if provided"
}
```

**Responses**:

- `200 OK` → `Project`, reflecting the merged/updated state.
- `404 Not Found` → `{"detail": "Project not found"}` when `project_id` does not exist. No changes applied.
- `422 Unprocessable Entity` → validation error on any provided field. No changes applied (all-or-nothing).

## Shared response shape: `Project`

```json
{
  "project_id": "uuid-string",
  "city": "string",
  "street": "string",
  "plot_area_m2": 220.0,
  "description": "string, verbatim as submitted",
  "status": "created",
  "created_at": "2026-09-03T12:00:00Z",
  "updated_at": "2026-09-03T12:00:00Z"
}
```

## GET /localities

City whitelist + autocomplete source. Not tied to a specific user story — supports the `city` field above.

**Responses**:

- `200 OK` → `string[]`, sorted list of 1,314 Israeli city/settlement names. Sourced from a data.gov.il
  official address registry snapshot (see `backend/app/localities/data.py` and `streets_by_city.json`) —
  real, official data, but a static, possibly-stale snapshot (source updates weekly; see research.md for
  refresh instructions). `POST`/`PATCH /projects` reject any `city` not exactly matching an entry here —
  see research.md for the tradeoff this accepts (a genuine locality missing from the snapshot currently
  cannot be entered) and why it was chosen anyway.

## GET /localities/{city}/streets

Street suggestion list for a specific, already-chosen city — supports the `street` field, and is what
gates it open on the frontend (street stays disabled until this returns successfully for a city).

**Responses**:

- `200 OK` → `string[]`, sorted list of street names known for `city` in the same address-registry
  snapshot as `GET /localities` (so any `city` from that list is guaranteed to have a — possibly small,
  never missing — entry here).
- `404 Not Found` → `{"detail": "City not recognized"}` when `city` is not an exact match in the
  snapshot (e.g. a typo, or a value from before the whitelist was introduced).

`POST`/`PATCH /projects` reject any `street` not exactly matching an entry in the submitted city's list
here (see data-model.md and research.md).
