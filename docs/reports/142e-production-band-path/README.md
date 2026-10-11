# #142E — Production band topology + per-cell sizing path

Productionizes the portion of the #142C/#142D path that was proven: an **exact band embedding** of a
required spatial-adjacency graph, an **exact per-cell sizing** of band layouts on the realizer's own
5 cm grid, **canonical NET semantics** for every room bound, a **typed pipeline diagnosis**, and a
**permanent regression suite** over the 20 frozen briefs. Downstream architectural constraints
(entrance placement, safe-room RC walls, access-vs-spatial mismatch, exposure, the B06/B07 band
geometry limits, B18's search space) are instrumented, not solved — see "Intentionally unsolved".

## What changed (production code)

| module | change |
|---|---|
| `app/vertical_slice/graph_planarity.py` (new) | exact planarity test (Demoucron–Malgrange–Pertuiset over biconnected components), dependency-free; a non-planar required graph is refused as `TOPOLOGY_NON_PLANAR` before any geometry |
| `app/vertical_slice/band_embedding.py` (new) | exact band embedding: typed pre-checks (non-planar, K4, triple-lens → `TOPOLOGY_REPRESENTATION_LIMIT`), then a complete-when-affordable native search over band *labelings* (room → band, `|Δ| ≤ 1` on every required pair) and chain-consistent within-band orders; every candidate is re-verified geometrically; candidates ranked by a generic plausibility score; refusals `BAND_UNSAT` (proof) / `EMBEDDING_SEARCH_EXHAUSTED` (budget) |
| `app/vertical_slice/band_sizing.py` (new) | exact per-cell sizing: band heights × column boundaries as integer units, every cell held to its NET bounds (area, short side, max aspect) with the insets its own walls will carry; heights by interval branch-and-bound, widths by difference constraints (Bellman–Ford); `solve_band_layout` additionally chooses the column interleaving between consecutive bands itself; INFEASIBLE is a proof, UNKNOWN is a budget |
| `app/vertical_slice/band_pipeline.py` (new) | `run_band_pipeline`: embedding → sizing of every candidate → unchanged `realize_layout` → unchanged `validate`; `PipelineSuccess` or `PipelineDiagnosis` with a typed code, the stage, a per-stage histogram and per-candidate records; proposal-level warnings (`ACCESS_SPATIAL_MISMATCH`, `SAFE_ROOM_RC_MISSING`) |
| `app/vertical_slice/rectilinear_realizer.py` | `_build_grid_wing` sizes with the exact solver (`_solve_grid(w)`), gates every cell on **NET** area/short side with C3's tolerance (`_net_dims_m`, `_NET_AREA_TOL_M2`); the original rank-1 fit is kept verbatim as `_solve_grid_rank1` behind `GRID_SIZING_RANK1_FALLBACK = False`; `GridWing.envelope_is_bound` (default False = original exact-tiling contract); `ZoneIntent` docstring states the canonical NET semantics |
| `app/vertical_slice/graph_embedding.py` | the #142A decision layer's ROW/GRID stage now uses the exact embedder (a single-band layout is still returned as a `RowWing`; the pinwheel-first rule for n = 5 is unchanged — policy, not touched); the old greedy slot search only annotates refusals with its best partial count |

Not changed: validators, access rules, room templates, wet-room rules, entrance/exposure policy,
Concept Engine, the pinwheel/row/notch-carve builders' own gates (see "Intentionally unsolved").

## Part A — embedding: implementation decision

Decision: **(1) deterministic native algorithm**, no solver dependency. The band family has an exact
combinatorial characterization (a required graph is band-representable iff rooms can be split into
ordered bands with every required pair inside one band and consecutive there or in two consecutive
bands, and the cross pairs between consecutive bands pairwise comparable in the product order), so a
backtracking search is complete and the geometry follows by construction (`_assign_columns`, a
topological order of band boundaries). `python-sat` stays in the research venv. Completeness is
honest: the search reports `search_complete` only when the labeling DFS and every ordering finished
inside the node budgets (true for small families such as B01/B05/B06/B07/B08/B09); otherwise
labelings are sampled with a seeded generator for diversity and the refusal (if any) is
`EMBEDDING_SEARCH_EXHAUSTED`, never a false impossibility.

## Part C — canonical net/gross semantics

Trace (unchanged code, see `docs/reports/142d-exact-cell-sizing/README.md` §2 for the measurement):
`ZoneSpec` ("Areas/dims are NET, never centerline"), `ZoneIntent` (mirrors ZoneSpec), `ROOM_TEMPLATES`
(net, C21's docstring), `engine.leaf_shapes` (inflates net to centerline), validators C3/C20/C21/C26
(net via `net_rect_m`). The only gross consumer was `_build_grid_wing`'s area gate, measured at ~90 %
false acceptance and ~97 % false rejection. **Canonical semantics: every area/dimension bound on a
room is NET.** The grid gate and the sizing solver now both measure a room after the insets its walls
will carry (EXTERIOR 0.15 m per side on the wing boundary, PARTITION 0.05 m inside, `inset_u`), with
C3's own tolerance (0.01 m²). C3 is unchanged. Drift tests: `tests/vertical_slice/test_band_sizing.py`
(`test_grid_gate_measures_net_not_gross`, `test_solution_satisfies_every_cell_on_net_dimensions`).
Known residual: the pinwheel and row/notch builders still gate on gross area with the 0.3 m
short-side margin (consistent with each other, inconsistent with C3) — intentionally unsolved here.

## Results on the 20 frozen briefs

| brief | outcome | stage | candidates tried | sized | realized | seconds | notes |
|---|---|---|---|---|---|---|---|
| B01 | **PASS** | VALIDATORS | #0 | — | — | 0.035 | spatial 6/6, access 4/4 |
| B02 | TOPOLOGY_REPRESENTATION_LIMIT | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_REPRESENTATION_LIMIT 1 |
| B03 | TOPOLOGY_REPRESENTATION_LIMIT | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_REPRESENTATION_LIMIT 1 |
| B04 | SAFE_ROOM_RC_MISSING | VALIDATORS | 120 | 83 | 31 | 0.336 | SIZING: GRID_INFEASIBLE 37; REALIZATION: NO_ENTRANCE 52; VALIDATORS: C4 5, C24+C4+C5 9, C19+C24+C4+C5+C8 9, C19+C4+C5+C8 4, C17+C24+C4+C5 3, C4+C5 1 |
| B05 | **PASS** | VALIDATORS | #18 | — | — | 0.126 | spatial 9/9, access 6/6 |
| B06 | BAND_GEOMETRY_LIMIT | SIZING | 58 | 0 | 0 | 0.091 | SIZING: GRID_INFEASIBLE 58 |
| B07 | SAFE_ROOM_RC_MISSING | VALIDATORS | 120 | 4 | 2 | 0.494 | SIZING: GRID_INFEASIBLE 116; REALIZATION: NO_ENTRANCE 2; VALIDATORS: C19+C24+C4+C5+C8 2 |
| B08 | **PASS** | VALIDATORS | #2 | — | — | 0.247 | spatial 10/10, access 7/7 |
| B09 | NO_ENTRANCE | REALIZATION | 30 | 4 | 0 | 0.078 | SIZING: GRID_INFEASIBLE 26; REALIZATION: NO_ENTRANCE 4 |
| B10 | TOPOLOGY_REPRESENTATION_LIMIT | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_REPRESENTATION_LIMIT 1 |
| B11 | SAFE_ROOM_RC_MISSING | VALIDATORS | 120 | 36 | 11 | 0.402 | SIZING: GRID_INFEASIBLE 84; REALIZATION: NO_ENTRANCE 25; VALIDATORS: C24+C4+C5 1, C17+C24+C4+C5 6, C19+C24+C4+C5+C8 4 |
| B12 | ACCESS_SPATIAL_MISMATCH | VALIDATORS | 120 | 38 | 18 | 0.742 | SIZING: GRID_INFEASIBLE 82; REALIZATION: NO_ENTRANCE 20; VALIDATORS: C17+C19+C24+C5+C8 18 |
| B13 | **PASS** | VALIDATORS | #20 | — | — | 0.345 | spatial 12/12, access 9/9 |
| B14 | TOPOLOGY_REPRESENTATION_LIMIT | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_REPRESENTATION_LIMIT 1 |
| B15 | TOPOLOGY_REPRESENTATION_LIMIT | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_REPRESENTATION_LIMIT 1 |
| B16 | TOPOLOGY_REPRESENTATION_LIMIT | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_REPRESENTATION_LIMIT 1 |
| B17 | ACCESS_SPATIAL_MISMATCH | VALIDATORS | 120 | 10 | 4 | 1.169 | SIZING: GRID_INFEASIBLE 110; REALIZATION: NO_ENTRANCE 6; VALIDATORS: C19+C24+C5+C8 3, C24+C5 1 |
| B18 | SAFE_ROOM_RC_MISSING | VALIDATORS | 120 | 3 | 1 | 1.283 | SIZING: GRID_INFEASIBLE 117; REALIZATION: NO_ENTRANCE 2; VALIDATORS: C19+C24+C4+C5+C8 1 |
| B19 | TOPOLOGY_NON_PLANAR | EMBEDDING | 0 | 0 | 0 | 0.0 | EMBEDDING: TOPOLOGY_NON_PLANAR 1 |
| B20 | NO_ENTRANCE | REALIZATION | 120 | 91 | 0 | 0.183 | SIZING: GRID_INFEASIBLE 29; REALIZATION: NO_ENTRANCE 91 |

Band-representable briefs: 13; sized ≥ 1 candidate: **12/13** (rank-1 baseline 4/13); realized ≥ 1: 10/13; validators PASS: **4/13** (B01, B05, B08, B13). The six representation-limit briefs and B19 refuse at EMBEDDING with zero candidates.

## Part F — oracle vs production

| brief | witnesses | both feasible | both infeasible | oracle F / prod I (false negative) | oracle I / prod F (free interleaving) | fixed-columns agree | ms/witness oracle | ms/witness production | production embedding (candidates / found / complete / sizable) |
|---|---|---|---|---|---|---|---|---|---|
| B01 | 68 | 56 | 12 | 0 | 0 | 68/68 | 41.11 | 0.716 | 34 / 34 / True / 28 |
| B04 | 904 | 329 | 405 | 2 | 168 | 900/904 | 94.78 | 1.137 | 150 / 800 / False / 94 |
| B05 | 679 | 501 | 178 | 0 | 0 | 679/679 | 28.69 | 0.587 | 150 / 284 / True / 91 |
| B06 | 156 | 0 | 156 | 0 | 0 | 156/156 | 37.3 | 0.052 | 58 / 58 / True / 0 |
| B07 | 4752 | 24 | 4688 | 0 | 40 | 4752/4752 | 33.25 | 0.064 | 150 / 540 / True / 4 |
| B08 | 694 | 277 | 309 | 0 | 108 | 694/694 | 100.95 | 0.448 | 150 / 562 / True / 81 |
| B09 | 180 | 28 | 140 | 0 | 12 | 180/180 | 38.44 | 0.267 | 30 / 30 / True / 4 |
| B11 | 816 | 80 | 618 | 0 | 118 | 815/816 | 69.69 | 3.996 | 150 / 653 / False / 42 |
| B12 | 750 | 179 | 387 | 0 | 184 | 748/750 | 103.06 | 0.374 | 150 / 800 / False / 39 |
| B13 | 750 | 193 | 373 | 0 | 184 | 747/750 | 101.96 | 0.713 | 150 / 800 / False / 14 |
| B17 | 1000 | 51 | 870 | 0 | 79 | 1000/1000 | 99.6 | 0.198 | 150 / 405 / False / 9 |
| B18 | 3000 | 1440 | 474 | 0 | 1086 | 2962/3000 | 155.37 | 0.665 | 150 / 680 / False / 3 |
| B20 | 900 | 292 | 569 | 0 | 39 | 884/900 | 78.23 | 0.676 | 150 / 800 / False / 114 |

Over 14649 #142D witnesses (net semantics): production's free-interleaving solver (`solve_band_layout`) is
FEASIBLE wherever the oracle is, except **2 witnesses** (all in B04), and additionally FEASIBLE on
2018 witnesses the oracle's fixed-column model could not size — expected, since production chooses
the column interleaving between bands itself (a strictly larger geometric family for the same ordered
bands). Like-for-like, the fixed-column production solver (`solve_band_sizing`) agrees with the oracle on
every witness but the same 2. **The 2 false negatives are explained**: the oracle's continuous
solutions sit on a knife edge that the realizer's 5 cm unit grid cannot represent — rounding them to
units (nearest, floor or ceil) violates a bound in every case (e.g. witness 529: HALL net area 30.04 >
30.01, BATHROOM_1 12.04 > 12.01, KITCHEN aspect 3.04 > 3.0). Production's INFEASIBLE is a proof over the
unit grid the realizer actually builds on; no unexplained false negative remains.

## Part G — performance

| brief | n | embed s | candidates / found / complete | sizing ms mean / max | sizable | realizations | pipeline s | peak MB | deterministic | outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | 0.004 | 34 / 34 / True | 0.576 / 4.053 | 28 | 1 | 0.031 | 0.14 | True | PASS |
| B02 | 6 | 0.0 | — / — / — | — / — | — | 0 | 0.0 | 0.01 | True | TOPOLOGY_REPRESENTATION_LIMIT |
| B03 | 6 | 0.0001 | — / — / — | — / — | — | 0 | 0.0 | 0.02 | True | TOPOLOGY_REPRESENTATION_LIMIT |
| B04 | 8 | 0.1035 | 150 / 800 / False | 0.427 / 10.332 | 90 | 83 | 0.306 | 0.93 | True | SAFE_ROOM_RC_MISSING |
| B05 | 7 | 0.0442 | 150 / 284 / True | 0.339 / 4.183 | 91 | 7 | 0.112 | 0.43 | True | PASS |
| B06 | 8 | 0.0779 | 58 / 58 / True | 0.037 / 0.049 | 0 | 0 | 0.082 | 0.34 | True | BAND_GEOMETRY_LIMIT |
| B07 | 9 | 0.4289 | 150 / 540 / True | 0.046 / 0.544 | 2 | 4 | 0.446 | 1.66 | True | SAFE_ROOM_RC_MISSING |
| B08 | 8 | 0.1603 | 150 / 562 / True | 0.359 / 6.056 | 75 | 3 | 0.223 | 0.91 | True | PASS |
| B09 | 9 | 0.0634 | 30 / 30 / True | 0.161 / 1.777 | 2 | 4 | 0.073 | 0.3 | True | NO_ENTRANCE |
| B10 | 9 | 0.0001 | — / — / — | — / — | — | 0 | 0.0 | 0.03 | True | TOPOLOGY_REPRESENTATION_LIMIT |
| B11 | 11 | 0.2048 | 150 / 653 / False | 0.125 / 1.331 | 14 | 36 | 0.366 | 4.11 | True | SAFE_ROOM_RC_MISSING |
| B12 | 10 | 0.5167 | 150 / 800 / False | 0.223 / 2.773 | 27 | 38 | 0.66 | 1.77 | True | ACCESS_SPATIAL_MISMATCH |
| B13 | 10 | 0.2805 | 150 / 800 / False | 0.082 / 0.955 | 11 | 9 | 0.305 | 1.91 | True | PASS |
| B14 | 11 | 0.0001 | — / — / — | — / — | — | 0 | 0.0 | 0.03 | True | TOPOLOGY_REPRESENTATION_LIMIT |
| B15 | 11 | 0.0001 | — / — / — | — / — | — | 0 | 0.0 | 0.03 | True | TOPOLOGY_REPRESENTATION_LIMIT |
| B16 | 13 | 0.0001 | — / — / — | — / — | — | 0 | 0.0 | 0.04 | True | TOPOLOGY_REPRESENTATION_LIMIT |
| B17 | 12 | 0.9819 | 150 / 423 / False | 0.103 / 3.27 | 4 | 8 | 1.018 | 9.92 | True | NO_ENTRANCE |
| B18 | 13 | 0.8866 | 150 / 676 / False | 0.063 / 0.093 | 0 | 2 | 0.906 | 11.34 | True | NO_ENTRANCE |
| B19 | 12 | 0.0003 | — / — / — | — / — | — | 0 | 0.0 | 0.05 | True | TOPOLOGY_NON_PLANAR |
| B20 | 10 | 0.093 | 150 / 800 / False | 0.43 / 3.766 | 75 | 91 | 0.16 | 2.21 | True | NO_ENTRANCE |

Worst case over the 20 briefs: pipeline **1.018 s**, embedding 0.9819 s, a single sizing
10.332 ms, peak memory 11.34 MB; all 20 runs deterministic (two runs, identical placements and
geometry): True; total for the suite 4.69 s. Bounds adopted for an interactive application
(enforced by node budgets, not wall-clock): embedding ≤ 40,000 ordering nodes + 15,000 labeling nodes + 2,500
samples (measured ≤ ~1.2 s), sizing ≤ 4,000 nodes per candidate (measured ≤ ~12 ms), ≤ 150 candidates sized,
≤ 150 realized; the regression suite asserts ≤ 8 s per brief end-to-end. Exact search completeness is
reported, never bought with an unbounded timeout.

## Part H — typed diagnoses

`PipelineDiagnosis.code` ∈ TOPOLOGY_NON_PLANAR · TOPOLOGY_REPRESENTATION_LIMIT · BAND_UNSAT ·
EMBEDDING_SEARCH_EXHAUSTED · BAND_GEOMETRY_LIMIT · SIZING_INFEASIBLE · NO_ENTRANCE ·
SAFE_ROOM_RC_MISSING · ACCESS_SPATIAL_MISMATCH · EXPOSURE_INFEASIBLE · VALIDATION_FAILED ·
REALIZATION_FAILED, with `stage`, `stage_histogram`, per-candidate `records` (stage reached, refusal,
failed checks, entrance/access/exposure flags) and proposal-level `warnings`.

## Regression suite (Part E)

`tests/vertical_slice/test_band_pipeline_regression.py` over `tests/fixtures/frozen_briefs_142.json`
(the 20 briefs, best policy-valid proposal each, zone bounds from `ROOM_TEMPLATES`): every band brief
embeds exactly with every candidate verified; the six representation-limit briefs and B19 refuse
explicitly with zero candidates; B01 full PASS with spatial 6/6 and access 4/4; B13 PASS with 12/12
and LIVING net aspect ≤ 2.5; sizing coverage > rank-1 baseline + 2; every failure typed; runtime
bounded; pipeline deterministic. Plus unit suites `test_band_embedding.py` (planarity classics,
obstructions, path/hub/wheel graphs, determinism, budget honesty) and `test_band_sizing.py`.

## Migration / rollout notes

- No caller of the production demo path is switched in this PR: `run_band_pipeline` is a new entry
  point; `realize_layout` behaviour changes only for `GridWing` (exact sizing + net gate). The #142A
  harness (`gap_closure_142a`) now goes through the exact embedder for ROW/GRID.
- `GRID_SIZING_RANK1_FALLBACK = True` restores the previous `_solve_grid` for a rollback; the net
  gate stays (it is a correctness fix, not a policy).
- `GridWing.envelope_is_bound=True` lets the solver choose the wing size inside a bound (the pipeline
  uses it with the brief footprint + 4 m); the default keeps the original exact-tiling contract.
- Budgets (`DEFAULT_NODE_LIMIT`, `LABELING_DFS_NODES`, `LABELING_SAMPLES`, `DEFAULT_RAW_CAP`,
  `DEFAULT_MAX_CANDIDATES`, `DEFAULT_MAX_REALIZATIONS`, `band_sizing.DEFAULT_NODE_LIMIT`) are the
  only knobs; all are node counts (no wall-clock cut-offs), so results are reproducible.

## Intentionally unsolved (next experiment)

- `NO_ENTRANCE`: an ALLOWED_ENTRANCE room must lie in the street band; the embedder carries no
  orientation intent (the `entrance_ok` flag is recorded per candidate).
- `SAFE_ROOM_RC_MISSING`: the rectilinear realizer never assigns `RC_SAFE_ROOM` walls, so C4 fails
  for every SAFE_ROOM brief (B04, B07, B11, B18, B20) by construction.
- `ACCESS_SPATIAL_MISMATCH`: proposals whose access graph enters a room through a wall the spatial
  adjacency never requires (B12, B17 and parts of B05/B18); the embedder takes `spatial_adjacency`
  only, as specified.
- `EXPOSURE_INFEASIBLE`: band families where a daylight room is always interior (B06, B07, B09, B12).
- B06 remains a proven band-geometry limit (complete family, every layout infeasible under net bounds);
  B07's four sizable layouts die on C4/C19/C24; B18's family is not exhaustible and is reported
  within the search bound only.
- The realizer is not complete: it realizes what the band family, the realizer's own gaps and the
  proposals allow — today 4 of the 13 band-representable briefs end-to-end.
