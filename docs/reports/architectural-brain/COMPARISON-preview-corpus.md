# Production vs the Architectural Brain on 26 briefs, drawn by the product's own renderer

**Issue #213** (child of ROOT #211, §3 of the owner's 2026-10-19 directive). Branch
`investigate/preview-comparison`, from `main` at `5b155d1`.
**Measurement only — no product code changed.** Everything new lives in `app/ai_harness/` and this
report.

> **Read this before the tables.** Both engines pass every validator on every brief that plans.
> **That proves nothing about architectural quality** and is not offered as evidence of it. The
> validators are a floor (no overlaps, every room reachable, doors fit, wet-room rules, MAMAD on an
> envelope wall); a plan can clear all of them and still be a plan no architect would present. The
> objective section below is facts; the judgments are in their own section, labelled as judgments,
> each tied to a figure, and they are mine, not the validators'.

---

## 1. What ran, and what drew the figures

| | |
|---|---|
| engines | one function, `app.demo.service.generate_demo_design` — the exact function `POST /projects/{id}/design/demo` calls. `brain=True` is exactly what `?engine=brain` sets (`demo/router.py:_brain_requested`). Neither pipeline is re-implemented in the harness. |
| brain configuration | the committed preview default: `service.BRAIN_SIZER = "exact"`, `service.BRAIN_FAMILIES = ("band", "spine", "stack", "cells")`, 30 s request budget (`brain/runner.py:REQUEST_BUDGET_S`) |
| payload | the product's own `DemoDesign` (`demo/contract.py:to_demo_design`), saved verbatim per plan |
| **figures** | **the product renderer.** `frontend/src/design/DemoPlan.tsx` and `PlanLegend.tsx` are mounted on each payload (`frontend/src/design/drawing-audit-render.test.tsx`), and the resulting SVG is rasterised in chromium with the product's own stylesheets (`app/ai_harness/drawing_audit/rasterise.mjs`). **No harness drawer was used anywhere in this report.** The caption burned into each figure is its payload's filename, so any figure can be traced to its data. |
| legibility numbers | measured in that same browser pass from the rendered text boxes (`getBBox`, SVG user units = plan metres) — not estimated from string lengths |
| cost | $0. No model call, no API key, no network (`docs/reports/architectural-brain/README.md`). |
| data | `data/comparison-corpus/results.json` (every measured value), `designs/` (50 payloads), `label-metrics.json`, `run.log` |
| figures | `figures/comparison-corpus/<brief>__{production,brain}.png` — 50 plans |
| reproduce | `uv run python -m app.ai_harness.comparison_corpus.run <out>` · render with `DRAWING_AUDIT_DESIGNS_DIR=<out>/designs npx vitest run src/design/drawing-audit-render.test.tsx` · `node app/ai_harness/drawing_audit/rasterise.mjs <svg> <png> <frontend> <out>/designs` · tables with `python -m app.ai_harness.comparison_corpus.report <out>` |

**One brief, one run, one machine.** Every number below is a single measurement, not a mean over
repeats; the seconds column in particular is wall-clock on a loaded laptop and should be read as an
order of magnitude.

---

## 2. The corpus — 26 briefs, and where each came from

Two sources, and the difference between them is itself a finding.

* **20 real briefs** — `app/ai_harness/topology_poc/briefs.py` (`select_briefs()`, the deterministic
  selection off the real corpus). These are what the product can actually receive, and **every one
  of them is a rectangle**, because `Project.selected_footprint` is a width × depth pair and
  `demo/scope.py:362` refuses any `shape_type` other than `RECTANGLE`.
* **6 frozen cases** — `docs/reports/shape-agnostic-realizer/cases/frozen-six.json`, declared before
  any spike code was written. These carry the repo's **only** non-rectangular envelopes (L, wide
  shallow strip, entry-court notch, garden court).

**Envelope families and the honest gap.** The rectangle families (square, rectangular, wide,
narrow/constrained) are covered by real briefs. **The L, courtyard and irregular-rectilinear
families exist only as frozen polygon cases, and the product cannot be handed one of them at all**
— so for F2/F4/F5 this report measures both engines on the case's *bounding rectangle*, which is
what a user asking for that site receives today, and records the polygon refusal separately
(§5). A rectangle is never silently substituted for a shape that failed.

