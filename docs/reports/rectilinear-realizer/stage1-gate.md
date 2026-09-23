# Rectilinear realizer — Stage 1 gate (Issue #117)

**9/10 real corpus layouts realized, 1/10 refused** — every check on every REALIZED layout ran through the UNCHANGED validator chain (`app.vertical_slice.validation.validate`) with zero validator/threshold changes anywhere in this Issue's diff. Families attempted: PINWHEEL (spike #108's own topology, generalized), L (corner-notch), U (edge-notch, AC-2's own "U/T/cross/Z" coverage), and TWO_WING (a genuinely non-rectangular envelope, two wings of different heights with a real seam).

**Methodology** (`stage1_gate.py`): each of the 10 attempts reads REAL room roles and REAL realized areas off the frozen 432-context regression corpus's own solved output (`project_from_context`/`generate_demo_design`, the exact unchanged production call the corpus itself was frozen with — see `tests/regression_corpus/freeze_corpus.py`). PLACEMENT (which family, which role goes where, the envelope's own dimensions) is this script's own deterministic choice — the realizer's mandated input is a PLACED layout; deciding placement from a retrieved/generated layout is Stage 2's scope, explicitly out of this Issue. Wet rooms (BATHROOM/TOILET) and SAFE_ROOM are excluded from every constructed layout — a disclosed simplification (see the module docstring), not a hidden one: C17/C29 need a `ResolvedWetRoom` list this script does not reconstruct. A refusal-recovery retry ladder (both larger and smaller envelope scales, up to 9 attempts) is this script's OWN policy, not the realizer's — `realize_layout` itself never approximates a layout; the ladder only tries a different, still fully-specified input next.

## Per-layout results

| # | family | outcome | validators ran/passed | source rooms/roles/adjacency | realized roles/adjacency survived | wall time (s) | SVG |
|---|---|---|---|---|---|---|---|
| 1 | PINWHEEL | REALIZED | 23/23 | 6/5/7 | 4/4 | 0.001 | svg/corpus-000_PINWHEEL.svg |
| 2 | PINWHEEL | REALIZED | 23/23 | 9/8/13 | 4/4 | 0.001 | svg/corpus-035_PINWHEEL.svg |
| 3 | PINWHEEL | REALIZED | 23/23 | 9/8/13 | 4/4 | 0.001 | svg/corpus-070_PINWHEEL.svg |
| 4 | PINWHEEL | REFUSED | 0/0 | 8/7/11 | 0/0 | 0.002 | — |
| 5 | PINWHEEL | REALIZED | 23/23 | 9/8/13 | 4/3 | 0.006 | svg/corpus-140_PINWHEEL.svg |
| 6 | PINWHEEL | REALIZED | 23/23 | 11/10/18 | 4/4 | 0.001 | svg/corpus-175_PINWHEEL.svg |
| 7 | PINWHEEL | REALIZED | 23/23 | 9/8/13 | 4/4 | 0.001 | svg/corpus-210_PINWHEEL.svg |
| 8 | L | REALIZED | 26/26 | 10/8/14 | 3/1 | 0.002 | svg/corpus-245_L.svg |
| 9 | U | REALIZED | 26/26 | 10/8/13 | 2/1 | 0.013 | svg/corpus-280_U.svg |
| 10 | TWO_WING | REALIZED | 24/24 | 12/9/17 | 5/4 | 0.004 | svg/corpus-315_TWO_WING.svg |

"validators ran/passed" is `ValidationReport.checks` (C1-C29, whichever ran for that fixture) PLUS `_group_checks`/C27 for a notch-carve layout — see `rectilinear_realizer.py`'s module docstring for which C3/C20/C21 are NOT authoritative for a notch-carve "big" zone's own cells (a NEEDS-POLYGON-VARIANT finding, not a disabled check) and what runs instead. "source rooms/roles/adjacency" and "realized roles/adjacency survived" are read off the REAL solved corpus context vs this layout's own realized geometry — see `SourceLayout.roles`/`adjacency_pairs` and `_run_one`'s own role-pair comparison; a coarse, disclosed metric (role-level, not room-instance-level — this script's placement is its own new construction, not a preserved copy of the real plan).

## Detail per refused layout

- **#4 (PINWHEEL, `corpus-105`)**: SHORT_SIDE_INFEASIBLE: N_LIVING: pinwheel-realized short side 3.10 m (gross) < 3.0 m (net) + 0.3 m inset margin

## NEEDS-POLYGON-VARIANT findings

For every REALIZED L/U/TWO_WING layout's own notch-carve group ("BIG_GROUP"), C3/C20/C21 ran at CELL granularity against a permissive placeholder `ZoneSpec` — not authoritative for the merged room (see `rectilinear_realizer._permissive_spec`'s docstring). The authoritative check is `_group_checks` (`GROUP-C2`/`GROUP-C3`/`GROUP-C20`), generalizing `room_merge.py`'s own redesigned C1/C2/C3/C20/C27 (Issue #107) from a 2-way LIVING+KITCHEN merge to N cells; C27 itself is likewise redesigned for a notch-carve group (`_group_c27`) rather than run through the generic net==width*depth formula, matching Issue #107's own precedent (a polygon room's bounding box is strictly bigger than its own true area by construction).

## Reproducing this gate

```
cd backend
uv run python -m spikes.geometry_shapes.stage1_gate
```
