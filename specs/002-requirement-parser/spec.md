# Feature Specification: Natural Language Requirement Parser

**Feature Branch**: `002-requirement-parser`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Feature 02 — Natural Language Requirement Parser (מתוך docs/AI_Home_Planner_SPEC.md, סעיף 5). לנתח את שדה ה-description החופשי שכבר נשמר על פרויקט קיים (Feature 01) ולהפוך אותו ל-structured requirements: floors, target_built_area_m2, bedrooms, safe_room, parking_spaces, pool (requested + length_m + width_m). כל שדה חייב תיוג מקור: requested / inferred / unknown. אסור להמציא נתונים. יש לשמור את התוצאה על הפרויקט ולאפשר טעינה חוזרת ו-re-parse לאחר עדכון התיאור. לא כולל: location resolution, RAG, compliance, יצירת layout — features נפרדים."

> **2026-09-03, later the same day — major amendment**: per a follow-up request ("`Project` should
> contain everything needed to eventually produce a sketch, with most of it filled in by the LLM from the
> description"), this feature's output was merged directly into Feature 01's `Project` entity instead of
> living in a separate `StructuredRequirements` resource. This removed: the separate `GET
> /projects/{project_id}/requirements` endpoint (Feature 01's existing `GET /projects/{project_id}`
> already returns everything now), the "not yet parsed" `404` (unparsed fields are simply `null` in a
> normal `200` response), and `target_built_area_m2` (redundant with Feature 01's own validated
> `built_area_m2`, added the same day). See `specs/001-project-creation/research.md` and this feature's
> research.md for the full reasoning. The rest of this document has been updated in place to reflect the
> merged design — sections below describe the *current* behavior, not a history of what changed, except
> where a dated note calls out something worth remembering about why.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Parse a project's description into structured requirements (Priority: P1)

A person who already created a project (with a free-text description of the house they want) asks the system to turn that description into structured, usable data — how many floors, how many bedrooms, whether a safe room and a pool are wanted, and so on — merged directly into their project.

**Why this priority**: This is the entire point of the feature — without it, the free-text description sits unused and no downstream feature (design, compliance, etc.) has anything structured to work with.

**Independent Test**: Can be fully tested by creating a project with a descriptive free-text description, requesting parsing for it, and verifying the project's own record now carries structured fields matching what the text actually says.

**Acceptance Scenarios**:

1. **Given** a project whose description is "אני רוצה בית בן קומתיים בשטח 220 מ"ר, 4 חדרי שינה, ממ"ד, חניה ל-2 עם בריכה 8 על 4 בחצר האחורית", **When** parsing is requested for that project, **Then** the project's own record now states floors=2, bedrooms=4, safe_room=true, parking_spaces=2, and a pool requested with length_m=8 and width_m=4 — each explicitly marked as coming from the user's own words, alongside the project's unchanged structured fields (city, street, plot area, built area).
2. **Given** a project whose description never mentions parking, **When** parsing is requested, **Then** the parking_spaces field is returned as unknown rather than a guessed number.
3. **Given** a project whose description mentions "בריכה" (a pool) without giving any dimensions, **When** parsing is requested, **Then** the pool is marked as requested, but its dimensions are marked unknown rather than invented.
4. **Given** a project_id that does not correspond to any existing project, **When** parsing is requested for it, **Then** the system returns a clear "not found" error and performs no parsing.

---

### User Story 2 - View previously parsed requirements (Priority: P2)

A person who already had their project's description parsed wants to see the structured result again later, without re-running the parse.

**Why this priority**: Parsing may take a few seconds and/or have a cost; re-displaying an already-known result should be instant and free. Still secondary to Story 1, since nothing can be viewed until at least one parse has happened.

**Independent Test**: Can be fully tested by parsing a project once, then loading the project (Feature 01's existing retrieval) and verifying the same structured result is present, without needing to resubmit the description.

**Acceptance Scenarios**:

1. **Given** a project that has already been parsed, **When** the project is loaded, **Then** the previously computed structured fields are present on it, including which parts came from the user's own words versus which were inferred versus which are unknown.
2. **Given** a project that has never been parsed, **When** the project is loaded, **Then** its planning fields (floors, bedrooms, safe room, parking spaces, pool) are clearly absent (not fabricated placeholder values) — distinguishable from a field that *was* parsed but came back unknown.

---

### User Story 3 - Re-parse after updating the description (Priority: P3)

A person changes their project's description (already possible per Feature 01) and wants the structured requirements refreshed to reflect the new text.

**Why this priority**: Useful for correcting or evolving requirements over time, but the feature is already valuable with a single one-time parse (Stories 1–2), so this is the lowest priority.

**Independent Test**: Can be fully tested by parsing a project, updating its description to say something different, requesting parsing again, and verifying the structured result changes to reflect the new text (not the old one).

**Acceptance Scenarios**:

1. **Given** a project that was already parsed once, **When** its description is updated and parsing is requested again, **Then** the project's structured fields reflect the updated description, replacing the previous parse's values.

### Edge Cases

- What happens when the description is extremely short or vague (e.g., just "בית")? Parsing must still succeed, with nearly every field marked unknown rather than the request failing.
- What happens when the description contains conflicting statements about the same thing (e.g., states 2 floors in one sentence and 3 in another)? The affected field must be marked unknown rather than guessing which statement wins — this overrides the FR-011 default for floors specifically: a conflict is not the same as "unstated," so it does not fall back to 1.
- What happens when a value is implied but not stated outright (e.g., "בית משפחתי גדול" implying more than one bedroom without a number)? Such a field is marked inferred, not requested, and only assigned a value if a specific one can reasonably be inferred — otherwise it too is unknown.
- What happens if parsing is requested for the same project twice in a row without any change to the description? Both requests succeed and produce equivalent results; the second is not required to detect "nothing changed" and skip work.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a user to request that an existing project's currently stored description be parsed into structured requirements, identified by that project's project_id.
- **FR-002**: The parsed result MUST cover the following aspects of the requested house, when the source text supports them: number of floors, number of bedrooms, whether a safe room is wanted, number of parking spaces, and whether a pool is wanted (and its length/width in meters if given). Built area is deliberately excluded here — see FR-012.
- **FR-003**: System MUST tag every field in the parsed result with exactly one source: `requested` (stated explicitly by the user), `inferred` (reasonably implied by the text but not stated outright), or `unknown` (cannot be determined from the text).
- **FR-004**: System MUST NOT assign a fabricated or default value to any field whose source is `unknown` — such fields carry no value, only the `unknown` tag.
- **FR-005**: System MUST merge the parsed result directly into the project's own record (Feature 01's `Project`), so it can be retrieved later via that project without a separate lookup.
- **FR-006**: System MUST allow re-parsing a project at any time, and the new result MUST replace the previously merged one.
- **FR-007**: System MUST always parse the project's description exactly as currently stored (per Feature 01) — parsing does not accept a separately supplied text to parse instead.
- **FR-008**: System MUST return a clear "not found" error, and perform no parsing, when parsing is requested for a project_id that does not exist.
- **FR-009**: A project that has never been parsed MUST present its planning fields as clearly absent (not empty/fabricated placeholder values) — distinguishable from a field that was parsed but whose source is `unknown`.
- **FR-011**: When the description does not state a number of floors, System MUST default `floors` to 1 (a single story), tagged `inferred` rather than `unknown`. This is the one deliberate, standing default in this feature — every other field, when unstated and not reasonably implied, remains `unknown` per FR-004, with no default substituted.
- **FR-012**: System MUST NOT extract or report a built area from the description — the project's own `built_area_m2` (Feature 01, validated and structured) is the single source of truth for that fact, and re-deriving it from free text would create a second, unreconciled value for the same thing (added 2026-09-03, later the same day, superseding the original FR-002's inclusion of a parsed built-area field).

