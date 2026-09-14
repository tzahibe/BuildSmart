# Feature Specification: Wet-Room Semantics

**Feature**: `007-wet-room-semantics` | **Date**: 2026-09-14 | **Status**: spec for review — nothing implemented
**Supersedes**: the interim guard `variant_keeps_bathroom_access` in `concept_generator.py`
**Evidence**: [docs/WET_ROOM_SEMANTICS_PROPOSAL.md](../../docs/WET_ROOM_SEMANTICS_PROPOSAL.md) (measurements, 2026-09-13)

## 0. Decisions already taken (from review of the proposal)

| # | Decision |
|---|---|
| A | An explicit `ENSUITE + GUEST_WC` brief with another bedroom and **no shared full bathroom** is `NEEDS_CLARIFICATION`, not a warning. |
| B | `FLEXIBLE` must be representable from conversation (brief text and chat) **and** visible + confirmable on the Review screen before generation. |
| C | Fixtures are not re-based merely to pass. Tests are updated to the correct semantics, then valid fixtures are added that prove each supported case. |
| D | `SUPPORTED_BEDROOMS` keeps 5 and 6 for now; the documented capacity/support envelope is re-measured and corrected. |
| — | **C17 (realized bathroom access) is required and fails closed.** |

## 1. Problem *(measured, not assumed)*

A wet room is a **count** through the whole pipeline (`RequirementExtraction.wet_rooms` → `Project.wet_rooms`
→ `ProgramSpec.wet_rooms`), and `build_room_program` re-invents the kinds from that number. The parser
already recognises "חדר הורים עם שירותים" and "שירותי אורחים" (it has `ENSUITE` / `GUEST_BATHROOM`
relationship tokens) and discards them.

`programme_variants` then produced a second candidate that hung the last shared bathroom off the last
secondary bedroom, and the area-proximity sort in `generate_concepts` ranked it ahead of the literal
reading. Measured on the 426-scenario failure log: **45 delivered plans** had no full bathroom
reachable from circulation (31 are now refused by the interim guard, 14 redrawn). None of the 4 text
briefs among them asked for a second ensuite. The `scope.py` capacity claims ("4BR/2wet 130 m²",
"5BR/2wet 165 m²") were measured with that behaviour in force.

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — What the brief says about bathrooms is what gets built (P1)
A person writes "חדר הורים עם מקלחת, שירותי אורחים, חדר רחצה" (3 wet rooms). The review screen lists
**three** wet rooms by kind — ensuite (master), guest WC, shared bathroom — and the plan has a door from
the master into the ensuite, and doors from the hall into the WC and the bathroom.
*Acceptance*: review shows the three kinds with their source text; C17 passes; no bedroom other than
MASTER has a door into any wet room.

### User Story 2 — A count with no kinds keeps today's house (P1)
"3 חדרי שינה, 2 חדרי רחצה". Nothing in the text says which is which. The programme is exactly what
`build_room_program` produces today (master ensuite + shared bathroom); every plan for every such
brief in the failure log is byte-identical to the current baseline.
*Acceptance*: sweep gate — 107/107 pre-existing primaries identical; review shows 2 × "לא צוין —
ברירת מחדל: …" so the defaults are visible, not silent.

### User Story 3 — A second ensuite is built only when asked for, or allowed (P1)
(a) "לכל חדר שינה חדר רחצה צמוד" → two ensuites in the literal programme; no shared full bathroom is
required because the person said so explicitly and every bedroom has one.
(b) "2 חדרי רחצה, לא משנה איפה" → the second is `FLEXIBLE`; review shows it as "גמיש — המתכנן רשאי
להצמיד לחדר שינה"; the person can flip it to fixed. Only then may `programme_variants` offer the
private-bathroom arrangement, and only if a shared full bathroom remains or none is required.
(c) Any brief without (a) or (b) — including every synthetic `__CONFIG__` scenario — never gets it.
*Acceptance*: unit tests on `programme_variants` for (a), (b), (c); sweep gate: GAINED 0 versus the
interim guard (the log contains no flexible brief).

