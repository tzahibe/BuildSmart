# DRAWING — the person's own parcel (Issue #223, ROOT #220)

Evidence for #223. Every number below is read off the product's own `DemoDesign` payload, produced
by `app.demo.service.generate_demo_design` — the exact function `POST /projects/{id}/design/demo`
calls, with `brain=True` being exactly what `?engine=brain` sets. The figures are the product's own
renderer (`DemoPlan` + `PlanLegend`), rasterised with the product's stylesheets. No harness drawer
and no second opinion about geometry appear anywhere in this report.

Data: `data/site-parcel/` · Figures: `figures/site-parcel/` · Tests:
`backend/tests/demo/test_site_from_brief.py`

---

## 1. Where the parcel actually enters, and where it was lost

The chain was already intact for all but one hand-off. Traced on `origin/main` at `5b155d1`:

| # | what happens | where |
|---|---|---|
| 1 | the person enters `plot_width_m`, `plot_depth_m`, the street-facing side and (optionally) their own setbacks | `app/demo/router.py:337-397` |
| 2 | the parcel is rotated into the engine's canonical frame (street at `y=0`) and the setbacks recorded — **never derived from the building**: `derive` deliberately takes no footprint argument | `app/demo/site_geometry.py:158` |
| 3 | a brief with no parcel is **refused**, not planned — `SITE_GEOMETRY_REQUIRED` | `app/demo/scope.py:326` |
| 4 | the parcel becomes `ArchitecturalSpec.plot`, the brief's bay count becomes `ProgramSpec.parking_spaces` | `app/demo/requirements_view.py:447` |
| 5a | **PRODUCTION** builds its site from that spec: `plot = Rect(0, 0, spec.plot.width_m, spec.plot.depth_m)`, `site.build_parking(spec)`, `site.classify_garden(...)` | `app/vertical_slice/general_pipeline.py:_site_plan_for` |
| 5b | **THE BRAIN** builds its programme from the same spec — and `Programme` had nowhere to put the parcel, so it was dropped here | `app/vertical_slice/brain/proposer.py:programme_from_spec` |
| 6b | with no parcel to draw, the realizer **synthesised** one: the footprint's bounding box plus a 2 m skirt, `parking=()`, and a garden that is only `remainder_within_bbox` — the crook a multi-wing footprint leaves inside its own box, which is **empty for a one-wing house** | `app/vertical_slice/rectilinear_realizer.py:_build_site` |
| 7 | `assemble` → `GeometricDesign.plot_m` / `parking_m` / `garden` → `to_demo_design` → the renderer | `design_output.py`, `demo/contract.py` |

**So the defect is the brain path only.** #213 reported it as affecting "production as well as the
brain"; measured, production carries the parcel correctly on every one of the three counts. That
correction is section 3.

## 2. What now reaches the payload

`site.SiteFrame` is the carrier: the plot rectangle, the street-side band (`front_band_m` already
resolved — the front setback, or one parking bay when that is deeper), the side and rear setbacks,
and the bays. It is built in exactly one place, `site.site_frame_for(spec)`, from the spec and
nothing derived from the building. It rides `Programme.site_frame` →
`band_pipeline.PipelineInput.site_frame` → `realize_layout(site_frame=...)` /
`realize_cells(site_frame=...)` → `_build_site(wings, frame)`. Every parameter defaults to `None`,
so no existing caller changes.

* **the plot** is the parcel, at `(0, 0)`, with the brief's own dimensions.
* **the setbacks** are already applied: the house is centred across the buildable width and flush
  to the street-side band — `site.place_footprint`'s convention, the one production's plans stand
  by. A rigid translation of the realized wings, applied before walls, doors, windows, the
  validators or the payload read the rects, so none of them can disagree with the placement.
* **the garden** is `site.classify_garden` — production's own remainder classification, not a
  second opinion — run on the real parcel, the real house and the real bays.
