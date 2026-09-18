# Seam-Shape Selection Investigation — fix D, measured

**Date**: 2026-09-16 · **State measured**: working tree as found (see §0.1 — an uncommitted,
in-progress change already sits on `concept_generator.py`; not modified by this investigation).
**Scope**: investigation only, no implementation, no fix applied. **Follows**:
`WET_ROOM_STRIP_INVESTIGATION_REPORT.md`, whose "fix D" (shape-aware, pairing-independent seam
re-selection with joint two-column acceptance) this report was asked to evaluate concretely: is it
reachable generically, and what does it buy corpus-wide.

**Method**: code trace of the seam search (`plan_layout`, `_seam_options`, `_columns_at_seam`,
`_quality_score`/`_quality_accepts`), then two runnable experiments (not committed, session
scratchpad): (1) the same hand-reconstructed repro arm the prior report used, swept across the
seam window; (2) a shadow sweep hooked onto `plan_layout`'s *normal* (`fallback=None`) calls, run
through the real pipeline (`generate_demo_design`) over a stride-12 sample of the 432-context
regression corpus (36 contexts), which realizes **every** seam in the existing 9-candidate window
per call instead of stopping at the first feasible one, and scores the result two ways: a
role-agnostic metric requiring no template change, and the tree's own already-shipped scoring
functions applied jointly across both columns.

---

## 0. Verdict up front

**Decision (2026-09-16): Fix D = REJECTED / NOT WORTH IMPLEMENTING.** Accepted as final — not
implemented, not queued as follow-up research. Reasons, each independently measured below: too few
plans ever have a second feasible seam (§3, 6%); the existing quality invariants correctly reject
the joint-column trade-off nearly every time it is available (§3, 0% under the tree's own
`_quality_accepts`); the repro itself does not materially improve under the real
`_distribute_column_surplus` logic (§2); and the added search/runtime complexity is not justified
by that measured benefit. This report is the evidence closing the path — no further action.

1. Two independent, real
   measurements (not a single hand-picked example) both show it barely reaches anything: **1/66**
   wet-room-strip occurrences improve under a bespoke generic metric, and **0/66** improve under
   the codebase's own already-shipped acceptance rule (`_quality_accepts`) applied jointly across
   columns. The mechanism is buildable — I built and ran it — but not worth building.
2. **Important state discovery, not caused by this investigation**: `backend/app/vertical_slice/
   concept_generator.py` already carries an **uncommitted** working-tree change that implements
   the earlier report's **fix A** — `preferred_aspect_ratio` on `BATHROOM` (2.0) and `TOILET`
   (2.5), plus a PRIVATE-before-SERVICE lexicographic tier in `_quality_score`/`_quality_accepts`
   that resolves the host-slot-contention risk that report flagged. This looks like another
   session's in-progress work (per the standing rule not to mutate git in the main checkout, I did
   not touch it, commit it, or revert it — flagging it here because it changes fix D's baseline and
   the user should know it's sitting there uncommitted). All measurements below were run against
   the tree **as found**, i.e. *with* this change present.
3. **The seam window and the data fix D needs already exist; nothing new had to be built to test
   it.** `_seam_options` already yields up to 9 candidate widths, and `_columns_at_seam` already
   fully realizes BOTH columns' rows and depths at any candidate width. The only thing stopping
   joint shape-scoring today is that `plan_layout`'s loop **returns at the first feasible seam** —
   it was never evaluating the other 8 in the first place. Removing that early return and scoring
   what's already computed is real, but small, code — I replicated it in a ~150-line
   instrumentation script with zero changes to the engine.
