# Feature Specification: Guest WC — by the entrance, and small

**Feature**: `009-guest-wc-placement` | **Date**: 2026-09-14 | **Status**: DRAFT, decisions A–D taken 2026-09-14 — nothing implemented
**Depends on**: `007-wet-room-semantics` (the `GUEST_WC` kind, `TOILET` realization, C17). This feature
is NOT an amendment to 007: 007's NF-4 and §8 forbid template and Geometry Core changes and gate on a
byte-identical baseline, and both of the things asked for here change plans.
**Evidence**: measured 2026-09-14 on the current `main` (see §1); reported by the user the same day:
"שירותי אורחים ממוקמים קרוב לכניסה לבית ומדובר בשירותים נורא קטנים".

## 0. Decisions taken (review of the draft, 2026-09-14)

| # | Decision |
|---|---|
| A | **"By the entrance" is an architectural preference, not a law.** `GUEST_WC` REQUIRES access from the public / circulation side of the house; that is what C19 checks and fails closed on. Proximity to the front door is a **quality metric that ranks candidates** — it becomes binding only when the person said so explicitly ("שירותים ליד הכניסה"), and then it rides on the existing relationship mechanism (`GUEST_BATHROOM near ENTRANCE`, enforced by C15), not on C19. A plan is never refused merely because the WC is not by the door. |
| B | A `TOILET` derived from the count alone (no "אורחים" in the brief) is a preference only: the placement is attempted, C19 is not run, and every such plan is byte-identical to the baseline unless the WC moved. |
| C | Access order of preference: **foyer / hall → public circulation → living room.** Never through a bedroom, never through the kitchen. |
| D | Size band **1.5–3.0 m² net, short side 0.9–1.2 m, aspect ≤ 2.2** — a DESIGN TARGET, not a standard. If a regulation layer later supplies numbers, that layer is the authority and these yield to it. |

## 1. Problem *(measured, not assumed)*

Three layers, in the order the request passes through them. 007 fixes the first two; nothing today
touches the third.