| brief | source | envelope family | envelope | programme | requested m² |
|---|---|---|---|---|---:|
| B01 | `topology_poc/briefs.py` | rectangular/square | 20.0 x 22.0 | 1bd / 1wet | 440 |
| B02 | `topology_poc/briefs.py` | rectangular | 12.0 x 18.0 | 1bd / 1wet / open | 216 |
| B03 | `topology_poc/briefs.py` | rectangular/wide | 19.05 x 13.12 | 2bd / 1wet | 250 |
| B04 | `topology_poc/briefs.py` | rectangular/square | 20.0 x 22.0 | 2bd / 2wet / ממ״ד | 440 |
| B05 | `topology_poc/briefs.py` | rectangular/square | 16.0 x 18.0 | 2bd / 1wet / open | 288 |
| B06 | `topology_poc/briefs.py` | narrow/constrained | 13.0 x 24.0 | 3bd / 2wet | 312 |
| B07 | `topology_poc/briefs.py` | rectangular/square | 18.0 x 20.0 | 3bd / 2wet / ממ״ד | 360 |
| B08 | `topology_poc/briefs.py` | rectangular/square | 11.0 x 12.0 | 3bd / 1wet / open | 132 |
| B09 | `topology_poc/briefs.py` | rectangular/square | 20.0 x 22.0 | 3bd / 3wet | 440 |
| B10 | `topology_poc/briefs.py` | rectangular/square | 16.0 x 18.0 | 4bd / 2wet | 288 |
| B11 | `topology_poc/briefs.py` | rectangular | 12.0 x 18.0 | 4bd / 2wet / ממ״ד / open | 216 |
| B12 | `topology_poc/briefs.py` | rectangular/square | 18.0 x 20.0 | 4bd / 3wet | 360 |
| B13 | `topology_poc/briefs.py` | rectangular/square | 11.0 x 12.0 | 4bd / 2wet / open | 132 |
| B14 | `topology_poc/briefs.py` | rectangular | 12.0 x 18.0 | 5bd / 3wet | 216 |
| B15 | `topology_poc/briefs.py` | rectangular/square | 12.5 x 14.5 | 5bd / 2wet / ממ״ד | 181 |
| B16 | `topology_poc/briefs.py` | rectangular/wide | 18.0 x 12.0 | 5bd / 3wet / ממ״ד / open | 216 |
| B17 | `topology_poc/briefs.py` | rectangular/wide | 18.0 x 12.0 | 6bd / 3wet | 216 |
| B18 | `topology_poc/briefs.py` | rectangular/square | 12.5 x 14.5 | 6bd / 3wet / ממ״ד | 181 |
| B19 | `topology_poc/briefs.py` | rectangular/square | 12.5 x 14.5 | 6bd / 2wet / open | 181 |
| B20 | `topology_poc/briefs.py` | rectangular/square | 11.0 x 12.0 | 2bd / 3wet / ממ״ד / open | 132 |
| F1-rect-control | `shape-agnostic-realizer/cases/frozen-six.json` | rectangular | polygon, bbox 12.0 x 18.0 | 4bd / 2wet | 216 |
| F2-L-envelope-fixed | `shape-agnostic-realizer/cases/frozen-six.json` | L-shaped | polygon, bbox 14.0 x 16.0 | 4bd / 3wet / ממ״ד | 190 |
| F3-wide-shallow-free | `shape-agnostic-realizer/cases/frozen-six.json` | narrow/constrained | polygon, bbox 24.0 x 9.5 | 5bd / 3wet / ממ״ד / open | 175 |
| F4-entry-court-notch | `shape-agnostic-realizer/cases/frozen-six.json` | irregular rectilinear | polygon, bbox 17.0 x 16.0 | 5bd / 3wet / ממ״ד | 215 |
| F5-garden-court | `shape-agnostic-realizer/cases/frozen-six.json` | U-shaped/courtyard | polygon, bbox 16.0 x 15.0 | 3bd / 2wet / open | 180 |
| F6-unsatisfiable-K4 | `shape-agnostic-realizer/cases/frozen-six.json` | rectangular | polygon, bbox 13.0 x 17.0 | 3bd / 2wet / ממ״ד | 200 |


**Coverage against #213's list:** rectangular/square ✅ (9 real briefs) · rectangular ✅ (4) ·
rectangular/wide ✅ (3) · narrow/constrained ✅ (B06 13 × 24, plus the F3 strip) · L-shaped ⚠️ (F2
only, polygon — the product takes its bounding box) · U-shaped/courtyard ⚠️ (F5 only, same) ·
irregular rectilinear ⚠️ (F4 only, same) · **B16, B19, B09 all present with their real outcome**
(§3, §6).

---

## 3. Objective facts

Read off the payloads and the rendered drawings. No judgment here; no "better" column.

