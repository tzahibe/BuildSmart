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

## `quality_metrics.py [--contexts gained.json] [--split-by-strategy]`

The Stage-0 architectural-quality metrics, measured on delivered geometry:
M1 room aspect (long/short) by room type · M2 habitable rooms touching the envelope · M3 circulation
share of room area · M4 doors on the hall and the hall's own long/short · M5 wet rooms sharing an
interior wall with a wet room / kitchen / laundry · M6 living-dining-kitchen joined by open interfaces.
Reference values from 21 professional plans are in `specs/005-hub-private-wing/spec.md` §1.

## `BASELINE.md`

Frozen output of `ab.py --toggle twins` at commit `2e19d89`, the "before" every later phase is
compared against.
