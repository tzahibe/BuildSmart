# Feature Specification: Engine-Chosen Building Outline

**Feature Branch**: `006-engine-chosen-outline`

**Created**: 2026-09-13

**Status**: Draft

**Input**: User description: "Engine-chosen building outline. Remove the 'בחר/י את מתאר הבניין' footprint-selection screen from the main flow. The person supplies plot dimensions, street side, room programme and requested built area; the engine itself runs the feasible outline shapes for that area (the same 4 width/depth ratios feasible_options already offers, inside the setbacks), plans each end to end (concepts, Geometry Core, validation), and presents up to three plans that differ in their architectural family — not merely in footprint proportion — each labelled with the outline it uses. Manual outline choice remains available as an 'advanced' option for a person with a real constraint (e.g. must keep a 15 m street frontage). Measured motivation on the 424-brief failure log at HEAD 5fd9474 … Acceptance: no brief that plans today loses its plan; every plan shown passes the same validation as today's primary; latency of a request is measured and reported (up to four full runs instead of one)."

---

## 1. Why *(the evidence this spec is built on)*

Today the person is asked twice for a width and a depth: once for the **plot** (a fact about their land) and once for the **building outline** (the rectangle the house will occupy inside the setbacks). The second question looks like the first but is not a fact the person knows — it is a planning decision, and the measurements below show they make it worse than the engine's own fixed shapes would.

Measured on the production refusal log (424 distinct briefs, code at `5fd9474`), every brief run at the outline the person chose **and** at each of the four outline shapes the engine already knows how to offer for the same built area:

| Question | Measured |
|---|---|
| How often does the person's own outline produce a plan? | **127 / 424 (30 %)** |
| How often does each of the engine's four fixed shapes produce a plan? | 35 % · 43 % · 45 % · 40 % — **every one beats the person's choice** |
| How many briefs get a plan at *some* outline (person's or engine's)? | **260 / 424 (61 %)** |
| Of the 297 briefs refused at the person's outline, how many plan at an engine outline? | **133**, at a median **97 %** of the requested area (95 of them ≥ 90 %) |
| Among the 127 briefs that plan today, built area ÷ requested area | person's outline median **0.79** → best engine outline **0.98**; in **44** briefs the person got < 95 % while another outline reaches ≥ 95 % |
| Among those 127, how often is the person's outline already the best one (area, then hall shape)? | **37 / 127** |
| Briefs whose shown plans include ≥ 2 distinct architectural families | **28 → 69** of 127 (≥ 2 distinct partis: 17 → 32) |
| Briefs where the four outlines give ≥ 3 genuinely different drawings | 109 / 127 |
| Briefs that plan at the person's outline and at **no** engine outline | 2 |
| Briefs refused at every outline | 164 (67 of them ask for more area than their room programme can use — a different problem, not addressed here) |

Two further facts shape the design:

- The engine already contains this search. When a request is refused today it silently plans the same four outlines and, if one succeeds, tells the person in text "it is possible at X × Y m" — after the failure, as a hint, instead of before it, as the plan.
- Outline shape does **not** decide the architectural family: the mix of families is nearly identical at every width/depth ratio. So this feature buys success rate, delivered area and *more* distinct plans per brief, but it is not the fix for family repetition — that lives in concept generation and is out of scope here.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — A person gets plans without choosing a building outline (Priority: P1)

A person enters their plot (dimensions, street side), the rooms they want and the built area they want. They are **not** asked to pick a building rectangle. The engine tries the feasible outline shapes for that area inside the setbacks, plans each one completely, and shows up to three finished plans, each labelled with the outline it occupies (e.g. "12.35 × 14.25 m").

**Why this priority**: it removes the one input the person cannot answer well, and on the measured log it lifts the share of briefs that get a plan from 30 % to 61 % and the delivered area from 79 % to 98 % of what was asked.

