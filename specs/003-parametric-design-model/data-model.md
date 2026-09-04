# Phase 1 Data Model: Parametric Design Model

No new entity — this feature adds fields to Feature 01's `Project` (per spec.md Key Entities and
research.md's merge decision).

## Shared shape: `Room`

| Field | Type | Notes |
|---|---|---|
| `type` | string | One of `"living_room"`, `"kitchen"`, `"bathroom"`, `"safe_room"`, `"bedroom"` (FR-006) |
| `floor` | int | 1-indexed; 1 = ground floor |
| `area_m2` | float | Computed per research.md's sizing rules |
| `x` | float | Meters, relative to this room's own floor's origin `(0, 0)` — not the full site (research.md) |
| `y` | float | Always `0` in this MVP's 1D row layout |
| `width_m` | float | `area_m2 / floor_depth_m` |
| `depth_m` | float | Equal to the floor's own assumed depth (every room on a floor spans the same depth) |

## New `Project` fields (added to `backend/app/projects/models.py`)

| Field | Type | Notes |
|---|---|---|
| `site_width_m` | float, nullable | `null` until first generated. `sqrt(plot_area_m2)` (FR-004, square-plot assumption) |
| `site_depth_m` | float, nullable | Same value as `site_width_m` (square assumption) — kept as a separate field rather than reusing `site_width_m` twice so a future non-square model is a non-breaking change |
| `rooms` | list of `Room`, nullable | `null` until first generated (User Story 2, Scenario 2) — never an empty-list placeholder for "not generated" |
| `design_notes` | list of string, nullable | `null` until first generated; `[]` (empty) once generated with nothing omitted; otherwise sentences recording which fields were `unknown` and excluded (FR-007/FR-008) |
| `design_generated_at` | datetime (UTC), nullable | `null` until first generated; refreshed on every regeneration |

`design_generated_at` mirrors `requirements_parsed_at`'s role from Feature 02: a `null` value is the
"never generated" signal, distinct from a "generated but the input was incomplete" state (which shows up
in `design_notes` instead). Generation never touches `updated_at` (user's own structured edits) or
`requirements_parsed_at` (Feature 02's own timestamp) — three independent timestamps, each tracking a
different kind of change.

## Generation algorithm (pure function `generate_design(project: Project) -> GeneratedDesign`)

Preconditions (checked by the router before calling this, per FR-002/FR-008):
- `project.requirements_parsed_at is not None` — else `422`/`404`-style error, no generation (FR-002).

Steps:
1. `site_width_m = site_depth_m = sqrt(project.plot_area_m2)` (FR-004).
2. `floors = project.floors.value` (always present after Feature 02's own FR-011 default — never `null`
   in practice, but the code still guards against it per FR-002's broader precondition).
3. `floor_area = project.built_area_m2 / floors` (FR-005), and `floor_depth_m = sqrt(floor_area)` (the
   per-floor footprint's own square-assumption, independent of the site's).
4. For the ground floor (floor 1): reserve `kitchen (12 m²)` + `bathroom (5 m²)`, plus `safe_room (9 m²)`
   only if `project.safe_room is not None and project.safe_room.source != "unknown" and
   project.safe_room.value is True`. If these reserved rooms alone exceed `floor_area`, raise a clear
   error (FR-012) — generate nothing.
5. Determine ground-floor "occupants" of the remaining area: the living room (always), plus every bedroom
   when `floors == 1` (see step 6 for `floors > 1`). Split the remainder evenly among them.
6. If `floors > 1`: bedrooms are distributed across floors `2..floors`, split as evenly as possible
   (earlier upper floors get any remainder). Each upper floor's entire `floor_area` is split evenly among
   its assigned bedrooms (no fixed rooms reserved on upper floors, per FR-006).
7. Bedroom count comes from `project.bedrooms.value` when `project.bedrooms.source != "unknown"`;
   otherwise **zero** bedrooms are generated, and a note is appended to `design_notes` recording that
   (FR-007). Same pattern for `safe_room` (FR-008) — reflected in step 4's condition already.
8. Lay out each floor's rooms in a single row: iterate the floor's room list in a fixed order (kitchen,
   bathroom, safe room, living room, then bedrooms in order), accumulating `x` by each prior room's
   `width_m`; every room's `depth_m = floor_depth_m` and `width_m = area_m2 / floor_depth_m`.

### Validation rules

- `design_notes` entries are only ever added for `bedrooms`/`safe_room` being `unknown` — every other
  omission this feature could theoretically hit (e.g. `floors` unknown) is already precluded by Feature
  02's own FR-011 default, so no note type exists for it.
- A floor with zero occupants after fixed-room reservation (e.g. `floors > 1`, an upper floor assigned
  zero bedrooms because `bedrooms` was `unknown`) simply has no rooms on it — not an error, just an empty
  floor in `rooms` (no entries with that `floor` number).

## Request/Response Shapes

Maps to `contracts/design-api.md`.

- **Generate request**: none — `POST /projects/{project_id}/design` takes no body; it reads the project's
  current parsed/structured fields server-side.
- **Response**: the full, updated `Project` (Feature 01's shape, now including the fields above) — same
  pattern as Feature 02's `POST /projects/{project_id}/requirements`.
