# #267 — The ground-truth comparison, and the recommendation

**ROOT #262, step 3. The evidence gate before the Construction Intelligence pivot.**
Issue #267 · branch `investigate/lodge-ground-truth` · base `feature/quantity-takeoff-harness`

> The owner's closing instruction for this gate: *the goal is measured trustworthiness, not another
> impressive demonstration, and a thin GO would be the worst possible outcome.*

---

## 0. The recommendation, first

> ## **CONDITIONAL GO — narrow.**
>
> **Two of the owner's five evaluation axes remain unmeasured, and that is part of this
> recommendation rather than a footnote.**
>
> * **Axis 1, source measurement accuracy, is unmeasured and cannot be measured without a real
>   surveyed building.** Nobody measured the Entrance Lodge; it was never built. Every candidate
>   source found across six avenues (#263) and four research sweeps is a *designed exercise*, a
>   *vectorisation* or a *Revit export*. This work did not improve that by one inch and no amount
>   of further reading will.
> * **Comparison B remains unavailable.** #257 established that no plan or document ingestion
>   capability exists anywhere in the product or its history, so there is nothing to extract with.
>   B has no numerator and no denominator. It is reported separately in §5 and is never folded
>   into A.
>
> The GO is conditional on §9's five named, testable conditions, **all five**, and it authorises
> one thing only: the work those conditions describe. It does not authorise a product, a claim, a
> price or a date.

**Why not GO.** Nothing here measures whether a quantity is *right about a building*. The one
comparison this work could construct **misses its frozen tolerance by 3.3×**, and the miss is in
the *source*, not the arithmetic.

**Why not NO-GO.** Three things got better in a way that is measurable rather than rhetorical.
The circularity that invalidated every previous comparison is **gone and proven gone** (§4). The
instrument refused correctly, abstained correctly and **failed zero times out of fifteen** (§3).
And the gate found a *defect in the instrument itself* (§4.3) that was invisible while every
reference was circular — which is exactly what an evidence gate is for.

---

## 1. What changed since #265, in one paragraph

#265 built the instrument and it refused everything: 358 of 358 references over the repository's
19 plans, in both arms, and **Fletcher's own three ceiling comparisons at a residual of exactly
0.0** — because the geometry it was handed came from the same dimension columns the professional
squared his quantity from. *A takeoff cannot validate a calculation that starts from the takeoff's
own dimensions.* #265 named the single input that would fix it: the room polygons, taken off the
figured ground plan, independently of the dimension columns. **This Issue took them off.** Nothing
frozen was edited, no threshold was revised and the guard was not weakened — only the input
changed.

---

## 2. The geometry (AC-1)

Source: **Banister Fletcher & H. P. Fletcher, *Quantities*, 9th ed., B. T. Batsford, 1923**,
`archive.org/details/banisterfletcherh.p.fletcher1923`, **CC Public Domain Mark 1.0** re-verified
on 2026-10-27 from the item's own metadata API (`licenseurl`), and public domain by age in the US
and the UK. Facts, dimensions and computed areas are cited with attribution; no plate, table or
worked example is reproduced.

The full audit trail is
[`data/plate8-ground-plan-geometry.json`](data/plate8-ground-plan-geometry.json) — one citation
per value, naming the plate, the leaf, the figure as printed, the two wall faces it runs between,
and the evidence for that match. The code is `backend/app/ai_harness/quantity_takeoff/plate8.py`.

### 2.1 The one rule

> **A printed figure is the only thing allowed to supply a length.** A pixel measurement on the
> scan decides only *which pair of drawn wall faces a printed figure runs between*. It never
> supplies a value and never overrides a figure. **No coordinate in the derived geometry comes
> from a pixel count.**

That rule is not fastidiousness, it is the schema: `MeasurementMethod` is a closed enum with **no
member a value scaled off a raster could declare itself under**, so a scaled length cannot enter
the schema at all. It is also the quantity surveyor's own rule — dimension paper is squared from
figures, never from a rule laid on the plate.

The scan scale used for *matching only* is **63.4 px per foot** on the archive scan of leaf 516
(6845 × 4234). It is cross-checked five ways against the plate's own figures, before any value was
accepted:

| Check | Predicted | Measured | Error |
|---|---|---|---|
| overall **31'0"** (right-hand dimension) | — | arrowheads y=1125→3090, 1965 px | **0.0%** (defines) |
| overall **37'0"** (bottom dimension) | 2347 px | arrowheads x=3565→5912, 2347 px | **0.0%** |
| overall **22'0"** (archway west wall) | 1395 px | wall y=1680→3069, 1389 px | **−0.4%** |
| figured **14"** wall thickness | 74 px | 75–79 px on four walls | ink spread of the solid poche |
| figured **9"** wall thickness | 48 px | 47–54 px on six walls | ink spread |
| figured **6'6"** (Scullery, E–W) | 412 px | drawn clear 414 px | **0.2 inch** |
| figured **10'0"** (Sitting Room, N–S) | 634 px | drawn clear 635 px | **0.2 inch** |

### 2.2 One room of three closes

**SCULLERY — derived.** A rectangle, **6'6" × 9'9"**, internal clear, matching the project's
`INTERNAL_CLEAR` convention (P11).

| Value | Figure as printed | Runs between | Evidence |
|---|---|---|---|
| clear E–W **6'6"** | `6'.6"` | east face of the 9" Kitchen/Scullery partition → inner face of the 9" east external wall | left arrowhead tip x=5348 on a face at x=5343; right arrowhead tip x=5737 on a face at x=5757; drawn clear 414 px against 412 px predicted — **0.2 inch** |
| clear N–S **9'9"** | `9'.9"` | inner face of the 9" north external wall → north face of the 9" Scullery/Yard partition | the plate prints **two** figures on this axis that differ by exactly one figured wall thickness and share their lower terminus: `10'.6"` runs from the north wall's **outer** face (y=1130) to the partition (arrowhead y=1705), `9'.9"` from its **inner** face to the same partition (arrowheads y=1205, y=1692). **10'6" − 9'9" = 9" = the figured north wall.** The chain closes on printed figures alone. |

**Recorded uncertainty, and it matters.** The *draughting* does not agree with that figure. The
drawn clear depth is 520 px = **8'2½"**, 16% less than the figured 9'9", on a plate whose other
figures check to 0.2%. A second reading of the same figure — `9'9"` taken outer face to outer
face, giving `9'9" − 9" − 9" = **8'3"`** — fits the draughting to 1.3% but leaves the plate's own
`10'6"` terminating on no drawn face. **Both readings are carried.** The chain reading is used in
comparison A because it is built from two printed figures and their printed difference; the second
is reported in §4.2 as an interpretation sensitivity and is **never aggregated**.

**SITTING_ROOM — abstained.** Figured **10'0"** north-to-south against the 14" west wall (and that
figure checks to 0.2 inch). **No west-to-east figure for this room appears anywhere on Plate 8**,
and no chain of printed figures closes it: the covered archway's clear width is unfigured, and the
plate's overall 37'0" does not terminate on a drawn face. The plasterer squares this ceiling at
**14'0" × 10'0"** and *that number may not be borrowed* — borrowing it is precisely the
circularity the guard exists to refuse. `missing_field: rooms[SITTING_ROOM].polygon`.

