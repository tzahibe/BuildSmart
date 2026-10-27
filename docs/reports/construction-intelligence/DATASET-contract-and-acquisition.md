# #263 — Dataset contract and acquisition: real plans with independently verified quantities

ROOT: #262 (owner directive 2026-10-27, the mandatory evidence gate before the Construction
Intelligence pivot). Child 1 of 3; #264 (schema, formulas, harness) and #265 (comparison report,
recommendation) are gated behind this one.

**Verdict: see §6. This document is read-only knowledge work — no production file is changed.**

The governing principle, in the owner's words, is that *a mathematically correct calculation is not
evidence that its input measurements are correct.* Everything below follows from it. A reference
value is only a reference value if it came from **outside** this system. The directive's two
prohibitions are therefore structural, not stylistic:

- **No synthetic fixture may support a real-world accuracy claim.**
- **No ground-truth value may be derived from BuildSmart's own calculation.**

§1 is the contract, written **before** acquisition was attempted so that no source could shape the
bar it had to clear — the commit order on this branch shows it. §2 says what a partially-compliant
project is still worth, because three of the four first materials do not need a third dimension.
§3 is what the repository already holds and why it does not qualify. §4 is the acquisition log,
one row per candidate with its licence and a verdict. §5 names the paid-only routes for the owner
to decide, none of them taken. §6 is the verdict. §7 is what the owner could supply that no public
source can.

---

## 1. The dataset contract

A **reference project** is one plan of one dwelling, with reference quantities attached. It counts
only if it satisfies §1.1 and §1.2. Anything short of that is graded under §2 rather than accepted
or rejected wholesale.

### 1.1 Required per project

| # | Field | Why it is required | Mandatory for |
|---|---|---|---|
| P1 | **The plan itself**, as geometry or as a dimensioned drawing | Without it there is nothing to compute from | all |
| P2 | **Licence**, explicitly stated by the publisher, permitting our use and retention | A dataset that cannot be used legally is not a dataset (§4 rejects on this alone) | all |
| P3 | **Metric scale, measured — not inferred** | An inferred scale makes every derived quantity a function of an assumption; see §3 | all |
| P4 | **Per-room floor area as measured**, with the **measurement method** named | The reference value for flooring, and the independent check on P3 | flooring |
| P5 | **Room perimeters, or enough geometry to derive them** | Baseboard/skirting runs the perimeter | baseboard |
| P6 | **Door widths** | Baseboard breaks at every door opening and wall paint deducts it; a takeoff without door widths is wrong by a bounded but unknown amount | baseboard, wall paint |
| P7 | **Window widths and sill/head dimensions** | Wall paint deducts window openings | wall paint |
| P8 | **Wall height, stated by the source** | AC-4 of ROOT #262 forbids inferring it from plan geometry | wall paint |
| P9 | **Opening areas, stated by the source** | Same prohibition: a door/window *area* is a 3-D fact, and deriving it from a plan-view width plus an assumed height is an inference | wall paint |
| P10 | **Finish type / material per surface**, as an input carrying provenance | "Flooring area" is only meaningful per finish; a room with two floor finishes has two quantities | all, where the source distinguishes them |
| P11 | **Wall thickness and the measurement convention** (internal clear / centre-line / external) | Per-room area differs by several percent between conventions; a comparison that mixes conventions measures the convention, not the engine | all |

P11 is not pedantry and it is the field most often missing. IS 1200, RICS NRM2/SMM7 and the
IPMS/RICS Code of Measuring Practice do not all deduct the same things. If the source does not say
which convention it measured under, its areas cannot be compared to ours at better than the
convention's own spread, and the project is capped at §2's *tolerance-limited* grade.

### 1.2 Required per reference value

Every single number offered as ground truth carries all six, or it is not ground truth:

