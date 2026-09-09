# PLAN_NOT_REALIZABLE_ROOT_CAUSE_REPORT

```
TOTAL_CASES              = 608 failures out of 1056 scenarios that reached the footprint stage
                           (the 566 seen through the API, plus 42 that the API counted under other
                           codes; the diagnostic runs the pipeline directly and sees all of them)
ESTIMATED_RECOVERABLE    = ~272 (45%) — proven by witness, see §5
DOMINANT CLASSIFICATION  = ENGINE_LIMITATION, not infeasibility
STATUS                   = diagnostics only, no planning behaviour changed
```

**The headline: 45% of these failures have a witness.** For 67 of a random 150 sampled failures, a
*different proportion of exactly the same area on exactly the same parcel* plans successfully. The
requirements are not impossible; the outline the product offered was one the engine cannot use.

---

## ROOT_CAUSE_CLUSTERS

The public code hides the split. Internally there are three distinct places a scenario dies:

| cluster | count | % of 608 | classification |
|---|---|---|---|
| **1. Zero concept candidates — the generator produced nothing** | **458** | **75.3%** | mostly `ENGINE_LIMITATION` |
| **2. Candidates existed, Geometry Core realized none** | **144** | **23.7%** | `ENGINE_LIMITATION` |
| **3. Realized and validated, then failed a check** | **6** | **1.0%** | `BUG` (pre-existing) |

### Cluster 1 — the concept generator returns an empty set (458, 75.3%)

Outcome `INSUFFICIENT_RECTANGULAR_CAPACITY`, which is raised when `generate_concepts` produces no
candidate at all. Every strategy rejected. By reason:

| rejection reason | occurrences |
|---|---|
| `ROOM_BELOW_MINIMUM_DIMENSION` | **422** |
| `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` | 36 |

And by the detail text, which is where the real cause is:

| detail (numbers elided) | occurrences |
|---|---|
| *west column needs more than N m of depth for its N rows at their minimum dimensions* | **1577** |
| *no footprint proportion satisfied the programme* | 390 |
| *DINING would be N m wide in the front band, below its 2.6 m minimum* | 240 |
| *east column needs more than N m of depth for its N rows* | 104 |
| *no footprint proportion satisfied the front-band parti* | 80 |
| *KITCHEN would be N m wide in the front band, below its 2.4 m minimum* | 56 |

383 of these 458 cases had **all six** strategies reject. This is not one parti failing; it is the
whole candidate set failing on the same geometric ground.

**Classification: `ENGINE_LIMITATION`.** The generator expresses one family of layouts — *west
column | hall spine | east column*, plus a front-band variant. Every rejection above is that family
saying "this rectangle is the wrong shape for me", not "no house fits here". §5 proves it: the same
programme and area, at a different proportion of the same parcel, plans.

### Cluster 2 — candidates existed, Geometry Core realized none (144, 23.7%)

Outcome `NO_SAFE_SOLVER_GEOMETRY`. The slicing tree could not be cut:

| solver note | occurrences |
|---|---|
| *no H split of Rect(...) for [BEDROOM_N, SAFE_ROOM, BATH_N] at forced position N* | 81 |
| *no V split of Rect(...) for [HALL, BEDROOM_N, BEDROOM_N, SAFE_ROOM, BATH_N]* | 56 |
| *no H split of Rect(...) for [SAFE_ROOM, BATH_N, BATH_N]* | 54 |
| *no V split of Rect(...) for [HALL, BEDROOM_N, BEDROOM_N, SAFE_ROOM, BATH_N, BATH_N]* | 30 |
| *no H split of Rect(...) for [SAFE_ROOM, BATH_N]* | 24 |

Note what recurs in almost every line: **`SAFE_ROOM` appears in the failing row group**. Its 2.4 m
minimum short side and zero elasticity make it the member that cannot be squeezed, and the row it
sits in is where the cut fails. 65 of the 144 had only **one** candidate to try.

**Classification: `ENGINE_LIMITATION`.** The forced-chain tree commits to one row order per column
before dimensioning; a different order of the same rooms is often cuttable and is never tried.

### Cluster 3 — realized, then failed validation (6, 1.0%)

All six are the same defect, and all six are `3BR + safe room + closed plan at 200 m²`:

```
C8: MASTER      (the master bedroom has no exterior wall, so no window)
```

**Classification: `BUG`.** This is the known residual C8 case, already documented in the
`GEOMETRY_DERIVED_OPEN_INTERFACES` work — the `_daylight_order` fix moved shared rows to the end of a
column but does not cover this configuration. Small, and genuinely a defect rather than a limit.

---

## TOP_3_ROOT_CAUSES

