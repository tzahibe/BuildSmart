# #142C — Exact band embedding through the unchanged GridWing path

Question: does an exact band embedding unlock the existing `GridWing` -> `_solve_grid` -> `realize_layout` -> `validate` path for the topologies GridWing can already represent? Stages are reported separately; a downstream failure is never reported as a topology failure.

Frozen dataset sha256 `03c52be5357ff41f30ee104cfd1ff0d2760bba0cf7f0576b64565767cb321598` (same selection rule as #160/#142A: best policy-valid proposal in each brief's top-8). Witness artifact: `witnesses.json` (isolated SAT prototype, K=300 distinct band layouts per brief, 90.0 s cap). Envelope ladder: 11 scales x 9 aspects over the rooms' total target area, bounded by the brief footprint + 4 m. Nothing in `app/vertical_slice` changed.

## Headline

| stage | passed / band-representable briefs |
|---|---|
| exact band embedding (verified geometrically) | 13/13 |
| GridWing sizing (`_solve_grid` + per-cell bounds) | 4/13 |
| realization (footprint, entrance, doors, windows) | 3/13 |
| validators PASS (unchanged `validate`) | **1/13** |

Primary criterion (>= 9/13 band-representable briefs realized with validator PASS): **NOT MET** (1/13).

## Stage-by-stage matrix, all 20 briefs

| brief | n | m | classification | EMBEDDING | SIZING | REALIZATION | VALIDATORS | witnesses tried/available | success envelope | spatial | access | #142A |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | 6 | BAND_REPRESENTABLE | PASS | PASS | PASS | PASS | 1/68 | 10.5x7.0 m | 6/6 | 4/4 | REFUSED DIMENSION_SOLVER (pinwheel, SHORT_SIDE_INFEASIBLE) |
| B02 | 6 | 9 | UNSAT — REPRESENTATION_LIMIT | FAIL | — | — | — | 0/0 | — | — | — | not run |
| B03 | 6 | 8 | UNSAT — REPRESENTATION_LIMIT | FAIL | — | — | — | 0/0 | — | — | — | not run |
| B04 | 8 | 9 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 185/185 | — | — | — | not run |
| B05 | 7 | 9 | BAND_REPRESENTABLE | PASS | PASS | PASS | FAIL | 168/168 | — | — | — | not run |
| B06 | 8 | 11 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 76/76 | — | — | — | not run |
| B07 | 9 | 12 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 132/132 | — | — | — | not run |
| B08 | 8 | 10 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 181/181 | — | — | — | not run |
| B09 | 9 | 14 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 100/100 | — | — | — | not run |
| B10 | 9 | 14 | UNSAT — REPRESENTATION_LIMIT | FAIL | — | — | — | 0/0 | — | — | — | REFUSED TOPOLOGY_EMBEDDING 9/14 |
| B11 | 11 | 13 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 162/162 | — | — | — | not run |
| B12 | 10 | 13 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 150/150 | — | — | — | not run |
| B13 | 10 | 12 | BAND_REPRESENTABLE | PASS | PASS | PASS | FAIL | 150/150 | — | — | — | REFUSED TOPOLOGY_EMBEDDING 9/12 |
| B14 | 11 | 15 | UNSAT — REPRESENTATION_LIMIT | FAIL | — | — | — | 0/0 | — | — | — | not run |
| B15 | 11 | 15 | UNSAT — REPRESENTATION_LIMIT | FAIL | — | — | — | 0/0 | — | — | — | REFUSED TOPOLOGY_EMBEDDING 9/15 |
| B16 | 13 | 19 | UNSAT — REPRESENTATION_LIMIT | FAIL | — | — | — | 0/0 | — | — | — | REFUSED TOPOLOGY_EMBEDDING 11/19 |
| B17 | 12 | 13 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 200/200 | — | — | — | not run |
| B18 | 13 | 14 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 184/184 | — | — | — | not run |
| B19 | 12 | 25 | UNSAT — NON_PLANAR_TOPOLOGY | FAIL | — | — | — | 0/0 | — | — | — | not run |
| B20 | 10 | 11 | BAND_REPRESENTABLE | PASS | PASS | FAIL | FAIL | 180/180 | — | — | — | not run |

## UNSAT briefs (never attempted, never weakened)

- **B02** — `UNSAT — REPRESENTATION_LIMIT`: K4 BATHROOM_1/HALL/LIVING/MASTER_BEDROOM
- **B03** — `UNSAT — REPRESENTATION_LIMIT`: edge HALL-BATHROOM_1 with common neighbours BEDROOM_1/LIVING/MASTER_BEDROOM
- **B10** — `UNSAT — REPRESENTATION_LIMIT`: K4 BATHROOM_1/BEDROOM_1/HALL/LIVING; edge LIVING-HALL with common neighbours BATHROOM_1/BEDROOM_1/KITCHEN
- **B14** — `UNSAT — REPRESENTATION_LIMIT`: edge LIVING-HALL with common neighbours BATHROOM_3/BEDROOM_4/KITCHEN
- **B15** — `UNSAT — REPRESENTATION_LIMIT`: edge HALL-BATHROOM_2 with common neighbours BATHROOM_1/BEDROOM_2/BEDROOM_3
- **B16** — `UNSAT — REPRESENTATION_LIMIT`: edge LIVING-HALL with common neighbours BATHROOM_3/BEDROOM_1/BEDROOM_4
- **B19** — `UNSAT — NON_PLANAR_TOPOLOGY`: non-planar graph: no partition of the plane has a non-planar contact graph

## Failure attribution for every band-representable brief that died after exact embedding

### B04 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'SHORT_SIDE_INFEASIBLE': 4215, 'AREA_INFEASIBLE': 10546, 'GRID_INFEASIBLE': 3554}

### B05 — furthest stage passed: REALIZATION
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 9328, 'SHORT_SIDE_INFEASIBLE': 4315, 'GRID_INFEASIBLE': 2983}
- REALIZATION refusals over all witnesses x envelopes: {'NO_ENTRANCE': 3}
- VALIDATORS refusals over all witnesses x envelopes: {'VALIDATION_FAILED': 3}
- witness 3 validator detail: 9.2x13.8 m: C3: LIVING aspect 2.83 > 2.5; C20: LIVING realized 8.90 x 3.15 m (aspect 2.83) past its LIVING template's 2.5
- witness 4 validator detail: 9.2x13.8 m: C3: LIVING aspect 2.83 > 2.5; C20: LIVING realized 8.90 x 3.15 m (aspect 2.83) past its LIVING template's 2.5

