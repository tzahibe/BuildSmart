# The preference sees the foyer — the arrival room's usability in the rank key, and the street rules in the V orientation (#207, 2026-10-18)

Branch `feature/foyer-preference`, on top of #206 (`50e8677` = #204 + the "foyer" group in the three
exact oracles). Two mechanisms the owner named on 2026-10-18 ("execute" on #205's recommendation),
and a measurement of both on the same eight real briefs, four configurations and harness as #206
(`PREVIEW-foyer-geometry.md`, whose data is the BEFORE baseline here). Data
`data/preview-foyer-preference/` (metrics, designs, `run.log`, `diag-after.json` — every accepted
plan per brief/configuration with its arrival room's usability, and every street-fronting exact
placement with its validator outcome), figures `figures/preview-foyer-preference/<brief>__<config>.png`
(`…-bydev.png` is the lowest-deviation plan, kept for comparison).

## What was built

**1. The arrival room's usability in the preference** (`brain/runner.py`). `arrival_usability(realized)`
reads the room the realized front door opens into (`_arrival_zone`) off the realized geometry —
`RoomOut.net_w_m` (net width along the street wall) and `net_h_m` (net depth away from it), the
rect as drawn, net of walls, as the sizer defines net; the realizer always puts the street at
y = min, whichever orientation the oracle solved in — and is 0 when net width ≥ `FOYER_MIN_NET_M`
(1.9 m) and net depth / net width ≤ `FOYER_MAX_DEPTH_TO_WIDTH` (1.5), else 1. The constants are
imported from `exact/milp_oracle.py`: one source of truth, so the preference's line is exactly the
sizer's. `_proportion_preference` (#201) places it at key 3:

    (arrival ok, street ok, area in tolerance, **arrival room usable**, room deviation %, circulation %,
     −garden rooms, |gross − requested|, circulation m², worst wet aspect)

The owner's three architectural priorities (2026-10-14) stay first and verbatim — the term sits
after area tolerance, which is a promise to the brief, and before every proportion, so a plan whose
front door opens into a strip ranks below one whose arrival room is a lobby whatever the rooms
behind them measure; between two lobbies, or two strips, the deviation decides as before. Hard
constraints are never in play: only validator-accepted candidates are ever ranked. The term is
coarse (0/1) on purpose — it is a line between a lobby and a strip, not a size to optimise.
`_key_text` names it ("arrival room usable" / "a STRIP") and the exact-vs-production notes now say
which key decided (`_decided_by`): "exact sizer's band plan ranked below production's on arrival
room (…)".

The same preference orders candidates inside `run_band_pipeline` for the production-sized partis,
so the brain·production column can change its pick within a parti's pool too; the production
sizer itself (`band_sizing.py`) and the validators are untouched and `run_brain(sizer="production")`
is byte-identical per parti (existing test).

**2. The street side in the three exact oracles** (`exact/milp_oracle.py`, `exact/milp_cells.py`).
`exact_pipeline` sizes every layout twice: as production orients it ("H", the envelope as is) and
on the transposed envelope ("V"), transposing the rects back (`transpose_rects`: x ↔ y). In V the
oracle's row 0 lands on the house's WEST side, and the cells that front the street are each band's
FIRST cell — the reading `screens.cells_selection` / `spine_selection` already give the V
orientation. The oracles did not know this: the three-door-widths entrance rule and the foyer
group were applied to the west band's circulation cell (row 0) and never to the fronting ones.
Every oracle now takes `street` (`STREET_SIDES = ("N", "W")`): "N" is row 0 fronts — byte-identical
to before, every #206 pin passes unchanged; "W" is each band's first cell fronts, with the cell's
frontage read as its band's height and its depth from the street as its width:

* band `milp_heights` and spine `_spine_once`: `_foyer_constraints_v` — net depth ≥ 1.9 m
  unconditionally, grid heights whose net frontage is under 1.9 m switched off, net depth ≤ 1.5 ×
  net frontage at every admissible height and, for the foyer proper (CIRCULATION), net depth ≥ net
  frontage + 1 u; plus `_entrance_frontage_v` — grid heights under three door widths switched off
  for a band whose first cell is circulation (in the N frame the door's wall is the band's whole
  width, which the rooms in it already make wider than three doors; in the W frame the wing's
  frontage is the band's height and nothing else bounds it);
* spine: the spine's own entrance rule along its HEIGHT (the section's summed heights) when a
  section band has no left part — that is when the spine fronts in V; the spine stays exempt from
  the foyer group (a declared corridor, `SPINE_MAX_ASPECT`);
* cells `milp_cells`: the same three bounds with frontage/depth swapped (every cell's H is linear
  there), the entrance rule on the frontage expression; a circulation cell spanning rows stays a
  corridor (`HALL_MIN_WIDTH_M`), not a foyer.

`exact_pipeline.py` changes by five lines: `street = {"H": "N", "V": "W"}` and `street=street[orient_tag]`
at the four oracle calls (band, spine, stack, cells). The family loops, `screens.py` and the
candidate order are untouched (#208 owns those). An unknown side is refused (`ValueError`).

So the V family does front the street — it is not "never by construction": #205's diagnostics
counted 11 V-orientation placements with a circulation cell on the street line (band, spine and
cells), 1 realized. The before/after of those is in the V section below.

## Gate verdict: **STOP**

Measured against #206's numbers, as the contract says. The measurement was run twice on this
branch (identical plans and keys both times; `run-1-loaded.log` / `metrics-run-1-loaded.json` kept)
and once more with #206's own code (`50e8677`, exported as plain files) through the same harness
in the same session — `before-same-session/` — because every column, including production's
untouched code, came out 30–40 % slower than on 2026-10-17 (load averages 1.5–3.1: #208's worker
shares this machine). The control is what the change is responsible for; the contract's clauses
are what they are.

| criterion | result |
|---|---|
| no shown-first plan has a strip arrival room where a usable-foyer plan of the same brief passed validators | **FAILED — B11.** Both exact columns show the production-sized `HALL_SPINE+FOYER` plan with a 1.70 × 4.25 m strip foyer (28.4 % deviation); #206 and the same-session control both realize that parti's exact plan with a 1.95 × 2.90 m usable foyer (22.9 %), which passes the validators. The mechanism is traced below: it is the V-orientation fix spending the budget, not the preference. The other strip arrivals shown first (B08 brain·production 2.30 × 4.65 hall; B20 1.50 × 3.40 foyer in three columns) have no usable-foyer plan of the same brief in any run — the key chose the best there was. |
| mean room deviation of the shown-first plan no worse than #206's by more than 1 point (#206: 15.8 / 16.2 / 14.3 / 13.8) | **FAILED on the all-families column.** After: 15.8 / 16.8 / 15.2 / **15.2** — +0 / +0.6 / +0.9 / **+1.4**. The same-session control gives 15.8 / 16.2 / 14.3 / 15.1 for #206's code today (B02's stack plan and B06's exact plan no longer fit the budget on this machine), so against the control the deltas are +0 / +0.6 / +0.9 / +0.1; the clause is written against #206 and fails by 0.4. |
| max request time ≤ 31.4 s | **FAILED as measured: 35.0 s** (B16, all families). The control measures #206's own code at **39.1 s** today (B16 band) and production's untouched path at 14.2 s where #206 recorded 10.0 s; the change itself adds no time (B16 never reaches the exact sizer — every placement is INFEASIBLE at the embedding, the #200 limit — and its 34.8 s is `run_band_pipeline` alone). |

So STOP, per the contract: no second mechanism, no retuning. What the measurement says, honestly:
the preference does what it was asked (B06, B08 below); the V-orientation fix makes the V
family real, and on a brief where production leaves the exact sizer 6 s of the 30 (B11) one
real V solve costs the plan the H orientation would have found. The branch is a measured,
reversible option; the mechanism that decides B11 is the family loop's H-then-V order inside one
shared budget, which is #208's file and a change of its own.

## Results — the plan the product shows first, before (#206) / after

Room deviation from target % / circulation share % · arrival room and its net width × depth (m)
· usable / STRIP by the sizer's line · seconds for the whole request · sizer. Bold = changed.

| brief | column | before (#206, 2026-10-17) | after (#207) | |
|---|---|---|---|---|
| B08 | production | 3.9 / 12.7 · HALL 1.30 × 11.70 STRIP · 0.3 s | same · 0.4 s | same |
| B08 | brain · production sizer | 9.0 / 9.0 · HALL 2.30 × 4.65 STRIP · 1.7 s | same · 2.7 s | same |
| B08 | brain · exact, band | 5.1 / 14.1 · CIRC 2.00 × 3.00 usable · 30.3 s exact | same · 25.4 s exact | same |
| B08 | brain · exact, all | 5.1 / 14.1 · CIRC 2.00 × 3.00 usable · 25.1 s exact | same · 30.3 s exact | same |
| B20 | production | 12.5 / 12.0 · HALL 1.20 × 11.70 STRIP · 0.2 s | same | same |
| B20 | brain · production sizer | 22.2 / 15.8 · CIRC 1.50 × 3.40 STRIP · 7.3 s | same · 9.6 s | same |
| B20 | brain · exact, band | 16.2 / 23.7 · HALL 3.40 × 8.15 STRIP · 22.4 s exact | **22.2 / 15.8 · CIRC 1.50 × 3.40 STRIP · 25.8 s production** | **worse** |
| B20 | brain · exact, all | 22.2 / 15.8 · CIRC 1.50 × 3.40 STRIP · 31.1 s production | same · 30.5 s | same |
| B02 | production | 23.6 / 11.5 · HALL 1.30 × 11.15 STRIP · 3.1 s | same · 4.0 s | same |
| B02 | brain · production sizer | 7.4 / 10.3 · HALL 4.90 × 3.00 usable · 0.5 s | same · 0.7 s | same |
| B02 | brain · exact, band | 7.4 / 10.3 · HALL 4.90 × 3.00 usable · 16.1 s production | same · 25.3 s | same |
| B02 | brain · exact, all | 2.0 / 9.4 · HALL 6.15 × 2.25 usable · 30.1 s exact/stack | **7.4 / 10.3 · HALL 4.90 × 3.00 usable · 32.4 s production** | **worse** (control: same loss) |
| B11 | production | 22.0 / 10.9 · HALL 1.20 × 13.75 STRIP · 10.2 s | same · 13.3 s | same |
| B11 | brain · production sizer | 28.4 / 19.4 · CIRC 1.70 × 4.25 STRIP · 17.2 s | same · 22.7 s | same |
| B11 | brain · exact, band | 22.9 / 13.8 · CIRC 1.95 × 2.90 usable · 26.3 s exact | **28.4 / 19.4 · CIRC 1.70 × 4.25 STRIP · 28.1 s production** | **worse** |
| B11 | brain · exact, all | 22.9 / 13.8 · CIRC 1.95 × 2.90 usable · 30.9 s exact | **28.4 / 19.4 · CIRC 1.70 × 4.25 STRIP · 30.4 s production** | **worse** |
| B16 | all four | 14.4 / 10.1 · HALL 1.20 × 14.30 STRIP · 10.0 s; brain 21.4 / 13.5 · LIVING 7.95 × 4.90 · 26.3–30.2 s production | same plans · 13.2 / 34.8 / 34.9 / 35.0 s | same |
| B19 | all four | 21.8 / 8.4 · LIVING 6.25 × 3.90 · 0.8 s; brain 19.9 / 12.8 · LIVING 4.20 × 4.75 · 20.3–30.1 s production | same plans · 1.1 / 27.1 / 30.2 / 30.3 s | same |
| B06 | production | 18.1 / 10.7 · HALL 1.30 × 13.45 STRIP · 0.7 s | same · 1.0 s | same |
| B06 | brain · production sizer | 8.6 / 12.1 · CIRC 1.60 × 3.15 STRIP · 1.9 s | **13.0 / 14.7 · CIRC 2.15 × 2.65 usable · 2.6 s** (PUBLIC_BAND+FOYER) | **better** by the key |
| B06 | brain · exact, band | 8.6 / 12.1 · CIRC 1.60 × 3.15 STRIP · 30.1 s production | **3.8 / 10.7 · CIRC 2.00 × 3.00 usable · 30.4 s exact** (TWO_HALL+FOYER) | **better** |
| B06 | brain · exact, all | 3.8 / 10.7 · CIRC 2.00 × 3.00 usable · 30.7 s exact | same · 30.3 s exact | same |
| B09 | production | 9.8 / 8.9 · HALL 1.30 × 14.45 STRIP · 1.2 s | same · 1.7 s | same |
| B09 | brain, all three | 13.1 / 14.9 · CIRC 1.95 × 2.60 usable · 5.2 / 30.0 / 30.0 s production | same · 6.9 / 30.0 / 30.0 s | same |
| **mean** | production | 15.8 / 10.7 · max 10.2 s | 15.8 / 10.7 · max 13.3 s | |
| | brain · production sizer | 16.2 / 13.5 · max 26.3 s | 16.8 / 13.8 · max 34.8 s | +0.6 |
| | brain · exact, band | 14.3 / 14.4 · max 30.3 s | 15.2 / 13.9 · max 34.9 s | +0.9 |
| | brain · exact, all | 13.8 / 13.1 · max 31.1 s | 15.2 / 13.9 · max 35.0 s | +1.4 |

Same-session control (#206's code today): means 15.8 / 16.2 / 14.3 / 15.1, max 14.2 / 36.5 / 39.1
/ 36.7 s; it reproduces every #206 plan except B02 all (stack, 2.0 → 7.4 production) and B06 all
(exact 3.8 → 8.6 production), both at the budget's edge. Full three-way table in
`before-same-session/` and `data/preview-foyer-preference/metrics*.json`.

### What changed, brief by brief

* **B06 — the preference working as designed.** brain·production: the key now picks
  `PUBLIC_BAND+FOYER`'s plan (2.15 × 2.65 m foyer, usable) over `BEDROOM_WING+FOYER`'s
  (1.60 × 3.15 m strip), paying 4.4 points of room deviation for it — exactly the trade the term
  exists to make, and the note on the losing plan names it. brain·exact band: `TWO_HALL+FOYER`'s
  exact plan (2.00 × 3.00 m, 3.8 %) now replaces production's strip plan — in #206 the band column
  kept the 8.6 % strip because the exact plan's deviation (4) did not beat the parti it was
  compared to under the old order of exact sizing; with usability ranked first, the exact
  `TWO_HALL+FOYER` plan wins its parti and the brief.
* **B08 — the #206 cost is now the right answer by the key.** The shown-first plan is unchanged
  (2.00 × 3.00 m, 5.1 %), but it now ranks ABOVE #204's 1.50 × 3.05 m strip plan
  ((0, 0, 0, **0**, 5, 14, …) < (0, 0, 0, **1**, 3, 13, …)); `test_brain.py`'s gate test loses its
  `xfail` marker for that reason, with this report as the reason, and still asserts the
  deviation it costs (5 vs 3).
* **B20 exact band — the V-orientation fix's price.** #206's shown-first plan was `PUBLIC_BAND`
  in the V orientation: a hub HALL 3.40 m along the street and 8.15 m deep, entered through its
  narrow end — a strip by the sizer's own line (depth 2.4 × frontage), which the oracle never saw
  because its street rules looked at the west band. With the rules on the fronting cell that
  placement no longer solves (the hall cannot be 8.15 m deep at 3.40 m of frontage; the diagnostics
  show 19 V/H placements realized for B20, none with a circulation cell on the street line), and
  the band column falls back to the production foyer parti (22.2 %, 1.50 × 3.40 m — also a
  strip). By the key the lost plan would still have won (both strips, 16 < 22): this loss is the
  sizer refusing a strip hall, not the preference — the cost of "a parti named foyer must execute
  a foyer" applied to the hall in V.
* **B11 — the budget, traced.** After: `NO_EXACT_PLAN: 0 placements realized` on both exact
  columns; control: the exact plan at 28.8 s. `trace_b11` (every band solve of the after run,
  street / status / seconds / time limit): production's pass over six partis leaves 6 s of the
  30 s budget, the top parti's share is 1.9 s, and the first screened candidate's four H rungs are
  INFEASIBLE in 0.02 s each, then its V solve — now a real problem with the foyer group on the
  fronting cell — runs to the 1.8 s limit and returns UNKNOWN; the share is gone, every later
  solve gets the 1 s floor, and the H candidate the control sizes is never reached (65 solves,
  64 INFEASIBLE, 1 UNKNOWN). Before #207 that V solve was trivially infeasible under the
  misplaced row-0 rule and cost 0.02 s. The loop sizes H then V per candidate inside one shared
  budget (`exact_pipeline`'s family loop, #208's file); ordering all H solves before any V, or
  capping V's share, is a change of its own and is not made here.
* **B02 all — the machine.** The stack plan (2.0 %) is lost in the control as well; nothing in
  this change touches the stack family's constraints in H.

### The V orientation: street-fronting placements before / after

From the placement-level diagnostics (`diag/diag-none.json`; before = #205's own diagnostics on
`50e8677`, the same code as the control): every exact placement realized or refused whose street
band holds a circulation cell, n / realized / failed on C25 / C26 / C28, and in brackets the
V-orientation ones (n / realized).

| brief | column | before | after |
|---|---|---|---|
| B08 | band | 7 / 7 / 0 / 0 / 0 (V 0 / 0) | 8 / 8 / 0 / 0 / 0 (V 0 / 0) |
| B08 | all | 17 / 12 / 0 / 5 / 3 (V 4 / 0) | 11 / 11 / 0 / 0 / 0 (V 0 / 0) |
| B20 | band | 1 / 1 / 0 / 0 / 0 (V 1 / 1) | 0 / 0 / 0 / 0 / 0 (V 0 / 0) |
| B02 | band | 14 / 8 / 3 / 2 / 0 (V 1 / 0) | 9 / 6 / 2 / 0 / 0 (V 0 / 0) |
| B02 | all | 16 / 7 / 2 / 6 / 0 (V 1 / 0) | 17 / 8 / 3 / 5 / 0 (V 2 / 2) |
| B11 | band, all | 1 / 1 / 0 / 0 / 0 (V 0 / 0) each | 0 / 0 (V 0 / 0) each |
| B06 | band | 7 / 5 / 2 / 0 / 0 (V 2 / 0) | 6 / 6 / 0 / 0 / 0 (V 0 / 0) |
| B06 | all | 6 / 4 / 2 / 0 / 0 (V 2 / 0) | 6 / 6 / 0 / 0 / 0 (V 0 / 0) |
| B16, B19, B09 | both | 0 (the #200 limit) | 0 |
| **total** | | **70 / 46 — V 11 / 1** (10 failed: C25 ×5, C26 ×5, C28 ×3) | **57 / 45 — V 2 / 2** (0 failed) |

The V-orientation count of street-fronting placements goes from 11 (1 realized, the B20 strip
hall; 10 failing C25/C26/C28 — the four B08 cells foyers 2.40 × 1.80–2.20 m, the B02/B06 band
foyers entered beside the hall) to 2 (both realized: B02 `HALL_SPINE+FOYER` spine, V, a
2.80 × 3.00 m foyer with the door — the first V-orientation foyer plans that pass). The other V
placements that used to front the street with a circulation cell no longer solve with the rules
on the right cell (they were strips) or sit lower in the budget. Among the fronting placements
that are sized, every C25/C26/C28 failure in the V orientation is gone; the H ones that remain
on B02 are #205's "beside the entrance" stubs.

## Where this sits on the path to execution

Row 1 of the #197 execution-plan table ("exact sizer: foyer geometry" — the door's room is a
usable room) **closes with this, as the owner decided on 2026-10-18**: the sizer refuses strips
(#205), and the preference now sees them (#207) — B06 and B08 show the key choosing the lobby
over the strip and explaining why. This measurement's verdict is STOP on the contract's clauses,
and the reasons are named: one real cost (B20 band: the V strip hall is refused, 16.2 → 22.2),
one budget interaction the V fix exposes (B11: a real V solve eats a 1.9 s share), and a machine
30–40 % slower than #206's session for the rest.

**The next blocker is row 2, the #200 limit (#208, running in parallel)** — B16, B19 and B09
still get no exact plan at all, and no foyer rule reaches a brief without one. Right after it,
and in #208's file: the family loop should size every H orientation before any V (or cap the V
share) so that a real V solve cannot cost the H plan on a brief where production leaves the exact
sizer a few seconds — that is what decides B11 here. Then row 3, the request-time budget: today's
numbers (production's own 14 s on B16, the brain's 35–39 s) say the 31 s figure is a per-machine
fact the owner should set, not measure.

## Tests

* `tests/vertical_slice/test_brain_entrance.py` (+2): a strip arrival room ranks below a usable
  one with equal arrival / street / area even when its rooms sit closer to target, the term's
  line is the oracle's constants (`FOYER_MIN_NET_M`, `FOYER_MAX_DEPTH_TO_WIDTH`), the notes name
  it; between two lobbies or two strips the deviation decides as before; the #201 slice
  assertion carries the new key.
* `tests/vertical_slice/test_foyer_geometry.py` (+4): per oracle (band, spine, cells), with
  `street="W"` a foyer first in its band is sized to the group and holds the front door after
  transposition, read off the realized room as the preference reads it, while the N rule on the
  same case leaves the foyer's band off the street line (band, spine: `no zone with an
  ALLOWED_ENTRANCE role fronts the street`) or makes it wider than deep (cells); an unknown street
  side is refused. The five #206 pins (never a strip in H; `_skip={"foyer"}` reproduces b460a42)
  pass unchanged: the N frame is byte-identical.
* `tests/vertical_slice/test_brain.py`: `MEASURED_204_KEYS` carries the arrival-room key (both
  #204 B08 plans had the 1.50 × 3.05 m strip: 1); the gate test's `xfail(strict=True)` is removed
  because the measured fact changed — the 2.00 × 3.00 m plan now ranks above #204's — and it
  asserts the deviation it still costs.

### Suites

Named files (`test_brain.py`, `test_brain_entrance.py`, `test_brain_area.py`,
`test_foyer_geometry.py`, `test_exact_band_142c.py`): **61 passed** in 285 s. The oracle suites
(`test_milp_oracle`, `test_milp_placement`, `test_milp_spine`, `test_cells`,
`test_staircase_sizing`, `test_spine_embedding`): **44 passed**. Full fast suite
(`WALLCLOCK_BUDGETS=off pytest -q -p no:cacheprovider -n 4`): **4 failed, 2449 passed, 883
skipped, 9 xfailed** in 648 s — the 4 are all `tests/test_local_gateway.py` on
`ModuleNotFoundError: No module named 'torch'` (`app/architect/local_gateway.py` imports torch,
which this worktree's venv lacks), the same four #206 recorded, untouched by this change. The
xfail count is 9 where #206 had 10: the one removed is this change's own gate test. The corpus
snapshot suite was not run (> 15 min); the production sizer and the validators are untouched by
construction and `run_brain(sizer="production")` is byte-identical per parti (existing test).

## Changes

* `exact/milp_oracle.py` — `STREET_SIDES`, `street=` on `milp_heights` / `milp_placement` /
  `milp_spine_placement` / `_spine_once`, `_fronts_street`, `_entrance_frontage_v`,
  `_foyer_constraints_v`; the spine's entrance rule along its height in the W frame.
* `exact/milp_cells.py` — `street=` on `milp_cells` / `cells_placement`; the three bounds and the
  entrance rule with frontage/depth swapped in the W frame.
* `brain/exact_pipeline.py` — five lines: the street side per orientation at the four oracle calls.
* `brain/runner.py` — `arrival_usability`, the key at index 3 in `_proportion_preference`,
  `_key_text`, `_decided_by`, the notes.
* Data: `data/preview-foyer-preference/` (metrics, designs, `run.log`, the loaded first run, the
  same-session control, `diag/`), 56 figures under `figures/preview-foyer-preference/`.