* **the parking** is `site.build_parking(spec)`: the bays the brief asked for, at the street edge,
  and the entrance walk is kept off them by `site.entrance_x_clear_of_parking` (moved there from
  `general_pipeline`, so there is one implementation rather than two; with no bays it returns the
  midpoint, which is what both call sites computed before).

### Measured, same brief, both engines

Brief: a **23.0 × 20.0 m** parcel (460.0 m²), setbacks 0 (the product's committed defaults), a
15 × 12 m outline, 180 m² requested, **2 parking spaces**. `data/site-parcel/engines-{before,after}.json`.

| fact | brain, before | brain, after | production, before **and** after |
|---|---|---|---|
| plot drawn | 19.30 × 15.95 m (**307.8 m²**) | **23.00 × 20.00 m (460.0 m²)** | 23.00 × 20.00 m (460.0 m²) |
| plot is the brief's parcel | **no** | **yes** | yes |
| footprint position | (2.00, 2.00) — the skirt | (3.85, 5.00) — centred, behind the bay band | (4.05, 5.00) |
| parking bays drawn | **0 of 2 asked for** | **2 of 2** | 2 of 2 |
| garden regions / area | **0 / 0.0 m²** | **4 / 231.4 m²** | 4 / 219.4 m² |
| entrance walk | 1.2 × 2.0 m, to the skirt's edge | 1.2 × 5.0 m, street → front door, clear of both bays | 1.2 × 5.0 m |

The same brief with `parking_spaces = 0`: brain garden **0 → 3 regions / 277.2 m²**, bays stay 0,
and the house moves onto the building line at `y = 0` exactly as production's does. Nothing is
invented when nothing is asked for.

## 3. The parking finding (AC-4) — the Issue is NOT narrowed

#213 could not measure this: every brief in its 26-brief corpus had `parking_spaces = 0`
(`comparison_corpus/run.py`'s `project_for` hard-codes it, and so does the `_project` helper it
builds on). Measured here against a brief that **does** ask for parking:

* **The brain drew 0 of the 2 bays the brief asked for.** `_build_site` passed `parking=()`
  unconditionally — the bay count never reached it. This half of the defect is real, and the Issue
  stays as filed.
* **Production is correct, and always was.** It draws exactly the requested bays (0 → 0, 2 → 2),
  at the street edge, with the house behind the 5.0 m band and the walk routed clear of them.
  `tests/test_parking_band.py` already pinned that behaviour; `test_site_from_brief.py` now pins it
  at the payload level alongside the brain's.

The same correction applies to the other two halves: production's plot and garden were already the
person's own. **#213's "it affects production as well as the brain" is wrong — the defect was the
brain path only**, and #223 changes nothing production draws (section 5).

## 4. When there is no parcel: a stated absence, never a rectangle

The product cannot reach this case — `scope.check_supported` refuses a project with no
authoritative parcel (`SITE_GEOMETRY_REQUIRED`) before anything is planned, and the new test pins
that first. A caller that realizes geometry **without** one (a harness, a frozen polygon case) now
gets the absence in the payload instead of a plausible boundary:

`SitePlan.notice` → `GeometricDesign.site_notice` → the plan's `validation.warnings`, through the
same channel #180's capacity notice uses for "something true about THIS plan you must read before
the drawing". The text (`site.NO_PARCEL_NOTICE`) names the rectangle a **drawing margin, not a plot
boundary**, and says the garden and parking are absent because there is no parcel to derive them
from. A realized footprint that runs past the buildable envelope is disclosed the same way
(`_parcel_notice`) rather than clamped away. The payload shape is unchanged: `warnings` is a list
that already existed, and `site_notice` is `None` for every plan built from a real brief.

## 5. The plan did not move — only the site around it

`primary_signature_changes: none`, checked two ways:

* **At the payload, all 8 brain plans of the parking brief** (`test_ac5_...`): every room, wall,
  door, window and validator verdict is byte-identical relative to the footprint's own corner,
  with the parcel and without it. Only where the footprint stands in the plot differs.
* **End to end through `?engine=brain`'s own exact sizer, three briefs**
  (`data/site-parcel/plan-did-not-move.json`): same partis, same alternatives, same count —
  `plan_identical_up_to_translation: true` on all three, with translations of
  (1.85, 3.00), (1.85, −2.00) and (0.00, 3.00) m.
* **Production's payload is byte-identical** on the same briefs before and after
  (`engines-{before,after}.json`); the only production file touched rebinds
  `_entrance_x_clear_of_parking` to the function moved into `site.py`.
* **The frozen regression corpus**, which is what `primary_signature_changes: none` is actually
  measured against: `TEST_MODE=REGRESSION pytest -q tests/regression_corpus` —
  **`856 passed in 5918.71s (1:38:38)`**, 0 failures, run at commit `3f8b0f1` with no commit made
  during the run (`corpus_snapshot` records `git rev-parse HEAD`). **No primary plan changed.** The
  only commit after it adds one test and this section — no product code was touched.

### The rest of the evidence

| suite | result |
|---|---|
| `backend/tests/demo/test_site_from_brief.py` | 17 passed |
| backend fast suite (`WALLCLOCK_BUDGETS=off pytest -q -n 4`) | 2463 passed, 883 skipped, 10 xfailed, 0 failed |
| frontend renderer (`npx vitest run src/design`) | 189 passed, 2 skipped |
| whole frontend suite (`npx vitest run`) | 242 passed, 2 skipped |
| regression corpus (`TEST_MODE=REGRESSION`) | 856 passed, 0 failed |

**CI did not run on this branch.** `.github/workflows/agent-ci.yml` gates every job on `head_ref`
starting with `agent/` or `integration/`, and #223 specified `feature/site-real-parcel`, so all five
gates reported `skipping`. The table above is the local equivalent, run in full.

## 6. The figures

`figures/site-parcel/site-parcel__before.png` and `..._after.png` — the same brief, the same parti
(`PUBLIC_BAND+FOYER`), the same rooms, drawn by `DemoPlan` + `PlanLegend` with the product's own
stylesheets.

* **before** — a pale rectangle hugging the house on two sides. No parcel, no garden, no bays; the
  legend has three entries. The walk stops 2 m from the door at the edge of a margin that looks
  exactly like a surveyed boundary.
* **after** — the client's 23 × 20 m parcel, the garden as the land genuinely left, the two bays
  they asked for at the street with the walk threaded between them, and a legend that now carries
  גינה and חניה. The plan inside the walls is the same drawing, pixel for pixel, moved.

Produced with #213's own rasteriser, copied unchanged: `backend/app/ai_harness/drawing_audit/`
(`rasterise.mjs`, `__init__.py`) and `frontend/src/design/drawing-audit-render.test.tsx`, from
`origin/investigate/preview-comparison`. #213's `run.py` and `comparison_corpus/` were **not**
copied — #223 measures the site from the payload directly and needs only the drawing. The brief and
the two payloads are `app/ai_harness/drawing_audit/figures_223.py`.

## 7. Out of scope, found while measuring

* **`classify_garden` leaves part of the street band unclassified.** It classifies the front strip
  only from the end of the parking row to the footprint's east edge, so land in the band east of the
  footprint is neither garden nor anything else — visible as the white strip top-right in the
  "after" figure. This is **production's own long-standing behaviour**, identical in both engines
  and untouched here, because changing it would change production's payload, which AC-5 forbids.
  Everything *behind* the building line is accounted for as house or garden, and the test asserts
  exactly that.
* **The brain's realized footprint can exceed the outline it was given** (15.30 m realized against a
  15.00 m outline on the headline brief). It still fits this parcel; a footprint that would not is
  now disclosed rather than clamped. Why the sizer exceeds the outline belongs to #197, not here.
