# #263 — Dataset contract and acquisition: real plans with independently verified quantities

ROOT: #262 (owner directive 2026-10-27, the mandatory evidence gate before the Construction
Intelligence pivot). Child 1 of 3; #264 (schema, formulas, harness) and #265 (comparison report,
recommendation) are gated behind this one.

**Verdict: PARTIAL — §6.** Two real projects acquired under a verified CC BY 4.0 grant; **no
reference quantity for any of the four materials was acquired, and none exists in public licensed
form.** No production file is changed.

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
source can. §8 lists everything left unverified.

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

| Candidate | What it STATES (as against derivable) | Licence | Verdict |
|---|---|---|---|
| **USACE Army Standard Designs** (Centers of Standardization, hosted on MRSI) | The only public source found that puts a **per-room area and a ceiling height on the same drawing**. Verified by extracting the PDF text layer: 492 `NNN SF` tags across 17 plan sheets, each beside a room name and number, plus **FINISH SCHEDULE** tables with columns `ROOM NO / ROOM NAME / … / MIN. CLNG HEIGHT / NET SF` — e.g. `108 SR LEADERS QUARTERS … 8'-0" 285 SF`, `108A BATH … 8'-0" 39 SF`, `110 LAUNDRY … 9'-0" 289 SF`. **Not stated**: perimeters, any door or window schedule, any takeoff | US Government work (USACE / ERDC-CERL) → **not subject to US copyright, 17 U.S.C. §105**. No distribution marking. Free, no login | **USABLE for P4 + P8** — and that is the high-water mark of this entire avenue. Three caveats: the schedule's own note says the net SF is "as reflected in the standard floor plan" and "may change", so it is a **design figure, not an as-built survey**; the programme is barracks, HQ and dining, not family housing; and there is still **no reference quantity** for any of the four materials |
| **2025 Army UH (barracks) Standard** + required room-module configurations | Residential module **minimums**: E1–E4 shared bedroom 240 NSF, E5–E6 bedroom 140 NSF, closet 30 NSF/soldier, 485 GSF/occupant, min bedroom width 10'-0", and the DoD net-area definition quoted ("within the interior face of full height walls… does not include the area of a closet") | US Gov work → **public domain** | **USABLE as a room-area reference**, weaker than the row above because the plan graphics carry no per-room tags. Minimum requirements, not plan measurements |
| **UK EPC open data** | `TOTAL_FLOOR_AREA` in m², defined as the "total enclosed floor area … measured to the internal face of the external walls … follows recognised professional standards (RICS)", and **`FLOOR_HEIGHT` in m, "Measured from finished floor level to the ceiling for each storey"** at national scale. Method documented (RdSAP conventions, 0.1 m precision). **`GLAZED_AREA` is a BAND, not a number**. No per-room areas, no perimeters, no opening widths | **Open Government Licence v3.0** for all fields other than address/postcode — verified verbatim | **USABLE for dwelling-level area and storey height; NOT for per-room.** The best-licensed *measured* figure found anywhere, and at the wrong granularity |
| **SEAI BER Research Tool** (Ireland) | The only source found stating **`WindowArea` AND `DoorArea`** plus per-storey heights (`GroundFloorHeight`, `FirstFloorHeight`, …) as data, per dwelling. Method: DEAP/BER assessor survey. No per-room areas. Known trap: the `FloorArea` / `GroundFloorArea` columns are inverted relative to their names | **CONFLICTING** — data.gov.ie states CC BY 4.0; SEAI's own T&Cs are narrower, "may be used for personal, research or education purposes" | **USABLE for research with attribution; commercial reuse UNVERIFIED.** Do not rely on the CC BY claim without asking SEAI |
| **NIST NZERTF** (TN 1847, TN 1767) | TN 1847 Table 1 states **per-façade** exterior wall surface area (71.3 / 71.3 / 83.7 / 83.7 / 310 m² total) and glazing area (11.7 / 16.5 / 6.2 / 4.2 / 38.6 m²). TN 1767 states 251.7 m² conditioned floor area actual (141.0 first / 110.6 second) against 284.6 m² in the energy model, with the 32.9 m² discrepancy itemised. **Rooms are named but never area-tabulated** — the model has two conditioned zones, i.e. whole floors. No door or window widths | NIST Technical Notes, US Gov → **public domain in the US** | **PARTIALLY USABLE** — an excellent single-house envelope and glazing reference, useless per-room. Note the 33 m² gap between the as-built area and the model's: a worked example of why "stated" needs a revision field (V4) |
| **HABS measured drawings** (Library of Congress / NPS) | **No area schedule exists, by design.** The guidelines say "Every drawing… should have at least one string of dimensions" but also "Avoid excessive dimensioning. For example, in plans it is not necessary to dimension every opening, only major massing features"; room dimensions are merely optional, "For significant rooms, it may also be useful to note the overall room dimensions". Measurement method is best-in-class — metal tapes, continuous running strings to avoid cumulative error, "to the nearest 1/8"", laser total station for irregular rooms | NPS (US federal) → public domain expected; the LoC rights statement itself is **UNVERIFIED** (403 on two attempts) | **NOT USABLE** — the finest measurement method found and it produces no numeric reference: zero areas, no opening widths, dimensions existing only as drawing annotations. This settles the HABS question directly |
| **VA PG-18-9 / PG-18-12**; **UK Nationally Described Space Standard** | Room areas in NSF by function, and NDSS minimum GIA by bedrooms/bedspaces, single bedroom ≥7.5 m² and ≥2.15 m wide, floor-to-ceiling ≥2.3 m over 75% of GIA | US federal public domain; NDSS under **OGL** | **USABLE as room-size priors and a validation rule set**, not as ground truth. These are programming criteria, never measurements of a built plan |
| **Dutch BAG / 3D BAG; Danish BBR** | BAG: `oppervlakte` per dwelling, measured under **NEN 2580:2007** from the inside of the enclosing construction, with a stated tolerance of 1.15·√(area). 3D BAG: per-building exterior wall area, party-wall area, roof areas, volumes and height percentiles with published RMSE. BBR: per-unit totals and a **room count**, areas measured *including* internal and external walls | 3D BAG **CC BY 4.0**; BAG open register, exact instrument **UNSTATED**; BBR open via Datafordeler, instrument **UNVERIFIED** | **NOT USABLE** for per-room. Notable for one thing only: BAG is the one source with a **stated measurement tolerance**, which is what V5 reliability should look like |
| **Hong Kong Housing Authority standard block plans** | Verified by extracting the PDF text: labels only — `1B / 2B / 3B / 1P`, `LIFT LOBBY`, `METER ROOM`, a title and a scale bar. **Zero dimensions, zero areas** | **Not open** — "any reproduction, adaptation, distribution … is strictly prohibited" without written authorisation; download for "personal or non-commercial use" only | **NOT USABLE** — no numbers *and* a prohibitive licence |
| **Singapore HDB BTO sales brochures** | Per **flat type** only: "Approx. Floor Area 48 sqm / Inclusive of Internal Floor Area of 46 sqm and Air-Con Ledge". Raster plans with room labels, no room dimensions, no area schedule | Brochure terms **UNSTATED** (terms URL 404); data.gov.sg datasets under the Singapore Open Data Licence carry dwelling counts, not room geometry | **NOT USABLE** for per-room |
| **Municipal permit / as-built archives** — NYC DOB, Amsterdam bouwdossiers, Tel Aviv, Vancouver Archives, Helsinki | Plan sets, not quantities. **One exception worth recording for §7**: an Israeli permit set must by regulation (תקנות חישוב שטחים ואחוזי בנייה) contain a **building-areas table by floor and by use** — a genuine stated area schedule, though by use and floor rather than per room | Third-party architect copyright throughout; archive terms **UNSTATED**. NYC paper copies $8 first page + $5/page; Helsinki must be purchased | **NOT USABLE / UNVERIFIED** — no stated numbers as data and no reuse licence |
| **UK local-authority planning portals** | Full drawing sets free to download, sometimes including an applicant's area schedule — as pictures, not data | **Not open** — restricted to "consultation purposes", copyright vests in the architect, and a 2017 High Court ruling confirmed that portal availability is not a reuse licence | **NOT USABLE** |
| **GSA IOLP**; DOE/PNNL and ORNL research houses | Building rentable square feet; prototype boxes (PNNL 30 ft × 40 ft, 2400 ft² CFA, window area assumed at 15% of CFA; NIST TN 1765 19.5 m × 7.6 m, 148.6 m² CFA, 2.4 m ceiling, doors 0.9 × 2.0 m — **and no interior partitions at all**; ORNL footprint and volume per floor) | US federal → **public domain** | **NOT USABLE** for per-room — every one is a single zone or a per-floor box |
| **Public-sector bills of quantities** (e.g. national public-works tender BoQs) and **Statsbygg HITOS** open IFC | The only two routes that would give a genuine takeoff, or IFC `Qto_SpaceBaseQuantities` plus door/window `OverallWidth` | **UNSTATED** — BoQ licences are per-tender; Statsbygg's published IFCs carry no stated licence | **UNVERIFIED** — plausible, and neither the drawing-to-quantity pairing nor the licence could be confirmed |

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

