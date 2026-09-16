# Multi-Level Phase 1 — implementation report

**Date**: 2026-09-16 · **Status**: implemented, not yet wired to the product · **Branch**: `017-multi-level-phase1` (worktree `sddproject-017`, from `main` @ `be8c0ca`) · **Builds on**: `MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` and `MULTI_LEVEL_PHASE_1_FOLLOWUP_REPORT.md` (the design baseline; both research-only, no code)

**Scope, as approved**: exactly 2 floors, a shared pinned straight-stair `VerticalCore`, `SHRUNK` band on the ground / `FULL` on the upper, `ABSORBED` (V2) offered on the ground only where eligible, allocations A and C as separate candidates (no ranking between them), the building-level wet-room invariant with a level-local warning instead of a per-level refusal, total built area shared across both floors, and Building-level V validation kept separate from per-level C validation. Explicitly **not** implemented: A-vs-C ranking, `V5` (the shifted-flight band), `SHRUNK`/`ABSORBED` on the upper level, L-shaped massing, 3+ floors, other stair types, elevators, any UI/`demo/*` wiring. **The ordinary single-level planner is untouched** — `concept_generator.py`, `general_pipeline.py`, `demo/*` and the frontend have zero diff; every new capability is reached only through the new modules below, called directly (as the investigation reports were, and as `run_general` is called directly in tests) — nothing here is on the live product's request path.

---

## 0. What was built

| File | Status | What it is |
|---|---|---|
| `vertical_slice/level_program.py` | **new**, 220 lines | `allocate_levels(program) -> (LevelAllocation, ...)` — allocations A (`PUBLIC_BELOW_PRIVATE_ABOVE`) and C (`PUBLIC_PLUS_ONE_BEDROOM_BELOW`, tried OPEN then `closed_fallback`), the building-level wet-room gate (`check_wet_room_invariants`, unchanged, called once), and the level-local "no full bathroom" warning. |
| `vertical_slice/level_planner.py` | **new**, 560 lines | `plan_level(...)` — the pinned core-band layout (`CoreLobbyForm.FULL/SHRUNK/ABSORBED`), a second entry point into `concept_generator`'s row/column/spec machinery, reused unchanged. |
| `vertical_slice/vertical.py` | **extended**, +65 lines | Stair geometry constants (`RISER_M`, `GOING_M`, `ENTRY_ZONE_M`), `VerticalCore.realize(...)` building the core from two solved levels. |
| `vertical_slice/validation.py` | **extended**, additive params | `validate(..., entry_seed="OUTSIDE", skip_site_checks=False)` — both default to exactly today's single-storey behaviour. |
| `vertical_slice/building_validation.py` | **extended**, +180 lines | `LevelRealization`, and V1/V3/V4/V5/V8 alongside the existing V2/V7 — run only when the caller passes two `LevelRealization`s (and `program` for V8); every Phase 0 call site is unaffected. |
| `vertical_slice/building_coordinator.py` | **new**, 390 lines | `plan_buildings(program, plot, total_area) -> CoordinatorResult` — the joint search: allocation × ground outline × ground lobby-form × upper massing × upper strip split (`k`), each candidate proven by the unchanged per-level C-checks and the new building-level V-checks. |
| `tests/vertical_slice/test_level_program.py`, `test_level_planner.py`, `test_building_validation_phase1.py`, `test_building_coordinator.py` | **new**, 382 lines, 47 tests | Unit and integration coverage of every module above, including two full end-to-end buildings solved through Geometry Core. |

**Nothing else changed.** `git diff --stat be8c0ca` (this branch's own base — `main` has since advanced with unrelated work from another session, so a diff against `main`'s current tip would show that work too): 6 files in `app/vertical_slice/`, 3 new + 1 extended; 0 files in `demo/`, `app/design`, `app/geometry`, `app/architect`, or `frontend/`.

---

## 1. The core band, as implemented

Exactly the mechanism measured in the two investigation reports, ported to production types:

```
CoreLobbyForm.SHRUNK (ground, default)        CoreLobbyForm.FULL (upper, default)
┌────────────────────────────────┐            ┌────────────────────────────────┐
│ strip room (front)              │            │  HALL_2 (lobby, full band)      │
├──────────┬───────────────────────┤            ├───────────┬────────────────────┤
│ STAIR    │  HALL (corridor,     │            │  STAIR    │ HALL (corridor,   │
│ (rear)   │  full remaining      │            │  (rear,   │ full remaining    │
│          │  depth fh-lobby)     │            │  s x L)   │ depth fh-lobby)   │
└──────────┴───────────────────────┘            └───────────┴────────────────────┘

CoreLobbyForm.ABSORBED (ground only, gated by `eligible_for_absorbed`)
┌────────────────────────────────┐
│ front rows (open-plan, full    │
│ column width incl. the strip)  │
├────────────────┬────────────────┤
│ rear rows       │ STAIR │ HALL  │
│ (open-plan      │ (s×L) │ (c×fh)│
│ members only)   │       │        │
└────────────────┴────────────────┘
```

`StairSeat` (`strip_w_m=1.2, corridor_w_m=1.4`, `floor_to_floor_m=3.0`) is the default and only seat used in this phase's matrix — a seat search was not part of the approved scope. `vertical.straight_flight_length_m(3.0) = 4.6 m` (17 risers × 0.175 m, 16 goings × 0.28 m, PARAMETER · UNVERIFIED exactly as the investigation reports state).

**`eligible_for_absorbed`** — the "access validity proves the lobby edge is unnecessary" gate the approval asked for — is a two-part test: (1) a structural precondition, computed before any geometry: the level has ≥ 2 open-plan public rooms, and every strip row *behind* the first one is itself an open-plan member (so it may legitimately recess behind the flight without a door); (2) the actual proof is left to the unchanged C6/C13 on the geometry `plan_level` produces — the precondition only decides whether `ABSORBED` is *attempted*, never whether it is *accepted*. A closed-kitchen ground is still eligible for its LIVING+DINING open-plan pair (KITCHEN, closed, plays no part) — this was the one refinement to the approved wording actually needed to make `ABSORBED` production-real rather than always-empty (§3).

---

## 2. Two bugs found and fixed while wiring this to real geometry

Both were found by the "solve every candidate through Geometry Core" discipline every module in this codebase applies — a candidate that merely *plans* (passes the pre-checks) is not trusted until it *solves*.

1. **A room's circulation neighbour depends on where it sits, not which column it's in.** The lobby room (`HALL_2`) spans the *whole* band width in the tree — both the strip and the corridor side — so a corridor-side room at the front of its column genuinely borders the lobby, exactly as a strip-side one does. An early version special-cased "the corridor column always borders `HALL`", which produced access edges (`HALL_2 → KITCHEN`) the declared tree could not realize and access edges (`HALL → BEDROOM_1`) the realized geometry did not support (C5/C13 failures on plans that had otherwise solved). Fixed by measuring both columns' rows against the same `lobby_depth` threshold — no per-column exemption.
2. **The reused guest WC was planned in two places at once.** When `SHRUNK`'s strip room is the programme's own guest WC (rather than an engine `STORAGE` room), the WC needs to be *moved out* of the corridor-side room list — an early version left it in both, so the same zone id appeared in two rows of the tree, and Geometry Core reported nonsensical forced-split failures (`"TOILET_1 cannot be 4.55x1.4 m"` — an east-column width on a strip-column room). This was the single largest driver of the matrix's improvement (§4): fixing it took the 36-brief survey from 17/36 to 30/36 feasible, because 3-wet-room briefs (which make the guest WC eligible for reuse on almost every outline) were refusing on this defect specifically, not on any real geometric limit.

