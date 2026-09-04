# Feature Specification: Parametric Design Model

**Feature Branch**: `003-parametric-design-model`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Feature 09 — Parametric Design Model (מתוך docs/AI_Home_Planner_SPEC.md, סעיף 12), בהמשך ל-Feature 01+02. לייצר עבור פרויקט קיים מודל תכנון פרמטרי דטרמיניסטי (לא LLM) — פריסת חדרים בסיסית על בסיס plot_area_m2, built_area_m2, floors, bedrooms, safe_room, parking_spaces, pool שכבר קיימים על ה-Project. הבסיס לסקיצה עתידית (SVG/Canvas), אך הציור עצמו הוא feature נפרד. יש למזג את המודל ישירות לתוך Project, כמו ש-Feature 02 מוזג, אלא אם יש סיבה טובה שלא. לא כולל: רינדור/ציור בפועל, location resolution, RAG, compliance אמיתי מול תקנות."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a design model for a project (Priority: P1)

A person whose project has already had its requirements parsed (Feature 02) asks the system to turn the project's numbers (plot size, built area, floor count, bedroom count, and any wanted extras) into a concrete, structured layout — how big the plot and building footprint are, and where a basic set of rooms sit on each floor.

**Why this priority**: This is the entire point of the feature — without it, the project has counts and areas but nothing spatial, and no downstream feature (drawing a floor plan, checking room-level constraints) has anything to work with.

