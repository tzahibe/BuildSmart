# Wet-Room Quality Tier — implementation record

**Date**: 2026-09-16/17 · **State**: uncommitted in the working tree, for review · **Follows**:
`docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md` (fix A) and `docs/ROOM_PROPORTION_QUALITY_TIER_REPORT.md`
(the bedroom-class original, commit `be8c0ca`).

**Scope as given**: extend the existing preferred-proportion quality tier to `SHARED_BATHROOM`
and `GUEST_WC` where the current machinery can improve them safely, as a soft objective only
(never a hard gate); do not touch tier-1 row rescue; do not add `BATHROOM` to any row-rescue role
set; do not touch `ENSUITE` sub-row behaviour; do not add shape-aware seam re-selection. `LAUNDRY`
excluded — confirmed not in the tested path (`LAUNDRY_ROOM_ENABLED` does not exist on this branch
at all; it lives only on the separate, locked `worktree-015-laundry-room-option`).

## What was built

| Where | What |
|---|---|
| `RoomTemplate.preferred_aspect_ratio` | `BATHROOM` 2.0, `TOILET` 2.5 (the investigation's own knee values). Still never a gate: `room_depth_band_m`, `_zone_spec` and C20 are untouched. |
| `_preferred_aspects` | Now also includes `BATHROOM`/`TOILET`, **except** any room whose `wet_kind is ENSUITE` — excluded unconditionally, regardless of the template value, because an ensuite's shape comes from its host row's combined depth, not its own (a different mechanism; left for the ensuite-sub-row's own future phase). |
| `general_pipeline._prefer_quality_twin`'s `preferred` dict | Same ENSUITE exclusion, mirrored, using `chosen.wet_rooms` — this is the REALIZED-shape phase-2 comparison, a separate code path from `_preferred_aspects` that needed the same guard independently. |
| `_quality_score` (**new, was 3-tuple, now 5**) | `(PRIVATE worst shortfall, PRIVATE rooms past target, SERVICE worst shortfall, SERVICE rooms past target, mean)` — PRIVATE (bedroom-class) judged strictly before SERVICE (wet), via `_QUALITY_TIER_GROUP` (keyed by role, mirroring `build_room_program`'s own unconditional group assignment for exactly these 5 roles — not a second role list to maintain). |
| `_quality_accepts` (**rewritten**) | A candidate is now rejected outright if it leaves any PRIVATE room worse (checked first, unconditionally); otherwise accepted if PRIVATE **or** SERVICE improves by the existing `_QUALITY_MIN_GAIN`/`_QUALITY_SPILL` thresholds (reused as-is, not recalibrated). The per-zone spill guard is unchanged in form, now simply applies to a wider room set. |
| `_quality_candidates`'s early-exit | Switched from reading the (now private-only) `score[0]` to calling `_quality_shortfall` directly over every scored room — otherwise a plan with a perfect bedroom set but a strip bathroom would never even be searched. |
| Nothing else | `_dependent_pairings`, `_pair_with_open_member`, `_access_intact`, the seam search, tier-1 row rescue, and every L-parti function were confirmed unchanged and untouched by reading, not by assumption (see the investigation report's code trace). |

**Why the tiering was necessary, not optional**: the naive first pass (pool BATHROOM/TOILET into
the same untiered objective as bedroom-class) was implemented, tested, and immediately caught a
real regression by the EXISTING test `test_the_l_arm_gets_a_quality_candidate_through_the_generic_hook`:
a candidate that squared a bathroom from 3.0 to 1.1 out-ranked one that improved a bedroom from
1.745 to 1.71, because the bathroom's shortfall against its 2.0 preferred was simply larger in
absolute terms. Rewriting `_quality_score`/`_quality_accepts` as a strict two-tier comparison
(PRIVATE first) fixed it — verified: the same test now passes, and the fixture's isolated bedroom
result is byte-identical to a hand-run "before" simulation (see Measured, below).

## Tests

`tests/vertical_slice/test_quality_repartition.py` (9, unchanged in count, 2 edited): all pass.
`test_the_preferred_aspect_is_a_target_and_the_hard_limits_are_untouched` extended with the new
`WET_QUALITY_ROLES` scope (`BATHROOM`→2.0, `TOILET`→2.5) instead of asserting they stay `None`.
`test_vocabulary_is_additive` (the literal `ROOM_TEMPLATES` snapshot) updated the same way — the
same pattern `be8c0ca` itself used when it first added the field. Full fast suite (excluding
regression/ai_harness/knowledge tiers): **1290 passed, 9 xfailed, 0 failed** before the snapshot
fix, **1 additional pass** after it — no other test anywhere in the suite was affected.

## Measured — full 432-context regression corpus, before/after in the same process

**Method**: two full sweeps of the real 432-context corpus (`generate_demo_design`'s own
`_plan_outlines_until_one_plans`), "before" simulating pre-change behaviour by nulling
`BATHROOM`/`TOILET`'s `preferred_aspect_ratio` back to `None` in-memory on the identical, current
codebase (faithful because `_quality_score`'s SERVICE tier degenerates to empty — and thus
provably inert — whenever no room in the scored set carries the field), "after" running the
change as committed to the working tree. Both processes ran concurrently on the same machine
under identical, non-trivial background load (see Runtime).

**Outcome-level**: 432/432 contexts identical between sweeps — **334 planned, 98 refused, 0
errors, in both**. **LOST/GAINED: 0.** (Note: the historical "404 planned/28 refused" figure
from earlier reports is stale against the current `main` — legitimate feature growth since then,
not this change; before/after agree with each other, which is what this measurement is for.)

**Validation**: 0 `C17`/`C20`/`C21` failures, before and after, across all 334 planned primaries.

**Aspect distributions** (both-planned contexts, n=334):

| | n | p50 before→after | p90 | max | >1.6 | >1.8 | >2.0 | >2.5 |
|---|---|---|---|---|---|---|---|---|
| BATHROOM (all) | 538 | 1.920→1.919 | 2.875 (same) | 3.000 | 348→348 | 300→300 | 245→**243** | 120→**122** |
| BATHROOM × `shared_bathroom` | 334 | 1.950→1.933 | 2.950 | 3.000 | 225→225 | 194→194 | 159→**157** | 101→101 |
| BATHROOM × `ensuite` (must be untouched) | 204 | 1.897→1.897 | 2.500→2.514 | 2.950 | 123→123 | 106→106 | 86→86 | 19→**21** |
| TOILET (`guest_wc`) | 75 | 2.355→2.355 | 3.462 | 3.500 | 56→56 | 53→53 | 47→47 | 36→36 |
| BEDROOM | 528 | 1.614→1.614 | 2.038 | 2.340 | 279→**280** | 173→**176** | 65→65 | 0→0 |
| MASTER_BEDROOM | 334 | 1.400→**1.409** | 2.117 | 2.433 | 114→**115** | 84→**85** | 54→54 | 0→0 |
| SAFE_ROOM | 187 | 1.500→1.500 | 2.146 | 2.375 | 71→**73** | 37→**39** | 25→**26** | 0→0 |

The shared-bathroom aspect distribution barely moves in aggregate (the topology ceiling the
investigation predicted: an unpairable lone bathroom, the common case, cannot be helped by this
mechanism at all — see below). The small ENSUITE count changes at the tail (`>2.5`: 19→21) are
**not** the quality tier touching ensuites (it never scores them) — they are the same downstream
effect as the bedroom-class counts moving: a different peer got chosen for unrelated reasons in a
small number of plans, which necessarily re-shapes every room in that plan's arm, ensuite
included. This is expected and bounded (see next section).

**Primaries with any change at all**: **2 of 334** (0.6%) — both variants (open/closed plan) of
one brief (3 BR + safe room + 2 wet rooms, 10×20 m footprint). `quality_repartitioned` primaries:
82 (before) → 80 (after).

**The one real finding, fully root-caused**: in both changed contexts, the delivered primary
**reverted from a bedroom-class-fixing quality peer to the unfixed base plan** — a genuine
regression for the bedroom-class rooms (MASTER 1.11→1.97, BEDROOM_1 1.61→1.89, BEDROOM_2
1.56→1.96, SAFE_ROOM 1.46→2.08), traded for a modest bathroom improvement (BATH_2 2.12→1.88).
Traced to the exact line: `_quality_accepts`'s **pre-existing, unmodified** spill guard —
*"no room that was inside its preferred aspect is carried more than `_QUALITY_SPILL` past
it"* — which now also watches `BATH_2` (it did not before, having no `preferred_aspect_ratio` to
watch). The peer that fixes all four bedroom-class rooms does so by a row move whose side effect
carries `BATH_2` from 1.875 to 2.121 — a spill of 0.121 against the 0.1 allowance — so the SAME
guard that protects bedroom-class rooms from an over-aggressive trade now also blocks this
particular private-only-favourable trade, because it cannot distinguish "this spill is on the tier
that is NOT improving" from "this spill is on the tier that IS." **This is a direct, measured
consequence of widening the guard's scope, not a bug in the new tiering** (the tiering itself
correctly identified PRIVATE as improving and SERVICE as not, and correctly refused to accept on
SERVICE's say-so) — it is the SAME check the tiering logic sits behind, doing exactly what it has
always done, now over a wider room set. Confirmed as the SOLE mechanism behind both of the two
changed primaries directly (not inferred): captured every `_quality_accepts` call for this exact
context and printed its `base`/`new` aspect dicts and the spill-triggering zone.

**Plans improved / worsened** (by the wider definition — any tracked room's aspect changed):
0 plans improved on service-with-no-private-cost (the only 2 changes are exactly the case above);
**2 plans "worsened"** in the sense that a private room's realized aspect is worse than it was —
both are this one root cause. Zero plans anywhere in the corpus show a private room getting worse
for any OTHER reason, and zero show a private room getting worse while a service room's shape is
unrelated to why.

**Runtime**: both sweeps ran concurrently on the same machine under substantial, non-uniform
background load (other investigation scripts and test runs share this environment) — 2725.3 s
(before) vs. 2725.4 s (after), a +0.006% paired difference. Given the noise floor this implies
(both runs took the same wall time to the second despite the shared, uneven load), this is
consistent with "no measurable runtime cost," but should not be read as a precise, isolated
number the way `be8c0ca`'s own controlled (idle-machine, repeated) methodology produced — a
dedicated idle-machine run would be needed for a number with that level of confidence.

## Interpretation

- **The topology ceiling predicted by the investigation is confirmed at full-corpus scale**: most
  `shared_bathroom`/`guest_wc` strips are simply unpairable (no ensuite shares their column), so
  the aggregate distributions barely move — this was never expected to be a broad fix, only a
  correctly-scoped one.
- **Where it does fire, it is safe in 332 of 334 cases (99.4%) and precisely explained in the
  other 2 (0.6%).** No ensuite was ever moved by this change; no C17/C20/C21 regression; no
  LOST/GAINED; no bedroom-class aspect got worse for any reason other than the one named above.
- **The one finding is a real trade-off, not a defect in the tiering this task asked for.** It is
  the pre-existing spill guard, now correctly but more broadly applied. Three honest options, not
  decided here:
  1. **Ship as measured.** 2/334 contexts trade a fixed bathroom for unfixed bedrooms — a real but
     rare and now fully disclosed cost.
  2. **A small, separately-reviewable follow-up**: make the spill guard tier-relative (only
     protect a tier that is not the one driving acceptance) — a few-line, mechanically simple
     change, but it is a behavior change to shared, pre-existing logic outside this task's
     explicit scope ("extend... only") and was not asked for, so it is named here and not applied.
  3. **Revert the SERVICE-tier addition's interaction with the spill guard specifically** by
     excluding SERVICE rooms from the spill check while keeping them in the accept/score tiers —
     narrower than option 2, same caveat.

No production code beyond the four listed edits was changed. Stopping for review before merge, as
instructed.

---

## Follow-up (2026-09-17): the spill guard made tier-relative

**Directive**: do not ship the 2/334 trade-off as-is; do not remove wet rooms from spill
protection entirely; make the spill guard tier-relative, consistent with `_quality_score`'s
existing PRIVATE-before-SERVICE ordering; keep wet rooms protected from hard-limit violations,
invalid geometry and materially severe degradation; leave ENSUITE exclusion, tier-1 rescue and
the seam search untouched; reuse `_quality_score`'s tier semantics rather than a second ranking
system.

**What changed**: `_quality_accepts`'s per-zone spill check is no longer one flat
`_QUALITY_SPILL` (0.1) for every room. A PRIVATE room keeps exactly that allowance,
unconditionally — a SERVICE-side trade can never cost a bedroom-class room anything beyond what
the rule always allowed. A SERVICE room gets the same flat 0.1 **unless** the PRIVATE tier is the
one actually improving this candidate (`private_improves`, the same boolean the accept logic
already computes for its own gate — no second computation, no second ranking system), in which
case its allowance widens to `_QUALITY_LOWER_TIER_SEVERE_FRACTION` (0.5) of its OWN hard headroom
— `preferred + 0.5 * (max_aspect_ratio - preferred)` — so a wet room pushed to, say, 2.5
(BATHROOM) or 3.0 (TOILET) is still refused; one pushed to 2.12 (the measured case) is not. Hard
limits (`max_aspect_ratio`, C20/C21), geometry validity (the solver/validator gate every candidate
regardless), tier-1 row rescue and the seam search are untouched — this is purely a widened
tolerance inside the QUALITY tier's own soft acceptance check.

**Re-measured on the exact same full 432-context corpus, same before/after method**:

| | before (no wet objective) | after (tier-relative spill) |
|---|---|---|
| planned / refused | 334 / 98 | 334 / 98 |
| LOST/GAINED | — | **0** |
| primaries byte-identical | — | **334 / 334 (100%)** |
| `quality_repartitioned` primaries | 82 | 82 |
| the 2 previously-affected primaries | MASTER 1.108, BEDROOM_1 1.614, BEDROOM_2 1.559, SAFE_ROOM 1.460 (open-plan); MASTER 1.394, BEDROOM_1 1.704, BEDROOM_2 1.643, SAFE_ROOM 1.346 (closed) | **identical, both variants** — bedroom improvements fully kept |
| BATHROOM (all, n=538) | p50 1.920, >2.5: 120 | **identical** |
| BATHROOM × `shared_bathroom` (n=334) | p50 1.950, >2.5: 101 | **identical** |
| BATHROOM × `ensuite` (n=204) | p50 1.897, >2.5: 19 | **identical** |
| TOILET × `guest_wc` (n=75) | p50 2.355, >2.5: 36 | **identical** |
| BEDROOM / MASTER_BEDROOM / SAFE_ROOM | p50 1.614 / 1.400 / 1.500 | **identical** |
| C17 / C20 / C21 | 0 / 0 / 0 | 0 / 0 / 0 |
| runtime | 2725 s | 2842 s (+4.3%, same shared, contended machine as the phase-1 measurement — not an isolated number) |

**Every single metric is now byte-identical between "no wet objective" and "wet objective with the
tier-relative spill guard," across all 432 contexts** — including the two previously-regressed
primaries, confirmed by direct comparison of their per-zone aspects (both variants: identical to
the last decimal). This is a stronger result than "the 2/334 trade-off is fixed": on this real
corpus, restoring the bedroom-class win never costs anything else measurable at all — the
0.5-of-hard-headroom allowance was never exercised anywhere near its own limit (the one case that
needed it used only 0.121 of a 0.5/1.0 budget on BATHROOM, comfortably inside).

**What this does and does not mean**: the fix is confirmed SAFE at full-corpus scale, not merely
"safe in the one case found." It does **not** mean the wet-quality objective changed any
DELIVERED primary's wet-room shape anywhere in this corpus (see the phase-1 "Interpretation"
section above — the topology ceiling means most `shared_bathroom`/`guest_wc` strips have no
column-local pairing partner to switch to at all, in this corpus, regardless of the spill guard).
What it means is narrower and precisely what was asked: extending the objective to wet rooms no
longer costs a single bedroom-class room anything, anywhere, in the real corpus measured — the
2/334 cost has gone from "measured and disclosed" to "measured and eliminated."

Tests: same 9 in `test_quality_repartition.py`, unaffected by this follow-up (re-run, all pass).
Stopping for review before merge, as instructed — this closes the one open question the phase-1
report left (§ "Interpretation," option 2, now applied and measured rather than merely proposed).