**ROOM_324B — abstained, twice over.** (1) Its **identity** is not established: no heading for it
appears on #265's transcribed pages, so matching it to the plate's Kitchen would be a guess. (2)
Even taken as the Kitchen, its north-to-south chain (`9" | 7'6" | 9" | 5'0"`) terminates on no
drawn face — the 7'6" segment spans 353–363 px against 476 px predicted — and its south boundary
is part solid wall, part canted wall and part unfigured opening. Its west-to-east dimension *is*
derivable from the top chain as `18'0" − 9" − 6'6" = 10'9"`, and **one derivable dimension does not
close a polygon.** `missing_field: rooms[ROOM_324B].polygon`.

### 2.3 No height is figured on any plate — all ten, both sections included

This is the second finding of §2 and it is larger than the first.

| Leaf | Plate | Figured dimensions |
|---|---|---|
| 502 | 1 — South Elevation | **none** |
| 504 | 2 — West Elevation | **none** |
| 506 | 3 — East Elevation | **none** |
| 508 | 4 — North Elevation | **none** |
| 510 | **5 — Section A-A** | **none** — scale bar only |
| 512 | **6 — Section B-B** | **none** — scale bar only |
| 514 | 7 — First Floor Plan | **none** |
| **516** | **8 — Ground Plan** | **the only fully figured plate; the whole of §2.2 comes from it** |
| 518 | 9 — Roof Plan | **none** |
| 520 | 10 — Drainage Plan | drain sizes, falls, a distance to the boundary — **no room dimension, no height** |

**The 8'0" the plasterer squares his walls at exists only in his dimension columns.** It is not
recoverable from the drawings by any method the schema admits. **F2, wall paintable area, abstains
for every room**, on `WALL_HEIGHT_NOT_STATED`, and would abstain again on
`OPENING_SCHEDULE_NOT_COMPLETE` because not one opening width or area is figured anywhere either.

This is #263's height finding — `Volume / GrossArea` spanning 2.045–4.225 m on one storey —
reproduced on a **complete professional drawing set a century old**. The third dimension is a
**dataset requirement**, not an engine gap, and a ten-plate architect's set by one of the most
published names in British architectural drawing does not supply it.

### 2.4 Provenance grade

Everything taken off the plate grades **`STATED` / `DESIGN_DRAWING_DIMENSION`**, never `VERIFIED`:
#263 V2 calls a design dimension an *intent*, not a measurement, and `Provenance.__post_init__`
refuses to let it grade higher. That is also the formal reason axis 1 stays unmeasured — the
strongest grade this entire ROOT has ever been able to attach to a length is "the architect drew
it".

---

## 3. Comparison A — per material, per project (AC-2)

Project `fletcher-1923-entrance-lodge-PLATE8`: 1 publisher, 3 rooms, 3 openings, convention
`INTERNAL_CLEAR`, wall thickness stated, scale stated, **0 rooms with a stated height**, 6
reference values offered. Full machine-readable output:
[`data/GROUND-TRUTH-results.json`](data/GROUND-TRUTH-results.json).

