# Results: Hub-Organised Private Wing — v1 implementation, measured

**Date**: 2026-09-11 · **Code**: implemented in the working tree on top of `c7216e0`, **not committed** — two hard acceptance gates failed (see §3). Harness: `backend/spikes/failure_log_sweep/` (commit `c7216e0`).

## 1. Non-regression gates — all pass

Through the real service, 420 distinct failure-log scenarios, hub parti disabled (OFF) vs shipped (ON):

| Gate | Result |
|---|---|
| Test suite | **768 passed, 7 skipped, 0 failed** (763 + `test_vocabulary_is_additive` + 4 hub tests) |
| Pre-existing primary designs byte-identical | **112/112** (primary + alternatives: 111/112 — one alternatives list changed) |
| Lost / crashes | 0 / 0 |
| Newly planning scenarios | 0 (the hub is a quality feature; none expected) |
| Refusal codes | unchanged in every bucket (15 / 26 / 87 / 180) |
| Latency, scenarios that already planned | median 1.11 s → 1.11 s, worst regression +0.02 s |
| Latency, total sweep | 531 s → 532 s |
| Existing partis / ROOM_TEMPLATES / Geometry Core | untouched (`test_vocabulary_is_additive` snapshots every existing template row) |
| Forced-first / unforced twin | hub candidates go through `generate_concepts`; `test_hub_root_to_hall_cuts_stay_forced_in_the_twin` pins that only root→HALL cuts stay forced |

## 2. Applicability on the failure log

| | count |
|---|---|
| Scenarios with a hub candidate in `generate_concepts` | **6 / 420** |
| Hub plan realized when the hub is the only candidate offered (`quality_metrics.py --hub-only`) | **2** |
| Hub selected as the delivered plan in production | **0** (area-proximity sort out-ranks it; research R2) |
| Hub appears among a plan's alternatives | 1 |
| Hub rejections — `INSUFFICIENT_WING_AREA` (bedrooms < 3, FLEX/over-capacity, < 2 public rooms) | 287 |
| Hub rejections — `ACCESS_DEGREE_EXCEEDED` (more than 4 rooms need a lobby door) | **124** |
| Hub rejections — `ROW_WIDTH_EXCEEDED` / `COLUMN_DEPTH_EXCEEDED` | 4 / 3 |

The ≥ 3-bedroom briefs in this log almost all carry a safe room and 2–3 wet rooms: 5–7 rooms that need a door on the lobby, against the 4 seats v1's single-lobby tree offers (two flanks + two rooms in the foot band). Research R8 predicted this for the 4BR+safe+3wet case; the sweep shows it is the rule, not the exception.

## 3. Architectural-quality acceptance (spec §6) on the 2 hub plans

| Metric | Target | Hub v1 (2 plans) | All 112 plans after twins | 85 plans before twins |
|---|---|---|---|---|
| Hall long/short ≤ 1.5 | 100 % | **1.1 — 100 %** ✓ | 9.3 — 0 % | 9.4 — 0 % |
| Doors on hall | 4–7 | **5** ✓ | 7 (4–9) | 7 |
| Habitable rooms on envelope | 100 % | **100 %** ✓ | 100 % | 100 % |
| Circulation share | ≤ 14 % | **7 %** ✓ | 10 % (max 14 %) | 11 % |
| Bedroom aspect median | ≤ 1.35 | **1.21** ✓ | 1.41 | 1.26 |
| Master aspect median | ≤ 1.40 | **1.59** ✗ | 1.56 | 1.57 |
| Wet-room adjacency | ≥ 80 % | **0 %** ✗ | 36 % | 40 % |
| Public zone contiguous | (informational) | 0 % (closed-plan briefs) | 36 % | 31 % |

Two gates fail; per the acceptance rule the hub is **not committed**.

### Root causes — structural, not tuning

1. **Wet adjacency 0 %.** The v1 tree (public band in front, lobby wing behind) has no head band: the only band that touches the lobby besides the flanks is the foot band, which seats two rooms. With a master suite the foot reads `[ensuite | master | shared bath]` — the two wet rooms are separated by the master by construction. The references put the wet cluster at the lobby's head; that needs the side-by-side regime (public column beside the wing), deferred in the spec.
2. **Master aspect 1.59.** The foot band's two door-needing rooms meet under the lobby's centre line (so each overlaps it by ≥ 1.2 m). The master therefore spans from its ensuite to the centre line — wide and, at the foot band's ~3.4 m depth, shallow. A third foot seat or a two-room flank would let the master keep its own width; both are v2 changes.
3. **Applicability.** 4 seats. Two-room flanks (bedroom over a bathroom, lobby depth ≈ 4.4 m) would give 6–7 seats and are the smallest v2 step; they push the lobby's area past `HUB_TEMPLATE.max_area_m2` at aspect ≤ 1.5, so that template figure needs re-deriving from the census (TV-room hubs are larger).

