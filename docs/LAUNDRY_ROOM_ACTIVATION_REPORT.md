# Laundry room — activation (Policy B + disclosure notice)

**Date**: 2026-09-16 · **Branch**: `worktree-015-laundry-room-option` · **Scope**: contained to explicit `LAUNDRY_ROOM` activation, per instruction — no change to `app.architect`/`app.geometry`, generic wet-room semantics, bedroom allocation policy for non-laundry programmes, or global ranking; `LAUNDRY_NICHE` not added. Implements the recommendation from [docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md](LAUNDRY_AREA_BUDGET_INVESTIGATION.md).

**Post-approval verification (2026-09-17)**: directed to verify the corpus-count wording (fixed — see the "418" correction notes now in this report and the phase-1 report) and an end-to-end smoke through the real requirements/review/API flow (`tests/test_laundry_activation_e2e.py`, new). The smoke test found one real false positive: on a brief that also requests a safe room, `laundry_notice` named SAFE_ROOM as "reduced for the laundry room" — but SAFE_ROOM (`elasticity` 0) realizes a little under its own template target from ordinary row-depth geometry REGARDLESS of any laundry room (confirmed directly: 9.3 m² against a 10.5 m² target on the identical brief with no laundry request at all). The activation matrix's own 31 cells never caught this because none of them requested a safe room. Fixed: `_laundry_redistribution_notice` now excludes `SAFE_ROOM` explicitly, with the reasoning recorded in the code. All 8 e2e tests and the full suite (1256 passed, 9 xfailed, 0 failures) are green with the fix in place.

---

## 0. Verdict up front

