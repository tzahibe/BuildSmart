# Results: Engine-Chosen Building Outline — measured

**Branch**: `006-engine-chosen-outline`, cut from `main` at `855a977` · **Date**: 2026-09-13
**Harness**: `backend/spikes/failure_log_sweep/` (`snapshot.py`, `outline_ab.py`), `pytest`.

> The spec's motivating numbers were measured on the `005-hub-v2` working tree (`5fd9474`, hub
> parti present, 424 briefs, 127 planning). `main` has no hub, and the failure log had grown to 426
> briefs by the time the baseline was frozen; the figures below are on that base. The targets in
> spec §4 are re-stated here against it.

## 0. Baseline at `855a977` (before any change)

| | value |
|---|---|
| `snapshot.py --save before.json` | **426 scenarios, 117 planned** |
| `pytest` | **764 passed, 7 skipped** |
| `npm test` (frontend) | recorded at Part B |

## 1. Phase 3 — the engine chooses the outline (US1)

`outline_ab.py --before before.json` on the Phase 3 code (T001–T022). A = every logged context
with its footprint (advanced path); B = the same contexts without one (main flow). `pytest`:
**790 passed, 6 skipped, 0 failed** (764 + the new tests).

| Gate | Target | Measured | |
|---|---|---|---|
| SC-005 advanced-path primaries byte-identical to `before.json` | 117/117 | **117/117**, LOST 0 | ✓ |
| SC-001 briefs receiving a plan, main flow | ≥ 250 | **257 / 426** (before: 117) | ✓ |
| Main-flow non-regression: briefs planned before, not planned in B | 0 + named exceptions | **2**, both predicted person-only briefs: 13.0×24.0 bd2 wet1 safe1 ask 312 (over-capacity); 12.5×14.5 bd6 wet2 safe1 ask 181 | ✓ (named) |
| SC-002 first-plan gross ÷ requested, briefs that planned before | median ≥ 0.95 | **0.975** (≥ 0.95 in 66/115) | ✓ |
| SC-004 shown plans failing validation | 0 | **0** (A and B) | ✓ |
| SC-007 refusals naming an outline | 0 | **0**; of 186 over-capacity refusals before, 44 now plan, **142/142** still refused keep the capacity diagnosis | ✓ |
| Crashes | 0 | 0 / 0 | ✓ |
| SC-003 briefs with ≥ 2 families shown | ≥ 60 | A 18, **B 31** / 117 | Phase 4 gate — alternatives are still same-outline (today's rule) |
| SC-006 same-family + same-outline pairs shown | 0 | **456** | Phase 4 gate — same reason |
| SC-008 latency median, all briefs | ≤ 4× before | A **2.47 s**, B **4.31 s**; before ≈ 1.25 s (531 s / 420) | B ≈ 3.5× ✓, see §1.2 |

Rescued in the main flow: **142** briefs refused before now plan, gross ÷ requested median **0.97**
(105 of them ≥ 0.90). The advanced path rescues the same 142 through its engine fallback.

### 1.1 What Phase 3 does and does not do

- Primary = the validated plan nearest the requested area across all outlines; family is not an
  input (asserted by `test_demo_outline_selection.py`). With an explicit outline that plans, its own
  primary is first and byte-identical — including today's alternatives.
- With an explicit outline, engine outlines are planned **only if it fails** (same cost profile as
  the retired `_outline_that_plans`); without one, all four are planned.
- `_outline_that_plans` and the "מתאר של X×Y … כן מתאפשר" sentence are gone (R7). A failed explicit
  outline that an engine outline rescues returns a **plan** with the note "המתאר שהזנת … לא אפשר
  לסדר את החדרים; מוצג מתאר אחר באותו שטח" (FR-008).
- Shown plans are capped at three (spec FR-004); Phase 4 chooses them across outlines by family.

### 1.2 Latency — the decision point for the owner

| population | before | A (advanced) | B (main flow) |
|---|---|---|---|
| briefs that planned before (117) | ≈ 1.1 s | **1.51 s** | **6.13 s** |
| briefs refused before (309) | ≈ 0.5 s (0.09 s without the outline search) | **4.04 s** | 3.08 s |
| all | ≈ 1.25 s | 2.47 s | 4.31 s; worst 22.2 s |
| one outline run (B) | — | — | median 1.42 s (planned 1.49 s / refused 1.00 s) |

Two effects, both structural and both honest to report rather than tune away here:

1. **Main flow, briefs that plan: ~4×** (1.5 s → 6.1 s). Every outline is run with
   `max_alternatives=3` (up to 8 extra solves each), although only the primary's outline needs
   them in Phase 3. Running the four outlines on the fast path (`max_alternatives=0`) and re-running
   only the chosen outline for alternatives would bring this to ≈ 4 × 0.4 s + 1.5 s ≈ 3 s without
   touching `run_general` (it is an argument, not a change). Deliberately **not done** here: Phase 4
   needs alternatives from more than one outline, so where to spend them is Phase 4's decision.
2. **Refusals: ~4–8× slower** (0.5 s → 3–4 s). Before, the outline search skipped the 164
   capacity refusals and stopped at the first outline that planned; now every refused brief plans
   all four outlines to the end. That is what buys the 142 rescues (44 of them over-capacity briefs
   that FLEX can absorb at another shape), so a capacity short-circuit would lose plans. The cost
   falls on the requests that end with nothing.

Recommended reading: SC-008 passes on the letter (3.5× overall) and fails the spirit for the person
whose brief already planned (4.1×). Part C's preview addresses the perceived wait; the
fast-path-then-alternatives change above addresses the real one and belongs to Phase 4.

## 2. Phase 4 — plans shown are different houses (US2) + the latency fast-path

Changes since §1 (owner instruction 2026-09-14): engine outlines are surveyed on the fast path
(`max_alternatives=0`), the primary outline is chosen among the outlines' own primaries by the
area-only rule, only that outline is re-run for alternatives; the shown alternatives are chosen from
that outline's alternatives plus the other outlines' primaries — unseen family first, then unseen
outline, never the same outline re-proportioned. `run_general` unchanged; family is a display key
only (`test_a_rarer_family_nearer_the_target_still_does_not_become_primary`). `pytest`: **797
passed, 6 skipped, 0 failed**.

| Gate | Target | §1 (Phase 3) | **§2 (Phase 4)** | |
|---|---|---|---|---|
| SC-005 advanced primaries byte-identical | 117/117 | 117/117 | **117/117**, LOST 0 | ✓ |
| SC-001 main flow plans | ≥ 250 | 257 | **257 / 426** | ✓ |
| Main-flow non-regression | 0 + named | 2 named | **2**, the same two person-only briefs | ✓ |
| SC-002 first-plan gross ÷ requested (planned before) | median ≥ 0.95 | 0.975 | **0.975** (≥ 0.95: 66/115) | ✓ |
| SC-003 briefs with ≥ 2 families shown (of 117) | ≥ 48 on `main` (restated, see §2.1) | 31 | **50** (A: 20) | ✓ |
| SC-004 shown plans failing validation | 0 | 0 | **0** | ✓ |
| SC-006 same-family + same-outline pairs | 0 | 456 | **0** | ✓ |
| SC-007 refusals naming an outline · capacity diagnosis kept | 0 · all | 0 · 142/142 | **0 · 142/142** | ✓ |
| Crashes | 0 | 0 | **0 / 0** | ✓ |

Latency (medians, seconds; "before" from the frozen sweep ≈ 1.1 s planned / ≈ 0.5 s refused):

| population | before | A advanced §1 → **§2** | B main flow §1 → **§2** |
|---|---|---|---|
| briefs that planned before (117) | ≈ 1.1 | 1.51 → **1.20** | 6.13 → **4.11** (p90 9.3, max 18.7) |
| briefs refused before (309) | ≈ 0.5 | 4.04 → **3.05** | 3.08 → **2.80** |
| all | ≈ 1.25 | 2.47 → **1.95** | 4.31 → **3.05** |
| B, briefs that plan / that are refused | | | 4.39 / 0.60 |

SC-008 (≤ 4× before, all briefs): B 3.05 s ≈ 2.4× ✓; for briefs that already planned, 4.11 s ≈ 3.4×
of A's 1.20 s. The §1 A figures were inflated by a test suite running concurrently; §2 ran alone.

What the shown alternatives now are (B, all 257 planned briefs, 359 alternatives): 111 other
outline + other family · 81 same outline + other family · 167 other outline + same family
(a different house size/shape of the same organisation) · **0** same outline + same family.

### 2.1 SC-003 — 50, not 60: the target was set on a different base

The spec's "69 of 127" (and the ≥ 60 target) was measured on the `005-hub-v2` tree, counting
families among **five** outline primaries — the person's plus four engine shapes — with the hub
parti present. Re-counting that same measurement under this feature's actual conditions:

| condition | briefs with ≥ 2 families among outline primaries |
|---|---|
| 5 outlines incl. person's, hub present (spec figure) | 69 / 127 |
| 4 engine outlines only, hub present | 59 / 127 |
| 4 engine outlines only, **hub plans excluded** | **48 / 127** |
| this branch (`main`, no hub), 4 engine outlines, measured | **50 / 117** |

So 50/117 is at the ceiling this design has on `main`: the outline search cannot manufacture a
second family where the generator offers one (spec §1 already said outline shape does not switch
family). The remaining diversity comes from the concept vocabulary — the hub parti on `005-hub-v2`
is worth ~+11 briefs here once merged, and the forced-cut experiment in the diagnosis is the other
lever. **Owner decision 2026-09-14**: SC-003 is restated against the actual 006 baseline — threshold
**≥ 48 on `main`**; measured **50/117 → PASS**. The hub parti may raise this further when it lands;
it is not a dependency of 006. Phase 4 accepted.

### 2.2 Advanced path — fewer plans shown

A (explicit outline) now shows 1 plan in 97/117 briefs, 2 in 16, 3 in 4 (before this phase most
of those briefs showed three re-proportioned twins). The primary is byte-identical; the strip lost
its duplicates. This is the spec's intent (FR-004) but it is a visible change for anyone using the
advanced path, and it is the reason the alternatives list is not part of the byte-identical gate.
**Owner decision 2026-09-14**: accepted — the leaner strip stays; same-family re-proportioned twins
are not reintroduced to raise the count; the explicit outline remains authoritative.
