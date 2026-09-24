# Rectilinear realizer — Stage 1 gate (Issue #117, re-run for Issue #136)

**6/10 real corpus layouts realized, 4/10 refused** — every check on every REALIZED layout ran through the UNCHANGED validator chain (`app.vertical_slice.validation.validate`) with zero validator/threshold changes anywhere in this Issue's diff. Families attempted: PINWHEEL (spike #108's own topology, generalized), L (corner-notch), U (edge-notch, AC-2's own "U/T/cross/Z" coverage), and TWO_WING (a genuinely non-rectangular envelope, two wings of different heights with a real seam).

**Issue #136 — re-run against current main.** This Stage 0/1 branch was cut before current main's Issue #22 added C25 (entrance-to-circulation integration, `app.vertical_slice.entrance_sequence`): the front door must land on circulation that is served within `ENTRANCE_POCKET_MAX_M` (4.00 m), not a dead stub. Merging main in and re-running this gate unchanged first reproduced the Issue's own finding exactly: the PINWHEEL and notch-carve (L) constructions placed a slot-to-slot door wherever the longest shared cell edge happened to fall, with no regard for how far that left the arrival zone's own street-facing segment from anything else — 4.17 m in the L/U hand-built fixture's HALL, 4.96 m in the PINWHEEL fixture's GALLERY, both over the limit. **The fix is entirely in `rectilinear_realizer.py`'s own construction, not in C25 or any other validator**: (1) `_best_touching_pair` (the row-wing's cross-slot door placement) now prefers, among candidates wide enough for that pair's own door class, the one whose shared segment sits closest to the wing's own street edge, instead of simply the longest edge; (2) `_build_pinwheel_wing` now also wires a door at each of the four corners where two arms physically interlock (the same corners that make the topology non-guillotine at all) whenever the access-rules table allows that role pair and the corner is wide enough for its door class — both are general, by-construction facts of every `RowWing`/`PinwheelWing`, not fixture-specific patches. After the fix, **zero** of the 10 real-corpus attempts below refuse on C25; the `C25 — entrance-to-circulation integration` section further down re-measures `entrance_sequence.pocket_length_m` directly for every REALIZED layout as evidence, not merely that `validate()` didn't refuse. The remaining gap from the pre-merge 9/10 headline is unrelated to C25: current main's Issue #118 also flipped `LIVING_KITCHEN_MERGE_ENABLED` to `True` by default, so `generate_demo_design` now regularly returns one merged `LIVING_KITCHEN` room instead of separate LIVING/KITCHEN ones for these same real contexts — this script's own room-pick heuristic did not recognise that type at all (fixed: `_MERGED_ROOM_TYPE_ROLES`, treating it as `ProgramRole.LIVING`), and once recognised, its own real (now larger, merged) area still makes 3 of the 10 real contexts geometrically infeasible for this script's fixed proportional pinwheel-scaling heuristic across all 9 of its retry scales — an honest SHORT_SIDE_INFEASIBLE/insufficient-usable-rooms refusal each time, not a C25 refusal and not a silently-forced pass. See "Detail per refused layout" below for the exact reason per case.

**Methodology** (`stage1_gate.py`): each of the 10 attempts reads REAL room roles and REAL realized areas off the frozen 432-context regression corpus's own solved output (`project_from_context`/`generate_demo_design`, the exact unchanged production call the corpus itself was frozen with — see `tests/regression_corpus/freeze_corpus.py`). PLACEMENT (which family, which role goes where, the envelope's own dimensions) is this script's own deterministic choice — the realizer's mandated input is a PLACED layout; deciding placement from a retrieved/generated layout is Stage 2's scope, explicitly out of this Issue. Wet rooms (BATHROOM/TOILET) and SAFE_ROOM are excluded from every constructed layout — a disclosed simplification (see the module docstring), not a hidden one: C17/C29 need a `ResolvedWetRoom` list this script does not reconstruct. A refusal-recovery retry ladder (both larger and smaller envelope scales, up to 9 attempts) is this script's OWN policy, not the realizer's — `realize_layout` itself never approximates a layout; the ladder only tries a different, still fully-specified input next.

## Per-layout results

