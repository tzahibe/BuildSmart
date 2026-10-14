# Path B, day 3: A1 — exact room areas in the objective — measured on the frozen six; **STOP at the time-box**

Owner directive: path B, three days, A1 folded in, STOP at day 3. Day 2's gate was GO (`DAY-2-spine-gate.md`). This is the last day's work and the closing verdict. Commit below on `feature/architectural-brain` (PR #198).

## 1. What A1 is

Gate 3's `objective="area"` maximised width × a fixed mid-grid height for habitable rooms — a proxy that trades height for width and leaves the hall as the sink. A1 (`milp_oracle._target_objective`, both oracles, `objective="target"`): every room's **exact** net area `(w − iw)(h − ih)` enters the objective through `p = w·z` products (McCormick with the height binaries, exact; `p` and the deviations continuous so the branch-and-bound stays on heights and boundaries). The objective minimises the **relative deviation from the programme's target** per habitable room and the relative **overshoot** per circulation room. Nothing else changed: same bands, same validators, same ladder, same six. `SHAPE_AGNOSTIC_OBJECTIVE=target` selects it in the harness; `tests/vertical_slice/test_milp_placement.py` holds the fact (rooms land on 30/13/10/13 where "area" gave 24.7/16.8/13.9/15.1).

Proportion metrics added to every plan record (`run._proportions`): `room_dev_pct` (mean |net − target| / target over habitable rooms), `circ_pct` (circulation share of net), `min_bed_pct` (smallest bedroom / its target).

## 2. Before / after on the six (`data/spine-day3-area/`, `data/spine-day3-target/`; counted plans only)

| case | obj | s | band | spine | gross | room dev | circ | min bed |
|---|---|---|---|---|---|---|---|---|
| F1 rect | area | 13.8 | 8 | 3 | 73.9 % | 25.9 % | 16.4 % | 67 % |
| | **target** | **131.9** | 8 | 4 | 77.2 % | **17.4 %** | 16.3 % | **75 %** |
| F2 L | area | 22.4 | 1 | 0 | 81.8 % | 26.5 % | 15.5 % | 76 % |
| | target | 27.1 | 1 | 0 | 78.1 % | 21.7 % | 19.0 % | 70 % |
| F3 wide-shallow | area | 21.5 | 1 | 1 | 105.8 % | 33.0 % | 17.1 % | 65 % |
| | target | 30.8 | 0 | 1 | 97.7 % | 31.9 % | 19.4 % | 65 % |
| F4 entry court | area | 21.3 | 3 | 1 | 79.6 % | 29.6 % | 18.3 % | 59 % |
| | target | 28.0 | 2 | 1 | 81.4 % | **23.0 %** | 16.7 % | 59 % |
| F5 garden court | area | 7.9 | 3 | 0 | 70.7 % | 35.7 % | 15.5 % | 71 % |
| | target | 11.1 | 3 | 0 | 73.9 % | 31.2 % | 12.7 % | **81 %** |
| F6 K4 | both | 0.0 | refused | | | | | |

All counted plans: **room deviation 28.7 % → 21.3 %, smallest bedroom 66 % → 73 % of target**, gross 77.9 → 78.4 %, circulation 16.7 → 16.1 %. Solved cases unchanged (5/5). The best single plan is F1's spine BEDROOM_WING (V): room deviation **6.3 %**, smallest bedroom **99 %** of target, gross 81.5 %, circulation 13.4 % — `figures/spine-day3/F1-rect-control__BEDROOM_WING__spine__target.png`: three 13.9 m² bedrooms off a 2.25 × 9.7 corridor, master 20.1, living 32.3, kitchen 23.4, the walk at the door.

**Cost:** the exact objective is a harder MILP. F1 went 13.8 → 131.9 s (18 band sizings + 10 spine sizings, each fixed-point round now seconds, not tenths); F3 30.8 s. The ≤ 30 s/case bar holds for four cases and fails on F1 — the case with the *most* feasible layouts, because every one of them is solved to optimality. A per-case sizing budget (`MAX_SIZINGS` lower, or stop at the first plan under a deviation threshold) would hold the bar; not tuned today.

## 3. What the numbers say

* The objective was worth ~7 points of room deviation and ~7 points of bedroom size across the board, and on the one structure that gives every room its own width (the spine with single-cell rows) it reaches a *credible* plan (6 % deviation). Elsewhere deviation stays at 19–32 %: rooms in a band share its depth, cells stacked in a column share a width, and the programme's targets cannot all be met under those ties. **The remaining gap is structural, not the objective** — the same fact Gate 3 named: a 2D wing (rooms that do not share a band's full depth) is what proportion needs. That is path B's *first* half ("2D wing per band"), which this spike did not build; the vertical spine was its second half.
* F3's band plans under "target" land at 110 % gross (`AREA_OVER_TOLERANCE`, not counted): pulling rooms to their targets on a 24 × 9.5 strip overshoots the requested 190 m² — the ladder's upper rungs and the target objective pull the same way; a case where "requested area" and "room targets" disagree should be decided by the programme, not the sizer.
* F2 is still the band family's (TWO_HALL); the spine's two-section generalisation (`DAY-2-spine-gate.md` §3) is unbuilt.

## 4. Verdict: STOP at the time-box, as directed

Delivered in three days: the spine family (embedding, exact aligned MILP, geometry, SELECTION screen, tests), the harness correction that reinstated F2/F4 for both families, a production fix (entrance walk), the A1 objective with its measurement, and the frozen six at 5/5 solved. Not delivered: the 2D wing, the two-section spine, the time budget under the exact objective.

**Recommendation for the next decision** (owner's): the realizer is now shape-free on five footprint classes and typed on the sixth; the credible-plan gap is proportion, and the evidence says it needs the 2D wing (GridWing-style rooms inside a band), estimated 2–3 days, with the target objective already in place to measure it. Everything in `app/ai_harness/shape_agnostic` stays harness-only until `scipy` is a declared dependency (path C, owner decision).
