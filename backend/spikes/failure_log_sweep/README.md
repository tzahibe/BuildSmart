# Failure-log sweep

The production refusal log (`app/data/failures.json`) de-duplicates to **418 distinct request
contexts** (plot, footprint, bedrooms, wet rooms, safe room, open plan, target area). Every planner
change in features 004 and 005 was measured against them, through the real service entry point
(`app.demo.service.generate_demo_design`), not through the concept stage alone — roughly a quarter of
outlines that pass the concept stage still fail downstream, so the concept stage is not the baseline.

Run everything from `backend/` with the project venv.

## `sweep.py`

`project_from_context(ctx)` turns a log context into a `Project`; `distinct_contexts()` yields the
418. Library for the two scripts below.

## `ab.py --toggle {twins,hub}`

Runs all 418 scenarios twice — with the named mechanism disabled, then as shipped — and reports:

- plans OFF / ON, and how many pre-existing **primary designs are byte-identical** (full room
  signature: every room's type, x, y, width, depth). This is the non-regression gate; the
  alternatives list is reported separately because it may legitimately change.
- LOST (must be 0), GAINED with requested area, delivered area, per-cent and validators; only rows
  at **≥ 80 % of the requested area** count as gains (a plan at half the asked size is a worse answer
  than an honest refusal — see the project memory).
- refusal-code table OFF vs ON.
- which strategy delivered each plan; for `hub`: how many plans selected the hub, how many had a hub
  candidate that another parti out-ranked, and hub rejections by reason.
- per-scenario latency: median OFF vs ON and the worst regression, split between scenarios that
  already planned (must stay ~flat) and the rest.
- `gained.json` next to this file, for `quality_metrics.py --contexts`.

## `outline_ab.py --before before.json` (feature 006)

Runs every context twice through `generate_demo_design`: **A** with the logged `selected_footprint`
(the advanced path) and **B** without one (the main flow — the engine chooses the outline). Prints
one line per success criterion of `specs/006-engine-chosen-outline/spec.md` §4: planned A/B; A
primaries byte-identical to the frozen `snapshot.py --save` file (SC-005) and LOST; main-flow
non-regression (briefs planned before that B does not plan, listed); first-plan gross ÷ requested
(SC-002); briefs with ≥ 2 distinct families shown (SC-003); shown plans failing validation (SC-004);
same-family + same-outline pairs (SC-006); refusals naming an outline and the capacity diagnosis
(SC-007); latency medians for briefs planned / refused before (SC-008). Writes `outline_ab.json`
(not committed — 1.6 MB, regenerable). `project_from_context(ctx, with_footprint=False)` is the
main-flow replay; `plans_shown(result)` lists what the screen shows.

## `quality_metrics.py [--contexts gained.json] [--split-by-strategy]`

The corpus driver and printed report for the Stage-0 architectural-quality metrics, measured on
delivered geometry: M1 room aspect (long/short) by room type · M2 habitable rooms touching the
envelope · M3 circulation share of room area · M4 doors on the hall and the hall's own long/short ·
M5 wet rooms sharing an interior wall with a wet room / kitchen / laundry · M6 living-dining-kitchen
joined by open interfaces. Reference values from 21 professional plans are in
`specs/005-hub-private-wing/spec.md` §1.

The computations themselves (Issue #17) live in `app.vertical_slice.quality_metrics` —
`measure_design` for one plan (also what feeds `QualityOut.metrics` on every delivered plan) and
`summarize` for the corpus-level report this script prints, unchanged. A committed baseline over
the frozen 432-context regression corpus and its no-regression test live in
`tests/regression_corpus/{quality_baseline.json,test_quality_baseline.py}`; see
`docs/wiki/architecture/geometry-validation.md` for the tolerances and the measured gaps against
the 21 professional plans.

## `hub_rooms.py [--hub-only]`

Every realized hub plan's rooms with their rectangles and aspects, plus medians by room type and —
since 008 — split by the hub's eligibility (`StrategyRecorder.chosen_rationale`).

## `hub_sizing_bound.py [W D ...]` · `hub_topology_bound.py [--wet 2|3] [--grid] [--only T1]`

The exact bounds behind v2.1 (sizing cannot fix the wide-shallow outlines) and v3 Phase 0
(per topology: door seats, wet adjacency, shape). Since 008 the T1 row runs through the engine's
`hub_bound`, so the tool and the eligibility decision share one model. RESULTS.md §6–§8.

## `BASELINE.md`

Frozen output of `ab.py --toggle twins` at commit `2e19d89`, the "before" every later phase is
compared against.

## `envelope.py` (feature 007, decision D)

The demo envelope as the engine actually meets it: a 216-cell grid — bedrooms 1–6 × wet rooms 1–3
× safe room × six log-typical footprints (11×12, 12.5×14.5, 12×18, 14×16, 18×12, 16×18 m; target
area = footprint area, open plan, no parking) — through `generate_demo_design`. Reports cells
planned per bedroom count and per wet-room bucket, the smallest of the six footprints that plans
each programme, every cell's result, and whether every plan passes C17 (must be 0 failures). Writes
`ENVELOPE.md` beside this file; the numbers in `app/demo/scope.py` are copied from there. ~8.5 min.
