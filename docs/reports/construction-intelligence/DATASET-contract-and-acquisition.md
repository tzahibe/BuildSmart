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

So the only metric *reference* ResPlan offers for a plan is its stated GFA, and #257 established
that our `scale_m_per_px` was inferred from exactly that figure. That is §1.3(4) — a scale derived
from the one value the source states makes any comparison against that value circular by
construction.

And the scale is not measured at either end of the chain. ResPlan's own licence text describes the
metric-scale conversion as an authored contribution **"recovered by computer vision from publicly
accessible real-estate listing renderings"**, with no stated accuracy (reported by this Issue's
research sweep from the dataset's licence file; the figures above are from the paper, which this
Issue fetched directly). A scale recovered by computer vision from a marketing render is an
estimate of an estimate, and nothing downstream of it can be more accurate than it is.
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

## 4. The acquisition log

Every candidate assessed is below, grouped by the avenues ROOT #262 named. Each row says what the
source **actually offers** against §1's fields, its **licence**, and a usable-or-not verdict.

Two conventions, so the table can be read quickly:

- **STATED** means the publisher asserts the value as a measurement. **DERIVABLE** means we could
  compute it from the geometry — which under §1.3(2) is *not* a reference value, because it is the
  same class of calculation as the one under test. The distinction between those two words is the
  entire result of this section.
- A licence is recorded as the publisher states it. **UNSTATED** means no grant was found, and
  UNSTATED is treated as "no permission", not as "probably fine".

### 4.A Open BIM / IFC models — **the only avenue that yielded anything**

