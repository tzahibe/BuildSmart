# Real-plan adjacency priors — measured artifact

Issue #141, Step 1: a measured `P(adjacent | both roles present)` per unordered pair of room roles, used later ONLY as a soft ranking preference behind `ADJACENCY_PRIORS_ENABLED` — never a gate, never a validator, never a hard constraint.

## Data source

`tests/spikes/fixtures/geometry_shapes/plans` — **19 real plan(s) scanned** (1 synthetic control plan(s) excluded).

The full ResPlan corpus (17,107 real plans) lives only on the unmerged branch `integration/poc-architectural-brain`, not reachable from this worktree — the same constraint Issue #140's `room_proportion_priors.py` documented. This report measures the one real, licensed, reproducible sample committed on this branch: the 19-plan fixture at `tests/spikes/fixtures/geometry_shapes/plans/` (CC BY 4.0).

## Method

For every scanned plan, rooms are grouped by `type` (role). Roles the engine's own programme models as ONE room per house — LIVING, KITCHEN, DINING, CIRCULATION, FAMILY_ROOM — are reduced to their single LARGEST-area instance per plan first (same rationale, same role set, as `room_proportion_priors`'s own reduction: ResPlan sometimes labels a small entrance nook or stair sliver with the same role as the real room, and an unreduced sliver touches almost everything). Every other role keeps every instance.

Adjacency is read directly from ResPlan's own precomputed `adjacency_edges` field — this scanner does not re-derive touching from room polygons. For each unordered pair of distinct roles both present in a plan, the pair counts as adjacent in that plan if ANY room-id of the first role touches ANY room-id of the second.

**Smoothing**: `laplace` (add-`1.0`) over the raw `adjacent_count / sample_count` rate — `p_adjacent = (adjacent_count + α) / (sample_count + 2α)` — so a pair observed at 0% or 100% on a thin sample never produces `log(0)`/`log(1)` when Step 2's score consumes it.

**Minimum support**: `3` plans. A pair below this is still reported below (flagged, never hidden) but contributes NOTHING to Step 2's score — neither to the sum nor to the eligible-pair count.

**Baseline adjacency rate**: `0.703448` — pooled across every (plan, role-pair) observation in the corpus. `lift = p_adjacent / baseline_adjacency_rate` per row.

## Measured rows

20 unordered role-pair row(s) observed in at least one scanned plan.

| role_a | role_b | sample_count | adjacent_count | raw_p_adjacent | p_adjacent | lift | meets_min_support |
|---|---|---|---|---|---|---|---|
| BEDROOM | LIVING | 16 | 16 | 1.0 | 0.944444 | 1.342593 | True |
| KITCHEN | LIVING | 16 | 16 | 1.0 | 0.944444 | 1.342593 | True |
| BATHROOM | BEDROOM | 15 | 15 | 1.0 | 0.941176 | 1.337947 | True |
| BATHROOM | LIVING | 16 | 15 | 0.9375 | 0.888889 | 1.263617 | True |
| BATHROOM | CIRCULATION | 3 | 3 | 1.0 | 0.8 | 1.137255 | True |
| BEDROOM | CIRCULATION | 3 | 3 | 1.0 | 0.8 | 1.137255 | True |
| BEDROOM | STORAGE | 2 | 2 | 1.0 | 0.75 | 1.066177 | False ⚠ below min support |
| LIVING | STORAGE | 2 | 2 | 1.0 | 0.75 | 1.066177 | False ⚠ below min support |
| LIVING | TOILET | 6 | 5 | 0.833333 | 0.75 | 1.066177 | True |
| BEDROOM | TOILET | 5 | 4 | 0.8 | 0.714286 | 1.015407 | True |
| CIRCULATION | LIVING | 4 | 3 | 0.75 | 0.666667 | 0.947713 | True |
| BATHROOM | STORAGE | 2 | 1 | 0.5 | 0.5 | 0.710785 | False ⚠ below min support |
| BATHROOM | TOILET | 7 | 3 | 0.428571 | 0.444444 | 0.631809 | True |
| KITCHEN | TOILET | 7 | 3 | 0.428571 | 0.444444 | 0.631809 | True |
| CIRCULATION | TOILET | 3 | 1 | 0.333333 | 0.4 | 0.568628 | True |
| BEDROOM | KITCHEN | 15 | 5 | 0.333333 | 0.352941 | 0.50173 | True |
| STORAGE | TOILET | 1 | 0 | 0.0 | 0.333333 | 0.473856 | False ⚠ below min support |
| BATHROOM | KITCHEN | 15 | 4 | 0.266667 | 0.294118 | 0.418109 | True |
| CIRCULATION | KITCHEN | 5 | 1 | 0.2 | 0.285714 | 0.406163 | True |
| KITCHEN | STORAGE | 2 | 0 | 0.0 | 0.25 | 0.355392 | False ⚠ below min support |

⚠ = below minimum support — reported, never hidden. On a 19-plan corpus most pairs sit near this floor; this is the honest state of the reachable sample.

Regenerate with (from `backend/`):

    uv run python -m app.knowledge.adjacency_priors --write-json ../docs/reports/real-plan-priors/adjacency.json --write-report ../docs/reports/real-plan-priors/adjacency.md

The scanner **fails loudly** (raises `EmptyCorpusError`, CLI exits non-zero) on zero plans scanned or an empty measurement — proven by `tests/knowledge/test_adjacency_priors.py`.