Four avenue sweeps were delegated in parallel. **Three reported** — open BIM/IFC, research and
university datasets, and government archives — and each verified its decisive candidates at source
rather than from summaries: PDF text layers extracted, licence files fetched, workbooks read. The
acquisitions in §4.A were then re-verified independently for this document: the CC BY 4.0 grants
were fetched from their own READMEs, and every content claim about the Duplex and the Clinic was
read out of the workbooks here, including the three defects recorded in `datasets/README.md`.

**The quantity-surveying worked-examples sweep did not report.** §4.D is therefore the one
avenue covered only by direct research in this session, and it is **breadth-limited**: the Irish
OER, the Indian IS 1200 teaching corpus, the standards bodies and the commercial template
category were each checked, but a further sweep could still surface an individually licensed
worked example that was missed.

That gap does not change the verdict, and it is worth saying why rather than asserting it. A
textbook worked example is a **hypothetical building**, so even a perfectly licensed one fails the
directive's stated preference for real projects with documented as-built measurements, and it
could not test layer 1 (source measurement accuracy) under any licence. The verdict turns on a
property every candidate in every avenue exhibited — §6 names it — not on how many candidates were
counted.

Unverified items are listed in §8.

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

---

## 6. The verdict

# PARTIAL

Two projects were acquired under a verified CC BY 4.0 grant. **No reference quantity for any of the
four materials was acquired, and none exists in public licensed form.** Those two sentences are the
whole verdict, and they point in opposite directions, so §6.1 says exactly what is covered and
§6.2 exactly what is not.

