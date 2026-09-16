# Multi-Level candidate primary selection — implementation report

**Date**: 2026-09-16 · **Status**: implemented, not yet wired to the product · **Branch**: `017-multi-level-phase1` (worktree `sddproject-017`) · **Builds on**: `MULTI_LEVEL_PHASE_1_IMPLEMENTATION_REPORT.md` (backend foundation, merged into this branch) and `MULTI_LEVEL_CANDIDATE_RANKING_INVESTIGATION_REPORT.md` (the approved policy this module implements)

**Scope, as approved**: carry real per-level warnings on `BuildingCandidate` instead of reconstructing them; thread `HouseConcept` into `plan_buildings` using the existing HARD/PREFERENCE grammar, no second source of truth; implement `select_primary` as a separate, lexicographic (not weighted) function over candidates that already passed every active C and V check; an open-plan trade-off disclosure notice that never overrides the preference. Explicitly **not** implemented: the 34/36 vs 30/36 seam-search gap, wider `plan_level` seam exploration, global building score weights, open-plan semantics changes, validation changes, L multi-level support. **`plan_level`, `level_program.py`'s allocation logic, `validation.py` and `building_validation.py` are untouched** — confirmed via `git diff --stat` below.

---

## 0. What was built

| File | Status | What it is |
|---|---|---|
| `vertical_slice/building_coordinator.py` | **extended**, +42/-4 lines | `BuildingCandidate` gained `ground_warnings`/`upper_warnings` (the real `LevelProgram.warnings`, not reconstructed) and a `warnings` property; `plan_buildings(..., *, concept: HouseConcept \| None = None)` — a HARD-bound `public_private_strategy` now excludes the non-matching allocation from generation entirely (a `BuildingRefusal`, not a ranking penalty), matching how HARD constraints already gate generation elsewhere in this codebase. |
| `vertical_slice/primary_selection.py` | **new**, 239 lines | `select_primary(candidates, program, requested_total_m2, *, concept=None) -> SelectionResult` — the lexicographic policy; `quality_metrics_of`, `preference_violations`, `quality_warning_count` (public helpers a caller can use to explain the ranking); `TradeOffNotice` / `RankedCandidate` / `SelectionResult` dataclasses. |
| `tests/vertical_slice/test_primary_selection.py` | **new**, 147 lines, 12 tests | Warning provenance, `HouseConcept` threading (HARD excludes, PREFERENCE still generates both), selection mechanics (order-independence, valid-only-by-construction), the trade-off notice (fires with structured metadata, never overrides the preference), warning de-duplication. |

```
$ git diff --stat 4bdebd4
 backend/app/vertical_slice/building_coordinator.py     | 46 +++++++++++++--
 backend/app/vertical_slice/primary_selection.py        | 239 ++++++++++++++++
 backend/tests/vertical_slice/test_primary_selection.py | 147 ++++++++++
 3 files changed, 428 insertions(+), 4 deletions(-)
```
No diff in `level_program.py`, `level_planner.py`, `validation.py`, `building_validation.py`, `demo/*`, or `frontend/*`.

---

## 1. Warnings: carried, not reconstructed