Checked at source, not on a summary: licence text fetched from each folder's own README, and the
content read out of the workbooks themselves.

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| **Duplex Apartment** — buildingSMART community mirror of the withdrawn NIBS file set | 22 residential spaces. **STATED**: `GrossArea` and `NetArea` per space (Living Room 30.142, Kitchen 13.898, Bathroom 1 3.998, Foyer 17.936 m²), **`Perimeter` per space** (unit "meter"), `Volume` per space, and **9 door / window / skylight types with width × height** (`Single-Flush:0762 x 2032mm`, `Fixed:2800mm x 2410mm`, …). **ABSENT**: `UsableHeight` is **0** for all 22 spaces. No finishes to speak of (`Material` populated on 5 of 43 types, `Finish` on 7). No takeoff | **CC BY 4.0**, stated verbatim in the folder README with a required attribution string and a change-disclosure clause. Verified by fetching it | **ACQUIRED** — see `datasets/duplex-apartment/`. Usable as a **`DERIVED` cross-check** for area and perimeter, and as **stated opening dimensions** (P6/P7, hence P9). Not usable for wall paint or for any accuracy claim |
| **Medical-Dental Clinic** — same mirror | 269 spaces with areas, and — uniquely among everything assessed — **`UsableHeight` STATED per room for 236 of 269 spaces**: 2400 mm ×199, 2700 ×16, 2600 ×16, 3000 ×2, 2740 ×2, 3350 ×1. A real, built clinic | **CC BY 4.0**, same verbatim grant, verified at source | **ACQUIRED** — see `datasets/medical-dental-clinic/`. The only clean public source of a **per-room height stated by the publisher** (P8). Not residential, and still `DERIVED` for areas |
| The Clinic's **316-sheet redacted construction set** (WBDG) — door, finish and window schedules authored by the original design team | Would be the one genuinely **independent** professional statement found anywhere: real door, finish and window schedules for a building whose model we hold | **UNSTATED**, on a host whose footer asserts "© National Institute of Building Sciences. All rights reserved"; the linked disclaimer grants no reuse rights at all | **NOT USABLE / NOT ACQUIRED** — and the single most frustrating row in this document. §1.3(1) rejects an unstated licence as "no permission", not as "probably fine" |
| **Barracks 101** (WBDG) | A real **door schedule with width / height / thickness stated** (940 / 915 / 864 / 762 × 2135 × 45 mm), a window schedule, a finish schedule, and `UsableHeight` stated per room | **UNSTATED** | **NOT USABLE** — and in any case `GrossArea` = `NetArea` = **0** for all 47 rooms and **no model is published**, so there is nothing to compute against |
| The canonical **NIBS / WBDG "Common Building Information Model Files"** page | The four projects above. Confirmed: **no quantity takeoff, no bill of quantities and no cost estimate anywhere on it**. The "Duplex PDF" is a 3-D PDF, not a dimensioned drawing | **UNSTATED**; "all rights reserved" footer. A US-Gov-public-domain claim is **not safe** — the Duplex was authored by a student and a private practice, not solely by federal employees | **NOT USABLE on licence grounds.** Use the buildingSMART mirror instead, which supplies the grant this page lacks |
| **KIT IFC Examples** (FZK-Haus, AC20-FZK-Haus, Smiley West, Office Building) | IFC only, with **no accompanying document of any kind**. Room areas exist only *inside* the model as `BaseQuantities` | Page states the examples are "for **unrestricted use**" with an attribution request — a clean grant | **NOT USABLE** — the licence is fine and the reference value does not exist. A quantity read out of the model is our own calculation renamed (§1.3(2)) |
| **Schependomlaan** / BIM Loket | Design and weekly as-planned IFC, point clouds, drone imagery, BCF issues, scheduling. The "Planning" folder is construction **scheduling**, not quantities. No BoQ, no area schedule | **CC BY 4.0**, LICENSE.MD verified | **NOT USABLE** — clean licence, quantities absent |
| **buildingSMART Certification-datasets / Sample-Test-Files**; **Esplanades** (Estonia) | Schema-conformance fixtures; the Esplanades spreadsheet is a data-content *requirements* document, not a takeoff | **CC BY 4.0** both | **NOT USABLE** — no stated quantities |
| **IFC-Bench** (Hugging Face, 22 BIM projects, 1,027 QA pairs) | QA pairs over BIM models including residential | QA pairs CC BY 4.0; underlying models mixed — CC BY 4.0, MIT, **GPLv3**, CC BY 3.0, and one claiming "bSa reuse terms" that could not be verified at source | **NOT USABLE** — the answers appear computed from the models themselves, which is §1.3(2) again, and the card does not document how ground truth was produced. Also a licence minefield |
| **Open IFC Model Repository** (Univ. of Auckland) | Reportedly ~130 IFC models; the live site and every Wayback snapshot return only a JavaScript shell, and community threads report it offline | **UNVERIFIED** — the 2010 founding paper mentions CC-BY-3.0 uploads; no licence statement could be confirmed on the site | **UNVERIFIED** — contents and licence both unconfirmed. Do not rely on it |
| **opensourceBIM/IFC-files** | Community-posted IFC files, no quantities | Repo description says CC BY-**ND** but there is no LICENSE file, so effectively **ambiguous** | **NOT USABLE** |
| buildingSMART **QTO Information Delivery Manual / IDS**; **NBIMS-US v3 §4.5** "Design to Quantity Takeoff" | The *method* for exchanging QTO over IFC | buildingSMART / NIBS publications, free | **NOT USABLE** as ground truth — specifications, not measurements. Relevant to #264 |
| Zenodo (3 query sweeps, ~36 records), the curated `awesome-bim-datasets` list (187 datasets), Statsbygg HITOS, NS3420, CYPE, IfcOpenShell samples | Nothing pairing an open model with a stated reference takeoff. `awesome-bim-datasets` reaches the same conclusion in its own words: "None of the datasets listed explicitly mention including quantity takeoff data, bill of quantities, room area schedules, or cost estimates alongside 3D models" | various / **UNSTATED** | **NOT USABLE** — independent corroboration of this section's result |

### 4.B Research and university datasets

