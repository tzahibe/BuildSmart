# Feature Specification: Project Creation (Basic Intake)

**Feature Branch**: `001-project-creation`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Feature 01 — Project Creation (מתוך docs/AI_Home_Planner_SPEC.md, סעיף 4). משתמש שרוצה לבנות בית פותח פרויקט חדש ומזין כתובת/מגרש, גודל מגרש במ"ר, ותיאור חופשי של הבית הרצוי. יש ליצור project_id, לשמור את הדרישות הגולמיות ואת הטקסט המקורי ללא שינוי, להחזיק status לפרויקט, ולאפשר טעינה ועדכון של פרויקט קיים. לא כולל parsing ל-structured requirements, location resolution, RAG או compliance — אלה features עתידיים נפרדים."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a new project (Priority: P1)

A person who wants to build a house opens a new project and submits the basic request details: a city, a street, the plot size in square meters, and a free-text description of the desired house.

**Why this priority**: This is the entry point for the entire system — no other feature can run without a project and its stored requirements existing first.

**Independent Test**: Can be fully tested by submitting a valid city, street, plot area, and description, and verifying a project is created and a project_id is returned.

**Acceptance Scenarios**:

1. **Given** a person has a city, a street, a plot area, and a description of the house they want, **When** they submit these as a new project, **Then** the system creates the project, assigns it a unique project_id and a status, and returns them to the user.
2. **Given** a person submits a new project with all required fields, **When** the project is created, **Then** the description is stored exactly as typed, with no reinterpretation or reformatting.
3. **Given** a person omits the city or street, leaves the description empty, or enters a plot area that is zero or negative, **When** they submit the project, **Then** the system rejects the submission with a clear error and does not create a project.

---

### User Story 2 - Load an existing project (Priority: P2)

A person returns to a project they created earlier and wants to see everything they submitted.

**Why this priority**: Without retrieval, the stored data is write-only and no downstream feature (parsing, location resolution, design, etc.) can build on it.

**Independent Test**: Can be fully tested by creating a project, then requesting it by its project_id and verifying every originally submitted field is returned unchanged.

**Acceptance Scenarios**:

1. **Given** a project was previously created, **When** it is requested by its project_id, **Then** the system returns the city, street, plot area, original description, status, and project_id exactly as stored.
2. **Given** a project_id that does not correspond to any existing project, **When** it is requested, **Then** the system returns a clear "not found" error instead of partial or default data.

---

### User Story 3 - Update an existing project's requirements (Priority: P3)

A person realizes they made a mistake or changed their mind about part of their request (e.g., the plot area or the description) and wants to correct it.

**Why this priority**: Useful for fixing input mistakes early on, but the system is still usable end-to-end (create + load) without it, so it's lower priority than Stories 1 and 2.

**Independent Test**: Can be fully tested by creating a project, submitting an update to one or more fields, and verifying a subsequent load reflects the new values while untouched fields remain the same.

**Acceptance Scenarios**:

1. **Given** an existing project, **When** the user submits new values for one or more of city, street, plot area, or description, **Then** those fields are updated and any fields not included in the update remain unchanged.
2. **Given** an update is submitted with an invalid value (e.g., a negative plot area), **When** the system processes it, **Then** the update is rejected with a clear error and the project's stored data remains unchanged.
3. **Given** a project_id that does not exist, **When** an update is submitted for it, **Then** the system returns a clear "not found" error.

### Edge Cases

- What happens when the description field is extremely long (e.g., several thousand characters)? It must still be stored verbatim without truncation.
- What happens when plot_area_m2 is provided as a non-numeric value? The submission must be rejected with a clear error.
- What happens when the same project is updated twice in quick succession? The final stored state must reflect the last successfully applied update.
- What happens when a project is requested immediately after creation, before any update? The returned data must exactly match what was submitted at creation time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a user to create a new project by submitting a city, a street, a plot area (in square meters), and a free-text description.
- **FR-002**: System MUST generate a unique project_id for every project it creates.
- **FR-003**: System MUST persist the submitted city, street, plot area, and description exactly as provided, without modification, reformatting, or interpretation.
- **FR-004**: System MUST retain the original free-text description as the authoritative source text, unchanged, for use by future features (e.g., requirement parsing).
- **FR-005**: System MUST assign a status to every project at creation time.
- **FR-006**: System MUST allow a user to retrieve a previously created project by its project_id, returning all stored fields.
- **FR-007**: System MUST return a clear "not found" error when a requested or updated project_id does not correspond to an existing project.
- **FR-008**: System MUST allow a user to update the city, street, plot area, built area, and/or description of an existing project, leaving any fields not included in the update unchanged.
- **FR-009**: System MUST validate, on both creation and update, that the city, street, and description are non-empty and the plot area is a positive number, rejecting any submission that fails validation with a clear error and making no partial changes.
- **FR-014**: System MUST require a built area (the size of the house the user wants to build on the plot) at creation time, as a positive number strictly smaller than the plot area, and MUST reject any creation or update that violates this — including an update to only one of the two areas that would make the resulting pair invalid against the project's existing other value (added 2026-09-03, per follow-up request; see Assumptions for why).
- **FR-011**: System MUST offer city suggestions from a list of known Israeli cities/settlements, and MUST reject any submission whose `city` does not exactly match a value from that list, with a clear error (added 2026-09-03; originally non-restrictive, tightened same day per follow-up request — see Assumptions).
- **FR-012**: System MUST offer street suggestions scoped to the currently chosen city, and the street input MUST NOT be usable until a valid city has been chosen and its street suggestions have loaded (added 2026-09-03, per follow-up request).
- **FR-013**: System MUST reject any submission whose `street` does not exactly match a value from that city's street suggestions, with a clear error — including a street that is real but belongs to a different city (added 2026-09-03, per further follow-up request; supersedes the free-text allowance originally stated in FR-012).
- **FR-010**: System MUST NOT perform any parsing of the description into structured data, location resolution, regulatory lookup, or compliance checking as part of this feature — those are handled by separate, later features.