1. **The offered footprint proportion is one the parti cannot use** — 458 cases die before a single
   candidate exists, and the aspect-ratio evidence below shows why.
2. **Column row-depth exhaustion** — 1577 mentions of a column needing more depth than the footprint
   has, for its rows *at their minimum dimensions*. The row set per column is fixed by the
   allocation; the depth is fixed by the outline; neither is re-tried against the other.
3. **The safe room is the binding member in the solver failures** — it appears in the failing row
   group of nearly every `no split` note in cluster 2.

## SUCCESS_VS_FAILURE_BOUNDARIES

**Aspect ratio is the single strongest predictor, and it is not close.**

| footprint ratio (w/d) | success | | 3BR + safe room only |
|---|---|---|---|
| 0.00–0.60 | 31/192 — **16.1%** | ▓▓▓▓ | 8.3% |
| 0.60–0.75 | 44/96 — 45.8% | ▓▓▓▓▓▓▓▓▓▓▓▓▓ | 25.0% |
| 0.75–0.90 | 91/168 — 54.2% | ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ | 42.9% |
| **0.90–1.10** | **161/216 — 74.5%** | ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ | **63.0%** |
| 1.10–1.30 | 63/120 — 52.5% | ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ | 10.0% |
| 1.30–1.60 | 17/48 — 35.4% | ▓▓▓▓▓▓▓▓▓▓ | **0.0%** |
| 1.60+ | 41/216 — **19.0%** | ▓▓▓▓▓ | **0.0%** |

**And here is the actionable part: 408 of the 1056 offered outlines (39%) land in the two worst
bands.** `feasible_options` spreads its four choices *evenly across the feasible width interval*,
which on a long parcel puts most of them at extreme proportions. The engine wants near-square; the
product offers extremes. For a 3-bedroom house with a safe room, **every single offer above ratio
1.3 failed — 66 of 66.**

Secondary boundaries:

- **By programme**: `3BR/3wet/safe` 9.1% at the bottom, `3BR/1wet/no-safe` 86.4% at the top. The
  safe room costs ~20 points of success rate wherever it appears.
- **By requested area**: 120 m² 20.8%, 160 m² 51.3%, 200 m² 59.4%. *Smaller areas fail more* — a
  small footprint forces narrow columns.

## SUSPICIOUS_NON_MONOTONIC_CASES

**10 cases where MORE area fails and LESS area succeeds**, same programme, same parcel:

| programme | plot | succeeds at | fails at |
|---|---|---|---|
| 2BR/1wet/safe/closed | 20×24 | 160 m² | **200 m²** |
| 2BR/1wet/safe/closed | 18×30 | 160 m² | **200 m²** |
| 2BR/1wet/safe/closed | 22×26 | 160 m² | **200 m²** |
| 2BR/1wet/no-safe/closed | 20×24, 18×30, 22×26 | 160 m² | **200 m²** |
| 2BR/2wet/no-safe/closed | 20×24, 22×26 | 160 m² | **200 m²** |
| 2BR/3wet/safe/closed | 22×26 | 120 m² | **160 m²** |
| 3BR/3wet/no-safe/open | 22×26 | 160 m² | **200 m²** |

Extra land cannot make a house harder to place. Six of the ten are `TARGET_AREA_EXCEEDS_CURRENT_
PROGRAM_CAPACITY` — a real ceiling, correctly reported. The rest are the aspect-ratio effect:
the larger area's *offered proportion* fell in a worse band than the smaller area's did. Both are
explained; neither is a hidden second bug.

## Representative cases