| brief | engine | gross m² | % of request | net m² | circ. share | worst bed aspect | no-window rooms | validators | label collisions | labels outside room | s |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| B01 | production | 151 | 34% | 139 | 10.3% | 2.37 | 0 | all 27 pass | 1 | 1 | 0.9 |
| B01 | brain | 125 | 28% | 115 | 9.9% | 2.22 | 0 | all 28 pass | 0 | 0 | 31.0 |
| B02 | production | 135 | 63% | 126 | 11.5% | 2.38 | 0 | all 27 pass | 1 | 1 | 4.1 |
| B02 | brain | 153 | 71% | 142 | 10.3% | 2.30 | 0 | all 27 pass | 0 | 0 | 34.1 |
| B03 | production | 181 | 72% | 168 | 9.9% | 1.59 | 0 | all 27 pass | 0 | 1 | 1.2 |
| B03 | brain | 139 | 56% | 128 | 9.3% | 1.27 | 0 | all 28 pass | 0 | 0 | 28.1 |
| B04 | production | 187 | 42% | 170 | 8.4% | 1.94 | 0 | all 27 pass | 0 | 2 | 1.9 |
| B04 | brain | 179 | 41% | 163 | 14.0% | 1.98 | 0 | all 28 pass | 0 | 1 | 31.9 |
| B05 | production | 196 | 68% | 184 | 10.2% | 2.12 | 0 | all 27 pass | 0 | 1 | 1.8 |
| B05 | brain | 174 | 61% | 162 | 9.4% | 1.72 | 0 | all 28 pass | 0 | 1 | 32.4 |
| B06 | production | 177 | 57% | 163 | 10.7% | 1.98 | 0 | all 27 pass | 1 | 1 | 1.0 |
| B06 | brain | 165 | 53% | 153 | 12.0% | 2.23 | 0 | all 27 pass | 0 | 1 | 32.0 |
| B07 | production | 161 | 45% | 145 | 11.0% | 1.70 | 0 | all 27 pass | 0 | 2 | 12.3 |
| B07 | brain | 179 | 50% | 162 | 19.7% | 2.06 | 0 | all 28 pass | 0 | 1 | 43.5 |
| B08 | production | 130 | 98% | 119 | 12.7% | 1.33 | 0 | all 27 pass | 2 | 2 | 0.4 |
| B08 | brain | 131 | 100% | 120 | 14.1% | 1.60 | 0 | all 28 pass | 0 | 2 | 30.5 |
| B09 | production | 227 | 52% | 211 | 8.9% | 1.87 | 0 | all 27 pass | 0 | 2 | 2.0 |
| B09 | brain | 179 | 41% | 165 | 14.9% | 2.46 | 0 | all 27 pass | 0 | 2 | 32.0 |
| B10 | production | 214 | 74% | 198 | 9.6% | 1.84 | 0 | all 27 pass | 1 | 1 | 1.6 |
| B10 | brain | 198 | 69% | 184 | 17.3% | 1.21 | 0 | all 27 pass | 0 | 2 | 31.7 |
| B11 | production | 167 | 77% | 151 | 10.9% | 1.51 | 0 | all 27 pass | 0 | 2 | 15.9 |
| B11 | brain | 170 | 79% | 154 | 19.4% | 2.46 | 0 | all 27 pass | 1 | 4 | 46.1 |
| B12 | production | 212 | 59% | 196 | 9.2% | 1.88 | 0 | all 27 pass | 1 | 1 | 1.7 |
| B12 | brain | 186 | 52% | 171 | 14.4% | 1.55 | 0 | all 27 pass | 0 | 2 | 34.0 |
| B13 | production | 131 | 99% | 120 | 12.7% | 1.26 | 0 | all 27 pass | 1 | 2 | 0.2 |
| B13 | brain | 144 | 109% | 131 | 15.5% | 1.46 | 0 | all 27 pass | 0 | 3 | 30.4 |
| B14 | production | 145 | 67% | 131 | 15.0% | 1.98 | 0 | all 27 pass | 2 | 2 | 11.7 |
| B14 | brain | 184 | 85% | 169 | 18.7% | 1.83 | 0 | all 27 pass | 2 | 5 | 41.7 |
| B15 | production | 165 | 91% | 148 | 11.5% | 1.94 | 0 | all 27 pass | 1 | 2 | 1.2 |
| B15 | brain | 178 | 98% | 161 | 17.1% | 1.51 | 0 | all 27 pass | 2 | 6 | 31.5 |
| B16 | production | 188 | 87% | 170 | 10.1% | 2.28 | 0 | all 27 pass | 1 | 2 | 13.1 |
| B16 | brain | 213 | 99% | 194 | 13.5% | 1.88 | 0 | all 27 pass | 1 | 4 | 50.0 |
| B17 | production | 179 | 83% | 164 | 11.7% | 2.25 | 0 | all 27 pass | 1 | 2 | 16.6 |
| B17 | brain | 188 | 87% | 173 | 20.9% | 1.83 | 0 | all 27 pass | 2 | 5 | 44.7 |
| B18 | production | 169 | 94% | 151 | 9.6% | 1.87 | 0 | all 27 pass | 3 | 2 | 8.6 |
| B18 | brain | 197 | 109% | 179 | 16.5% | 2.12 | 0 | all 27 pass | 0 | 6 | 45.6 |
| B19 | production | 173 | 95% | 159 | 8.4% | 2.04 | 0 | all 27 pass | 3 | 3 | 1.1 |
| B19 | brain | 182 | 101% | 168 | 12.8% | 2.39 | 0 | all 27 pass | 2 | 3 | 31.9 |
| B20 | production | 131 | 99% | 117 | 12.0% | 1.43 | 0 | all 27 pass | 1 | 2 | 0.2 |
| B20 | brain | 133 | 101% | 119 | 15.8% | 1.22 | 0 | all 27 pass | 2 | 3 | 30.8 |
| F1-rect-control | production | 184 | 85% | 169 | 11.6% | 1.79 | 0 | all 27 pass | 1 | 2 | 0.8 |
| F1-rect-control | brain | 198 | 92% | 184 | 17.3% | 1.21 | 0 | all 27 pass | 0 | 2 | 31.0 |
| F2-L-envelope-fixed | production | 160 | 84% | 143 | 12.1% | 2.21 | 0 | all 27 pass | 2 | 2 | 3.5 |
| F2-L-envelope-fixed | brain | 191 | 101% | 174 | 18.9% | 2.35 | 0 | all 27 pass | 1 | 5 | 34.4 |
| F3-wide-shallow-free | production | **PLAN_NOT_REALIZABLE** | | | | | | | | | 4.8 |
| F3-wide-shallow-free | brain | **PLAN_NOT_REALIZABLE** | | | | | | | | | 4.8 |
| F4-entry-court-notch | production | 158 | 74% | 141 | 10.4% | 1.92 | 0 | all 27 pass | 2 | 2 | 16.4 |
| F4-entry-court-notch | brain | 194 | 90% | 177 | 20.5% | 1.83 | 0 | all 27 pass | 1 | 6 | 46.7 |
| F5-garden-court | production | 179 | 100% | 167 | 9.8% | 1.87 | 0 | all 27 pass | 1 | 2 | 2.6 |
| F5-garden-court | brain | 195 | 108% | 181 | 16.6% | 2.08 | 0 | all 28 pass | 0 | 1 | 34.8 |
| F6-unsatisfiable-K4 | production | 202 | 101% | 184 | 14.6% | 2.06 | 0 | all 27 pass | 0 | 2 | 1.6 |
| F6-unsatisfiable-K4 | brain | 197 | 99% | 181 | 17.3% | 2.23 | 0 | all 27 pass | 2 | 2 | 33.3 |


**What the columns are.** *gross m²* `DemoDesign.gross_area_m2`; *% of request* gross over the
brief's `built_area_m2`; *net m²* the sum of the rooms' usable areas; *circ. share* circulation net
over total net; *worst bed aspect* the longest/shortest side of the worst bedroom; *no-window rooms*
habitable rooms with no window (halls are excluded — circulation has window policy NONE in
production by design); *validators* the per-check dict the payload already carries; *label
collisions* / *labels outside room* measured in the browser as described in §1; *s* wall-clock for
the whole request.

### 3.1 Aggregates over the 25 briefs both engines planned

