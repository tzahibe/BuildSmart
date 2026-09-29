# Real-plan adjacency priors — full-corpus validation (Issue #149-B)

**Measurement only.** Re-measures Issue #141's Step-1 adjacency prior on the full ResPlan corpus with an honest train/holdout split, and keeps SPATIAL ADJACENCY and ACCESS strictly separate. No ranking, generator, validator or hard constraint is changed by this report.

## Corpus scan (AC-1)

Source: `/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl`. **17107 plans scanned** from the pickle (exact count, never a sample — see module docstring); skipped: {}; **17107 plans used**.

## Train/holdout split (AC-2)

Deterministic 80/20 split by `sha256(plan_id)` mod 100 (`< 20` -> HOLDOUT, else TRAIN) — independent of pickle/list order, reproducible from each plan's own id alone.

- TRAIN: **13648** plans — the prior below is built from TRAIN ONLY.
- HOLDOUT: **3459** plans — the calibration below is measured on HOLDOUT ONLY, scored against the TRAIN-built prior. No in-sample calibration anywhere in this report.

## Role vocabulary, honestly bounded by the data

ResPlan's own graph node types for indoor rooms are **LIVING, KITCHEN, BEDROOM, BATHROOM, BALCONY only** (verified by a full scan of all 17107 plans' own graph nodes — no other type ever appears as a graph node). `MASTER`, `ENSUITE`, `DINING`, `CIRCULATION` and `TOILET`/`WC` are **not distinct roles in this corpus** and are never inferred (e.g. "largest bedroom = master") — every headline pair below needing one of these roles is marked **UNMEASURABLE**, not fabricated.

## A. Spatial adjacency — TRAIN-built prior (AC-3)

Built ONLY from `adjacency`-typed edges (rooms that share a boundary). Smoothing: `laplace` (add-`1.0`). Minimum support: `3` plans. Baseline adjacency rate (pooled across every TRAIN (plan, role-pair) observation): `0.223059`. `lift = p_smoothed / baseline_rate`.

### Headline pairs (AC-3)

| role_a | role_b | sample_count | adjacent_count | raw_p | p_smoothed | lift | note |
|---|---|---|---|---|---|---|---|
| BEDROOM | LIVING | 13648 | 13601 | 0.996556 | 0.996484 | 4.467354 | meets min support |
| BEDROOM | CIRCULATION | — | — | — | — | — | **UNMEASURABLE** — CIRCULATION is not a distinct role in ResPlan's own node vocabulary |
| MASTER | ENSUITE | — | — | — | — | — | **UNMEASURABLE** — MASTER/ENSUITE is not a distinct role in ResPlan's own node vocabulary |
| MASTER | BATHROOM | — | — | — | — | — | **UNMEASURABLE** — MASTER is not a distinct role in ResPlan's own node vocabulary |
| KITCHEN | LIVING | 13576 | 13544 | 0.997643 | 0.99757 | 4.472223 | meets min support |
| KITCHEN | DINING | — | — | — | — | — | **UNMEASURABLE** — DINING is not a distinct role in ResPlan's own node vocabulary |
| BATHROOM | BEDROOM | 13648 | 0 | 0.0 | 7.3e-05 | 0.000328 | meets min support |
| BATHROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.00033 | meets min support |
| BATHROOM | LIVING | 13648 | 0 | 0.0 | 7.3e-05 | 0.000328 | meets min support |
| BALCONY | BATHROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000447 | meets min support |

### Every measured spatial-adjacency row

| role_a | role_b | sample_count | adjacent_count | raw_p | p_smoothed | lift | support |
|---|---|---|---|---|---|---|---|
| KITCHEN | LIVING | 13576 | 13544 | 0.997643 | 0.99757 | 4.472223 | yes |
| BEDROOM | LIVING | 13648 | 13601 | 0.996556 | 0.996484 | 4.467354 | yes |
| BALCONY | KITCHEN | 9959 | 0 | 0.0 | 0.0001 | 0.00045 | yes |
| BALCONY | BATHROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000447 | yes |
| BALCONY | BEDROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000447 | yes |
| BALCONY | LIVING | 10021 | 0 | 0.0 | 0.0001 | 0.000447 | yes |
| BATHROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.00033 | yes |
| BEDROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.00033 | yes |
| BATHROOM | BEDROOM | 13648 | 0 | 0.0 | 7.3e-05 | 0.000328 | yes |
| BATHROOM | LIVING | 13648 | 0 | 0.0 | 7.3e-05 | 0.000328 | yes |

**Key finding (AC-4)**: BATHROOM's spatial-adjacency rate to BEDROOM/KITCHEN/LIVING is essentially zero in section A (`raw_p≈0.0`) while its ACCESS rate to the same roles in section B is high (`0.91`/`0.87` to BEDROOM/LIVING) — because ResPlan labels a boundary-sharing pair EITHER `adjacency` OR `via_door`, never both: a bathroom's shared wall almost always carries a door, so it is recorded as `via_door`, not `adjacency`. Reading section A alone would wrongly conclude bathrooms rarely sit next to a bedroom; conflating A and B would wrongly conclude "touches" and "entered from" are the same fact. Neither artifact infers the other's number — this is exactly why AC-4 requires them kept apart.

