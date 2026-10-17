# `?engine=brain` — rank the partis, then size the best exactly (#197, 2026-10-16/17)

Branch `feature/brain-rank-then-size`, on top of #203. The step the previous report named as the one
before showing the preview to users: the exact sizer no longer gets an equal 1/8 share of the 30 s
budget per parti. Production sizes every parti first (0.2–6 s per brief), the partis are ranked by
the brain's own preference, and the exact sizer spends the whole remaining budget on the best-ranked
ones (`EXACT_TOP = 3`, then any further parti while ≥ 5 s remain). An exact plan replaces
production's for the same parti only when it **counts** and its preference key is **no worse**.

Same eight real briefs, same four configurations, same renderer (`DemoPlan`), data
`data/preview-compare-top3/` (metrics, designs, `run.log`), figures
`figures/preview-rank-then-size/<brief>__<config>.png` (the plan the product shows first) and
`…__<config>-bydev.png` (the plan with the lowest room deviation, for comparison with the first report).

## A correction to the first report (`PREVIEW-visual-comparison.md`)

The first report's headline — "where the exact sizer runs, the rooms are on target: B08 1.4 %, B02
1.2 %, B06 0.7 %" — was measured on each configuration's plan with the **lowest room deviation**.
Checked on the saved designs: all 16 of those exact plans put the **front door into the living room
with the hall in an interior band** — the very defect the #197 entrance preference exists to prevent —
and the sentence "the front door opens into the hall in B02 and B06" was wrong. The brain's own
preference ranks "the front door opens into the room the parti nominated" and "that room reaches the
street" above every proportion, so none of those plans is the one the product would show first.
The table below reports the **primary** (the plan the product shows); the by-deviation plan is kept
only as a second figure per cell.

## Why the exact plans arrived in the living room, and what was done

Measured on B08 before any change: 89 exact band realizations, 77 with the arrival room in an
interior band (43 realized into a living-room arrival, 34 refused `NO_ENTRANCE`), 8 with it on the
street — of which 3 realized and 5 failed validators (C25 unserved corridor beside/beyond the
entrance door, C28 two door swings overlapping in a 5–7 m² foyer, C26 dead ends). The exact
pipeline sized the screened candidates in the embedder's plausibility order, which puts the hall in
the middle, and never sized production's flipped orientation. Two changes, neither a new constraint:

* `_orientations` — the exact path sizes the same top/bottom flip `run_band_pipeline` sizes when it
  has a preference (an entrance room in both the street band and the last band).
* `arrival` — candidates that put the parti's arrival room in the street band are sized **first**.
  An order, not a screen: nothing is dropped or admitted.

A cheap unaligned MILP probe as the ranking was measured and rejected: its objective does not
predict the realized plan (B02: probe 0.2 % → 21.6 % realized, probe 0.3 % → 1.2 %), and on
B16/B19 every exact band placement is INFEASIBLE for every parti, so no ranking buys a plan there.
Production's own plan per parti is the ranking: it is the fallback anyway and yields the same key.

## Results — the plan the product shows first

Room deviation from target % / circulation share % · arrival room · seconds for the whole request ·
sizer/family. `CIRC` = the parti's entry foyer (`ENTRY`, role CIRCULATION).

| brief | production | brain · production sizer | brain · exact, band | brain · exact, all families |
|---|---|---|---|---|
| B08 | 3.9 / 12.7 · HALL · 0.3 s | 9.0 / 9.0 · HALL · 1.8 s | **3.1** / 12.5 · CIRC · 30 s exact | **1.4** / 12.8 · CIRC · 28 s exact/stack |
| B20 | **12.5** / 12.0 · HALL · 0.2 s | 22.2 / 15.8 · CIRC · 7.5 s | 16.2 / 23.7 · HALL · 24 s exact | 22.2 / 15.8 · CIRC · 30 s (production) |
| B02 | 23.6 / 11.5 · HALL · 3.4 s | 7.4 / 10.3 · HALL · 0.6 s | 7.4 / 10.3 · HALL · 28 s (production) | **2.0** / 9.6 · HALL · 30 s exact/stack |
| B11 | 22.0 / 10.9 · HALL · 10 s | 28.4 / 19.4 · CIRC · 18 s | 28.4 / 19.4 · CIRC · 27 s (production) | **16.6** / 14.3 · CIRC · 31 s exact |
| B16 | **14.4** / 10.1 · HALL · 10 s | 21.4 / 13.5 · LIVING · 27 s | 21.4 … · 30 s (production) | 21.4 … · 30 s (production) |
| B19 | 21.8 / 8.4 · LIVING · 0.8 s | **19.9** / 12.8 · LIVING · 21 s | 19.9 … · 27 s (production) | 19.9 … · 31 s (production) |
| B06 | 18.1 / 10.7 · HALL · 0.7 s | **8.6** / 12.1 · CIRC · 2.0 s | 8.6 / 12.1 · CIRC · 31 s (production) | 8.6 / 12.1 · CIRC · 31 s (production) |
| B09 | **9.8** / 8.9 · HALL · 1.2 s | 13.1 / 14.9 · CIRC · 5.5 s | 13.1 … · 30 s (production) | 13.1 … · 31 s (production) |
| **mean** | 15.8 / 10.7 · 3.4 s | 16.2 / 13.3 · 10.4 s | 14.8 / 14.2 · 28.5 s (max 31.4) | **13.2** / 13.6 · 30.2 s (max 31.4) |

