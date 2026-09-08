# Geometry Core Proof Spike — Result

**Verdict: the core assumption holds on all four fixtures. 44/44 proofs pass.**

Fable adversarial review accepted the original 3-fixture spike as **GO WITH PATCHES** and
required exactly 5 proof patches before Vertical Slice (§8). All 5 are implemented below;
no engine redesign, no scope expansion.

| | |
|---|---|
| Claim under test | `PRIVATE_HOUSE_V1_ENGINE_DECISION.md` §3 + §7 — slicing tree + shape curves + wall thickness known **before** dimensioning |
| Fixtures | rectangle · L house · open-plan + safe room · **branching hall (new)** |
| Result | 4/4 realized · 44/44 proofs pass (11 proofs × 4 fixtures) · 34/34 regression tests pass |
| Solve time | 15 / 20 / 54 / 27 ms |
| Status | **SPIKE CODE.** Not production. Excluded from the production suite by `backend/pyproject.toml`'s `testpaths` |

```bash
cd backend/spikes/geometry_core
python3 run_spike.py                     # full report
python3 -m pytest test_spike.py -q       # regression gate
```

Nothing here imports `app/`, and `app/` must never import this.

---

## 1. Corrections applied before the spike

| # | Correction | Where | Exercised? |
|---|---|---|---|
| 1 | `DesiredAccessTopology` distinguishes `DOOR` / `OPEN_CONNECTION` / `CASED_OPENING` | `model.ConnectionKind` | **Yes** — proof P8 |
| 2 | LOOSE furniture is movable at placement but **still counts** toward final circulation clearance | `model.Mobility` | Encoded, **not exercised** — furniture placement is outside the geometry core |
| 3 | Garden/terrace are explicit classifications; a remainder is `UNCLASSIFIED_REMAINDER` | `model.OutdoorRegion` | **Yes** — F2's L-shaped bounding-box remainder stays unclassified |

---

## 2. Results

| Fixture | Gross | Net | Net/Gross | Wall iterations | Solve |
|---|---|---|---|---|---|
| F1 rectangle | 104.50 m² | 95.33 m² | 0.912 | **1** | 15 ms |
| F2 L house | 134.25 m² | 123.11 m² | 0.917 | **1** | 20 ms |
| F3 open plan + safe room | 137.50 m² | 124.15 m² | 0.903 | **2** | 54 ms |
| F4 branching hall (new, §8 patch 3) | 121.00 m² | 111.03 m² | 0.918 | **1** | 27 ms |

All eleven proofs pass on all four: full tiling · no overlap · no unassigned interior · area
tolerance · min short side + aspect · thickness-aware net area · required adjacency/access ·
open plan without artificial doors · declared seams real · corridor-joint width continuity
(P10, new) · per-role minimum furniture envelope (P11, new).

### F3 output (the hardest case)

```
zone             centerline        net w×d   net m²  walls (N,E,S,W)
LIVING         6.40×6.25      6.20×6.10       37.82  Xp·X
DINING         3.20×4.75      3.05×4.60       14.03  ··XX
KITCHEN        3.20×4.75      3.15×4.60       14.49  ·pX·
HALL           1.70×11.00     1.50×10.70      16.05  XRXp
MASTER         4.40×3.60      4.20×3.30       13.86  XXRp
SAFE_ROOM      4.40×2.50      4.10×2.20        9.02  RRRR
BEDROOM_1      4.40×3.00      4.20×2.80       11.76  RXpp
BATH           4.40×1.90      4.20×1.70        7.14  pXXp
                    X=exterior  p=partition  R=RC  ·=no wall
```

`·` in LIVING/DINING/KITCHEN is the proof of open plan: those boundaries carry **no wall**, so
they cost no area and generate no door. `RRRR` on SAFE_ROOM is the fix described in §4 below.

---

## 3. What the spike actually proved

**The wall-thickness circularity dissolves, and the measurement is exact.** Wall type is a
function of the tree plus the program: exterior sides come from tree position, open sides from
open-group membership, safe-room sides from the program. All are known before any dimension is
chosen, so the net→centerline inflation happens *inside* the shape curve and the first pass is
already thickness-correct. **F1 and F2 converged in one iteration — zero loop.**

