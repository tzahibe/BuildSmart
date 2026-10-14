# Gate 3 — day 5 verdict: **STOP at the time-box** — a working shape-agnostic realizer for three of five footprint classes, quality below the bar, two costed paths forward

> **Correction (2026-10-14, day-2 of path B — see `DAY-2-spine-gate.md`):** the F2/F4 refusals attributed below to the band family's exposure/entrance limit were, for every candidate that survived selection, a **harness defect**: frozen-six v1.1's `access_extra` KITCHEN–LIVING duplicated the parti's LIVING–KITCHEN door, two doors overlapped, C28 refused. With one door per unordered pair the band family alone solves F2 (TWO_HALL) and F4; the spine family adds F1/F3/F4. The cases are unchanged. The STOP verdict's *quality* findings stand.


Every number here is read off the product's own `DemoDesign` payload (`profile_designs.py`) or
the harness's `results.json`, for plans that passed the 28 unchanged validators with every
contact and door preserved.

## 1. The Gate-3 axes on the solved cases (aligned oracle + area objective, commit below)

| plan | gross | area verdict | circ m² (share) | circ aspect | worst wet aspect | smallest bedroom | no window | arrival | wings |
|---|---:|---|---:|---:|---:|---:|---|---|---:|
| F1-rect-control__BEDROOM_WING+FOYER | 83.5 % | BELOW_TARGET_DISCLOSED | 31.3 (0.188) | 2.43 | 2.03 | 9.1 | — | LIVING | 3 |
| F1-rect-control__BEDROOM_WING | 75.6 % | BELOW_TARGET_DISCLOSED | 12.0 (0.08) | 2.38 | 2.18 | 13.2 | — | LIVING | 3 |
| F1-rect-control__HALL_SPINE+FOYER | 74.7 % | BELOW_TARGET_DISCLOSED | 22.6 (0.152) | 2.17 | 2.08 | 9.6 | — | LIVING | 3 |
| F1-rect-control__HALL_SPINE | 72.2 % | BELOW_TARGET_DISCLOSED | 22.6 (0.157) | 1.02 | 2.19 | 9.8 | — | LIVING | 3 |
| F1-rect-control__PUBLIC_BAND+FOYER | 65.6 % | BELOW_TARGET_DISCLOSED | 25.2 (0.195) | 2.32 | 2.18 | 9.6 | — | LIVING | 3 |
| F1-rect-control__PUBLIC_BAND | 70.8 % | BELOW_TARGET_DISCLOSED | 16.3 (0.116) | 1.41 | 2.17 | 9.8 | — | LIVING | 3 |
| F1-rect-control__TWO_HALL+FOYER | 80.8 % | BELOW_TARGET_DISCLOSED | 37.1 (0.23) | 2.37 | 2.09 | 9.1 | — | CIRCULATION | 4 |
| F1-rect-control__TWO_HALL | 71.9 % | BELOW_TARGET_DISCLOSED | 20.1 (0.141) | 1.88 | 2.17 | 10.2 | — | LIVING | 3 |
| F3-wide-shallow-free__SERVICE_CORE | 108.0 % | WITHIN_TOLERANCE | 27.0 (0.158) | 3.0 | 1.94 | 9.1 | — | LIVING | 3 |
| F5-garden-court__BEDROOM_WING | 80.0 % | BELOW_TARGET_DISCLOSED | 18.5 (0.14) | 1.25 | 2.02 | 12.3 | — | HALL | 2 |
| F5-garden-court__PUBLIC_BAND | 66.2 % | BELOW_TARGET_DISCLOSED | 12.5 (0.116) | 1.65 | 2.06 | 13.9 | — | LIVING | 4 |
| F5-garden-court__TWO_HALL+FOYER | 65.8 % | BELOW_TARGET_DISCLOSED | 22.3 (0.209) | 2.12 | 1.26 | 9.0 | — | CIRCULATION | 3 |

**Latency:** F1 7.4 s (8 plans, 8 distinct footprints), F3 17.8 s, F5 7.2 s — all under the 30 s
target. **Refusals:** F6 typed in 0.0 s; F2/F4 typed at selection / oracle / validators.
**Diversity:** 8 distinct footprints on the rectangle control, 3 on the garden court.