First report (lowest deviation, living-room arrivals): 15.8 / 13.2 / 10.9 / 10.1, requests up to
43.7 s. The same lowest-deviation measure on this branch: 15.8 / 13.2 / 12.3 / 11.4.

## What the drawings show

* **Where the exact sizer wins, it now wins with the right front door.** B08 `brain-exact-all` is
  the foyer parti's stack plan at 1.4 % with the door in the foyer (`B08__brain-exact-all.png`:
  living/kitchen 42 m², dining 17, master 16, bedrooms 11.4–11.6); B02 is the hall-spine stack plan
  at 2.0 % arriving in a 6.15 × 2.35 m hall (`B02__brain-exact-all.png`); B11's foyer plan goes from
  28.4 % to 16.6 % with the foyer on the street. On B20 the band-only exact plan (16.2 %) beats the
  brain's production primary (22.2 %) but pays with 23.7 % circulation — the preference ranks room
  deviation before circulation (#201) and that order shows here.
* **No parti ranks below its production plan.** A plan is replaced only when the exact one's key is
  no worse; where the exact plan lost, the production plan carries the reason in its notes
  ("ranked below production's: arrival ok, street ok, area out of tolerance, rooms 13 %,
  circulation 17 % vs … rooms 9 %, circulation 12 %"). B06 is that case: with the foyer on the
  street the exact sizer's rooms sit at 12–13 % where production's sit at 9 %, so production is
  kept. The first report's 0.7 % on B06 was a living-room-arrival plan.
* **Every request ends at the budget**: 24–31.4 s where the first version took 35–44 s on the large
  briefs; what exceeds 30 s is the last solve in flight.
* **B16, B19, B09 still show production's plan.** On B16/B19 the exact band placement is
  INFEASIBLE for every parti and candidate (the limit #200 measured: layout generation versus room
  bounds); on B09 (10 rooms) every solve within its share returns UNKNOWN. The budget bought nothing
  there and the plan's note says so.
* **The ranking changes the brain's own primary** on B20, B11, B09: a foyer plan with the right
  arrival (22.2 / 28.4 / 13.1 %) now ranks above a tighter plan whose door opens into the living
  room (13.3 / 17.9 / 8.4 %). That is the approved priority order (arrival and street before
  proportion); the size of the gap on B20 and B11 is a fact for the owner to weigh, not something
  this change decides. The foyers themselves are strips (B08: 1.50 × 3.05 m) — see "Next".

## Changes

* `brain/runner.py` — `run_brain`: production first, `_rank` sets `BrainPlan.rank_key`,
  `_improve_exactly` (top `EXACT_TOP = 3`, then while ≥ `EXACT_EXTRA_MIN_S` remain),
  `BrainResult.distinct` ordered by `rank_key`; `_one(fallback=False)` returns the exact refusal as
  a plan; notes name both keys when the exact plan loses (`_key_text`).
* `brain/exact_pipeline.py` — `_orientations`, `arrival`, `_fronts`; the stack family takes the
  same two.
* `exact/milp_oracle.py` — `OracleResult.objective` (the solver's objective value; used by the
  rejected probe experiment, kept because it costs nothing and makes the result legible).
* Tests: `test_the_exact_sizer_improves_partis_and_never_ranks_one_below_production`,
  `test_the_primary_is_the_best_ranked_plan_not_the_first_parti`; `run_brain(sizer="production")`
  is byte-for-byte unchanged per parti (existing test). 60 brain/exact tests pass.

## Next, if the owner wants the exact sizer to win more often

The street-fronting exact placements that fail do so on **circulation geometry** — C25 (unserved
corridor beside/beyond the entrance door), C28 (two door swings in a 5–7 m² foyer), C26 (dead ends)
— not on room bounds, and the foyers that pass are strips. A minimum foyer/hall geometry in the
exact sizer (width at the entrance door, no strip foyers) is the next lever; it is new research
(~1 day), not in this change. B16/B19 remain the #200 limit.
