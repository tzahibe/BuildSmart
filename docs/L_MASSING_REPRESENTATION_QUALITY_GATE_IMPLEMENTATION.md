# L-Massing Representation Quality Gate — implementation record

**Date**: 2026-09-17 · **State**: uncommitted in the working tree, for review · **Follows**:
`docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md`.

**Scope as given**: replace the unconditional "first valid L gets a representation slot"
behaviour with a realized-quality eligibility gate; no score/bonus merely for being an L; an
ineligible L lets the next best rectangle occupy the slot; reuse the existing hub-guard-style
area + correctness pattern rather than inventing a new scoring system; do not touch entrance-door
selection or entrance-sequence logic (a separate, named follow-up); commit separately from the
wet-room quality-tier change.

## What was built

| Where | What |
|---|---|
| `app/vertical_slice/l_massing_guard.py` (**new module**) | `ExposureProportions` (worst wet-room aspect, two-sided habitable share — the two realized metrics `hub_guard.PlanProportions` does not carry) and `exposure_of(design)`. `l_earns_representation_slot(rect, rect_x, l, l_x, *, area_keep_ratio=hub_guard.AREA_KEEP_RATIO)`: the same two-rule shape as `hub_guard.hub_keeps_primary` — (1) CORRECTNESS: the L must be better on at least one of bedroom/master/safe-room aspect, worst wet-room aspect, wet adjacency, two-sided exposure, or larger; (2) POLICY: the L must deliver at least `area_keep_ratio` of the best rectangle's area, reusing `hub_guard.AREA_KEEP_RATIO` (0.85) directly rather than a new number. `eligible_for_slot(rect_plan, l_plan)`: the one seam both call sites use, reading `.design` — deliberately does NOT touch `hub_guard.py`'s own dataclass or its 008 tests. |
| `general_pipeline._alternative_plans` — **both** the normal walk and the "MASSING REPRESENTATION" block | Every place a non-"1W" candidate could be added is gated: `l_massing_guard.eligible_for_slot(best_rect_so_far, plan)` against the best "1W" plan realized so far (`[chosen] + found`, by `concept.used_area_m2`); an ineligible candidate is skipped (`continue`), not added. The normal walk needed the SAME gate as the representation block — a brief with fewer than `limit` distinct rectangle families reaches an L there directly, before the representation block ever runs; found and fixed during measurement (§ below), not assumed away. |
| `demo/service._select_plans`'s Pass 0 | The same gate, applied after `_break_l_tie` picks an orientation (eligibility and orientation are independent — the brief's own point 5), against the best "1W" plan anywhere in the pool. Routed through a new one-line seam, `_l_massing_eligible(rect_plan, l_plan)`, mirroring the EXISTING `_l_quality_of_plan` seam the orientation tiebreak already uses — the same reason: a test can stand in for it without building full geometry. |
| Entrance-door selection / entrance-sequence logic | **Untouched**, as instructed. Recorded as a separate follow-up defect in the investigation report (§5.1) — not this change's concern. |
| Nothing else | `_break_l_tie`, `LQuality`, `hub_guard.py`'s own dataclass/tests, tier-1 row rescue, the seam search — untouched, confirmed by reading and by the regression run below. |

**Why the normal-walk gate was necessary, not optional**: first measured with the gate only in
the "MASSING REPRESENTATION" block, the fixture sweep still showed the L unconditionally shown on
several 2BR briefs (e.g. `base 2BR_open`: L at 125.0 m² against a 157.4 m² rectangle already
found — ratio 0.79, well under 0.85). Root cause: `_alternative_plans`'s FIRST loop takes any
not-yet-seen-family candidate in generator order up to `limit`; a brief with fewer than `limit`
distinct rectangle families reaches an L candidate there directly, before the "MASSING
REPRESENTATION" block — which only runs for massings not yet represented — is ever reached. The
gate now applies at both points, using the same `l_massing_guard.eligible_for_slot` call.

## Tests

`tests/test_demo_outline_selection.py`: a new `autouse` fixture `_stub_l_eligibility` stubs
`demo.service._l_massing_eligible` to always return `None` (eligible) — every existing test in
this file is about REPRESENTATION MECHANICS (which slot, which pass, which tiebreak), not
eligibility itself, mirroring how `_stub_l_quality` already decouples the orientation tiebreak
from real geometry. One new test,
`test_an_ineligible_l_is_not_shown_and_the_next_rectangle_takes_its_place`, overrides the stub to
exercise the gate's real integration. `tests/vertical_slice/test_l_parti.py`: the two tests that
asserted the OLD unconditional behaviour on `l_shaped_site_deep_primary()` now bypass the gate
(`l_massing_guard.eligible_for_slot` forced permissive) to keep testing slot MECHANICS in
isolation; a new test, `test_an_ineligible_l_on_this_brief_does_not_reach_the_alternatives`, checks
the gate's real, un-bypassed effect on that exact brief (measured ratio ~0.72–0.83, correctly
rejected). `tests/test_demo_p0.py`: the same pattern for the three real, end-to-end (API-level)
tests this change affected — two bypass the gate to keep testing survey/labelling and orientation
preference mechanics, one new test confirms the gate's real effect on the exact brief measured in
the investigation report (~132 m² L against a ~194 m² rectangle, ratio ~0.68).

Full fast suite (excluding regression/ai_harness/knowledge tiers), combined with the wet-room
change already in the tree: **1290 passed, 9 xfailed, 0 failed** (identical to the wet-room
report's own count — this change added net zero to that total: 5 new tests, 5 tests' scenarios
narrowed/bypassed rather than removed).

## Measured

