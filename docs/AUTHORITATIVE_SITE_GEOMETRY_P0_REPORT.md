# AUTHORITATIVE_SITE_GEOMETRY_P0_REPORT

```
SYNTHETIC_SITE_FROM_FOOTPRINT = REMOVED
TESTS = 719 backend (was 711, +8), 75 frontend (was 72, +3), tsc clean
```

The derivation now runs in the only honest direction. The parcel is the input; the buildable region
is what is left after subtracting stated assumptions from it; the footprint must fit inside that or
it is refused.

---

## The table

| site | setbacks (front/side/rear) | buildable region | requested footprint | result |
|---|---|---|---|---|
| 20 × 20 = 400 m² | 5.5 / 3.0 / 4.0 | 14.00 × 10.50 = 147.0 m² | 11.00 × 8.00 | planned |
| 20 × 24 = 480 m² | 5.5 / 3.0 / 4.0 | 14.00 × 14.50 = 203.0 m² | 11.00 × 12.00 | planned |
| 25 × 16 fronting **north** = 400 m² | 5.5 / 3.0 / 4.0 | 19.00 × 6.50 = 123.5 m² | 11.00 × 12.00 | **`FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION`** |
| 25 × 16 fronting **east** = 400 m² | 5.5 / 3.0 / 4.0 | 10.00 × 15.50 = 155.0 m² | 9.00 × 8.00 | planned |
| 16 × 25 fronting north = 400 m² | 5.5 / 3.0 / 4.0 | 10.00 × 15.50 = 155.0 m² | 11.00 × 10.00 | **`FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION`** |
| 20 × 20, relaxed **3 / 3 / 2** = 400 m² | 3.0 / 3.0 / 2.0 | 14.00 × 15.00 = 210.0 m² | 11.00 × 12.00 | planned |
| **your case** 15 × 20 = 300 m² | 5.5 / 3.0 / 4.0 | 9.00 × 10.50 = 94.5 m² | 17.23 × 12.77 | **`FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION`** |

Rows 3–5 are all 400 m². Same area, three different answers — that is the whole point of the change.
Row 6 is the same 400 m² parcel with corrected assumptions, and it plans: the setbacks are now a
lever the person holds rather than a constant they cannot see.

The last row is the case you reported. Previously it produced a plan on a synthesised 517 m² site;
it now says plainly that a 220 m² single-storey footprint does not fit on a 300 m² parcel under
these assumptions.

## SITE_MODEL

Rectangular parcel, one cardinal edge facing the street. `app/demo/site_geometry.py`:

```
SiteGeometry(plot_width_m, plot_depth_m, street_facing_side,
             canonical_width_m, canonical_depth_m,
             front_setback_m, side_setback_m, rear_setback_m)
```

`canonical_*` is the parcel in the engine's frame, where the street lies on the y=0 edge. An EAST or
WEST frontage swaps width and depth before the setbacks are applied — that is the entirety of P0's
orientation support, and it changes the answer materially (rows 3 and 4). `plot_*` keeps the numbers
the person actually typed, so the review screen shows those rather than the rotated ones.

No polygons, no corner lots, no angled frontage, no GIS, no regulation lookup. Anything outside the
model is refused, never approximated.

## AUTHORITATIVE_FIELDS

`Project.plot_width_m`, `Project.plot_depth_m`, `Project.street_facing_side` — collected on the
project form as two dimensions and a frontage. `plot_area_m2` remains, **derived from the dimensions
and displayed**, never entered separately.

They are optional on the model so projects stored before this existed still load and the legacy
`app/design` path is untouched; the **demo path refuses to plan without them**
(`SITE_GEOMETRY_REQUIRED`) rather than inventing a parcel, which is exactly what it used to do.

## SETBACK_SEMANTICS

**Explicit, editable demo assumptions.** `SetbackAssumptions{front_m, side_m, rear_m}` is stored per
project and correctable on the review screen, alongside:

> הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.

They are editable precisely because they are assumptions: nobody has verified them, and on a small
parcel they decide almost everything about what can be built. Keeping them fixed and invisible made
a demo-level guess look like a regulatory fact. A project with no stored assumptions falls back to
the module defaults (5.5 / 3.0 / 4.0) — still assumptions, still labelled.

They are applied **only by subtraction**. Nothing anywhere uses them to produce a site.

## BUILDABLE_REGION_DERIVATION

```
plot (authoritative)
  − setbacks (stated assumptions, edge-relative via street_facing_side)
  = buildable rectangle
  ⊇ selected footprint, placed centred and flush to the street edge
  = the BuildableRegion handed to the planner
```

Both containments are real, so the region the engine receives is a subset of land the person owns.
It used to be the footprint rectangle at an origin derived from a plot that had itself been computed
from that same footprint — which made the containment vacuous. Its provenance moved from
`Authority.ASSUMED` to `Authority.AUTHORITATIVE` accordingly.

## FOOTPRINT_FIT_BEHAVIOR

Checked in `scope.check_supported`, before any planning. On failure,
`FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` carries all three sets of numbers — plot, setbacks,
buildable, footprint — and names the shortfall ("2.00 m too wide and 5.50 m too deep").