**Independent Test**: Can be fully tested by creating and parsing a project with known floors/bedrooms/built area, requesting a design model, and verifying the returned site dimensions, floor count, and room list are internally consistent (room areas sum sensibly within each floor's footprint) and match the deterministic rules below.

**Acceptance Scenarios**:

1. **Given** a parsed project with floors=1, built_area_m2=100, bedrooms=3 (all `requested`), safe_room=true, **When** a design model is requested, **Then** the result includes site dimensions derived from the plot size, one floor containing a living room, kitchen, bathroom, safe room, and 3 bedrooms, each with a floor, an area, and a position/size, and the rooms' areas do not exceed the floor's footprint.
2. **Given** a parsed project with floors=2, **When** a design model is requested, **Then** bedrooms are placed on the upper floor(s) and the ground floor holds the shared rooms (living room, kitchen, bathroom, safe room if applicable).
3. **Given** a project that has never been parsed (Feature 02), **When** a design model is requested for it, **Then** the system returns a clear error and generates no model.
4. **Given** a parsed project whose `bedrooms` came back `unknown` (the description never mentioned bedrooms), **When** a design model is requested, **Then** the system still generates a model (living room, kitchen, bathroom, and safe room if applicable, but no bedroom rooms) and clearly records that bedroom count was unknown and excluded, rather than silently guessing a count or silently producing an incomplete-looking model with no explanation.
5. **Given** a parsed project whose built area per floor is too small to fit the fixed-size rooms (kitchen, bathroom, and safe room if applicable), **When** a design model is requested, **Then** the system returns a clear error and generates no (partial or invalid) model.

---

### User Story 2 - View a previously generated design model (Priority: P2)

A person who already generated a design model for their project wants to see it again later without regenerating it.

**Why this priority**: Regeneration is deterministic but still unnecessary work to repeat on every view; a generated model should simply be part of the project once created. Secondary to Story 1, since nothing can be viewed until at least one generation has happened.

**Independent Test**: Can be fully tested by generating a design model once, then loading the project and verifying the same model is present without needing to request generation again.

**Acceptance Scenarios**:

1. **Given** a project that already has a generated design model, **When** the project is loaded, **Then** the same site/building/room data is present on it.
2. **Given** a project that has never had a design model generated, **When** the project is loaded, **Then** its design-model fields are clearly absent (not fabricated placeholder geometry).

---

### User Story 3 - Regenerate after requirements change (Priority: P3)

A person whose project's parsed requirements changed (e.g., they updated their description and re-parsed, per Feature 02, or updated `built_area_m2` directly) wants the design model refreshed to reflect the new numbers.

**Why this priority**: Useful for keeping the design model current as requirements evolve, but the feature is already valuable with a single one-time generation (Stories 1–2), so this is the lowest priority.

**Independent Test**: Can be fully tested by generating a design model, changing the project's built area and/or re-parsing with a different description, requesting generation again, and verifying the new model reflects the updated numbers (not the old ones).

**Acceptance Scenarios**:

1. **Given** a project with an existing design model whose bedroom count or built area has since changed, **When** a design model is requested again, **Then** the new result reflects the current numbers and replaces the previous model.

### Edge Cases

- What happens when `floors` is known (it almost always is, per Feature 02's default) but `bedrooms` or `safe_room` is `unknown`? The model is still generated, using zero bedrooms / no safe room respectively, with the omission explicitly recorded (see User Story 1, Scenario 4) — never a fabricated guess.
- What happens when the fixed-size rooms alone don't fit in a floor's available footprint? Generation is refused with a clear error rather than producing rooms with negative or nonsensical sizes (User Story 1, Scenario 5).
- What happens when `pool` or `parking_spaces` are requested? They are not placed as rooms and do not consume built area in this feature — see Assumptions. A later feature is responsible for siting them within the plot.
- What happens if a design model is requested twice in a row with no change to the underlying project data? Both requests succeed and produce equivalent results; the second is not required to detect "nothing changed" and skip work.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a user to request a parametric design model for an existing project, identified by project_id.
- **FR-002**: System MUST require that the project has been parsed at least once (Feature 02) before a design model can be generated; if it hasn't, System MUST return a clear error and generate nothing.
- **FR-003**: The generated model MUST include: the site's width and depth (meters), the building's floor count, and a list of rooms — each with a type, the floor it's on, its area (m²), and its position and size (x, y, width, depth in meters) within that floor.
- **FR-004**: Site width and depth MUST be derived deterministically from the project's `plot_area_m2` using a fixed, documented assumption about plot shape (this feature does not have access to a real surveyed plot outline) — see Assumptions.
- **FR-005**: Each floor's available room area MUST be derived deterministically by splitting the project's `built_area_m2` evenly across its `floors` count.
- **FR-006**: The room list MUST deterministically include a living room, a kitchen, and a bathroom on the ground floor; a safe room on the ground floor when `safe_room` is known to be requested; and the project's bedrooms, distributed across floors (all on the ground floor when `floors` = 1, otherwise on the upper floor(s)), with each bedroom's area computed by dividing the remaining available area evenly among them.
- **FR-007**: System MUST NOT fabricate a specific bedroom count when `bedrooms`' source is `unknown` — the model MUST still be generated (with no bedroom rooms included), and MUST record that bedroom count was unknown and excluded from the layout.
- **FR-008**: System MUST NOT include a safe room in the generated model when `safe_room`'s source is `unknown`, and MUST record this omission the same way as FR-007.
- **FR-009**: System MUST persist the most recently generated design model for a project, retrievable later without regenerating.
- **FR-010**: System MUST allow regenerating a project's design model at any time, and the new result MUST replace the previously generated one.
- **FR-011**: The design model MUST be structured data only — this feature MUST NOT render or produce a visual drawing/image; that is a separate, later feature.
- **FR-012**: When the fixed-size rooms required on a floor (per FR-006) do not fit within that floor's available area (per FR-005), System MUST return a clear error and generate no model — partial or invalid (zero/negative-area) room geometry MUST NOT be produced.

### Key Entities

- No separate entity — per the same pattern established by Feature 02, the design model (site dimensions, building floor count, room list, any omission notes, and when it was generated) is merged directly into Feature 01's **Project** entity as a set of additional attributes, rather than living in its own resource.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can request a design model for a parsed project and receive a result in under 10 seconds.
- **SC-002**: For a project with a known bedroom count, every one of those bedrooms appears as a room in the result, 100% of the time, with no more and no fewer.
- **SC-003**: Requesting a design model for a project that has never been parsed returns a clear error and creates no model, 100% of the time.
- **SC-004**: For a project whose `bedrooms` or `safe_room` came back unknown from parsing, the resulting model clearly records that omission rather than silently producing a layout that looks complete, 100% of the time.
- **SC-005**: A user can change a project's requirements (re-parse or update built area) and, by requesting a design model again, see the result change to reflect the new numbers within the same 10-second budget as SC-001.
- **SC-006**: A project whose floor footprint can't fit the fixed-size rooms returns a clear error rather than a model with invalid (zero, negative, or overlapping) room geometry, 100% of the time.

## Assumptions

- **Plot shape**: `plot_area_m2` is a single number, not a surveyed outline, so this feature assumes a simple square plot (`width = depth = sqrt(plot_area_m2)`) to derive `site.width_m`/`site.depth_m`. This is a deliberately coarse placeholder, not real geometry — documented explicitly rather than presented as if it were surveyed, consistent with this project's evidence-first principle. A later feature with access to real parcel/plot geometry (per the source specification's Location Resolution feature) should replace this assumption rather than this feature attempting to guess a more "realistic" shape with no more actual information to go on.
- **Equal floor split**: `built_area_m2` is split evenly across `floors` — no attempt is made to model a smaller top floor or similar real-world massing variation, which would require information this system doesn't have.
- **Fixed room sizes are placeholders, not architectural standards**: kitchen, bathroom, and safe room use fixed reasonable area values (documented at the planning/implementation stage, not here, since specific numbers are a technical detail); living room and bedrooms absorb whatever area remains after those fixed rooms, split evenly among bedrooms. These are simplifications appropriate to a preliminary, non-binding sketch input — not a claim of code-compliant room sizing (compliance is a separate, later feature per the source specification).
- **Pool and parking are not placed**: `pool`/`parking_spaces`, if requested, are already recorded on the project (Feature 02) and are not turned into rooms or subtracted from `built_area_m2` here — siting them within the plot is left to a later feature (Layout Generator, per the source specification) that has more to work with (e.g. real site shape).
- **No history**: only the latest generated design model is kept per project, consistent with how both earlier features (Project's own edits, and Feature 02's parses) already work — no version history in this feature either.
- **No manual editing**: if a generated model isn't wanted as-is, the expected path is to change the underlying project data (built area, or re-parse a different description) and regenerate — not to hand-edit room positions, consistent with Feature 02's same choice for its own output.
- **Merged into `Project`, not a separate entity**: per explicit request, following the precedent Feature 02 already established (see `specs/001-project-creation/research.md` and `specs/002-requirement-parser/research.md`) — one project, one place to find everything known about it.