### Side observation (twins, not hub)

The 112-plan population after the unforced-twin change is less square than the 85 before it (bedroom 1.41 vs 1.26, wet 36 % vs 40 %): the solver's area-ratio splits produce the rescued plans, and they are proportioned worse than the forced ones. A shape-aware objective for the released cuts is a candidate follow-up.

## 5. v2 — two-room flanks, feasible-window boundaries (2026-09-13, branch `005-hub-v2`)

**What changed** (all in `concept_generator.py`, additive): a flank may stack two rooms (a bedroom
over a wet room, an H split off the root→HALL path, so the twin may re-balance it); the boundary
between the two foot-band rooms, and the width of the first public zone, follow area shares inside
the window where the opening's 1.10 m shared edge is guaranteed (v1 pinned both to the lobby's
edges); the first public zone must reach past the footprint's centre so the entrance lands on its
wall (C16) clear of parking (C11); the hub honours a requested corridor width as its own short side
and declines requests outside 2.4–3.6 m; the hub is inserted LAST so no no-target baseline changes
its plan; `HUB_TEMPLATE.max_area_m2` 12 → 16 (a 3.1 × 4.6 lobby is 14 m²; TV-room hubs in the
references are that size). Tests: **771 passed, 6 skipped, 0 failed** — one former "known limit"
skip (12.5 × 13 m, 3BR + safe room) now plans, through the hub.

**Sweep, 421 scenarios, real service, hub OFF → ON:**

| | v1 | **v2** |
|---|---|---|
| Hub candidate present | 6 | **43** |
| Hub delivered as the primary plan | 0 | **17** |
| Hub candidate present, another parti won | 1 | 10 |
| Plans | 112 → 112 | 117 → **127** (+10; 7 counted at ≥ 80 % of ask) |
| Lost / crashes | 0 / 0 | **0 / 0** |
| Pre-existing primaries byte-identical | 112/112 | 110/117 — **7 replaced by a hub plan** via the area-proximity sort |
| Hub rejections `ACCESS_DEGREE_EXCEEDED` / `COLUMN_DEPTH` / `INSUFFICIENT` | 124 / 3 / 287 | 68 / 20 / 290 |
| Latency, plans that already existed | +0.02 s | median +0.04 s, worst +1.61 s; total +5 % |
| Validation refusals | unchanged | unchanged (4 → 4) |

**Acceptance (spec §6) on the 17 production hub plans, beside the 110 non-hub plans:**

| Metric | Target | **Hub v2 (17)** | Non-hub (110) | Hub v1 (2) |
|---|---|---|---|---|
| Hall long/short ≤ 1.5 | 100 % | **1.4 — 100 %** ✓ | 9.3 — 0 % | 1.1 ✓ |
| Doors on hall | 4–7 | **6 (6–7)** ✓ | 7 (4–9) | 5 ✓ |
| Habitable rooms on envelope | 100 % | **100 %** ✓ | 100 % | 100 % ✓ |
| Circulation share | ≤ 14 % | **8 % (max 10 %)** ✓ | 10 % | 7 % ✓ |
| Wet-room adjacency | ≥ 80 % | **83 %** ✓ | 34 % | **0 %** ✗ |
| Bedroom aspect median | ≤ 1.35 | **1.42** ✗ | 1.50 | 1.21 ✓ |
| Master aspect median | ≤ 1.40 | **1.50** ✗ | 1.60 | 1.59 ✗ |
| Public zone contiguous | (info) | 71 % | 35 % | 0 % |

Hub-only mode (every scenario realized from its hub candidates alone, 24 plans): wet adjacency 74 %,
bedroom 1.62, master 1.59, lobby 1.4 / 100 %, doors 6.

**Reading.** Both v1 failures are structural fixes that worked: wet adjacency 0 % → 83 % (the shared
bath stacks under a flank bedroom, above the ensuite) and the lobby is compact in 100 % of plans.
Six of eight targets pass. Bedroom (1.42) and master (1.50) miss narrowly — and both are *better*
than the plans the hub replaced (1.50 / 1.60), as is every other metric except the safe room
(1.66 vs 1.33) and the kitchen, which stays a strip (2.23) because the public band is still a
1-D chain. Cause of the two misses: flank and foot widths follow area shares; when the lobby is
4.4–4.6 m deep for a stacked flank, a single-room flank beside it becomes 4.6 deep × ~3.2 wide, and
the master's foot slot is wider than deep. A shape-aware share (surplus width toward the room
whose aspect is worst) is the v2.1 lever; it is sizing, not topology, and it must be measured with
the same harness — not tuned.