| # | Field | Admissible values / notes |
|---|---|---|
| V1 | **Source** | The publishing body and a resolvable citation (URL, DOI, drawing number, archive reference). Not "a textbook". |
| V2 | **Measurement method** | One of: as-built physical survey; instrumented/laser survey; professional quantity takeoff from drawings; design-drawing dimension; publisher-computed from their own model. **The last two are weaker and must be labelled as such** — a design dimension is an intent, not a measurement. |
| V3 | **Units**, explicit | m, m², mm. No bare numbers. Unit errors are the single most likely silent failure in a takeoff comparison. |
| V4 | **Revision** | The drawing or dataset revision/date the value belongs to. A quantity from rev A compared to geometry from rev C is noise. |
| V5 | **Reliability** | `VERIFIED` (independent physical measurement or a professional takeoff signed by a third party) / `STATED` (publisher asserts it, method documented, not independently checked) / `DERIVED` (publisher computed it from their own geometry) / `UNVERIFIED`. **Only `VERIFIED` and `STATED` may carry an accuracy claim.** `DERIVED` is usable as a cross-check only, and must be reported as such. |
| V6 | **Independence** | An explicit statement that the value does **not** originate in BuildSmart, in any BuildSmart-derived artifact, or in a calculation of the same kind as the one under test. This field exists to make ROOT #262's AC-2 checkable rather than merely asserted. |

### 1.3 Disqualifying conditions

A candidate is rejected outright, with no §2 fallback, if any of these hold:

1. The licence does not permit the use, or the licence is **unstated** and the publisher cannot be
   taken to have granted anything (P2).
2. The reference quantity was computed by **the same class of calculation** that is under test —
   i.e. polygon area in, polygon area out. This is the trap §3 falls into and it is the easiest
   mistake to make while believing one has ground truth.
3. The geometry is **synthetic, generated or reconstructed by a model**, and is being offered as a
   real-world reference.
4. The scale is **inferred from the reference value itself**. That makes the comparison circular:
   the "ground truth" is recoverable from the geometry by construction, so agreement proves only
   that the arithmetic inverted correctly.
5. Acquisition requires **payment** — out of scope without the owner's explicit approval (AC-6);
   such sources are named with cost and licence in §4 and left for the owner.

### 1.4 Minimum viable set

The experiment needs a **small** set, not a large one — ROOT #262 says so and the statistics agree:
with per-project percentage error as the measure, a handful of projects measured well beats a
corpus measured badly. The bar:

- **≥ 3 projects** satisfying §1.1 fully (including P8/P9), for the wall-paint claim.
- **≥ 5 projects** satisfying §1.1 without P8/P9, for the other three materials (§2).
- **≥ 2 distinct publishers**, so that one publisher's measurement convention is not mistaken for
  reality.
- Every value graded `VERIFIED` or `STATED` under V5.

Below that, #265 may report *per-project* errors but must not report an accuracy figure for the
system.

---

## 2. What a partially-compliant project is still worth

This section is deliberately in the experiment's favour, and it rests on a structural fact ROOT
#262 states: **of the four first materials, three need only plan-view geometry plus door widths.**

| Material | Needs | Needs a height? |
|---|---|---|
| Flooring area | per-room polygon or stated area (P3, P4) | **No** |
| Ceiling paintable area | per-room polygon or stated area (P3, P4) | **No** |
| Baseboard / skirting length | per-room perimeter (P5) **and door widths (P6)** | **No** |
| Wall paintable area | perimeter, **wall height (P8)** and **opening areas (P9)** | **Yes** |

Therefore:

- **A project with no stated wall height is a fully usable reference for three of the four
  materials.** It is not rejected; it is admitted with `wall_paint: OUT OF SCOPE for this project`.
  Rejecting it wholesale would discard three quarters of its value for the sake of a field that one
  material needs.
- **A project with no stated door widths** is usable for flooring and ceiling area only. Baseboard
  length computed without door deductions is not a defensible quantity, and must be reported as
  abstained rather than estimated. Door widths are the cheapest field to obtain and their absence
  is the most damaging per unit of effort.
- **A project with stated per-room areas but no polygon** is a reference for flooring and ceiling
  only, and cannot test the geometry layer at all — it tests the material layer on top of the
  source's own geometry. Useful, and must be labelled as a narrower test.
- **A project with a polygon but no stated area** tests nothing by itself. It is a *geometry input*
  awaiting an independent reference; see §3.
- **A project whose wall-thickness convention (P11) is unstated** is *tolerance-limited*: usable,
  but its per-project error must be reported against the convention spread rather than as a point
  figure.

