# #265 — The measurement schema, the quantity formulas and the evaluation harness

ROOT: **#262** (owner directive 2026-10-27, the mandatory evidence gate before the Construction
Intelligence pivot). Child 2 of 3. Child 1 is **#263** (PR #264, verdict PARTIAL); child 3 is
**step 3**, the ground-truth comparison and the recommendation.

> **What this document is, and is not.** It is the **instrument**, not the measurement. #263
> searched six avenues and established that **no reference quantity for flooring, ceiling paintable
> area, baseboard length or wall paintable area exists in public licensed form**. So there is
> nothing to be accurate *against* yet. This child builds the schema, the four formulas and the
> harness so that when one reference project with a professional takeoff arrives, the comparison is
> a **run**, not a project. No accuracy figure is reported here, because none can honestly be
> produced. §8 is the one real reference quantity that could be acquired — a 1923 professional
> takeoff in the public domain — and §8.1 says sharply what it does and does not validate. §10
> states exactly what input makes step 3 runnable.

**Harness only.** Everything lives in `backend/app/ai_harness/quantity_takeoff/` and
`backend/tests/ai_harness/test_quantity_takeoff.py`. No production file is changed, no existing
test is weakened, no generator validator is used as a building-validity check, and deleting the
directory restores the tree. Nothing is merged or deployed.

---

## 0. The three facts that shaped the design

Each is a measurement somebody already made, not a position.