**7 replaced primaries.** The area-proximity sort prefers the hub when its footprint lands nearer
the requested area. Whether a hub plan should out-rank an area-closer spine plan (spec §11 (c)) is
now a live product question, because it happens in production: for those 7 briefs the delivered
plan is a compact lobby with 83 % wet adjacency instead of a 9.3-aspect spine.

## 6. v2.1 — sizing by shape, measured and NOT accepted (2026-09-13, branch `005-hub-v2.1-sizing`)

Recorded in full on that branch's copy of this file. In one line: sizing the wing by a number-free
shape objective (least squares on log-aspect over flank split, foot boundary, lobby depth) moved
the medians (master 1.61 → 1.08, bedroom 1.57 → 1.36) only by choosing which room is the strip —
safe room 1.66 → 1.76 (8.0 × 4.0 m), more bedrooms above 1.35 (24 → 29 of 43), a guest WC under a
flank outgrowing its ensuite (one product test) — and `hub_sizing_bound.py` showed the wide-shallow
outlines cannot reach < 1.6 by any sizing. The miss is topological.

## 7. v3 Phase 0 — topology bound with access seats and wet adjacency (2026-09-14)

**Tool:** `spikes/failure_log_sweep/hub_topology_bound.py [--wet 2|3] [--grid] [--only T1]`. For
each candidate tree and each of six representative outlines it enumerates every sizing decision
and every admissible foot-band order on a coarse grid, builds the rooms as rectangles and checks
the three facts the gates measure: geometry (template minimums, lobby caps, habitable rooms on the
envelope), access (≥ 1.10 m of shared edge with the lobby for every room that needs a door; ensuite
beside its master) and wet adjacency (M5's rule). Candidates: T1 = v2 (stacked flank); T3 = no
stacking, bath beside the lobby; T4/T4b = hybrid wet stack (bath over the ensuite beside the lobby,
master under both) with two flank bedrooms / with the second bedroom at the foot; T5 = guest bath at
the lobby's head in the front band; T2 = side-by-side, control only.

**3 bedrooms + safe room + 2 wet rooms** (T1 on a 0.25 m grid, the rest 0.5 m):

| | 14.25 × 12.35 | 18 × 12 | 13 × 15 | 12 × 18 | 10 × 20 | 14 × 16 |
|---|---|---|---|---|---|---|
| **T1** seats / wet max | 5/5 · 100 % | 5/5 · 100 % | 5/5 · 100 % | 5/5 · 100 % | 5/5 · 100 % | 5/5 · 100 % |
| **T1** best bed-class aspect, wet ≥ 80 % | **1.65** ✗ | **2.38** ✗ | **1.32** ✓ | **1.28** ✓ | **1.27** ✓ | **1.42** ✗ |
| T1 master / safe at that layout | 1.16 / 1.64 | 1.78 / 2.38 | 1.32 / 1.28 | 1.28 / 1.26 | 1.27 / 1.26 | 1.39 / 1.41 |
| T3 no stacking | access 4/5 | access 4/5 | access 4/5 | access 4/5 | no layout | access 4/5 |
| T4 hybrid wet stack | access 4/5 | access 4/5 | access 4/5 | access 4/5 | no layout | access 4/5 |
| T4b hybrid, BED2 at foot | no layout | access 2/5 | access 2/5 | access 2/5 | access 2/5 | access 2/5 |
| T5 head-band bath | no layout | 1.81, wet 0 % | no layout | no layout | no layout | no layout |
| T2 side-by-side (control) | BED1 interior | BED1 interior | BED1 interior | BED1 interior | no layout | BED1 interior |

**3 wet rooms**, T1: seats 6/6 everywhere but wet adjacency tops out at **67 %** (the third wet room
stacks under the second flank bedroom with nothing wet beside it), and with both flanks stacked
the shape bound is 2.00 / 2.71 / 1.75 / 1.56 / 1.17 / 1.94. T3 and T4 seat 5/6, T4b 3/6; T5 fits
only 18 × 12 (1.81, wet 0 %); T2 fails exposure everywhere.

**What the seats prove.** A band seats at most two door-needing rooms on the lobby's edge (each
needs 1.10 m of a ≤ 3.6 m edge and a room between them would need ≥ 2.6 m), and a flank bedroom
loses its door the moment a bath sits between it and the lobby. For the 5-door brief a three-band
tree has exactly four seats — two flanks, two at the foot — unless it stacks (T1) or puts a room at
the lobby's head (T5, an 18 m front only, bath isolated). Every "no stacking" / "wet cluster
beside the lobby" variant fails access by construction. T1 is the unique three-band tree that
seats five and clusters the wet rooms — and its stack is what costs the lobby band 4.6 m and breaks
the bedroom shapes on the wide outlines.

