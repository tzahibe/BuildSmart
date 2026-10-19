# DRAWING — the open plan is drawn (Issue #221, ROOT #220)

Branch `feature/open-plan-interface`, based on `origin/main` at `5b155d1`. Evidence: #213 (PR #219).

**What this measures, and what it does not.** The acceptance measurement here is a COUNT — how many
of #213's nine open-plan briefs the brain now draws as open plan — not a time. Several agents share
this machine, so every second in this report is incidental context, never evidence (standing rule).
Passing every validator proves nothing about architectural quality either; nothing below is an
architectural judgment — every number is read off a payload or a validator report.

---

## 1. The defect

`backend/app/vertical_slice/rectilinear_realizer.py`, in `realize_cells`:

```python
open_pairs: set[frozenset[str]] = set()        # created, never added to
...
# walls — the same precedence as `realize_layout`: OPEN (none here) > RC > EXTERIOR > PARTITION
```

`open_pairs` was created empty and never populated, so `Fixture.open_groups` was `()` on every plan
the brain produced, `GeometricDesign.open_groups` was `()`, the demo payload's `open_interfaces` was
`[]`, and `demo/contract.py:1008`'s `group_of` was empty — which is why `_open_corridor_to_public`
(`demo/contract.py:975`) could not fire either. The brain's second realizer, `realize_layout` (the
production *sizer*'s realizer, used whenever the exact sizer falls back), had an `open_pairs` of its
own, but it only ever carried **same-zone notch-carve seams** — fragments of one room — never a join
between two different rooms.

#213 measured the result: **0 open interfaces in 56 of 56 brain payloads; 0 of 9 open-plan briefs
drawn as open plan**, where production draws **9 of 9** (`concept_generator._build_access`:
`groups.append(tuple(public_ids))` when `open_plan and len(public_ids) > 1`).

## 2. Why this is not room fragmentation

The module records, in a comment above those very lines, *why* open walls were left out:

