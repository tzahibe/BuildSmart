# Wet Rooms

Status: IMPLEMENTED_MERGED

## Current behavior

A toilet is a **fixture**; a WC is a **room** — the parser (`OpenAIRequirementParser`, not the
planner) counts each שירותים mention and extracts a `FixtureDemand`; deterministic normalization
rules (R1–R5, `wet_room_normalizer.py`) turn that into concrete wet rooms with an origin
(`explicit` vs `count_derived`) and, where the demand is ambiguous, a structured question with
proposed kinds rather than a silent guess. `GUEST_WC` is created only when explicit — toilets
otherwise absorb into bathrooms. This extends into the review/chat/frontend flow (proposals a
person can accept or correct).

**Room-proportion quality tier extended to wet/service rooms**: `SHARED_BATHROOM` and `GUEST_WC`
now also get the bounded `preferred_aspect_ratio` quality tier (as a soft objective only, never a
hard gate) — see the Room Proportion / Quality Tier page for the shared mechanism. `LAUNDRY` is
explicitly excluded from this extension — not because the capability is missing (it's implemented
on `main`, see the Laundry page), but as a deliberate quality-tier/domain decision: `LAUNDRY` has
no `preferred_aspect_ratio` and was never added to `_QUALITY_TIER_GROUP`.

