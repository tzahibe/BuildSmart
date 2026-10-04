# #142G — SAFE_ROOM RC-wall capability in the rectilinear realizer

**Final question.** Does correct SAFE_ROOM RC-wall construction convert the three measured C4-only
cases into fully valid plans without causing regressions elsewhere?

**Answer: yes.** With the rectilinear realizer typing safe-room walls the way the Geometry Core
already does (the safe room's own four sides and every neighbour side that touches it are
`RC_SAFE_ROOM`, derived from the realized rects, precedence OPEN > RC > EXTERIOR > PARTITION) and the
sizing/gate measuring net areas with the matching 0.15 m insets, B04, B11 and B18 pass every
unchanged validator on the #142F selection path: **4/13 → 7/13**. B01, B05, B08 and B13 remain PASS.
The plain production pipeline (no intent-aware selection) gains B04: **4/13 → 5/13**; B11 and B18
still need the door-width-aware sizing and entrance orientation that are #142F findings, deliberately
not absorbed here. Full backend suite green; no validator touched.

## 1. C4, traced (§1)

- **What C4 requires** (`validation.py` C4, unchanged): for every zone with `ProgramRole.SAFE_ROOM`
  realized, all four `walls[(zone, side)]` must be `WallType.RC_SAFE_ROOM`, and the NET area
  (`net_rect_m`: centerline minus half wall thickness per side) must be ≥ `net_area_min_m2`. With an
  authoritative SAFE_ROOM constraint it also fails when no safe room is realized at all.
- **Which walls must be RC**: the safe room's own envelope — all four sides, *including* a side on
  the building exterior ("a safe room's EXTERIOR wall is still a safe-room wall", `engine.solve_wing`),
  and, by the Geometry Core's own rule, every side of a neighbouring room that shares a boundary with
  the safe room (`engine._discovered_walls` / `_neighbour_sides`, found by a bounded re-solve). C33
  then requires every wall touching a safe room to be classified PROTECTED or EXTERIOR.
- **Representation**: a `WallMap` keyed `(zone_id, Side)` → `WallType`; `WALL_THICKNESS_M[RC] = 0.30 m`
  (a flagged regulation placeholder), inset 0.15 m per RC side — the same as EXTERIOR, three times a
  PARTITION's 0.05 m. Downstream, `geometry_adapter` maps RC → `Construction.RC_SAFE_ROOM`, `walls.py`
  classifies PROTECTED vs EXTERIOR (a wall can be both RC and on the envelope), the renderer draws it
  thick red, the demo contract reports it.
- **Exterior vs interior RC walls**: the realized `WallType` is RC for both; exposure is kept as a
  separate geometric fact (`envelope_sides`, `design_output` reports EXTERIOR *and* RC together), so a
  safe room's exterior side still receives its window (SAFE_ROOM is REQUIRED-exposure, C19/C8).
