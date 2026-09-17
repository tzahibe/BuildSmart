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

## Authoritative implementation

- `app/requirements/wet_room_normalizer.py` (deterministic rules R1–R5), `app/requirements/parser.py`
  (`FixtureDemand`, `NamedBathroom`, `AttachedWetRoom`, `SeparateWC` extraction).
- `app/vertical_slice/wet_rooms.py`.
- Wet-room semantics (007): PRs #2 (`e513d91`) and #4 (`ae6e1b8`), fix commits `a166777`, `8c4cdba`.
- Wet-room quality-tier extension: commit `f2092af`.
- Tests: `tests/wet_room_corpus/` (61 hand-labelled briefs), `tests/vertical_slice/test_quality_repartition.py`.

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

None currently tracked beyond what's listed as explicitly out of scope above.

## Evidence/history

`specs/007-wet-room-semantics/{spec,plan}.md` (phase-by-phase implementation record),
`docs/ROOM_PROPORTION_QUALITY_TIER_REPORT.md` (the bedroom-class original this extension follows),
`docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md` (why the extension was needed — the shared-bathroom
strip-room problem, general case), `specs/009-guest-wc-placement` (ACTIVE_RESEARCH, spec only,
nothing implemented — a separate, not-yet-started extension).

## Last verified against git

`1d648c3` (main HEAD). `f2092af`, `8c4cdba`, `a166777` confirmed on `main` via `git log --oneline main`.
