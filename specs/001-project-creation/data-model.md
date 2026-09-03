# Phase 1 Data Model: Project Creation (Basic Intake)

## Entity: Project

Represents a single home-building request submitted by a user (per `spec.md` Key Entities).

> **2026-09-03 amendments**: `address` was split into `city` + `street`, with `GET /localities` and `GET
> /localities/{city}/streets` (see contracts/projects-api.md) added to power cascading city→street
> autocomplete on the frontend. `city` was initially free text (suggestions only), then tightened to a
> strict whitelist; the whitelist source then moved from a Wikipedia scrape to an official government
> address registry so city+street data are consistent; finally, `street` was also tightened to require an
> exact match within the chosen city's street list. See the Validation rules below and research.md for the
> full decision trail.

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `project_id` | string (UUID) | generated | n/a — server-assigned, never client-supplied | Unique identifier, assigned at creation (FR-002) |
| `city` | string | yes | non-empty; must exactly match an entry in `GET /localities` | See Localities note below. Stored verbatim (FR-003) |
| `street` | string | yes | non-empty after trimming | Stored verbatim (FR-003) |
| `plot_area_m2` | number (float) | yes | strictly greater than 0 | Rejected with a validation error otherwise (FR-009) |
| `description` | string | yes | non-empty after trimming | Stored verbatim as the authoritative source text (FR-003, FR-004) — never reformatted or parsed in this feature (FR-010) |
| `status` | string | generated | fixed value `"created"` in this feature | Placeholder for a real status lifecycle once later features (parsing, compliance, etc.) exist (FR-005) |
| `created_at` | datetime (UTC) | generated | n/a | Set once at creation |
| `updated_at` | datetime (UTC) | generated | n/a | Set at creation, refreshed on every successful update |

### Validation rules (from FR-009)

- `city`: required, non-empty string, and **must exactly match** one of the values in `GET /localities`
  (`backend/app/localities/data.py`, loaded from `streets_by_city.json` — a snapshot of an official
  data.gov.il address registry, 1,314 cities/settlements). A real locality outside this snapshot currently
  cannot be entered — a deliberate, explicitly requested trade for guaranteed-clean, consistent city data;
  see research.md for the full reasoning and refresh instructions.
- `street`: required, non-empty string, and on `ProjectCreate` **must exactly match** one of the streets
  for the submitted `city` in `CITY_STREETS` (same snapshot as `city`, via `GET
  /localities/{city}/streets`) — a street real in a different city is rejected too. On `ProjectUpdate`
  this cross-check only runs when **both** `city` and `street` are provided in the same request; a
  street-only (or city-only) partial update cannot be checked against the pair at the schema level — see
  research.md for why, and what `PATCH` (T013) still needs to do about it.
- `description`: required, non-empty string. No length cap enforced in this feature (edge case in spec.md:
  very long descriptions must still be stored verbatim).
- `plot_area_m2`: required, numeric, `> 0`. Non-numeric input is rejected at the schema level (FastAPI/
  Pydantic type validation) before reaching business logic.

### State / lifecycle

Single state for this feature: every project is created with `status = "created"` and stays there — no
transitions are defined yet (compliance/design status values belong to later features, per FR-010 and the
Assumptions in spec.md). Updates only ever touch `city`, `street`, `plot_area_m2`, `description`, and
`updated_at`; they never change `project_id`, `status`, or `created_at`.

### Update semantics (User Story 3 / FR-008)

- Partial update: only the fields present in the update request are changed.
- No history is kept of previous values (per spec.md Assumptions) — an update overwrites in place.
- The same validation rules apply to updated fields as to creation; an invalid update is rejected in full
  (no partial application) and the stored project is left unchanged (spec.md edge case).

## Request/Response Shapes

These map directly to the contract in `contracts/projects-api.md`.

- **ProjectCreate** (request): `city`, `street`, `plot_area_m2`, `description`.
- **ProjectUpdate** (request): `city?`, `street?`, `plot_area_m2?`, `description?` — all optional, at
  least conceptually "one of" should be provided, but an empty update is harmless (no-op) rather than an
  error.
- **Project** (response): all fields in the table above.
