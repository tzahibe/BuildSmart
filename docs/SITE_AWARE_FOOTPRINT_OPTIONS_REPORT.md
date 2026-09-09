# SITE_AWARE_FOOTPRINT_OPTIONS_REPORT

```
FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION:  1032  ->  0
REACHED A DRAWING:                        10.9%  ->  31.1%   (157 -> 448 of 1440)
CRASHES:                                     0  ->  0
TESTS = 728 backend (+9), 77 frontend (+2), tsc clean
```

The footprint step used to offer four outlines derived from `built_area_m2` alone, knowing nothing
about the land. Every one of those 1032 refusals was somebody choosing an option **the system itself
had offered** and could already have known was impossible. Options now come from the buildable
region, so an impossible one is never on screen.

---

## 1440-scenario scan, before and after

| | before | after |
|---|---|---|
| **reached a drawing** | 157 (10.9%) | **448 (31.1%)** |
| `FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` | **1032** | **0** |
| `PLAN_NOT_REALIZABLE` | 243 | 566 |
| `BUILT_AREA_EXCEEDS_ONE_STOREY_CAPACITY` | — | 384 |
| `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` | 6 | 36 |
| `PLAN_FAILED_VALIDATION` | 2 | 6 |
| **crashes** | 0 | 0 |

Three of those rows need reading carefully, because two of them went **up**:

- **`FOOTPRINT_DOES_NOT_FIT` is gone from the flow entirely.** Not reduced — zero. It remains
  reachable only by submitting an outline the system never offered, which is now refused at
  creation rather than at generation.
- **`BUILT_AREA_EXCEEDS_ONE_STOREY_CAPACITY` (384) is not new infeasibility.** These are cases that
  previously appeared inside the 1032 as a refusal *after* choosing; they are the same houses that
  genuinely do not fit, now said **before** any choosing, with the capacity number attached.
- **`PLAN_NOT_REALIZABLE` rose from 243 to 566 because far more scenarios now reach the planner at
  all.** Roughly 650 scenarios that used to die at the footprint gate now get as far as planning,
  and 566 of them fail there. That is exposure, not regression — and it is the next problem, which
  this task deliberately did not touch.

Net: the number of people who see a drawing nearly tripled, and nobody is refused any more for a
choice the product handed them.

## Option-generation flow, before and after

**Before**

```
built_area_m2 ──► generateFootprintOptions(area)            [browser, knows nothing of the land]
              ──► four fixed aspect ratios 1.0 / 1.35 / 1.8 / 0.56
              ──► user picks one
              ──► POST /projects            (accepted whatever it was)
              ──► POST /design/demo         ──► FOOTPRINT_DOES_NOT_FIT   ← 80% of all failures
```

**After**

```
site (w, d, frontage) + setback assumptions
              ──► BuildableRegion = plot − setbacks           [backend, app/demo/site_geometry.py]
              ──► feasible_width_range(area)                   the widths at which THIS area fits
              ──► up to 4 outlines spread across that range    every one proven to fit
              ──► user picks one
              ──► POST /projects            (re-validated; an unoffered outline is refused here)
              ──► POST /design/demo
```

The mathematics is small and worth stating: a footprint of fixed area is the curve
`depth = area / width`; requiring `width ≤ BW` and `depth ≤ BD` turns it into the interval
`width ∈ [area / BD, BW]`. Empty interval means the area cannot fit in one storey at all, and no
proportion rescues it. Non-empty means a whole continuum fits — so the four offered outlines are
spread across it, **all at exactly the requested area**. Nothing is ever shrunk to make it fit.

## Max-capacity semantics

`one_storey_footprint_capacity_m2` is the **buildable rectangle's area and nothing more**, named in
the UI as *קיבולת מתאר גאומטרית לקומה אחת*.

It is deliberately **not** called a maximum house area. It is a geometric ceiling: the room
programme, minimum room dimensions, corridor width and the C1–C15 checks can all reduce what is
actually achievable below it — and the scan proves it, with 566 `PLAN_NOT_REALIZABLE` occurring
strictly inside this capacity. The screen says so in as many words:

> זו קיבולת גאומטרית בלבד — תוכנית החדרים, מידות מינימום ורוחב המסדרון עשויים להקטין אותה עוד.

## Zero-option behavior

When the interval is empty there are no cards at all, and the person sees, **before choosing**:
requested built area, plot dimensions, derived buildable dimensions, the one-storey geometric
capacity, and the disclaimer. Two actions are offered, and only two — *reduce the requested built
area* or *edit the setback assumptions*. A second storey is not offered, because it is not
implemented.

## Backend enforcement

Frontend filtering is not a guarantee — a stale page, a direct API call or a hand-edited payload can
all still submit an impossible outline. Three independent layers:

1. **Generation** — the options endpoint returns only fitting outlines, computed by the backend.
2. **Creation** — `POST /projects` re-checks the selected footprint against the buildable region and
   returns 422 `FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION`. **An impossible footprint can no longer be
   stored at all**, which is the earliest point the rule can be enforced.
3. **Generation-time** — `scope.check_supported` still checks, because the setbacks can be edited in
   review after creation and may invalidate a footprint that fitted when it was chosen.

Creation validates against the setback assumptions the person was actually shown: `ProjectCreate`
now accepts them, so a choice made under corrected assumptions is not refused against defaults the
person had already replaced.

## UI behavior

The form's site fields feed `POST /projects/site/footprint-options` on the way to the footprint step.
The grid renders exactly what comes back — where the site is generous four genuinely different
proportions, where it is tight one or two, where nothing fits none plus the explanation above.
Options are labelled by the shape that **resulted** (NARROW / COMPACT / BALANCED / WIDE) rather than
from a fixed catalogue, because on a constrained site the offered proportions are whatever fits.

The custom entry is validated against the buildable rectangle too and says which dimension is the
problem, rather than accepting an entry the backend will refuse.

## Tests

Nine new backend tests through the real API:

| Test | Case |
|---|---|
| every offered option fits the buildable region | the core invariant |
| offered options never reduce the requested area | the area is not silently shrunk to fit |
| variety is preserved where the site allows it | a generous site still spans real proportions |
| a tight site offers fewer options rather than impossible ones | graceful narrowing |
| nothing fits is said before choosing, with the capacity named | pre-selection outcome, all four numbers |
| the capacity is geometric | equals the buildable rectangle, not a promise |
| relaxing the assumptions changes which options exist | the lever works |
| the backend refuses an outline it never offered | client filtering is not the guarantee |
| **an offered option is always accepted end to end** | the contract that makes the refusal disappear |

Four earlier tests were rewritten rather than preserved: they asserted the refusal arrives at
*generation*, and it now arrives at *creation*. That is the "surface it earlier" the task asked for,
so the tests moved with the behaviour.

Two frontend tests were updated for the backend-sourced options; the App fetch mock now serves the
new endpoint.

---

## Not addressed, by instruction

`PLAN_NOT_REALIZABLE` — 566 cases, now the dominant failure and concentrated in 3-bedroom
programmes with a safe room. Geometry Core, the Concept Generator and multi-storey support were all
left untouched.

Stopping for review.