| fact | production | brain |
|---|---|---|
| area delivered, median \|% − 100\| | 22.6 pts | **12.9 pts** |
| circulation share, median (max) | **10.7 % (15.0 %)** | 15.8 % (20.9 %) |
| circulation area, median (max) | **16.6 m² (26.9 m²)** | 26.2 m² (36.3 m²) |
| circulation room aspect, median (max), all circulation rooms | 10.35 (12.0) — **25 of 25 above 4** | **1.91 (3.0) — 0 of 47 above 4** |
| arrival room: short side, median (min) | 1.30 m (1.20 m) | **1.90 m (1.50 m)** |
| arrival room: aspect, median (max) | 10.35 (12.0) — **22 of 25 above 3** | **1.62 (2.50) — 0 of 25 above 3** |
| circulation with no exterior wall (landlocked) | **0 of 25** | 19 of 25 |
| ≥ 1 public room reaching the garden (south) facade | 2 of 25 | **16 of 25** |
| open-plan briefs drawn with open interfaces | **9 of 9** | **0 of 9** |
| windows on the street (north) facade, total | **19** | 49 |
| plans with no window at all on the garden facade | 5 of 25 | 4 of 25 |
| worst bedroom aspect, median | 1.92 | 1.88 |
| biggest wet room, median (max) | **9.4 m² (13.2 m²)** | 11.0 m² (13.9 m²) |
| label collisions, total | 26 | **16** |
| label blocks outside their own room, total | **44** | 67 |
| alternatives offered | 0 on 9 briefs, 1 on 9, 2 on 7 | **2 on 22 briefs**, 1 on 2, 0 on 1 |
| request time, median (max) | **1.8 s (16.6 s)** | 32.4 s (50.0 s) |

### 3.2 The site, as each engine hands it to the drawing

The site drawing is not decoration: it is what tells a reader where the house sits on the parcel,
where the garden is and how one arrives. The two engines do **not** hand the renderer the same kind
of object.

| brief | engine | parcel drawn (m) | garden regions | parking bays | entrance walk (m) | footprint wings | open interfaces | cased openings |
|---|---|---|---:|---:|---:|---:|---:|---:|
| B01 | production | 28.0 x 30.0 | 3 | 0 | 0.0 | 1 | 0 | 1 |
| B01 | brain | 23.6 x 14.3 | 1 | 0 | 2.0 | 2 | 0 | 0 |
| B02 | production | 20.0 x 26.0 | 3 | 0 | 0.0 | 1 | 7 | 0 |
| B02 | brain | 16.2 x 16.6 | 0 | 0 | 2.0 | 1 | 0 | 0 |
| B03 | production | 27.1 x 21.1 | 3 | 0 | 0.0 | 1 | 0 | 1 |
| B03 | brain | 20.8 x 12.8 | 0 | 0 | 2.0 | 2 | 0 | 0 |
| B04 | production | 28.0 x 30.0 | 3 | 0 | 0.0 | 1 | 0 | 1 |
| B04 | brain | 18.4 x 19.6 | 0 | 0 | 2.0 | 4 | 0 | 0 |
| B05 | production | 24.0 x 26.0 | 3 | 0 | 0.0 | 1 | 7 | 0 |
| B05 | brain | 20.0 x 14.9 | 0 | 0 | 2.0 | 2 | 0 | 0 |
| B06 | production | 21.0 x 32.0 | 3 | 0 | 0.0 | 1 | 0 | 1 |
| B06 | brain | 16.9 x 16.9 | 0 | 0 | 2.0 | 1 | 0 | 0 |

*(full table for all 25 briefs in `data/comparison-corpus/results.json` + `designs/`; the pattern
above is uniform across the corpus)*

**The fact, stated plainly:** for **every** brain plan the parcel that gets drawn is not the
person's parcel. `rectilinear_realizer.py:1379` (`_build_site`, used by both of the brain's
realizers) synthesises `plot = footprint + 2 m`, sets `parking=()` unconditionally, and classifies
as garden only the *crook between wings* — never the remainder of the real plot. Production uses
`vertical_slice/site.py`, which places the house on the parcel the person entered, classifies the
leftover as garden and lays out the parking bays and the entrance walk from the street.

### 3.3 Which layout family the preview actually shows

`BRAIN_FAMILIES` enables band, spine, stack and cells. **In 25 of 25 briefs the plan the preview
shows first came from the `band` family.** The cross-band families are reachable — forcing a single
family (`app/ai_harness/drawing_audit/`) produces valid, renderable spine, stack and cells plans,
and on B08 a `stack` plan appeared as the first alternative — but at the committed 30 s budget they
do not win the brain's own ranking on real briefs. The cross-band work is enabled and, in practice,
nearly inert.

---

## 4. The drawing matrix — can the product draw what the brain plans?

"Cannot draw" is a legitimate result, so it is recorded as one. Evidence: **56 payloads** built
through the product path and rendered (the 50 corpus plans plus the per-family payloads of
`app/ai_harness/drawing_audit/`), checked mechanically for the facts the renderer draws from.