**Independent Test**: run the 424 logged briefs through the new flow with the person's outline withheld; count briefs that receive at least one plan, measure built ÷ requested area for the first plan, and count distinct families among the plans shown. Compare against the table in §1.

**Acceptance Scenarios**:

1. **Given** a plot, street side, room programme and requested area that fit inside the setbacks, **When** the person asks for a design, **Then** they receive between one and three plans without having been asked for a building width or depth, and every plan states the outline (width × depth, area) it uses.
2. **Given** a brief that is refused today at the person's chosen outline but plans at one of the engine's four shapes (133 such briefs in the log), **When** it is run through the new flow, **Then** it receives a plan.
3. **Given** a brief that plans today at a smaller-than-requested area while another outline reaches ≥ 95 % of the request (44 such briefs), **When** run through the new flow, **Then** the first plan shown is at ≥ 95 % of the requested area.
4. **Given** any plan shown, **Then** it has passed every validation check that today's primary plan must pass; no plan is shown with a caveat, warning or reduced standard.

---

### User Story 2 — The plans shown are different houses, not one house re-proportioned (Priority: P1)

When several outlines produce plans, the person sees plans that differ in how the house is organised — where the public zone sits relative to the bedrooms, whether the bedrooms open onto a corridor or a compact lobby — rather than the same arrangement stretched to a different rectangle.

**Why this priority**: today 142 of the 178 alternative plans shown across the log are the primary plan's own family at another proportion. Offering three near-identical houses is offering one.

**Independent Test**: for each logged brief that yields ≥ 2 plans, classify each shown plan's family (dimension- and mirror-independent); the count of briefs with ≥ 2 distinct families shown must reach the §1 figure (69 of 127 among today's planning briefs).

**Acceptance Scenarios**:

1. **Given** the validated plans from all outlines contain ≥ 3 distinct families, **When** the plans are shown, **Then** the three shown are of three different families.
2. **Given** they contain exactly two families, **Then** both are shown; a third slot, if filled, must come from a different outline than any plan already shown — never the same outline re-proportioned.
3. **Given** they contain one family from one outline only, **Then** one plan is shown, and the screen does not pad the set with proportion variants.
4. **Given** two plans of the same family from two outlines, **Then** they are shown only if no other family is available, and each is labelled with its outline so the difference (a different house size or shape) is visible.

---

### User Story 3 — A person with a real constraint can still fix the outline (Priority: P2)

A person who must keep, say, a 15 m frontage to the street, or has a building permit tied to a specific rectangle, can open an "advanced" option, enter the outline themselves, and get plans for exactly that rectangle. The engine's own outlines may still be offered beside it, clearly marked as the engine's suggestions.

**Why this priority**: the constraint is rare but real, and losing the ability would be a regression for the people who have it. It is also how today's logged requests — all of which carry a chosen outline — remain reproducible.

**Independent Test**: submit a brief with an explicit outline; the first plan shown occupies exactly that rectangle when it plans; when it does not plan, the refusal names that rectangle and, if an engine outline plans, offers it as a separate, labelled plan.

**Acceptance Scenarios**:

1. **Given** the person has entered an explicit outline and it plans, **Then** the first plan shown uses that outline, byte-identical to what the same request produces today.
2. **Given** the explicit outline does not plan but an engine outline does, **Then** the person is told their outline could not be planned and is shown the engine-outline plan(s), each labelled as a different outline than the one they entered.
3. **Given** the explicit outline does not fit inside the setbacks, **Then** the person is told so before any planning is attempted, exactly as today.

---

### User Story 4 — A refusal is final and honest (Priority: P2)

When no outline produces a plan, the person is told once, with the reason that applies (the room programme cannot fill the requested area; the programme does not fit the plot; a required relationship cannot be met), and is **not** told to "try another outline" — every feasible outline has already been tried.

**Why this priority**: today's refusal path suggests an outline the person then has to enter by hand and resubmit. Once the engine tries them itself, that suggestion is either already a plan on screen or provably useless, and offering it would send the person to a dead end.