- **Doors/openings**: doors are placed on declared access edges by `generate_interior_doors`
  regardless of wall type; nothing forbids a door in an RC wall, and the safe room is PRIVATE
  (entered from circulation). Windows read exposure, not wall type (`windows.py` note: "read off a
  WallType whose RC precedence may have overwritten it").
- **What the realizer already knows**: the realized rects, every zone's roles and the touching
  pairs per side — everything the engine needs for its RC rule. It was simply not applying it
  (`realize_layout` typed only OPEN/PARTITION/EXTERIOR; `band_pipeline.input_warnings` flagged it).

## 2. Implementation (§2)

| change | where |
|---|---|
| wall typing in `realize_layout`: a side is OPEN if an open pair touches it; else RC_SAFE_ROOM if the zone is a safe room **or any room touching that side is one**; else EXTERIOR / PARTITION as before. Derived from `rects`, deterministic, before `validate` | `rectilinear_realizer.py` (walls block) |
| the grid gate measures NET with RC insets on exactly those sides (`rc_sides_from_rows` from the cell grid: a safe room's sides, same-row W/E neighbours, overlapping N/S neighbours) | `rectilinear_realizer._build_grid_wing`, `_net_dims_m(rect, exterior, rc)` |
| the fixed-column sizing uses the same RC insets (`cells_from_rows`); the free-interleaving sizing treats a safe room's own sides as RC and re-solves (≤ 4 rounds) until the neighbour RC sides read off its own result stop changing | `band_sizing.cell_insets_u`, `rc_sides_from_rows`, `solve_band_layout` |

Nothing is marked after validation, no brief is special-cased, C4/C33 untouched. Because the sizing
knows the insets, a safe room is sized to meet its minimum *net of RC walls* (B18's tight 9.01 m² is
the solver landing on the bound).

## 3. Openings remain valid (§3)

For every passing safe-room plan: one placeable door HALL↔SAFE_ROOM (B04, B11, B18), a window on the
safe room's exterior side, C5/C24 (reachability, door edges), C8/C19 (exposure), C33 (hosted
doors/windows, safe-room walls PROTECTED), C26/C28/C31 all PASS — `figures/safe_room_evidence.json`.
Unit tests pin the same facts on a synthetic 6-room layout (`tests/vertical_slice/test_safe_room_rc_walls.py`).

## 4. Frozen suite, before / after (§4, §5)

**Selection path** (#142F harness: spatial ∪ access contacts, HARD flags, free flip to the street
band, door-width-aware sizing injected; `data/intent_harness_before_rc.json` / `_after_rc.json`):

| stage (13 band briefs) | before RC | after RC |
|---|---:|---:|
| ≥ 1 HARD-feasible candidate | 7 | 7 |
| sized | 7 | 7 |
| realized | 7 | 7 |
| **validators PASS (unchanged)** | **4** | **7** |

| brief | before | after | passing candidates after |
|---|---|---|---|
| B01 | PASS | PASS | 16/16 realized |
| B04 | fails only C4 (29 candidates) | **PASS** | 11 (18 of the 29 are now refused at the gate: with RC insets on their neighbours they fall below a net bound — correct, since C3 would have failed them) |
| B05 | PASS | PASS | 43/50 |
| B08 | PASS | PASS | 19/19 |
| B11 | fails only C4 (3) | **PASS** | 3 |
| B13 | PASS | PASS | 3/3 |
| B18 | fails only C4 (1) | **PASS** | 1 (safe room net 9.01 m² ≥ 9.0) |
| B06 | no HARD-feasible candidate (exposure) | unchanged | — |
| B07, B09, B17 | ACCESS_SPATIAL_CONTRADICTION | unchanged | — |
| B12, B20 | ACCESS_POLICY_CONFLICT | unchanged | — |

**Production pipeline** (`run_band_pipeline`, no selection; `data/production_pipeline_after_rc.json`):
sized 11/13, realized 8/13, **PASS 5/13** (B01, B04, B05, B08, B13) vs 4/13 before. B11 and B18 do not
pass here because their realized candidates lack a door-width-sufficient wall / the right orientation
(C24+C5, C17; `SIZING_INFEASIBLE` for B18) — the #142F selection findings, out of scope by design.

Remaining validator failures after RC (selection path): B06 — EXPOSURE_INFEASIBLE in its complete
band family; B07/B09/B17 — proposals whose access requirements contradict their adjacency under
rectangles; B12/B20 — proposals requesting a door the realizer's wet-room filter forbids. None of
them is a C4 case any more.

## 5. Regression (§4, §8)

- `tests/vertical_slice/test_safe_room_rc_walls.py` (6): RC on all four safe-room sides and C4 PASS;
  neighbour sides facing the safe room RC and nothing else (exterior side still RC); door + window
  + C5/C24/C8/C19/C33 PASS; the gate refuses a safe room that meets its minimum only under PARTITION
  insets (exercised through the rank-1 fallback, which knows no insets); RC assignment deterministic
  (identical walls and rects on repeat); `rc_sides_from_rows` matches contacts.
- `tests/vertical_slice/test_band_pipeline_regression.py`: B04 added to the required passes; a new
  test asserts B04's safe room has RC on all sides and C4 PASS in the production pipeline; B01/B13
  controls unchanged.
- Full backend suite: 1899 passed, 883 skipped, 9 xfailed (0 failures).
- Determinism: this branch is based on the #165 seed fix (process-independent embedding); RC
  assignment is a pure function of the realized rects (no randomness, no iteration order effects).

## 6. Evidence (§6)

`figures/B04_safe_room_plan.png`, `B11_…`, `B18_…`: realized plans with walls coloured by type (thick
red = RC_SAFE_ROOM, black = EXTERIOR, grey = PARTITION), doors (■, labelled), windows (—), entrance
(★, street at the top), gross and net dimensions per room, and the validator verdict in the title.
`figures/safe_room_evidence.json` lists per brief the safe room's sides, the RC neighbour sides, its
door and window, which of its RC sides are also exterior, and the (empty) failed-check list.

## Out of scope, intentionally (§7)

B07/B09/B17 contradictions, B12/B20 policy conflict, B06 exposure, L-shaped rooms, B18's search space
(only its known valid candidate is preserved), productionizing #142F selection (door-width sizing,
orientation, HARD filters) — the next decision.
