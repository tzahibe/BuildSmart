# Massing Representation in the Shown Plans — implementation record

**Date**: 2026-09-16 · **Branch**: `013-massing-representation` (stacked on `012-l-parti`) · **Plan**: `BUILDING_SHAPE_MASSING_FAMILIES_REPORT.md` §3.3, the display half only

**What this is**: a guarantee that a valid plan of another **massing** (one wing vs two) is shown beside the plans that won on area — the L parti existed but could not surface. **What it is not**: a change to which plan is primary. The primary stays the area-nearest plan under the rule the demo has always used; nothing here scores exposure, circulation or shape, and no UI was added.

## The gap it closes

Measured on the five L sites × five programmes after branch `012`: a valid two-wing plan existed for 17 of the 25 briefs and reached the screen for **one** — as the primary, on the one brief where nothing one-wing planned. Two reasons, one per layer:

1. `general_pipeline._alternative_plans` walks candidates in the generator's order and stops after `ALTERNATIVE_ATTEMPT_LIMIT = 8` solves. The L ranks by area like every other candidate — behind the one-wing re-proportionings nearer the request — and past the cap. On the long-arm site the fifteen area-nearest L forced trees were also solver-infeasible (the forced-cut-versus-wall-inset gap) while every unforced twin solved, so even a longer walk in list order found nothing.
2. `demo/service._select_plans` de-duplicates the shown set by *organisation* family (`family_signature`), which is finer than a massing: three one-wing organisations fill the three slots before a two-wing plan is considered.

## What changed

| Where | What |
|---|---|
| `general_pipeline.massing_of` / `RealizedPlan.massing_signature` | `"1W"` for one rectangle, `"2W"` for two wings. Metadata for display, like `family_signature`; never an input to the primary. |
| `general_pipeline._alternative_plans` — **representation pass** | After the normal walk, for every massing present among the candidates but absent from `{chosen} ∪ found`, that massing's candidates are tried — forced trees **interleaved with their unforced twins** — for at most `MASSING_ATTEMPT_LIMIT = 4` solves; the first valid, distinct plan joins the alternatives, replacing the area-farthest one when the list is full, so the pool stays within `limit`. Gated on a second massing existing: a brief whose candidates are all one wing pays nothing. |
| `demo/service._select_plans` — **pass 0** | Before "organisation families not yet shown": a plan whose massing is not yet shown takes a slot first. Symmetric — a two-wing primary gets a one-wing alternative first. The primary rule is untouched. |

## Measured

Pipeline runs (`run_general_from_site`, `max_alternatives=3`), six sites × five programmes. "pool" = the massings of the primary and the alternatives, in order.

```
                                      primary (unchanged)      pool                 L alternative
E1 rear-arm   2BR open               SPINE_PUBLIC_PRIVATE 151.0   1W 2W               123.6
E1 rear-arm   3BR open               SPINE_DOUBLE_LOADED  181.2   1W                  (no valid L on this site)
E1 rear-arm   3BR closed             BRANCHED_TWO_STACK   198.4   1W 1W 1W 2W         150.7
E1 rear-arm   3BR noMMD open         SPINE_DOUBLE_LOADED  178.5   1W 1W 1W 2W         130.2
front-arm     (same four outcomes as E1; L alternatives 129.9 / 151.6 / 130.2)
west-arm      (mirrors E1 exactly)
long-arm      2BR open               BRANCHED_TWO_STACK   148.8   1W 1W 1W            (no valid L)
long-arm      3BR open               SPINE_DOUBLE_LOADED  181.9   1W 2W               143.1
long-arm      3BR closed             SPINE_DOUBLE_LOADED  198.1   1W 1W 1W 2W         159.0   ← found only with the twin interleave
long-arm      3BR noMMD open         SPINE_DOUBLE_LOADED  182.7   1W 1W 1W 2W         137.1
deep-primary  2BR open               SPINE_PUBLIC_PRIVATE 150.3   1W 1W 2W            147.0
deep-primary  3BR open               SPINE_DOUBLE_LOADED  170.5   1W 2W               141.5
deep-primary  3BR closed             SPINE_DOUBLE_LOADED  197.5   1W 2W               156.9
deep-primary  3BR noMMD open         SPINE_DOUBLE_LOADED  179.1   1W 1W 1W 2W         136.5
deep-primary  4BR open               MULTI_WING_SPLIT     165.5   2W                  (primary; no one-wing plan validates)
rectangle     all five               unchanged                    1W …                —
4BR open on the 5 m-arm sites: refused, as before.
```

- **Every brief that has a valid L now shows one**: 17 of 26 planned briefs (16 as an alternative, 1 as the primary), up from 1. The remaining 9 have no valid L (refusals named in the L report) or are the rectangle.
- **The primary is unchanged in every row.** The pool's first entry is what it was; the L is added, never promoted.
- **Runtime**: L sites 1.5–5.0 s against 1.1–4.4 s before (at most four extra solves, only where a second massing exists); the rectangle site is identical.
- The twin interleave mattered once (long-arm 3BR closed: first valid L at try 16 in list order, at try 2 interleaved).

## Tests

`test_demo_outline_selection.py` (+3, on stubs): another massing takes the first alternative slot before a second organisation; nothing changes when every plan is one wing; a two-wing primary gets a one-wing alternative first. `test_l_parti.py` (+3): a valid L reaches the alternatives on the deep-primary site with the one-wing primary unchanged and the pool within the limit; a one-wing site's alternatives are all `1W`; `massing_signature` counts the wings.

## Regression

- **Backend suite**: 1101 passed, 9 xfailed, 2 failed — the same two that fail on `main` @ `2a00c0f`, untouched.
- **432-context demo snapshot** against branch `012` (full `DemoPlanSet` payloads, primary + alternatives, 431 contexts in the worktree's log copy): **planned before = after = 404; 404/404 payloads byte-identical; 0 status changes; 0 missing.** As expected — the pass is gated on a second massing existing among the candidates, which the demo path (one rectangle) never has.
- Frontend unchanged on this branch.

## Not done here (by scope)

Anything that changes the primary — a grouped primary rule, quality metrics in ranking (exposure, circulation share, two-sided rooms), or the person's massing preference ordering candidates (shapes report §3.1). UI labels for the massing (`footprints` already carries the wings). Row sharing in wide arms.
