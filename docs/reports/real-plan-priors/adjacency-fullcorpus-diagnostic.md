# Real-plan adjacency priors — full-corpus diagnostic re-run (Issue #149-B)

Re-runs #141's own decision-relevance + four-state diagnostic over the frozen, committed **432-context** regression corpus, scoring every candidate against the FULL-CORPUS TRAIN-built spatial-adjacency prior and calibrating "near real" against that same artifact's HOLDOUT distribution (never in-sample). Measurement only — see this Issue's own Out-of-scope section.

## Holdout calibration used (AC-2)

- `real_median_score` (HOLDOUT): **-0.000665**
- `real_stdev_score` (HOLDOUT, population): **0.058796**
- threshold (`median - stdev`): **-0.059461**
- HOLDOUT plans scored: **3459**

## Headline result (AC-5)

- contexts: **432** (404 PLANNED/analyzable, 28 REFUSED, not analyzable)
- % of candidate sets with prior variance (`score_spread >= 1e-6`): **27.7%**
- % decision-relevant (tied AND scores differ): **0.0%**
- best candidate score anywhere in the corpus: **-0.942193**
- candidate score distribution: min=-6.703052, median=-2.529689, max=-0.942193

## Four-state classification (AC-5)

| state | count | share of analyzable |
|---|---|---|
| VARIES_COULD_CHANGE_WINNER | 0 | 0.0% |
| VARIES_BLOCKED_BY_RANKING | 0 | 0.0% |
| NO_REAL_VARIANCE | 0 | 0.0% |
| NO_CANDIDATE_NEAR_REAL | 404 | 100.0% |

`VARIES_COULD_CHANGE_WINNER`/`VARIES_BLOCKED_BY_RANKING` collapse #141's states 1/2: an actual re-ranked ON pass with THIS table is out of scope for this Issue (it is never wired into production), so "could change" is reported analytically (`could_change_winner`: tied AND this table's own scores differ) rather than empirically confirmed as "did change" — see the script's own module docstring. Measured: **0/404** tied contexts have `could_change_winner=True` under this table. Of the tied contexts, **345** have byte-identical raw eligible-pair outcome patterns across every tied candidate — a table-independent proof this term cannot discriminate them under ANY table, not just this one (the structural "forced tree + free twin" finding #141 made). The remaining **59** have differing raw outcome patterns yet STILL score identically under this specific table (verified directly) — the pairs where they differ fall outside this table's own role vocabulary (a role name this corpus never labels, e.g. a corridor/hall role) and contribute nothing to the score, per `plan_log_likelihood`'s own "unsupported pair" rule; a table WITH a row for that role could, in principle, discriminate them, but this one — like #141's 19-plan table — cannot.

## Distance and percentile, not only a binary threshold (AC-6)

z-distance stats (best candidate vs HOLDOUT distribution): min=-113.9939, median=-43.0135, max=-16.0135

percentile stats (best candidate's position within the HOLDOUT distribution): min=0.0, median=0.0, max=0.26

| context | status | state | best_candidate_score | z_distance | percentile |
|---|---|---|---|---|---|
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 132.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -0.942193 | -16.0135 | 0.26 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 181.25, "footprint_depth_m" | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -0.942193 | -16.0135 | 0.26 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -2.529689 | -43.0135 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | REFUSED | None | None | None | None |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -1.945098 | -33.0708 | 0.0 |
| {"bedrooms": 1, "built_area_m2": 200.0, "footprint_depth_m": | PLANNED | NO_CANDIDATE_NEAR_REAL | -3.532595 | -60.0709 | 0.0 |

(first 20 of 432 contexts shown; full per-context table in the companion JSON report.)

## Reproduce

From `backend/`:

    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py --save diag.json --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_fullcorpus_diagnostic.py --compare diag.json --report diag-report.json --write-markdown ../docs/reports/real-plan-priors/adjacency-fullcorpus-diagnostic.md
