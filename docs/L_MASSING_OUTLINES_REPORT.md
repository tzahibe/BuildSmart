# L Massings on a Rectangular Plot — implementation record

**Date**: 2026-09-16 · **Branch**: `016-l-massing-outlines` (from `main` @ `60cf113`) · **Plan**: `BUILDING_SHAPE_MASSING_FAMILIES_REPORT.md` §3.2 (the massing candidate stage), Phase 2

**What this is**: the engine's outline search now also carves two **L massings** from the buildable rectangle at the requested area and surveys them beside its four rectangles. Until now the L parti (branch `012`) could only fire on an L-shaped *site*; every one of the 432 real briefs is a rectangle, so no real brief could see an L. **What it is not**: a shape the person picks (no UI beyond the label), a change to the primary rule, or a change to which rectangles are surveyed.

## How

| Where | What |
|---|---|
| `site_geometry.LMassing`, `l_massings(site, area)` | Two wings of the requested area inside the buildable rectangle behind the parking band: a 5 m arm (`L_ARM_WIDTH_M` — the width at which single-room private rows plan; 6 m needs row sharing) of 9.5 m, or 8.5 / 7.5 for a smaller house; the primary takes the rest, as deep as the site allows up to 20 m (so an open-plan band has room beyond the seam), at least 6 m wide. Two orientations: arm at the **rear** (public band on the street) and at the **front** (band to the garden). A geometric guard: the primary column must outweigh the full-width strip along the arm, or the adapter's largest rectangle is that strip and the "arm" lands north/south — which the parti refuses. The area is never reduced; no fit → no L. |
| `service.Outline.massing` | An `Outline` is a rectangle or, with a massing, an L whose bounding box the width/depth are; `shape`, `area_m2` (the L's), `as_out()` → `OutlineOut.shape`, `wing_dims_m`. |
| `service._outlines_for` | The L massings after the rectangles, `origin = ENGINE`. |
| `service._buildable_from(spec, project, outline)` | For an L outline the region is the L itself — one six-point ring placed by the same rule as a rectangle — so the adapter yields the primary and the arm as two adjacent candidates, exactly as on an L-shaped site. |
| `service._plan_outlines` | A massing outline contributes **only two-wing plans** to the pool; the one-wing plans the pipeline also makes on the primary rectangle are rectangles the rectangle outlines already cover. |
| `service._select_plans` | One plan per non-rectangle massing in the shown set (passes 1 and 2): the two L orientations are different families (band above / below the seam) and would otherwise both take a slot, leaving none for a rectangle alternative. Measured before the rule: two 141.5 m² L's beside one rectangle. |
| `contract.OutlineOut / OutlineTried` | `shape` (`RECTANGLE` default), `wing_dims_m`. Additive. |
| frontend `DemoWorkspace.outlineText` | An L is labelled by its two wings — "בית L: 8.25 × 18.50 + 5.00 × 9.50 מ׳ · 200 מ״ר" — so a 143 m² L never reads as a 200 m² rectangle. |

The L outlines join the **engine survey**, which runs only when the person gave no outline (the 006 main flow) or theirs planned short. A person's own outline still plans first and alone.

## Measured

**Sample of every 4th failure-log context (108; 98 planned), this branch against `main`:**

- Primaries **98/98 identical**; **0 gained, 0 lost**; refusal codes unchanged. The L never changes what wins on area — it appears only as an alternative.
- The L massings were surveyed in **14** planned briefs (the ones where the engine surveys at all: no outline of the person's, or theirs planned short; and a site + area that hold an L). An L **planned and is shown in 5** of them; L as primary: 0.
- Where shown, the set is `rectangle · L · rectangle` (one brief has only one rectangle alternative to show); **zero** double-L after the shown-set rule.
- **Latency on those 14 briefs**, main vs this branch: median 12.6 s → 12.9 s (**+0.5 s**), max 23.4 s → 24.9 s (**+4.7 s**). These are the heavy briefs already (four outlines surveyed then one re-run with alternatives); the L adds two fast-path surveys. Briefs with a person's outline that plans are untouched (their median in the sample stays ~2–3 s).

**Synthetic 3BR briefs on a 24 × 28 m plot (200 m², main flow)**: the L planned and was shown for open-plan 3BR with 1–2 wet rooms with or without a safe room (131.9–143.6 m² beside a 192–197 m² rectangle); a 2BR on 22 × 26 m gets no L massing (the primary would be a strip), by design.

**Six real 3BR briefs on a 21 × 26.5 m plot at 224 m²**: L surveyed in all six, planned in one (open plan), refused in five (closed plans with 2–3 wet rooms — the column beside the hall cannot fill the seam; the same refusals the L report named).

## Tests

`test_demo_outline_selection.py` (+5): massings carve two wings at the requested area within the site, with the primary outweighing the strip; the ring is the L, counter-clockwise, with the front-arm variant full-width at the street; no massing for a small house, a tight site or an over-wide request; the outline list has the L's after the rectangles, labelled; a second same-family L does not take a rectangle's slot; the two orientations are different families but only one is shown. `test_demo_contract_additive.py` (+1 and the tried-fields assertion). `test_demo_p0.py` (+1, through the API: two L outlines surveyed after the four rectangles, the primary a rectangle, one L alternative with two footprints and C22, no C22 on the one-wing plan). Frontend `DemoPlan.test.tsx` (+1: the L label).

## Regression

- **Backend suite**: 1229 passed, 9 xfailed, 0 failed (8 new tests). No sample artefacts touched (branch `015`).
- **Frontend**: 164 passed (1 new); `tsc` only the six pre-existing errors.
- The 108-context sample: primaries 98/98 identical to `main`, 0 gained, 0 lost (above).

## The L-orientation tiebreak (same branch, second commit)

The two L massings are the same dimensions and the parti sizes them symmetrically, so their plans tie EXACTLY on the pool's area criterion (measured on all five real dual-valid briefs: 161.5/161.5, 167.87/167.87, 168.5/168.5 ×2, 165.97/165.97). Left to the pool's determinism (`outline.order`), the rear-arm L was shown every time and a garden-facing L never. `_select_plans` now breaks that tie — and only that tie, among valid plans of one non-rectangle massing otherwise tied — in `demo/service.py`:

1. `HouseConcept.public_open_side`: GARDEN → the L whose band faces the garden (arm at the front); STREET → the band on the street (arm at the rear). (The demo has no concept field yet, so today this is always ENGINE; the path is tested on stubs.)
2. ENGINE → **realized quality of the tied peers only**, Pareto (better on ≥ 1, worse on none) over existing measures: the bedroom-class aspect (`hub_guard.proportions_of`: worst of bedrooms and master), wet adjacency share (same source), and two-sided exposure (habitable rooms with two exterior walls, from `wall_facts`). No global rule, no bonus for being an L, the primary untouched.
3. Exact tie → `outline.order`, for determinism.

Measured on the five dual-valid briefs — the orientations are NOT exact mirrors in realized quality: rear dominates once (two-sided 0.71 vs 0.57), **front dominates once** (4BR/216 m²: 0.625 vs 0.5 — the garden-facing L wins on merit), three tie exactly and fall to order. Shown: rear ×4, front ×1. 108-context sample vs `main`: primaries 98/98 identical, 0 gained, 0 lost; every L brief shows `rectangle · L · rectangle` (one has only one rectangle alternative to show); 0 rectangle alternatives displaced by a second L. Tests (+8 on stubs): GARDEN → front, STREET → rear, ENGINE picks the dominating peer and falls to order when measures conflict or tie, a preference nobody matches falls through to quality, rectangles and the primary untouched, one L in the shown set, and the tiebreak never overrides the area criterion (a nearer L wins whatever the preference).

## Left open

- Cost: each L massing is a full `run_general` (one-wing partis on the primary rectangle included, then discarded). A `two_wing_only` mode in the generator would roughly halve the L survey; left out because `concept_generator.py` is under concurrent edit.
- Both L orientations are worth showing; the three-slot shown set is what prevents it (`_SHOWN_LIMIT`).
- The L still loses on area by construction (a `column + hall` bar); whether it should ever be primary is the grouped-primary question, untouched.
