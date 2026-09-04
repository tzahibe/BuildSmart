# Phase 1 Data Model: Natural Language Requirement Parser

> **2026-09-03 major amendment**: this feature no longer owns an entity. Its output merges directly into
> Feature 01's `Project` — see `specs/001-project-creation/data-model.md`'s "Merged-in planning fields"
> section for the authoritative field-by-field shape. This file now describes the *extraction* shape (what
> the parser produces before it's merged in) rather than a stored entity.

## Shared shape: `SourceTag`

An enum with exactly three values: `requested`, `inferred`, `unknown` (per spec.md FR-003). Defined in
`backend/app/projects/models.py` (moved there 2026-09-03 so `Project` can reference it directly). Used by
every tagged field below.

## Shared shape: tagged field

Every extracted field is `{value, source}`:

| Field | Type | Notes |
|---|---|---|
| `value` | type-specific (see below), nullable | `null` whenever `source == "unknown"` (FR-004) |
| `source` | `SourceTag` | `requested` / `inferred` / `unknown` |

Three concrete instantiations are used (also in `app/projects/models.py`): an integer-valued tagged field
(`floors`, `bedrooms`, `parking_spaces`), a float-valued one (the pool's `length_m`/`width_m`), and a
boolean-valued one (`safe_room`, and the pool's `requested`). There is deliberately no float-valued
top-level field anymore — built area was the only one, and it's gone (FR-012).

## Parser output: `RequirementExtraction`

The shape `RequirementParser.parse(description: str)` returns (`backend/app/requirements/parser.py`) —
purely the fields this feature is responsible for, with no project identity or timestamps attached:

| Field | Type | Notes |
|---|---|---|
| `floors` | tagged int field | FR-002, FR-011. Defaults to `{value: 1, source: "inferred"}` when the text doesn't state a floor count — see Floors default below. `unknown` only in the rare case of a stated conflict (spec.md Edge Cases) |
| `bedrooms` | tagged int field | FR-002 |
| `safe_room` | tagged bool field | FR-002 |
| `parking_spaces` | tagged int field | FR-002 |
| `pool` | object: `{requested: tagged bool field, length_m: tagged float field, width_m: tagged float field}` | FR-002. `length_m`/`width_m` are meaningful only when `pool.requested.value` is `true`; when the pool itself is `unknown` or `false`, dimensions are `unknown` too (never independently `requested`/`inferred`) |

**Not included**: `target_built_area_m2` — removed per FR-012; `Project.built_area_m2` (Feature 01) is the
single source of truth for built area, so the parser is explicitly instructed (see
`backend/app/requirements/parser.py`'s system prompt) not to extract or report one.

## Floors default (FR-011)

Unlike every other field, `floors` never has a "true" `unknown` state for the common case of simply not
being mentioned — it defaults to `{value: 1, source: "inferred"}`. The one exception where `floors` can
still be `unknown` is a *stated conflict* (e.g., "2 floors" in one sentence and "3 floors" in another) —
that's not the same as "unstated," so the default does not apply there (spec.md Edge Cases). This default
is applied by the model itself, via prompt instructions — not a post-processing step — see research.md for
why.

## How extraction becomes part of `Project`

`POST /projects/{project_id}/requirements` (`backend/app/requirements/router.py`):

1. Loads the `Project` via Feature 01's repository; `404` if it doesn't exist (FR-008).
2. Calls `RequirementParser.parse(project.description)` → a `RequirementExtraction`.
3. Calls `ProjectRepository.set_parsed_requirements(project_id, floors=..., bedrooms=..., safe_room=...,
   parking_spaces=..., pool=...)` (Feature 01's repository, extended for this — see that feature's
   data-model.md) — merges the five fields into the stored `Project`, sets `requirements_parsed_at` to
   now, and explicitly does **not** touch `updated_at` (that tracks the user's own structured edits, not
   derived data).
4. Returns the updated `Project` (not a separate resource).

### Validation rules

- Every one of the 5 tagged fields (`floors`, `bedrooms`, `safe_room`, `parking_spaces`, `pool.requested`)
  MUST be present with a `source` of exactly one of the three `SourceTag` values (FR-003) whenever a parse
  has happened — there is no "field omitted entirely" state within a parse result; an unknown field is
  still present, just with `value: null, source: "unknown"`. Before any parse, all five are `null` at the
  `Project` level instead (see Feature 01's data-model.md) — a different, coarser "never even tried" state.
- `value` MUST be `null` whenever `source` is `unknown` (FR-004); a non-null `value` MUST have `source`
  `requested` or `inferred`.
- `pool.length_m`/`pool.width_m` follow the same rule independently, but are only ever non-`unknown` when
  `pool.requested.value` is `true` (see Edge Cases in spec.md — a pool that isn't requested has no
  meaningful dimensions to extract).

### Update semantics (User Story 3 / FR-006)

- Every `POST` fully replaces all 5 fields plus `requirements_parsed_at` — there is no partial re-parse.
- No history is kept of previous parses (per spec.md Assumptions) — a re-parse overwrites in place.
- `updated_at` (Feature 01's own field, tracking structured edits) is never touched by a parse — only
  `requirements_parsed_at` is.

## Request/Response Shapes

These map directly to the contract in `contracts/requirements-api.md`.

- **Parse request**: none — `POST /projects/{project_id}/requirements` takes no body; it reads the
  project's current `description` server-side (FR-007).
- **Response**: the full, updated `Project` (Feature 01's shape) — not a feature-specific shape.