> (Splitting a partially-abutted cell into same-zone fragments was tried here and measured —
> C20/C9/C24/C31 run per cell and reject the fragments. Steps must land on cell boundaries — the
> sizer's alignment rule — and a layout that cannot is refused, never fragmented.)

That refusal is about **one room cut into pieces**. This Issue is the opposite case: LIVING and
KITCHEN are two **whole, separate cells** that already share a complete wall segment, and the work
is to type that one shared interface `OPEN`. Structurally:

* `_open_cell_pairs` only ever returns pairs of **existing** cells. It creates no cell, removes
  none, and subdivides none; `zone_of_cell` and `groups` (the notch-carve bookkeeping) are not
  touched, and every rectangle is unchanged. `test_opening_an_interface_creates_no_cell_and_moves_no_geometry`
  asserts exactly this: `out.rects == closed.rects`, `out.zone_of_cell == closed.zone_of_cell`,
  `out.groups == closed.groups == {}`, and the only difference in the whole wall map is two sides —
  one on each of the two cells — both now `OPEN`.
* The per-cell validators the comment names therefore still run on the same cells they always did.
  C20 (aspect) and C9 (furniture) measure whole rooms, not fragments; C24 (access topology) reads
  `Fixture.open_groups`, which is what tells it the pair is open-plan rather than a private chain;
  C31 walks the realized access graph, in which an OPEN interface is a legitimate connection
  (`validation.realized_connections` already accepted "a shared boundary whose facing wall sides are
  BOTH OPEN" before this Issue).
* The FULL-SIDE precondition is what keeps a `WallMap` side single-typed. A `WallMap` entry is
  `(zone, side) -> one WallType`, so an interface covering only part of a side would have to be part
  open and part solid — the same problem the comment refuses to approximate. `_open_cell_pairs`
  requires the shared boundary to cover the whole side of **both** cells, which also guarantees that
  side has no other neighbour on it, so removing the wall exposes nothing else. This is
  `geometry_core.engine._discover_open_interfaces`'s own non-optional precondition, mirrored rule for
  rule — including its skip of a safe room, whose envelope is RC on every side (C4/C33).

A declared pair the placement left only partially adjacent is **reported and left walled**, never
forced and never fragmented:

```
open plan not expressed between LIVING and DINING: they share 5.40 m of a 5.40 m / 7.40 m side,
and a wall side carries one type — the pair stays walled
```

## 3. How the intent reaches the realizer

Through the existing programme/pipeline contract, with no new side channel and no room named by the
code that builds the group:

| step | what carries it |
|---|---|
| the brief | `spec.program.open_plan_living` — the same bit production reads |
| the programme | `brain.proposer.Programme.open_plan`, and `Programme.open_group`: the public chain when open-plan living was asked for and there is more than one public room — **production's own rule** (`concept_generator._build_access`), applied to the brain's own `public` |
| the pipeline input | `band_pipeline.PipelineInput.open_groups`, beside `access_edges` |
| the exact sizer | `brain/exact_pipeline.py` -> `realize_cells(..., open_groups=inp.open_groups)` |
| the production sizer | `band_pipeline.run_band_pipeline` -> `RealizationIntent.open_groups` -> `realize_layout` |
| the realizer | `_open_cell_pairs` -> `WallType.OPEN` on both cells' shared side; `ConnectionKind.OPEN_CONNECTION` on the edge, so `generate_interior_doors` places no leaf (C6) |
| the design | `Fixture.open_groups` = the connected components **actually opened**, carried verbatim onto `GeometricDesign.open_groups` |
| the payload | the OPEN side's `construction` is `NONE`, so `demo/contract.py:_wall_segments` emits **no wall segment** and one `OpenInterface` instead |
| the drawing | `DemoPlan.tsx`: "an OPEN interface has no wall segment at all, so open-plan reads as one continuous space"; `PlanLegend` names it `מעבר פתוח — אין קיר כלל` |

**Nothing is hardcoded by room name.** The group is whatever `programme_from_spec` put in the public
chain (LIVING/DINING/KITCHEN on today's briefs), and any adjacent pair of its members is opened —
band, spine, stack or cells, since all four families go through the same `realize_cells`.

**One documented divergence from production.** Production's `public_ids` is every `ZoneGroup.PUBLIC`
room, which includes FLEX. The brain treats FLEX as a spare room off the circulation
(`Programme.private`), so FLEX never joins the brain's open group. On B02 and B05 production
therefore reports a `FLEX/KITCHEN` interface the brain does not; on the LIVING/DINING/KITCHEN pairs
the two engines name the same thing.

**Reported groups are the realized ones, not the declared one.** This is what keeps C6 ("no
artificial doors in open-plan") and C13 ("declared access topology is physically realized") true at
the same time: a member pair that could not be opened is simply not in any group, and keeps the
ordinary door it asked for.

## 4. The measurement — #213's nine open-plan briefs

Harness: #213's own, copied (not rewritten) from `origin/investigate/preview-comparison` —
`backend/app/ai_harness/comparison_corpus/` (corpus, runner, report) and
`backend/app/ai_harness/drawing_audit/` (payload `analyse`, `rasterise.mjs`), plus
`frontend/src/design/drawing-audit-render.test.tsx` and `backend/tests/ai_harness/test_comparison_corpus.py`.
Both engines are reached through one function, `demo.service.generate_demo_design`, with
`brain=True` being exactly what `?engine=brain` sets. No harness drawer anywhere.

The nine briefs are the ones #213's report names as asking for open plan: B02, B05, B08, B11, B13,
B16, B19, B20 and F5-garden-court (on its bounding rectangle, which is all the product can receive).

**BEFORE** is the same code with the declaration suppressed — `Programme.open_plan=False`, which
empties `Programme.open_group`, so `PipelineInput.open_groups` is `()` and both realizers take
exactly the path they took before this Issue (no pair found, every wall type and edge kind as it
was, `Fixture.open_groups` empty). It reproduces #213's finding: **0 of 9**.

### The count

| brief | before (declaration suppressed) | after | LDK doors before -> after | sizer that made the shown plan | validators |
|---|---|---|---|---|---|
| B02 | **none** | DINING/LIVING + DINING/KITCHEN | 2 -> 0 | exact (stack) | all 28 pass -> all 28 pass |
| B05 | **none** | KITCHEN/LIVING | 1 -> 2 | exact (band) | all 28 pass -> all 28 pass |
| B08 | **none** | DINING/KITCHEN + DINING/LIVING | 2 -> 0 | exact (band) | all 28 pass -> all 28 pass |
| B11 | **none** | DINING/KITCHEN | 2 -> 1 | exact (band) | all 28 pass -> all 28 pass |
| B13 | **none** | **none** | 2 -> 2 | production (band) | all 27 pass -> all 27 pass |
| B16 | **none** | **none** | 2 -> 2 | production (band) | all 27 pass -> all 27 pass |
| B19 | **none** | **none** | 2 -> 2 | production (band) | all 27 pass -> all 27 pass |
| B20 | **none** | **none** | 2 -> 2 | production (band) | all 27 pass -> all 27 pass |
| F5-garden-court (bbox) | **none** | DINING/LIVING+KITCHEN | 1 -> 1 | exact (band) | all 28 pass -> all 28 pass |

**DRAWN AS OPEN PLAN: 0 of 9 before, 5 of 9 after. The gate asked for at least 7 of 9, so the gate
is NOT met.** Nothing regressed: every brief that planned still plans, every validator that passed
still passes, and no brief lost a check (regression budget LOST 0 held). Where a brief gained an
open interface it also lost the doors that used to separate those rooms — B02 and B08 go from two
LDK doors to none. B05 shows a candidate change: the plan that now ranks first has one more LDK
door than the one that did before, which is `primary_signature_changes: tagged:open_plan` behaving
as declared (an OPEN side carries no wall inset, so net areas shift and the preference key with
them), and it is an open-plan brief.

### Why 5 and not 9 — measured, not guessed

The split is exact and it is not about the realizer:

* **5 of 5** briefs whose shown plan the EXACT sizer produced are now drawn as open plan.
* **0 of 4** briefs whose shown plan came from the production-sizer fallback are.

Those four — B13, B16, B19, B20 — fall back because `run_exact_pipeline` returns `NO_EXACT_PLAN`,
and that is **pre-existing**: the control run, with the declaration suppressed, takes the production
sizer on exactly the same four. This Issue did not cause it and does not change it.

On those four the public rooms are realized as a COLUMN of unequal-width rooms, and the realizer
says so per pair. B16, for instance:

| room | rect (x, y, w, d) in m |
|---|---|
| LIVING | 10.00, 2.00, 8.15, 5.10 |
| DINING | 14.75, 7.10, 3.40, 3.65 |
| KITCHEN | 14.05, 10.75, 4.10, 4.45 |

LIVING and DINING share 3.40 m — DINING's whole north side, but 3.40 of LIVING's 8.15 m south side.
A `WallMap` side carries exactly one type, so that side cannot be part open and part solid, and
`validation.realized_connections` only accepts a join whose two facing sides are BOTH `OPEN`. The
pair therefore stays walled, with the measurement in the plan's own notes:

```
B13:  open plan not expressed between LIVING and DINING: they share 3.90 m of a 8.05 m / 3.90 m
      side, and a wall side carries one type — the pair stays walled
B11:  open plan not expressed between LIVING and DINING: they share 5.40 m of a 5.40 m / 7.40 m
      side, and a wall side carries one type — the pair stays walled   (B11 still opened DINING/KITCHEN)
F5:   open plan not expressed between LIVING and KITCHEN: they share 5.55 m of a 7.75 m / 5.55 m
      side, and a wall side carries one type — the pair stays walled   (F5 still opened DINING/LIVING+KITCHEN)
```

and, on the plan itself, one line that says the brief was not delivered:

```
open plan was requested and is NOT expressed in this plan: LIVING/DINING/KITCHEN are walled
```

This is why production reaches 9 of 9 and the brain does not: production's GENERATOR builds the
open-plan rooms as tree siblings whose cut is full-width by construction
(`concept_generator._build_access`'s own docstring explains the CASED_OPENING choice for exactly
this reason), so the geometry always satisfies the precondition. The brain's partis do not place
them that way, and no amount of work inside the realizer can open a side that is only half shared
without either fragmenting a room (what the module measured and refused) or making a `WallMap`
side carry two types.

### The lever for the remaining four, and why it was not pulled here

It is SELECTION, and it is out of this Issue's scope. ROOT #220 puts the concept side — "partis,
critic, preference" — in #197, and this Issue's own scope is the realizer, the payload and the
renderer. The evidence, measured on the PRODUCT path — `generate_demo_design(project, brain=True)`, primary plus the
alternatives the product already puts on the board — for the four briefs that miss:

| brief | primary (shown first) | alternatives the product also shows | open plan available to the user at all? |
|---|---|---|---|
| B13 | BEDROOM_WING+FOYER — walled | BEDROOM_WING — walled; **TWO_HALL — DINING/KITCHEN + DINING/LIVING** | **yes, as an alternative** |
| B16 | SERVICE_CORE — walled | **PUBLIC_BAND — DINING/KITCHEN + DINING/LIVING** | **yes, as an alternative** |
| B19 | BEDROOM_WING+FOYER — walled | BEDROOM_WING — walled | no |
| B20 | SERVICE_CORE+FOYER — walled | **HALL_SPINE+FOYER — DINING/KITCHEN**; **HALL_SPINE — DINING/LIVING** | **yes, as an alternative** |

So on three of these four the brain ALREADY produces, and the product ALREADY draws, an open-plan
plan — it is simply not the one ranked first. Counting every plan the product puts on the board,
**8 of 9 briefs now have at least one plan drawn as open plan** (B19 is the only brief with none);
counting only the plan shown first, which is what the gate measures, it is **5 of 9**.

The brain's plan ranking (`runner._plan_key`) has no term for "the brief asked for open plan and
this candidate delivers it". Production's engine has exactly such a term —
`primary_selection._open_plan_violated`, a structural check, not a string match — and it is what
keeps production's primary honest on these briefs. Adding the analogous term to the brain's
ranking is a one-line-shaped change in a module this Issue may not touch; it is the single
recommended follow-up, and it is what would move this count from 5 to (measured) 7 or more.


## 5. Figures

Rendered by the PRODUCT's own path: `DemoPlan` + `PlanLegend` mounted on the real payload
(`frontend/src/design/drawing-audit-render.test.tsx`) and rasterised in chromium with the product's
stylesheets (`backend/app/ai_harness/drawing_audit/rasterise.mjs`). No harness drawer.

**The pair — B08, the headline.**

| before | after |
|---|---|
| `figures/open-plan-221/B08__before.png` | `figures/open-plan-221/B08__after.png` |

Before: מטבח, פינת אוכל and סלון are three rooms behind two internal walls with a door in each.
After: one continuous space across all three, no wall and no door between them, and the legend
gains its open-passage key — `מעבר פתוח — אין קיר כלל`. The envelope, the bedrooms, the hall, the
windows and the entrance are unchanged; the areas move only by the wall insets the removed
partitions no longer take (סלון 28.7 -> 29.0 m², פינת אוכל 17.3 -> 17.8 m²).

**The pair that still refuses — B16.**

| before | after |
|---|---|
| `figures/open-plan-221/B16__before.png` | `figures/open-plan-221/B16__after.png` |

Identical, deliberately: B16's shown plan comes from the production-sizer fallback and its public
rooms form a column of unequal widths, so the realizer refuses the opening and says why rather
than approximating it. This is the figure for the typed refusal, not a missing feature.


## 6. Tests

New: `backend/tests/vertical_slice/test_realize_cells_open_plan.py` — **15 passed**. It covers
AC-1..AC-3 and the payload half of AC-4, on a REAL exact placement (`embed_band` ->
`cells_placement` -> `cells_rects`, both orientations, production's own entrance screen), not a
hand-placed rectangle:

| test | what it pins |
|---|---|
| `test_the_closed_plan_is_the_defect_this_issue_fixes` | without a declaration, `open_groups` is `()` — the behaviour before this Issue, unchanged |
| `test_a_declared_open_pair_of_adjacent_cells_is_named_on_the_design` | AC-1: `Fixture.open_groups` and `GeometricDesign.open_groups` both name the pair |
| `test_the_brains_programme_carries_the_briefs_own_open_plan_intent` | AC-1's first half: B08's `Programme.open_group` is its public chain; with `open_plan_living=False` it is `()` |
| `test_the_shared_interface_is_open_on_both_cells` | AC-2: exactly one side of each cell is `OPEN`, and it is the side they fully share |
| `test_no_door_and_no_window_lands_on_an_open_interface` | AC-2: no door, no window — and the closed plan DID have that door |
| `test_the_open_pair_is_declared_open_connection_not_a_door` | the edge kind, so `generate_interior_doors` places no leaf |
| `test_the_unchanged_validators_pass_on_the_open_plan` | AC-3: `report.ok`, with C5/C6/C13/C24 among the passed |
| `test_opening_an_interface_creates_no_cell_and_moves_no_geometry` | **the fragmentation check** — same rects, same `zone_of_cell`, same (empty) `groups`, exactly two wall sides differ |
| `test_a_pair_the_placement_left_partially_adjacent_stays_walled_and_says_so` | AC-3's typed refusal: nothing re-typed, the note explains, the plan still passes |
| `test_a_member_absent_from_the_layout_is_simply_not_opened` | a declared member that is not a cell is skipped, not an error |
| `test_the_full_side_precondition_is_the_rule_discover_open_interfaces_uses` | the rule itself on synthetic rects: full match opens, partial reports, no contact is silent, a 3-chain opens its two touching pairs |
| `test_a_safe_room_is_never_opened` | C4/C33 — the RC envelope is skipped, as in `_discover_open_interfaces` |
| `test_the_realized_group_is_the_component_that_was_actually_opened` | `_open_components` |
| `test_the_demo_payload_carries_the_open_interface_and_drops_its_wall` | AC-4's payload half: `open_interfaces` names the pair, **no wall segment overlaps it**, no door between them; the closed payload has both |
| `test_the_brain_delivers_the_open_plan_an_open_plan_brief_asked_for` | end to end through `run_brain(sizer="exact")` on B08 |

Extended: `frontend/src/design/DemoPlan.test.tsx` — **69 passed** (67 before). Two added, in the
file that already owned the OPEN-interface case: the renderer draws both rooms and nothing on the
boundary they share (no wall line, no door leaf, no swing arc), and `PlanLegend` names the open
passage through `DemoWorkspace`.

Suites:

```
backend  (OPENAI_API_KEY=dummy WALLCLOCK_BUDGETS=off uv run pytest -q -p no:cacheprovider -n 4)
         4 failed, 2460 passed, 883 skipped, 10 xfailed, 4 warnings in 395.83s

         the 4 failures are all tests/test_local_gateway.py, on a missing `torch` — a known
         environment fact of this machine, stated and not fixed here.

frontend (npx vitest run)
         Test Files  24 passed | 2 skipped (26)
         Tests  244 passed | 2 skipped (246)
```

AC-6 (production's path untouched): no file under `concept_generator.py`, `concept_compilers.py`,
`concept_spec.py`, `geometry_core/` or `primary_selection.py` was changed, and
`test_the_production_sizer_is_untouched_by_the_seam` still asserts every geometry signature, sizer
and family it did before — it now additionally NAMES the only note that may appear on that path
(#221's brief-delivery disclosure) instead of asserting that no note appears at all.

`regression:corpus` — the frozen regression corpus, the whole of it, NOT skipped:

```
backend  TEST_MODE=REGRESSION OPENAI_API_KEY=dummy WALLCLOCK_BUDGETS=off
         uv run pytest -q -p no:cacheprovider -n 4 tests/regression_corpus
         856 passed in 2673.84s (0:44:33)
```

Nothing was committed while it ran (`corpus_snapshot` records `git rev-parse HEAD`, and a commit
mid-run fails `test_merged_shards_equal_single_node_snapshot` spuriously). It took longer than the
15-minute allowance because other agents were loading the same machine; it was let run rather than
skipped, since this is the check that proves the realizer change did not move a frozen plan.


## 7. Not verified / open

* **The gate is not met: 5 of 9, against the 7 of 9 asked for.** The realizer defect is fixed and
  general; the shortfall is in which plan the brain ranks first, which this Issue's scope excludes.
  Counting every plan the product shows, 8 of 9 briefs now have an open-plan plan on the board.
* **The recommended follow-up, measured:** give `brain.runner._plan_key` the term production
  already has (`primary_selection._open_plan_violated`) — prefer a candidate that delivers a
  declared open plan over one that does not, at the lowest precedence so it can never outrank
  circulation, the quality tier or the area budget. On B13, B16 and B20 the plan that would then
  rank first already exists and already draws correctly. B19 would still miss.
* **Not measured here:** the remaining 17 briefs of #213's 26 (this Issue's gate is the nine
  open-plan ones); the other #220 children (#222's landlocked hall, #223's parcel); request time,
  which is #214's and is not this Issue's evidence; and whether an architect prefers the new plans
  — #213's preference count would have to be re-run by a reader to say.
* **One run per brief.** The exact sizer is wall-clock bounded, so which parti wins can move
  between runs on a loaded machine; the counts above come from one product run per brief per arm.
  The STRUCTURAL facts (which pairs are fully adjacent, which are refused and by how much) do not
  depend on that, and the control was run the same way.
* **The harness is a copy, not a fork.** `comparison_corpus/`, `drawing_audit/`,
  `drawing-audit-render.test.tsx` and `tests/ai_harness/test_comparison_corpus.py` are byte copies
  of #213's files on `origin/investigate/preview-comparison` (PR #219, not merged). If #219 merges
  first these are the same content, not a second implementation.
* **`tests/test_local_gateway.py` fails on a missing `torch` in this environment** — a known
  environment fact, stated and not fixed here.