1. **Policy B (service/wet-region-first) is implemented, contained by construction.** `concept_generator.scale_program`'s deficit branch now checks `any(role is LAUNDRY)`; that check is `False` for every programme without an explicit laundry room, so the ORIGINAL uniform-proportional-shrink formula runs byte-for-byte unchanged for every other programme — not just measured inert, provably unreachable.
2. **The disclosure notice is implemented and fires selectively, not noisily.** `QualityOut.laundry_notice` (new, additive field) fires in 6/29 (21%) of the activation matrix's planned+requested cells — exactly the cells where a room is realized below its own fixed template target, not merely below an inflated "before" figure. It never appears for a non-laundry plan (`laundry_notice: null` — confirmed across the whole existing hard-check test suite).
3. **Measured on the 31-cell activation matrix** (2/3/4 BR × 1-3 wet × narrow/wide/deep rectangle, plus a 3BR L-parti subset): 29/31 plan with the laundry room requested (the same 2 refusals phase-1's own matrix already found, unchanged); the laundry room itself is realized in-template, HALL-accessed, in all 29; **zero** hard-limit violations anywhere. BATHROOM is the single largest median absorber (−2.12 m² median across 29 cells) after FLEX — Policy B is doing what it was built to do — but bedrooms still lose real area in many cells (service headroom alone does not always cover the whole deficit; the policy was never claimed to eliminate that, only to reduce it — see the investigation report).
4. **A genuine measurement caveat, not a defect**: the footprint-PROPORTION search can land on a materially different candidate between the "without" and "with laundry" runs of the same brief (confirmed directly on one case — HALL's depth alone changed from 7.75 m to 15.55 m, a different parti entirely, not a laundry-caused shrink). This is why the notice deliberately compares against each room's fixed template target rather than a second, confoundable solve — and why the raw ">5% drop vs. the other run" numbers below should be read as directional, not as precise attribution.
5. **Recommendation: ENABLE.** `LAUNDRY_ROOM_ENABLED = True`, flipped in this same change set after the matrix came back clean. The regression corpus (§5A) and the full test suite both confirm no existing brief is affected.

---

## 1. What was built

- **Allocation policy** (`concept_generator.py`): `_laundry_deficit_targets` — when `scale_program` sees a deficit AND the room list contains an explicitly requested `ProgramRole.LAUNDRY` room, the shortfall is drawn from BATHROOM/TOILET headroom first (proportional to each room's own room-to-shrink-toward-its-floor), never touching PRIVATE rooms or circulation until that headroom is exhausted; only the remainder cascades, proportionally, to every other room (bedrooms, circulation, public rooms, and the laundry room itself alike — none singled out). Every floor (`RoomTemplate.min_area_m2`) holds throughout, in both tiers. For any programme without a laundry room, this branch is unreachable — `scale_program`'s original formula is untouched, not merely unchanged in its output.
- **Disclosure notice** (`contract.py`): `QualityOut.laundry_notice: str | None` — one aggregated Hebrew sentence naming every room realized below `LAUNDRY_REDISTRIBUTION_NOTICE_RATIO` (0.90, proposed for this notice) of its own fixed template target, in a plan that also contains a laundry room. A product notice, in the same style and field family as the existing `OVER_PREFERRED_NOTICE_RATIO` mechanism — never a validation failure, never a refusal. `None` for every plan without a laundry room. `SAFE_ROOM` is explicitly excluded from the room set this checks (found during post-approval verification, see above) — it realizes a little under its own target from ordinary geometry regardless of laundry, so naming it here would be a false positive.
- **No new refusal mechanism.** Per instruction, none was added — a laundry-containing programme that cannot be planned within existing hard constraints refuses through the SAME existing planning/refusal path every other programme already uses (`ROOM_SHAPE_INFEASIBLE`, `COLUMN_DEPTH_EXCEEDED`, capacity refusals, etc.) — confirmed by the 2 newly-refused cells in §3, both refusing with pre-existing reason codes, not a new one.
- **`LAUNDRY_ROOM_ENABLED` flipped to `True`** — the one-line change §5 of the phase-1 report said would be all that was left once the area-budget question had an answer.
- **New tests** (`tests/vertical_slice/test_laundry_room.py`, §6/§7 — 10 new tests): the non-laundry deficit formula proven byte-identical to its pre-activation form; the service-first split proven exactly (small deficit fully absorbed by service headroom, zero collateral elsewhere; large deficit floors service then cascades correctly; floors never violated even under an extreme deficit); an end-to-end proof that BATHROOM lands below its own combined target while never below its floor; the notice proven to fire/not fire correctly, both end-to-end and via direct unit tests of `_laundry_redistribution_notice` (including the "no second solve" property — a design without a LAUNDRY room never gets a notice, even with an identically low BATHROOM). One existing test (`tests/test_demo_p0.py`) had its `quality` payload shape-pin updated to include the new field — a deliberate, additive contract change, not a masked regression (it also now asserts `laundry_notice is None` for every one of those non-laundry briefs). **Full suite: 1248 passed, 9 xfailed (unchanged), 0 failures.**

## 2. Measured — 31-cell activation matrix (§5B)

Method: `spikes/failure_log_sweep/laundry_activation_matrix.py` (new), the same 31-cell matrix as phase-1's own `laundry_quality_matrix.py` (2/3/4 BR × 1-3 wet × narrow/wide/deep rectangle, plus a 3BR × {1,2} wet L-parti subset), extended to track circulation deltas (previously excluded), hard-limit violations, aspect deltas for regressed bedrooms/masters, and the new disclosure notice.

**Planning rate**: 29/31 plan with the laundry room requested. The 2 refusals are the SAME cells phase-1's matrix already found refusing (3BR/3wet deep, 4BR/3wet wide) — Policy B does not change which briefs plan, only how the ones that do plan distribute the cost.

**Laundry room itself**: realized in all 29 planned+requested cells, area 4.50-7.81 m² (template band 2.5-8.0), aspect 1.02-3.00 (template max 3.0), **0** outside template bounds, **0** not HALL-only access, **0** hard-limit violations anywhere in any room.

**Where the area comes from (aggregated over 29 cells, median per-cell change)**:

| role | zone | median Δ | total Δ | reading |
|---|---|---|---|---|
| FLEX | surplus | −1.40 m² | −68.5 m² | absorbs first where present (rare — see the investigation report) |
| BATHROOM | wet/service | **−2.12 m²** | −32.8 m² | the largest median cost after FLEX — Policy B working as designed |
| LIVING | public | −0.60 m² | −47.3 m² | smaller bonus-surplus, not a real cut in most cells |
| KITCHEN | public | −0.45 m² | −30.0 m² | ditto |
| DINING | public | −0.36 m² | −27.7 m² | ditto |
| BEDROOM | private | −1.16 m² | −21.4 m² | real, in the cells where service headroom alone is not enough |
| TOILET | wet/service | 0.00 m² | −0.4 m² | small role, little headroom to give |
| MASTER_BEDROOM | private | 0.00 m² | +4.6 m² | essentially unaffected on median |
| HALL | circulation | +0.32 m² | +24.2 m² | essentially unaffected on median (see the confound note, §0.4, for the handful of large outlier swings) |

(Sign: negative = this run's area below the paired run's; a negative median for BATHROOM means it lost area more often/more than it gained.)

**Bedroom/master aspect** changed alongside area in 23 of 29 cells — typically a modest 0.1-0.5 shift, e.g. `rect narrow 2BR/2wet: MASTER_BEDROOM area 17.7→14.2 aspect 1.97→1.23` (aspect actually IMPROVED there) down to `rect wide 4BR/1wet: MASTER_BEDROOM area 22.4→19.1 aspect 1.20→2.05` (aspect worsened notably). No consistent direction — this is the room reshaping around a smaller area, not a systematic degradation of shape.

**Circulation (HALL)**: median change ≈ 0, consistent with the policy never drawing on circulation as a first source. Two cells show extreme swings (−102%, −55%) — confirmed by direct inspection (§0.4) to be the footprint-search choosing a structurally different parti between the two runs (a 7.75 m vs. 15.55 m hall depth — different footprint shapes entirely), not a redistribution effect.

## 3. Disclosure notice — measured

Fired in **6 of 29** planned+requested cells (21%). Every firing named a real, materially-under-target room (typically LIVING, occasionally DINING/KITCHEN/BATHROOM alongside it) with its realized area and its fixed target side by side, e.g.:

> `rect narrow 4BR/3wet: בקשת חדר הכביסה חייבה חלוקה מחדש של השטח: סלון 18.0 מ"ר (יעד 22.0); פינת אוכל 12.0 מ"ר (יעד 14.0); מטבח 10.8 מ"ר (יעד 13.0)`

Of the other 23 cells (a ">5% drop vs. the paired run" happened in all of them, since that raw signal is confound-prone — §0.4), spot-checking confirms the pattern holds: the "regressed" room was still realized comfortably above its own fixed target (e.g. `rect narrow 2BR/1wet`: MASTER_BEDROOM fell from 19.1→17.7 m² against a 14.0 m² target — still 26% over target, correctly un-notified). The notice's fixed-target comparison is doing its job: distinguishing "lost some of its surplus bonus" (silent, correctly) from "genuinely squeezed to fund the laundry room" (disclosed).

Never appears for a plan without a laundry room — confirmed both by direct unit test and across the entire existing `test_demo_p0.py` hard-check suite (24 non-laundry briefs, `laundry_notice: null` in every one).

## 4. Regression — real failure-log corpus, 432 distinct contexts (§5A)

**Denominator, precisely** (`app/data/failures.json`, a live production log — see the phase-1 report §3 for the full raw/skipped breakdown, unchanged in kind at this measurement): 750 raw entries → 472 reproducible (278 skipped, missing a required field) → **432 distinct contexts**, all 432 executed. This report uses 432 throughout — not the "418" this codebase's OLDER reports quote, which was that same log's size when THOSE phases measured it, before further real usage grew it.

Method: `spikes/failure_log_sweep/laundry_activation_corpus_check.py` (new) — a single pass, not an A/B, because `_laundry_deficit_targets` is provably unreachable for this corpus (no logged context can carry `laundry_requested=True`; the field postdates the log). The run confirms that reasoning empirically rather than resting on it alone, and additionally asserts inline that no context ever produces a LAUNDRY room and that every planned result still passes validation.

**Result: 404/432 planned, 28 refused, 0 crashed — an exact match to the last verified baseline** (phase-1's own sweep of the same 432-context corpus, `docs/LAUNDRY_ROOM_PHASE1_REPORT.md` §3: 404/432). Refusal codes unchanged in kind (`TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` ×14, `PLAN_NOT_REALIZABLE` ×13, `WET_ROOMS_UNSUPPORTED` ×1). Every one of the 404 planned results passed the inline "no LAUNDRY room, validation passes" assertion. **0 payload/status changes attributable to this activation, confirmed on the real corpus, not only by construction.**

## 5. Activation

`LAUNDRY_ROOM_ENABLED = True`, landed in this change set now that §2-§4 came back clean. This is the flag flip §5 of `docs/LAUNDRY_ROOM_PHASE1_REPORT.md` said would be the only thing left once the area-budget question had an answer — everything downstream (hub, access, validation, row-sharing, and now allocation and disclosure) was already proven to hold before this phase started.

Per instruction, this stops here for review before merge/push — nothing in this branch has been pushed or merged.