**Shape curves give exact tiling, not approximate.** Integer 5 cm units mean
`Σ leaf area == footprint area` exactly, not within tolerance. There is no residue to hide a
sliver in. This is proof P1 + P3, and it is why the approach answers the dead-space problem
structurally rather than by penalty.

**Open plan needed almost no machinery.** A slicing leaf is a `PhysicalSpace`; an open group is
a subtree whose internal boundaries are typed `OPEN` with zero inset. V2.1's
PhysicalSpace/FunctionalZone split maps onto the slicing tree one-to-one.

**Infeasibility is diagnosed, not fudged.** Shrinking F1's wing to 6.0 × 5.0 raises
`SpikeInfeasible` naming the node whose shape curve emptied — never a quietly wrong plan.

---

## 4. Defect the spike caught

On the first run F3/P6 failed:

```
SAFE_ROOM not RC on all sides: N=RC, S=RC, E=EXTERIOR, W=RC
```

`derive_wall_types` tested exposure **before** safe-room membership, so the ממ״ד's envelope wall
was typed as an ordinary exterior wall. Both happen to be 0.30 m in the current parameters, so
the geometry was right and **only the semantics were wrong** — which is worse, because every
downstream ממ״ד construction rule would silently have stopped applying to that wall.

Fixed by making precedence explicit: `OPEN > RC_SAFE_ROOM > EXTERIOR > PARTITION`, with a named
regression test. This is exactly the class of error a spike exists to surface.

---

## 5. Limitations found — carry into the engine work

| # | Finding | Consequence |
|---|---|---|
| **L1** | **A hall serving 3+ rooms must be a full-height/width strip**, OR — proven in §8 patch 3 below — two-or-more hall leaves joined by an open-plan internal boundary. | Confirms `L_CARVE_CIRCULATION`-style branching is **representable with existing machinery** (the open-group mechanism, not a new engine concept). A genuinely **bent** (dogleg) corridor remains unproven — see §8 patch 3's honest limitation note. |
| **L2** | **An L seam is full on the small wing's side and partial on the large wing's side.** A partly-exterior/partly-internal leaf side has no single wall type. | Solved here with a **forced cut** (`Split.fixed_at_u`) aligning the seam to a leaf boundary, plus proof P9 verifying it. Archetypes must emit forced cuts, not just wing rectangles. |
| **L3** | **`max_aspect_ratio` cannot be global.** A corridor at 7:1 is correct; a bedroom at 7:1 is not. | Per-zone, from `RuleSet` keyed by role — not one PRODUCT POLICY number. |
| **L4** | **Wall thicknesses must be even multiples of the grid.** 0.25 m gives a 0.125 m inset = 2.5 units and breaks exact tiling. | **Closed by §8 patch 1**: this used to round silently; it now raises `ValueError` instead. Grid separation (5 cm search / exact-mm wall faces) remains a documented future option, not implemented. |
| **L5** | **Net/gross came out 0.90–0.92, above the 0.80–0.87 real houses show.** These fixtures have few internal partitions. | Not a defect, a calibration gap. Confirms experiment **E3** is still needed; do not hard-code an efficiency constant. |
| **L6** | The safe room costs **exactly one** extra iteration. | §7's bounded convergence is real but not free. `NON_CONVERGENT` stays necessary. Its staleness risk is tested and closed — see §8 patch 5. |

---

## 6. What this spike did NOT test