| shape / layout family | payload | walls | doors | windows | room labels | dimensions | legend | site |
|---|---|---|---|---|---|---|---|---|
| **band**, rectangular envelope | draws (25/25) | draws | draws | draws | **wrong** ¹ | partial ² | draws | **wrong** ³ |
| **spine** (corridor cell spanning rows) | draws | draws | draws | draws | **wrong** ¹ | partial ² | draws | **wrong** ³ |
| **stack** (two rooms in one column) | draws | draws | draws | draws | **wrong** ¹ | partial ² | draws | **wrong** ³ |
| **cells** (a room two rows deep) | draws | draws | draws | draws | **wrong** ¹ | partial ² | draws | **wrong** ³ |
| **merged L room** (`shape="L"`, `polygon_m`, #118) | draws | draws | draws | draws | draws ⁴ | partial ² | draws | **wrong** ³ |
| **open-plan semantics** (any family) | draws | **wrong** ⁵ | **wrong** ⁵ | draws | draws | partial ² | **wrong** ⁶ | — |
| **non-rect envelope** (L / court / notch) | **cannot** ⁷ | — | — | — | — | — | — | — |
| *same, through the harness path* | draws ⁸ | draws | draws | draws | **wrong** ¹ | partial ² | draws | partial ⁹ |

1. **Labels leave their room.** Measured, not eyeballed: 67 label blocks sit outside the room they
   belong to across the brain's 25 plans (production 44), overflowing by up to **1.05 m**
   (`B20__brain`, the master bedroom's block) and 1.02 m (`F2 … TWO_HALL`). 16 label pairs overlap
   each other (production 26). The mechanism is `demoRoomLabel.ts` rotating and offsetting a block
   that does not fit, with no clamp to the room's own rectangle. Figures: `B15__brain.png`,
   `B18__brain.png`, `F4-entry-court-notch__brain.png` (6 escaped blocks each).
2. **Dimensions: per room only.** Both engines print each room's `w × d` and area, window widths
   and a scale bar; **neither draws an overall building dimension string**, which the reference set
   (`product-readiness-audit/reference-sources.md`, §A) puts *inside* concept-stage scope. Equal for
   both engines, so it is not a brain defect — it is a product gap.
3. **The site is fabricated** — §3.2. A 2 m skirt instead of the parcel, no parking bays, garden
   only in a wing crook. `rectilinear_realizer.py:1379`.
4. The merged L room draws correctly: `DemoPlan.tsx:135` fills its `polygon_m`, and its label
   centres on the polygon's **area centroid**, not the bbox centre, so it cannot land in the crook.
5. **Every room-to-room boundary is a wall with a door.** In 56/56 payloads the brain produced
   **zero** `CASED_OPENING` doors and **zero** open interfaces. Cause, exactly: in
   `rectilinear_realizer.realize_cells` the set `open_pairs` is created empty at **line 1263** and
   never added to (the comment at line 1273 says so: *"OPEN (none here)"*), so `design.open_groups`
   is empty (line 1329). `realize_layout`, which the brain's production-sizer path uses, only ever
   opens seams between cells of the **same** zone (line 1448) — never living-to-kitchen. Because
   `open_groups` is empty, the contract's own corridor-opening post-process
   (`demo/contract.py:975`) can never fire either.
6. The legend is honest about the payload it is given — which is why the brain's figures have no
   *"מעבר פתוח — אין קיר כלל"* row and usually no *"גינה"* row. The legend is right; the payload is
   impoverished.
7. **Cannot build.** There is nowhere to put an orthogonal polygon: `Project.selected_footprint` is
   width × depth, `demo/scope.py:362` refuses a non-RECTANGLE `shape_type`, `service._brain_result`
   passes `(outline.width_m, outline.depth_m)`, and `brain/exact_pipeline.py:128` builds
   `Envelope.rectangle(*inp.footprint_m)`. No exception is raised — the request never gets far
   enough to raise one, which is why this is recorded as a contract limit and not a crash.
8. Outside the product, the same realizer and the same `to_demo_design` **do** produce drawable
   polygon plans, and `DemoPlan` draws them: 19 payloads over F2/F4/F5 with 2–12 footprint wings,
   rendered with correct walls, doors, windows and a stepped outline (figure
   `drawing-audit/F2-L-envelope-fixed__C-polygon__…__cells.png`). This is the evidence that the
   *drawing* is not the blocker for non-rectangular shapes — the *input contract* is.
9. On the polygon path the notch does become garden (the crook rule), so those figures do show a
   court — but still on a synthesised parcel.

**Mechanical checks across all 56 payloads: 0 windows on interior walls, 0 windows or doors without
a host wall, 0 rooms outside the footprint union, 0 overlapping rooms, 0 duplicated wall segments,
0 validation failures.** Walls, doors and windows are drawn from the backend's own facts and are
sound in every payload produced. The drawing defects are in the two places above (labels, site) and
in what the payload *fails to say* (open interfaces).

---

## 5. The non-rectangular envelopes, recorded as they happened

| case | family | what the product did | what the brain's geometry can do outside the product |
|---|---|---|---|
| **F2-L-envelope-fixed** | L-shaped | **cannot receive the L.** Planned on the 14 × 16 bounding rectangle instead: production 160 m² / 84 %, brain 191 m² / 101 % | 2 polygon plans realized and drawn (band, cells) — `drawing-audit/F2-L-envelope-fixed__C-polygon__*.png` |
| **F4-entry-court-notch** | irregular rectilinear | **cannot receive the notch.** Planned on the 17 × 16 bounding rectangle: production 158 m² / 74 %, brain 194 m² / 90 % | 8 polygon plans realized and drawn — but every one of them sits *below* the street notch rather than fronting the street inside it, so the entry court is not used as an entry court |
| **F5-garden-court** | U-shaped / courtyard | **cannot receive the court.** Planned on the 16 × 15 bounding rectangle: production 179 m² / 100 %, brain 195 m² / 108 % | 9 polygon plans realized and drawn, the court appearing as garden |
| **F3-wide-shallow-free** | narrow/constrained | **both engines REFUSED**, typed, same code: `PLAN_NOT_REALIZABLE`, 4.8 s. A 24 × 9.5 m strip with 5 bedrooms, 3 wet rooms and a MAMAD does not plan in either engine. The refusal is honest and identical — this is not a brain regression. |
| **F1-rect-control** | rectangular | both planned (production 85 %, brain 92 %) | — |
| **F6-unsatisfiable-K4** | rectangular | both planned. **This does not violate the frozen spec's "a plan here is a FAIL" rule**: that rule is about the *declared K4 contact set*, which the product's own programme does not carry and has no way to express. Through the product path F6 is just a 13 × 17 brief. |

**The one-line version:** the brain's *geometry* already realizes and draws L, court and notched
envelopes; the *product* has no way to accept one. #208's day-2 verdict was STOP on the
shape-agnostic generator, so this is a known, open front, not a surprise.

---

## 6. Architectural judgments

**This section is judgment, not measurement.** It is my reading of the drawings, criterion by
criterion; another architect may weigh these differently. Every claim names the figure it comes
from. The validators have no vote here.

### 6.1 Entrance and foyer — the brain is clearly better

Production opens the front door **into the corridor itself** on 22 of 25 briefs: a slot
1.20–1.30 m wide and 11–15 m long, aspect 8.5–12.0. `B16__production.png` is the clearest case —
you enter and are immediately standing in a 1.20 × 14.30 m passage with six doors off it. There is
no arrival space, nowhere to stand aside, nowhere to put a coat.

The brain gives an arrival **room** in 25 of 25: short side 1.50–4.90 m, aspect 1.1–2.5.
`B16__brain.png` arrives into a 4.90 × 7.95 m hall; `B19__brain.png` into 4.20 × 4.75 m. This is
#205's foyer geometry doing exactly what it was built to do. At the weak end (`B10`, `B14`, `B15`,
`F1`, `F2`: 1.50 m × 3.75 m, aspect 2.5) it is a narrow lobby rather than a foyer — but still a
room you can stand in, which the production corridor is not.

### 6.2 Circulation — the brain trades one defect for another

Production's corridor is a textbook double-loaded spine: aspect 8.5–12.0 on every single plan, 1.2 m
wide, with at least one dead end. It is *bad circulation*, and it has one virtue — it always
touches an exterior wall, so it can be lit.

The brain's hall is well proportioned (aspect 1.9 median, never above 3.0) but **landlocked in 19 of
25 plans and much larger**: median 26.2 m² against 16.6 m², up to 36.3 m², 15.8 % of the house
against 10.7 %. `B18__brain.png` is the extreme — a 9.40 × 3.15 m, 29.6 m² windowless internal hall
in a 181 m² house, larger than any bedroom in the plan and larger than the living room of several
briefs in this corpus. A 30 m² room with no daylight is not a hall, it is a lost room.

**Neither engine's circulation is shippable as architecture.** Production draws a corridor nobody
wants to walk down; the brain draws a hall nobody can see out of. This is the single clearest
"both are wrong, differently" result in the corpus, and it matches the earlier `PART-3-quality.md`
finding now measured at corpus scale.

### 6.3 Open plan — the brain does not deliver what the brief asked for

Nine briefs in this corpus ask for open plan. Production draws it as open plan on **all nine**: in
`B08__production.png` the living, dining and kitchen are one continuous space with no wall between
them, and the legend names the convention. The brain draws **walls with doors** between them on
**all nine**. `B02__brain.png` is the starkest: a one-bedroom, 216 m² open-plan brief rendered as a
46 m² salon, a 28 m² dining room and a 22 m² kitchen, each sealed off with its own door. That is not
a different design opinion, it is the brief not being delivered — and §4 note 5 shows it is a
single unset variable, not a design position.

### 6.4 Zoning, orientation and privacy — mixed, and the brain wins the garden

The brain puts a public room on the garden facade in 16 of 25 plans; production in 2 of 25
(production habitually parks the whole public band on the street side — `B16__production.png`).
Orienting the living space to the garden is the right instinct and the brain has it.

Against that, the brain puts **49 windows on the street facade to production's 19**. On
`B19__brain.png` two bedrooms and the dining room all face the street with 1.95 m windows. For an
Israeli single-family plot that is a privacy choice most clients would push back on, and production's
reticence toward the street is the more conventional reading.

### 6.5 Room proportion and the service rooms — a real brain defect

Bedroom proportions are comparable (worst-aspect median 1.88 vs 1.92). The problem is **relative**
size: in 8 of 25 brain plans a wet room is **larger than the smallest bedroom**. `B18__brain.png`
has a 13.3 m² bathroom beside 9.0 m² bedrooms; `B09__brain.png` has 13.1 m² and 11.1 m² bathrooms;
`B17__brain` 13.8 m² against a 9.1 m² bedroom. A bathroom bigger than a child's bedroom reads as a
sizing artefact — the surplus area going wherever the solver's bounds let it — not as a decision.
Production does this twice. `B18__brain.png` also draws a **12.9 m² MAMAD**, above the 12 m² ceiling
the market reference records (`product-readiness-audit/reference-sources.md` §D); production's is
10.0 m².

### 6.6 Envelope utilisation — the brain is better, and this one is not close

Median deviation from the requested built area: brain 12.9 points, production 22.6. On the briefs
where production simply gives up a quarter of the house — B14 67 %, B04 42 %, B09 52 %, B12 59 % —
the brain delivers 85 %, 41 %, 41 %, 52 %. It is not uniform (B03 56 % vs 72 % and B09 41 % vs 52 %
go the other way) and *over* 100 % is a deviation too (B13 109 %, B18 109 %), but across the corpus
the brain is the engine that fills the house it was asked for.

### 6.7 Legibility of the drawing itself

Both engines produce drawings with text problems, and the brain's are worse in the way that
matters: 67 label blocks outside their own room against 44, up to 1.05 m adrift. On
`B15__brain.png` and `B18__brain.png` six blocks each sit over a neighbouring room or over a wall.
The cause is shared by both engines (`demoRoomLabel.ts` offsets and rotates without clamping to the
room), but the brain triggers it more often because it produces more narrow service rooms.

### 6.8 Plausibility, at a glance

Asked "could this be an architect's concept sketch?", `B16__brain.png` and `B19__brain.png` read as
plausible houses with a real arrival, generous public rooms and a sensible bedroom wing, spoiled by
a windowless hall and by doors where the brief asked for openness. `B16__production.png` and
`B08__production.png` read as efficient but institutional: a long corridor, rooms off it, a correct
open-plan living space. **Neither engine produces a drawing I would put in front of a client
unchanged.**

---

## 7. Ranked defects of the brain's output

Ranked by how much each one damages a plan shown to a client, highest first. Each names the figure
and the suspected cause in code.

| # | defect | how often | figure | suspected cause | fix size |
|---|---|---|---|---|---|
| **1** | **Open plan is never drawn.** Every room-to-room boundary is a wall with a door, including living↔dining↔kitchen on briefs that asked for open plan. The brief is not delivered. | **9 of 9 open-plan briefs; 0 open interfaces in 56/56 payloads** | `B02__brain.png`, `B08__brain.png`, `B16__brain.png` | `rectilinear_realizer.py:1263` — `open_pairs` is created empty in `realize_cells` and never populated (comment at line 1273: *"OPEN (none here)"*), so `design.open_groups` is empty at line 1329; `realize_layout:1448` only opens same-zone seams; with no open group `demo/contract.py:975`'s corridor-opening post-process cannot fire either | **days** — the brain has no notion of a declared open group; it needs one from the parti/programme through the placement and into the realizer |
| **2** | **The hall is a large windowless interior room.** Well proportioned but landlocked and oversized — up to 29.6 m² with no exterior wall. | **19 of 25 landlocked**; circulation 15.8 % median vs production 10.7 % | `B18__brain.png`, `B19__brain.png`, `B09__brain.png` | circulation is the elastic filler in the band sizing: the hall's area band is the loosest in the programme (`brain/proposer.py` `_hall_intent`, `HALL_CEILING_M2`), so surplus lands there; nothing in the preference ranks a hall's exterior contact (`brain/runner.py:_preference`) | **days** — add exposure/area terms to the hall's intent and to the preference key, then re-measure; the memory note "circulation is the elastic filler" says capping alone shrinks the house |
| **3** | **The person's parcel is not drawn.** A 2 m skirt is drawn instead of the real plot; no parking bays; garden only in a wing crook. For a preview judged visually, the site reads as wrong on every plan. | **25 of 25** | any `*__brain.png` beside its `*__production.png` (e.g. `B01`: parcel 23.6 × 14.3 drawn, real plot 28 × 30) | `rectilinear_realizer.py:1379` `_build_site` — `plot = footprint + 2 m`, `parking=()`, garden = crook remainder only; `service._brain_result` never re-attaches the project's own site | **hours–1 day** — the brief's plot, parking and garden are all available at `_brain_result`; this is a plumbing fix, not a geometry one |
| **4** | **Service rooms outgrow bedrooms.** A wet room larger than the smallest bedroom; one MAMAD above the 12 m² market ceiling. | **8 of 25** (wet > bedroom); MAMAD 12.9 m² on B18 | `B18__brain.png`, `B09__brain.png`, `B17__brain.png` | same elastic-area mechanism as #2 one tier down — per-role maxima are not binding in the exact placement's target objective (`exact/milp_oracle.py` objective `"target"`); production's `ROOM_TEMPLATES` preferred maxima do bind | **1–2 days** |
| **5** | **Room labels leave their rooms.** Up to 1.05 m outside; 6 blocks adrift on a single plan. | 67 blocks over 25 plans (production 44) | `B15__brain.png`, `B18__brain.png`, `F4-entry-court-notch__brain.png` | `frontend/src/design/demoRoomLabel.ts` — the block is offset and rotated to dodge furniture and door swings, but never clamped to the room's own rectangle, and small rooms have no compact fallback that fits | **1–2 days**, shared with production (it is a renderer defect, worse under the brain's geometry) |
| **6** | **32 s median, 50 s max per request.** Production's median is 1.8 s. | 25 of 25 | — (timing column, §3) | `brain/runner.py:REQUEST_BUDGET_S = 30.0` plus `EXACT_TOP = 3` partis sized exactly, serially; the module's own comment says the honest fix is parallelising independent partis | **1–2 days** — belongs to #214, named here because it is what a previewer will feel first |
| **7** | **The cross-band families are effectively inert.** band wins 25 of 25 shown-first plans although spine/stack/cells are enabled. | 25 of 25 | §3.3 | the 30 s budget is consumed by the band family's own ladder before the later families are sized (`brain/exact_pipeline.py` `out_of_time()` gating per family); on the frozen cases, with per-family budgets, they do produce plans | **investigation** — decide whether to budget them per family or to leave them off for the preview |
| **8** | **Non-rectangular envelopes cannot reach the engine at all.** | 3 of 3 polygon cases | §5 | `demo/scope.py:362` + `brain/exact_pipeline.py:128` | **weeks** — this is ROOT-level work (#208 STOP), not a preview fix |

**Defects #1 and #3 are the two that make a brain plan look wrong to a non-technical viewer in the
first three seconds**, and both are plumbing rather than geometry. #2 is the one that makes it look
wrong to an architect.

---

## 8. Which engine would an architect prefer, per brief

**Judgment, with a stated rubric.** In order: (1) does the plan deliver what the brief asked for
(open plan); (2) is the arrival usable; (3) is the main circulation habitable; (4) are rooms
sensibly proportioned relative to each other; (5) is the requested area delivered. Site drawing is
excluded — it is a plumbing defect, not a design one.

| brief | preferred | why, in one line |
|---|---|---|
| B01 | **brain** | same circulation share, a 3.0 × 3.8 m foyer instead of a 1.3 × 11.1 m slot; both waste the brief's area badly (28 %/34 %) |
| B02 | production | open plan asked and delivered; the brain seals three huge public rooms behind doors |
| B03 | production | the brain gives up 16 points of area (56 % vs 72 %) and gains only the foyer |
| B04 | brain | foyer, and equal area; the brain's hall is not landlocked here |
| B05 | production | open plan asked and delivered |
| B06 | brain | narrow 13 × 24 envelope: the brain's foyer and 2.0-aspect circulation beat a 1.3 × 13.5 m spine |
| B07 | neither | brain circulation 20 %, landlocked; production arrival aspect 11.0 — both are poor |
| B08 | production | open plan asked and delivered, at 98 % of the request; the brain matches the area but seals the LDK |
| B09 | production | the brain loses 11 points of area and draws two bathrooms of 13.1 and 11.1 m² |
| B10 | brain | foyer + 1.21 worst-bedroom aspect, against an 11.2-aspect arrival corridor |
| B11 | neither | open plan asked (production delivers) but production's arrival is a 1.2 × 13.8 m slot; brain circulation 19 %, landlocked |
| B12 | production | brain draws a 13.9 m² wet room beside 9.8 m² bedrooms and loses 7 points of area |
| B13 | production | open plan asked and delivered |
| B14 | brain | 85 % vs 67 % of the request, better bedroom aspect; wet/bedroom margin is marginal (10.7 vs 10.5) |
| B15 | brain | 98 % vs 91 %, foyer, better bedrooms; 6 escaped labels is a renderer defect, not a design one |
| **B16** | **neither** | the brain's plan is the better *house* (99 % of the request, a real hall, bedrooms 11–18 m²) but it ignores the open-plan brief and the hall is landlocked; production delivers open plan down a 1.2 × 14.3 m corridor |
| B17 | brain | 87 % vs 83 % and a usable arrival, despite a 13.8 m² wet room; production's corridor is 11.3 aspect |
| B18 | production | the brain's 29.6 m² windowless hall and 13.3 m² bathroom beside 9.0 m² bedrooms outweigh its area win |
| **B19** | **brain** | the strongest brain plan in the corpus: 101 % of the request, a 4.2 × 4.75 m arrival hall, bedrooms 9.6–17.6 m²; costs are the open-plan brief and a landlocked hall |
| B20 | production | open plan asked and delivered at 99 % |
| F1 | brain | 92 % vs 85 %, foyer vs a 1.3 × 15.2 m arrival slot |
| F2 (bbox) | brain | 101 % vs 84 % on the bounding rectangle — but neither engine is drawing the L the case is about |
| F3 | **neither — both refused**, identically and honestly (`PLAN_NOT_REALIZABLE`) |
| F4 (bbox) | brain | 90 % vs 74 %; both ignore the entry court, which neither can receive |
| F5 (bbox) | production | open plan asked and delivered; the brain overshoots to 108 % |
| F6 | tie | 99 % vs 101 %, both plausible; the case's real constraint cannot be expressed through the product |

**Count: brain 11 · production 10 · neither 3 · tie 1 · both refused 1.**

Read that count carefully. It is close, and it splits almost exactly along one line: **production
wins 8 of the 9 open-plan briefs and the brain wins most of the rest.** Remove defect #1 and the
count moves decisively toward the brain; leave it in and the brain cannot be shown on any brief
whose client asked for an open kitchen.

---

## 9. What I could not verify

* **Parking bays.** Every brief in the corpus has `parking_spaces = 0` (the shared test-project
  helper sets it), so "the brain drops the parking bays" is read from `_build_site`'s
  unconditional `parking=()` (`rectilinear_realizer.py:1389`) and from production drawing bays on
  other briefs — **not** from a measured side-by-side on a brief that asked for parking.
* **Alternatives.** Only the plan shown first was rendered and measured per brief. The brain offers
  two alternatives on 22 of 25 briefs and production none on 9 of 25; whether the brain's
  alternatives are genuinely different concepts was measured for #142 in the Product Readiness
  Audit, not re-measured here.
* **Timing.** Single runs on one loaded laptop, with two of the three families' MILP work inside a
  30 s budget. Treat §3's seconds as an order of magnitude; #214 owns real latency work.
* **Hebrew typography.** The figures are rasterised in headless chromium with the product's
  stylesheets but not the product's web fonts, so glyph metrics — and therefore the exact label
  collision counts — may differ slightly from a user's browser. The *relative* comparison between
  engines is unaffected (both rendered identically).
* **F4's entry court.** That the polygon plans sit below the notch rather than fronting the street
  inside it was read off the payload geometry (street-row wings spanning the full width at
  `y = 7.0`), not from a dedicated check of the frozen case's own expectation.
* **Judgments.** §6 and §8 are one reader's architectural reading. They are not derived from the
  validators and should not be quoted as if they were.

---

## 10. Reusable workflow (what this leaves behind)

| piece | what it does |
|---|---|
| `app/ai_harness/comparison_corpus/corpus.py` | the 26-brief corpus, labelled by envelope family, each entry naming its source file |
| `app/ai_harness/comparison_corpus/run.py` | both engines on one brief through the product's own entry point; saves both payloads and measures them |
| `app/ai_harness/comparison_corpus/report.py` | prints every objective table in this report |
| `app/ai_harness/drawing_audit/run.py` | per-layout-family and polygon-envelope payload builds, plus the mechanical payload checks of §4 |
| `frontend/src/design/drawing-audit-render.test.tsx` | mounts `DemoPlan` + `PlanLegend` on a directory of payloads and writes their markup |
| `app/ai_harness/drawing_audit/rasterise.mjs` | rasterises that markup with the product's stylesheets and measures label legibility in the browser |
| `backend/tests/ai_harness/test_comparison_corpus.py` | AC-1: both engines on one brief, each producing a payload carrying every field `DemoPlan` reads |

Adding a brief is one line in `corpus.py`; re-running the whole comparison is the four commands in
§1.