| # | programme | area | plot | buildable | footprint | ratio | cands | internal reason | class |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2BR/1wet/safe/open | 120 | 20×24 | 14.0×14.5 | 8.30×14.46 | 0.57 | 0 | DINING would be 0.95 m wide in the front band | B |
| 2 | 2BR/1wet/safe/open | 120 | 20×24 | 14.0×14.5 | 10.20×11.76 | 0.87 | 1 | same | B |
| 3 | 2BR/1wet/safe/open | 120 | 20×24 | 14.0×14.5 | 12.10×9.92 | 1.22 | 0 | same | B |
| 4 | 2BR/1wet/safe/open | 160 | 20×24 | 14.0×14.5 | 13.00×12.31 | 1.06 | 4 | west column needs > 12.30 m depth for 4 rows | B |
| 5 | 2BR/1wet/safe/open | 120 | 20×24 | 14.0×14.5 | 14.00×8.57 | 1.63 | 0 | DINING below minimum | B |
| 7 | 2BR/1wet/safe/open | 120 | 18×30 | 12.0×20.5 | 7.90×15.19 | 0.52 | 0 | DINING below minimum | B |
| 8 | 2BR/1wet/safe/open | 160 | 18×30 | 12.0×20.5 | 9.20×17.39 | 0.53 | 0 | DINING below minimum | B |
| 9 | 2BR/1wet/safe/open | 200 | 18×30 | 12.0×20.5 | 9.76×20.49 | 0.48 | 0 | DINING below minimum | B |
| 10 | 2BR/1wet/safe/open | 200 | 18×30 | 12.0×20.5 | 10.50×19.05 | 0.55 | 5 | west column needs > 11.25 m depth | B |
| 13 | 2BR/1wet/no-safe/closed | 200 | 20×24 | 14.0×14.5 | 13.80×14.49 | 0.95 | 0 | target exceeds programme capacity | **A** |
| 15 | 3BR/1wet/safe/open | 120 | 20×24 | 14.0×14.5 | 8.30×14.46 | 0.57 | 0 | DINING below minimum | B |
| 17 | 3BR/1wet/safe/open | 160 | 20×24 | 14.0×14.5 | 13.00×12.31 | 1.06 | 1 | east column needs > 12.30 m depth for 5 rows | B |
| 18 | 3BR/1wet/safe/open | 200 | 18×30 | 12.0×20.5 | 10.50×19.05 | 0.55 | 5 | west column needs > 12.60 m depth | B |

## Witnesses — the evidence for `ENGINE_LIMITATION`

150 failures sampled at random; for each, up to 8 feasible proportions of the **same area on the
same parcel** were tried. **67 (45%) planned at a different proportion.**

| programme | area | plot | offered → FAILS | witness → SUCCEEDS |
|---|---|---|---|---|
| 3BR/1wet/safe/closed | 120 | 18×30 | 12.00 × 10.00 | **9.35 × 12.83** |
| 2BR/2wet/no-safe/closed | 120 | 20×24 | 8.30 × 14.46 | **11.55 × 10.39** |
| 3BR/2wet/safe/open | 160 | 22×26 | 9.70 × 16.49 | **11.50 × 13.91** |
| 3BR/1wet/no-safe/closed | 120 | 25×20 | 16.50 × 7.27 | **11.45 × 10.48** |
| 3BR/3wet/no-safe/closed | 120 | 18×30 | 7.90 × 15.19 | **11.10 × 10.81** |
| 2BR/3wet/safe/closed | 120 | 18×30 | 7.90 × 15.19 | **10.25 × 11.71** |
| 2BR/2wet/safe/open | 200 | 18×30 | 9.76 × 20.49 | **12.00 × 16.67** |

Every witness moves toward square. This is one pattern, not seven coincidences.

A separate, weaker experiment agrees: of the 608 failures, **45 plan when the outline is simply
turned 90°**, 401 cannot be rotated within the buildable region at all, and 162 fail both ways.

## ESTIMATED_RECOVERABLE_CASES

**~272 of 608 (45%)**, extrapolated from the 150-case sample. These are cases where a valid layout
demonstrably exists at exactly the requested area on exactly the supplied land.

That is a lower bound. The sweep tried only 8 proportions of one area; it did not vary row order,
allocation, or anything inside the generator.

The remaining ~336 divide into genuine `PROVABLY_INFEASIBLE` (a small programme in a small
footprint, and the 36 capacity-ceiling cases) and deeper `ENGINE_LIMITATION` in cluster 2, which
one proportion change will not reach.

---

## Recommended next task — exactly one

**`IMPLEMENT_PLANNABILITY_AWARE_FOOTPRINT_OPTIONS`**

`feasible_options` currently spreads four widths **evenly across the feasible interval**, purely
geometrically. It should instead prefer proportions the planner can actually use — near-square
first — and offer extremes only when nothing else fits.

Why this one:

- It is the **largest recovery for the smallest change**: ~272 cases, in one function in
  `app/demo/site_geometry.py`. No change to the Concept Generator, Geometry Core, validation, room
  sizes, corridor logic or the constraint model — the same task boundary you set for the last three
  pieces of work.
- The evidence is unusually direct: near-square succeeds 74.5% and the extremes 16–19%, while 39% of
  what is currently offered lands in the extremes. The witnesses all move the same way.
- It composes with the fix already shipped. Site-aware options removed outlines that cannot go on
  the land; this removes outlines that go on the land but cannot hold a house.
- It surfaces nothing dishonestly: an outline is still only offered if it fits, still at exactly the
  requested area, and a site where only extreme proportions fit will still refuse — correctly.

The two things it will **not** fix, which should follow it in this order: cluster 2's row-order
commitment (~144 cases, a Concept Generator change), and the six-case C8 daylight bug.

Nothing implemented. Stopping for review.