### B06 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 4575, 'GRID_INFEASIBLE': 2200, 'SHORT_SIDE_INFEASIBLE': 749}

### B07 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 7521, 'SHORT_SIDE_INFEASIBLE': 2426, 'GRID_INFEASIBLE': 3121}

### B08 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'SHORT_SIDE_INFEASIBLE': 5289, 'AREA_INFEASIBLE': 6713, 'GRID_INFEASIBLE': 3745}

### B09 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 5123, 'GRID_INFEASIBLE': 3509, 'SHORT_SIDE_INFEASIBLE': 1268}

### B11 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 5918, 'GRID_INFEASIBLE': 5361, 'SHORT_SIDE_INFEASIBLE': 2815}

### B12 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'SHORT_SIDE_INFEASIBLE': 2844, 'GRID_INFEASIBLE': 3526, 'AREA_INFEASIBLE': 8480}

### B13 — furthest stage passed: REALIZATION
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 5059, 'SHORT_SIDE_INFEASIBLE': 4048, 'GRID_INFEASIBLE': 2286}
- VALIDATORS refusals over all witnesses x envelopes: {'VALIDATION_FAILED': 7}
- witness 2 validator detail: 12.4x12.4 m: C3: LIVING aspect 2.72 > 2.5; C20: LIVING realized 8.70 x 3.20 m (aspect 2.72) past its LIVING template's 2.5
- witness 3 validator detail: 12.4x12.4 m: C3: LIVING aspect 2.72 > 2.5; C20: LIVING realized 8.70 x 3.20 m (aspect 2.72) past its LIVING template's 2.5

### B17 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 8775, 'GRID_INFEASIBLE': 7148, 'SHORT_SIDE_INFEASIBLE': 1477}

### B18 — furthest stage passed: EMBEDDING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 5133, 'GRID_INFEASIBLE': 7978, 'SHORT_SIDE_INFEASIBLE': 1609}

### B20 — furthest stage passed: SIZING
- SIZING refusals over all witnesses x envelopes: {'AREA_INFEASIBLE': 6222, 'SHORT_SIDE_INFEASIBLE': 2722, 'GRID_INFEASIBLE': 5455}
- REALIZATION refusals over all witnesses x envelopes: {'NO_ENTRANCE': 1}

## Successful cases — realized geometry

### B01 — witness 0 (rank score 0.1625, 2 rows x 4 cols), envelope 10.5x7.0 m, spatial 6/6, access 4/4

| room | x | y | w | d | area m2 |
|---|---|---|---|---|---|
| BATHROOM_1 | 2.0 | 5.7 | 2.4 | 3.3 | 7.92 |
| HALL | 4.4 | 5.7 | 4.95 | 3.3 | 16.34 |
| KITCHEN | 9.35 | 5.7 | 3.15 | 3.3 | 10.39 |
| LIVING | 6.7 | 2.0 | 5.8 | 3.7 | 21.46 |
| MASTER | 2.0 | 2.0 | 4.7 | 3.7 | 17.39 |

## Reproducing

```
# stage 1 (isolated venv with python-sat; regenerates witnesses.json, deterministic):
python backend/spikes/topology_representation/band_witnesses.py <briefs.json> docs/reports/142c-exact-band-embedding/witnesses.json 150 120
# stage 2 (project venv, no solver dependency):
cd backend && uv run python -m app.ai_harness.topology_poc.exact_band_142c
```