The one thing §2 may never do is promote a missing field into an assumed one. A plan without a
stated height does not acquire a 2.5 m height because 2.5 m is typical. Under ROOT #262's AC-4 the
height is an **input with provenance**, and "typical" is not a provenance.

---

## 3. What the repository already holds, and why it does not qualify

The repository holds **20 plan fixtures** at
`backend/tests/spikes/fixtures/geometry_shapes/plans/` — 19 derived from **ResPlan** (Abouagour &
Garyfallidis 2025, arXiv:2508.14006) under **CC BY 4.0**, and 1 hand-built synthetic
(`synthetic-spine-01.json`, whose own provenance says `SYNTHETIC`). Attribution and the licence
grant are recorded in `ATTRIBUTION.md` beside them.

Measured at `c07bf71`, not cited:

| Fact | Measurement |
|---|---|
| Real plans | 19 (`provenance.source_dataset == "ResPlan"`), plus 1 synthetic |
| Rooms | 183 total, **179** in the 19 real plans (the synthetic fixture has 4) |
| Per-room fields present | `area_m2`, `polygon`, `width_m`, `depth_m`, `type`, `exposure` — union across all 20 files |
| Door polygons | present in 18/19 real plans (`1263.json` has 0 doors) |
| Window polygons | present in 18/19 real plans (`31.json` has 0 windows) |
| Wall thickness | one **per-plan scalar** in `derived`, 0.205–0.322 m; not per wall, and no convention stated |
| Files containing any of `height`, `material`, `finish`, `ceiling`, `paint`, `storey`, `floor_to` | **0 of 20** |
| Metric scale | `derived.scale_m_per_px`, a **derived** field — i.e. computed, not supplied by the source |

And the finding that settles it. For all **179** real rooms, the stated `area_m2` equals the
shoelace area of the room's own `polygon` to within **0.00061 m²** — i.e. to the last published
decimal. The only two deviations anywhere in the file set, 2.0 m² and 4.0 m², are both in the
synthetic fixture, whose stated areas are internally inconsistent with its own polygons.

That is not a reassurance, it is the disqualification. **`area_m2` carries no information that the
polygon does not already carry.** Offering it as ground truth for a computed floor area would be
comparing a polygon area to the same polygon's area — exactly §1.3(2), and exactly what ROOT
#262's AC-2 and the owner's "do not manufacture ground truth from BuildSmart's own calculations"
forbid. The agreement would be an identity, reported as an accuracy.

The scale compounds it, and the upstream dataset's own paper settles that rather than leaving it to
inference. ResPlan (arXiv:2508.14006) publishes, per plan, **one** metric metadata attribute — "an
area value indicating the total internal floor area in square meters (gross floor area, GFA)" —
and the paper documents **no methodology for establishing or validating the pixel-to-metre scale**.
It states plainly that the dataset "does not include explicit 3D features such as ceiling heights
(beyond assuming a default height)", and it carries no per-room areas, no door or window
dimensions and no materials.