## B. Access graph — TRAIN-built, from via_door/direct edges only (AC-4)

**ADJACENCY IS NOT ACCESS.** This section is built ONLY from `via_door`/`direct`-typed edges — never inferred from section A. `via_door` = a door bridges two rooms; `direct` = the front door opens directly into a room. This is the corpus's own undirected "bridged by a door" fact, not a directional entry sequence — ResPlan does not encode entry order, so none is invented here. `via_window` edges (a rare, distinct relation) are excluded from BOTH artifacts, not folded into either.

Baseline access rate (pooled across every TRAIN (plan, role-pair) observation): `0.30529`.

### Headline pairs — access, for direct comparison against A (AC-4)

| role_a | role_b | sample_count | access_count | raw_p | p_smoothed | lift | note |
|---|---|---|---|---|---|---|---|
| BEDROOM | LIVING | 13648 | 0 | 0.0 | 7.3e-05 | 0.00024 | meets min support |
| BEDROOM | CIRCULATION | — | — | — | — | — | **UNMEASURABLE** — CIRCULATION is not a distinct role in ResPlan's own node vocabulary |
| MASTER | ENSUITE | — | — | — | — | — | **UNMEASURABLE** — MASTER/ENSUITE is not a distinct role in ResPlan's own node vocabulary |
| MASTER | BATHROOM | — | — | — | — | — | **UNMEASURABLE** — MASTER is not a distinct role in ResPlan's own node vocabulary |
| KITCHEN | LIVING | 13576 | 0 | 0.0 | 7.4e-05 | 0.000241 | meets min support |
| KITCHEN | DINING | — | — | — | — | — | **UNMEASURABLE** — DINING is not a distinct role in ResPlan's own node vocabulary |
| BATHROOM | BEDROOM | 13648 | 12435 | 0.911123 | 0.911062 | 2.984252 | meets min support |
| BATHROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.000241 | meets min support |
| BATHROOM | LIVING | 13648 | 11817 | 0.865841 | 0.865788 | 2.835951 | meets min support |
| BALCONY | BATHROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000327 | meets min support |

### Every measured access row

| role_a | role_b | sample_count | access_count | raw_p | p_smoothed | lift | support |
|---|---|---|---|---|---|---|---|
| BATHROOM | BEDROOM | 13648 | 12435 | 0.911123 | 0.911062 | 2.984252 | yes |
| BATHROOM | LIVING | 13648 | 11817 | 0.865841 | 0.865788 | 2.835951 | yes |
| BALCONY | BEDROOM | 10021 | 7554 | 0.753817 | 0.753766 | 2.469017 | yes |
| BALCONY | LIVING | 10021 | 5346 | 0.53348 | 0.533473 | 1.74743 | yes |
| BALCONY | KITCHEN | 9959 | 0 | 0.0 | 0.0001 | 0.000329 | yes |
| BALCONY | BATHROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000327 | yes |
| BATHROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.000241 | yes |
| BEDROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.000241 | yes |
| KITCHEN | LIVING | 13576 | 0 | 0.0 | 7.4e-05 | 0.000241 | yes |
| BEDROOM | LIVING | 13648 | 0 | 0.0 | 7.3e-05 | 0.00024 | yes |

### Front-door direct access, by role (supplementary access fact)

P(role has a `direct` edge to the front door | role present), TRAIN only.

| role | sample_count | direct_count | rate |
|---|---|---|---|
| BALCONY | 10019 | 0 | 0.0 |
| BATHROOM | 13645 | 0 | 0.0 |
| BEDROOM | 13645 | 0 | 0.0 |
| KITCHEN | 13576 | 0 | 0.0 |
| LIVING | 13645 | 13530 | 0.991572 |

## C. Spatial touching — TRAIN-built, UNION of adjacency and via_door edges (repair for SPEC_MISMATCH)

**This is the table our own `y` is comparable to — see module docstring 'WHICH TABLE OUR OWN Y IS COMPARABLE TO, AND WHY'.** `app.vertical_slice.adjacency_priors._rects_adjacent` — the candidate's own `y` this Issue's diagnostic scores — is a PURE GEOMETRIC shared-boundary test, `True` whenever two rooms' walls touch regardless of whether a door pierces that wall. Section A's `adjacency`-only table undercounts true touching wherever a shared wall usually carries a door (ResPlan records that as `via_door`, never both) — measured on a 3,000-plan sample: BEDROOM-BATHROOM **0.000** under adjacency-only vs **0.955** under adjacency-OR-door, while BEDROOM-LIVING (**0.998**) and KITCHEN-LIVING (**0.999**), pairs rarely door-separated, are unchanged either way. Section A and section B are kept EXACTLY as originally reported above — neither table's own rows or baseline change; this section is additive.