### Key Entities

- **Project**: Represents a single home-building request. Attributes: project_id (unique identifier), city, street, plot_area_m2, built_area_m2 (strictly smaller than plot_area_m2 — added 2026-09-03, FR-014), description (verbatim source text), status, created timestamp, last-updated timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can submit a new project and receive a project_id back in under 5 seconds.
- **SC-002**: 100% of successfully created projects, when retrieved, return the city, street, plot area, and description exactly as originally submitted.
- **SC-003**: 100% of submissions with a missing city, missing street, empty description, or non-positive plot area are rejected with a clear error, and no project is created or altered as a result.
- **SC-004**: A user can update one field of an existing project and see that change reflected immediately on the next retrieval, with all other fields unchanged.
- **SC-005**: A user requesting a nonexistent project_id receives a clear "not found" response 100% of the time, rather than an unclear error or partial data.

## Assumptions

- No user authentication or authorization is included in this initial slice — any project is accessible by its project_id. This matches the single-location, single-user MVP scope described in the source specification; multi-user access control can be added later if needed.
- No history of prior values is kept when a project is updated in this feature — the update simply overwrites the affected fields. Change history (e.g., for "what-if" comparisons) belongs to a later, separate feature.
- Parsing the free-text description into structured requirements (floors, bedrooms, pool, etc.) is explicitly out of scope for this feature and is deferred to a separate future feature.
- Location resolution, regulatory document retrieval, and compliance checking are explicitly out of scope for this feature and are deferred to separate future features.
- **(2026-09-03 amendments)** The single `address` field was split into `city` + `street`. City autocomplete/validation was backed first by a ~229-entry Wikipedia-sourced list (suggestion-only, then tightened to a whitelist per FR-011), then — per a follow-up request for city-scoped street suggestions (FR-012) — switched entirely to a 1,314-city snapshot of an official data.gov.il address registry (`backend/app/localities/streets_by_city.json`), which also supplies the 63,575-street `GET /localities/{city}/streets` data. A final follow-up request (FR-013) tightened `street` itself to require an exact match within the chosen city's list, checked via a cross-field validator on `ProjectCreate` (and on `ProjectUpdate` only when both fields are supplied together — see research.md for that gap). Using one official source for both city and street guarantees every listed city has matching, consistent street data. A real locality outside this snapshot currently cannot be entered as `city`, and by extension its streets can't be entered either; this trade-off was made explicitly and knowingly — see research.md for the full reasoning and how to refresh the snapshot.
- **(2026-09-03, well after initial ship)** `built_area_m2` (FR-014) was added after observing that a project could be created with a perfectly valid `plot_area_m2` but a `description` carrying no real information (e.g. random characters) — since `description` is deliberately free text with no semantic validation (see the note below), such a project would previously have had *no* reliable numeric planning data beyond the plot size itself. Requiring a validated `built_area_m2` at creation time guarantees every project has real size/footprint data regardless of what `description` contains — description's semantic quality remains intentionally unvalidated (see below), but it no longer needs to be trustworthy for the system to have basic planning inputs. This also relates to Feature 02: see that feature's research.md for how its own (LLM-parsed, un-validated-against-this-field) `target_built_area_m2` now overlaps with this structured field.
- `description`'s *content* is still never validated for meaningfulness (only non-emptiness, per FR-009) — this was a deliberate decision, not an oversight: defining "meaningful" reliably would itself require an LLM call on every submission (cost/latency for a soft, disputable judgment), and the source specification's "smallest working version" principle argues against gatekeeping input this aggressively. `built_area_m2` (above) addresses the actual downstream risk (no usable planning data) directly and deterministically, which is a better fix than trying to police free text.