Out of scope by instruction, and none of it is implied by the result: UI · parking/site ·
windows/daylight · multi-candidate/diversity · second floor · full furniture placement (only
*derived* min dimensions plus, since §8 patch 4, a per-role envelope-fit screen were used) ·
repair operators · `DesignDecision` · doors as geometry (openings are counted and located on a
boundary, not drawn with swings) · a genuinely bent (dogleg) single circulation leaf (§8
patch 3's limitation note).

---

## 7. Files

| File | Role |
|---|---|
| `model.py` | Domain types, the three corrections, grid/wall constants, the grid-alignment guard (patch 1), the SAFE_ROOM/open_groups guard (patch 2), the furniture-envelope screen (patch 4) |
| `engine.py` | Structural wall typing → shape curves → assignment → bounded re-solve (unchanged by the 5 patches) |
| `fixtures.py` | Four fixtures, incl. the branching hall (patch 3) |
| `validate.py` | Eleven proofs (P1–P11) + opening generation |
| `run_spike.py` | Report runner |
| `test_spike.py` | 34 regression tests, incl. the negative (infeasible) case and the 5 patches' regressions |

---

## 8. Five proof patches (Fable review, GO WITH PATCHES)

| # | Patch | Where | Result |
|---|---|---|---|
| 1 | Fail-fast validation for non-grid-aligned wall thickness — **never silently round** | `model.half_thickness_units`, called by `inset_u` and eagerly at import over the whole `WALL_THICKNESS_M` table | `half_thickness_units(0.25, ...)` now raises `ValueError` instead of silently becoming 2 units (the exact review-cited defect: `round(2.5)` → 2, not 2.5). Existing 0.30/0.10 values unaffected. Explicitly commented as a **temporary safety guard**, not a permanent domain limit — the real fix for a non-grid-aligned regulation value is an exact-millimetre reconciliation pass, not a finer grid or a relaxed check. |
| 2 | Reject `SAFE_ROOM` inside `open_groups` eagerly | `Fixture.__post_init__` | Raises `ValueError` naming the conflicting zone(s) and group at **construction time**, instead of only being discoverable later as a confusing P6 `"not RC on all sides: ...=OPEN"` failure. |
| 3 | 4th fixture requiring branching circulation | `fixtures.branching_hall` (`F4_BRANCHING_HALL`) + new proof **P10** | `HALL_MAIN`/`HALL_SPUR` are two leaves in one open circulation group. `LIVING`+`BEDROOM_1` are reachable only via `HALL_MAIN`; `KITCHEN`+`BEDROOM_2`+`BATH` (3 rooms) are reachable **only** via `HALL_SPUR` — genuinely requires the branch (`test_branching_hall_genuinely_requires_the_branch` asserts this directly on the solved geometry). All 11 proofs pass, including new P10 (clear-width continuity across the wall-less corridor joint: 1.50 m net width on both sides). **Honest limitation, not solved**: this proves a hall *split into two leaves* that together reach rooms no single leaf could — it does not prove a geometrically bent dogleg/L-shaped single corridor. The open-marking mechanism (`engine._mark_open_interfaces`) only recognises a wall-less boundary between direct tree siblings, and direct siblings are always axis-aligned (same width for an H-cut, same height for a V-cut) — a true perpendicular bend needs non-sibling adjacency, which is out of scope here (no engine changes made). |
| 4 | Per-role minimum furniture-envelope feasibility (bounding-box screen, not placement) | `model.MIN_FURNITURE_ENVELOPE_M` / `min_furniture_envelope_m` / `furniture_envelope_fits`, new proof **P11** | **Found a real, pre-existing gap while implementing this**: F3's `SAFE_ROOM` (dual-role SAFE_ROOM+BEDROOM) had net short side 2.20 m — satisfied its own area minimum and P5's aspect gate, but could not inscribe the 2.4×2.4 m envelope a room doubling as a bedroom needs. Fixed by raising the fixture's `min_short_side_m` 2.2→2.4 m (a fixture-data fix, not an engine or envelope-constant change — the check was right, the input was under-specified). All 4 fixtures now pass P11. |
| 5 | Perturbation regression for the wall re-solve loop's staleness risk | `test_wall_resolve_loop_does_not_go_stale_when_geometry_shifts` | The review raised a theoretical risk: `extra_rc` only ever *adds* a zone-side to RC, never removes it, so a later geometry shift could in principle leave a stale RC wall. Tested empirically by perturbing `MASTER`/`BEDROOM_1`'s target areas enough to change their solved dimensions (asserted directly), then re-solving: the discovered safe-room-adjacent sides and iteration count are **unchanged**. Confirmed why: in this guillotine-tree engine, sibling-chain adjacency is fixed by **tree topology**, not by the numeric split position `assign()` picks — so the theoretical risk does not materialise in this design. No engine change was needed; `test_wall_resolve_loop_still_returns_structured_diagnostic_on_non_convergence` additionally confirms `SpikeInfeasible` is still raised (not a silent bad plan) when convergence is deliberately forced to fail. |

**No engine redesign.** `engine.py` is byte-for-byte unchanged by these 5 patches — every patch lives in `model.py` (2 guards + 1 data table), `fixtures.py` (1 new fixture + 1 corrected zone spec), or `validate.py` (2 new proofs).