**Decision gate: no topology passes geometry + access + wet adjacency across the set.** T1 passes
all three on the narrow-deep outlines and fails shape on every outline ≥ 14 m wide. Recommendation
taken forward as feature 008: not a new tree but a *policy* — offer the hub as a peer only where
the bound says the outline can pass, keep it as the last resort elsewhere.

## 8. Feature 008 — hub eligibility by computed feasibility, measured (2026-09-14, branch `008-hub-eligibility`)

**What changed** (concept stage only; `_plan_hub_wing`, templates, Geometry Core untouched):
`hub_bound()` computes, on the engine's own `_hub_allocation` and the lobby widths `_hub_concept`
would try, the Phase 0 bound with door seats and wet adjacency — 1–58 ms per brief, exiting as
soon as a sizing passes the gates. A hub whose bound passes (`ELIGIBLE`) keeps v2's ordering; one
that fails (`LAST_RESORT`) is moved, with its twin, after every other candidate. The rationale
carries the figures. The Phase 0 tool's T1 row now runs through the same function.

**Baseline `30e2312` vs 008, frozen worktrees, 430-scenario log** (the log grew by 4 refused
scenarios during the work; both sides were re-run on the same file):

| | baseline | **008** |
|---|---|---|
| Plans / LOST / GAINED (vs hub OFF, ≥ 80 %) | 107 / 0 / 10 (7) | 107 / 0 / 10 (7) |
| Hub candidates / delivered / other parti won | 44 / 19 / 7 | 44 / **12** / **14** |
| Hub-OFF primaries changed by the hub | 9/97 | **2/97** |
| Primaries byte-identical, 008 vs baseline | — | **100/107** (the 7 displaced hub plans; nothing else) |
| Refusal codes | 38 / 94 / 190 / 1 | identical |
| Test suite | 4 failed (the baseline's own) | **3 failed, all the baseline's**; 0 new (the baseline's 4th, `zoning_pressure_4BR_saferoom`, now passes) |
| Sweep time (`ab.py`, hub OFF → ON, same process) | — | **536 s → 536 s**; medians 1.43 → 1.43 s (planned) and 0.53 → 0.51 s (refused); worst +0.48 s (SC-006 ✓; a first run under five concurrent sweeps read +37 % and was discarded) |

**The 12 remaining hub primaries**: 3 `ELIGIBLE` (13 × 15; 12 × 18 ×2) and 9 `LAST_RESORT` — every
one of the 9 is a hub-only rescue (no other parti plans it), delivered as before. The 7 displaced
primaries reverted to their hub-OFF plans (SC-004: non-hub bedroom median 1.30).

**Quality, by eligibility (`hub_rooms.py`):**

| | baseline hub (19) | 008 eligible (3) | 008 last resort (9) | non-hub (95) |
|---|---|---|---|---|
| Bedroom median | 1.57 | **1.42** ✗ | 1.57 | 1.30 |
| Master median | 1.61 | **1.50** ✗ | 1.61 | 1.55 |
| Safe room median | 1.66 | 1.48 | 1.84 | 1.26 |
| Lobby ≤ 1.5 / doors / exposure / circulation | ✓ | ✓ 1.39 / 6 / 100 % / 8 % | ✓ | — |
| Wet adjacency (hub population) | 79 % | 83 % (12 plans) | | 40 % |

**Reading — the policy works as ordering; the eligible plans still miss the shape gates.** US1/US2
hold exactly (SC-001, SC-002, SC-004, SC-005, SC-006 tests). SC-003 fails: the bound proves a
sizing exists on 12 × 18 with all four bedroom-class rooms ≤ 1.28, but `_plan_hub_wing`'s
area-share sizing delivers 5.15 × 2.8 / 3.45 × 4.6 bedrooms and a 4.8 × 3.2 master (1.42 / 1.50)
on the same outline — the gap between "can be good" and "is good" is the sizing on *eligible*
outlines, where (unlike the wide-shallow case v2.1 measured) a passing sizing demonstrably exists
and the bound has already found it.

**Not merged; stopped for review.** The candidate next step, if wanted, is narrow and already
half-built: on `ELIGIBLE` outlines only, let `_plan_hub_wing` take the sizing `hub_bound` found
(lobby depth, flank split, foot boundary, foot depth) instead of its area shares — measured with
the same harness; last-resort outlines keep v2's sizing.

## 4. Decision

- `HUB_PRIVATE_WING` v1: **not committed**. Left in the working tree (`concept_generator.py`, `test_concept_generator.py`) for the owner to keep on a branch or drop; the harness, plan, research, data model, quickstart, tasks and this report are committed so v2 starts from measured ground.
- Recommended v2 scope, in order: (a) two-room flanks with a re-derived hub max area; (b) the side-by-side regime with a head band for the wet cluster; (c) only then revisit the area-proximity ordering so a hub plan can win when it exists.
