# Realizability gap closure (Issue #162 / #142A)

Generalizes `app.vertical_slice.rectilinear_realizer` beyond the fixed 5-room pinwheel with a genuine 2D structural carrier (`GridWing`) and a matching dimension solver (`_solve_grid`), and runs #160's own frozen 5 selected cases (B01, B10, B13, B15, B16) through it via the new embedding decision layer (`graph_embedding.embed_adjacency_graph`). No validator, access rule, room minimum, wet-core rule, critic or proposal datum changes anywhere in this work (AC-8).

## STOP RULE (AC-10)

**Did not fire.** The extension stayed bounded: one new `Wing` variant (`GridWing`) following the EXACT same pattern `PinwheelWing`/`RowWing` already establish (a dataclass + a `_build_*_wing` function + a sizing solver), one new decision module (`graph_embedding.py`) that searches among the THREE existing wing shapes and refuses explicitly when none fits, and one small, central, additive fix (`_filter_wet_room_access`) for a pre-existing gap (no wing ever passed `wet_rooms` to `validate()`) that would otherwise have misclassified every wet-room-bearing case as a VALIDATOR failure regardless of this Issue's own structural work. No second realization engine, no change to `geometry_core`, no change to any validator/access rule/room minimum.

**Frozen dataset (AC-7)**: `docs/reports/llm-topology-poc/generation-dataset.json`, `dataset_sha256` `03c52be5357ff41f30ee104cfd1ff0d2760bba0cf7f0576b64565767cb321598` — verified via `generation_dataset.load_dataset()` (the SAME preflight #151 established: a canonical re-hash of the file's own body, raising rather than silently proceeding on any mismatch). No new LLM call, no change to any proposal, no case substituted after seeing a failure (AC-7).

## Gate A — can the n>5 topologies be structurally PLACED? (AC-3)

Before any dimensioning: required spatial-adjacency edges, how many of them the chosen placement structurally achieves (geometric touching, verified against the real built rects whenever the case later reaches Gate B successfully), lost, extra, and which placement form (ROW / PINWHEEL / GRID RxC) the embedding search chose — or, when no available structure reaches full coverage, the honest best found.

| brief | n rooms | required edges | structurally preserved | lost | extra | placement form | embeddable |
|---|---|---|---|---|---|---|---|
| B10 | 9 | 14 | 9 | 5 | 0 | GRID 3x3 | False |
| B13 | 10 | 12 | 9 | 3 | 0 | GRID 3x4 | False |
| B15 | 11 | 15 | 9 | 6 | 0 | GRID 4x3 | False |
| B16 | 13 | 19 | 11 | 8 | 0 | GRID 5x3 | False |

**0/4 of the n>5 cases are structurally embeddable** by the generalized realizer (row/pinwheel/grid) — the measured answer to Gate A, before any sizing is attempted.

## Gate B — can every placed case be DIMENSIONED? (AC-4)

All 5 cases, B01 included (never assumed feasible). No room minimum is weakened anywhere in this diff — every refusal below is `realize_layout`'s own, unmodified area/short-side/aspect check, or the embedding step's own honest TOPOLOGY_EMBEDDING refusal when Gate A itself already failed.

| brief | dimensioned | envelope used | brief footprint (m) | refusal | failure class |
|---|---|---|---|---|---|
| B01 | False | — | 20.0x22.0 | SHORT_SIDE_INFEASIBLE | DIMENSION_SOLVER |
| B10 | False | — | 16.0x18.0 | TOPOLOGY_EMBEDDING | TOPOLOGY_EMBEDDING |
| B13 | False | — | 11.0x12.0 | TOPOLOGY_EMBEDDING | TOPOLOGY_EMBEDDING |
| B15 | False | — | 12.5x14.5 | TOPOLOGY_EMBEDDING | TOPOLOGY_EMBEDDING |
| B16 | False | — | 18.0x12.0 | TOPOLOGY_EMBEDDING | TOPOLOGY_EMBEDDING |

**0/5 cases can be dimensioned** while preserving the structure and every hard room minimum.

## Per-case final result (AC-9)

| brief | topology (rooms/edges) | placement | adjacency preserved | access preserved | dimension result | validator result | final status | reason |
|---|---|---|---|---|---|---|---|---|
| B01 | 5/6 | PINWHEEL | — | — | DIMENSION_SOLVER | NOT REACHED | REFUSED | SHORT_SIDE_INFEASIBLE: KITCHEN: pinwheel-realized short side 1.50 m (gross) < 2.4 m (net) + 0.3 m inset margin (exhaustive 31x31 width/height grid search over this SAME placement found zero feasible envelopes) |
| B10 | 9/14 | GRID 3x3 | — | — | TOPOLOGY_EMBEDDING | NOT REACHED | REFUSED | TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 9 rooms: best found is GRID 3x3, achieving 9/14 requested spatial-adjacency pairs |
| B13 | 10/12 | GRID 3x4 | — | — | TOPOLOGY_EMBEDDING | NOT REACHED | REFUSED | TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 10 rooms: best found is GRID 3x4, achieving 9/12 requested spatial-adjacency pairs |
| B15 | 11/15 | GRID 4x3 | — | — | TOPOLOGY_EMBEDDING | NOT REACHED | REFUSED | TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 11 rooms: best found is GRID 4x3, achieving 9/15 requested spatial-adjacency pairs |
| B16 | 13/19 | GRID 5x3 | — | — | TOPOLOGY_EMBEDDING | NOT REACHED | REFUSED | TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 13 rooms: best found is GRID 5x3, achieving 11/19 requested spatial-adjacency pairs |

**realized/5: 0** · **topology-preserving/5: 0** · **validator-passing/5: 0**

## Preservation detail, per realized case (AC-5)

No selected case realized in this run — nothing to measure preservation on.

## Failure classification (AC-6)

Every refusal above is exactly one of **TOPOLOGY_EMBEDDING** (Gate A itself could not embed the requested graph in any available structure), **PLACEMENT** (a structure was selected but no room-to-slot assignment of it could satisfy the request), **DIMENSION_SOLVER** (structure embedded, but no envelope this run's retry ladder tried could size every room within its own hard minimum), **FOOTPRINT_INFEASIBLE** (the realized footprint exceeds the brief's own stated footprint), **REALIZER_INTERNAL** (a construction defect unrelated to sizing or topology), or **VALIDATOR** (`validation.validate` rejected the realized geometry) — never a generic "cannot realize". **Disclosed gap**: `PLACEMENT` is not produced by any code path in this implementation — `graph_embedding.embed_adjacency_graph` decides "which structure" and "which assignment of it" together in one search and reports every shortfall as `TOPOLOGY_EMBEDDING` (the best structure/assignment pair found), never distinguishing "no structure could ever fit" from "a structure was selected but its own assignment search fell short". This is honestly reported as an unreached bucket, not demonstrated by a constructed example.

## Remaining measured capability gaps

- **B01**: DIMENSION_SOLVER — SHORT_SIDE_INFEASIBLE: KITCHEN: pinwheel-realized short side 1.50 m (gross) < 2.4 m (net) + 0.3 m inset margin (exhaustive 31x31 width/height grid search over this SAME placement found zero feasible envelopes)
- **B10**: TOPOLOGY_EMBEDDING — TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 9 rooms: best found is GRID 3x3, achieving 9/14 requested spatial-adjacency pairs
- **B13**: TOPOLOGY_EMBEDDING — TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 10 rooms: best found is GRID 3x4, achieving 9/12 requested spatial-adjacency pairs
- **B15**: TOPOLOGY_EMBEDDING — TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 11 rooms: best found is GRID 4x3, achieving 9/15 requested spatial-adjacency pairs
- **B16**: TOPOLOGY_EMBEDDING — TOPOLOGY_EMBEDDING: no available 2D structure (row/pinwheel/grid; grid shapes with 1-6 rows tried) can embed the requested graph among 13 rooms: best found is GRID 5x3, achieving 11/19 requested spatial-adjacency pairs

## Reproducing this report

```
cd backend
uv run python -m app.ai_harness.topology_poc.gap_closure_142a
```
