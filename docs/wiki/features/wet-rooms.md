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

## Authoritative implementation

- `app/requirements/wet_room_normalizer.py` (deterministic rules R1–R5), `app/requirements/parser.py`
  (`FixtureDemand`, `NamedBathroom`, `AttachedWetRoom`, `SeparateWC` extraction).
- `app/vertical_slice/wet_rooms.py`.
- Wet-room semantics (007): PRs #2 (`e513d91`) and #4 (`ae6e1b8`), fix commits `a166777`, `8c4cdba`.
- Wet-room quality-tier extension: commit `f2092af`.
- Wet-room privacy and access quality (Issue #37): `app/vertical_slice/wet_privacy.py`; wired into
  `validation.py` (C29) and `design_output.py`/`contract.py` (`QualityOut.wet_privacy`).
- Tests: `tests/wet_room_corpus/` (61 hand-labelled briefs), `tests/vertical_slice/test_quality_repartition.py`,
  `tests/vertical_slice/test_wet_privacy.py`.

## Current constraints/invariants

- Toilet-vs-room policy: toilets absorb into bathrooms; `GUEST_WC` only when explicit.
- The quality-tier extension does not touch tier-1 row rescue, does not add `BATHROOM` to any
  row-rescue role set, does not touch `ENSUITE` sub-row behavior, and adds no shape-aware seam
  re-selection.
- `LAUNDRY` is excluded from the quality-tier extension — the capability is implemented on `main`
  (see the Laundry page), but it's intentionally not part of `_QUALITY_TIER_GROUP`: a quality-tier
  scope decision, not an absence of the capability.

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

## Evidence/history

`specs/007-wet-room-semantics/{spec,plan}.md` (phase-by-phase implementation record),
`docs/ROOM_PROPORTION_QUALITY_TIER_REPORT.md` (the bedroom-class original this extension follows),
`docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md` (why the extension was needed — the shared-bathroom
strip-room problem, general case), `specs/009-guest-wc-placement` (ACTIVE_RESEARCH, spec only,
nothing implemented — a separate, not-yet-started extension).

## Last verified against git

`1d648c3` (main HEAD). `f2092af`, `8c4cdba`, `a166777` confirmed on `main` via `git log --oneline main`.
