# #142C — Exact band embedding through the unchanged GridWing path: result and attribution

**Question.** Does an exact band embedding unlock the existing `GridWing` → `_solve_grid` →
`realize_layout` → `validate` path for the topologies GridWing can already represent?

**Answer: no — the primary criterion is NOT met (1/13), and the experiment falsifies the assumption
that topology is the primary blocker for the representable family.** Exact embedding succeeds for
13/13 band-representable briefs (every witness re-verified with the realizer's own geometry), but the
unchanged downstream path realizes and validates only B01. The dominant blocker is **`_solve_grid`'s
rank-1 (proportional) sizing**: for 207 witnesses across 9 briefs an exact row-height/column-width
sizing satisfying the realizer's own per-cell checks exists, and `_solve_grid` sizes **0/207** of
them even when handed that sizing's own envelope. Behind sizing sit two further, smaller blockers
that an exact sizing exposes (measured with a solver stub, experiment-only): entrance resolution
(`NO_ENTRANCE`) and door-ability (C5/C24), then C26/C3. With an exact sizing, 3/13 briefs (B01, B08,
B13) pass realization and the unchanged validators end-to-end. Per the stop rule: stop here, add no
representation power, no L-shapes.

Generated artifacts in this directory: `results.md` / `results.json` (the stage matrix, driver
output), `witnesses.json` (exact embeddings), `sizing_feasibility.json`, `rank1_vs_lp.json`,
`lp_sizing_probe.json`, `sizing_feasibility_extended_summary.json`, `rank1_vs_lp_extended.json`,
`lp_sizing_probe_extended.json` (attribution evidence; the 5.8 MB extended witness file is regenerable and not committed).

## Repository hygiene (§11)

- `origin/main` is still `a7f1ad2` (the commit the investigation read); no drift in
  `graph_embedding.py`, `rectilinear_realizer.py`, `topology_poc/`, validators, access rules or the
  frozen dataset (sha `03c52be5…`).
- Baseline rerun: `gap_closure_142a` on this worktree reproduces the committed #142A `results.md`
  **byte-identical**.
- Work is on branch `experiment/142c-exact-band-embedding` in its own worktree; the main checkout
  was not touched. `python-sat` stays in a scratch venv (§10): the driver reads a committed witness
  artifact and runs in the dev venv with no new dependency; the attribution scripts use `scipy`,
  already present transitively, and live under `backend/spikes/` only.

## What was built (minimum isolated integration)

| piece | where | role |
|---|---|---|
| exact band embedder | `backend/spikes/topology_representation/band_witnesses.py` (isolated venv, `python-sat`) | per brief: exact classification; for band-representable graphs, distinct band layouts carrying EVERY required edge, emitted as `GridWing` rows/spans; explicit UNSAT classes, never partial |
| witness artifact | `witnesses.json` | 13 briefs × up to 300 witnesses (round-robin over every grid W+H=n+1, so no single band count dominates), ranked by a generic rank-1 plausibility score; 7 UNSAT briefs with their proven class |
| driver | `backend/app/ai_harness/topology_poc/exact_band_142c.py` (dev venv, no solver) | re-verifies every witness geometrically (`Rect.shared_edge_len_u`), then runs the **unchanged** `GridWing` → `realize_layout` path over a fixed envelope ladder (11 scales × 9 aspects on the rooms' total target area, inside footprint+4 m), recording PASS/FAIL per stage |
| test | `backend/tests/ai_harness/test_exact_band_142c.py` | stage mapping never reports a downstream refusal as topology; every committed witness is a well-formed GridWing carrying all edges |
| attribution scripts | `backend/spikes/topology_representation/{sizing_feasibility,rank1_vs_lp,lp_sizing_probe}.py` | §"Failure attribution" below |

Nothing under `app/vertical_slice/` changed. No validator, room minimum, access rule or proposal
datum was touched. Witness order and envelopes are generic; nothing was tuned per brief.

## 1. Stage-by-stage matrix, all 20 briefs

`GRAPH → EXACT BAND EMBEDDING → GRIDWING SIZING → REALIZATION → VALIDATORS` (a stage is PASS when at
least one witness × envelope passed it; "—" = not applicable).

| brief | n | m | classification | EMBEDDING | SIZING | REALIZATION | VALIDATORS | witnesses tried | #142A |
|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | 6 | BAND_REPRESENTABLE | PASS | PASS | PASS | **PASS** (10.5×7.0 m, spatial 6/6, access 4/4) | 1/68 | REFUSED DIMENSION_SOLVER (pinwheel) |
| B02 | 6 | 9 | UNSAT — REPRESENTATION_LIMIT (K4 BATHROOM_1/HALL/LIVING/MASTER_BEDROOM) | FAIL | — | — | — | 0 | not run |
| B03 | 6 | 8 | UNSAT — REPRESENTATION_LIMIT (HALL–BATHROOM_1, 3 common neighbours) | FAIL | — | — | — | 0 | not run |
| B04 | 8 | 9 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 185/185 | not run |
| B05 | 7 | 9 | BAND_REPRESENTABLE | PASS | PASS | PASS | FAIL (C3/C20 LIVING aspect 2.83) | 168/168 | not run |
| B06 | 8 | 11 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 76/76 | not run |
| B07 | 9 | 12 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 132/132 | not run |
| B08 | 8 | 10 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 181/181 | not run |
| B09 | 9 | 14 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 100/100 | not run |
| B10 | 9 | 14 | UNSAT — REPRESENTATION_LIMIT (K4 BATHROOM_1/BEDROOM_1/HALL/LIVING; LIVING–HALL lens) | FAIL | — | — | — | 0 | REFUSED TOPOLOGY_EMBEDDING 9/14 |
| B11 | 11 | 13 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 162/162 | not run |
| B12 | 10 | 13 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 150/150 | not run |
| B13 | 10 | 12 | BAND_REPRESENTABLE | PASS (12/12) | PASS | PASS | FAIL (C3/C20 LIVING aspect 2.72) | 150/150 | REFUSED TOPOLOGY_EMBEDDING 9/12 |
| B14 | 11 | 15 | UNSAT — REPRESENTATION_LIMIT (LIVING–HALL, 3 common neighbours) | FAIL | — | — | — | 0 | not run |
| B15 | 11 | 15 | UNSAT — REPRESENTATION_LIMIT (HALL–BATHROOM_2, 3 common neighbours) | FAIL | — | — | — | 0 | REFUSED TOPOLOGY_EMBEDDING 9/15 |
| B16 | 13 | 19 | UNSAT — REPRESENTATION_LIMIT (LIVING–HALL, 3 common neighbours) | FAIL | — | — | — | 0 | REFUSED TOPOLOGY_EMBEDDING 11/19 |
| B17 | 12 | 13 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 200/200 | not run |
| B18 | 13 | 14 | BAND_REPRESENTABLE | PASS | FAIL | FAIL | FAIL | 184/184 | not run |
| B19 | 12 | 25 | UNSAT — NON_PLANAR_TOPOLOGY | FAIL | — | — | — | 0 | not run |
| B20 | 10 | 11 | BAND_REPRESENTABLE | PASS | PASS | FAIL (NO_ENTRANCE) | FAIL | 180/180 | not run |

Counts over the 13 band-representable briefs (denominator always 13):

| stage | passed |
|---|---|
| exact band embedding (verified geometrically) | **13/13** |
| GridWing sizing (`_solve_grid` + per-cell area/short-side checks) | **4/13** (B01, B05, B13, B20) |
| realization (footprint, entrance, doors, windows) | **3/13** (B01, B05, B13) |
| validators PASS (unchanged `validate`) | **1/13** (B01) |

**Primary criterion (≥ 9/13): NOT MET.** Refusal volume over all witnesses × envelopes:
AREA_INFEASIBLE 83,2xx, GRID_INFEASIBLE 50,8xx, SHORT_SIDE_INFEASIBLE 33,7xx; VALIDATION_FAILED 12;
NO_ENTRANCE 4 (exact per-brief histograms in `results.md`).

## 2. B01 — carrier-selection diagnosis (§3)

Confirmed. Bypassing the pinwheel-first rule, the very first exact band witness (ranked by the
generic score) realized at the first envelope that sized: rows `[MASTER 2 | LIVING 2]` over
`[BATHROOM_1 1 | HALL 2 | KITCHEN 1]`, envelope 10.5 × 7.0 m, **validator PASS, spatial 6/6,
access 4/4**. #142A's `SHORT_SIDE_INFEASIBLE` for B01 was a property of the pinwheel carrier, not of
the brief. (With an exact sizing, 16 of B01's 40 dimensionally feasible witnesses pass end-to-end;
12 fail C26 circulation ratio, 12 `NO_ENTRANCE` — see §4.)

## 3. B13 — search-failure proof (§4)

- 150 exact witnesses, each verified to carry **12/12** required edges before sizing (vs. 9/12 for
  the production search in #142A).
- Unchanged downstream: 5/150 witnesses sized (rank-1) and reached the validators; all 5 failed
  **C3/C20: LIVING aspect 2.72 > 2.5** (LIVING realized 8.70 × 3.20 m). 145/150 died in sizing.
- Attribution: 21/100 of B13's witnesses have an exact sizing satisfying the realizer's checks (18
  also within the validators' max-aspect); `_solve_grid` sizes 0/21 of them with their own envelope.
  With the exact sizing stubbed in, **2 witnesses pass realization + all validators** (the rest:
  `NO_ENTRANCE` 11, C5 door-ability 6, AREA 2). **B13's blocker is precisely the rank-1 sizing**, and
  behind it entrance/door placement — never topology.

## 4. Failure attribution for every brief that died after exact embedding (§8)

Three independent measurements, all on the same witnesses (`sizing_feasibility.json`,
`rank1_vs_lp.json`, `lp_sizing_probe.json`):

- **(a) Does ANY sizing exist?** Alternating-LP search over row heights × column widths for exactly
  `_build_grid_wing`'s own checks (gross cell area in the zone's [min,max], short side ≥ min_short +
  0.3 m, inside footprint+4 m), with and without the validators' max-aspect. Existence search:
  "found" is a proof; "none found" is reported as such.
- **(b) Rank-1 with the ideal envelope.** Each LP-feasible witness's own envelope (Σ widths × Σ
  heights) handed to the unchanged path.
- **(c) Solver stub.** `_solve_grid` replaced in-process by the LP sizing; everything after it
  (walls, access edges, `resolve_entrance`, doors, windows, furniture, `validate`) unchanged.

| brief | witnesses checked | (a) feasible sizing exists | (a) also within max-aspect | (b) rank-1 sized with the LP's envelope | (c) with exact sizing: realization pass / validators pass | dominant blocker |
|---|---|---|---|---|---|---|
| B01 | 68 (complete family) | 40 | 40 | 1 (the realized one) | 28 / **16** | none (realized); secondary: NO_ENTRANCE 12, C26 12 |
| B04 | 100 | 11 | 9 | **0** | 0 / 0 | **rank-1 sizing**, then NO_ENTRANCE (6), AREA (5) |
| B05 | 100 | 43 | 35 | **0** | 7 / 0 | **rank-1 sizing**, then NO_ENTRANCE (28), C3 net area + C5/C24 door-ability (7) |
| B08 | 100 | 19 | 16 | **0** | 10 / **3** | **rank-1 sizing**, then NO_ENTRANCE (9), C5/C24 (7) |
| B11 | 100 | 2 | 2 | **0** | 0 / 0 | **rank-1 sizing**, then NO_ENTRANCE (2) |
| B13 | 100 | 21 | 18 | **0** | 8 / **2** | **rank-1 sizing**, then NO_ENTRANCE (11), C5 (6) |
| B20 | 100 (+1,800 extended: 65 feasible, 48 within aspect, rank-1 0/65) | 9 | 8 | **0** | 4 / 0 (extended) | **rank-1 sizing**, then NO_ENTRANCE (56 of 65), C3/C4 (4) |
| B06 | 156 (complete family) | 0 | 0 | 0 | — | **dimensional feasibility of the band family** (see below) |
| B09 | 180 (complete family) | 0 | 0 | 0 | — | **dimensional feasibility of the band family** |
| B07 | 1,241 (extended, capped) | 0 | 0 | 0 | — | **no feasible band sizing found** (1,241 witnesses) |
| B12 | 1,355 (extended, capped) | 13 | 11 | **0** | 4 / 0 | **rank-1 sizing**, then NO_ENTRANCE (5), C5/C24 (4) |
| B17 | 2,000 (extended, capped) | 24 | 24 | **0** | 4 / 0 | **rank-1 sizing**, then NO_ENTRANCE (13), C3 net area + C5 (4) |
| B18 | 1,840 (extended, capped) | 0 | 0 | 0 | — | **no feasible band sizing found** (1,840 witnesses) |

Reading, in the order §8 asks:

1. **Rank-1 sizing — dominant.** 207 witnesses in 9 briefs (B04, B05, B08, B11, B13, B20 in the base
   set; B12, B17, B20 only in the extended sets of 1,355–2,000 witnesses) are dimensionally feasible
   under the realizer's own checks; `_solve_grid` sizes 0/207 of them even with the right envelope. The
   proportional fit (R + C degrees of freedom for R·C targets, which `_solve_grid`'s own docstring
   already calls "the best rank-1 compromise") cannot hit per-cell bounds for a heterogeneous band
   layout: a hub band (HALL/LIVING spanning the full width) forces every other row's cells to share
   the same column widths, so a 1.5 m-deep hall pulls the bedroom columns to widths their own
   minima reject, and vice versa.
2. **Dimensional feasibility — the blocker for B06 and B09 (complete families: 156 and 180 band
   layouts, none sizable) and, as far as 1,241 / 1,840 witnesses go, B07 and B18.** No band layout
   found for these carries the graph AND has a feasible sizing under the `ROOM_TEMPLATES` bounds.
   (B12/B17/B20 looked the same at 100 witnesses and turned out sizable at 1,355–2,000: the
   feasible band layouts are rare, which is itself a finding about this family.) The mechanism is visible in the witnesses: a room that must touch many
   others ends up as a **single-cell band**, and its own max area caps the wing width at
   `max_area / (min_short + 0.3)` — 4.83 m for a BEDROOM, 6.06 m for MASTER, 6.32 m for a BATHROOM,
   9.63 m for KITCHEN (`single_cell_band_width_caps_m`); a wing that narrow cannot host the other
   bands. This is the band representation and the room bounds interacting, not topology: the graph is
   carried, the rooms cannot be shaped.
3. **Realization — `NO_ENTRANCE`.** Once sizing is exact, the most frequent refusal is
   `resolve_entrance` finding no ALLOWED_ENTRANCE-role zone fronting the street: band layouts freely
   put LIVING/HALL in a middle band. The embedder carries no orientation/entrance intent (the
   proposals' `entrance_relation` is not an input to the experiment, by scope).
4. **Carrier translation — not a cause.** Every witness is verified against the realizer's own
   geometry before use (test), and the band witnesses translate 1:1 into `GridWing` rows/spans.
5. **Validator incompatibility — small, and specific.** With exact sizing the validators reject
   witnesses for C5/C24 (a room whose only touching neighbours are pairs `access_rules` forbids a
   door between — an enclosed room with no way in), C26 (circulation ratio > 24 % when HALL is a
   full-width band), and C3 (net area below minimum although the realizer's gross-area check passed
   — `_build_grid_wing` compares **gross** rect area to **net** bounds, `validate` C3 uses net; a
   latent inconsistency worth a separate note, not fixed here).

## 5. Comparison against #142A

| | #142A (production search) | #142C (exact embedding, same downstream) |
|---|---|---|
| B01 | pinwheel, REFUSED SHORT_SIDE_INFEASIBLE | **REALIZED + validator PASS**, 6/6 spatial, 4/4 access |
| B10 / B15 / B16 | REFUSED TOPOLOGY_EMBEDDING 9/14, 9/15, 11/19 (search's best) | UNSAT — REPRESENTATION_LIMIT, with the named obstruction (never attempted) |
| B13 | REFUSED TOPOLOGY_EMBEDDING 9/12 | embedding **12/12**; dies in rank-1 sizing (5 witnesses reach the validators, fail LIVING aspect) |
| other 15 | not run | 8 band-representable: all die in sizing; 6 obstructed/non-planar: explicit UNSAT |
| realized / validator-passing | 0/5 | 1/20 (1/13 band-representable) |

Everything #142A classified TOPOLOGY_EMBEDDING for B13 was a search artefact; everything it classified
TOPOLOGY_EMBEDDING for B10/B15/B16 is a real representation limit; its one DIMENSION_SOLVER case
(B01) was a carrier choice.

## 6. Recommendation (measured)

- **Stop here** (per the stop rule): no L-shapes, no second realizer, no GridWing rewrite. Topology
  is not the primary blocker for the representable family; **`_solve_grid` is**, and behind it
  entrance resolution and door-ability.
- The next bounded question, in the same frame: *"Does an exact per-cell sizing of a band layout
  (row heights × column widths as free variables with each cell's own bounds — an LP per witness, no
  proportionality) unlock the unchanged realization + validators?"* The stub already answers it for
  the current witnesses: **3/13 pass end-to-end (B01, B08, B13)**, 6/13 (B04, B05, B11, B12, B17,
  B20) remain blocked by `NO_ENTRANCE` first and then C5/C24 door-ability, C3 net area, C4 safe-room
  RC walls, C26; 4/13 (B06, B07, B09, B18) have no feasible band sizing found at all. So an exact sizing solver is necessary but, alone, reaches ~3/13; the experiment after it
  must carry **entrance/orientation intent into the embedder** (which band fronts the street) and
  **door-ability** (require every room to touch at least one room it may be entered from — an
  `access_rules` constraint the embedder can take as input), both of which are topology-side
  constraints the exact embedder can enforce at zero representation cost.
- For B06/B09-type briefs the honest reading is that a band layout cannot shape these rooms within
  `ROOM_TEMPLATES`; whether a general slicing tree (the Geometry Core's family, which lets a hub
  touch rooms in several bands without spanning the full width) is dimensionally feasible there is
  the right follow-up question — a dimensional one, still not an L-shape one.
- Zero-risk diagnostic (§9): the classification BAND_REPRESENTABLE / RECTANGULAR_OBSTRUCTION /
  NON_PLANAR is emitted per brief by the embedder (planarity, K4, triple-lens: exact, O(n·Δ²)) and
  could be reported on proposals as-is; it flags 7/20 proposals before any geometry.

## Reproducing

```
# stage 1 — isolated venv (python-sat); deterministic
python backend/spikes/topology_representation/band_witnesses.py <briefs_142c.json> docs/reports/142c-exact-band-embedding/witnesses.json 300 90
# stage 2 — dev venv, no solver dependency
cd backend && uv run python -m app.ai_harness.topology_poc.exact_band_142c --max-witnesses 300
# attribution (dev venv; scipy present transitively)
python backend/spikes/topology_representation/sizing_feasibility.py <briefs> witnesses.json results.json sizing_feasibility.json 100
python backend/spikes/topology_representation/rank1_vs_lp.py sizing_feasibility.json witnesses.json rank1_vs_lp.json
python backend/spikes/topology_representation/lp_sizing_probe.py sizing_feasibility.json witnesses.json lp_sizing_probe.json
```
`briefs_142c.json` is the per-brief export of zones (`ROOM_TEMPLATES` bounds), graph and footprint
from the frozen dataset (`gap_closure_142a.room_area_intent`), regenerated by the one-liner in the
investigation notes; the embedder needs it only for witness ranking.
