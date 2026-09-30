# Real-plan room-proportion priors — measured artifact

Issue #140, Step 1: a measured distribution of how real ResPlan plans size rooms, used later ONLY as a soft ranking preference behind `ROOM_PROPORTION_PRIORS_ENABLED` — never a hard constraint, never a change to `ROOM_TEMPLATES`.

## Data source

`tests/spikes/fixtures/geometry_shapes/plans` — **19 real plan(s) scanned** (1 synthetic control plan(s) excluded).

The Issue names the full ResPlan corpus (17,107 real plans, ingested for the POC as `PlanReference`). That corpus, and the POC ingest code that produced it (`spikes/architectural_brain/`), live only on the unmerged branch `integration/poc-architectural-brain` — not reachable from this worktree, the same constraint Issue #102's `measure_real_plan_shapes.py` documented. The one real, licensed, reproducible sample committed on this branch is the 20-plan fixture at `tests/spikes/fixtures/geometry_shapes/plans/` (19 real ResPlan plans, CC BY 4.0, + 1 synthetic control this scan excludes). This report measures that 19-plan sample. A full-corpus remeasurement is the natural next step once an integration worktree makes `spikes/architectural_brain/corpus/` reachable — see `.agent/proposals/roadmap/102-1-full-corpus-remeasurement.md` for the exact precedent.

## Bucket definitions, justified from the data's own distribution

**House-size bucket**: the plan's own `derived.footprint_area_m2`, split into thirds at the 33rd/66th percentile of the plans actually scanned (recomputed every run — a larger corpus gets its own edges, never a value tuned for this 19-plan sample).
Measured edges on this scan: 142.1 m2 / 167.2 m2.

**Bedroom-count bucket**: the same tercile method over `derived.room_type_counts["BEDROOM"]`, except when the corpus has fewer than 3 distinct bedroom counts (true here: 16/19 plans are 3-bedroom) — in that case the split degenerates to a single point, so this scan falls back to three groups relative to the corpus's OWN median bedroom count instead: `LOW` (below it), `TYPICAL` (equal to it), `HIGH` (above it). Measured median on this scan: 3 bedroom(s).

## Measured rows

22 (role, house-size bucket, bedroom-count bucket) row(s) with at least one real sample. No row is fabricated for a combination the data never produced.

| role | house_size_bucket | bedroom_count_bucket | median_area_m2 | p25_area_m2 | p75_area_m2 | median_aspect | area_share_of_plan | sample_count |
|---|---|---|---|---|---|---|---|---|
| BATHROOM | LARGE(>167m2) | LOW(<=3bd) | 6.059 | 5.548 | 6.665 | 1.646 | 0.0311 | 14 |
| BATHROOM | MEDIUM(142-167m2) | LOW(<=3bd) | 5.433 | 5.293 | 6.319 | 1.715 | 0.0358 | 15 |
| BATHROOM | SMALL(<=142m2) | LOW(<=3bd) | 5.122 | 4.816 | 5.512 | 1.546 | 0.041 | 15 |
| BEDROOM | LARGE(>167m2) | LOW(<=3bd) | 22.831 | 22.548 | 25.389 | 1.143 | 0.1328 | 12 |
| BEDROOM | MEDIUM(142-167m2) | HIGH(>3bd) | 16.278 | 13.234 | 17.637 | 1.108 | 0.1095 | 4 |
| BEDROOM | MEDIUM(142-167m2) | LOW(<=3bd) | 21.581 | 18.395 | 24.654 | 1.257 | 0.1419 | 15 |
| BEDROOM | SMALL(<=142m2) | LOW(<=3bd) | 17.812 | 16.226 | 22.03 | 1.27 | 0.1377 | 21 |
| CIRCULATION | LARGE(>167m2) | LOW(<=3bd) | 28.446 | 17.515 | 39.67 | 1.087 | 0.141 | 3 |
| CIRCULATION | MEDIUM(142-167m2) | HIGH(>3bd) | 9.863 | 9.863 | 9.863 | 1.251 | 0.0664 | 1 ⚠ low-confidence |
| CIRCULATION | MEDIUM(142-167m2) | LOW(<=3bd) | 48.807 | 48.807 | 48.807 | 1.294 | 0.3261 | 1 ⚠ low-confidence |
| KITCHEN | LARGE(>167m2) | LOW(<=3bd) | 13.751 | 12.65 | 16.089 | 1.352 | 0.0742 | 6 |
| KITCHEN | MEDIUM(142-167m2) | HIGH(>3bd) | 9.241 | 9.241 | 9.241 | 1.235 | 0.0622 | 1 ⚠ low-confidence |
| KITCHEN | MEDIUM(142-167m2) | LOW(<=3bd) | 12.075 | 9.836 | 12.767 | 1.354 | 0.0763 | 5 |
| KITCHEN | SMALL(<=142m2) | LOW(<=3bd) | 11.853 | 10.299 | 13.965 | 1.182 | 0.0982 | 5 |
| LIVING | LARGE(>167m2) | LOW(<=3bd) | 70.849 | 64.957 | 72.822 | 1.397 | 0.3525 | 6 |
| LIVING | MEDIUM(142-167m2) | HIGH(>3bd) | 48.108 | 48.108 | 48.108 | 1.233 | 0.3236 | 1 ⚠ low-confidence |
| LIVING | MEDIUM(142-167m2) | LOW(<=3bd) | 52.947 | 49.947 | 55.994 | 1.205 | 0.3387 | 4 |
| LIVING | SMALL(<=142m2) | LOW(<=3bd) | 42.24 | 40.875 | 45.035 | 1.232 | 0.3498 | 7 |
| STORAGE | LARGE(>167m2) | LOW(<=3bd) | 4.128 | 3.535 | 4.72 | 1.12 | 0.0219 | 2 ⚠ low-confidence |
| TOILET | LARGE(>167m2) | LOW(<=3bd) | 3.02 | 2.421 | 3.647 | 1.397 | 0.0134 | 4 |
| TOILET | MEDIUM(142-167m2) | LOW(<=3bd) | 2.626 | 2.461 | 2.79 | 1.599 | 0.0167 | 2 ⚠ low-confidence |
| TOILET | SMALL(<=142m2) | LOW(<=3bd) | 3.663 | 3.482 | 3.736 | 1.468 | 0.0316 | 4 |

⚠ = below 3 samples — reported, never hidden. On a 19-plan corpus most rows sit near this floor; this is the honest state of the reachable sample, not a defect in the scanner (see 'Data source' above for the reachability gap this reflects).

## Method

`app.knowledge.room_proportion_priors.build_priors_table` reads every `*.json` file in the corpus directory as a `PlanReference` (tolerating either the bare schema or the `{"plan_reference": {...}}` wrapper used by the geometry-shapes fixture), excludes any plan whose `provenance.source_dataset` is `SYNTHETIC`, and for every remaining room with `area_m2`/`width_m`/`depth_m`/`type` computes `aspect = max(w,d)/min(w,d)` and `area_share = area_m2 / footprint_area_m2`. Rows aggregate by median/p25/p75 (`statistics.quantiles`, `method="inclusive"`).

Regenerate with (from `backend/`):

    uv run python -m app.knowledge.room_proportion_priors --write-json ../docs/reports/real-plan-priors/room-proportions.json --write-report ../docs/reports/real-plan-priors/room-proportions.md

The scanner **fails loudly** (raises `EmptyCorpusError`, CLI exits non-zero) on zero plans scanned or zero usable room samples extracted — proven by `tests/knowledge/test_room_proportion_priors.py`.