Both are now covered by regression tests (`test_level_planner.py`'s WC-reuse test solves through Geometry Core and asserts no `SROOM` was fabricated; the closed-kitchen KITCHEN/BEDROOM tests assert the correct hall assignment).

---

## 3. One deliberate refinement to the approved wording

**"`ABSORBED` only when the selected allocation has a genuinely open public topology"** was read literally at first as "only `GroundLayout.OPEN`" (the un-closed layout) — which made `ABSORBED` almost never eligible in practice, because `OPEN`'s three-room strip (LIVING+DINING+KITCHEN) rarely fits a 4.6 m flight's rear block (measured in the follow-up report §1.4: DINING+KITCHEN together need 5.4–6.7 m of stacked depth). The closed-kitchen ground *also* has a genuinely open public group — LIVING+DINING, with KITCHEN closed and moved out of the strip entirely — and that two-room (in practice, one-*trailing*-room) group is exactly the case the follow-up report measured as working (§1.4's "a single trailing row... fits"). `eligible_for_absorbed` was implemented to check "does this level have an open-plan group with an eligible trailing block", not "is the ground layout literally `OPEN`" — this is what makes `ABSORBED` real in the matrix (4/30 feasible buildings, §4) rather than a code path that never fires. This is a mechanism decision, not a scope expansion: no new lobby form, no relaxed access rule, no ranking of `ABSORBED` above `SHRUNK`.

---

## 4. Measured — the 36-brief matrix

Same setup as both investigation reports: 3/4/5 bedrooms × 1/2/3 wet rooms × regular (20×24) / narrow (15×30) / wide (26×20) / deep (18×32) sites. `plan_buildings(..., stop_at_first=True)` — the fast path a production caller wants — searching allocation A then C, `SHRUNK` then `ABSORBED` (when eligible) on the ground, 4 outline ratios, retreats `{same, W1, W2, E1}`, `k ∈ {0, 1, 2}` on the upper, the standard 4-tier sizing fallback (normal → deficit → over-preferred → both) at each step. **No quality ranking is applied** — this is the *first* valid building the search order reaches, not the best one; a Building-level ranking is explicitly out of this phase's scope.

### 4.1 Headline

| | This implementation | Investigation follow-up report (wider, exploratory search) |
|---|---|---|
| **Complete buildings / 36** | **30/36** | 34/36 |
| by bedrooms (3/4/5) | 11/10/9 | 11/12/11 |
| by wet rooms (1/2/3) | 10/11/9 | 11/12/11 |
| Circulation L0 median (p90) | 14.9% (15.7%) | 13% (17%, curated selection) |
| Circulation L1 median (p90) | 21.0% (24.5%) | 20% (24%) |
| Stair % of total | 4.6% | 5% |
| Delivered / requested median (range) | 108% (99–115%) | 105% (94–112%) |
| Bedroom aspect median (>1.5) | 1.28 (26%) | 1.17 (18%) |
| Master aspect median (>1.5) | **1.71 (60%)** | 1.50 (44%) |
| Runtime (fast path) | 231 ms median, 1.15 s max | not comparable (survey mode) |

### 4.2 Explaining every delta from the research harness

- **30/36 vs 34/36 — narrower search, by design.** All 6 infeasible briefs are **narrow (15×30, 9 m buildable width) sites** — the same structural width floor the follow-up report named (§4.3: `bedroom column ≥ 3.2 + band 2.6 + bath column ≥ 2.8 = 8.6 m` minimum, tight against a 9 m site). The investigation's harness tried a wider set of seats and band combinations per brief (an exploratory sweep); this implementation searches one seat and the three approved lobby forms, which is a materially smaller space on the sites that were already marginal. This is not a new limitation — it is the *same* limitation, reached with less search effort by design (`stop_at_first=True`, 4 outlines, no seat search).
- **Master aspect 60% > 1.5 vs 44% — no quality selection, by design.** The follow-up report's 44% figure is from a *curated* selection (best-per-brief, worst-aspect-first tie-break, explicitly built to show what quality-aware ranking would deliver). This implementation returns the *first* valid building the search order reaches (`k=1` before `k=2`, `same` retreat before a real one) — exactly the approved scope ("no global A vs C ranking yet" extends naturally to "no quality ranking within a family yet" either). The gap is the expected, quantified cost of not yet ranking — not a defect.
- **Delivered 108% vs 105%** — a small, expected consequence of the same "first, not best" selection; both are within the tracking behaviour `_proportions` already has for the single-storey path.
- **Runtime**: 231 ms median per *complete building* (including every refused attempt along the way) is well within an interactive budget; the max (1.15 s, the 5BR/1-wet family) is the same family the follow-up report flagged as the hardest (no ensuite forces a deep master).

### 4.3 A/C, lobby-form and refusal breakdown

| | |
|---|---|
| Allocation chosen | A: 27/30 · C: 3/30 (A is tried first and usually succeeds — matches "no ranking," not "A is better") |
| Ground layout | closed-kitchen: 30/30 (every completed building used the closed-kitchen ground; open-plan/`ABSORBED` completed on rectangles that still count as `closed_kitchen`'s LIVING+DINING group, §3 — a *genuinely open 3-room* ground plus `ABSORBED` was not reached by the search order used here) |
| Ground lobby form | `SHRUNK`: 26/30 · `ABSORBED`: 4/30 |
| Retreat | `same`: 17 · `W1`: 12 · `E1`: 1 · `W2`: 0 |
| Refusal totals (fast path, all 36 briefs, stops accumulating at each brief's first success) | 704 total; 565 inside the 30 successful briefs (median 12/brief before success), 139 inside the 6 infeasible ones (full search exhausted) |
| Refusal stage + reason, full survey of the 6 infeasible (narrow-site) briefs | upper: 116 (`COLUMN_WIDTH_EXCEEDED` 83, `ROOM_ABOVE_MAXIMUM_AREA` 19, `SEAM_PINNED_OUTSIDE_WINDOW` 9, `COLUMN_DEPTH_EXCEEDED` 4, `STAIR_BLOCKS_FRONTAGE` 1) · ground: 23 (`ROOM_ABOVE_MAXIMUM_AREA` 10, `COLUMN_DEPTH_EXCEEDED` 6, `ROW_WIDTH_EXCEEDED` 4, `GEOMETRY_INFEASIBLE` 3) — `COLUMN_WIDTH_EXCEEDED` on the upper dominates, matching §4.2's width-floor explanation exactly: the 9 m buildable width cannot hold `bedroom column + band + bath column` at any seam once a retreat narrows it further |

### 4.4 The C/V check ledger

Across every building in the matrix: **every per-level C-check that ran, ran unchanged** (C1–C9, C13, C17, C20–C22 on both levels; C10–C12/C16/C18 on the ground only; C14 absent from the ledger since no `CorridorRequirement` was set in this matrix). **Every Building-level V-check ran and passed on every completed building**: V1 (core identical), V2 (containment), V3 (no overlap), V4 (reachability across both levels), V5 (entry/arrival face circulation), V7 (area accounting), V8 (every requested room exactly once). Zero V failures across all 30 completed buildings — the coordinator never offers a candidate whose C-checks pass but whose V-checks do not, because it does not stop searching until both hold.

---

## 5. Regression — the ordinary single-level path

- **Full backend suite**: `1226 passed, 9 xfailed, 4 failed` before AND after every change in this phase — the 4 failures are `tests/test_local_gateway.py` (`ModuleNotFoundError: torch`, an environment gap unrelated to this work, pre-existing on `main`). **Zero tests newly broken.**
- **432-context single-level snapshot** (`spikes/failure_log_sweep/snapshot.py`, the standard byte-identity gate every prior phase in this codebase used): saved on `main` @ `be8c0ca` before any change in this branch (404/432 planned), compared against the same 432 contexts after every change in this report:

  ```
  planned before=404  now=404
  pre-existing PRIMARY designs byte-identical: 404/404   LOST: 0   GAINED: 0
  refusal codes:
    PLAN_NOT_REALIZABLE                                  before=  13  now=  13
    TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY         before=  14  now=  14
    WET_ROOMS_UNSUPPORTED                                before=   1  now=   1
  ```

  **Every one of the 404 pre-existing single-storey designs is byte-for-byte identical**, nothing was lost, nothing gained, and every refusal code fires the same number of times. This is the expected result given the mechanism (§0): the single-storey request path (`concept_generator.generate_concepts`, `general_pipeline.run_general`, `demo/*`) has zero diff and imports none of the four new/extended Phase 1 modules — but it is now measured, not merely inferred from the diff.
- **`tests/vertical_slice/` in full**: `515 passed, 9 xfailed` (the same 9 xfails as before this branch) — every existing test in the vertical slice, plus the 47 new Phase 1 tests, in one run.

---

## 6. Not implemented (as approved) and why the boundary was kept

| Excluded | Where the boundary actually sits in the code |
|---|---|
| A vs C ranking | `plan_buildings` returns every valid `BuildingCandidate` it finds, tagged with `.family`; nothing compares them. §4.3 shows A dominates only because it is tried first and the search stops at the first success — not because anything judged it better. |
| `V5` (shifted-flight band) | `CoreLobbyForm` has exactly three members: `FULL`, `SHRUNK`, `ABSORBED`. `V5` from the follow-up report was measured and explicitly dominated by `SHRUNK` — not ported. |
| `SHRUNK`/`ABSORBED` on the upper | The coordinator calls `plan_level(..., CoreLobbyForm.FULL, kind="upper", ...)` unconditionally — the only place this choice is made. `level_planner.plan_level` itself is generic over all three forms (nothing in its own code refuses `SHRUNK`/`ABSORBED` on an upper level), so extending this later is a one-line change in the coordinator, not a new mechanism. |
| L-shaped massing | `Massing` still takes one region per level (the pinned core-band tree assumes a single `Wing`); `l_parti.py` was not touched or imported anywhere in this phase. |
| 3+ floors | `building_coordinator.py` hard-codes "ground" and "upper" throughout (two calls, two realize functions); `Building`/`LevelPlan`/`Massing` from Phase 0 already generalise to N levels, but the coordinator's search loop does not. |
| Other stair types | `StairArchetype.STRAIGHT` is the only one `vertical.straight_flight_length_m` computes for; `L_SHAPED`/`U_HALF_LANDING` remain declared, unused enum members from Phase 0. |
| Elevators | No `VerticalCoreKind` other than `STAIR` exists; nothing in this phase reads or writes one. |
| UI enablement | `demo/scope.py`'s `SUPPORTED_FLOORS = 1` is untouched; `demo/service.py`, `demo/contract.py` and every frontend file have zero diff. `plan_buildings` is reachable only by importing `app.vertical_slice.building_coordinator` directly, exactly as `run_general` is reachable by tests and the investigation reports' scratch harnesses — not through any request the live product serves. |

---

## 7. Stop for review

Every valid `Building` `plan_buildings` finds is returned, untouched, with the allocation/lobby-form/outline/retreat/`k` that produced it — **no candidate is preferred over another**. The decision this report deliberately leaves open, per the approved scope:

**Which of the 30 completed buildings' candidates becomes the primary a person would see, when a brief admits more than one** (allocation A vs C where both plan; `SHRUNK` vs `ABSORBED` where both plan; which `k`, which retreat) — this needs an explicit product ranking rule (nearest requested area? the follow-up report's worst-bedroom-aspect-first curation? a named priority order?) and is exactly the kind of decision `stop_at_first=True`'s search order should not be silently mistaken for. Nothing here should be treated as "A is primary" or "the first-found building is best" — §4.2's own delta (60% vs 44% oversized masters) is the measured cost of that not being decided yet.

*End of report.*