### User Story 4 — A house nobody can wash in is a question, not a plan (P1, decision A)
"2 חדרי שינה, חדר הורים עם מקלחת, שירותי אורחים" (2 wet rooms, both explicit, none shared, and a
second bedroom). Generation refuses with `NEEDS_CLARIFICATION` naming the second bedroom and stating what is
missing (a bathroom it can reach). The refusal does not choose an answer; it may list the
representable ways to answer (add a shared bathroom, change a kind). "Accept as is" is a Phase 5
question — it needs a representation the person can confirm on the Review screen.
*Acceptance*: `check_supported` test; the refusal is raised **before** any planning, at the same
place `CLARIFICATION_REQUIRED` is raised for ambiguous relationships today.

### User Story 5 — The drawing can never contradict the kinds (P1, C17)
Whatever candidate wins and however ranking changes in future, a plan whose realized doors do not match
the wet-room kinds is refused by validation.
*Acceptance*: C17 test with a fixture whose door set is deliberately wrong (a bathroom entered only
from a secondary bedroom while its kind is `SHARED_BATHROOM`) → `ok=False`, `PLAN_FAILED_VALIDATION`
names the room; C17 passes on every current baseline plan.

### User Story 6 — The envelope tells the truth (P2, decision D)
`SUPPORTED_BEDROOMS` stays `(1..6)`. The comment in `scope.py`, the review-screen limits, and the
`test_demo_p0` "many bedrooms" fixtures describe what the engine plans **without** semantic violations.
*Acceptance*: the envelope grid (§6.3) re-run after implementation; the three 4BR/2wet fixtures at
13.2×10.2 m are replaced by fixtures that prove 4/5/6BR on footprints that actually plan literally.

## 3. Vocabulary

```
WetRoomKind      SHARED_BATHROOM | ENSUITE | GUEST_WC | UNSPECIFIED
WetRoomStrength  REQUIRED | FLEXIBLE
WetRoomRequirement(kind, host: str | None, strength, source_text)
                  host: "MASTER_BEDROOM" | "BEDROOM" — ENSUITE only; None otherwise
```

- `SHARED_BATHROOM`: full bathroom, entered from circulation.
- `ENSUITE`: full bathroom, entered **only** from its host bedroom. Host defaults to `MASTER_BEDROOM`.
  `host="BEDROOM"` is an explicit second suite (US3a); which secondary bedroom is the planner's choice.
- `GUEST_WC`: WC + basin, entered from circulation. (Realized as `ProgramRole.TOILET`.)
- `UNSPECIFIED`: counted by the brief, kind not stated. Legacy projects have only these.
- `FLEXIBLE`: the person stated the placement does not matter. Only meaningful on `SHARED_BATHROOM`
  and `UNSPECIFIED`; ignored (and shown as ignored) on `ENSUITE` and `GUEST_WC`.

## 4. Requirements

### Functional

- **FR-1 Extraction.** `RequirementExtraction.wet_room_kinds: list[WetRoomRequirement]` (default `[]`).
  The parser fills it under the existing "never guess" contract (rules in §5). `wet_rooms` (count)
  stays and remains the authority on *how many*; when both are present `len(kinds) == wet_rooms`,
  padded with `UNSPECIFIED`. A mismatch is a parser defect and is reported as `ambiguous`, never
  silently truncated.
- **FR-2 Storage.** `Project.wet_room_kinds: list[WetRoomKindRecord]` (default `[]`) alongside
  `wet_rooms`. Records store kind/host/strength as plain strings (as `RoomRelationshipRecord` does) so
  a future value never invalidates a project on disk.
- **FR-3 Review (decision B).** `RequirementsReview.wet_room_kinds: list[WetRoomKindNote]` — one row
  per wet room: kind label in Hebrew, host, strength, source text or "לא צוין — ברירת מחדל: <kind>".
  `ReviewEdit.wet_room_kinds` lets the person set kind/host/strength per row, and setting `wet_rooms`
  (count) re-pads or truncates the list from the end. Edits are authoritative (`source="requested"`).
- **FR-4 Chat (decision B).** `UPDATE_PROJECT_FIELDS` gains `wet_rooms` and `wet_room_kinds`; a
  proposal that changes kinds is shown and confirmed through the existing proposal flow. "לא משנה
  איפה חדר הרחצה השני" → proposal to mark item 2 `FLEXIBLE`.