The temptation here was to call this ACQUIRED, and it must be refused. Two real buildings with
publisher-stated per-room areas is a genuine result and it is **not** the thing ROOT #262 asked
for.

### 6.1 What is covered

| Project | Licence | Provenance | Fields it supplies |
|---|---|---|---|
| **Duplex Apartment**, 22 residential spaces | **CC BY 4.0**, grant quoted verbatim, attribution string recorded | Published in Germany → US Army ERDC-CERL → NIBS 2009–2020 → buildingSMART mirror. `ExtSystem` = `Autodesk Revit Architecture 2011` | P1, P2, P3 (SI), **P4** area, **P5 perimeter**, **P6/P7** door and window width × height, **P9** opening areas |
| **Medical-Dental Clinic**, 269 spaces | **CC BY 4.0**, grant quoted verbatim | → ERDC-CERL → NIBS 2010–2020 → buildingSMART mirror; the US "COBie Challenge" test model | P1, P2, P3, **P4** area, and **P8 — a per-room height stated by the source for 236 of 269 rooms** |

So three things are genuinely now possible that were not before:

1. **An area and perimeter cross-check against a third party's figures** for the same building —
   the first reference numbers in this repository that did not come out of its own arithmetic.
2. **Baseboard length with real door deductions**, because the Duplex states door width × height
   per type and maps 36 opening instances to the spaces they serve. Nothing else public does this.
3. **Wall height and opening area as inputs carrying provenance**, satisfying ROOT #262's AC-4
   without inferring either — the Clinic's `UsableHeight` for the height, the Duplex's stated
   opening dimensions for the areas.

Also recommended to #264, assessed but deliberately not acquired because they change nothing the
verdict turns on: **Swiss Dwellings v3** (CC BY 4.0, commercial use permitted, ~520,000 rooms with
`layout_area` *and* `layout_perimeter` stated) as the geometry corpus in place of our 19 ResPlan
plans, and **SAGC-A68** (CC BY 4.0, 275 apartments) for `Max_door_width`.

### 6.2 What is missing — and it is the thing the gate exists to test

**No public, licensed source states a quantity of flooring, ceiling paintable area, baseboard
length or wall paintable area for any building.** Not one, across every avenue in §4. Every source
found publishes *inputs* — areas, heights, opening sizes — and never the *output* this experiment
was built to validate.