| # | family | outcome | validators ran/passed | source rooms/roles/adjacency | realized roles/adjacency survived | wall time (s) | SVG |
|---|---|---|---|---|---|---|---|
| 1 | PINWHEEL | REFUSED | 0/0 | 5/4/5 | 0/0 | 0.000 | — |
| 2 | PINWHEEL | REALIZED | 26/26 | 9/8/13 | 4/4 | 0.002 | svg/corpus-035_PINWHEEL.svg |
| 3 | PINWHEEL | REALIZED | 26/26 | 9/8/13 | 4/4 | 0.002 | svg/corpus-070_PINWHEEL.svg |
| 4 | PINWHEEL | REFUSED | 0/0 | 7/6/9 | 0/0 | 0.000 | — |
| 5 | PINWHEEL | REFUSED | 0/0 | 8/7/11 | 0/0 | 0.000 | — |
| 6 | PINWHEEL | REALIZED | 26/26 | 11/10/18 | 4/4 | 0.002 | svg/corpus-175_PINWHEEL.svg |
| 7 | PINWHEEL | REFUSED | 0/0 | 8/7/11 | 0/0 | 0.002 | — |
| 8 | L | REALIZED | 29/29 | 9/7/12 | 2/0 | 0.002 | svg/corpus-245_L.svg |
| 9 | U | REALIZED | 29/29 | 10/8/13 | 2/1 | 0.015 | svg/corpus-280_U.svg |
| 10 | TWO_WING | REALIZED | 27/27 | 12/9/17 | 5/4 | 0.005 | svg/corpus-315_TWO_WING.svg |

"validators ran/passed" is `ValidationReport.checks` (C1-C29, whichever ran for that fixture) PLUS `_group_checks`/C27 for a notch-carve layout — see `rectilinear_realizer.py`'s module docstring for which C3/C20/C21 are NOT authoritative for a notch-carve "big" zone's own cells (a NEEDS-POLYGON-VARIANT finding, not a disabled check) and what runs instead. "source rooms/roles/adjacency" and "realized roles/adjacency survived" are read off the REAL solved corpus context vs this layout's own realized geometry — see `SourceLayout.roles`/`adjacency_pairs` and `_run_one`'s own role-pair comparison; a coarse, disclosed metric (role-level, not room-instance-level — this script's placement is its own new construction, not a preserved copy of the real plan).

## Detail per refused layout

- **#1 (PINWHEEL, `corpus-000`)**: not enough usable real rooms in this context to build a layout at any of this script's retry scales
- **#4 (PINWHEEL, `corpus-105`)**: SHORT_SIDE_INFEASIBLE: N_LIVING_KITCHEN: pinwheel-realized short side 3.15 m (gross) < 3.0 m (net) + 0.3 m inset margin
- **#5 (PINWHEEL, `corpus-140`)**: SHORT_SIDE_INFEASIBLE: W_BEDROOM: pinwheel-realized short side 2.65 m (gross) < 2.4 m (net) + 0.3 m inset margin
- **#7 (PINWHEEL, `corpus-210`)**: SHORT_SIDE_INFEASIBLE: N_LIVING_KITCHEN: pinwheel-realized short side 3.20 m (gross) < 3.0 m (net) + 0.3 m inset margin

## C25 — entrance-to-circulation integration (Issue #22, re-checked for #136)

`entrance_sequence.measure`/`classify_pocket` — the SAME unchanged function C25 itself calls in `validation.validate` — re-measured directly against every REALIZED layout's own `GeometricDesign`, as independent evidence beyond "`validate()` did not refuse":

| # | family | arrival zone | pocket_length_m | C25 |
|---|---|---|---|---|
| 2 | PINWHEEL | GALLERY | 1.92 | PASS |
| 3 | PINWHEEL | GALLERY | 1.72 | PASS |
| 6 | PINWHEEL | GALLERY | 1.82 | PASS |
| 8 | L | HALL | 1.68 | PASS |
| 9 | U | HALL | 1.19 | PASS |
| 10 | TWO_WING | GALLERY | 1.87 | PASS |

Every REALIZED layout's arrival zone clears `ENTRANCE_POCKET_MAX_M` (4.00 m); no C25 refusal occurs anywhere in this re-run (see "Detail per refused layout" above — every refusal reason there is SHORT_SIDE_INFEASIBLE or an insufficient-usable-rooms count, neither of which is C25).

## NEEDS-POLYGON-VARIANT findings

For every REALIZED L/U/TWO_WING layout's own notch-carve group ("BIG_GROUP"), C3/C20/C21 ran at CELL granularity against a permissive placeholder `ZoneSpec` — not authoritative for the merged room (see `rectilinear_realizer._permissive_spec`'s docstring). The authoritative check is `_group_checks` (`GROUP-C2`/`GROUP-C3`/`GROUP-C20`), generalizing `room_merge.py`'s own redesigned C1/C2/C3/C20/C27 (Issue #107) from a 2-way LIVING+KITCHEN merge to N cells; C27 itself is likewise redesigned for a notch-carve group (`_group_c27`) rather than run through the generic net==width*depth formula, matching Issue #107's own precedent (a polygon room's bounding box is strictly bigger than its own true area by construction).

## Reproducing this gate

```
cd backend
uv run python -m spikes.geometry_shapes.stage1_gate
```