So the only metric anchor ResPlan offers for a plan is its stated GFA. #257 established that our
`scale_m_per_px` was inferred from exactly that figure, and the paper confirms there was nothing
else available to infer it from. That is §1.3(4) — the scale is derived from the only reference
value the source states, which makes any comparison against that value circular by construction.
The normaliser itself is **not present in this repository** (the `ResPlan → PlanReference` code
from #94/#95 lives on `integration/poc-architectural-brain`), so the exact arithmetic is
**unverified at this head**; the conclusion does not depend on it, because the source has only the
one number to offer.

**Contract grade: the 19 ResPlan plans fail P3, P4, P8, P9, P10 and P11.** They satisfy P1, P2
(CC BY 4.0, cleanly), P5 and — uniquely among everything assessed in §4 — **P6 and P7 in derivable
form**, since door and window polygons are present in 18/19.

So, precisely:

- **They can serve as a geometry input** — the plan side of a comparison whose reference values
  would have to come from somewhere else entirely. Their door and window polygons are real and
  make them better geometry input than most of §4's candidates.
- **They cannot serve as ground truth for any quantity**, cannot support any statement about
  measurement accuracy, and cannot be used for wall paint at all (no height exists in the files,
  and inferring one is forbidden).
- **`synthetic-spine-01.json` may not appear in this experiment in any role.** It is a
  known-positive control for a separability test, and ROOT #262's AC-2 bars it from supporting a
  real-world claim. Its own internal area inconsistency is a second, independent reason.

The repository therefore holds **plans without ground truth** — which is the one substitution this
Issue may not make.

---

## 5. Paid-only options, named for the owner to decide

AC-6: **nothing was purchased, and no payment was attempted.** The directive puts paid acquisition
behind the owner's explicit approval, so the viable paid routes are named here with cost and
licence and left alone. Costs are indicative market figures with their source named, not quotations
— none was requested, because requesting one is the start of a purchase.

| Route | Cost (indicative) | What it would supply against the contract | Licence | Source of the figure |
|---|---|---|---|---|
| **A. Outsourced professional quantity takeoff**, ordered per plan | **USD ~150–400** per single-family residential takeoff; ~USD 250 typical single-trade start; alternative model USD 0.02–0.10 per sq ft | P4, P5, P6 and the reference quantities themselves, at reliability **`VERIFIED`** under V5 — a human quantity surveyor's measurement, independent of BuildSmart | Work-for-hire; the commissioning party holds the deliverable, so redistribution inside the repo is ours to grant | 2026 estimating-market pricing guides (commercial publishers) |
| **B. RICS/IPMS measured building survey**, commissioned on a real dwelling | **GBP 1,500–15,000** per building, scaling with floor area and detail | **The entire contract, including P8/P9/P11** — the standard deliverable is scaled plans with wall thicknesses, doors, windows and room dimensions *plus cross-sections giving floor-to-ceiling heights*, measured under a named convention | Survey contract; client-owned deliverable | A chartered surveyor's own published cost guide — a commercial source, not a tariff |
| **C. Phone-scan floor-plan service** (CubiCasa, Matterport and equivalents) | **USD 22.99–29.99 per scan** (CubiCasa base/plus); USD 15–50 per property standalone; ANSI-compliant GLA certification as a paid add-on | P3, P4, P5 and — for the 3-D products — a measurable wall height. Convention is **named** (ANSI Z765), which satisfies P11 | Service terms; **requires physical access to the dwelling** | Vendor pricing pages and review aggregators, 2026 |
| **D. Unit-rate databases** — RSMeans, Dekel (מחירון דקל), and insurance-valuation datasets such as Verisk 360Value or CoreLogic | Subscription, various | **Nothing.** They supply unit *rates*, not a project's measured *quantities* | Proprietary, no redistribution | Named only so the list is complete |

Three things follow from the table and are worth stating rather than leaving implicit.

**Route A is cheap enough to be a real decision rather than a project.** Five plans at roughly
USD 250 is on the order of USD 1,250 — within the range of things that get approved without a
business case. And it can be ordered against plans **we already hold under CC BY 4.0**: a surveyor
takes off the 19 ResPlan plans and the reference values are then independent of BuildSmart in both
measurer and method, which is what ROOT #262's AC-2 actually asks for.

**But route A inherits our scale, and that limit must not be glossed.** A takeoff produced from our
rendering of a ResPlan plan is measured against **our** `scale_m_per_px` and **our** wall-thickness
convention. It therefore tests layers 2, 3 and 4 of ROOT #262's five — canonical geometry, material
quantities, calculation logic — and does **not** test layer 1, source measurement accuracy. That is
a genuinely useful experiment, and it is a smaller claim than "BuildSmart's quantities are accurate".
#265 would have to say so in exactly those words.

**Route D is listed to close it off.** Price books are the thing most easily mistaken for
construction ground truth, and they contain none: a rate per square metre of painting is not a
measurement of any building.

**Route C's independence has a caveat of its own.** A phone-scan product is itself an automated
measurement system, published at 1–3% against physical ANSI measurement. It is independent of
BuildSmart, which is what AC-2 requires, so it grades **`STATED`** under V5 with a published
tolerance — not `VERIFIED`, and not a professional takeoff. Comparing one automated measurer against
another is defensible only if the tolerance is reported alongside the error.