- **FR-5 Programme.** `ProgramSpec.wet_room_kinds: tuple[WetRoomRequirement, ...] = ()`.
  `build_room_program` honours explicit kinds literally; fills `UNSPECIFIED` items with today's
  defaults **in today's order**; the all-`UNSPECIFIED` case produces a programme identical to today's.
- **FR-6 Invariants** (checked in `check_supported`, before planning):
  - **I1** — if any item is `UNSPECIFIED`, the programme contains ≥ 1 `SHARED_BATHROOM`. A WC does not
    satisfy it. (Today's defaults always satisfy this; the check guards edits and future defaults.)
  - **I2** — every `GUEST_WC` is entered from circulation.
  - **I3** — every `ENSUITE` is entered only from its host.
  - **I4 (decision A)** — if there is no `SHARED_BATHROOM` and no `UNSPECIFIED`, then every bedroom
    must be the host of an `ENSUITE`; otherwise `NEEDS_CLARIFICATION` (new `ScopeCode`, same refusal
    shape as `CLARIFICATION_REQUIRED`), naming the bedroom(s) without a bathroom.
- **FR-7 Variant eligibility.** `programme_variants` may convert one `SHARED_BATHROOM` (or the
  `UNSPECIFIED` item that defaulted to one) into `ENSUITE(host=BEDROOM)` only when that item is
  `FLEXIBLE` **and** I1–I4 hold afterwards. Otherwise the literal programme is the only one. No rule
  may reference bedroom counts, footprints or scenarios. `variant_keeps_bathroom_access` is removed
  once this lands (its behaviour is the `strength=REQUIRED` case of FR-7).
- **FR-8 Ranking contract.** `generate_concepts` sorts only what `programme_variants` returned;
  eligibility is never re-decided after ranking. Documented in both docstrings; tested by asserting
  the candidate pool of a `REQUIRED` brief contains no candidate whose access graph has a bathroom
  entered from a non-host bedroom.
- **FR-9 C17 — realized bathroom access (fails closed).** For every wet room zone, the realized
  interior doors must match its kind: `SHARED_BATHROOM`/`GUEST_WC` → exactly one door and it is from
  circulation (HALL/hub); `ENSUITE` → exactly one door and it is from the host bedroom zone. Any
  wet room whose kind cannot be resolved (zone missing, kinds shorter than wet rooms, unknown
  kind string) **fails** the check — never passes by absence. `_STATEMENTS["C17"]`:
  "הגישה לכל חדר רחצה תואמת את מה שביקשת".
- **FR-10 Envelope (decision D).** `SUPPORTED_BEDROOMS` unchanged. The `scope.py` comment, the
  minimum-area claims and the review `limits` text are rewritten from the post-implementation grid.

### Non-functional

- **NF-1 Byte-identical baseline.** Every pre-existing primary (and its alternatives) in the
  failure-log sweep is unchanged: 107/107. LOST = 0. Crashes = 0.
- **NF-2 Backward compatibility.** Projects, extractions and chat proposals stored before this feature
  load without migration and behave as `UNSPECIFIED` (§7).
- **NF-3 Latency.** Sweep total within +5 % of the interim-guard baseline (593 s ON arm); C17 is
  O(doors) per plan.
- **NF-4 No Geometry Core, template, tolerance or corridor change.**

## 5. Extraction rules (parser prompt additions)

| text | item |
|---|---|
| חדר הורים עם מקלחת / עם שירותים / אנסוויט / חדר רחצה צמוד לחדר הורים | `ENSUITE, host=MASTER_BEDROOM, REQUIRED` |
| שירותי אורחים / שירותים לאורחים / שירותים ליד הכניסה | `GUEST_WC, REQUIRED` |
| חדר רחצה / מקלחת / חדר אמבטיה, unqualified | `SHARED_BATHROOM, REQUIRED` |
| חדר רחצה לחדר הילדים / לכל חדר שינה חדר רחצה (צמוד) | `ENSUITE, host=BEDROOM, REQUIRED` — one per such bedroom |
| "לא משנה איפה", "יכול להיות צמוד לחדר", "גמיש" attached to a wet room | that item `FLEXIBLE` |
| a bare count ("3 חדרי רחצה") | `UNSPECIFIED × n` |
| kinds named but count not stated | count = number of kinds, `source="requested"` |
| kinds named and count stated but they disagree | keep the count, pad with `UNSPECIFIED`, and add an `ambiguous` `UnsupportedRequest` quoting the text |

The existing rule "one room with shower AND toilet is ONE wet room" is unchanged.

## 6. Verification plan and gates

### 6.1 Unit (pytest, `backend/tests`)
- `build_room_program`: all-`UNSPECIFIED` equals today's output for every `PROGRAMS` entry (snapshot);
  explicit kinds honoured; padding; I1–I4 in `check_supported` including the decision-A case.
- `programme_variants`: US3 (a)/(b)/(c); `FLEXIBLE` on an `ENSUITE`/`GUEST_WC` is inert.
- `validation.C17`: passes on every baseline fixture; fails on a doctored door set; fails closed on
  missing/unknown kind.
- Parser: canned Hebrew briefs → expected items (extend `CANNED` in `test_demo_p0.py`); mismatch →
  `ambiguous`.
- Review/edit/chat: kinds round-trip through `ReviewEdit` and a chat proposal; count edits re-pad.
- Daylight ordering tests (feature 005/006 work) unchanged and green.

### 6.2 Sweep gates (`spikes/failure_log_sweep/ab.py`, isolated worktree)
- `--toggle wetkinds` (OFF = interim guard, ON = this feature): planned 107 → 107, byte-identical
  107/107, LOST 0, GAINED 0, C8 0/0, PLAN_FAILED_VALIDATION 0/0, C17 failures 0.
- `--toggle daylight` re-run under the feature: unchanged from the interim-guard run.

### 6.3 Envelope re-measurement (decision D)
The 216-cell grid (bedrooms 1–6 × wet 1–3 × safe × six footprints, `scope` guard lifted) is promoted
to `spikes/failure_log_sweep/envelope.py` and its output replaces the numbers in `scope.py` and in
the review `limits` copy. Every cell that plans must pass C17.

### 6.4 Fixtures (decision C)
`test_demo_p0` "many bedrooms" fixtures are rewritten so each asserts a **supported** case: for
4, 5 and 6 bedrooms a footprint on which the literal programme plans (from §6.3), with C17 and
"every wet room reachable as its kind says" asserted. The 13.2×10.2 m 4BR/2wet fixture becomes a
**refusal** test (`PLAN_NOT_REALIZABLE` with the outline hint), because that is now the correct answer.

## 7. Migration and backward compatibility

- **Stored projects** (`projects.json`): no `wet_room_kinds` → model default `[]` → all
  `UNSPECIFIED` → today's programme. No rewrite of the file.
- **Stored extractions / chat proposals**: same default; a proposal built before the feature never
  carries kinds and applies unchanged.
- **Stored designs** (`design_versions.json`): untouched; C17 runs only on new generations.
- **API**: new fields are additive and optional on every request model; responses gain fields
  clients may ignore. `ReviewEdit` without `wet_room_kinds` leaves kinds as parsed.
- **Frontend**: Review renders the new rows when present; an older backend returning no rows renders
  today's screen.
- **Failure log**: existing entries have no kinds and keep replaying as legacy — the sweep's
  `project_from_context` passes none.
- **Removal**: `variant_keeps_bathroom_access` and its tests are deleted in the same change that lands
  FR-7, with the sweep gate proving equivalence on the log.

## 8. Out of scope

- Any change to ranking (`generate_concepts` area sort), room templates, tolerances, corridor rules,
  Geometry Core, or the daylight ordering.
- Additional wet-room kinds (laundry, powder room, outdoor shower) — the vocabulary is closed for
  this feature.
- Choosing *which* secondary bedroom hosts a `host="BEDROOM"` ensuite by name (planner's choice).
- Narrowing `SUPPORTED_BEDROOMS` (decision D).

## 9. Success definition

A brief's bathroom-access semantics are represented, shown, confirmable, honoured literally, and
enforced on the drawing; no delivered plan can lack a corridor-reachable full bathroom unless the
person explicitly asked for exactly that and every bedroom has its own; and the documented capacity
envelope is one the engine actually meets without semantic violations.