**Fixture sweep** (5 L sites × 6 programmes, 30 briefs — the same set the investigation report
used): L shown as an alternative in **16 → 2** briefs.

| site | programme | before (alt areas, m²) | after |
|---|---|---|---|
| base | 2BR_open | 153.1, 157.4, **125.0** | 153.1, 157.4 |
| base | 3BR_open | 192.2, 163.2, 159.3, **130.2** | 192.2, 163.2, 159.3 |
| front_arm | 2BR_open | 153.1, 157.4, **125.0** | 153.1, 157.4 |
| front_arm | 3BR_open | 192.2, 163.2, 159.3, **130.2** | 192.2, 163.2, 159.3 |
| front_arm | 1BR_open | 113.5, **93.7** | 113.5 |
| long_arm | 2BR_open | 146.3, 149.6, **114.6** | 146.3, 149.6, **129.0** (a different rectangle fills the slot) |
| long_arm | 3BR_open | 194.8, 157.4, 154.4, **137.1** | 194.8, 157.4, 154.4 |
| long_arm | 3BR_mmd_open | **143.1** (only alt) | — (none: no rectangle existed to take the slot) |
| deep_primary | 2BR_open | 155.0, 155.0, **119.0** | 155.0, 155.0 |
| deep_primary | 3BR_open | 189.0, 165.8, 162.4, **136.5** | 189.0, 165.8, 162.4 |
| deep_primary | 3BR_mmd_open | **141.5** (only alt) | — (none) |
| deep_primary | 4BR_open | **161.5** (only alt) | — (none) |
| west_arm | 2BR_open | 153.1, 157.4, **125.0** | 153.1, 157.4 |
| west_arm | 3BR_open | 192.2, 163.2, 159.3, **130.2** | 192.2, 163.2, 159.3 |

The 2 that remain (`base`/`west_arm 1BR_open`, L at 100.0 m² against a 113.5 m² rectangle, ratio
0.87) clear the area floor and are correctly kept — matching the investigation report's own
prediction that not every measured case fails at 0.85.

**Which rectangle replaced each removed L**: in 12 of 14 removed cases, the alternatives list
simply loses its L slot — the pool already had every rectangle alternative the walk found, and
none was displaced by the L in the first place (`014`'s own guarantee, preserved). In 1 case
(`long_arm 2BR_open`) the normal walk's own gate (not the representation block) lets a *different*
rectangle (129.0 m²) take the slot the L would have — a direct, measured instance of "let the
next best rectangle occupy the slot." In 3 cases (`*_mmd_open`, `4BR_open`) no other massing
existed at all for that brief/site, so the slot is simply not filled — there was nothing to
replace the L with, which is the correct outcome, not a gap.

**Real-corpus sweep** (36 of 432 regression contexts, stride 12, through the actual
`demo.service._select_plans`): 32 planned, 4 refused — identical before/after. **1 of 32** briefs
shows an L in the shown set, **unchanged before and after** (167.9 m² against a 192.2 m² best
rectangle, ratio 0.874 — above the 0.85 floor, and it wins on master aspect: 1.37 vs. 2.09) —
confirming the one borderline case the investigation flagged is handled exactly as predicted, not
swept away by an overly blunt rule.

**Delivered/effective area, before → after**: for the 14 removed-L fixture briefs, the shown
alternatives now deliver what the rectangles already delivered (94.5–100% of what they delivered
with the L present, since none was displaced) — the L's own 60–87% delivery is simply no longer
shown as an equal-looking option.

**Room-quality/warning changes**: none beyond the L's own removal — `over_preferred`/quality
warning fields on the surviving rectangle alternatives are unaffected (same candidates, same
realization).

**Alternative count**: unchanged in 11 of 14 removed cases (a rectangle slot the L used to occupy
is simply gone, or replaced 1-for-1); the pool shrinks by exactly one in the 3 `*_mmd_open`/`4BR_open`
cases with no other massing to offer.

**Primary changes**: **0**, everywhere measured — fixture and real-corpus alike, confirmed by
`layout_signature`/`concept.rationale` equality, exactly as the gate's design guarantees (it is
never consulted for the primary, only for representation slots).

**Runtime**: fixture sweep 42.0 s → 49.4 s (+17.6%, 30 briefs, includes the extra realized-metric
computation the gate needs); real-corpus sweep 265.8 s → 263.9 s (-0.7%, noise-level, 36 contexts
through the full product path). No new solves are introduced in the common case: the gate only
ever reads `.design` on plans ALREADY realized to check `.ok`; where a candidate is rejected the
existing `MASSING_ATTEMPT_LIMIT`/attempt budgets (already paid for, pre-existing) absorb the
retry, not a new one.

## Interpretation

- **The gate does what the investigation predicted, at the measured magnitude**: ~88% of shown
  engine L's (14 of 16 in the fixture sweep) lose their unconditional slot; the one real-corpus
  case and the two fixture cases that survive do so because they genuinely clear the same,
  already-shipped `hub_guard.AREA_KEEP_RATIO` threshold this reuses.
- **No score or bonus for being an L**: confirmed by construction — `l_earns_representation_slot`
  never reads `massing_signature`, only realized metrics of both plans being compared.
- **Explicit vs. engine-generated stays moot, as the investigation found**: `SelectedFootprint`
  is still rectangle-only; there is no code path this gate could accidentally apply to a person's
  own authoritative choice.
- **Entrance-sequence quality (investigation §5.1) is untouched**, as instructed — a real, related,
  but separate defect for its own future review.

No production code beyond `l_massing_guard.py` (new) and the three call-site edits was changed.
Stopping for review before merge, as instructed — commit separately from the wet-room change.