**The site is not enlarged and the footprint is not shrunk.** The footprint is not silently rotated
either: a wide outline on a deep narrow plot is something the person chose, and turning it 90° would
be a different house from the one they picked.

## AREA_CONSISTENCY_BEHAVIOR

`_check_plot_area_consistent` on `ProjectCreate`: when both a `plot_area_m2` and dimensions are
supplied and they disagree beyond 1% (floor 0.5 m²), the request is **rejected** naming both values.
Neither is trusted, because guessing which one the person meant would plan on a parcel they never
described — the same class of mistake as synthesising a site from the building.

## UI_REVIEW_BEHAVIOR

The form collects **רוחב מגרש / עומק מגרש / איזו חזית פונה לרחוב** and shows the derived area. The
review screen shows, before Generate:

```
המגרש
  מידות              20.00 × 24.00 מ׳
  שטח                480.00 מ״ר
  חזית לרחוב          צפון
הנחות נסיגה לדמו     [חזית 5.5] [אחורית 4.0] [צדדים 3.0]     ← editable
  הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.
  אזור בנייה שנגזר    14.00 × 14.50 מ׳ (203.00 מ״ר)
  מתאר הבית שנבחר     11.00 × 12.00 מ׳
```

When the outline does not fit, that line reads **"— אינו נכנס בשטח שנותר לבנייה"** in the danger
colour, before the button is pressed.

## Failure wording

Every feasibility refusal now carries the required scoping, in both languages —
`_FEASIBILITY_CODES` in `service.py` appends it automatically, so it cannot be forgotten on a new
code:

- detail: `[not feasible under the current site geometry and setback assumptions]`
- message: *"לא ניתן לביצוע עם גאומטריית המגרש והנחות הנסיגה הנוכחיות. אין בכך קביעה שהתכנון בלתי אפשרי — שינוי מידות המגרש, הנסיגות או התוכנית עשוי לפתור זאת."*

Applied to `PLAN_NOT_REALIZABLE`, `PLAN_FAILED_VALIDATION`, `PLAN_OUTSIDE_BUILDABLE`,
`TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`, `CORRIDOR_WIDTH_NOT_FEASIBLE`,
`ROOM_RELATIONSHIP_NOT_FEASIBLE`, `FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` and
`SITE_GEOMETRY_REQUIRED`. Scope refusals that are about a malformed or unsupported *request* are
left alone — they are not feasibility statements.

## TEST_RESULTS

**719 backend, 75 frontend, tsc clean.** Eight new backend tests through the real path:

| Test | Case |
|---|---|
| A | 20 × 20 site, footprint fits → planned, buildable is exactly plot − setbacks |
| B | 25 × 16 site → refused, message carries all three dimension sets, no "impossible" claim |
| C | same 400 m² as 20×20 / 25×16 / 16×25 → one plans, two refuse |
| D | frontage NORTH vs EAST on 25 × 16 → 19.0 × 6.5 vs 10.0 × 15.5, and the same footprint fits one only |
| E | area 300 with dimensions 20 × 20 → 422, names both values |
| F | a project with area and no dimensions → `SITE_GEOMETRY_REQUIRED`, not an invented site |
| G | source scan: no demo/vertical-slice path derives a site from a footprint, and `derive()` has no footprint parameter at all |
| — | setbacks are editable and change what fits: 11 × 12 refused at 5.5/4, planned at 3.0/2.0 |

**The old fixtures were corrected, not preserved.** `_create` used to declare a flat
`plot_area_m2: 500` with no dimensions — including one case (15.5 × 15.5) that needed 538 m² and
nothing noticed. Every fixture now states a parcel that genuinely holds its house.

Three frontend tests cover the site panel, editing the assumptions through to Generate, and the
does-not-fit warning.

## FILES_CHANGED

**Backend:** `app/demo/site_geometry.py` (new), `app/demo/requirements_view.py`, `app/demo/scope.py`,
`app/demo/service.py`, `app/demo/router.py`, `app/projects/models.py`, `app/projects/repository.py`,
`tests/test_demo_p0.py`.

**Frontend:** `src/App.tsx`, `src/types.ts`, `src/design/ReviewPage.tsx`, `src/design/ReviewPage.css`,
`src/design/demoDesign.ts`, `src/App.test.tsx`, `src/design/DemoPlan.test.tsx`.

**Untouched, as instructed:** Geometry Core, the Safe Geometry Adapter, the Concept Generator,
corridor behaviour, room-relationship behaviour, validation semantics, built-area target behaviour.
The only integration change was the type of land handed to `run_general` — the same
`BuildableRegion`, now genuinely inside the parcel.

## SYNTHETIC_SITE_FROM_FOOTPRINT = REMOVED

Confirmed three ways: the code is gone (`grep` for the pattern returns zero on the demo path),
`site_geometry.derive` takes no footprint argument and so cannot be influenced by the building, and
`test_G_no_code_path_reconstructs_a_site_from_the_footprint` asserts both at the source.

---

## Known, and yours to decide

No multi-storey support was added, as instructed — so a 220 m² programme still needs roughly a
500 m² parcel at the default assumptions. The two levers now visible to the user are the setbacks
and the footprint; the third, a second storey, remains a capability decision.

Stopping for review.