| Material | Unit | Scopes | Computed | Abstained | Failed | Abstention rate | Failure rate | Accuracy cmps | Cross-check | **Refused** | Passes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FLOORING_AREA | m² | 3 | 1 | 2 | 0 | **66.7%** | 0.0% | 0 | 0 | 0 | — |
| FLOORING_PURCHASE | pack | 3 | 0 | 3 | 0 | **100%** | 0.0% | 0 | 0 | 0 | — |
| WALL_PAINT_AREA | m² | 3 | 0 | 3 | 0 | **100%** | 0.0% | 0 | 0 | 2 | — |
| CEILING_PAINT_AREA | m² | 3 | 1 | 2 | 0 | **66.7%** | 0.0% | 0 | 0 | 3 | — |
| BASEBOARD_LENGTH | m | 3 | 0 | 3 | 0 | **100%** | 0.0% | 0 | 0 | 1 | — |
| **total** | | **15** | **2** | **13 (86.7%)** | **0 (0.0%)** | | | **0** | **0** | **6 of 6** | |

`Passes` is `—`, never `False` and never `True`: with no accuracy-bearing comparison the question
of passing does not arise, and the harness says so in the type rather than in a note.

### 3.1 Absolute and percentage error, where a quantity was computed

| Material | Scope | Computed | Reference (1923 takeoff) | Absolute error | Percentage error | Frozen tolerance | **Within tolerance** | Status |
|---|---|---|---|---|---|---|---|---|
| CEILING_PAINT_AREA | SCULLERY | **5.88773016 m²** (63.375 sq ft, 6'6" × 9'9") | **5.52773088 m²** (59.5 sq ft, booked 8'6" × 7'0", p.324) | **+0.35999928 m²** | **+6.51%** | 2.0% rel / 0.10 m² abs → **0.11055 m²** | **NO — 3.26× over** | **REFUSED** (R1) |
| FLOORING_AREA | SCULLERY | 5.88773016 m² | *no reference exists* | — | — | — | — | — |

Percentage error is reported for the only comparison whose denominator clears
`MIN_MEANINGFUL_DENOMINATOR` (1.0 m²). Everywhere else the quantity abstained, so there is no
numerator.

### 3.2 Missing measurements, and the manual correction effort

Every abstention names **the one field a human would have to supply** to turn it into a
computation. That count *is* the manual-correction-effort metric — a count, not an opinion.

| Material | Effort (distinct field-supplies) | The fields |
|---|---|---|
| FLOORING_AREA | 2 | `rooms[SITTING_ROOM].polygon`, `rooms[ROOM_324B].polygon` |
| FLOORING_PURCHASE | 3 | the two polygons, plus `rooms[SCULLERY].finishes[FLOOR]` |
| WALL_PAINT_AREA | 3 | `rooms[SCULLERY].wall_height`, plus the two perimeters |
| CEILING_PAINT_AREA | 2 | the two polygons |
| BASEBOARD_LENGTH | 3 | `openings[SCULLERY-PLATE8-0].width`, plus the two perimeters |
| **total** | **13** | |

Collapsed to distinct human actions: **figure two room polygons, state one wall height, state one
floor finish, state three opening widths.** Six facts would take this project from 2 computed
quantities to 15. None of the six is on any of the ten plates.

### 3.3 Unsupported categories

**One**, and it is a different outcome from a missing field. `FLOORING_PURCHASE/SCULLERY` abstains
on `FINISH_NOT_STATED` — the plate names no floor finish for the Scullery, so there is no product,
therefore no pack size, therefore no purchase quantity. No `UNSUPPORTED_FINISH_CATEGORY` was
reached, because the run never got as far as a finish the harness holds no convention for.

### 3.4 Provenance completeness

Two fractions, as #265's metric table defines them. The **P fraction** is the per-project #263
fields this material needs that are present with a provenance; the **V fields** are enforced by
the constructor, so an incomplete provenance cannot exist and the informative figures are the
count and the grades.

| Material | P fraction | P fields missing (count of room-slots) | Reference values | V5 grades | V2 weaker methods |
|---|---|---|---|---|---|
| FLOORING_AREA | **0.667** | P10 ×3, P1\|P4 ×2 | 0 | — | 0 |
| FLOORING_PURCHASE | **0.476** | P10 ×3, L5:pack ×3, L5:wastage ×3, P1\|P4 ×2 | 0 | — | 0 |
| WALL_PAINT_AREA | **0.583** | **P8 ×3**, **P9 ×3**, P1\|P5 ×2, P6 ×1, P7 ×1 | 2 | STATED ×2 | 0 |
| CEILING_PAINT_AREA | **0.667** | P10 ×3, P1\|P4 ×2 | 3 | STATED ×3 | 0 |
| BASEBOARD_LENGTH | **0.800** | P1\|P5 ×2, P6 ×1 | 1 | STATED ×1 | 0 |

**P8 is missing in 3 of 3 rooms and P9 in 3 of 3.** That single row is §2.3 restated as a metric.

### 3.5 Failure rate

**0 of 15. Zero.** No formula raised, on a project where thirteen of fifteen inputs were absent.
`MAX_FAILURE_RATE` is 0.0 and it is met. An abstention is a recorded result with a reason code; a
failure would be a crash. The distinction held under the worst input this ROOT has produced.

---

## 4. The self-validation guard: what the independent geometry changed, and what it did not

### 4.1 R2, the geometric-identity half — **cleared, for the first time in this ROOT**

| Arm | Comparison | Residual | Identity band | Headroom | R2 verdict |
|---|---|---|---|---|---|
| #265 — geometry from the takeoff's own dimension columns | CEILING / SCULLERY | **0.0** | 0.01 m² | 0× | **REFUSED** |
| #265 | CEILING / ROOM_324B | **0.0** | 0.01 m² | 0× | **REFUSED** |
| #265 | CEILING / SITTING_ROOM | **0.0** | 0.01 m² | 0× | **REFUSED** |
| #265 | BASEBOARD / ROOM_324B | 2.5908 m | 0.01 m | 259× | not an identity (refused by R1 alone) |
| **#267 — geometry figured on Plate 8** | **CEILING / SCULLERY** | **0.35999928 m²** | **0.01 m²** | **36.0×** | **NOT REFUSED** |

That row is the thing this Issue was created to produce. **The circularity is gone and the
guard's own empirical test says so.** Across 358 references on 19 plans, 3 on Fletcher's own
columns and now 1 on Plate 8, this is the first area reference the identity guard has ever let
through.

### 4.2 And the answer, once it was allowed through, is **wrong by 6.5%**

| Reading of the plate's own N–S figure | Clear | Computed | Error vs the 1923 quantity | Within 2.0%? |
|---|---|---|---|---|
| **chain** (used in comparison A) — `9'9"` and `10'6"` share their lower terminus and differ by the figured 9" north wall | 6'6" × 9'9" | 5.88773016 m² | **+0.35999928 m² / +6.51%** | **no** |
| outer face to outer face (**sensitivity only, never aggregated**) — `9'9"` across both walls, less two figured 9" thicknesses | 6'6" × 8'3" | 4.98192552 m² | **−0.54580536 m² / −9.87%** | **no** |

**The two readings of the same printed figure bracket the professional's quantity from opposite
sides, and neither is inside the frozen tolerance.** No choice of reading rescues it. There are
three different answers for one small room in one book:

* the plate **figures** it 6'6" × 9'9" = 63.375 sq ft;
* the plate **draws** it 6'6" × 8'2½" ≈ 53.3 sq ft;
* the plasterer **squared** it 8'6" × 7'0" = 59.5 sq ft.

**Attribution of the miss (AC-4): GEOMETRY — and specifically the source's own.** Not the
measurements (there are none; axis 1 is unmeasured). Not the material assumptions (F3's flat-
ceiling assumption is unengaged here: Section B-B shows a flat ground-floor ceiling under the
first floor). Not the calculation logic (F3 is `net plan area − stated ceiling openings`, there
are no ceiling openings, and the arithmetic is an exact unit conversion of two printed figures,
verified to the bit by test). The gap is that **the drawing disagrees with itself, and the
professional resolved that disagreement a third way without recording that he had.**

### 4.3 R1, the declared-class half — **refuses all six, and that is a defect in the instrument**

| Reference | Material | R1 refusals | Severity |
|---|---|---|---|
| SCULLERY ceiling | CEILING_PAINT_AREA | `SAME_CALCULATION_CLASS` | FATAL |
| SITTING_ROOM ceiling, walls | CEILING / WALL_PAINT | `SAME_CALCULATION_CLASS` | FATAL |
| ROOM_324B ceiling, walls, skirting | CEILING / WALL_PAINT / BASEBOARD | `SAME_CALCULATION_CLASS` | FATAL |

No other refusal fires: V5 is `STATED`, P11 is `INTERNAL_CLEAR`, the independence statement names
no part of this system, and nothing declares itself computed from the supplied geometry.
`SAME_CALCULATION_CLASS` fires alone, on all six.

**Why.** `frozen.REFERENCE_VALUE_CLASS_CONFLICT` maps a quantity's calculation *class* to the
reference classes that disqualify it. A plasterer's squared ceiling is a `PLAN_POLYGON_AREA`
figure and `CEILING_PAINT_AREA` **is** a `PLAN_POLYGON_AREA` calculation, so the reference is
refused. The rule compares **the kind of arithmetic**, not **the inputs the arithmetic ran on**.

**The consequence, stated plainly: under the frozen rules as written, no professional takeoff of
an area can ever be scored, however independent its measurements are.** Length × breadth is what
an area takeoff *is*. The rule is unsatisfiable for the only kind of reference that exists.

This is not a reason to weaken the guard and it is not weakened here. It is a **finding about the
instrument that was invisible while every reference was circular** — R1 and R2 agreed on
everything, so R1's over-breadth never showed. The independent geometry separated them, and the
separation is what exposed it. Fixing it is **condition C1 in §9**, and it belongs to a *new*
freeze, not to an edit of this one.

---

## 5. Comparison B — **NOT APPLICABLE** (AC-3)

> **Comparison B: quantities computed from AUTOMATICALLY EXTRACTED measurements.**
>
> **Status: NOT APPLICABLE.** #257 (PR #258) established that no plan or document ingestion
> capability exists — no PDF, raster, OCR, DXF, DWG, IFC or SVG-parsing dependency on any of 71
> branch tips or anywhere in history, and `python-multipart` is absent from the lockfile, so the
> service cannot physically accept an uploaded file. **There is nothing to extract with, so B has
> no numerator and no denominator.**

It is a **different type** from comparison A in the harness, with no field a number could be
written into, and a test asserts that it holds no numeric value. It is reported here, separately,
and is **never folded into A**. Nothing in §3 or §4 is a B result.

**And note what §2 says about B's future difficulty.** The extraction B would need is not OCR of a
dimension string. On this set it would have to: find the one figured plate out of ten; read
hand-lettered figures that defeat the archive's own OCR entirely; decide **which pair of wall
faces each figure runs between** (§2.1), which is where every ambiguity in this report lived; and
**notice that the plate disagrees with itself** (§4.2) rather than silently picking one reading.
A system that did the first two and not the last two would have produced 63.375 sq ft with
complete confidence and been 6.5% wrong.

---

## 6. The convention disagreement is a result, not noise (AC-5)

Professional practice is **not internally consistent**, and the inconsistency is larger than every
tolerance in `frozen.py`. All three divergences below are measured on Fletcher's own pages and
none is reported as an error — a convention divergence is a **fifth** thing, beside measurements,
geometry, assumptions and logic, and conflating it with an error is how an instrument gets blamed
for a disagreement about a rule.

| Formula | Our frozen choice | The source's own rule | Divergence | Frozen tolerance | Exceeds? |
|---|---|---|---|---|---|
| **F4 baseboard length** | `BASEBOARD_BREAKS_AT_DOOR_OPENINGS = True`, full stated opening width deducted | **The joiner** (p.84): collect the wall lengths "making the deductions for doors, chimney-pieces, &c.". **The plasterer** (p.132): "Take the lengths and collect the same on 'Waste'", and on p.325 the cement skirting of ROOM_324B is booked at its **full** 35'6" girth with the breaks numbered separately as 8 stopped ends, 2 mitres and 4 irregular | ours 8.2296 m vs source 10.8204 m, **−23.94%** | 2.5% | **yes, 9.6×** |
| **F3 ceiling paintable area** | `CEILING_IS_FLAT_AND_COINCIDENT_WITH_FLOOR = True`, no cornice deduction | p.128: where cornices occur "it is customary to make a deduction of the width of the cornice upon each dimension" — his own worked example books a 20'0" × 16'0" room with a 12" cornice as 19'0" × 15'0" | **10.94%** | 2.0% | **yes, 5.5×** |
| **F2 wall paintable area** | `WALL_PAINT_DEDUCTS_SKIRTING_BAND = False`, measured floor to ceiling | p.130: the height is "taken **from the top of the skirting grounds** to the ceiling", less half the cornice height where there is one | ~4.0% at a 0.10 m skirting on a 2.50 m height | 3.0% | **yes** — and this is the one term the freeze *deliberately* placed outside the tolerance budget, because it is bigger than the tolerance |

**The headline is the first row. The joiner and the plasterer, in the same book, by the same
authors, about the same room, disagree with each other by 23.94% on where skirting breaks.** Not
two schools of thought in two countries a century apart — two trades on facing pages of one
worked example. **No frozen value was revised in their light**; the fixture was identified after
the freeze and the divergences are recorded as divergences.

### 6.1 What this means for the product — the part that is not a footnote

> **A trustworthy quantity is one that names its convention. A quantity that does not name its
> convention is not a quantity, it is a number with a unit on it.**

The divergences above are **7×, 5× and 1.3× the tolerances the same work is held to**. So a
product that computes to ±2% and does not state its convention is reporting a precision that its
own convention choice destroys. Three consequences, each of them a product decision rather than an
engineering one:

**(a) These conventions must become explicit inputs, not constants.** Every one of them is
currently a module constant in `frozen.py`, correctly named as a *choice* and correctly bounded —
but a constant. Each must become a per-job input carried on the result:

| Must become an input | Because | Spread it controls |
|---|---|---|
| **Does skirting break at an opening?** (break at full structural opening / break at leaf / run through and let the joiner deduct) | the two trades in one book disagree | **23.9%** |
| **Is a cornice deducted from the ceiling, and at what girth?** | the source's own rule deducts it; ours does not | **10.9%** |
| **Where does the wall height start** — floor, or top of the skirting grounds? | the source's rule contradicts ours directly | **~4.0%** |
| **Is an opening deducted whole, half, or not below a threshold?** | ours deducts every stated opening; Fletcher deducts the full structural opening *including grounds*; Nichols (1908, relayed) deducts **half** | a third convention again |
| **Internal clear / centre-line / external** | already P11, already enforced | **~12%** on a 3×4 m room |
| **Figures govern, or scale the drawing?** | §4.2: on this plate the two differ by 16% on one room | **16%** here |

That last row is **new to this Issue** and is not in `frozen.py` at all. It was invisible until a
geometry was derived from a drawing rather than from a bill.

**(b) What a user must state before a number can be given at all.** Eight facts. A product that
cannot collect all eight should abstain, in the user's face, with the name of the missing one —
exactly as the harness does:

1. the **trade and method of measurement** the quantity is for (the skirting rule follows from it);
2. the **area convention** (P11) — in Israel, Standard 9 supplies this by law for a dwelling;
3. the **wall height**, measured, with its datum (floor or top of grounds) — *never inferred*;
4. whether there is a **cornice**, and its girth;
5. the **opening schedule**, declared complete, with widths and heights;
6. the **floor finish** per room, and the product's pack coverage and **wastage allowance** — an
   input, never a guess, and Fletcher's own rule (p.84) states a cutting-and-waste *dimension*
   rather than a percentage;
7. the **source-of-truth rule** when the drawing disagrees with itself: figures govern, or scale;
8. the **drawing revision** the answer belongs to.

**(c) Two numbers under two conventions are not an error bar, they are two answers.** The product
must be able to produce the same takeoff under two named conventions and show the difference as a
*convention difference*, not as uncertainty. The harness already carries the conventions on every
result and refuses to let a figure travel without them; the product must do the same thing in its
output, not in a footnote.

---

## 7. Against the frozen thresholds — no threshold revised (AC-4)

`frozen.py` has **exactly one commit** (`4ef4f3b`, the freeze), which precedes every result commit
on this branch, and a test asserts it (`test_step_3_revised_no_frozen_threshold_and_no_frozen_convention`).
The values below are the ones applied, read out of the module at run time.

| Threshold | Frozen value | Applied | Met? |
|---|---|---|---|
| `TOLERANCE_REL[CEILING_PAINT_AREA]` | 2.0% | 2.0% | **NO** — the one comparison is +6.51% |
| `TOLERANCE_ABS[CEILING_PAINT_AREA]` | 0.10 m² | 0.10 m² | **NO** — error 0.35999928 m² |
| `TOLERANCE_REL` (flooring / baseboard / wall paint / purchase) | 2.0% / 2.5% / 3.0% / 0% | unchanged | **not reached** — nothing computed to compare |
| `MIN_WITHIN_TOLERANCE_RATE` | 0.90 | 0.90 | **not reached** — 0 accuracy comparisons |
| `MAX_ABSTENTION_RATE` | 0.25 | 0.25 | **NO** — 0.667 to 1.000 per material, **0.867 overall** |
| `MAX_FAILURE_RATE` | 0.0 | 0.0 | **YES** — 0 of 15 |
| `IDENTITY_ABS_M2` / `IDENTITY_REL` | 0.01 / 0.0005 | 0.01 m² on this reference | **cleared at 36.0×** |
| `MIN_DISTINCT_PUBLISHERS` | 2 | 1 | **NO** |
| `MIN_PROJECTS_WITH_HEIGHT` | 3 | **0** | **NO** |
| `MIN_PROJECTS_WITHOUT_HEIGHT` | 5 | 1 | **NO** |
| `frozen.verdict()` | — | **`NOT_EVALUABLE`** | one publisher cannot be mistaken for reality (#263 §1.4) |

**`frozen.verdict()` was run, not replaced.** It returns `NOT_EVALUABLE` and stops on the
accuracy-bearing count before it reaches a tolerance. §0's CONDITIONAL GO is a **recommendation
about the pivot**, made by a human reading all of the above; it is not, and must never be reported
as, a verdict of that function.

### 7.1 Every miss, attributed

| Miss | Attribution | Evidence |
|---|---|---|
| CEILING / SCULLERY at +6.51% | **geometry — the source's own, not the engine's** | §4.2: the plate figures, the plate draws, and the plasterer squared, three different answers for one room |
| Abstention rate 0.867 ≫ 0.25 | **measurements** — absent inputs, not a broken formula | §3.2: 13 abstentions, each naming one field; 6 distinct facts would clear all of them |
| WALL_PAINT 100% abstained | **measurements** | §2.3: **no height on any of ten plates, both sections included**, and AC-4 forbids inferring it |
| BASEBOARD 100% abstained | **measurements** | three doorways drawn on the plate, **no width figured for any of them**; F4 abstains rather than treat a drawn doorway as solid wall |
| FLOORING_PURCHASE 100% abstained | **measurements** + **material assumptions as inputs** | no floor finish stated, therefore no product, therefore no pack coverage and no wastage — and wastage is an input, never a guess |
| 6 of 6 references refused | **calculation logic — of the instrument** | §4.3: `SAME_CALCULATION_CLASS` compares the kind of arithmetic, not the inputs; condition **C1** |
| Convention divergences of 23.94% / 10.94% / ~4.0% | **none of the four — a fifth thing** | §6; recorded as convention divergences, never as errors |

---

## 8. What this gate did *not* establish

Said here so that no reader has to infer it.

1. **Axis 1, source measurement accuracy: unmeasured, and unmeasurable from any source found.**
   Nobody measured the Entrance Lodge. The strongest grade attachable to any length in this work
   is `STATED` / `DESIGN_DRAWING_DIMENSION` — "the architect drew it".
2. **Comparison B: unavailable — not applicable, and reported as such.** No extraction capability
   exists (§5), so B has no numerator and no denominator.
3. **No system accuracy figure exists, and none could honestly be given.** 1 publisher against a
   minimum of 2; 1 project against a minimum of 5; 0 projects with a height against a minimum of 3.
4. **Four of the five materials were never scored at all**, because they never computed.
5. **One room of three, in one project.** Two rooms abstained and the bill's numbers were not
   borrowed to close them.
6. **The 1923 plate itself is partly unresolved**: the overall 37'0" terminates on no drawn wall
   face at the scale its own siblings establish, and the plate's drawn west-to-east extent scales
   38'5". Recorded; nothing in §2.2 depends on it.
7. **ROOM_324B's identity is still unverified.** It is still carried under a neutral id and still
   not called the Kitchen.
8. **Leaning 1897 and Brooks 1870 are still unread**, and Nichols 1908 is still relayed rather than
   fetched — only its arithmetic was checked internally. Unchanged from #265 and still labelled as
   unread in the data file.

---

## 9. The recommendation, with its conditions (AC-6)

> # CONDITIONAL GO — narrow
>
> **Axis 1, source measurement accuracy, remains unmeasured without a real surveyed building, and
> comparison B remains unavailable: two of the owner's five evaluation axes.** Both are stated
> here, in the recommendation, because neither is a detail and the second has no engineering fix
> short of building an ingestion capability that has never existed.

Conditional on **all five** of the following. Each is named, testable, and has a stated failure
action. None of them is "try harder".

| # | Condition | Test (the evidence that settles it) | If it fails |
|---|---|---|---|
| **C1** | **Re-specify the self-validation guard so it refuses on shared INPUTS, not on shared arithmetic class.** `SAME_CALCULATION_CLASS` must become a refusal only where the reference's *provenance* traces to the geometry supplied, with R2 remaining the empirical backstop. The re-specification is a **new** frozen module committed **before** the next comparison runs; `frozen.py` is not edited. | The SCULLERY comparison reaches `status == ACCURACY` with R2 still clearing it at ≥30× the identity band, **and** a reference that genuinely *is* computed from the supplied polygon is still refused. Both, in tests, in one run. | **NO-GO.** Without C1 the instrument cannot score any area takeoff and the gate can never be passed by any dataset. |
| **C2** | **One real building, measured.** A professional takeoff — a **כתב כמויות** — for the four materials, with units and the measurer's name, plus the plan at a stated scale, per-room areas measured on site with the method and convention named, a door and window schedule with width **and** height, measured wall heights, and wall thickness with its convention. | ≥1 project grading `VERIFIED` on ≥1 material, with its P11 stated and its reference clearing both halves of the guard. | **NO-GO on any accuracy claim.** Axis 1 stays unmeasured and the product may never say a number is right about a building — only that it is right about a drawing. |
| **C3** | **The conventions of §6.1(a) become per-job inputs carried on every result**, with the six listed above represented, including the new **"figures govern / scale the drawing"** rule. | A test produces the *same* takeoff of the *same* room under two named conventions and the two differ by the §6 magnitudes (23.9% / 10.9% / 4.0%); and **no** quantity can be emitted with a convention unstated. | **NO-GO.** A ±2% engine under an unnamed convention is a precision claim its own convention destroys. |
| **C4** | **The eight facts of §6.1(b) are collectable, and absence abstains in the user's face** with the name of the missing field. | On a deliberately incomplete job, the product returns an abstention naming exactly one field per missing fact, and **never** a number; the failure rate stays 0. | **Re-scope to an assistive tool**, not a quantity source: it may help a surveyor, it may not answer. |
| **C5** | **The gate is re-run and reported before anything is built on top.** §3's table, regenerated, against the same thresholds, with C1–C4 in place. | ≥3 materials with ≥1 accuracy comparison each; within-tolerance rate reported against `MIN_WITHIN_TOLERANCE_RATE`; abstention rate against `MAX_ABSTENTION_RATE`; `frozen.verdict()` run, not replaced. | **NO-GO**, and the ROOT closes. |

**The order matters.** C1 is cheap and must come first, because until it is done C2's expensive
data cannot be scored. C2 is the only one that needs something the owner alone can supply. C3 and
C4 are product decisions that C5 then measures.

### 9.1 What would make this a NO-GO tomorrow

Stated in advance so it cannot be reinterpreted later: **if C2 is not obtainable within the next
phase, the honest outcome is NO-GO on the pivot as a quantity product**, regardless of how well
C1, C3 and C4 go. Everything in C1/C3/C4 improves the *instrument*; none of it moves axis 1. A
quantity product whose accuracy against a real building has never been measured is the "visually
impressive demonstration" the directive forbids, with better internal hygiene.

---

## 10. A sized minimal architecture for the next phase (AC-7)

Sized against **#257's finding that reuse concentrates at the bottom of the stack and at the top,
never the middle** — and this Issue is a direct confirmation of it. Layer 3 (canonical geometry)
was reused unchanged and the polygon dropped straight in. Layers 4–5 were reused unchanged. The
*middle* — the thing that turns a drawing into geometry — did not exist and had to be done by
hand. All 282 of this Issue's 452 new lines are that middle, and so is every hour of §2.

| Layer | Component | Reused / New | Size | Why |
|---|---|---|---|---|
| **1. Ingestion** | — | **NOT BUILT** | **0** | Deliberately. §5: building ingestion to make B measurable is the single most expensive thing on this list and it would be built before anything had proven it was worth ingesting *into*. Defer past C5. |
| **2. Measurement entry** | `plate8.py` generalised to a **manual, cited take-off form** — a human enters each figure with the plate, the sheet, and the two faces it runs between | **NEW, small** | **~250 LOC + a form** | The only new middle piece, and it is deliberately *manual*. §2.1's rule and §2.2's abstentions are the specification; it is the same work a surveyor already does on dimension paper. |
| **3. Canonical geometry** | `schema.RoomGeometry` | **REUSED, unchanged** | **0** | Shoelace area and perimeter, exact on the derived rectangle to the bit (test). Took the plate geometry with no change at all. |
| **3b. Provenance & schema** | `schema.Measured` / `Provenance` / `ReferenceProject` | **REUSED, unchanged** | **0** | Carried `DESIGN_DRAWING_DIMENSION` correctly, refused to let it grade `VERIFIED`, and had no field a scaled value could enter under. The bottom of the stack did its job. |
| **4. Formulas** | `formulas.py` F1–F4 | **REUSED, unchanged** | **0** | 15 scopes, 2 computed, 13 abstained, **0 failed**, every abstention naming one field. Nothing about the new input stressed it. |
| **4b. Conventions** | `frozen.py` constants → **per-job convention inputs** (C3) | **NEW, replacing constants** | **~150 LOC + 6 inputs** | §6.1(a). A new frozen module; the old one is not edited. |
| **5. Product specs** | `schema.ProductSpec` | **REUSED, unchanged** | **0** | Abstained correctly on a missing finish. |
| **6. Pricing** | — | **NOT BUILT** | **0** | Out of ROOT scope and absent rather than stubbed; a test asserts no price, rate or currency identifier exists anywhere in the package. |
| **Guard** | `selfcheck.py` R1 re-specified, R2 unchanged | **NEW frozen module + ~40 LOC** | **~90 LOC** | C1. R2 is already right and proven right by §4.1; only R1's class rule changes. |
| **Harness** | `harness.py` | **REUSED, unchanged** | **0** | Emitted every directive metric on an input it had never seen. |
| **Runner / report** | `run267.py` | **REUSED, extended** | **~60 LOC** | C5 re-runs it. |

**Total new code: roughly 550 lines and one data-entry form**, against the **2,358 lines of
#265's package reused unchanged**. **The reuse ratio is ~81%, and every line of the new 19% sits
in exactly the two places #257 predicted: the measurement-entry middle, and the convention layer
just above the formulas.** This Issue is the same shape in miniature: 452 new lines, of which 282
are the manual measurement entry and 170 are a runner, and not one line of layer 3, 4 or 5 changed.

**What is deliberately not in the architecture:**

* **no automatic plan extraction** (§5) — it is the most expensive component and the least
  justified before C5;
* **no inference of any kind** — no height from a volume, no scale from a pixel count, no "typical"
  anything; the schema has no member any of them could declare itself under and that property is
  load-bearing, not decorative;
* **no generator validator** as a building-validity check — #242's R1 measured why (0 of 19 real
  plans carried, 18 of 19 refused on a policy condition unrelated to geometry);
* **no pricing, no suppliers, no marketplace** — deferred behind this gate by the directive and
  absent from the code;
* **no regulatory claim.**

---

## 11. Isolation, and what was not done

* **No production change.** The diff is additive and lives under
  `backend/app/ai_harness/quantity_takeoff/`, its own test file and
  `docs/reports/construction-intelligence/`. Tests assert that nothing outside the package imports
  it, that it imports no production module and no generator validator, that it rebinds and patches
  nothing, that deleting the directory restores the tree, and that no price, rate or currency
  identifier appears anywhere in it.
* **Nothing frozen was edited.** `frozen.py` still has exactly one commit, asserted by test.
* **No threshold was revised**, in either direction, before or after seeing a result.
* **The guard was not weakened.** R1 refuses all six references and this report says so in §4.3
  rather than relabelling anything to get past it.
* **No test was weakened**; #265's 57 still pass unchanged and 15 were added.
* **Nothing merged, deployed, paid for or notified.** No `agentctl notify`, no admin exemption.
* **No fabricated measurement.** Where the plate figures nothing, the field is absent and the
  formula abstains.

### Test counts, verbatim

```
backend/tests/ai_harness/test_quantity_takeoff.py    72 passed in 0.70s
  (57 from #265, unchanged and still passing; 15 added by #267)
```

---

## 12. One paragraph for the owner

We took the Lodge's geometry off the architect's own ground plan instead of off the surveyor's
arithmetic, and the circularity that invalidated every previous comparison is gone — measured
gone, at 36× the identity band. What came through the gap is sobering. One room of three closed;
no height is figured on any of ten plates including both sections, so wall paint cannot be
computed at all; thirteen of fifteen quantities abstained; and the one quantity that *could* be
compared is **6.5% wrong, with the error living in the source**, which figures the room one way,
draws it another and was squared by the professional a third. In the same book, the joiner and
the plasterer disagree with each other by **24%** about where skirting breaks. Nothing crashed,
nothing was invented and nothing was fudged — the instrument behaved exactly as designed, and in
behaving correctly it exposed a flaw in its own guard that no circular reference could ever have
revealed. **The verdict is a narrow CONDITIONAL GO on five testable conditions, and two of your
five axes are still unmeasured: comparison B has nothing to run on, and source measurement
accuracy needs one real building that somebody actually measured.**