**Independent Test**: run the 164 logged briefs that plan at no outline; each must return a single diagnosis, none may mention an alternative outline, and the 67 over-capacity briefs must carry the capacity diagnosis.

**Acceptance Scenarios**:

1. **Given** a brief that plans at no feasible outline, **Then** the response is a refusal with one diagnosis and no outline suggestion.
2. **Given** the refusal is for a requested area the room programme cannot use, **Then** the diagnosis says so and states the area the programme can reasonably fill, as today.

---

### Edge Cases

- **Tight site** — the four preferred shapes clip to one or two distinct rectangles inside the setbacks. The engine plans each *distinct* rectangle once; duplicates are not run twice and do not count as separate plans.
- **No feasible outline** — the requested area does not fit inside the setbacks at any shape. Refused before planning, with the existing "does not fit the plot" diagnosis.
- **Every outline gives the same family** — one plan is shown (or several only under the different-outline rule of Story 2); the screen never shows an empty slot or a placeholder.
- **Explicit outline coincides with an engine shape** — planned once; labelled as the person's outline.
- **Two briefs that plan only at the person's outline** (2 of 424 in the log) — in the main flow, with no outline given, these receive a refusal or a plan from a different outline; the advanced path reproduces today's plan. This is an accepted, quantified trade.
- **Latency** — up to four complete planning runs instead of one. The person sees stage progress as today, the total time is recorded per request, and the first plan may be shown as soon as it exists while remaining outlines are still being planned.
- **A required room relationship** (from the chat) is satisfiable at one outline and not another — an outline whose plans all break a hard relationship produces no plan; the rule is applied per outline exactly as it is applied per candidate today.