## 2. The area objective, measured (before = feasibility program, after = width × mid-height proxy)

| case / parti | before | after |
|---|---:|---:|
| F1 BEDROOM_WING | 79.4 % | 75.6 % |
| F1 BEDROOM_WING+FOYER | 77.3 % | 83.5 % |
| F1 HALL_SPINE | 68.3 % | 72.2 % |
| F1 HALL_SPINE+FOYER | 65.6 % | 74.7 % |
| F1 PUBLIC_BAND | 68.3 % | 70.8 % |
| F1 PUBLIC_BAND+FOYER | 63.9 % | 65.6 % |
| F1 TWO_HALL | 61.8 % | 71.9 % |
| F1 TWO_HALL+FOYER | — | 80.8 % |
| F3 SERVICE_CORE | 95.8 % | **108.0 %** (`WITHIN_TOLERANCE`) |
| F5 BEDROOM_WING | 80.0 % | 80.0 % |
| F5 PUBLIC_BAND | 72.2 % | 66.2 % |
| F5 TWO_HALL+FOYER | 63.9 % | 65.8 % |

Mean gross 72.4 % → 76.3 %; one more plan. Two plans got *worse*: the proxy weights width by a
fixed mid-grid height, so the solver can trade height for width. The sound objective puts the
selected heights into the area term (per-candidate width copies) — about a day, not done.

## 3. What the renders show (`figures/area-objective/`) — the poor ones named

- **F3 SERVICE_CORE** — the strip solved as a stepped three-band house: every bedroom and the safe
  room on an exterior wall, the wet core grouped at the street as the parti intends, 108 % of the
  request. Poor: a **9.0 × 3.0 m hall (27 m², 3.0 : 1)** — circulation is still the sink; three
  bedrooms at **9.1 m²** (their minimum); dimension labels overflow the 1.6 m-wide wet rooms.
- **F1 TWO_HALL+FOYER** — four wings, 80.8 %, but **37 m² of circulation (23 %)**: the second
  corridor plus the foyer. Valid, not credible.
- **F1 BEDROOM_WING** — the best of the control: 12 m² circulation (8 %), bedrooms 13.2 m²+, flush
  rectangle, 75.6 %.
- **F5 BEDROOM_WING** — a 16 × 9 m house above the court arriving at the hall, 80 %, bedrooms
  12.3 m²+: the most house-like plan of the spike.
- F5 PUBLIC_BAND / TWO_HALL+FOYER — stepped, 66 %: too small for the request, honestly disclosed.

## 4. Verdict

**STOP this spike at the time-box, as the contract says.** What exists is a shape-agnostic
realizer in the exact sense the ADR defined: one IR, one algorithm, an envelope polygon, no shape
named anywhere, the downstream unchanged — and it produces valid, graph-preserving, rendered plans
on rectangles, strips and courts, with typed refusals elsewhere. It is **not** a customer-credible
planner yet: area 66–83 % on most plans, circulation 8–23 %, bedrooms at minimum. And it does not
reach the L and the street-side court, because one row of full-depth rooms per band cannot meet
the product's exposure and entrance rules for 12–13-room programmes.

## 5. Paths forward, with cost

| path | what it buys | cost | risk |
|---|---|---|---|
| **A1. Heights in the objective** (per-candidate width copies in the MILP) | area toward the request, circulation back to its target; the quality bar on F1/F3/F5 | ~1 day | none structural; the MILP stays ~1 s |
| **A2. Exposure-aware embedding** (ask `embed_band` for candidates with REQUIRED-exposure rooms in outer bands / band ends) | fewer of the 1 240 selection rejections on F2/F4; maybe F4 | ~1 day | may still leave F2 (entrance) |
| **B. 2D wing per band** (`GridWing` + `solve_band_sizing` per wing, staircase between wings; wing grouping decision) | F2/F4-class programmes: interior rooms get a second edge, the hub hall a street-side neighbour | 2–3 days | the oracle must learn 2D wings too |
| **C. Ship the oracle** | `scipy` as a declared production dependency (free library; an owner decision) | hours | adds ~30 MB to the backend environment |

No merge, deploy, live change or spend was made in the five days; `realize_layout` and every
validator are byte-unchanged; production remains behind the default-off flag.
