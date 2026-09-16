# Room Proportions — the quality tier, implementation record

**Date**: 2026-09-16 · **Follows**: `ROOM_PROPORTION_REPARTITION_REPORT.md` (the investigation) · **State**: uncommitted in the working tree, for review.

**Scope as given (phase 1)**: BEDROOM, MASTER, SAFE_ROOM; improve poor proportions by changing the decomposition only; the normal planning path unchanged; beside a valid candidate that leaves a bedroom-class room past its preferred aspect (1.5), bounded quality-repartition candidates through the existing tier-2 pairing machinery — at most 9 seams, 3 legal pairings, access-valid pairings only; same footprint, programme, wet-room semantics, access topology, hard limits, C17/C20/C21; normal candidates unchanged and available; no global ranking change. **Phase 2 (approved on the phase-1 recommendation)**: the narrowest ranking step — a quality peer competes only against its own base.

Not done, by scope: shrinking, relaxing any hard limit, wet-room semantics (the shared-bath-to-ensuite variant), corridor topology, L-specific logic, the hub, the ensuite sub-row, any global ranking rule.

## What was built

| Where | What |
|---|---|
| `RoomTemplate.preferred_aspect_ratio` | 1.5 on BEDROOM, MASTER_BEDROOM, SAFE_ROOM; None elsewhere. A target, never a gate: `room_depth_band_m`, `_zone_spec` and C20 still carry the hard 2.5. |
| `Repartition.quality / quality_rank / hard` | The tier-2 options object, in quality mode: re-partition for proportions, the `quality_rank`-th best legal pairing, the base plan's ceiling tier. |
| `_quality_candidates` | At a column width: for every lone row, every `_dependent_pairings` placement (a lone room of any role takes the master's slot beside the ensuite; the master goes full-width), `_finish_rows` + `_access_intact` exactly as tier 2, ranked by the estimated `(worst shortfall, rooms past target, mean aspect)` at that width, best `_MAX_QUALITY_PAIRINGS = 3`. Open-chain pairings (public rooms) are not tried — outside the objective. |
| `_rows_for_width(…, areas)` | The one hook every parti passes through (`_columns_at_seam`, `_plan_front_band_at`, `_plan_l`): quality mode starts from the normal path's rows (the WC rule included) and applies `_quality_repartition_rows`. |
| `plan_layout` / `_plan_front_band` / `_plan_l` | Quality mode keeps the normal nine seams (`_MAX_SEAM_OPTIONS`); tier 2 alone walks the whole window. |
| `_quality_layouts` (column partis), `_quality_front_bands` (front band), `l_parti._quality_l_plans` (L) | Beside each plan a strategy found (normal, shrunk, over-preferred; never a tier-2 plan): re-plan the same proportion with `fallback=Repartition(quality=True, rank=k)` at the base's own tier, k = 0..2, stop when the base plan comes back; keep the best by exact planned shapes that clears `_quality_accepts`. For the L the peer must have the base's wings. |
| `_quality_accepts` | Worst bedroom-class shortfall improves by ≥ `_QUALITY_MIN_GAIN` 0.1 — or, worst no worse, one room fewer past the target — and no room that was inside its target is carried more than `_QUALITY_SPILL` 0.1 past it (the full-width master at 4.8 m and 3.1 m deep is 1.55). |
| `ConceptCandidate.quality_repartitioned` | Marked, `repartitioned` as well (the pipeline's tier-2 rule applies), rationale marker `QUALITY_RATIONALE`. |
| `generate_concepts` | Quality candidates are their own block after tier 2, forced trees then twins, before the last-resort hubs and the no-target L. |
| **Phase 2** `general_pipeline._prefer_quality_twin` | After the chosen plan and the hub guard: the chosen plan's quality peers (same strategy, wings, sizing tier; forced tree first, then the solver-cut twin) are realized and validated; the first whose REALIZED bedroom-class shapes clear `_quality_accepts` against the chosen plan's takes its place; the displaced base is skipped in `_alternative_plans`. Without relationships only. Nothing else is compared. |

## Measured — phase 1 (432 contexts, the real service; baseline main @ 518e133 in a frozen worktree)

**Gates**: planned 404 → 404, **LOST 0**, GAINED 0; **primaries byte-identical 404/404** (rooms and strategy); 0 quality candidates failed C17/C20/C21 — every one of the 78 primaries' quality twins that solved passed every check. No hard limit moved: the hard aspect is still 2.5/3.0/3.5, the hard areas unchanged (`test_vocabulary_is_additive` snapshot updated for the new field only).

**Candidates**: +12 % (p50 58 → 64 per brief, max 464 → 584); 7,416 quality candidates in 53,338 (forced + twin). Planner calls +3 % (`plan_layout` p50 1,950 → 2,009). Solves unchanged (p50 13). Alternatives: 366 → 413 slots; 65 briefs' alternatives list changed (a quality plan of an unseen family or massing enters through the existing family rule); 67 quality plans shown as alternatives.

**The primary's quality twin** (same strategy, footprint, tier, cut regime — what phase 2 promotes):

| | |
|---|---|
| primaries with a bedroom-class room > 1.5 | 358 of 404 |
| with a quality twin generated | 89 (SPINE_PUBLIC_PRIVATE 62, BRANCHED_TWO_STACK 17, FRONT_PUBLIC_BAND 10) |
| twin solved and valid | 78 (11 forced trees refused by the solver; phase 2 falls through to their solver-cut twins) |
| worst bedroom-class aspect, primary → twin | p50 **2.03 → 1.62**, mean 2.01 → 1.65 |
| plans improved (worst moves > 0.05) | 64; worst unchanged but one strip fewer: 14 |
| brought from > 1.6 to ≤ 1.6 | 25; twin worst ≤ 1.5: 19 |
| bedroom-class rooms > 1.6 in those primaries | 197 → 90 |
| another bedroom-class room (not the worst) worse by > 0.05 | 10 (the spill: a master carried from ≤ 1.5 to ≤ 1.6) |
| room net area change, twin − primary (median / p10 / p90) | MASTER +2.0 / +1.4 / +3.7 m²; BATHROOM −1.8 / −3.8 / +0.6; SAFE_ROOM −1.5 / −2.4 / +0.1; BEDROOM −0.1 / −2.7 / +0.3; public rooms +0.6–0.9 |
| delivered area | gross unchanged (same footprint); net −0.74 … +1.17 m² (median +0.22) |

Typical twin: MASTER 3.1 × 6.3 m (2.03) beside a 2.15 × 6.3 m ensuite becomes MASTER 4.6 × 4.15 m (1.11) over two 2.25 × 4.4 m bathrooms; a 5.0 × 2.4 m safe room (2.08) becomes 2.5–2.8 × 3.6–4.2 m (1.3–1.5).

**Poor primaries with no twin: 269** — wet = 1 (no ensuite, no host slot) 129; SPINE_DOUBLE_LOADED 70 (the ensuite pair sits in the public column, the poor bedrooms in the other); SPINE_PUBLIC_PRIVATE 25, FRONT_PUBLIC_BAND 21, SPINE_SERVICE_CLUSTER 12 (no pairing that clears the rule at the nine seams); tier-2 primaries 10; BRANCHED 2. The investigation's replay predicted 87 twins from dependent pairings alone; the tier produced 89.

**L fixtures** (5 sites × 6 programmes, every L candidate realized): the normal L candidate lists are unchanged; 14 of 30 briefs get valid quality L plans; **129 of 129** same-wings pairs improve; arm bedroom-class rooms p50 **1.68 → 1.31**, rooms > 1.6: 167 → 34 of 292; 130 quality candidates solved and passed C1–C22 (16 forced trees refused by the solver, their twins solved). Generation per L brief 1.03 → 1.15 s (p50).

**Runtime, controlled** (72 briefs, every 6th context, one process per run on an idle machine, main run twice around the phase-1 run): main p50 4.17 / p90 11.26 / p95 14.24 s, phase 1 p50 4.16 / p90 11.09 / p95 13.97 s, main again p50 4.09 / p90 11.22 / p95 14.13 s. Paired per-brief delta of phase 1 against the better main run: p50 +0.06 s, p90 +0.22 s, p95 +0.29 s, max +0.89 s (ratio p50 1.02, p90 1.09); main-to-main noise p50 0.07 s. The planner-side bound holds by construction: ≤ 9 seams × ≤ 4 `plan_layout` calls per poor base plan (`test_the_quality_search_is_bounded`).

## Measured — phase 2 (the peer may take the primary's place; same 432 contexts, same baseline)

**Gates**: planned 404 → 404, **LOST 0**, GAINED 0; primaries identical **318**, **replaced by their own quality peer 86**, changed otherwise **0**. Every primary passes every check (validation gates the primary). Gross area identical in every substituted case; delivered/requested median 0.739 → 0.739, under 80 %: 248 → 248.

**The 86 substitutions**: worst bedroom-class aspect p50 **2.02 → 1.62** (mean 2.01 → 1.65); brought from > 1.6 to ≤ 1.6: 27; now ≤ 1.5: 20; worst unchanged but one strip fewer: 12; another bedroom-class room worse by > 0.05: 10 (the spill, ≤ 1.6 by rule); bedroom-class rooms > 1.6 in those plans 220 → 100. Net area delta median +0.24 m² (−0.74 … +1.17). Room areas move as in phase 1 (master +1.9 m² median, bathroom −1.5, safe room −1.8). The peer that won was the forced tree in 71 cases and the solver-cut twin in 15 (11 of them where the forced peer was refused by the solver — the fall-through phase 2 adds).

**All 404 primaries after phase 2**: worst bedroom-class aspect p50 1.97 → **1.86**; > 1.6: 342 → 315; > 2.0: 163 → 128. By role: MASTER p50 1.63 → **1.43** (> 1.6: 209 → 148), SAFE_ROOM 1.73 → **1.60** (160 → 123), BEDROOM 1.70 → 1.62 (430 → 408), BATHROOM 2.14 → 1.95.

**Alternatives**: 366 → 412 slots; 81 briefs' lists changed (the displaced base is skipped; quality plans of other families enter through the existing family rule: 47). **Solves**: +6.6 % (17,052 → 18,180; p50 13 → 15 per brief) — one or two peer realizations per poor primary with a peer. **Runtime, controlled** (same 72 briefs, one process per run, main run three times around the two phases): phase 2 p50 4.12 / p90 11.02 / p95 13.81 / max 23.11 s against main p50 4.05–4.17 / p90 10.97–11.26 / p95 13.81–14.24 / max 23.11–23.36 s. Paired per-brief delta against the best of the three main runs: phase 2 p50 +0.06 s, p90 +0.49 s, p95 +0.82 s, max +1.01 s (ratio p50 1.02, p90 1.19, p95 1.22); phase 1 on the same pairing p50 +0.09 s, p90 +0.32 s, max +1.07 s; a main run against the same best-of-three p90 +0.00 s, max +0.29 s (the noise floor). The p90–p95 tail is the peer realizations on the large briefs that have one.

Backend suite with phase 2: **1230 passed, 9 xfailed, 0 failed**.

## Tests

`tests/vertical_slice/test_quality_repartition.py` (9): the target is not a gate; the reported brief gets a quality candidate beside every normal one with the normal list identical to the tier-off list; the quality candidate squares the master (≤ 1.5), keeps the ensuite's door from the master and the shared bath's from the hall, passes C17/C20/C21, same footprint, every room inside its hard limits; no candidate without an ensuite; the search is bounded; the pipeline primary changes only to its own peer (phase 2), the reported brief is delivered with a square master, a peer that does not beat its base never replaces it; the L arm gets a quality candidate through the generic hook with the same wings and better realized shapes. Updated: `test_vocabulary_is_additive` (the new template field), `_tiers` three-way (bounded candidate set: quality after tier 2), `test_fallback_candidates_come_after_every_normal_one` (the quality marker), `test_no_fallback_attempt_runs_without_a_failure_that_asked_for_its_mechanism` (the quality tier is not a fallback).

Backend suite with phase 1: **1227 passed, 9 xfailed, 0 failed**. With phase 2: see below.

## Left for the next review

The 269 poor primaries without a twin are the topology limit the investigation named: one ensuite per programme, and the double-loaded split puts it in the wrong column. The levers are the wet-semantics variant (a flexible shared bath as a second ensuite), the ensuite sub-row (the 145 ensuites stood on end), or an allocation that keeps the ensuite pair beside the poorest bedroom — each its own review. Open-chain (public-room) pairings as quality moves (26 plans in the replay) were left out by scope.
