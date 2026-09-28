# Real-plan adjacency priors — full-corpus diagnostic re-run (Issue #149-B)

Re-runs #141's own decision-relevance + four-state diagnostic over the frozen, committed **432-context** regression corpus, scoring every candidate against the FULL-CORPUS TRAIN-built **spatial_touching** table and calibrating "near real" against that same table's own HOLDOUT distribution (never in-sample). Measurement only — see this Issue's own Out-of-scope section.

**Table used: `spatial_touching` — the UNION of adjacency and via_door edges (Table C).** This is the table our own `y` (`app.vertical_slice.adjacency_priors._rects_adjacent`, a pure geometric shared-boundary test indifferent to door placement) is actually comparable to — see `docs/reports/real-plan-priors/adjacency-fullcorpus.md`'s own module docstring, "WHICH TABLE OUR OWN Y IS COMPARABLE TO, AND WHY". The `spatial_adjacency`-only numbers this diagnostic originally reported are restated side by side below, not replaced.

## Holdout calibration used (AC-2)

- `real_median_score` (HOLDOUT): **-0.128868**
- `real_stdev_score` (HOLDOUT, population): **0.137503**
- threshold (`median - stdev`): **-0.26637**
- HOLDOUT plans scored: **3459**

## Headline result (AC-5)

- contexts: **432** (404 PLANNED/analyzable, 28 REFUSED, not analyzable)
- % of candidate sets with prior variance (`score_spread >= 1e-6`): **27.7%**
- % decision-relevant (tied AND scores differ): **0.0%**
- best candidate score anywhere in the corpus: **-0.351264**
- candidate score distribution: min=-5.465778, median=-2.29532, max=-0.351264

## Four-state classification (AC-5)

| state | count | share of analyzable |
|---|---|---|
| VARIES_COULD_CHANGE_WINNER | 0 | 0.0% |
| VARIES_BLOCKED_BY_RANKING | 0 | 0.0% |
| NO_REAL_VARIANCE | 0 | 0.0% |
| NO_CANDIDATE_NEAR_REAL | 404 | 100.0% |

`VARIES_COULD_CHANGE_WINNER`/`VARIES_BLOCKED_BY_RANKING` collapse #141's states 1/2: an actual re-ranked ON pass with THIS table is out of scope for this Issue (it is never wired into production), so "could change" is reported analytically (`could_change_winner`: tied AND this table's own scores differ) rather than empirically confirmed as "did change" — see the script's own module docstring. Measured: **0/404** tied contexts have `could_change_winner=True` under this table. Of the tied contexts, **345** have byte-identical raw eligible-pair outcome patterns across every tied candidate — a table-independent proof this term cannot discriminate them under ANY table, not just this one (the structural "forced tree + free twin" finding #141 made). The remaining **59** have differing raw outcome patterns yet STILL score identically under this specific table (verified directly) — the pairs where they differ fall outside this table's own role vocabulary (a role name this corpus never labels, e.g. a corridor/hall role) and contribute nothing to the score, per `plan_log_likelihood`'s own "unsupported pair" rule; a table WITH a row for that role could, in principle, discriminate them, but this one — like #141's 19-plan table — cannot.

## Distance and percentile, not only a binary threshold (AC-6)

z-distance stats (best candidate vs HOLDOUT distribution): min=-38.813, median=-15.7557, max=-1.6174

percentile stats (best candidate's position within the HOLDOUT distribution): min=0.0, median=0.0, max=13.88

| context | status | state | best_candidate_score | z_distance | percentile |
|---|---|---|---|---|---|
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.680194 | -11.2821 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.680194 | -11.2821 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.292415 | -8.462 | 0.12 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | REFUSED | None | None | None | None |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.683099 | -18.5758 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.29532 | -15.7557 | 0.0 |

(first 20 of 432 contexts shown; full per-context table in the companion JSON report.)

## Side by side: `spatial_touching` (this report) vs `spatial_adjacency` (repair evidence, AC-5/AC-6)

Same 432-context corpus, same scoring/classification code, different TRAIN table and its own HOLDOUT calibration — kept apart per AC-2 (never in-sample, never one table's calibration applied to the other's scores).

| | `spatial_touching` | `spatial_adjacency` |
|---|---|---|
| holdout median | -0.128868 | -0.000665 |
| holdout stdev | 0.137503 | 0.058796 |
| holdout threshold | -0.26637 | -0.059461 |
| best candidate score overall | -0.351264 | -0.942193 |
| z-distance median | -15.7557 | -43.0135 |
| percentile median | 0.0 | 0.0 |
| VARIES_COULD_CHANGE_WINNER | 0 | 0 |
| VARIES_BLOCKED_BY_RANKING | 0 | 0 |
| NO_REAL_VARIANCE | 0 | 0 |
| NO_CANDIDATE_NEAR_REAL | 404 | 404 |

The four-state classification is UNCHANGED between the two tables (404/404 `NO_CANDIDATE_NEAR_REAL` either way — the engine's candidates are still, on this corpus, further from either table's own real-plan distribution than its own threshold), but the DISTANCE moves substantially: z-distance median improves from -43.0135 (`spatial_adjacency`) to -15.7557 (`spatial_touching`), and percentile max from 0.26% to 13.88% — the underlying 432-context corpus, scoring code and holdout split are byte-identical between the two columns, so this shift is entirely the table's own doing. This is why AC-6 requires distance/percentile alongside the binary threshold: on the `spatial_adjacency` table alone, this corpus looked uniformly, drastically far from real; under the table our own `y` is actually comparable to, it is still far, but far less so — see the per-pair evidence in `docs/reports/real-plan-priors/adjacency-fullcorpus.md`, section C.

## Reproduce

From `backend/`:

    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py --save diag-touching.json --table-kind spatial_touching --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py --save diag-adjacency.json --table-kind spatial_adjacency --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py --compare diag-touching.json --baseline diag-adjacency.json --report diag-report.json --write-markdown ../docs/reports/real-plan-priors/adjacency-fullcorpus-diagnostic.md
