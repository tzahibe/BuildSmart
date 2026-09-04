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
| `built_area_m2` | number (float) | yes | strictly greater than 0, and strictly less than `plot_area_m2` | Added 2026-09-03, FR-014 — desired built house size on the plot |
| `description` | string | yes | non-empty after trimming | Stored verbatim as the authoritative source text (FR-003, FR-004) — never reformatted or parsed in this feature (FR-010) |
| `status` | string | generated | fixed value `"created"` in this feature | Placeholder for a real status lifecycle once later features (parsing, compliance, etc.) exist (FR-005) |
| `created_at` | datetime (UTC) | generated | n/a | Set once at creation |
| `updated_at` | datetime (UTC) | generated | n/a | Set at creation, refreshed on every successful update. **Not** touched by parsing (below) |
| `floors` | tagged int, nullable | generated | n/a | Added 2026-09-03 — see "Merged-in planning fields" below |
| `bedrooms` | tagged int, nullable | generated | n/a | See below |
| `safe_room` | tagged bool, nullable | generated | n/a | See below |
| `parking_spaces` | tagged int, nullable | generated | n/a | See below |
| `pool` | object, nullable | generated | n/a | `{requested, length_m, width_m}`, each a tagged field — see below |
| `requirements_parsed_at` | datetime (UTC), nullable | generated | n/a | `null` until first parsed; refreshed on every re-parse |

### Merged-in planning fields (2026-09-03, per follow-up request)

Feature 02 (`specs/002-requirement-parser/`) originally stored its parsed output in a separate
`StructuredRequirements` entity, linked by `project_id`. Per explicit request — "`Project` should contain
everything needed to eventually produce a sketch" — that entity was **merged directly into `Project`**:
`floors`, `bedrooms`, `safe_room`, `parking_spaces`, `pool` now live here, each a tagged field
(`{value, source}`, `source` ∈ `requested`/`inferred`/`unknown` — see Feature 02's data-model.md for the
full shape and semantics, unchanged by the move). They default to `null` on a newly created project — that
`null` means "never parsed yet", distinct from a tagged field whose `source` is `"unknown"` (parsed, but
the text didn't say). `requirements_parsed_at` is `null` until `POST /projects/{project_id}/requirements`
(Feature 02) runs at least once, then tracks the most recent parse. Parsing never touches `updated_at` —
that field tracks the user's own structured edits (this feature), not derived data.

One field was deliberately **not** carried over: Feature 02's original `target_built_area_m2` (parsed from
free text) is gone — `built_area_m2` above (FR-014, structured and validated) is now the single source of
truth for built area, so re-deriving the same fact from free text would just create a second,
unreconciled value for the same thing. See Feature 02's research.md for the full reasoning and this
feature's research.md for the earlier note about the overlap this move resolves.

### Validation rules (from FR-009)

- `city`: required, non-empty string, and **must exactly match** one of the values in `GET /localities`
  (`backend/app/localities/data.py`, loaded from `streets_by_city.json` — a snapshot of an official
  data.gov.il address registry, 1,314 cities/settlements). A real locality outside this snapshot currently
  cannot be entered — a deliberate, explicitly requested trade for guaranteed-clean, consistent city data;
  see research.md for the full reasoning and refresh instructions.
- `street`: required, non-empty string, and **must exactly match** one of the streets for the effective
  `city` in `CITY_STREETS` (same snapshot as `city`, via `GET /localities/{city}/streets`) — a street real
  in a different city is rejected too. On `ProjectCreate` this is checked directly by a schema-level
  `model_validator`. On `ProjectUpdate`, the schema only cross-checks when **both** `city` and `street`
  are provided together (it has no access to the project's stored values); the `PATCH` route (T013)
  additionally re-checks the *merged* pair — existing stored values overlaid with whatever the update
  provides — before saving, so a street-only or city-only update can't leave the two inconsistent. See
  research.md for the full reasoning.
- `description`: required, non-empty string. No length cap enforced in this feature (edge case in spec.md:
  very long descriptions must still be stored verbatim).
- `plot_area_m2`: required, numeric, `> 0`. Non-numeric input is rejected at the schema level (FastAPI/
  Pydantic type validation) before reaching business logic.
- `built_area_m2`: required, numeric, `> 0`, and **strictly less than** `plot_area_m2` (equal is rejected,
  not just greater). On `ProjectCreate` this is a schema-level `model_validator`. On `ProjectUpdate`, same
  gap/mitigation pattern as `street`/`city` above: the schema only cross-checks when both fields are
  supplied together; the `PATCH` route re-checks the merged pair (existing values overlaid with the
  update) so a plot-only or built-area-only update can't leave the pair invalid.

### State / lifecycle

Single state for this feature: every project is created with `status = "created"` and stays there — no
transitions are defined yet (compliance/design status values belong to later features, per FR-010 and the
Assumptions in spec.md). Updates only ever touch `city`, `street`, `plot_area_m2`, `built_area_m2`,
`description`, and `updated_at`; they never change `project_id`, `status`, or `created_at`.

### Update semantics (User Story 3 / FR-008)

- Partial update: only the fields present in the update request are changed.
- No history is kept of previous values (per spec.md Assumptions) — an update overwrites in place.
- The same validation rules apply to updated fields as to creation; an invalid update is rejected in full
  (no partial application) and the stored project is left unchanged (spec.md edge case).

## Request/Response Shapes

These map directly to the contract in `contracts/projects-api.md`.

- **ProjectCreate** (request): `city`, `street`, `plot_area_m2`, `built_area_m2`, `description`.
- **ProjectUpdate** (request): `city?`, `street?`, `plot_area_m2?`, `built_area_m2?`, `description?` — all
  optional, at least conceptually "one of" should be provided, but an empty update is harmless (no-op)
  rather than an error.
- **Project** (response): all fields in the table above.