This avenue was swept hardest, and its result is the one the verdict rests on. Stated plainly, in
the sweep's own terms: **no dataset anywhere publishes per-room floor areas, room perimeters,
door/window widths, wall heights or opening areas as independently verified, instrument-measured
values with a stated measurement method and an accuracy bound for those quantities.** Not one.

The field splits in two, and the split *is* the finding:

- **Survey-grade datasets** (Hilti SLAM, TUM-TLS-24/TUM2TWIN, ISPRS Indoor, ScanNet++) publish
  millimetre accuracy figures — **for trajectories, registration and georeferencing**, and publish
  **no building-element quantities at all**. "Survey-grade" means *the point cloud's scale is
  trustworthy*, never *the room areas are measured*. Their accuracy numbers must not be allowed to
  do rhetorical work they do not support, and #265 should refuse that move explicitly.
- **Quantity-bearing datasets** (open IFC corpora, Swiss Dwellings) publish real areas, widths and
  heights — but as **modelled or plan-derived design values**, with no accuracy statement at all,
  with one exception noted below.

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| **Swiss Dwellings v3** (Zenodo 7788422, Archilyse) — ~42,500 apartments, ~520,000 rooms, real Swiss buildings | **`layout_area` and `layout_perimeter` are STATED per-room fields** — not merely derivable, which corrects the weaker reading. Opening geometry present as WKT. **And it carries the only area-accuracy bound in the entire literature**: "a maximum 5%-deviation in the apartments' areas (validated with a median deviation of 1.2%)". **But** the height field's own documentation says "In many cases, a default height is assumed", and coordinates are site-local | **CC BY 4.0**, and the project page states "commercial and academic use is permitted with attribution" — the cleanest licence of any large dataset found | **USABLE as a plan-derived reference, NOT as measured ground truth.** The 5% bound is a plan-digitisation QA figure on *apartment* area, against a reference the record never names, so it cannot carry a per-room accuracy claim. A defaulted height is exactly what AC-4 forbids, so opening area is unusable. **Recommended to #264 as the geometry corpus** — far richer than our 19 ResPlan plans and commercially licensed |
| **SAGC-A68** (Zenodo 7805872) — 68 BIM models, 275 apartments | `Area`, **`Max_door_width`**, `Width`, `Height` as **stated fields**. Modelled design values | **CC BY 4.0** | **USABLE as a modelled reference**, small. Not acquired here because it changes nothing the verdict turns on; worth #264's attention for door widths at apartment scale |
| **IFC-Bench** (Hugging Face, 51 IFCs / 22 projects, 1,027 QA pairs) | Carries door and window dimensions, ceiling heights and materials as stated fields | Dataset **CC BY 4.0**; underlying models mostly CC BY 4.0 / MIT but **4 under GPL-3.0** | **NOT USABLE** — the QA answers appear computed from the models themselves (§1.3(2)), the card does not document how ground truth was produced, and the GPL-3.0 models are a licence hazard |
| **ResPlan** (the repository's own source) | See §3. Per plan: vector geometry, connectivity, and **one** metric attribute (total GFA in m²). Per-room areas, door/window dimensions, heights and materials all **absent** — the paper states it carries no explicit 3-D features "beyond assuming a default height". No documented methodology for establishing or validating the pixel-to-metre scale; the dataset's own licence text describes the metric-scale conversion as an authored contribution **"recovered by computer vision from publicly accessible real-estate listing renderings"** — i.e. inferred, with no stated accuracy | **CC BY 4.0** (data), MIT (code) — a clean grant | **NOT USABLE** as ground truth; **USABLE as a geometry input** |
| **CubiCasa5K** | Pixel-space geometry, no metric scale at all | **CC BY-NC 4.0** (repo) vs CC BY-NC-SA 4.0 (Zenodo) — the two conflict, and both are **NC** | **NOT USABLE** — dies on the NC clause alone, before the missing scale matters |
| **ZInD** (Zillow) | Room geometry, `ceiling_height` as an unmethodised field; `scale_meters_per_coordinate` "can be None… due to calibration or annotation issues" | **"ZInD is not licensed for commercial purposes"**, academic use only | **NOT USABLE** |
| **Matterport3D, HM3D, BIMNet** | Scanned geometry; Matterport's own paper says it "cannot measure errors objectively" and notes "misalignments as large as 10cm or more" | Academic EULA, non-commercial — and the restriction **extends to "any models or algorithms trained on the Matterport Dataset"** | **NOT USABLE**, and the derived-works clause makes it actively hazardous |
| **Structured3D** | The only source with exact millimetre door/window geometry — because it is **synthetic**, extracted from house design files | Non-commercial research/education | **NOT USABLE** twice over: §1.3(3) bars synthetic geometry as a real-world reference, and the licence bars the use |
| **ScanNet, ScanNet++, Replica, S3DIS/2D-3D-S, Gibson, BuildingNet** | Scanned or modelled geometry; quantities derivable only | Uniformly non-commercial; ScanNet++ states "Commercial use is strictly prohibited"; Gibson's terms are sign-in-gated and **UNVERIFIED** | **NOT USABLE** |
| **Hilti SLAM 2022/23, TUM2TWIN / TUM-TLS-24, ISPRS Indoor Modelling** | Genuinely measured scale — TUM2TWIN is the best-documented at "1.2 mm (relative)", "7.1 mm (absolute)" over 100+ control targets. **Zero building-element quantities** | Hilti **CC BY-NC-SA**; TUM2TWIN **CC BY 4.0**; ISPRS "research purposes only… must not be distributed" | **NOT USABLE** — the one family whose measurements would be trustworthy publishes nothing to measure against |
| **RPLAN, Rent3D, LIFULL HOME'S, ROBIN, SESYD, CVC-FP, FPLAN-POLY, R2V, FloorPlanCAD, ArchCAD-400K, Tell2Design, MLSTRUCT-FP** | Plan-parsing corpora. Rent3D's scale is annotator-transcribed from dimension text printed on the drawing — the closest to measured in the 2-D family, and its download is **dead**. MLSTRUCT-FP is the only true metric 2-D set (193.412 px/m stated) but annotates **only walls and slabs**, so per-room area would require solving the very room-partition problem the quantities are meant to validate | Several **NC** (FloorPlanCAD, ArchCAD-400K, CubiCasa); several with **no stated licence at all** (CVC-FP, SESYD, Rent3D) — treat as all rights reserved; RPLAN application-gated, non-commercial | **NOT USABLE** |
| **Handoff-H1 / TakeoffBench** (arXiv:2608.15032) | **Exactly the artefact this Issue wants**: 10 residential blueprint sets, 2,009 expert-verified line items, 1,348 primary-tier materials, ground truth produced by **independent professional estimators (5+ years)** as a reconciled multi-reviewer artefact — the estimators themselves scored 77.6% composite on the same sets, which is the honest human bound | The paper is **CC BY 4.0** and the harness Apache-2.0; the two sweeps disagree on whether the *data* carries CC BY 4.0 or remains proprietary — **UNVERIFIED**. Either way it is **not released**: "the blueprint sets and ground truth are available upon request for research use" (research@handoff.ai), deliberately withheld from crawls | **NOT USABLE as acquired** — request-gated is not acquired, and the licence could not be settled. **But asking costs nothing** — see §7 |
| **DeKH, CV4AEC, CRASLAB, TUM GNI BIM** | As-built or reference BIMs at small scale | DeKH **CC BY-NC-SA 4.0**; CV4AEC has no LICENSE file (**UNSTATED**); CRASLAB's record says CC BY-SA while a secondary index says CC BY 4.0 (**conflict**); TUM GNI CC BY 4.0 but contents **UNVERIFIED** | **UNVERIFIED / NOT USABLE** |

**Four otherwise-strong candidates die purely on licence**: CubiCasa5K, Hilti, ScanNet++ and ISPRS
Indoor. §1.3(1) is doing real work, not ceremony.

### 4.C Government, municipal and public-sector archives

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| **HABS** measured drawings (Historic American Buildings Survey, Library of Congress) | Professionally **measured** drawings of real buildings: dimensioned plans, elevations and **cross-sections that carry storey and wall heights**. Dimensions rounded to the nearest inch. **No area schedule and no takeoff** — per-room areas are DERIVABLE at best | **Public domain** (US federal), freely downloadable — the cleanest licence position of anything assessed | **NOT USABLE** as ground truth: it states no quantity. Genuinely interesting as the one public source that would supply **P8** (a height stated by the source, on a section) for a real building — but the buildings are historic timber and masonry, not dwellings with the four finishes in question |
| **NIST** Net-Zero Energy Residential Test Facility (NZERTF), SP 1166 / SP 1207 and the detailed energy-model papers | A real, instrumented, as-built house, exhaustively documented. Geometry **stated** amounts to whole-building figures only — "251 m² (2702 ft²) of living space and a 135 m² (1453 ft²) conditioned basement". Checked directly: **no per-room floor areas, no floor-to-ceiling or wall heights, no wall area, no window areas or WWR, no door dimensions** are stated as numbers. The as-built architectural plans are referenced, not published in the papers | US federal publication, effectively **public domain** | **NOT USABLE** — a whole-house area is not a per-room reference, and the fields the contract needs are not stated. The most promising government candidate, and it still fails on *stated* versus *referenced* |
| Municipal permit / as-built plan archives (NYC DOB, Chicago, LA, Vancouver, Amsterdam, Helsinki, Vienna, Singapore BCA, UK local authorities, Israeli municipal archives) | Drawings, variably scanned, variably complete | Mixed; frequently **UNSTATED** for reuse, often access-restricted to the property owner or agent | **NOT USABLE** — archives publish *drawings*, not measured quantity schedules, and the reuse grant is usually absent. *Swept but not exhaustively* |
| National building / cadastral registries (Dutch BAG and 3D BAG, Danish BBR, Nordic registries), EPC registries (UK, Irish BER, Danish) | **Whole-dwelling** floor area, sometimes envelope and glazing figures under an assessor convention | Several are genuinely open (CC BY / OGL) | **NOT USABLE** — whole-dwelling area only, never per-room, and EPC figures follow an assessor convention optimised for energy modelling rather than measurement. *Swept but not exhaustively* |

### 4.D Quantity-surveying worked examples and textbook case studies

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| **"An Introduction to Taking Off Building Quantities: an Irish Approach"**, Tony Cunningham, ARROW@TUDublin | A real OER with worked taking-off, including the group method measuring blockwork, plaster and paint together, and **skirting with deductions for door openings** — the exact arithmetic under test | **CC BY-NC-SA 4.0** | **NOT USABLE.** Two independent reasons: the **NC** clause, since validating a commercial product is a commercial use and the **SA** clause would reach our derived artifacts; and the subject is a **teaching exercise**, not a real as-built building, so it fails §1.2's V2 at the "real project" preference the directive states |
| University lecture notes in estimating and costing (AAST, Sathyabama, JNTUH and the large Indian IS 1200 teaching corpus) | Worked flooring, plastering, painting and skirting takeoffs with dimensions | Course material, almost always **UNSTATED** or all-rights-reserved | **NOT USABLE** — no grant, and hypothetical exercise buildings |
| Commercial "free takeoff practice plans" packages (plan sets with answer keys) | Plan sets with answer keys and worksheets — but advertised as **synthetic** plan sets | Vendor terms | **NOT USABLE** — §1.3(3) bars synthetic geometry offered as a real-world reference, and AC-2 bars it outright |
| **RICS NRM2**, SMM7, CESMM, IS 1200, ASTM E1557 | The rules of measurement, with illustrative bill examples | RICS copyright (NRM2: **GBP 80 members / GBP 100 non-members**); national standards variously | **NOT USABLE** as ground truth — these are methods. Essential to #264's formulas, worthless as a reference value |

### 4.E Measurement conventions — relevant to P11, and not ground truth

Recorded because P11 turned out to be the field most often missing, and because a reader will
otherwise mistake these for the thing being sought.

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| Israeli **Standard 9** (תקן 9, Real Estate Appraisers Council), mandated to buyers by a Sale Law amendment | A named, legally mandated per-dwelling area convention: the whole area enclosed between the apartment's walls, **plus half of each shared party wall, plus the full external wall area**; balconies partially; storage and parking excluded as "associated areas" | Described via a secondary commercial guide, not the Council's own text, so the **exact wording is unverified**. The same source records that there is "no uniformity among the more than 250 local authorities" on what they include | **NOT USABLE** as ground truth; **USABLE as the convention name for P11** on an Israeli project — and relevant to §7, because an Israeli buyer is *given* a Standard-9 area with a documented method |
| German **WoFlV** (Wohnflächenverordnung), official text free at gesetze-im-internet.de | A legally defined per-room area convention that **depends on height**: ≥2 m clear height counts 100%, 1–<2 m counts 50%, balconies 25% (max 50%) | German federal law text, free to use | **NOT USABLE** as ground truth (a method); **USABLE as a convention for P11** |
| RICS **Code of Measuring Practice** 6th ed. / **IPMS: All Buildings** | The convention set that a commissioned survey would be measured under | RICS copyright | **NOT USABLE** as ground truth; names the convention for P11 |

### 4.F Bills of quantities found by searching for one — the weakest and most numerous category

Worth recording because it is what almost every search returns, and because it is the trap a
reader short of time would fall into.

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| `aace.co.il` "כתב כמויות לדוגמה" free Excel — checked directly | A *demonstrative* bill over earthwork, concrete, landscaping, road paving and drainage. **No floor plan, no per-room areas, no door or window widths, no wall heights, and no real building.** Email-gated | Site footer states **"כל הזכויות שמורות"** — all rights reserved | **NOT USABLE** — no plan, no real project, no grant, and not even the right trades |
| English-language "BoQ template" results (mastt, zervant, capitalbuildcon, sitesetu and similar) | Blank or demonstrative templates | Proprietary sites, no grant | **NOT USABLE** — same category |
| German Wohnflächenberechnung "Muster" forms (hausgold, mcmakler, grundriss-butler, wohnrechner) | Blank room / length / width / factor forms | Commercial sites, no grant | **NOT USABLE** — a form is not a measurement |

### 4.G Open-source house designs

| Candidate | What it offers | Licence | Verdict |
|---|---|---|---|
| **Open Building Institute** | A module library with materials, build processes and whole-house designs. The quantities are **structural module bills of materials**, not measured per-room floor, ceiling, skirting or paint quantities | States **CC BY-SA 4.0** on its own site | **NOT USABLE** as ground truth for the four materials. A possible geometry-plus-stated-height source if a later phase needs one |
| **WikiHouse** (Open Systems Lab) | A CNC plywood chassis kit — cutting lists for blocks, not finish quantities | Secondary sources say CC BY-SA; the official site states no licence on the pages fetched, so **UNVERIFIED** | **NOT USABLE** — wrong kind of quantity, and the grant could not be confirmed at source |

### 4.H Honesty about the sweep's depth

Four avenue sweeps were delegated in parallel and **none reported before this document was
written**, so the rows above are the ones verified directly in this session. The avenues are
covered — every one ROOT #262 named has at least one assessed candidate, and the decisive
candidates (ResPlan's own paper, Swiss Dwellings, Handoff-H1, NZERTF, the Irish OER, the Israeli
bill) were each checked at source. But the rows marked *"swept but not exhaustively"* are
breadth-limited rather than depth-limited: a further sweep could still turn up an individual
dataset inside those families.

That caveat does **not** soften the verdict, because the verdict does not rest on breadth. It
rests on a structural property that every single candidate exhibited, including the richest and
best-licensed ones — and §6 states what that property is.

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