**And nothing acquired is a measurement.** Both acquisitions self-declare as a Revit export, so
both grade `DERIVED` under V5, which §1.2 restricts to a cross-check that "may not carry an
accuracy claim". The §4.B sweep put the general case beyond argument: no dataset anywhere publishes
per-room areas, perimeters, opening widths or heights as independently verified, instrument-measured
values with a stated method and an accuracy bound. The field splits into survey-grade datasets that
measure *trajectories* to a millimetre and publish no building quantities, and quantity-bearing
datasets that publish modelled design values with no accuracy figure at all.

Three measured facts from §3 and §4 that each independently block the stronger claim:

- The repository's own 19 plans are disqualified by an identity: across all 179 real rooms,
  `area_m2` equals the shoelace area of the room's own polygon to within **0.00061 m²**. Comparing
  against it would report an identity as an accuracy.
- The Duplex's stated `Volume` cannot supply the missing height: `Volume / GrossArea` spans
  **2.045 m to 4.225 m** and differs between a bathroom and a kitchen on one storey. The tempting
  inference is both forbidden and wrong.
- The one artefact that is exactly right — Handoff-H1's 10 residential blueprint sets with 2,009
  expert-verified line items from independent professional estimators — is **not released**, and
  the two sweeps could not even agree on its data licence.

### 6.3 What this binds on #264 and #265

Stated as constraints rather than advice, because the gate's value depends on them:

1. **§1.4's minimum viable set is not met** — zero projects carry a `VERIFIED` or independently
   `STATED` reference value. #265 **may not report an accuracy figure for the system**. It may
   report a per-project cross-check, labelled as a cross-check.
2. **Layer 1 of ROOT #262's five — source measurement accuracy — cannot be tested at all** on what
   was acquired, and must be reported as such alongside comparison B's existing "not applicable".
   Two of five layers unmeasurable is itself a finding for the pivot decision.
3. **Comparison A is bounded to layers 2–4** (canonical geometry, material quantities, calculation
   logic), against publisher-`DERIVED` references, on two buildings of which one is a clinic.
4. **Survey-grade accuracy figures may not be borrowed.** A dataset's 1.2 mm registration accuracy
   says nothing about its room areas, and #265 must refuse that substitution explicitly.

### 6.4 Why not BLOCKED, and why not ACQUIRED

**Not BLOCKED**, because two legally usable real projects were obtained and they move real work
forward: #264 can now build the schema and formulas against stated opening dimensions, a stated
per-room height and third-party areas, instead of against nothing.

**Not ACQUIRED**, because ROOT #262 asks whether BuildSmart can produce *trustworthy construction
quantities*, and after a full sweep of six avenues not a single public licensed source states one.
Calling two Revit exports "ground truth" would be the precise failure the owner's directive names.

---

## 7. What the owner could supply that no public source can

This is the most useful part of a PARTIAL verdict, so it is a checklist rather than prose. The
single gap is a **reference quantity measured on a real building**. The owner can close it; the
internet cannot.

### 7.1 The one artefact that would change everything

**One real project, with its professional takeoff.** An Israeli project the owner can reach — his
own, a client's, or a contractor or quantity surveyor he knows — supplying all seven items:

| # | Artefact | Why no public source has it | Contract field |
|---|---|---|---|
| 1 | **The plan at a stated scale** — PDF or DWG with a title-block scale, or dimension strings on the drawing | Public plans are either unlicensed or carry an inferred scale | P1, P3 |
| 2 | **Per-room floor areas as measured on site**, with the method named (tape / laser) and the convention stated (Standard 9, or net clear internal) | Every public per-room area found is a design or model figure, never a site measurement | P4, V2 |
| 3 | **Room perimeters**, or dimensioned room geometry to derive them | One public source states perimeters; it is a Revit export | P5 |
| 4 | **Door and window schedule** — width **and** height per opening, as built | Found exactly twice in public, both under an unstated licence | P6, P7, P9 |
| 5 | **Wall heights, measured** — floor-to-ceiling per room | The scarcest field in this entire report. One public source states it per room, for a US clinic | P8 |
| 6 | **Wall thickness and the measurement convention** | Essentially never stated | P11 |
| 7 | **The professional takeoff — the כתב כמויות** for flooring, ceiling paint, skirting and wall paint, with units and the measurer's name | **This is the item that exists in no public, licensed source anywhere on earth.** §4 found one such artefact and it is request-gated and proprietary | The reference values themselves, at `VERIFIED` |

