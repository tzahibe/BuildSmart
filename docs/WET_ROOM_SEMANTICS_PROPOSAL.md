# Wet-room semantics — proposed policy and spec

Status: **PROPOSAL, not implemented.** Written 2026-09-13 after the C8 / `programme_variants`
investigation. Nothing in this document is in the code yet except the interim guard
`variant_keeps_bathroom_access` (never consume the last shared full bathroom), which this proposal
supersedes.

## 1. What was measured

The failure-log sweep (426 distinct request contexts) and a 216-cell envelope grid were run through
the real demo service under two policies: the shipped `programme_variants` ("hang the last shared
bathroom off the last secondary bedroom, always") and the interim guard.

| | shipped variant policy | interim guard |
|---|---|---|
| log scenarios planned | 138 | 107 |
| plans whose only/last shared full bathroom was private to a secondary bedroom | 45 (31 refused now + 14 redrawn) | 0 |
| C8 refusals (with the daylight ordering fix) | 0 | 0 |

Every one of the 45 was a **semantic violation of the brief**: a house in which no full bathroom is
reachable from circulation. Of the 31 that now refuse, 27 are synthetic `__CONFIG__` scenarios with
no brief text and the 4 text briefs ask for a master ensuite and/or a guest WC — none asks for a
second ensuite. The shipped policy was therefore never honouring a request; it was trading access
semantics for one fewer private row (~40 m² of footprint).

The bedroom envelope in `app/demo/scope.py` was measured **with** that policy in force. See §8 for
what survives without it.

## 2. Why the count is not enough

Today a wet room is a **count**. The parser prompt says so explicitly ("an en-suite described as part
of a bedroom still counts, and the count is the TOTAL for the house"), `ProgramSpec.wet_rooms: int`
carries only the number, and `build_room_program` re-invents the kinds from it:

- wet ≥ 2 and a master → the first is the master's ensuite;
- two or more shared → the first shared becomes a WC (`TOILET`), the rest full bathrooms.

So "חדר הורים עם שירותים, שירותי אורחים" (ensuite + guest WC) and "שני חדרי רחצה" (two shared
bathrooms) both arrive as `wet_rooms=2` and both become *ensuite + shared bathroom*. The parser
**does** recognise the words — its relationship vocabulary already has `ENSUITE` and
`GUEST_BATHROOM` tokens — but discards them on the way to the programme. The information the
policy needs exists at parse time and is thrown away.

## 3. Vocabulary

```
WetRoomKind
  SHARED_BATHROOM   full bathroom (shower/bath + WC), entered from circulation
  ENSUITE           full bathroom entered ONLY from its host bedroom (host: MASTER by default)
  GUEST_WC          WC + basin, entered from circulation, wants the entrance side
  UNSPECIFIED       counted by the brief, kind not stated (legacy / ambiguous)

WetRoomRequirement
  kind:     WetRoomKind
  host:     role token | None       ENSUITE only — MASTER_BEDROOM, or BEDROOM for a second suite
  strength: REQUIRED | FLEXIBLE     FLEXIBLE = the person said the placement does not matter
  source_text: str                  the words the parser read, for the review screen
```

`ProgramSpec.wet_rooms` (the count) stays; `ProgramSpec.wet_room_kinds: tuple[WetRoomRequirement, …]`
is added and may be empty (legacy). Invariant: `len(kinds) == wet_rooms` once the parser fills it,
padded with `UNSPECIFIED`.

## 4. Extraction rules (parser)

Same "never guess" contract as every other field:

| text | requirement |
|---|---|
| חדר הורים עם מקלחת / עם שירותים / אנסוויט | `ENSUITE, host=MASTER_BEDROOM, REQUIRED` |
| שירותי אורחים / שירותים לאורחים | `GUEST_WC, REQUIRED` |
| חדר רחצה / מקלחת (unqualified) | `SHARED_BATHROOM, REQUIRED` |
| חדר רחצה לחדר הילדים / לכל חדר שינה חדר רחצה | `ENSUITE, host=BEDROOM, REQUIRED` — an explicit second suite |
| "לא משנה איפה", "אפשר גם צמוד לחדר" attached to a wet room | that item `FLEXIBLE` |
| a count with no kinds ("3 חדרי רחצה") | 3 × `UNSPECIFIED` |

The review screen shows each item ("חדר רחצה משותף", "צמוד לחדר הורים", "שירותי אורחים") so the
person can correct a misread before anything is planned — the same principle that exposed the
`open_plan` negation bug.

## 5. Programme derivation (`build_room_program`)

1. Explicit kinds are honoured literally. Each `ENSUITE` is entered from its host; each `GUEST_WC`
   is a `TOILET` entered from circulation; each `SHARED_BATHROOM` is a `BATHROOM` entered from
   circulation.
2. `UNSPECIFIED` items are filled by today's defaults, in today's order (first → master ensuite when
   a master exists and there are ≥ 2 wet rooms; first shared → WC when ≥ 2 shared; rest shared
   bathrooms). This keeps every current plan for every current brief byte-identical.
3. **Invariant I1 — corridor access for the unstated.** If any item is `UNSPECIFIED`, the programme
   must contain at least one `SHARED_BATHROOM`. A WC does not satisfy it.
4. **Invariant I2.** A `GUEST_WC` is always entered from circulation.
5. **Invariant I3.** An `ENSUITE` is entered only from its host bedroom.
6. Explicit briefs that leave no shared full bathroom (e.g. `ENSUITE + GUEST_WC`, 2 bedrooms) are
   honoured, not refused — it is what was asked — and the review screen states the consequence
   ("לחדר השינה השני אין חדר רחצה עם מקלחת"). *Open question §9(a).*

## 6. Variant eligibility (`programme_variants`)

A variant is a different arrangement of the **same** requirements. It may convert a wet room from
`SHARED_BATHROOM` to `ENSUITE(host=secondary bedroom)` only when:

- that item is `FLEXIBLE`, **or**
- the brief explicitly asked for that ensuite — in which case it is not a variant at all but the
  literal programme (§5.1);

**and** invariants I1–I3 still hold afterwards.

Consequences:

- Legacy / `UNSPECIFIED` briefs never get the variant (they are not flexible). This is exactly the
  interim guard's behaviour and is what the 107-plan baseline measures.
- The variant becomes a real feature only once the parser emits `FLEXIBLE`. Until then it is
  dormant by design, not by accident.
- No rule refers to bedroom counts, footprints, or any scenario.

## 7. Ranking and enforcement

- Eligibility is decided in `programme_variants`, before `generate_concepts` sorts by area
  proximity. The sort ranks only semantically valid candidates; it can never promote an invalid one
  because none exists in the pool. (This is already true with the interim guard; the proposal keeps
  it and documents it as the contract.)
- **New validator C17 — bathroom access realized.** For every wet room, the realized door set must
  match its kind: `SHARED_BATHROOM` / `GUEST_WC` have a door from circulation and none from a
  bedroom; `ENSUITE` has a door from its host and none from circulation. Like C14 (corridor width),
  this makes the semantics a hard gate on the *drawing*, independent of which candidate won and of
  any future ranking change. It costs nothing on current plans — every literal programme already
  satisfies it.

## 8. What the envelope looks like without the violation

Measured on a 216-cell grid: bedrooms 1–6 × wet rooms 1–3 × safe room × six log-typical footprints
(11×12, 12.5×14.5, 12×18, 14×16, 18×12, 16×18 m; target area = footprint area; open plan), through
the real service with the scope guard lifted so the engine, not the guard, is measured.

| bedrooms | shipped policy (cells planned / 36) | of which violated I1 | interim guard |
|---|---|---|---|
| 1 | 3 (8 %) | 0 | 3 (8 %) |
| 2 | 13 (36 %) | 1 | 12 (33 %) |
| 3 | 25 (69 %) | 5 | 22 (61 %) |
| 4 | 19 (52 %) | 8 | 17 (47 %) |
| 5 | 16 (44 %) | 9 | 11 (30 %) |
| 6 | 15 (41 %) | 10 | 11 (30 %) |

By wet rooms (shipped → guard, of 12 cells): 3BR wet1 8→6; 4BR wet1 7→5; 5BR wet1 8→5, wet2 5→4,
wet3 3→2; 6BR wet1 6→5, wet2 5→3, wet3 4→3; all other buckets unchanged. Smallest planning footprint
at wet=2 + safe room: 2BR 14×16 (both); 3BR and 4BR 12.5×14.5 (both); 5BR 18×12 under the shipped
policy, **none of the six** under the guard; 6BR 12.5×14.5 → 14×16.

Failure-log scenarios, planned by bucket (shipped policy → interim guard):

| bedrooms | scenarios | shipped policy | interim guard |
|---|---|---|---|
| 1 | 95 | 9 (9 %) | 9 (9 %) |
| 2 | 91 | 42 (46 %) | 33 (36 %) |
| 3 | 95 | 45 (47 %) | 39 (41 %) |
| 4 | 92 | 24 (26 %) | 18 (19 %) |
| 5 | 31 | 13 (41 %) | 5 (16 %) |
| 6 | 22 | 5 (22 %) | 3 (13 %) |

Buckets that move (bed/wet, shipped → guard): 2/1 21→19, 2/2 10→4, 2/3 11→10, 3/1 15→10, 3/2 16→15,
4/1 11→6, 4/2 8→7, 5/1 6→3, 5/2 4→1, 5/3 3→1, 6/2 2→0. The 31 that refuse: 27 synthetic `__CONFIG__`
scenarios (no text) and 4 text briefs, none of which requests a second ensuite — all stay refused
under §6.

`SUPPORTED_BEDROOMS = (1, 2, 3, 4, 5, 6)` and the 4BR/5BR minimum-area claims in `scope.py` were
measured with the violation in force. **Support for 4, 5 and 6 bedrooms does not *depend* on the violation** — 47 % / 30 % / 30 % of grid
cells still plan under the guard, from the literal programme — but the **claimed minima do**:
"4BR/2wet 130 m²" (the 11×12 fixture) and "5BR/2wet 165 m²" were reached only by making the last
shared bathroom private. Under the guard the smallest 4BR/2wet/safe footprint in the grid is
12.5×14.5 (181 m²), and no 5BR/2wet/safe cell plans on any of the six footprints. Roughly half of
the 5BR and two-thirds of the 6BR plans the shipped policy delivered were I1 violations. The
`scope.py` comment and the three `test_demo_p0` fixtures therefore document the violation, not the
engine's honest envelope.

## 9. Open questions for review

- (a) §5.6 — an explicit `ENSUITE + GUEST_WC` brief with two bedrooms leaves the second bedroom
  without a shower. Honour with a review-screen note (proposed), or refuse with a clarification
  request?
- (b) How is `FLEXIBLE` expressed in practice — only from text, or also as a review-screen toggle
  ("גמיש") per wet room? Without a UI affordance the variant will almost never fire.
- (c) The three `test_demo_p0` 4BR/2wet fixtures at 13.2×10.2 m pin the violation. They should be
  re-based to footprints where the literal programme plans, once this policy is accepted.
- (d) `SUPPORTED_BEDROOMS` — keep 5 and 6 with the honest (lower) rates in §8, or narrow the guard?

## 10. Implementation order (after acceptance)

1. `WetRoomKind` / `WetRoomRequirement` in `spec.py`; `ProgramSpec.wet_room_kinds` (default empty).
2. `build_room_program` consumes kinds; `UNSPECIFIED` path byte-identical to today (sweep gate).
3. `programme_variants` eligibility per §6, replacing `variant_keeps_bathroom_access`.
4. Validator C17.
5. Parser field + prompt rules + review-screen rendering.
6. Re-base the three fixtures; re-measure and rewrite the `scope.py` envelope comment.

Each step gated by the failure-log A/B (LOST 0, pre-existing primaries byte-identical) exactly as the
daylight fix was.