## 3. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The main design flow MUST NOT require the person to enter a building width or depth. The inputs are plot dimensions, street-facing side, room programme (bedrooms, wet rooms, safe room, open plan, and chat-derived rooms and relationships) and requested built area.
- **FR-002**: For a request without an explicit outline, the system MUST derive the set of feasible outlines for the requested area inside the setbacks — the same four preferred width/depth shapes offered on today's selection screen, de-duplicated after clipping — and MUST plan **each** of them completely (concept, geometry, validation), never only until the first success.
- **FR-003**: Every plan shown MUST have passed the identical validation the primary plan is held to today. A plan that fails any check is not shown, not offered as a lesser option, and not described.
- **FR-004**: The system MUST show at most three plans, chosen so that distinct architectural families are exhausted before any family repeats; when a family repeats, the repeat MUST come from a different outline than every plan already shown. The same outline is never shown twice re-proportioned.
- **FR-005**: Each plan shown MUST state the outline it occupies: width, depth and gross area, and whether the outline was the engine's or the person's.
- **FR-006**: The first plan shown MUST be the validated plan whose gross area is nearest the requested area across all outlines planned (today's selection rule, applied across outlines rather than within one). Ties are broken toward the outline shape the engine prefers first.
- **FR-007**: An "advanced" option MUST let the person enter an explicit building outline. When given, that outline MUST be planned first; if it plans, its plan MUST be the first plan shown and MUST be identical to what the same request produces today. Engine outlines MAY be planned in addition and shown after it, labelled as engine suggestions.
- **FR-008**: When the explicit outline does not plan, the response MUST say so by name (its width × depth) and MUST still show any engine-outline plan that exists, labelled as a different outline.
- **FR-009**: When no outline produces a plan, the system MUST return exactly one refusal with the applicable diagnosis and MUST NOT suggest another outline.
- **FR-010**: The system MUST record, for every request, the number of outlines planned, which of them produced a validated plan, the family of each plan shown, and the total time from request to response; these MUST be available in the request's diagnostics as today's per-candidate metrics are.
- **FR-011**: Plot dimensions, setbacks and buildable area MUST continue to be shown to the person as facts about their land; only the outline *choice* leaves the main flow.
- **FR-012**: Nothing in how a single outline is planned — concept generation, geometry, doors, windows, furniture, validation, drawing — changes. This feature changes only which outlines are planned and how their results are selected and presented.

### Key Entities

- **Requested Brief**: what the person asked for — plot, street side, room programme, requested built area, chat-derived rooms and relationships, and optionally an explicit outline. Unchanged except that the outline becomes optional.
- **Outline**: a rectangle (width, depth, position inside the setbacks) of the requested area; carries its origin — *engine* (one of the preferred shapes) or *person* (advanced entry).
- **Outline Result**: the outcome of planning one outline end to end — either a set of validated plans or a diagnosis; also records time spent.
- **Architectural Family**: the dimension- and mirror-independent organisation of a plan — where the public zone sits relative to the private wing, whether bedrooms open onto a corridor spine or a compact lobby, and which rooms share a column or band. Two plans of the same family differ only in proportions; two plans of different families are different houses. Used only to choose which plans to show.
- **Plan Set**: what the person receives — one to three plans, each with its outline label and family, plus the diagnostics of FR-010; or a single refusal.

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

Measured on the 424-brief production log, person's outline withheld (main flow), unless stated.

- **SC-001**: Briefs that receive at least one plan rise from 127 (30 %) to at least **250 (59 %)**.
- **SC-002**: Among briefs that plan today, the first plan's gross area ÷ requested area has a median of at least **0.95** (today 0.79).
- **SC-003**: Among briefs that plan today, at least **60** (today 28) show two or more distinct architectural families.
- **SC-004**: No plan shown fails any validation check: **0** of all plans shown across the log.
- **SC-005**: With the person's outline supplied through the advanced path, **127 of 127** briefs that plan today produce a first plan byte-identical to today's (room types, positions and sizes).
- **SC-006**: **0** shown plan sets contain two plans of the same family from the same outline.
- **SC-007**: Refusals: **0** of the 164 all-outline refusals mention an alternative outline; all 67 over-capacity briefs carry the capacity diagnosis.
- **SC-008**: Median time from request to response over the log stays within **4×** today's median (today ≈ 1.1 s per planning run in the harness), and the worst case is reported, not hidden.
- **SC-009**: The main-flow screen count between "plot entered" and "plans shown" drops by one; the advanced outline entry is reachable in one action from the flow.

## 5. Assumptions

- The four preferred width/depth shapes and their clipping inside the setbacks are the right candidate set for v1; widening the set (more shapes, non-rectangular outlines) is a separate decision. The measurement in §1 was made with exactly these four.
- "Nearest the requested area" remains the rule for the first plan. A selection rule that also weighs plan quality (compact hall, wet-room clustering, public contiguity) is a separate feature; this spec deliberately does not introduce one, so that the only variable changed here is *which outlines are planned*.
- Family classification is available as a stable, dimension-independent signature of a plan's organisation; it is used only to pick which plans to show and is not exposed as a user-facing label beyond the outline text.
- Today's logged requests all carry an explicit outline; they are reproduced through the advanced path (FR-007), which is how the byte-identical gate (SC-005) is checked.
- Planning several outlines costs several planning runs; the cost is accepted and measured (SC-008). Running outlines concurrently or showing the first plan before the others finish are implementation choices, not requirements, as long as SC-008 is met and reported.
- The existing "does not fit the plot" and "programme cannot use this much area" diagnoses are reused unchanged; this feature only removes the outline suggestion from the refusal.
- The 2 logged briefs that plan only at the person's own outline are an accepted trade for the main flow; they remain reachable through the advanced path.

## 6. Out of Scope

- Any change to how one outline is planned (concept vocabulary, forced cuts, geometry, validation). The repetition of families across briefs is a concept-generation property and is addressed separately.
- A quality-aware ranking of plans.
- More than four outline shapes, non-rectangular outlines, or multi-storey distribution of area.
- Over-capacity briefs (requested area beyond what the programme can use): they are refused with the capacity diagnosis as today.
