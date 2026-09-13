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

**Question.** Can the two failing §6 gates (bedroom ≤ 1.35, master ≤ 1.40) be met by sizing alone —
no topology change, no ranking bonus, no relaxation — with the six passing gates and LOST = 0 kept?

**Diagnosis** (`spikes/failure_log_sweep/hub_rooms.py`, the 17 v2 hub plans' rectangles). Every
v2 width is shared by *area* and every v2 depth is the *minimum* the areas need, the public band
absorbing the rest. On the wide-shallow footprints (10 of 17) that gives the stacked flank 6.4 m
of width — a 6.4 × 2.8 m bedroom (2.29) over a 6.4 × 1.8 m bathroom — beside a 4.2 × 4.6 m
bedroom (1.10), and a 3.2 m-deep foot band holding a 5.65 × 3.2 m master (1.77). On the 10 × 20
fronts the 0.7 m of surplus width goes to the stacked flank, not to the 2.8 × 4.6 m single bedroom
(1.64).

**Change** (`_plan_hub_wing`, additive, feasibility gates unchanged): the wing's own decisions —
flank split, foot-band boundary inside its opening window, lobby depth inside its (net) aspect and
area caps — are searched on the 0.05 m grid for the minimum of a number-free objective, the sum of
ln(long/short)² over the wing's habitable rooms. v2's sizing is a member of every search, and the
gates are evaluated at v2's sizing first, so the candidate set is identical (44/44 hub candidates).
A first cut also searched the foot depth with the public band's zones in the objective; it drained
the band to relieve the kitchen strip (living 1.47 → 1.81, 34 m² bedrooms under the lobby) and
was dropped before the frozen measurement below.

**Measurement discipline.** Another session was editing `programme_variants` in the same working
tree during this work (a bathroom-access guard on the second-ensuite variant: plans 138 → 107 on
today's 426-scenario log). All numbers below therefore come from two frozen worktrees at
`75b31e8` with that edit applied to both: **R** = v2, **C** = v2.1. The R figures differ from §5
(19 hub plans instead of 17; bedroom 1.57, wet adjacency 79 %) because the population changed,
not the hub.

| | R (v2) | **C (v2.1)** |
|---|---|---|
| Plans / hub candidates / hub delivered / other parti won | 107 / 44 / 19 / 7 | 107 / 44 / 19 / 7 |
| Gained vs hub OFF (counted ≥ 80 %) / LOST / crashes | 10 (7) / 0 / 0 | 10 (7) / 0 / 0 |
| Primaries byte-identical, C vs R | — | **93/107** (14 hub plans resized; non-hub plans identical) |
| Refusal codes, validation refusals | 37 / 91 / 190 / 1 | identical |
| Sweep, hub ON | 428 s, worst +0.00 s | 428 s, worst +0.08 s |
| Test suite | 777 passed, **4 failed** (the concurrent edit's) | 776 passed, **5 failed** (+ `test_a_three_wet_room_brief_gets_a_guest_wc_not_twin_bathrooms`) |

**§6 gates on the 19 production hub plans:**

| Metric | Target | R (v2) | **C (v2.1)** |
|---|---|---|---|
| Hall long/short ≤ 1.5 | 100 % | 1.4 — 100 % ✓ | 1.4 — 100 % ✓ |
| Doors on hall | 4–7 | 6 ✓ | 6 ✓ |
| Habitable rooms on envelope | 100 % | 100 % ✓ | 100 % ✓ |
| Circulation share | ≤ 14 % | 8 % ✓ | 9 % ✓ |
| Wet-room adjacency | ≥ 80 % | 79 % | 79 % (unchanged — topology) |
| **Bedroom aspect median** | ≤ 1.35 | 1.57 | **1.36 ✗** — and rooms above 1.35: 24/43 → **29/43** |
| **Master aspect median** | ≤ 1.40 | 1.61 | **1.08 ✓** |
| Safe room aspect median | (M1) | 1.66 | **1.76 ✗** |
| Living / dining / kitchen | (M1) | 1.47 / 1.82 / 2.23 | 1.47 / 1.58 / 1.93 |

**Reading — the gates moved, the strips did not go away.** The master passes because the foot
boundary slides to the master's side of its window and the *other* foot room takes the width: on
14.25 × 12.35 the master goes 5.65 × 3.2 → 3.8 × 4.0 and the safe room 5.3 × 3.2 → **8.0 × 4.0 m**
(2.00); the deeper foot takes 0.95 m from the public band (living 7.5 × 4.5 → 7.5 × 3.55, 2.11).
The bedroom median improves while *more* bedrooms exceed 1.35, and a guest WC stacked under a
flank bedroom grows with the flank (7.9 × 1.5 m, larger than the ensuite — the failing test). On
the 10 × 20 fronts nothing changes: the stacked flank's area-driven width consumes the surplus
before any share is made.

**Root cause — exact, not an impression** (`spikes/failure_log_sweep/hub_sizing_bound.py`): an
exhaustive search over every free sizing decision of the v2 tree (lobby width and depth, flank
split, foot boundary, foot depth), with every room only at its template minimum, gives the best
reachable max-aspect of the four bedroom-class wing rooms per footprint —
**14.25 × 12.35 → 1.64** (living 2.49 at that point), **18 × 12 → 2.29**, both-flanks-stacked
**16.9 × 12 → 2.39**, **14 × 16 → 1.85**; only the narrow-deep footprints are reachable
(12 × 18 → 1.22, 10 × 20 → 1.38). Cause: three full-width bands on a footprint ≤ 12.5 m deep
leave ~4 m per band; the stacked flank fixes the lobby band at ≥ 4.6 m, the 3-room foot band spans
the whole front at 3.2–4 m depth, and its boundary window is tied to the lobby's position, so the
stacked-flank bedroom, the master and the far foot room are coupled — any objective only chooses
which of them is the strip. Half the hub population is wide-shallow, so no sizing passes both
medians without a regression elsewhere.

**Decision.** v2.1 is not merged and not carried on `005-hub-v2`: it fails the bedroom gate,
regresses the safe room and a product test, and the bound shows the miss is the topology's, not
the numbers'. The code and this measurement are parked, reproducible, on `005-hub-v2.1-sizing`;
the two diagnosis scripts are kept in the harness. Per the brief, no v3 and no ranking change
were started. What would change the bound — and is therefore v3 material, not sizing: not
stacking on wide-shallow footprints (the wet room elsewhere), or a foot band that does not span
the whole front (side-by-side regime, spec §11 (b)).

## 4. Decision

- `HUB_PRIVATE_WING` v1: **not committed**. Left in the working tree (`concept_generator.py`, `test_concept_generator.py`) for the owner to keep on a branch or drop; the harness, plan, research, data model, quickstart, tasks and this report are committed so v2 starts from measured ground.
- Recommended v2 scope, in order: (a) two-room flanks with a re-derived hub max area; (b) the side-by-side regime with a head band for the wet cluster; (c) only then revisit the area-proximity ordering so a hub plan can win when it exists.