**Privacy and access quality (Issue #37, `wet_privacy.py`)**: C17 above already fails closed on
WHO may enter a wet room (an ensuite only from its host bedroom, everything else only from
circulation); this extension adds WHAT that access looks and feels like, per wet room, as a
`WetPrivacy` record computed off the REALIZED geometry (never off the requirement): the
entered-from zone's class (`PRIVATE`/`CIRCULATION`/`PUBLIC`/`SERVICE`), the zone the open door
faces (`door_facing`, a real segment test across a circulation zone's width when entered from
circulation), `direct_sight_line`, a tiered `public_exposure_score`, `circulation_obstruction`
(the door's own opening width against the corridor's net clear width) and `adjacency_quality`
(shares an interior wall with another wet room or the kitchen — the per-room read of M5's own
relationship). A new check, **C29 "wet-room privacy"**, fails closed ONLY on the hard rule: a wet
room entered DIRECTLY from `KITCHEN` or `DINING`. Corridor access is never refused by C29,
however exposed its facing geometry scores — decision A of `specs/009-guest-wc-placement`
already settled that proximity/exposure to the public part of the house is a ranking concern, not
a law, and `LIVING` is a legitimate corridor-class-adjacent entry (specs/009 §0 decision C's own
third-choice public access zone), so it is deliberately not in C29's hard-fail set. Everything
short of the hard rule is quality data only: `QualityOut.wet_privacy` (`app.demo.contract`) for
display, and `wet_privacy.candidate_privacy_key` for ranking — wired into
`app.demo.service._break_l_tie` (via `_privacy_key_of_plan`) as the last tiebreak among L-massing
peers already tied on the person's garden/street preference and on `LQuality`'s own Pareto
comparison. Not wired into `concept_generator.py`'s row-proportion quality tier — that stage runs
BEFORE doors exist, so no privacy signal could be computed there at all.

**Plumbing / wet-core efficiency (Issue #44, `wet_core.py`)**: a SOFT preference, never a hard
constraint — no check gates on it, and no candidate is refused for it. Per realized plan, a
`WetCore` record: `shared_wall_length_m` (interior wall shared between two wet rooms only),
`clusters`/`cluster_count` (wet rooms connected wall-to-wall through other wet rooms — one
plumbing stack could plausibly serve a whole cluster), `kitchen_adjacent_count` (wet rooms sharing
a wall with the kitchen) and `plumbing_complexity_index` (an ESTIMATE of independent plumbing
stacks/runs: connected components over wet rooms *and* the kitchen together — a wet cluster that
also touches the kitchen shares its run rather than adding one; lower is better). On
`QualityOut.metrics.wet_core` (`app.demo.contract`), additive and read-only. A ranking preference,
`wet_core.candidate_wet_core_key`/`better_candidate` (LOWER IS BETTER: fewer stacks first, then
more shared wet wall), mirrors `wet_privacy.candidate_privacy_key`/`better_candidate` — no caller
is wired to it by this Issue; it exists for a future one comparing otherwise-equal candidates, the
same way `wet_privacy`'s key existed before `_break_l_tie` used it. `wet_core_alignment` is a
separate, optional multi-level fact: given the realized wet rooms of two levels, how many of the
upper level's overlap a wet room on the level below (footprint overlap on the shared plot-absolute
grid, the same fact `building_validation.py`'s V2 already relies on) — not wired into any
single-level pipeline call (`design_output.assemble` only ever sees one level), for a future
caller that has both levels' realized geometry to call directly.

## Authoritative implementation

- `app/requirements/wet_room_normalizer.py` (deterministic rules R1–R5), `app/requirements/parser.py`
  (`FixtureDemand`, `NamedBathroom`, `AttachedWetRoom`, `SeparateWC` extraction).
- `app/vertical_slice/wet_rooms.py`.
- Wet-room semantics (007): PRs #2 (`e513d91`) and #4 (`ae6e1b8`), fix commits `a166777`, `8c4cdba`.
- Wet-room quality-tier extension: commit `f2092af`.
- Wet-room privacy and access quality (Issue #37): `app/vertical_slice/wet_privacy.py`; wired into
  `validation.py` (C29) and `design_output.py`/`contract.py` (`QualityOut.wet_privacy`).
- Plumbing / wet-core efficiency (Issue #44): `app/vertical_slice/wet_core.py`; wired into
  `design_output.py` (`GeometricDesign.wet_core`) and `contract.py`
  (`QualityOut.metrics.wet_core`) only — no `validation.py` check.
- Tests: `tests/wet_room_corpus/` (61 hand-labelled briefs), `tests/vertical_slice/test_quality_repartition.py`,
  `tests/vertical_slice/test_wet_privacy.py`, `tests/vertical_slice/test_wet_core.py`.

## Current constraints/invariants

- Toilet-vs-room policy: toilets absorb into bathrooms; `GUEST_WC` only when explicit.
- The quality-tier extension does not touch tier-1 row rescue, does not add `BATHROOM` to any
  row-rescue role set, does not touch `ENSUITE` sub-row behavior, and adds no shape-aware seam
  re-selection.
- `LAUNDRY` is excluded from the quality-tier extension — the capability is implemented on `main`
  (see the Laundry page), but it's intentionally not part of `_QUALITY_TIER_GROUP`: a quality-tier
  scope decision, not an absence of the capability.
- Wet-core (Issue #44) adds no check to `validation.py` and no ranking caller — it does not touch
  tier-1 row rescue, `concept_generator.py`'s quality tier, or the L-massing tiebreak `wet_privacy`
  is wired into. `wet_core_alignment` is computed and tested standalone; no product call site
  passes it two levels' realized geometry today (Multi-Level is IMPLEMENTED_MERGED at the module
  level but not wired to the live product path — see the Multi-Level Wiki page).

## Supersedes

`docs/WET_ROOM_SEMANTICS_PROPOSAL.md` (superseded by `specs/007-wet-room-semantics/spec.md`);
`docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md` (superseded by the quality-tier extension,
`f2092af`, same commit as its own companion investigation).

## Known follow-ups

The privacy ranking signal is wired into the L-massing orientation tiebreak only
(`app.demo.service._break_l_tie`) — it does not yet reach the general pool sort in
`_select_plans`/`_nearest_primary` (those functions are deliberately design-agnostic, tested on
stand-ins with no `.design`; see `tests/test_demo_outline_selection.py`'s own docstring), nor
`concept_generator.py`'s row/seam search (impossible there today — that stage runs before doors
exist, so no door-facing signal could be computed). Extending the tiebreak's reach beyond L-massing
peers is future work, not part of this Issue's scope. `specs/009-guest-wc-placement` remains
unimplemented (spec only): today every non-ensuite wet room is still planned in the private stack,
entered only from `HALL`/`CIRCULATION` (C17's own invariant), so C29's `LIVING`-is-not-a-hard-fail
carve-out has no real plan to apply to yet — it anticipates that spec's decision C rather than
reacting to shipped behavior.

`wet_core.candidate_wet_core_key`/`better_candidate` (Issue #44) has no caller wired in — a future
Issue choosing between otherwise-equal candidates (the way `_break_l_tie` already does for
privacy) is the natural next step, not part of this Issue's scope. `wet_core_alignment` likewise
has no caller: it needs two levels' realized geometry, which no single-level pipeline call
provides today (Multi-Level Phase 1 is backend-only — see the Multi-Level Wiki page); wiring it in
is future work for whenever Multi-Level reaches the live product path.

## Evidence/history

`specs/007-wet-room-semantics/{spec,plan}.md` (phase-by-phase implementation record),
`docs/ROOM_PROPORTION_QUALITY_TIER_REPORT.md` (the bedroom-class original this extension follows),
`docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md` (why the extension was needed — the shared-bathroom
strip-room problem, general case), `specs/009-guest-wc-placement` (ACTIVE_RESEARCH, spec only,
nothing implemented — a separate, not-yet-started extension).

## Last verified against git

`1d648c3` (main HEAD). `f2092af`, `8c4cdba`, `a166777` confirmed on `main` via `git log --oneline main`.