1. **Extraction** — "שירותי אורחים" adds 1 to `wet_rooms` and the kind is discarded
   ([parser.py:53-61](../../backend/app/requirements/parser.py#L53-L61)). → 007 FR-1.
2. **Programme** — `build_room_program` creates a `TOILET` only from the COUNT, and only with two or
   more SHARED wet rooms ([concept_generator.py:380-391](../../backend/app/vertical_slice/concept_generator.py#L380-L391)).
   The most common wording, "חדר רחצה ושירותי אורחים" with a master bedroom (2 wet rooms), becomes
   ensuite + shared bathroom: **no WC at all**. → 007 FR-5.
3. **Placement and size** — the `TOILET` is a `ZoneGroup.SERVICE` room, and every strategy but
   `BRANCHED_TWO_STACK` puts service rooms in the private column as one full-width row
   ([concept_generator.py:595](../../backend/app/vertical_slice/concept_generator.py#L595), `:1325`,
   `:1417`, `:1704`). Its short side is the row depth and its long side is the column's width, so the
   template ([concept_generator.py:118](../../backend/app/vertical_slice/concept_generator.py#L118),
   2.2 / 4.0 / 6.0 m², short side ≥ 1.1) cannot make it small, and nothing places it by the entrance —
   `ENTRANCE` exists only as a relationship token that resolves to the HALL.

Measured on the one brief that yields a `TOILET` today (3BR + ממ"ד + 3 wet, open plan), three
footprints, 5.5/3/4 setbacks, primary and alternatives:

| footprint | WC size (w × d) | area | entered from | WC door → front door | next to |
|---|---|---|---|---|---|
| 12.5 × 14.5 | 4.25 × 1.45 | 6.2 m² | HALL | 10.2 m | BATH_2 (4.85 × 1.80) |
| 12.5 × 14.5 alt | 3.55 × 1.35 | 4.8 m² | HALL | 11.6 m | BATH_2 |
| 15.0 × 12.0 | 5.40 × 1.45 | 7.8 m² | HALL | 8.1 m | BATH_2 (6.20 × 1.80) |
| 11.0 × 16.5 | 4.05 × 1.45 | 5.9 m² | HALL | 10.8 m | BATH_2 |
| 11.0 × 16.5 alt | 3.40 × 1.35 | 4.6 m² | HALL | 11.5 m | BATH_2 |

Every case: the WC is 2–3× the size asked for, a strip (aspect 2.5–3.7), at the far end of the
corridor beside the family bathroom, and reads on the plan as that bathroom's twin. One realized
area (7.8 m²) exceeds the template's own `max_area_m2` of 6.0 — headroom scaling lets a "small"
room drift past its ceiling, which is a separate defect this feature fixes by construction (§4 FR-3).

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — The guest WC is reached from where guests are (P1, decisions A/C)
"3 חדרי שינה, חדר הורים עם מקלחת, חדר רחצה, שירותי אורחים." The plan's `TOILET` has exactly one
door, and it opens from the public side of the house: the foyer/hall, else public circulation, else
the living room (decision C). Never from a bedroom, never from the kitchen.
*Acceptance*: C19 passes on the primary AND on every alternative; a fixture whose WC is entered from
a bedroom or the kitchen fails C19 naming the room and the zone it was entered from. A WC entered
from the hall at the far end of the bedroom corridor **passes C19** — it is ranked down (US1b), not
refused.

### User Story 1b — Closer to the front door ranks higher (P1, decision A)
Among candidates that pass every check, the one whose WC door is nearer the front door (walking
distance along the realized circulation) is preferred. On the 5 measured cases of §1 the delivered
WC door is ≤ **4.0 m** from the front door wherever such a candidate exists; where none exists the
plan is delivered anyway and the review notes the distance.
*Acceptance*: ranking test on a fixture with two otherwise-equal candidates; §1 cases re-measured.

### User Story 1c — "ליד הכניסה", said explicitly, is binding (P1, decision A)
"שירותי אורחים ליד הכניסה." The wording becomes a room relationship (`GUEST_BATHROOM near ENTRANCE`,
hard requirement) and is enforced the way every other relationship is — C15 — with the existing
`ROOM_RELATIONSHIP_NOT_FEASIBLE` refusal when no candidate satisfies it. No new mechanism.
*Acceptance*: parser test (§5); C15 fixture; the refusal names the relationship in the person's words.

### User Story 2 — The guest WC is a small room, not a strip (P1, decision D)
Same brief. The realized `TOILET` is 1.5–3.0 m² net, short side 0.9–1.2 m, aspect ≤ 2.2, and does
not span the full width of any column: it is a **pocket** carved beside the entrance (from the lobby's
depth, from a public zone's corner, or from the hall's entrance end), with the neighbouring zone
absorbing the remainder of the row.
*Acceptance*: C3 with the new template band; a geometric test that the WC's long side is strictly
shorter than the row/column it sits in; the 5 cases of §1 re-measured at ≤ 3.0 m².

### User Story 3 — It does not look like the bathroom's twin (P1)
The WC is not in the private column's row stack and does not share its row with a full bathroom.
*Acceptance*: on the 5 cases of §1, `TOILET` and `BATH_2` are in different columns/bands.

### User Story 4 — Plumbing still wants company (P2)
Where a candidate exists in which the WC shares a wall with the kitchen or another wet room, it is
preferred over one where it does not (memory: wet-room adjacency is a measured gap, 40 % vs 85–90 %).
*Acceptance*: ranking test only; never a refusal.

### User Story 5 — A count-only brief keeps today's house (P1, decision B, NF-1)
"3 חדרי שינה, 3 חדרי רחצה" — no "אורחים". The `UNSPECIFIED`-derived WC is placed by the same rule
when a candidate allows it, ranked by the same metric, and C19 is **not run**; every plan in the failure-log sweep for a brief
that never named a guest WC is byte-identical to the current baseline unless the WC moved — and the
sweep reports which moved and where.
*Acceptance*: sweep gate; LOST = 0.

### User Story 6 — The review screen says it (P2)
The wet-room row for a `GUEST_WC` (007 FR-3) shows its access ("מהמבואה" / "מהסלון") and, when the
brief said "ליד הכניסה", the relationship row shows it as the hard requirement it is. The person can
add or drop the relationship there, as with any other relationship.

### Edge Cases
- **No hall at all** (front door opens into the living room, open plan): the WC pocket is carved from
  the living room's entrance corner and entered from it (decision C, third choice). C19 passes.
- **The only public zone the pocket could join is the kitchen** (closed kitchen fronting the entrance,
  living at the back): the pocket is not placed there; the strategy rejects (`guest_wc=True`) or
  falls back (`guest_wc=False`).
- **Two WCs asked for** ("שירותי אורחים ושירותים נוספים"): out of scope (§7); the parser reports the
  second under `other_requests`, exactly as an unsupported room is reported today.
- **Hub parti (008)**: the hub is circulation; a pocket on the hub's entrance side qualifies as
  "public circulation". The hub's own eligibility bound is re-measured with the pocket present.
- **"ליד הכניסה" with no candidate that satisfies it**: `ROOM_RELATIONSHIP_NOT_FEASIBLE`, as for any
  relationship today — never a silent downgrade to a preference.
- **A count-only brief whose WC cannot become a pocket in any strategy**: today's plan, unchanged,
  byte for byte (decision B).

## 3. Vocabulary (additions to 007's) — *Key Entities*

```
PublicAccess       the zones a GUEST_WC may be entered from, in order of preference:
                   foyer/HALL segment at the entrance → public circulation → LIVING. Never BEDROOM, never KITCHEN.
EntranceZone       the zone the front door opens into (HALL, or the public zone when there is no lobby)
Pocket             a room that shares its row/column with a neighbour and takes a fixed corner of it
EntranceDistance   walking distance, along realized circulation, front door → WC door (a ranking metric)
```

## 4. Requirements

### Functional
- **FR-1 Programme.** `ProgramRoom` gains `guest_wc: bool` — true for a `GUEST_WC` whose kind came
  from the brief (007), false for an `UNSPECIFIED`-derived `TOILET`. It decides whether C19 runs
  (decision B); it does not change what the planner tries.
- **FR-2 Concept.** A new placement rule in the concept generator: every `TOILET` is removed from the
  private stack and attached as a **pocket** to a public-access zone — first choice the entrance end
  of the HALL, then public circulation, then LIVING (decision C). Applies to every strategy (spine,
  double-loaded, front band, hub). When no pocket fits: a `guest_wc=True` room makes the strategy
  reject with a named `RejectionReason` (`NO_PUBLIC_POCKET`) — a WC in the bedroom corridor beside
  the family bathroom is the drawing this feature exists to stop; a `guest_wc=False` room falls back
  to today's private-stack row, so a count-only brief never loses a plan it has today (decision B,
  NF-1).
- **FR-3 Template.** `ProgramRole.TOILET` template becomes 1.5 / 2.0 / 3.0 m², short side 0.9,
  aspect ≤ 2.2, elasticity 0.0 — a WC never absorbs surplus. Design target (decision D): the row
  carries the same PRODUCT POLICY note as every other template, and a future regulation layer
  overrides it. `scale_program`'s headroom must not lift
  a zero-elasticity room above `max_area_m2` (the 7.8 m² case in §1 is the test).
- **FR-4 Doors.** The pocket has exactly one door, into its public-access zone; `generate_interior_doors`
  never places a second one. C17 (007) already enforces "from circulation" — a public-access zone
  counts as circulation for this purpose even when it is the living room (decision C).
- **FR-5 C19 — guest WC access semantics (fails closed).** For every `TOILET` with `guest_wc=True`:
  exactly one realized door, and the zone on its other side is a `PublicAccess` zone — never a
  bedroom, never the kitchen, never another wet room. Any such `TOILET` whose door or neighbour
  cannot be resolved **fails**. Not run when `guest_wc=False` (decision B). C19 says NOTHING about
  distance to the front door (decision A). `_STATEMENTS["C19"]`: "שירותי האורחים נגישים מהחלק הציבורי של הבית".
- **FR-6 Ranking.** Among candidates that pass every check, rank by (1) `EntranceDistance`, shorter
  first, then (2) wet adjacency (US4). Both are quality metrics; neither is ever a refusal. Eligibility
  is never re-decided after ranking (007 FR-8 contract carries over).
- **FR-6b Explicit proximity.** "ליד הכניסה" in the brief is extracted as
  `RoomRelationship(GUEST_BATHROOM, ENTRANCE, near, hard_requirement)` (§5) and enforced by C15 —
  the mechanism, the refusal code and the review row that exist today. This feature adds no second
  path for it.
- **FR-7 Review / chat.** 007's wet-room row shows the WC's realized access zone; an explicit
  "ליד הכניסה" appears in the relationships list as it does for any relationship (US6).

### Non-functional
- **NF-1 Baseline.** Failure-log sweep: for briefs with no `GUEST_WC` from the brief, LOST = 0 and
  every changed plan is listed with the WC's old and new position; nothing else may differ.
- **NF-2 Quality, not count.** "More scenarios plan" is not a success criterion; the built area vs.
  requested area comparison of the sweep is reported alongside (memory: planner gains must be
  quality-checked).
- **NF-3 Latency.** Sweep total within +5 %.

## 5. Extraction rules (parser prompt additions)
- "שירותי אורחים", "שירותים לאורחים", "שירותי כניסה" → `GUEST_WC, REQUIRED` (007 §5's table, unchanged).
- "שירותים ליד הכניסה", "שירותי אורחים ליד הכניסה", "שירותים קרוב לדלת" → the same `GUEST_WC` **plus**
  `room_relationships += (GUEST_BATHROOM, ENTRANCE, near, hard_requirement)` with the person's words
  as `source_text`. "עדיף ליד הכניסה" → the same with `preference`.
- "שירותים נוספים" / "עוד שירותים" with no location → `GUEST_WC, REQUIRED`, no relationship.
- Any other room named for the WC's location ("שירותים ליד המטבח") → a relationship as today; this
  feature adds nothing there.

## 6. Verification plan and gates
1. **Unit** — template band; pocket geometry; C19 pass (from hall / from living) and fail (from a
   bedroom / from the kitchen) fixtures; door count; headroom cap; ranking by `EntranceDistance`;
   parser test for "ליד הכניסה" → relationship.
2. **The 5 measured cases of §1** re-run: all ≤ 3.0 m², C19 passes, none beside `BATH_2`, and the
   `EntranceDistance` of each delivered plan is reported (target ≤ 4.0 m where a candidate exists).
3. **Sweep** (`spikes/failure_log_sweep/ab.py`, frozen worktree): NF-1, NF-2, NF-3.
4. **Stop for review** after 2, before 3 — the pocket rule is the risky part, and its effect on hub
   candidates (008) is unknown until measured.

## 7. Out of scope
- Anything 007 owns (kinds, ensuite host, C17, review of kinds).
- A second WC, a WC with a shower, a laundry/utility pocket — the vocabulary stays closed.
- Fixing the count-derived WC's *existence* for 2-wet-room briefs (that is 007 FR-5).
- Moving the family bathroom; wet-adjacency in general (memory gap #2 is its own feature).

## 8. Success Criteria *(measurable)*

- **SC-1** On the 5 measured cases of §1: WC net area ≤ 3.0 m² in 5/5 (today 4.6–7.8), aspect ≤ 2.2
  in 5/5 (today 2.5–3.7), and in 5/5 the WC and the family bathroom are in different columns/bands
  (today 0/5).
- **SC-2** On those 5 cases the delivered WC door is ≤ 4.0 m walking distance from the front door in
  every case where any passing candidate achieves it (today 8.1–11.6 m in 5/5).
- **SC-3** 0 delivered plans, primary or alternative, whose brief-named guest WC is entered from a
  bedroom, a kitchen or another wet room (C19; fails closed).
- **SC-4** Failure-log sweep: LOST = 0; every changed plan belongs to a brief that names a guest WC
  or is listed as "WC moved" with old and new position; nothing else differs (NF-1).
- **SC-5** Requested-vs-built area distribution of the sweep is not worse than the baseline (NF-2).
- **SC-6** A brief with "שירותי אורחים ליד הכניסה" shows the relationship on the review screen and is
  either satisfied (C15) or refused naming it — 0 silent drops.

### Success definition
A brief that names a guest WC gets a small room entered from the public side of the house — never
from a bedroom or the kitchen — and the drawing is refused rather than delivered when that is not
what was built; among the plans that qualify, the one nearest the front door wins, and "ליד
הכניסה" said out loud is enforced like any other relationship; every brief that never named a guest
WC is untouched.

## 9. Assumptions
- 007 lands first and delivers `GUEST_WC` as a kind, `TOILET` as its realization and C17; this feature
  reads those and adds nothing to 007's own gates.
- "Public side of the house" means, in this engine's vocabulary, the HALL/foyer, any circulation zone
  (including the 008 hub) and LIVING/DINING; KITCHEN is public but excluded by decision C.
- Walking distance is measured along realized circulation zones through realized doors — the same
  graph C5 uses for reachability — not as a straight line.
- The 1.5–3.0 m² / 0.9–1.2 m band is a design target for a WC with pan and basin; it is superseded by
  any regulation layer added later (decision D).
- The five §1 cases remain reproducible on the commit this feature branches from; they are re-run
  on that commit before any change so the "before" numbers are the feature's own, not this
  document's.
