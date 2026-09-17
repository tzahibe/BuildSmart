# L-Massing

Status: IMPLEMENTED_MERGED

## Current behavior

The engine's outline search carves two L massings from the buildable rectangle at the requested
area and surveys them beside its four rectangles, on **any rectangular plot** (not only an
L-shaped site — that was the prior, narrower behavior). An L-orientation tie is broken by
preference, then realized quality, then order.

**On top of that base capability**, a later quality gate (commit `9ae6893`) replaced the
unconditional "first valid L gets a representation slot" behavior with a realized-quality
eligibility gate: an engine-generated L must clear a realized-quality bar (worst wet-room aspect,
two-sided habitable share) to take its slot; an ineligible L lets the next-best rectangle occupy
it instead. No score/bonus is given merely for being an L. Entrance-door and entrance-sequence
selection are explicitly untouched by this gate (a separate, named follow-up).

There is also an original, narrower "first production L parti" (`l_parti.py`) that only fires on
an actual L-shaped *site* — distinct from, and superseded in scope (not correctness) by, the
rectangular-plot L-massing survey above for the common case.

## Authoritative implementation

- `app/vertical_slice/l_massing_guard.py` (the realized-quality eligibility gate).
- `app/vertical_slice/l_parti.py` (the original L-shaped-site parti).
- Base L-massing-on-rectangular-plot: branch `016-l-massing-outlines`, merge commit `5195368`.
- Quality gate: commit `9ae6893`.
- Tests: `tests/vertical_slice/test_l_parti.py`; `tests/test_demo_outline_selection.py`,
  `tests/test_outline_offer.py` (outline-survey/offer plumbing).

## Current constraints/invariants

- No score/bonus is given merely for being an L — only the realized-quality gate decides
  eligibility.
- Entrance-door/entrance-sequence selection logic is untouched by the quality gate.
- The L-massing survey never changes which rectangles are surveyed or the primary-selection rule.

## Supersedes

`docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md` (the investigation behind the
quality gate — same commit, `9ae6893`, companion doc).

## Known follow-ups

- Orientation-ordering refinements beyond the current preference → quality → order tiebreak are
  explicitly out of scope for the quality gate and remain a listed follow-up, not current
  behavior — do not present orientation-ordering changes as already landed.

## Evidence/history

`docs/BUILDING_SHAPE_MASSING_FAMILIES_REPORT.md` (the approved massing-family plan this
implements), `docs/L_PARTI_REPORT.md` (the original L-shaped-site parti), `docs/L_MASSING_OUTLINES_REPORT.md`
(the rectangular-plot generalization), `docs/L_MASSING_REPRESENTATION_QUALITY_GATE_IMPLEMENTATION.md`
and its investigation companion (why the quality gate was needed), `docs/MASSING_REPRESENTATION_REPORT.md`
(the display-layer fix these outlines needed to render correctly).

## Last verified against git

`1d648c3` (main HEAD). `5195368` and `9ae6893` both confirmed on `main` via `git log --oneline main`.