**Item 7 is the whole ask.** Items 1–6 are inputs the experiment can already partly cover; item 7
is the only thing that makes the comparison a measurement of trustworthiness rather than a
consistency check. One project with item 7 beats every public source assessed in this document,
combined.

Two facts that make this more reachable for the owner than for most people, both recorded in §4:
an Israeli permit set must by regulation contain a **building-areas table by floor and by use**;
and an Israeli buyer is *given* a **Standard 9** area with a documented convention — "the whole
area enclosed between the apartment's walls, plus half of each shared party wall, plus the full
external wall area". A named, legally mandated convention satisfies P11, which almost nothing else
does.

### 7.2 Three cheaper fallbacks, in order of value per effort

1. **Tape-measure three dwellings he can enter.** Room-by-room clear internal dimensions, the wall
   height, and every door and window width and height. **Free**, independent of BuildSmart, and the
   only route in this document that grades **`VERIFIED`** under V5 — a human physically measuring a
   real building. It supplies P3–P11 but not item 7, so #265 could test layers 1–3 and still not
   compare against a professional's judgement. Even so it is more than anything public offers,
   and it is the cheapest thing on this list.
2. **Ask Handoff for the benchmark.** Email research@handoff.ai requesting the TakeoffBench
   blueprint sets and ground truth for research use: 10 residential sets, 2,009 expert-verified
   line items, ground truth reconciled across multiple professional estimators, with a published
   human bound of 77.6% composite. **No payment, and asking costs nothing.** Two caveats the owner
   should weigh himself: the data licence could not be settled from public sources, and the
   publisher is commercially adjacent to this product area.
3. **One phone call to a quantity surveyor.** A QS asked for a single past project's drawings plus
   its כתב כמויות, for validating software, is a far smaller favour than it sounds and is the
   fastest path to item 7.

### 7.3 If he will authorise spend

§5 has the costs and licences; nothing was purchased. In short: a professional takeoff at
**USD 150–400 per plan** is the cheapest route to item 7 and can be ordered against plans already
held under CC BY 4.0 — but it inherits our scale and convention, so it tests layers 2–4 and not
layer 1. A commissioned **RICS/IPMS measured building survey at GBP 1,500–15,000** is the only paid
route that satisfies the entire contract, heights and openings included.

### 7.4 What the owner should not do

Supply a plan **without** item 7 and expect an accuracy verdict. That is the position this report
is already in, with two buildings; adding a third changes nothing. The missing artefact is the
measured quantity, not more geometry.

---

## 8. Unverified, and what would settle each

| # | Claim | How it would be settled |
|---|---|---|
| 1 | The exact arithmetic by which our `scale_m_per_px` was derived — #257's finding is cited, the normaliser is on `integration/poc-architectural-brain` from #94/#95 and not at this head | Read the normaliser on that branch. The §3 conclusion does not depend on it |
| 2 | ResPlan's licence-file wording about the computer-vision scale recovery came from a research sweep, not a direct fetch | Fetch the licence file from the Kaggle release. The paper's own statements in §3 and §4.B were fetched directly |
| 3 | Handoff-H1's **data** licence — one sweep reports CC BY 4.0, another reports proprietary | The access request in §7.2(2) would settle it |
| 4 | Israeli **Standard 9**'s exact wording, taken from a secondary commercial guide rather than the Real Estate Appraisers Council's own text | Read the Council's published standard |
| 5 | The Clinic's 316-sheet construction set — whether any reuse is permitted | Ask NIBS/WBDG. It is the one genuinely independent professional artefact found |
| 6 | **WikiHouse**'s licence — secondary sources say CC BY-SA, the official site states none on the pages fetched | Read the licence in its GitHub repositories |
| 7 | **SEAI BER**'s commercial-reuse terms — data.gov.ie says CC BY 4.0, SEAI's own T&Cs are narrower | Ask SEAI |
| 8 | Statsbygg HITOS, public-sector tender BoQs, Open IFC Model Repository (site returns a JS shell), Gibson and S3DIS full terms (sign-in gated), CRASLAB's licence (two sources conflict) | Each named in §4 with what blocked verification |
| 9 | §4.D's breadth — the quantity-surveying worked-example sweep did not report | A further sweep. §4.H says why the verdict does not turn on it |
| 10 | Whether a US-federal public-domain claim is safe for the NIBS-hosted files, given a private practice co-authored the Duplex | Moot in practice: the buildingSMART mirror supplies an explicit CC BY 4.0 grant, which is what was relied on |