Built ONLY from the per-plan UNION of `adjacency`-typed pairs and `via_door`-typed pairs (never `direct`, which bridges the front door to a room, not two rooms to each other). Same smoothing/min-support/TRAIN split as sections A/B. Baseline spatial-touching rate (pooled across every TRAIN (plan, role-pair) observation): `0.52835`.

### Headline pairs — spatial touching, for direct comparison against A and B

| role_a | role_b | sample_count | touching_count | raw_p | p_smoothed | lift | note |
|---|---|---|---|---|---|---|---|
| BEDROOM | LIVING | 13648 | 13601 | 0.996556 | 0.996484 | 1.886029 | meets min support |
| BEDROOM | CIRCULATION | — | — | — | — | — | **UNMEASURABLE** — CIRCULATION is not a distinct role in ResPlan's own node vocabulary |
| MASTER | ENSUITE | — | — | — | — | — | **UNMEASURABLE** — MASTER/ENSUITE is not a distinct role in ResPlan's own node vocabulary |
| MASTER | BATHROOM | — | — | — | — | — | **UNMEASURABLE** — MASTER is not a distinct role in ResPlan's own node vocabulary |
| KITCHEN | LIVING | 13576 | 13544 | 0.997643 | 0.99757 | 1.888085 | meets min support |
| KITCHEN | DINING | — | — | — | — | — | **UNMEASURABLE** — DINING is not a distinct role in ResPlan's own node vocabulary |
| BATHROOM | BEDROOM | 13648 | 12435 | 0.911123 | 0.911062 | 1.724354 | meets min support |
| BATHROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.000139 | meets min support |
| BATHROOM | LIVING | 13648 | 11817 | 0.865841 | 0.865788 | 1.638663 | meets min support |
| BALCONY | BATHROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000189 | meets min support |

### Every measured spatial-touching row

| role_a | role_b | sample_count | touching_count | raw_p | p_smoothed | lift | support |
|---|---|---|---|---|---|---|---|
| KITCHEN | LIVING | 13576 | 13544 | 0.997643 | 0.99757 | 1.888085 | yes |
| BEDROOM | LIVING | 13648 | 13601 | 0.996556 | 0.996484 | 1.886029 | yes |
| BATHROOM | BEDROOM | 13648 | 12435 | 0.911123 | 0.911062 | 1.724354 | yes |
| BATHROOM | LIVING | 13648 | 11817 | 0.865841 | 0.865788 | 1.638663 | yes |
| BALCONY | BEDROOM | 10021 | 7554 | 0.753817 | 0.753766 | 1.426642 | yes |
| BALCONY | LIVING | 10021 | 5346 | 0.53348 | 0.533473 | 1.009696 | yes |
| BALCONY | KITCHEN | 9959 | 0 | 0.0 | 0.0001 | 0.00019 | yes |
| BALCONY | BATHROOM | 10021 | 0 | 0.0 | 0.0001 | 0.000189 | yes |
| BATHROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.000139 | yes |
| BEDROOM | KITCHEN | 13576 | 0 | 0.0 | 7.4e-05 | 0.000139 | yes |

## Holdout calibration — section A, adjacency-only (AC-2, AC-6)

Every HOLDOUT plan's own spatial-adjacency pattern scored against the TRAIN-built prior (section A) via `plan_log_likelihood` — the identical Step-2 scoring function, never re-derived. Scorable: **3459/3459** HOLDOUT plans (the rest have zero eligible pair with a supported TRAIN row).

- `real_median_score` (HOLDOUT): **-0.000665**
- `real_stdev_score` (HOLDOUT, population stdev): **0.058796**
- threshold (`median - stdev`): **-0.059461**

This calibration replaces #141's in-sample one (`real_median_score=-0.3253`, `real_stdev_score=0.1455`, measured on the same 19 plans the prior itself was built from).

## Holdout calibration — section C, spatial touching / UNION (AC-2, AC-6)

Every HOLDOUT plan's own spatial-touching pattern (its own UNION of adjacency and via_door pairs) scored against the TRAIN-built section-C prior via the SAME `plan_log_likelihood` — the calibration the diagnostic re-run below actually uses, since section C is the table our own `y` is comparable to. Scorable: **3459/3459** HOLDOUT plans.

- `real_median_score` (HOLDOUT, touching): **-0.128868**
- `real_stdev_score` (HOLDOUT, touching, population stdev): **0.137503**
- threshold (`median - stdev`): **-0.26637**

See `docs/reports/real-plan-priors/adjacency-fullcorpus-diagnostic.md` for the 404-context diagnostic re-run against BOTH calibrations side by side.

## Regenerate

From `backend/`:

    uv run python -m app.knowledge.adjacency_priors_fullcorpus --write-json ../docs/reports/real-plan-priors/adjacency-fullcorpus.json --write-report ../docs/reports/real-plan-priors/adjacency-fullcorpus.md

The scanner **fails loudly** (raises `EmptyFullCorpusError`, CLI exits non-zero) on a missing/empty pickle or zero usable plans — proven by `tests/knowledge/test_adjacency_priors_fullcorpus.py`.