| Fact | Where from | What it forced |
|---|---|---|
| Across all **179** real rooms in the repository's **19** ResPlan plans, the stated `area_m2` equals the **shoelace area of the room's own polygon** to **0.00061299 m²** | #263, re-measured here | The repository's own area field is an **identity**, not a reference. §7 makes offering it as ground truth impossible — not discouraged, refused. |
| **0 of 20** fixtures carry a height, material, finish or paint field, and the one acquired model's `Volume / GrossArea` spans **2.045 m to 4.225 m** on a single storey | #263 | A wall height is **an input with provenance or it is absent**. Never a quotient, never a default. The schema has **no field a quotient could enter under** (§2.3). |
| The generator's validators refused a **policy** condition unrelated to geometry in **18 of 19** real plans | #242's R1 (PR #259) | They encode what the generator *may build*, not what a building *is*. **Not imported here for any building-validity purpose** — §11 asserts it with a test. |

---

## 1. The six layers, and which two this child builds

ROOT #262 requires the layers kept separate. They are separate **modules with no upward imports**:

| # | Layer | Module | State |
|---|---|---|---|
| 1 | Plan and document ingestion | — | **Does not exist** (#257). Comparison B therefore reports **NOT APPLICABLE** (§5.2). |
| 2 | Measurement extraction | — | Does not exist (#257). Same consequence. |
| 3 | Canonical geometry | `schema.py` (`RoomGeometry`) | Built: polygon → area, perimeter, by shoelace. Pure. Knows no material. |
| 4 | Quantity calculations | `formulas.py` | Built: the four formulas of §3. Reads only layer 3 plus provenance-carrying inputs. |
| 5 | Product specifications | `schema.py` (`ProductSpec`) | Built as **inputs**: pack coverage and wastage carry provenance; absent ⇒ abstain. Never inferred. |
| 6 | Pricing | — | **Out of scope** of this ROOT. No price, no rate, no currency appears anywhere in the harness. |

A layer-3 function is forbidden to know a material and a layer-4 function is forbidden to touch a
polygon except through layer 3. That is what keeps "the geometry is right" and "the quantity is
right" separately falsifiable — the directive's central requirement.

---

## 2. The schema (AC-1)

`backend/app/ai_harness/quantity_takeoff/schema.py`. The fields are **exactly #263's contract**:
eleven per project (P1–P11), six per reference value (V1–V6).

### 2.1 Per project — P1…P11

| # | Field | Type in the schema | Required for |
|---|---|---|---|
| P1 | The plan itself | `rooms: tuple[RoomRecord, ...]`, each with a polygon **or** a stated area | all |
| P2 | Licence, explicitly stated by the publisher | `licence: str` (non-empty, enforced) | all |
| P3 | Metric scale, **measured** | `scale: Measured[float] \| None`; the method enum has no "inferred" member | all |
| P4 | Per-room floor area as measured, with the method named | `RoomRecord.stated_area: Measured[float] \| None` | flooring, ceiling |
| P5 | Room perimeters, or geometry to derive them | `RoomRecord.stated_perimeter` **or** `RoomRecord.polygon` | baseboard, wall paint |
| P6 | Door widths | `OpeningRecord.width: Measured[float] \| None` | baseboard, wall paint |
| P7 | Window widths and sill/head dimensions | `OpeningRecord.width`, `.sill_height`, `.head_height` | wall paint |
| P8 | **Wall height, stated by the source** | `RoomRecord.wall_height: Measured[float] \| None` | wall paint |
| P9 | **Opening areas, stated by the source** | `OpeningRecord.area: Measured[float] \| None` | wall paint |
| P10 | Finish type / material per surface, as an input carrying provenance | `RoomRecord.finishes: dict[Surface, Measured[str]]` | all, where distinguished |
| P11 | Wall thickness **and the measurement convention** | `wall_thickness: Measured[float] \| None`, `convention: MeasurementConvention` | all |

### 2.2 Per reference value — V1…V6

Every number offered as ground truth carries all six or it is not a reference value. The
constructor rejects it; there is no partially-specified reference.

| # | Field | Type | Enforcement |
|---|---|---|---|
| V1 | Source — publishing body **and a resolvable citation** | `source`, `citation` | both non-empty |
| V2 | Measurement method | `MeasurementMethod` (5 closed members) | `DESIGN_DRAWING_DIMENSION` and `PUBLISHER_COMPUTED` are flagged **weaker** in the type and **cannot grade `VERIFIED`** |
| V3 | Units, explicit | `units: str` | must equal the material's unit; a bare number is rejected |
| V4 | Revision | `revision: str` | non-empty |
| V5 | Reliability | `Reliability` — `VERIFIED` / `STATED` / `DERIVED` / `UNVERIFIED` | only the first two may support an accuracy claim |
| V6 | Independence | `independence: str` | non-empty, and a statement naming BuildSmart or a BuildSmart-derived artifact is **refused** (`NOT_INDEPENDENT`) |

### 2.3 Why the schema cannot express "typical"

This is the part that is a design, not a rule in a document:

1. **There is no `default=` anywhere.** Every input that could carry a convenient default —
   wall height, pack coverage, wastage allowance, finish, scale, wall thickness — is a
   `Measured[T]`, and `Measured` has **no constructor that takes a value without a provenance**.
   An absent input is `None` and `None` makes the formula **abstain**.
2. **The method enum is closed and has no member for an inference.** There is no
   `ASSUMED`, no `TYPICAL`, no `INDUSTRY_STANDARD`, no `COMPUTED_FROM_VOLUME`, no
   `SCALED_FROM_RASTER`. A height recovered as `volume / area` has nothing to declare itself
   under, so #263's 2.045 m–4.225 m quotient cannot enter the schema at all.
3. **The grade ladder has no rung between `STATED` and `DERIVED`.** A promoted default is not a
   provenance (#263), and there is no grade that would let it pretend to be one.
4. **A test enforces it.** `test_the_schema_has_no_way_to_express_a_typical_value` greps every
   module in the directory for a default-bearing construct and for the tokens `typical`,
   `assume`, `default height`, `standard height` and the literals `2.4`/`2.5`/`2.7` appearing as a
   height, and `test_measured_cannot_be_built_without_a_provenance` asserts the constructor
   refuses. `test_no_quotient_can_enter_as_a_height` asserts there is no enum member a quotient
   could use.

---

## 3. The four formulas, with their assumptions (AC-2)

Each formula states **inputs**, **deductions**, **conventions** and **assumptions**. Where a
convention is contested the choice is **named as a choice** and its magnitude is bounded, so a
disagreement with a quantity surveyor is locatable rather than mysterious. All of them are frozen
constants in `frozen.py` §4; the harness copies the applicable ones onto **every result**, so no
figure ever travels without the conventions that produced it.

### F1 — Flooring area, and purchase quantity

```
net_floor_area          = area(room polygon)   or   stated_area        [m²]
purchase_quantity       = ceil( net_floor_area × (1 + wastage) / pack_coverage )   [packs]
```

* **Inputs.** P4 stated area **or** P1 polygon (layer 3 shoelace); P11 convention; P10 floor finish;
  and for the purchase quantity a `ProductSpec` carrying `pack_coverage_m2` and `wastage_fraction`,
  **both `Measured`**.
* **Deductions.** None. No deduction for the footprint of sanitary ware, a built-in unit or a
  chimney breast.
* **Convention — a CHOICE.** `FLOORING_DEDUCTS_FIXTURE_FOOTPRINT = False`. SMM7/NRM2 practice makes
  no deduction for a void of ≤ 0.50 m², and no #263 field states such a footprint. The alternative
  convention deducts them. **Bound:** a shower tray or a chimney breast is 0.6–1.0 m², so a
  bathroom's flooring area can be overstated by up to ~1 m² under this choice.
* **Convention — a CHOICE.** `FLOORING_INCLUDES_DOOR_REVEAL = False`: flooring is measured to the
  room face of the wall and is not carried under the door leaf. **Bound:** ~0.9 m × 0.1 m = 0.09 m²
  per doorway, so a 4-door dwelling is understated by ~0.36 m².
* **Convention — not a choice.** `FLOORING_PURCHASE_ROUNDS_UP = True`. A pack is indivisible.
* **Assumption.** The floor is a single horizontal plane coincident with the room's plan outline.
  A split level or a stepped floor is not detectable from any schema field.
* **Assumption.** The wastage allowance is **an input, not a guess** — explicitly required by this
  Issue. Absent ⇒ `WASTAGE_ALLOWANCE_NOT_STATED`, pack count **abstains**. The area is still
  computed; the two are separate results so one missing product field never costs the geometry.
* **Abstains when.** No polygon and no stated area (`FLOOR_AREA_NOT_STATED`); the floor finish is
  not stated and the project distinguishes finishes (`FINISH_NOT_STATED`); the finish category has
  no pack convention (`UNSUPPORTED_FINISH_CATEGORY`, recorded as an *unsupported category*, which
  is one of the metrics the directive asks for); pack coverage or wastage absent (purchase only).

### F2 — Wall paintable area

```
gross_wall_area   = room_perimeter × wall_height                       [m²]
paintable         = gross_wall_area − Σ stated areas of this room's openings
```

* **Inputs.** P5 perimeter (stated, or shoelace perimeter of the polygon); **P8 wall height, stated
  by the source, carrying provenance**; **P9 opening areas, stated by the source**; P11 convention.
* **Deductions.** Every opening with a stated area that belongs to this room.
* **The one prohibition that is absolute.** The height is **never** inferred: not from a volume
  (#263 measured `Volume/GrossArea` at 2.045 m for a bathroom and 2.411 m for a kitchen *on the
  same storey* — the tempting inference is both forbidden and wrong), not from a storey count, not
  from a regional norm. Absent ⇒ `WALL_HEIGHT_NOT_STATED` and F2 **abstains**. This is the only
  one of the four materials that needs a third dimension, so on a project with no stated height the
  other three still run and F2 alone abstains — #263 §2's rule, implemented rather than described.
* **Convention — a CHOICE, and the largest one.** `WALL_PAINT_DEDUCTS_SKIRTING_BAND = False`: the
  wall is measured floor to ceiling. **Bound: 0.10 m of a 2.50 m height is 4.0% of the wall area —
  larger than this material's own 3.0% tolerance.** That is why it cannot be absorbed into the
  tolerance budget and why a project whose P11 convention is `UNSTATED` is refused the accuracy
  claim for this material instead of compared loosely.
* **Convention — a CHOICE.** `WALL_PAINT_DEDUCTS_EVERY_STATED_OPENING = True`. SMM7 makes no
  deduction for a void ≤ 0.50 m²; this harness deducts all of them, because P9 *requires* opening
  areas to be stated and discarding a stated measurement to follow a rounding rule would make the
  answer depend on the rule rather than on the measurement. The two conventions do not differ on a
  door; they differ on small high-level windows and vents.
* **Convention — not a choice.** `WALL_PAINT_REQUIRES_COMPLETE_OPENING_SCHEDULE = True`. A room
  with **no openings listed** and a room whose **openings were not listed** are different facts.
  Unless the project declares its opening schedule complete, F2 abstains
  (`OPENING_SCHEDULE_NOT_COMPLETE`) rather than deduct zero. Conflating the two is how a missing
  deduction becomes a silent ~10% overstatement.
* **Assumption.** The walls are vertical, plane, and of one height around the room; the perimeter
  measured in plan is the perimeter at every height. A rake, a vault or a dropped head over a
  recess breaks it and no schema field detects any of them.
* **Assumption.** The paintable surface is the whole wall minus the openings — no deduction for a
  fitted wardrobe or a tiled splashback, because no #263 field states either. In a bathroom this
  is the dominant unquantified term and step 3 must say so wherever a wet room is compared.
* **Abstains when.** Height absent; any opening of the room lacks a stated area
  (`OPENING_AREA_NOT_STATED` — a partial deduction is not a defensible quantity); the schedule is
  not declared complete; the perimeter is unavailable.

### F3 — Ceiling paintable area

```
ceiling_paintable = net_floor_area − Σ stated areas of this room's CEILING openings   [m²]
```

* **Inputs.** P4 stated area **or** P1 polygon; P11 convention; any stated ceiling opening.
* **Deductions.** Every stated ceiling opening — a skylight well, a stair void.
  (`CEILING_DEDUCTS_EVERY_STATED_OPENING = True`, same reasoning as F2.)
* **Assumption — the one that matters, and it is not checkable.**
  `CEILING_IS_FLAT_AND_COINCIDENT_WITH_FLOOR = True`: the ceiling is flat, horizontal, coincident
  in plan with the floor, and carries no dropped bulkhead or soffit. **No plan-view field detects a
  slope or a bulkhead**, and #263's contract has no field for a ceiling form, so this cannot be
  turned into an input without inventing a field #263 never required. It is therefore recorded on
  **every** F3 result and step 3 must print it beside every F3 figure. **Bound:** a 30° monopitch
  understates the developed area by 15.5%; a 0.4 m bulkhead around a 14 m perimeter adds 5.6 m² of
  vertical face this formula does not count. Both exceed F3's 2.0% tolerance by an order of
  magnitude, so on a dwelling with a vaulted room F3 is wrong and nothing in the data says so.
* **Assumption.** Ceiling paint covers the whole soffit; no deduction for a light fitting or a
  grille.
* **Abstains when.** No polygon and no stated area; the ceiling finish is not stated and the
  project distinguishes finishes.

### F4 — Baseboard / skirting length

```
baseboard_length = room_perimeter − Σ stated widths of this room's door openings   [m]
```

* **Inputs.** P5 perimeter; **P6 door widths, stated**; the room's own access edges.
* **Deductions.** The **full stated structural opening width** at every door opening of the room.
* **Convention — a CHOICE.** `BASEBOARD_BREAKS_AT_DOOR_OPENINGS = True` with the full opening
  width. The alternatives deduct only the leaf width, or deduct nothing and let the architrave
  absorb the run. **Bound:** an architrave is 60–80 mm each side, ≈ 0.15 m per doorway, ≈ 1.1% of a
  14 m perimeter per door.
* **Convention — a CHOICE.** `BASEBOARD_RETURNS_INTO_REVEAL = False`. Paired with the line above;
  the two together are the one convention a reference takeoff must match.
* **Convention — a CHOICE forced by the schema.**
  `BASEBOARD_DEDUCTS_BUILT_IN_FURNITURE = False`. No #263 field states a fitted wardrobe or a
  kitchen unit run, so there is nothing to deduct. **Bound: a 3 m wardrobe run is 21% of a 14 m
  perimeter — the largest single unquantified term in any of the four formulas.** Step 3 must state
  it wherever a bedroom or a kitchen is compared, and it is deliberately **not** in F4's tolerance
  budget: an unbounded term may not be absorbed into a tolerance.
* **Convention.** `BASEBOARD_TREATS_CASED_OPENINGS_AS_BREAKS = True`. A cased opening or an
  archway with no leaf is a break when the source states its width. An access edge with **no**
  stated width makes F4 **abstain** — it is never silently treated as a solid wall, because that
  error is invisible and one-directional.
* **Assumption.** The skirting runs around the full room perimeter at floor level and the plan
  perimeter is its run; a bay, a niche or a curved wall measured as a chord is understated.
* **Abstains when.** The perimeter is unavailable; any access edge of the room lacks a stated width
  (`DOOR_WIDTH_NOT_STATED`).

---

## 4. Abstention as a first-class outcome (AC-3)

A quantity that cannot be computed from the inputs present **abstains with a reason**. It never
estimates and it never raises.

* Every formula returns a `Quantity` whose `outcome` is one of **`COMPUTED`**, **`ABSTAINED`** or
  **`FAILED`**. `ABSTAINED` carries an `AbstentionReason` from a closed enum of 11 codes, each
  naming the **one input** whose absence caused it, plus the scope and the field name.
* **An abstention is not an exception.** No formula raises on missing input. `FAILED` exists only
  for an *unexpected* exception, which the harness catches and records so the **failure rate** and
  the **abstention rate** stay separately countable — the directive asks for both, and an
  instrument that crashes and an instrument that declines are different instruments.
* **The abstention rate is an acceptance threshold**, not a footnote:
  `MAX_ABSTENTION_RATE = 0.25`. A material fails on a project if it abstains on more than a
  quarter of its scopes, however accurate the rest is.
* **Manual correction effort** is defined as a **count of abstentions by missing field** — one unit
  is one provenance-carrying input a human would have to supply to turn one abstention into a
  computation. It is a count of enum codes, not an opinion about effort.

---

## 5. The harness (AC-4)

`harness.py`. It takes a reference project in the schema, computes what it can, abstains where it
cannot, refuses what it must not score against, and emits per material:

| Metric | Definition |
|---|---|
| **Absolute error** | `computed − reference`, per scope; and the mean and max of \|error\| over scopes |
| **Percentage error where meaningful** | `100 × (computed − reference) / reference`, **omitted** (`None`) where \|reference\| < `MIN_MEANINGFUL_DENOMINATOR` — 1.0 m² / 1.0 m, below which the denominator dominates |
| **Missing measurements** | one row per (project, scope, field) that an abstention named |
| **Unsupported categories** | finish/material categories reached for which no formula or pack convention exists |
| **Manual correction effort** | abstentions grouped by missing field; one unit = one input field for one scope |
| **Provenance completeness** | two fractions: P-fields present for the material / P-fields it requires, and V-fields complete / 6 over the project's reference values |
| **Failure rate** | `FAILED` scopes / scopes attempted — threshold 0.0 |
| **Abstention rate** | `ABSTAINED` scopes / scopes attempted — threshold 0.25 |
| **Within-tolerance rate** | accuracy-bearing comparisons within the frozen tolerance / accuracy-bearing comparisons |

### 5.1 Comparison A — from verified input measurements

Scores only comparisons that clear **all three** gates: V5 ∈ {`VERIFIED`, `STATED`}; P11 convention
stated; and not refused by §7. Anything that clears fewer is still **computed and reported**, under
`cross_check_only`, and is **never** aggregated into A's accuracy figures.

### 5.2 Comparison B — from automatically extracted measurements

**NOT APPLICABLE.** A separate output object with no numerator, no denominator and no metric
dictionary. Its reason is a frozen string, so it cannot drift:

> **NOT APPLICABLE**: comparison B scores quantities computed from automatically extracted
> measurements, and #257 (PR #258) established that no plan or document ingestion capability
> exists — no PDF, raster, OCR, DXF, DWG, IFC or SVG-parsing dependency on any of 71 branch tips or
> anywhere in history, and `python-multipart` is absent from the lockfile, so the service cannot
> physically accept an uploaded file. There is nothing to extract with, so B has no numerator and
> no denominator. It is reported separately and is never folded into A.

A test asserts B carries **no numeric metric of any kind** and that A and B are distinct objects in
the emitted JSON. Folding B into A is the failure ROOT #262 names by name, so it is made
structurally impossible rather than merely avoided.

### 5.3 What the harness refuses to report at all

Per #263 §1.4, with **zero** `VERIFIED` or independently `STATED` reference quantities acquired,
the harness's own summary reports `NOT_EVALUABLE` and **no system accuracy figure**. `frozen.verdict`
returns that before looking at anything else. Two of the directive's five evaluation layers —
**source measurement accuracy** (layer 1) and **comparison B** — are unmeasurable today, and that
is itself a finding for the pivot.

---

## 6. The frozen acceptance thresholds (AC-6)

`frozen.py` §5. **Committed in a commit that precedes every results commit on this branch** — that
order is the whole point of this section and it is the difference between an experiment and a
demonstration. Nothing below was chosen after a number was seen, and a tolerance may not be widened
to make a figure pass: a refusal and an abstention are results.

A comparison is **within tolerance** when
`|computed − reference| ≤ max(TOLERANCE_ABS, TOLERANCE_REL × |reference|)`.

| Material | Tolerance | Absolute floor | The budget, term by term |
|---|---|---|---|
| **Flooring area** | **±2.0%** | 0.10 m² | the drawing/scale term (~1%: a dimensioned drawing at a stated scale, and #263 P3 requires a **measured** scale) **doubled** for headroom |
| **Ceiling paintable area** | **±2.0%** | 0.10 m² | the same plan polygon as flooring, so the same budget |
| **Baseboard length** | **±2.5%** | 0.10 m | 2.0% plan term **+** ~0.5–1.1% for the door-opening convention (an architrave is ≈0.15 m per doorway, ≈1.1% of a 14 m perimeter) |
| **Wall paintable area** | **±3.0%** | 0.10 m² | 2.0% perimeter term **+** 1.0% for the stated height (25 mm on 2.50 m, a realistic as-built variation across one room). The opening deduction is a stated measurement under P9 and carries no budget of its own. |
| **Flooring purchase quantity** | **exact** (0%) | 0 packs | deterministic integer arithmetic once area, pack coverage and wastage are inputs; any mismatch is a rule error, not measurement noise |

**Two terms are deliberately excluded from every budget**, because absorbing them would let the
tolerance hide them:

* **The measurement convention (P11).** Internal-clear versus centre-line on a 3×4 m room with
  0.10 m partitions differs by ~12% — **four times** the largest tolerance above. It is handled by
  **refusing the accuracy claim** when P11 is `UNSTATED` (§7 R1 `CONVENTION_UNSTATED`), never by
  widening a tolerance.
* **The skirting-band convention in F2 (4.0%) and built-in furniture in F4 (up to 21%).** The first
  is larger than F2's own tolerance; the second is unbounded by any schema field. Both are reported
  beside the figure and neither is absorbed.

**The rates are thresholds too**, so accuracy cannot be bought with silence:

| Threshold | Value | Why |
|---|---|---|
| `MIN_WITHIN_TOLERANCE_RATE` | **0.90** | one room in ten may be out — where a single mis-scheduled opening or an unrecorded wardrobe lands; a lower bar would let a *systematic* convention error pass as scatter |
| `MAX_ABSTENTION_RATE` | **0.25** | an instrument that abstains on half a building is not usable even when everything it computes is right |
| `MAX_FAILURE_RATE` | **0.0** | a formula that crashes is not an instrument |
| `MIN_MEANINGFUL_DENOMINATOR` | **1.0 m² / 1.0 m** | below this the percentage error is denominator noise and the absolute error is reported alone |

**The evidence bar, restated from #263 §1.4** so step 3 cannot lower it after seeing results:
≥ **3** projects carrying P8/P9 for the wall-paint claim, ≥ **5** projects for the other three,
≥ **2** distinct publishers, and every reference value graded `VERIFIED` or `STATED`.

`frozen.verdict()` maps these onto **GO / CONDITIONAL GO / NO-GO / NOT EVALUABLE**. Step 3 may
**run** it; it may not replace it. On today's data it returns `NOT_EVALUABLE` before examining
anything, because #263 acquired zero accuracy-bearing reference quantities.

### 6.1 Unit tests on synthetic geometry are correctness, never accuracy

Said here because it is the easiest honest claim to overstate. The harness's unit tests build
rectangles and L-shapes with known areas and check that F1–F4 return the documented number with the
documented deductions. That is **correctness**: the formula computes what it says it computes. It is
**not** accuracy, it says **nothing** about any real building, and no synthetic figure appears in
comparison A — ROOT #262 AC-2 forbids it and `frozen.SYNTHETIC_TESTS_ARE_CORRECTNESS_ONLY` states
it in the module the report cites.

---

## 7. The self-validation guard (AC-5)

Two independent refusals. Either one alone is enough; the second exists because the first trusts a
declaration and declarations are wrong.

**R1 — the declared-provenance refusal.** A reference value is refused when its provenance makes it
a product of the same class of calculation under test. Four codes:
`SAME_CALCULATION_CLASS` (#263 §1.3 condition 2 — `CALCULATION_CLASS` maps each material to a
`CalculationClass` and `REFERENCE_VALUE_CLASS_CONFLICT` says which reference classes collide with
it, so "polygon area in, polygon area out" is a comparison the harness makes, not a judgement a
reader makes); `DERIVED_FROM_SUPPLIED_GEOMETRY`; `NOT_INDEPENDENT` (#263 V6);
`NOT_ACCURACY_BEARING` (V5 `DERIVED`/`UNVERIFIED`); and `CONVENTION_UNSTATED` (P11).

**R2 — the geometric-identity refusal.** Independent of every declaration: the harness recomputes
the quantity from the **supplied geometry** and compares it to the offered reference. If the
residual falls inside the identity band the reference carries **no information the geometry does
not**, and it is refused as `GEOMETRIC_IDENTITY`. A residual of exactly zero is refused
unconditionally.

> Band: `|residual| ≤ max(0.01, 0.0005 × |reference|)`, in m² or m.
> **Above the identity it must catch:** 0.05% of a 42 m² room is 0.021 m², **34×** #263's observed
> 0.00061299 m² worst case; the 0.01 m² floor is **16×** it for a small room.
> **Below any real discrepancy:** public per-room areas are published to 0.01–0.1 m², so two
> independent measurers agree to the published rounding at best, and a survey-versus-drawing
> comparison on one convention differs by of the order of 1% — **20×** the relative term.

**The demonstration the Issue asks for** is §9.1: feed the harness the 19 real plans with their own
`area_m2` offered as the flooring reference and it must decline rather than report a near-perfect
score.

---

## 8. The 1923 Fletcher takeoff — a real reference quantity, and the two claims it must never mix

> **Banister Fletcher & H. P. Fletcher, *Quantities*, 9th ed., B. T. Batsford, 1923, Chapter XXII,
> "Proposed Entrance Lodge."**
> `archive.org/details/banisterfletcherh.p.fletcher1923` — **CC Public Domain Mark 1.0**, read from
> the item's own metadata API (`licenseurl`) on 2026-10-27, and public domain by age in the US and
> the UK. It is a **professional quantity takeoff**: a plasterer's dimension paper room by room,
> the opening deductions written out, the skirting as its own item in running measure, ceiling
> plaster and whitening, a separate Taking Off for Painter, and ten plates including a figured
> ground plan (Plate 8) and two sections.

**It was identified after §6's thresholds were frozen, and no threshold was revised in its light.**
That is the right order and it is the order the git history shows: `frozen.py` is commit 1 on this
branch and the Fletcher fixture is commit 2.

### 8.1 The two claims, kept as far apart as A is from B

| | Fletcher validates | Fletcher says nothing about |
|---|---|---|
| **Which of the owner's five axes** | **2 geometric calculation, 3 material quantity, 4 completeness of required inputs, 5 provenance and auditability** | **1 source measurement accuracy** |
| **Why** | the conventions and the deductions are **written out on the page**, which no other source does | **nobody measured this lodge. It was never built.** It is a designed exercise taken off by a professional |
| **What would change it** | nothing; this is what it is for | a real project, measured on site, with its כתב כמויות — see §10 |

**No source found anywhere measures a verified *built* house.** Every one of the public-domain
quantity-surveying works is a designed exercise. So axis 1 joins comparison B on the list of things
this gate **cannot** measure, and the report must say so in the same breath as any Fletcher figure —
exactly as it must never fold B into A.

### 8.2 Why the OCR was not used

The `_djvu.txt` of this work is **unusable for the dimension-paper columns**: the three-column
waste / dimension / squaring layout does not survive text extraction. Every figure in
`data/fletcher-1923-entrance-lodge.json` was read **from the page image**, with the leaf and the
printed page recorded per item. The prose chapters OCR correctly, and §8.4's convention quotations
come from there.

### 8.3 How the transcription was checked

A reading that did not reproduce the book's own printed arithmetic was not recorded. Eight checks
pass, and `test_the_fletcher_transcription_reproduces_the_books_own_printed_totals` re-runs them:

| Check | Result |
|---|---|
| Scullery girth: 4'3"+4'0"+2'6"+2'0"+7'0"+1'0" | **20'9"**, as printed (p.324) |
| Scullery render: 20'9" × 5'0" | **103.75 sq ft**, printed `103·9` |
| Room-324B girth: 5'0"+4'3"+6'6"+2'3"+6'6"+11'0" | **35'6"**, as printed |
| Room-324B walls: 35'6" × 8'0" | **284.0 sq ft**, printed `284·0` |
| Room-324B deductions: 3/(2'10"×6'4") + 4'6"×2'6" + 4'6"×2'6" + 2/½(1'6"×1'6") | **78.583 sq ft**, printed `78·7` |
| Sitting Room girth: thirteen lengths collected on waste | **56'3"**, as printed |
| Sitting Room walls: 56'3" × 8'0" | **450.0 sq ft**, printed `450·0` |
| Sitting Room deductions: five lines | **102.611 sq ft**, printed `102·7` |

Three rooms were transcribed: **Scullery**, **Sitting Room**, and one room the transcribed pages do
not name. The takeoff order and Plate 8 make it the Kitchen; **that is not a transcription**, so it
is carried under the neutral id `ROOM_324B` and no claim is made about which room it is. The
Scullery's 20'9" is the **rendered length, not the room perimeter** — a room of 8'6" × 7'0" has a
perimeter of 31'0" — so it is **not** offered as a P5 perimeter, and F2 and F4 abstain for that room
rather than use a number that means something else. That refusal is the schema working.

### 8.4 Every contested convention is now contested *on the page*, not in the abstract

This is what §3's choices were waiting for. Each is quoted from the source's own
method-of-measurement chapters, with the page.

| Formula | Our frozen choice | Fletcher's stated rule | Agrees? |
|---|---|---|---|
| **F3 ceiling** | net plan area; no cornice or chimney-breast deduction | *"Measure the ceilings the full dimensions between the walls; but where cornices occur, it is customary to make a deduction of the width of the cornice upon each dimension... Make the deductions for chimney breasts"* (p.128) | **No.** His own worked example books a 20'0"×16'0" room with a 12" cornice as 19'0"×15'0" = 285 sq ft instead of 320 — a **10.94%** divergence, five times F3's tolerance |
| **F2 skirting band** | `WALL_PAINT_DEDUCTS_SKIRTING_BAND = False`, floor to ceiling | *"Rendering to walls is measured the length by the height, **the latter being taken from the top of the skirting grounds to the ceiling**"* (p.130) | **No — a direct, cited contradiction** of the one term §6 placed outside the tolerance budget because it is worth ~4.0%. The frozen value stands; the divergence is recorded |
| **F2 opening deduction** | deduct every opening at its stated area | *"take the full dimensions for length and height **to the outside of the grounds, and not the net dimensions**"* (p.130–131) | **Partly.** He agrees every opening is deducted and specifies *which* dimensions. Our P9 does not say whether a stated area is the structural or the clear opening — a gap step 3 must close per project |
| **F4 baseboard** | breaks at every door opening, full stated width deducted | The **joiner's** rule deducts: *"making the deductions for doors, chimney-pieces, &c."* (p.84). The **plasterer's** cement-skirting rule does not: on p.325 `ROOM_324B`'s 6" cement skirting is booked at **35'6", the full collected girth**, with the breaks numbered separately as 8 stopped ends, 2 mitres and 4 irregular | **The two trades in the same book disagree.** Measured on this room, our convention gives 27'0" against his 35'6" — a **−23.94%** divergence, ten times F4's tolerance |
| **F1 wastage** | an input with provenance, never a guess | *"make an allowance for all irregular cuttings, taking the length by a width of 3 in. for the cutting and waste"* (p.84) | **Yes** — a cited precedent that a cutting-and-waste allowance is a *stated rule with a dimension*, not an assumed percentage |

A sixth convention is relayed but **not read here**: Nichols 1908 deducts **half** the opening area
(13,141 sq ft gross − (32×40 + 34×15)/2 = **12,246** net — the arithmetic checks exactly, and a test
asserts it). That is a *third* convention, different from both ours and Fletcher's. Leaning 1897 and
Brooks 1870 are named as step-3 candidates and were **not fetched or read** in this work; Fletcher's
own two trades are the independent corroboration that F4's convention is genuinely contested.

**A convention divergence is not an error.** It is the difference between two defensible ways of
booking the same work, and conflating it with an error is how an instrument gets blamed for a
disagreement about a rule. `fletcher.convention_audit()` reports them as their own output, labelled,
and never inside comparison A.

---

## 9. Results

Produced by `PYTHONPATH=backend python -m app.ai_harness.quantity_takeoff.run`, written to
`data/QUANTITY-harness-results.json`. **No accuracy figure appears below, because none can honestly
be produced.** `frozen.verdict()` returns **`NOT_EVALUABLE`** before examining anything.

### 9.1 AC-5, on the repository's own 19 plans

Both arms: 19 plans, 179 rooms, **358 reference values offered** (each room's `area_m2` for both
area materials), **358 refused, 0 scored, 0 even admitted as a cross-check.**

| Arm | What the reference claimed | R1, the declarations | R2, the residual |
|---|---|---|---|
| **as_graded** — the plans described honestly | `DERIVED`, `PUBLISHER_COMPUTED`, no stated convention | refuses 358× `SAME_CALCULATION_CLASS`, 358× `NOT_ACCURACY_BEARING`, 358× `CONVENTION_UNSTATED` | refuses 358× `GEOMETRIC_IDENTITY` |
| **optimistic** — the same number in the strongest form an advocate could claim: `STATED`, `DESIGN_DRAWING_DIMENSION`, a full V6 statement, a declared `INTERNAL_CLEAR` convention and a stated scale | nothing wrong with it | **raises nothing at all** | **refuses all 358 on the residual alone** |

**The optimistic arm is the demonstration.** A guard that only reads declarations is a guard that
trusts them. R2 ignores every declaration, recomputes the area from the supplied polygon, and finds
the reference inside the identity band — so it declines rather than report a near-perfect score.

Re-measured here, not quoted: across all **179** rooms the residual between the stated `area_m2` and
the shoelace area of the room's own polygon never exceeds **0.00061299 m²** (worst case plan `13578`,
`CIRCULATION_0`: stated 48.8074, shoelace 48.808013). **179 of 179 inside the band, 0 outside**, with
**39.8× headroom** at the worst room. The band was frozen before this was run.

### 9.2 What the harness computed and abstained on, on real data

Identical in both arms, because the inputs are the same; 895 scopes per arm, **0 failures**.

| Material | Computed | Abstained | Rate | Why it abstained |
|---|---|---|---|---|
| Flooring area | 179 | 0 | 0.00 | — |
| Ceiling paint area | 179 | 0 | 0.00 | — |
| Baseboard length | 30 | **149** | 0.83 | `DOOR_WIDTH_NOT_STATED` ×149. ResPlan lists the doors but states no width, and a width read off the door polygon would be a figure computed from the supplied geometry — the very thing §7 refuses. The 30 that computed are rooms with no door at all |
| Wall paint area | 0 | **179** | 1.00 | `WALL_HEIGHT_NOT_STATED` ×179 — 0 of 20 fixtures carry one, and a quotient is forbidden |
| Flooring purchase | 0 | **179** | 1.00 | `FINISH_NOT_STATED` ×179 — no fixture carries a material or finish field |

**Manual correction effort: 507 fields** across the two area-free materials and the purchase count
(179 heights + 179 finishes + 149 door widths). That is the count the directive asks for, and it is
a count of enum codes, not an opinion.

### 9.3 The 1923 Fletcher takeoff, through the same harness

3 rooms, 14 openings, **6 reference values offered** — the first real reference quantities in this
work. **0 scored as accuracy.** The reasons are the finding:

| Material | Outcome | What happened |
|---|---|---|
| **Ceiling paint area** | **3 refused, residual exactly 0.0** | `GEOMETRIC_IDENTITY` **and** `SAME_CALCULATION_CLASS`. The geometry came from the same dimension columns the quantity was squared from, so recomputing it is **arithmetic, not accuracy** — and the harness says so instead of reporting three perfect scores. **The guard catches a real professional takeoff, not just our own fixtures.** |
| **Wall paint area** | 3 abstained | `OPENING_SCHEDULE_NOT_COMPLETE` ×2 (the deduction lines give an opening's size but not its wall, and the joinery schedule was not transcribed) and `PERIMETER_NOT_AVAILABLE` ×1 (the Scullery's partial girth is not a perimeter) |
| **Baseboard length** | 2 computed, 1 abstained, 1 refused | computed 8.230 m against the takeoff's 10.820 m. Residual 2.59 m — **not** an identity, so R2 passes it; refused on `SAME_CALCULATION_CLASS` alone. The gap is **entirely the skirting convention of §8.4**, and it is reported as a convention divergence, never as an error |
| **Flooring purchase** | 3 abstained | `FINISH_NOT_STATED` — the finishes are in the painter's and joiner's takeoffs, which were not transcribed |
| **Flooring area** | 3 computed | no reference offered for it |

Provenance completeness for wall paint on this project: **18 of 24 P-field slots present (0.75)**,
missing `P9` ×3, `P7` ×2, `P1|P5` ×1; **2 reference values, both graded `STATED`, 0 weaker methods**.
That is the most complete provenance any source in this work has produced.

### 9.4 The one thing §9.3 proves about the instrument

Fletcher is the first artefact that could have produced a number, and the harness **still** produced
none — for a stated, checkable reason, on a reference it had every incentive to accept. The three
ceiling refusals with a residual of exactly `0.0` are the proof that §7 is not decoration.

---

## 10. What step 3 needs

*Written with §9 empty, before any result existed, and unchanged since.*

### 10.1 The single input that makes step 3 a run rather than a project

> **The room polygons of the Entrance Lodge, taken off the figured ground plan (Plate 8, leaf 516),
> independently of the dimension columns.**

That one input converts Fletcher's six refused comparisons into six real ones. The plan is fully
figured (37'0" × 22'0"/31'0" overall, wall thicknesses 14" and 9", rooms figured) and carries a drawn
scale bar, so the geometry has a source that is **not** the takeoff — which is exactly what the
identity refusal in §9.3 is asking for. It is a day of careful reading off a page image, and it
needs nothing bought, nothing licensed and nobody's permission.

With it, step 3 can report, for the first time, a **per-project cross-check of axes 2 to 5** on a
real professional takeoff: does our geometry → quantity chain reproduce what a quantity surveyor
booked, and where it does not, is the gap a calculation error or a convention difference? §8.4
already names which conventions will account for which gaps, so the answer will be attributable
rather than mysterious.

### 10.2 The input that nothing in this work can substitute for

> **Axis 1, source measurement accuracy, needs a real project measured on site.**

No public source anywhere measures a verified **built** house. Fletcher is a designed exercise;
ResPlan is a vectorisation; the two CC BY 4.0 projects #263 acquired are Revit exports. Until one
real building is measured — a professional takeoff, the **כתב כמויות**, with units and the measurer's
name, alongside the plan at a stated scale, per-room areas measured on site with the method and
convention named, the door and window schedule with width **and** height, measured wall heights and
the wall thickness with its convention — **axis 1 cannot be tested at all**, and step 3 must report
it as unmeasurable alongside comparison B. **Two of the directive's five axes unmeasurable is itself
a finding for the pivot.**

### 10.3 What step 3 may not do

1. **Report a system accuracy figure.** #263 §1.4's minimum is not met and §6 restates the bar:
   ≥3 projects with P8/P9, ≥5 without, ≥2 publishers, every value `VERIFIED` or `STATED`.
   `frozen.verdict()` returns `NOT_EVALUABLE` and step 3 may run it, not replace it.
2. **Widen a tolerance.** §6 is frozen and commit 1 proves when. A refusal and an abstention are
   results.
3. **Present a synthetic figure as accuracy.** The unit tests build rectangles and L-shapes with
   known areas. That is correctness. It is not evidence about any building.
4. **Fold comparison B into A**, or fold a convention divergence into an error. Both are separate
   outputs for the same reason.

### 10.4 Cheap inputs that would each buy one material

| Missing input | Buys | Cheapest source |
|---|---|---|
| Door widths per room | baseboard length on 149 of 179 real rooms | the ResPlan door polygons are **not** a source; a figured plan is |
| A stated wall height | wall paint — the only material of the four that needs a third dimension | Fletcher states 8'0" per storey; the two CC BY 4.0 projects #263 acquired state one for 236 of 269 rooms |
| A floor finish per room | the purchase quantity on every room | Fletcher's joiner's and painter's takeoffs, not yet transcribed |
| The joinery schedule | closes `OPENING_SCHEDULE_NOT_COMPLETE` on Fletcher's wall paint | the same book, Chapter XXII, pages not yet read |

---

## 11. Isolation, and what was not done (AC-7)

* **No production file is changed.** The diff is `backend/app/ai_harness/quantity_takeoff/`, one
  test file, and this report with its two data files. A test asserts exactly that, so deleting the
  directory restores the tree.
* **Nothing outside the directory imports it** — asserted by a scan of every `.py` under
  `backend/app`.
* **No generator validator is imported, for any purpose.** #242's R1 measured why: they refused a
  policy condition unrelated to geometry in **18 of 19** real plans, so they encode what the
  generator may build, not what a building is. An AST test lists the forbidden modules and fails on
  an import of any of them.
* **Nothing is rebound or patched** in any imported module — AST-checked, with `monkeypatch` and
  `setattr` banned outright.
* **Layer 6, pricing, is absent rather than stubbed.** An identifier scan fails on `price`, `cost`,
  `rate_per`, `currency` and the rest.
* **No existing test is weakened**; none is touched.
* Nothing is merged, deployed, bought or notified.

### Test counts

```
backend/tests/ai_harness/test_quantity_takeoff.py   56 passed, 1 skipped
```

The skip is `test_git_history_shows_the_thresholds_were_committed_before_any_result` when run on a
tree where the results file is not yet committed — it passes once it is, and a skip there is itself
compatible with the ordering claim.
