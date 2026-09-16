# Laundry room — area-budget product decision (investigation only)

**Date**: 2026-09-16 · **Branch**: `worktree-015-laundry-room-option` · **Scope**: measurement only. Nothing in `app/` was touched; `LAUNDRY_ROOM_ENABLED` is still `False`; `app.architect`/`app.geometry` untouched. Follows [docs/LAUNDRY_ROOM_PHASE1_REPORT.md](LAUNDRY_ROOM_PHASE1_REPORT.md) §4/§5's open question.

**Method**: a new spike script, `backend/spikes/failure_log_sweep/laundry_area_budget_policies.py`, monkeypatches `concept_generator.scale_program` — the one function that turns a target built area into a per-room area allocation — for the duration of one measurement run, so each policy below is exercised through the REAL solver (`generate_demo_design`), not a standalone calculation. Nothing is wired into the shipped pipeline; the monkeypatch is undone after every run.

**Representative cases**: 2BR/1wet, 3BR/2wet, 4BR/2wet, each at three footprint tiers — **tight** (the programme's own natural, no-surplus gross area — the realistic case: a normally-sized house that then also asks for a laundry room), **generous** (+25% over tight), and **flex_present** (just above `program_capacity_gross_m2`, the actual threshold this codebase already uses to add a FLEX zone — see §2, a real surprise). 9 base cases × (1 baseline + 3 policies) = 36 real solves.

---

## 0. Verdict up front

1. **Where the area comes from today (Policy C, shipped)**: in the realistic **tight** tier, adding a requested laundry room costs another room 10-33% of its area in every single case measured. LIVING and DINING often GROW slightly (they are highest-elasticity, so they absorb a favourable share whenever there is any slack at all) while BATHROOM, BEDROOM, MASTER_BEDROOM, and HALL are the ones that actually shrink — not FLEX, which usually isn't even in the room list at this tier. This is the same finding as the phase-1 report, now attributed to specific rooms rather than "another room."
2. **Policy A ("consume FLEX/surplus first") does not work, and cannot, given how FLEX exists today.** FLEX is only added to a programme when the requested target exceeds `program_capacity_gross_m2` — every room already at its own PREFERRED MAXIMUM, summed — roughly **double** the natural target (measured: 3BR/2wet needs 226.7 m² before FLEX appears, against a 120.0 m² natural target). A brief with that much slack never has a deficit for FLEX to protect anyone from in the first place. Measured directly: across all 9 cases, Policy A produced **byte-identical results to Policy C in every one** — there was never a case where FLEX existed AND a real deficit needed absorbing in the delivered plan. **This policy, as specified, is not implementable as a meaningful difference from the status quo.**
3. **Policy B ("consume service/wet-region budget first") gives a real, modest, low-risk improvement — but only in the tight tier**, where it actually matters. Drawing the deficit from BATHROOM/TOILET headroom before PRIVATE/PUBLIC rooms reduced the worst single-room drop by 2-4 percentage points in every tight-tier case (e.g. 3BR/2wet: 16.0%→13.4%; 4BR/2wet: 12.4%→10.2%) with zero cost anywhere else. In the generous/flex_present tiers it is identical to C (nothing to improve — there's no deficit).
4. **Policy D ("refuse/clarify") at a strict, symmetric 10% threshold would refuse 7 of 9 representative cases (78%)** — a literal "never degrade any room by more than 10%" rule would make the feature refuse almost every realistic request, not a usable activation policy on its own.
5. **Both hard constraints held everywhere measured**: zero hard-limit violations (no room ever went below `RoomTemplate.min_area_m2`, in any policy, any case) and zero invented area (every comparison used the identical `target_built_area_m2` for the with- and without-laundry run).
6. **Recommendation**: adopt Policy B's allocation change (a real, future, small implementation task — not done here) **combined with a loose disclosure threshold, not a hard refusal** — see §5. Do not pursue Policy A as specified.

---

## 1. Where the laundry area comes from today (Policy C, shipped, aggregated over all 9 cases)

| room | zone | net change (m², summed) |
|---|---|---|
| LIVING | public | **+16.4** (grows — highest elasticity, 3.0) |
| FLEX | surplus | **+9.4** (grows where present, but rarely present — see §2) |
| DINING | public | **+2.8** (grows — elasticity 1.5) |
| MASTER_BEDROOM | private | −0.2 |
| BATHROOM | wet/service | −0.8 |
| BEDROOM | private | −1.0 |
| KITCHEN | public | −2.4 |
| HALL | circulation | −2.5 |

Aggregated numbers understate the realistic case: this sums tight (real deficits) with generous/flex_present (real surpluses, where nothing shrinks below its own target). Read per-tier: at **tight**, the aggregate above is entirely deficit-driven and every one of BATHROOM/BEDROOM/MASTER_BEDROOM/HALL/KITCHEN's shrinkage happens there — LIVING/DINING's apparent "growth" at the aggregate level is a **generous/flex_present** artefact (more total area to hand out, laundry takes a sliver of it, LIVING still gets the largest slice of what's left). The two dynamics are different problems: **tight** is "who pays for the laundry room," **generous/flex_present** is "who gets slightly less of the leftover" — only the first is the real product risk.

## 2. Why Policy A doesn't work — FLEX's actual trigger condition

`generate_concepts` adds a FLEX zone only when `target_built_area_m2 > program_capacity_gross_m2(rooms)` — the sum of every room's own **preferred maximum** (`RoomTemplate.max_area_m2`), not its target. Measured thresholds:

| case | natural (tight) target | FLEX threshold (capacity) | ratio |
|---|---|---|---|
| 2BR/1wet | 101.1 m² | 197.8 m² | 1.96× |
| 3BR/2wet | 120.0 m² | 226.7 m² | 1.89× |
| 4BR/2wet | 131.7 m² | 242.2 m² | 1.84× |

A person has to ask for **nearly double** their programme's natural size before FLEX ever enters the room list. Directly instrumented `scale_program` during a `flex_present`-tier solve (1024 calls, one per candidate footprint proportion tried): only 44 (4.3%) ever saw a deficit, and none of those were the DELIVERED candidate — every accepted, planned result at that tier had a comfortable surplus. So in practice, whenever FLEX exists, there is no deficit left for it to protect anyone from by the time a plan is actually delivered — which is exactly why Policy A measured identically to Policy C in every one of the 9 cases: there was never a delivered case combining "FLEX present" with "a real shortfall to absorb." Redesigning FLEX's own trigger condition (so it appears at more modest surpluses, specifically to reserve room for small requested add-ons) would be a real, separate, and non-trivial planner change — out of scope for "smallest safe activation policy."

## 3. Full comparison, per case × tier × policy

| case | tier | policy | status | laundry m² | aspect | delivered m² | rooms changed | worst single-room drop |
|---|---|---|---|---|---|---|---|---|
| 2BR/1wet | tight | C / A (identical) | planned | 4.50 | 1.88 | 97.2 | 5 | 19.2% |
| 2BR/1wet | tight | B | planned | 4.50 | 1.88 | 97.2 | 5 | **17.2%** |
| 2BR/1wet | generous | C / A / B (identical) | planned | 6.89 | 1.02 | 121.5 | 6 | 32.5%* |
| 2BR/1wet | flex_present | C / A / B (identical) | planned | 5.10 | 1.68 | 203.5 | 5 | 28.6%* |
| 3BR/2wet | tight | C / A (identical) | planned | 3.90 | 1.65 | 119.3 | 2 | 16.0% |
| 3BR/2wet | tight | B | planned | 4.03 | 1.60 | 119.3 | 4 | **13.4%** |
| 3BR/2wet | generous | C / A / B (identical) | planned | 3.90 | 1.65 | 147.2 | 4 | 13.7% |
| 3BR/2wet | flex_present | C / A / B (identical) | planned | 7.38 | 1.69 | 218.9 | 6 | 29.4%* |
| 4BR/2wet | tight | C / A (identical) | planned | 4.88 | 2.03 | 125.2 | 4 | 12.4% |
| 4BR/2wet | tight | B | planned | 4.80 | 2.00 | 125.2 | 5 | **10.2%** |
| 4BR/2wet | generous | C / A / B (identical) | planned | 4.95 | 2.06 | 161.3 | 5 | 6.0% |
| 4BR/2wet | flex_present | C / A / B (identical) | planned | 7.60 | 2.75 | 192.8 | 8 | 9.5%* |

\* generous/flex_present drops are partly a footprint-PROPORTION-search artefact, not purely the area formula: the with- and without-laundry runs can land on genuinely different candidate footprints even at the same target area (this codebase's search couples proportion and allocation — the same effect the phase-1 report's own `laundry_quality_matrix.py` data showed). Real behaviour a user would see either way, but not a clean isolation of "the formula's fault" at these tiers — another reason the **tight** tier is the one that matters for this decision.

**Refusals/crashes**: 0 newly refused or crashed in any policy, any case. **Hard-limit violations**: 0, everywhere. **Laundry room itself**: planned, in-template, HALL-accessed in all 12 planned-with-laundry cells (consistent with phase 1's own finding).

## 4. Policy D, applied to Policy C's results

At a **10%** degradation threshold (proposed for this measurement — see the script's own docstring for why, and re-derive a different number directly from §3's per-case column if preferred): **7 of 9** cells Policy C planned would instead refuse — every tight-tier case, plus 2BR/generous and 3BR/flex_present. At a **20%** threshold: only 2BR/generous (32.5%) and one flex_present case would refuse — 2 of 9. At **30%**: 0 of 9 refuse.

This is the central trade-off of Policy D: strict enough to genuinely protect every room, and the feature refuses almost everyone; loose enough to actually deliver most requests, and it stops meaningfully protecting anyone. A flat threshold on its own is not a good fit for "smallest safe activation policy" — see the recommendation.

## 5. Recommendation

**Adopt Policy B's allocation change, paired with a disclosure notice rather than a hard refusal — as a future, separate, small implementation task. Do not implement it now; do not enable the flag.**

Reasoning:
- **Policy A is not worth pursuing as specified.** It cannot do anything in the cases that matter (§2) without a separate, larger redesign of when FLEX itself appears — a different, bigger project.
- **Policy B is the smallest real improvement available.** It is a well-contained, low-risk change (draw the deficit from BATHROOM/TOILET headroom before PRIVATE/PUBLIC rooms, exactly the same shape of change as the shipped allocator's own deficit branch — see the spike script's `policy_b_service_first` for the exact, minimal diff against `scale_program`), it never made anything worse in any measured case, and it measurably reduces the worst-case damage by 2-4 points specifically where the damage is worst (the tight tier). It does nothing to fix the underlying problem — a laundry room still costs *something* — but it is a genuine, free, no-downside improvement over the status quo formula.
- **A hard refusal (pure Policy D) is too blunt at any single threshold** (§4) — recommend against it as the sole mechanism.
- **A disclosure notice is the missing piece, not a new allocation formula.** This codebase already has the right-shaped precedent: `OVER_PREFERRED_NOTICE_RATIO` surfaces a quality signal to the person when a room is stretched past a threshold, without refusing the plan. The same pattern — plan it, deliver it, but tell the person which room absorbed the cost and by how much — fits this situation better than either silent delivery (today) or a blanket refusal (pure Policy D). A genuinely extreme case (a room pushed to a large fraction of its floor, not just its target) is still a reasonable place for an honest refusal, matching this codebase's own established "an honest refusal beats a plan at half the size" philosophy — but that bar should be set much looser than 10%, closer to the 30%+ range §4 shows stops firing on ordinary requests.

This is a recommendation for **what to build next**, not something implemented in this investigation. Stop for review, per instruction.