4. **Why it barely helps — two separate, both measured, reasons**:
   - **Reason 1 — most arms have no alternative to choose between.** Of 66 real `plan_layout`
     attempts that left a lone wet room past aspect 1.6, only **4** (6%) had more than one
     *feasible* width anywhere in the 9-candidate window. The other 94% are seam-locked: narrower
     blows the column's own row floors, wider starves the opposite column. The seam search window
     is mostly a formality for these arms, not a real menu.
   - **Reason 2 — even where an alternative exists, the elasticity-driven surplus distribution
     fights it, and the existing no-regression rule (correctly) blocks it.** Traced directly on the
     repro (§2 below): narrowing the arm 4.85→4.20 m improves the BEDROOM (elasticity 0.5) from
     1.73→1.35 while the BATHROOM (elasticity 0.15) barely moves, 2.20→2.21 — the column's spare
     depth is redistributed toward the more elastic room, not the strip. And structurally, a seam
     move re-sizes **every row in both columns at once**, unlike row-pairing (fix A's mechanism),
     which touches exactly two rooms and leaves everything else provably alone — so a seam move
     collides with `_quality_accepts`'s strict "no PRIVATE room may get worse, ever" rule far more
     often. That rule is correct and already shipped; the measurement here shows *seam* re-selection
     is a much blunter instrument for satisfying it than *pairing* is.
5. **Runtime is not the blocker.** Realizing all ≤9 seams instead of one, on every successful
   normal `plan_layout` call across the sample (9,243 calls, all strategies/outlines the generator
   tries internally) cost 3.97 s against 127.5 s of real planner time — about 3% overall, ungated.
   Gated the way the existing row-pairing quality tier already is (only on calls that show a
   defect) it would cost a small fraction of that. If this direction is ever revisited, cost is not
   the reason not to.

---

## 1. What already exists vs. what fix D would need

Traced in `app/vertical_slice/concept_generator.py`:

- **Candidate seam window**: `_seam_options(natural_m, lo_m, hi_m, limit=9)` — the area-share
  ("natural") width first, then outward in 0.25 m steps, snapped to a 0.05 m grid, bounded by each
  column's own minimum width. Unchanged by fallback/quality mode in the *normal* path; tier 2
  (`fallback` given, not quality) walks the full window (`limit=None`) but for feasibility, not
  shape — see next point.
- **How many seams are actually considered today**: `plan_layout`'s loop
  (`for seam_w in seams: ... if plans is not None: break`) stops at the **first** seam that plans
  successfully for **both** columns. For every one of the 66 sampled wet-strip occurrences, this
  first-feasible seam was confirmed (by direct comparison) to be the same seam the real pipeline
  delivered — so in practice, one seam is realized, not nine, for the plans this investigation
  looked at.
- **Data available after row planning**: `_columns_at_seam` returns a `ColumnPlan` (width, rows,
  chosen depths) for **each** column at the seam it was called with — already fully realized, from
  which `_row_shapes` gives every room's net (width, depth) directly. Nothing new needs to be
  computed for scoring; it only needs to not be thrown away after the first success.
- **Whether Pareto/lexicographic comparison is sufficient**: yes, mechanically — the existing
  `_quality_score`/`_quality_accepts` tuple-lexicographic scheme (now 5 terms: PRIVATE worst
  shortfall, PRIVATE count-over, SERVICE worst shortfall, SERVICE count-over, mean) works exactly
  the same way whether its input aspects come from one column's row-pairing candidates or from two
  columns' seam candidates — it does not care where the `{zone: aspect}` dict came from. The
  question was never "can a lexicographic comparison work here" (it can, trivially); it's "does a
  seam move ever produce an aspect dict this rule accepts" — measured in §3, rarely.

## 2. Repro, swept across the window (as asked — not patched)

Same reconstruction the prior report used (SAFE_ROOM 10.9 m², BEDROOM 12.8 m², BATHROOM 8.1 m²,
7.90 m column depth), run through the real `_row_depths`/`_row_shapes` at each width in the
window (values differ slightly from the prior report's own reconstruction, which flagged the same
imprecision — read off a drawing, not a saved fixture):

| net width | SAFE_ROOM | BEDROOM | BATHROOM | generic worst-fraction* |
|---|---|---|---|---|
| 4.85 m | 4.85×2.60 (1.87) | 4.85×2.80 (1.73) | 4.85×2.20 (**2.20**) | 0.746 |
| 4.60 m | 4.60×2.60 (1.77) | 4.60×2.95 (1.56) | 4.60×2.05 (**2.24**) | 0.748 |
| 4.40 m | 4.40×2.60 (1.69) | 4.40×3.10 (1.42) | 4.40×1.90 (**2.32**) | 0.772 |
| 4.20 m | 4.20×2.60 (1.62) | 4.20×3.10 (1.35) | 4.20×1.90 (**2.21**) | 0.737 |
| 4.00 m | — | — | — | **refused**: floors alone need 7.95 m against 7.90 m available |

\* max over all three rooms of `aspect / template.max_aspect_ratio` — a role-agnostic metric
using a field every `RoomTemplate` already has, needing no new calibration.

**The bathroom does not meaningfully improve across the whole legal window** (2.20 → 2.21, worse
if anything) even though the bedroom clearly does (1.73 → 1.35). This directly contradicts the
prior report's own illustrative table (which showed the bathroom improving 2.62→2.10) — that
example did not carry through `_distribute_column_surplus`'s elasticity-weighted surplus step
faithfully; doing so here, the low-elasticity wet room (0.15) simply does not receive the freed
depth a narrower seam creates, because the more elastic bedroom (0.5) absorbs it first. **This one
example was not representative, and the corpus measurement below confirms it.**

## 3. Corpus-wide measurement

Sample: every 12th of the 432 regression-corpus contexts (36 contexts), run through the real
`generate_demo_design` pipeline with `plan_layout` instrumented to additionally realize (not
select — realize, for measurement only) every seam in the existing window on every successful
normal call.

| metric | value |
|---|---|
| contexts sampled / pipeline completed | 36 / 21 (15 raised — scope refusals or no plannable proportion; expected) |
| normal `plan_layout` calls realized (all strategies/outlines the generator tries) | 9,243 |
| shadow seam realizations performed | 64,638 (7.0 per call average) |
| added wall time | 3.97 s of 127.5 s real planner time (≈3%), ungated |
| calls with ≥1 lone wet room past aspect 1.6 | 66 |
| … of those, >1 seam in the window was even feasible | **4 (6%)** |
| … seam-fixable under a role-agnostic metric (≥0.1 gain, no PRIVATE-class regression) | **1 (1.5%)** |
| … seam-fixable under the tree's own `_quality_accepts`, applied jointly across columns, unchanged | **0 (0%)** |
| candidates that scored better but were correctly rejected for a PRIVATE-room regression | 0 (out of the 4 with an alternative at all) |

The one role-agnostic "win" found: a 0.19 aspect gain on the strip room, from a 0.25 m seam move —
in line with the repro's own scale, and still rejected once the tree's stricter, already-shipped
acceptance rule (§1) is used instead of a bespoke one.

**Caveat on scope**: these are plan-*attempt* counts (every strategy/outline `generate_concepts`
tries internally), not distinct delivered primaries — consistent with wanting a mechanism-level
answer ("when the normal seam search hits a wet-room strip, is there anything better to pick"),
but not a headcount of affected user-visible plans. The `matches_real` check (the shadow sweep's
first-feasible seam always equalled the real pipeline's chosen seam, 66/66) confirms the
instrumentation faithfully reproduces the real planner rather than diverging from it. One
methodological note: a second run of the same 36-context sample produced a different
pipeline-completion split (21/15 vs. an earlier 32/4) under the added per-call instrumentation
overhead — plausibly wall-clock-sensitive behavior somewhere downstream (solver iteration/timeout
paths were not traced) — the wet-strip and seam-fixability *rates* were consistent across both
runs; the absolute completion count was not, and should not be read as a stable pipeline yield
figure from this script.

## 4. Interactions asked about

- **Bedroom quality tier (fix A, now already present)**: no double-counting observed in this
  sample — but only because so few seam alternatives existed at all (§3), not because the
  interaction is proven safe. If reach were larger, a seam-quality pass and the row-pairing quality
  pass would both search from the same base plan inside the same `plan_layout` call graph
  (`_quality_layouts` re-invokes `plan_layout` with `fallback=quality` over the identical seam
  window) — ordering the two (which runs first, and whether a seam-quality candidate should even be
  offered once row-pairing has already fixed the worse room) is unresolved and untested here.
- **L arms**: not separately measured. Each wing of the 016 L-massing path plans through the same
  `plan_layout`/`_columns_at_seam` machinery per the code read, so the mechanism should generalize
  mechanically, but this investigation did not run the two-wing path (`_two_wing_pair`) specifically.
- **Risk to existing primaries**: zero by construction in every experiment run here — this was only
  ever tested as an *additional* candidate alongside the untouched first-feasible base plan (the
  same non-destructive pattern `be8c0ca`'s row-pairing tier already uses), never as a replacement.
  No LOST cases are possible under that pattern; none were observed.

## 5. Recommendation

**REJECTED / NOT WORTH IMPLEMENTING — decision accepted, closed.** The earlier report's stated reason
for NEEDS_RESEARCH ("no existing acceptance mechanism spans two columns") is retired — one was
built here in an afternoon, reusing the tree's own already-shipped scoring unchanged. The real
reason to hold off is what got measured once it existed: **seam re-selection reaches at most ~1.5%
of wet-room strips under a favorable bespoke metric, and 0% under the codebase's own stricter,
correct acceptance rule**, because (a) most strip-carrying arms have no second feasible seam to
offer at all, and (b) a seam move resizes every row in both columns simultaneously, which the
existing "never let a PRIVATE room get worse" invariant — correctly — almost always refuses, in a
way that row-pairing's surgical, two-room swap does not.

If this area is revisited, the more promising, smaller lever the two experiments here point at
directly is **`_distribute_column_surplus`'s elasticity weighting**: BATHROOM (0.15) and TOILET
(0.10) receive almost none of a column's freed depth even when a narrower seam is otherwise
legal, while BEDROOM (0.5) absorbs most of it — giving a wet room more expansion priority *when it
is the worst room in its column* would act locally (inside `_row_depths`, no new search axis, no
new candidate tier) rather than re-fighting the whole seam question. That is new, separate research
and outside what was asked here — not evaluated, not recommended as ready, just the more promising
thread this investigation surfaces on the way out.

No production code was changed. No fix was applied to any plan.
