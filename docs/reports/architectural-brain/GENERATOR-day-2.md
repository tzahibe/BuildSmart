# Screen-aware, bound-aware generator for the exact path — day 2, the frozen six (#208, 2026-10-18)

Branch `feature/exact-generator`, on top of `main` 5b155d1 (#206). Row 2 of the #197 execution-plan
table: the #200 limit. Module `backend/app/vertical_slice/exact/generator.py`; harness family
`generator` in `app/ai_harness/shape_agnostic/run.py` (ON there, `SHAPE_AGNOSTIC_GENERATOR=0`
turns it off); pipeline family `"generator"` in `brain/exact_pipeline.run_exact_pipeline` (not in
`ALL_FAMILIES`, not in `service.BRAIN_FAMILIES` — the preview is unchanged). Same harness, same
objective (`SHAPE_AGNOSTIC_OBJECTIVE=target`), same validators and area verdicts as #200's
`CELLS-DAY-2-gate.md`; data `data/generator-day2-target/` (per-case `results.json`, `run.log`,
every realized plan's design JSON, merged `results.json`); figures `figures/generator-day2/`
(`<case>__<parti>__<family>.png`, the product's own `DemoPlan`). The five cases ran concurrently on
one machine, so the per-case seconds are inflated against #200's sequential runs.

## Gate verdict: **STOP**

Room-area deviation ≤ 15 % in at least 3 cases, without losing any previously solved case:

| case | #200 best (family) | now best (family / parti) | circ | smallest bedroom | gross | generator's own best | generator plans counted | ≤ 15 % |
|---|---|---|---|---|---|---|---|---|
| F1 rect | **6.3** (spine) | **6.3** spine / BEDROOM_WING V | 13.4 | 99 % | 81.5 % | 11.2 % (TWO_HALL+FOYER, living two rows) | 71 / 71 | ✓ |
| F2 L | 16.9 (stack) | 16.9 stack / BEDROOM_WING H | 12.8 | 74 % | 86.6 % | 17.2 % (BEDROOM_WING, hall down three rows) | 22 / 22 | ✗ |
| F3 wide-shallow | 31.9 (spine) | **19.5** generator / HALL_SPINE+FOYER H | 18.3 | 66 % | 107.4 % | 19.5 % | 12 / 26 (14 AREA_OVER_TOLERANCE) | ✗ |
| F4 entry court | 18.7 (band) | 18.7 band / PUBLIC_BAND H | 17.2 | 64 % | 85.8 % | 28.0 % (BEDROOM_WING+FOYER, kitchen two rows) | 18 / 18 | ✗ |
| F5 garden court | 23.6 (band) | 23.6 band / BEDROOM_WING H | 14.0 | 79 % | 80.0 % | 28.5 % (TWO_HALL, dining two rows) | 72 / 72 | ✗ |

**1 of 5 under 15 % (gate: 3). No previously solved case lost** (5/5 solved; the other four
families' counted plans are #200's: band 8/1/0/2/2, spine 4/0/1/1/0, stack 6/1/0/5/4, cells
7/1/0/0/3 — one stack plan fewer on F1 and F5, one band plan fewer on F5, inside the budgets'
noise; every best-by-case plan is the same plan as #200's except F3). The gate says STOP, so this
stops here: no day 3, the family stays OFF in the preview, nothing is retuned to buy a case back.

What moved: **F3 31.9 → 19.5 %**, the generator's own plan — the first counted plan on the
24 × 9.5 m strip that is not the spine's 31.9 % — and the generator counts plans on **every** case
(195 of 215 realized; #200's cells family counted on F1, F2 and F5 only). What did not move: F2 and
F4, where the generator's best (17.2 / 28.0 %) sits beside or behind the stack's and the band's.

## What was built (one module, no shape named)

`generate(zones, required, access, wet_rooms, envelope, *, arrival, orient_tag)` yields
`CellLayout`s (#200's representation: rows of zone ids, a zone in consecutive rows spans them —
band, spine, stack and two-row rooms are all instances) that already pass the screens and the
room bounds, in a deterministic DFS from the hub outward, bounded by a node budget and a deadline:

* **Screens at generation time** (`layout_rejections`, claimed as `SCREENS`): the parti's own
  arrival room is in the street row (H) or first in its row (V); for a foyer parti no hall fronts
  the street (a hall outranks a foyer for the door, `ENTRANCE_ZONE_PRIORITY`, and the foyer would
  be #205's blind stub beside the entrance); `screens.cells_selection` (entrance feasible, foyer
  fronts, every REQUIRED-exposure room and the safe room exterior); every direct-access pair a
  possible contact and a legal door pair (`band_pipeline._legal`); every room reachable from the
  arrival room through legal required contacts. The enumerator applies the structural parts while
  assigning rows (a middle-row exposure room must be a row end, so at most two per row; a row's
  induced required graph must be a linear forest; interchangeable rooms — four bedrooms off the
  hall — are assigned in order, one representative per permutation). For a plain band layout,
  production's own `hard_rejections(placement_flags(...))` agrees with the verdict (test).
* **Room bounds before any MILP** (`precheck`, `cell_bounds`): per cell the sizer's own depth
  range (`band_sizing._height_bounds` with the insets `milp_cells._insets` will assign), the
  oracle's entrance rule and the #205 foyer group as per-depth admissibility on a fronting
  circulation cell, `HALL_MIN_WIDTH_M` on a spanning one; then a walk of the sizer's own
  `_height_grid` (k = 6) over the rows — every row's cells' least integer gross widths at that
  depth, the sum held to the intersection of the cross-sections the row covers, a spanning cell at
  its summed depth — with the contact rule relaxed in (same-row pairs: the shared rows' depth is
  at least the door's need; a cell with k required neighbours in the adjacent row covers the k − 2
  narrowest plus two door needs). Applied order-free to every zone-to-row assignment before an
  order is enumerated, and to every ordered layout before the MILP.
* **Search where the embedder's order does not look**: row counts from the programme's own
  estimate (area over the frame's width at ~4 m per row) outward to six; the hall may run down up
  to four rows (the spine), the public rooms across two; same-tier stacks of every layout.

Measured cost and agreement (`tests/vertical_slice/test_generator.py`, and the same comparison
over 80 band candidates and their moves per case in both orientations):

| case | layouts compared | MILP screen feasible | pre-check refuses | refuses only MILP-infeasible | pre-check | MILP screen |
|---|---|---|---|---|---|---|
| F1 | 160 | 59 | 91 | yes | 0.7 ms | 20.6 ms |
| F2 | 144 | 0 | 144 | yes | 0.8 ms | 4.9 ms |
| F4 | 28 | 0 | 28 | yes | 0.9 ms | 5.6 ms |
| F5 | 160 | 5 | 149 | yes | 0.7 ms | 3.3 ms |

(F3's embedder gives one screened candidate.) The pre-check never refused a layout the MILP
screen accepts — it is a relaxation and the test keeps it one — and it refuses 57–100 % of the
embedder's own candidates at 1/5 to 1/30 of the MILP screen's cost.

## Where it stops, by evidence

**The funnel per case** (harness stages; "screen" = `milp_cells` with no objective at the loosest
rung, k = 6, 2 s; "sizing" = `cells_placement` with the target objective up the ladder):

| case | layouts emitted | screen feasible | sized (FEASIBLE / INFEASIBLE) | realized | counted | generator seconds |
|---|---|---|---|---|---|---|
| F1 | 733 | 170 (23 %) | 96 / 564 | 71 (20 NO_ENTRANCE, 5 VALIDATION_FAILED) | 71 | 64 |
| F2 | 2 261 | 44 (2 %) | 22 / 154 | 22 | 22 | 86 |
| F3 | 301 | 139 (46 %) | 38 / 518 | 26 (12 VALIDATION_FAILED) | 12 (14 AREA_OVER_TOLERANCE) | 348 |
| F4 | 1 198 | 216 (18 %) | 36 / 828 | 18 (18 VALIDATION_FAILED) | 18 | 222 |
| F5 | 452 | 148 (33 %) | 84 / 506 | 72 (12 VALIDATION_FAILED) | 72 | 22 |

Three facts, in order of weight:

1. **The pre-check passes what the MILP then refuses, and the gap is the x-positions.** On F2 the
   enumerator refused 6 926 of 6 948 zone-to-row assignments and 191 of 211 ordered layouts before
   any MILP (HALL_SPINE+FOYER, H, 8 s), yet of the 2 261 layouts it emitted over ten partis the
   MILP screen accepted 44. The relaxation sees depths, widths and the door needs; it does not see
   that every row is one left-to-right sequence sharing boundary nodes with its neighbours (the
   staircase), nor the alignment rule. Dropping the pre-check's own width bound per row would not
   change the verdict — those 2 217 refusals are the sizer's, not the relaxation's — but the
   screen rate says the cheap pre-check is not the bound-aware part that matters on the L; the
   feasibility MILP (5 ms) is.
2. **Where the generator's plans realize, the street row is 3.0 m deep and every room in it pays.**
   Every generator plan of a foyer parti on F1–F4 has its street row at 3.00–3.10 m: the #205
   foyer group on the single-row CIRCULATION cell (net ≥ 1.9 m each way, depth ≤ 1.5 × width,
   deeper than wide, ≤ 9 m²) admits a street-row depth between ~2.75 and ~3.3 m gross, and the
   MASTER / LIVING / KITCHEN that the screens put beside the foyer are then 3 m deep —
   F3: LIVING 18.0 / 43 m² (−58 %), MASTER 14.7 / 20, KITCHEN 12.7 / 20, ENTRY 9.0 / 5 (+80 %);
   F1 TWO_HALL+FOYER: MASTER 11.8 / 20 (−41 %), ENTRY 8.7 / 5 (+74 %); F4: MASTER 11.1 / 20,
   BATH_1 / BATH_2 4.8 / 12 (−60 %), ENTRY 8.4 / 5. A foyer that shares a band's depth is a
   constraint on the band, not on the foyer. The plans without a foyer show the same shape from
   the other side: F2 BEDROOM_WING's hall down three rows is 2.95 × 8.75 m (+75 %) and its living
   room 5.50 × 3.00 (−60 %); F5 TWO_HALL's hall is 2.90 × 3.00 (−47 %).
3. **The layouts that fit are the shallow ones.** The generator reaches row counts and
   assignments the embedder does not (F3's 19.5 % plan is three rows of 6 / 4 / 4 rooms with the
   hall 8.10 × 2.70 m across the middle — the embedder's screened candidates for F3 number one),
   but on F2 and F4 the layouts that pass the sizer are 3–4 rows at ~3 m each in a 16 m / 11 m
   depth, and the public rooms are wide and shallow. The gate measure is room deviation; the
   search found feasible layouts, not proportioned ones, and proportion at a fixed row structure is
   what the sizer's objective buys — it cannot buy a 46 m² living room in a 3 m row.

What the evidence does **not** show: that no layout under 15 % exists on F2 / F3 / F4. The
enumeration is budgeted (node limits per row count, 120 layouts per orientation per parti, 60 s
per parti), the stacks are only same-tier pairs, and the hall is the only cell allowed to span more
than two rows.

## What the drawing shows

`figures/generator-day2/F3-wide-shallow-free__HALL_SPINE+FOYER__generator.png` — the plan the
generator found on the 24 × 9.5 m strip, drawn by the product: the front door opens into a
2.90 × 3.10 m foyer on the street, the foyer into an 8.10 × 2.70 m corridor across the middle of
the house, the five bedrooms, the safe room and the wet rooms off it on both sides, every bedroom
with a window — the entrance sequence and the exposure the spine's 31.9 % plan did not have. And
the public rooms are the street row's leftovers: a 5.80 × 3.10 m living room (18 m², target 43),
a 4.10 × 3.10 kitchen, a 6.00 × 2.60 dining room at the back — a corridor house with a small front
room, which is the 19.5 % in one picture. The F2 / F4 figures (`…__BEDROOM_WING__generator.png`,
`…__BEDROOM_WING+FOYER__generator.png`) show the same: rooms placed and served correctly, the
public rooms one shallow row deep.

## Where this sits on the path to execution

Row 2 of the #197 table ("screen-aware generator — B16/B19-class briefs get an exact plan at all;
gate ≥ 3 cases ≤ 15 %") moves to **measured: STOP at day 2**. What it bought, measurably: a
generator that emits only screen-passing layouts (0 of 4 945 emitted layouts failed a screen,
against #200's ≈ 55 %), refuses most sizer-infeasible assignments in a millisecond, counts plans on
every case, and lowers F3 from 31.9 to 19.5 %. What it did not buy: a second case under 15 %.
The family is OFF in the preview; day 3 (the eight briefs, B16 / B19 / B09) does not run.

**The next blocker is not search.** It is the foyer's depth coupling: the one rule that makes the
front door's room a room (#205) sizes the whole street band to the foyer's window, and the
generator's layouts — which always put the arrival room on the street, as the preference demands —
inherit it on every foyer parti. A foyer that does not share its band's depth (a sub-row member
beside a full-depth neighbour — the stack form, with the entrance rule on the member; or a foyer
one row deep inside a two-row public room) is a representation question for `milp_cells` and the
#205 group, not a generator one. The second blocker, for F2 / F4 specifically, is the sizer's own
feasibility screen as the candidate filter (5 ms, 98 % refusal on the L): the relaxation cannot
carry the staircase, so the generator should call the screen per emitted layout before spending
its budget on orders of a refused assignment. Row 3 (the request-time budget) and the preview
deploy are untouched.

## Changes

* `backend/app/vertical_slice/exact/generator.py` — new: `depth_frame`, `CellBounds` /
  `cell_bounds`, `precheck`, `layout_rejections`, `generate` (with `stats=` reporting nodes,
  labelings, refusals, emitted), same-tier stacks.
* `backend/app/vertical_slice/brain/exact_pipeline.py` — family `GENERATOR_FAMILY = "generator"`
  (not in `ALL_FAMILIES`): the loosest rung's bounds drive the enumeration, the feasibility MILP
  screens each layout (`GENERATOR_SCREEN_S`), `cells_placement` sizes up the ladder, `realize_cells`
  and the unchanged validators, `ExactPlacement("generator", rows=..., label=...)`.
* `backend/app/ai_harness/shape_agnostic/run.py` — `_generator_family`, step 7, ON by default
  (`SHAPE_AGNOSTIC_GENERATOR=0` to skip), 60 s per parti.
* `backend/tests/vertical_slice/test_generator.py` — 14 tests: every emitted layout passes the
  screens it claims (and production's `placement_flags` agrees on plain band layouts, both
  orientations); the pre-check never refuses a MILP-feasible layout on the frozen five; what cannot
  fit is refused; determinism and the row-count order; the deadline; the family OFF unless asked
  for and naming its maker when ON; `service.BRAIN_FAMILIES` unchanged.
* Production path untouched; `run_brain(sizer="production")` byte-identical per parti (existing
  test). The oracles' entrance/foyer rules, `band_sizing`, the validators, the critic and
  `brain/runner.py`'s preference are not changed.
