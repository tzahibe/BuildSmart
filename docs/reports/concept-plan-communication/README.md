# Concept Plan Communication Pass

Make the existing production concept plan professionally readable, without touching architectural
geometry, planning, validators or solver behaviour.

Scoped to the three evidence-backed findings of the Product Readiness Audit (PR #179), measured on
the same eight frozen briefs and the same sixteen plans, rendered through the real `DemoPlan`
browser path before and after.

## Result

| measure, over all 28 rendered plans | before | after |
|---|---:|---:|
| text collision pairs | **280** | **0** |
| collisions involving a room label | 211 | **0** |
| collisions involving a fixture label | 280 | **0** |
| room labels obscured by a furniture symbol | 85 | **25** |
| room labels over a door swing | 120 | 85 |
| fixture/furniture text tokens drawn | 438 | **0** |
| total text elements on the drawings | 1081 | 643 |

| capacity disclosure | result |
|---|---|
| over-capacity briefs where the warning is shown | **3 / 3** (B02, B06, B09) |
| within-capacity briefs where no warning is shown | **5 / 5** (B08, B11, B16, B19, B20) |

**The plans are geometrically identical.** Proven two ways, below.

---

## 1. Plan label readability

### What was wrong
The audit measured 280 text collisions across the audited plans. **Every one of them involved a
furniture or fixture label** — because the object's `kind` was printed at the object's centre and a
room's own name sits at the room's centre, so `SOFA` landed on `סלון` and `BED` on `חדר שינה`.

### What was done
Three changes, in order of effect:

1. **Fixture text became fixture symbols** (§2). This alone removed every text-text collision,
   because every collision had a fixture label on one side.
2. **Deterministic label placement.** `demoRoomLabel.roomLabelLayout` — the existing utility that
   already fitted a label inside its room — now also takes the obstacles the drawing actually
   contains: the furniture rectangles the engine placed in that room, and the quarter each door
   leaf sweeps (from the engine's own `hinge_x`/`hinge_y`/`swing_deg`). It evaluates each candidate
   layout (three-line / compact, upright / rotated) at each of 7×7 positions on the room's free
   axes and keeps the one covering the least obstacle area; ties go to the position nearest the
   centre, then to the richer three-line stack. No per-room-type offsets, no randomness, no
   dependence on obstacle order — all pinned by tests.
3. **Paint order.** `InteriorLayout` now draws *under* the room labels. Architectural information
   outranks contents, so a piece of furniture can never paint over a room's name.

The room is never resized to make a label fit, and a room too small to hold the block anywhere still
gets its label at the centre — it degrades, it never disappears.

### What remains
25 room labels still touch a furniture symbol and 85 still touch a door swing, out of 269. These are
rooms where the block cannot clear the obstacle at any position — small wet rooms, and labels beside
a door into a narrow room. The metric is strict: it counts any overlap of the text's bounding box,
which includes its whitespace. See §6.

## 2. Fixture and furniture communication

438 raw tokens were being printed on the drawings: `SOFA`, `BED`, `WARDROBE`, `COUNTER_RUN`,
`COOKTOP`, `SINK`, `TOILET`, `SHOWER`, `REFRIGERATOR`, `DINING_TABLE`, `COFFEE_TABLE`, `ISLAND`,
`FOCAL_WALL` — English implementation identifiers in an otherwise Hebrew plan. A professional plan
draws the sofa; it does not write `SOFA` across the living room.

Each of the thirteen kinds the current contract emits now renders as a conventional plan symbol
inside the rectangle **the engine already placed**: a bed with its pillow strip, a sofa with its
back, a toilet as cistern plus pan, a sink as a basin, a shower with its drain cross, a cooktop with
four burners, a wardrobe with the drafting diagonal, a counter run as a plain band. The object's
name moved into `<title>`, so it is still available as a tooltip and to screen readers, in Hebrew.

Nothing is invented: no object is added, moved, resized or guessed, and an object the backend did
not place is still simply absent. Symbols are drawn at the lightest weight on the sheet, which is
the convention the audit's reference sources establish — walls and openings heaviest, fixtures thin,
furniture lightest, so a reader can tell instantly what is building and what is contents.

## 3. Programme-capacity communication

The backend already computed the condition and already carried the sentence, but raised it as
`TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` — a refusal, which only fires when **nothing** plans.
On a successful generation the person received a plan far smaller than the number they typed, with
no explanation at all; on B09 that meant a 227 m² house for a 440 m² request containing a 54 m²
block labelled "unassigned".

Now:

- the sentence lives in exactly one place, `contract.capacity_notice_text`. Both copies that were
  inline in `demo/service.py` were removed and now call it, so the refusal and the notice can never
  drift apart. A test asserts the wording appears nowhere else;
- the capacity itself is still `concept_generator.program_capacity_gross_m2` — the formula is not
  duplicated, least of all in the frontend;
- on the success path it is attached to `QualityOut.capacity_notice`, the same additive shape as
  `laundry_notice` and `dead_space_notice`, and carried by **every** plan in the response, so it
  cannot appear and vanish as the person switches between alternatives;
- the workspace renders it as a note with `role="note"`. It is **not** a validation failure: the
  plan still passes, and the sentence never enters `validation.warnings`.

## 4. Proof that the plans did not change

**Backend.** All eight briefs were regenerated and compared field by field against the payloads
captured for PR #179: `rooms`, `walls`, `doors`, `windows`, `open_interfaces`, `footprint`, `plot`,
`gross_area_m2`, `net_area_m2`, `layout`, `garden`, `validation`, `outline`, `family`.

> **All eight product plans geometrically identical: True** — the only difference anywhere in the
> payload is the new `quality.capacity_notice`.

**Frontend.** Every drawn element in all 28 rendered SVGs was extracted and compared, excluding only
the fixture symbols, which changed by design.

> **28 / 28 plans: non-fixture drawn geometry byte-identical.** Room rectangles, walls, doors, door
> swings, windows, dimension lines, compass and scale bar are unchanged, to the attribute.

The snapshot guard in `PlanCanvas.test.tsx` fired, as it is meant to. Its diff is a single change:
`<g class="demo-layout">` moved from after the room labels to before them. Every coordinate in it is
identical.

**Selection is unchanged**: nothing in this milestone touches concept generation, scoring, ranking
or `select_proposal`.

## 5. Tests and suites

- `backend/tests/test_capacity_notice.py` — 10 tests: the wording in one place, both numbers named,
  no notice when the request fits or when there is no target, the disclosure on the real success
  path for the two over-capacity briefs and its absence on the two that fit, that it is never a
  validation failure, and that every alternative carries the same sentence.
- `frontend/src/design/demoRoomLabel.placement.test.ts` — 9 tests: centred when nothing is in the
  way, moves off a covering symbol, deterministic, independent of obstacle order, stays inside its
  room, still labels a room too small to dodge anything, never mutates the room, and the door-swing
  obstacle is the engine's own quarter and is absent when the engine decided no swing.
- `InteriorLayout.test.tsx` — rewritten to the new contract while keeping its boundary: one symbol
  per object at the object's own footprint, identified by `data-kind` and a Hebrew `<title>`, no
  text on the drawing, every symbol inside the placed rectangle.
- `DemoPlan.test.tsx` — 3 tests for the disclosure: shown verbatim, absent when the brief fits,
  presented as a note and never as a warning.
- `test_demo_p0.py`'s additive-contract guard updated for the new `quality` key, in the same shape
  as `dead_space_notice` before it.

**Full backend suite: 2324 passed, 0 failed, 883 skipped, 9 xfailed. Frontend suite: 231 passed, 1 skipped.**

## 6. Remaining blocker before another milestone

One, and it is a presentation residue rather than a defect: **25 room labels still sit on a
furniture symbol and 85 still touch a door swing.** In every remaining case the room is too small
for the label block to clear the obstacle at any position. Closing it would need something this
milestone deliberately excluded — a leader line to a label outside the room, or an abbreviated label
for very small rooms. Both are real options; neither is justified by evidence yet, and both would be
a new convention rather than a fix.

Everything else the audit named is addressed: there are no text collisions left, no English tokens
on the drawing, and the capacity mismatch is disclosed exactly on the briefs that have one.

## 7. Scope kept

No Geometry Core change. No room sizing, topology, selection, scoring or validator change. #142 not
integrated and untouched. No frontend redesign — three components and two stylesheets. No new
architectural semantics and no construction-document detail: every quantity drawn was already in the
contract. No new ranking logic.

**Artefacts.** `figures/` (eight before/after sheets and all 28 after-plans) ·
`data/measure_before.json`, `data/measure_after.json` (per-plan collision measurements).