*(FR-010, an "essential fields missing → message" requirement, existed briefly the same day and was removed
in the same amendment that produced FR-012 — once built area stopped being parsed at all, and floors
already defaults per FR-011, there was nothing left for that check to meaningfully flag. See research.md.)*

### Key Entities

- No separate entity — the fields this feature produces (floors, bedrooms, safe room, parking spaces, pool, plus when they were last parsed) are attributes of Feature 01's **Project** entity. See `specs/001-project-creation/data-model.md` for the full `Project` shape, including these fields.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can request parsing for a project and receive an updated project record in under 10 seconds.
- **SC-002**: For a description that explicitly states a value for a given field (e.g., an exact number of bedrooms), parsing returns that value tagged `requested`, matching the stated value exactly.
- **SC-003**: For a description that never mentions a given field and gives no reasonable basis to infer it, parsing returns that field tagged `unknown` with no fabricated value, 100% of the time.
- **SC-004**: A user can update a project's description and, by requesting parsing again, see the structured result change to reflect the new text within the same 10-second budget as SC-001.
- **SC-005**: Requesting parsing for a nonexistent project returns a clear error 100% of the time, with no partial or misleading data.
- **SC-007**: When a description never mentions floors at all, `floors` is returned as `1`, tagged `inferred`, 100% of the time — never `unknown` and never absent from the result.

## Assumptions

- Parsing is triggered explicitly (an on-demand action against an existing project), not run automatically every time a project is created or its description changes — this keeps the cost/latency of parsing under the user's control and matches Feature 01's scope boundary (which explicitly excluded parsing).
- Only the latest parse result is kept per project; no history of earlier parses is retained in this feature (consistent with Feature 01's "no update history" assumption). Comparing versions over time belongs to a later, separate feature (What-If / Design Optimization, per the source specification).
- The parsed field set is: floors, bedrooms, safe room, parking spaces, and pool (with optional dimensions) — built area is deliberately excluded (FR-012). Additional constraint types listed elsewhere in the source specification (e.g., balconies, basements, roof type) are deferred to a later iteration of this feature or to Feature 07 (Regulatory Knowledge Extraction), which deals with a different, regulation-derived set of constraint types.
- No manual correction/editing of a parsed result is included — if the parsed result is wrong, the expected path is to update the project's description (Feature 01) and re-parse, not to hand-edit individual structured fields.
- No confidence scoring beyond the three-way source tag is included — a full confidence system (combining source quality, verification, etc.) is a later, separate feature per the source specification.
- The technical approach ended up being an LLM call (OpenAI's `gpt-5-nano`), per explicit request — see plan.md/research.md for that decision and its trade-offs; this spec only constrains the observable behavior (what gets extracted, how it's tagged, and that nothing is fabricated).
- Parsed fields live directly on Feature 01's `Project` (this file's major 2026-09-03 amendment, see the note at the top) rather than in a feature-owned entity — a deliberate choice to keep "everything about this project" in one place rather than splitting it across resources that have to be kept in sync.