`BuildingCandidate` now stores `ground_warnings`/`upper_warnings` straight from the `LevelAllocation`s that produced it (`building_coordinator.py`'s single construction site), exposed as `.warnings = ground_warnings + upper_warnings`. `primary_selection.py` never re-derives a warning from geometry or re-matches warning text to decide what happened — the one exception is *removing* the open-plan reinterpretation warning from the quality-warning count when it has already been counted as an explicit-preference violation (§3), and that removal is **positional** (`ground_warnings[:-1]`, since `_closed_kitchen_program` always appends it last), not a string match, because the warning text has no importable constant to match against.

**A pre-existing property of `level_program.py` surfaced here**: `_split()` builds one shared `warnings` list and hands it to both the ground and upper `LevelProgram`s largely unchanged, so a candidate whose real defect is a single fact (e.g. "no full bathroom on this level") can carry the *same string* in both `ground_warnings` and `upper_warnings`. `quality_warning_count` de-duplicates by `set(ground) | set(upper)` rather than raw length, so this candidate is not penalized twice for one gap. Fixing the duplication at its source in `level_program.py` was explicitly out of scope for this change (item 7: "do not change open-plan semantics") — the workaround is confined to the counting function, not the data.

---

## 2. `HouseConcept` threading

`plan_buildings` takes `concept: HouseConcept | None = None`. The only field it reads is `public_private_strategy`, reusing the existing `is_binding()` HARD/PREFERENCE grammar from Phase 0 — no second copy of the person's preference is introduced:

- **HARD-bound and not `ENGINE`**: the allocation search still runs both A and C internally (unchanged), but any candidate from the non-matching strategy is turned into a `BuildingRefusal("...", "allocation", "HARD_PREFERENCE_EXCLUDED", ...)` instead of a `BuildingCandidate` — it never reaches ranking.
- **PREFERENCE-strength (the default) or `concept is None`**: both A and C still generate freely, exactly as the single-level-unchanged requirement demands; the preference is read later, in `select_primary`'s stage A.

`test_single_level_behaviour_unchanged_when_no_concept_given` confirms `plan_buildings(..., concept=None)` and the no-`concept`-argument call produce the identical candidate family set.

---

## 3. `select_primary` — the lexicographic policy

A separate function, called after `plan_buildings`, never folded into it. Every candidate it receives already passed every active per-level C-check and building-level V-check by construction (`plan_buildings` only ever appends a `BuildingCandidate` after `validate_building(...).ok`) — so `select_primary` performs **no filtering and no re-validation**; this was confirmed directly against the 36-brief matrix (`all_valid_c_v = True` for all 30 feasible briefs, i.e. every ranked candidate for every brief, not just the primary).

The key, stage by stage, exactly as approved — a tuple comparison, never a weighted sum:

```python
(preference_violations, worst_bed_aspect, master_aspect,
 quality_warning_count, total_circ_core_pct, delivered_dist, index)
```

- **A. `preference_violations`** — sum of two independent, structural predicates: `_open_plan_violated` (`program.open_plan_living` true and `candidate.ground_layout == "closed_kitchen"`, read off the field `level_program.py` already sets, never off warning text) and `_strategy_preference_violated` (`concept.public_private_strategy` set at PREFERENCE strength and not matching `candidate.strategy`; HARD-bound mismatches never reach this function at all, per §2).
- **B/C. worst bedroom-class aspect, then master aspect** — measured off `candidate.building.levels[*].design.rooms`, not off which generator path produced the candidate.
- **D. `quality_warning_count`** — de-duplicated remaining warnings, with the already-counted open-plan warning subtracted positionally when stage A already counted it (§1), so nothing is counted under two names.
- **E. `total_circ_core_pct`** — `(HALL + HALL_2 + STAIR net area, both levels) / (total net area)`.
- **F. `delivered_dist`** — `|gross built area / requested area − 1|`.
- **G. `index`** — the candidate's position in `plan_buildings`'s own output order, used only as the final, deterministic tiebreak.

No stage compares `strategy`, `ground_lobby_form`, `retreat` or `k` for its own sake — `test_no_bonus_for_generation_order_strategy_or_lobby_form` proves this directly by reversing the candidate list and asserting the winner and its metrics are unchanged.

---

## 4. The open-plan trade-off notice

The notice's comparison baseline is **the best candidate the same lexicographic key would pick with stage A dropped** (`_lex_key(...)[1:]`) — i.e. exactly "the best valid candidate ignoring the preference," not an arbitrary runner-up. It fires only when:

1. the primary honours `open_plan_living` (is not `_open_plan_violated`) while the quality-only best candidate does not, **and**
2. the primary's worst bedroom-class aspect exceeds `2.0` absolute, or exceeds the quality-only alternative's by `≥ 0.25`.

When it fires, the preference-honouring candidate **stays primary** — the notice only attaches structured metadata (`selected_worst_bed_aspect`, `alternative_worst_bed_aspect`, `alternative_family`) and the approved Hebrew message: *"העדפת חלל ציבורי פתוח נשמרה, אך היא גורמת לחדר שינה צר יותר בתוכנית זו."* `test_trade_off_notice_never_overrides_the_preference` asserts this directly.

---

## 5. Measurement — full 36-brief matrix

Ran `plan_buildings` + `select_primary` (unmodified, real code) over the same 3 bedrooms × 3 wet-rooms × 4 sites matrix as the Phase 1 report, `open_plan_living=True` throughout, no `concept` (so both strategies always compete freely).

**Feasibility**: 30/36 — unchanged from the Phase 1 implementation measurement (the 34/36 vs 30/36 seam-search gap is explicitly out of scope for this change, per item 7, and confirmed untouched by the empty `level_planner.py` diff).

**Primary strategy split**: A (`public_below_private_above`) = 16/30, C (`public_plus_one_bedroom_below`) = 14/30. **Ground layout**: open = 11/30, closed_kitchen = 19/30.

**How often the explicit preference determined the winner**: 11/30 feasible briefs selected the open-ground candidate — every one of these is a case where `open_plan_living` was the deciding factor (a closed-kitchen alternative was always available and, per §4's comparison, was the quality-only best in every one of them). Of those 11, **10/30 crossed the trade-off-disclosure threshold** and carry a `TradeOffNotice`; the remaining 1 open selection was already the quality-only best too (no cost to disclose).

**Trade-off notices (10/30)** — all in the 4BR/1–2-wet and 5BR/2–3-wet briefs (the ones where the open-ground bedroom is genuinely squeezed):

| Brief | selected (open) | alternative (closed) | Δ |
|---|---|---|---|
| 4BR_1wet_regular / wide / deep | 2.135 | 1.696 | 0.439 |
| 4BR_2wet_regular / deep | 2.350 | 1.609 | 0.741 |
| 5BR_2wet_regular | 1.717 | 1.359 | 0.358 |
| 5BR_2wet_wide | 1.656 | 1.324 | 0.332 |
| 5BR_2wet_deep | 1.810 | 1.359 | 0.451 |
| 5BR_3wet_regular | 1.767 | 1.324 | 0.443 |
| 5BR_3wet_deep | 2.000 | 1.324 | 0.676 |

**Before/after** (before = generation-order candidate 0, i.e. what a caller would have gotten pre-ranking; after = selected primary), medians across the 30 feasible briefs:

| Metric | before | after |
|---|---|---|
| worst bedroom-class aspect | 1.737 | 1.734 |
| master aspect | 1.706 | 1.507 |
| delivered (gross/requested) | 1.081 | 1.090 |

Worst-bedroom aspect is essentially flat at the median (expected — the preference stage already dominates 11/30 cases regardless of quality, and generation order 0 is frequently already the best-quality candidate in the rest); master aspect improves materially (1.706 → 1.507) since stage C only ever engages once stage A and B are tied. **Circulation burden** (`total_circ_core_pct`) has no directly comparable "before" figure (candidate 0's circulation was not captured as a like-for-like metric in the Phase 1 report); the selected primaries' own median is 0.224.

**Pareto front**: re-verified this session (median front size 3.0, max 12) — the selected primary is on the Pareto front in 30/30 feasible briefs, which is guaranteed by construction for any lexicographic selection (a lexicographically-first candidate cannot be dominated: domination would require another candidate to be no-worse on every stage and strictly better on one, which would make it lexicographically prior).

**All C/V validity**: confirmed for every ranked candidate in every one of the 30 feasible briefs (`all_valid_c_v = True`), not just the primary.

**Runtime**: median 1620 ms/brief, max 2563 ms — `select_primary` itself is O(n log n) over at most a few dozen candidates; the cost is entirely `plan_buildings`'s own geometry search, unchanged by this work.

---

## 6. Single-level regression

`spikes/failure_log_sweep/snapshot.py --compare` against the frozen pre-Phase-1 baseline (432 contexts, 404 planned):

```
planned before=404  now=404
pre-existing PRIMARY designs byte-identical: 404/404   LOST: 0   GAINED: 0
refusal codes:
PLAN_NOT_REALIZABLE                             before=13  now=13
TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY    before=14  now=14
WET_ROOMS_UNSUPPORTED                           before=1   now=1
```

Zero payload or status changes anywhere in the single-level corpus, as required.

**Full `tests/vertical_slice/` suite**: `527 passed, 9 xfailed` (515 pre-existing + this change's 12 new tests in `test_primary_selection.py`; 0 new failures, xfail count unchanged).

---

## 7. Explicitly out of scope, unaddressed here

Per item 7 of the approval: the 34/36 vs 30/36 seam-search gap, wider `plan_level` seam exploration, global building score weights, open-plan semantics, validation changes, L multi-level support. None of these were touched — `level_planner.py`, `level_program.py`, `validation.py`, and `building_validation.py` all show an empty diff against `4bdebd4`.

---

## 8. Recommendation

The policy is implemented, tested, measured over the full matrix, and regression-clean. As with the Phase 1 report, this is backend-only — no `demo/*` or frontend wiring, matching the approved scope. **Stopping here for review before merge**, per the approval's own instruction.
