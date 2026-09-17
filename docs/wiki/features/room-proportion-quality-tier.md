# Room Proportion / Quality Tier

Status: IMPLEMENTED_MERGED

## Current behavior

Bedroom-class rooms (`BEDROOM`, `MASTER_BEDROOM`, `SAFE_ROOM`) get a bounded
`preferred_aspect_ratio` (1.5) as a quality **target**, never a gate — the hard `max_aspect_ratio`
(2.5) and every area maximum are untouched, and validation checks C17/C20/C21 still hold the
realized drawing to them regardless of which planner path produced it. Mechanism: a lone row can
take the master's corridor-facing slot beside its ensuite, letting the master (or whichever room
hosts an ensuite) go full-width while the displaced room sits beside it instead of alone — the
existing tier-2 repartition machinery, generalized to run for quality, not only to repair a hard
shape refusal. Phase 2 narrows ranking further: a quality peer competes only against its own base,
never globally.

This same mechanism was later extended to `SHARED_BATHROOM`/`GUEST_WC` — see the Wet Rooms page.

## Authoritative implementation

- `app/vertical_slice/general_pipeline.py`, `concept_generator.py`, `l_parti.py` (repartition/
  tier-2 pairing, quality-twin selection).
- Commit `be8c0ca` (bedroom-class original); commit `f2092af` (wet/service-room extension).
- Tests: `tests/vertical_slice/test_quality_repartition.py` (9 tests: quality candidate presence,
  no-candidate-without-an-ensuite, bounded search, C17/C20/C21 preserved).

## Current constraints/invariants

- `preferred_aspect_ratio` is a soft target, never a hard gate — the hard aspect ceiling (2.5) and
  area maxima are unchanged.
- A shared row in every parti (spine columns, front-band rear columns, L arm) has exactly **one**
  corridor-facing slot — this is a topology ceiling, not a search ceiling. Measured over the
  432-context regression corpus: at most ~16% of lone private/service rows can ever be paired, and
  no quality candidate may fail C17/C20/C21 (every one of 78 primaries' quality twins that solved
  passed every check, 0 quality candidates failed).
- No candidate exists without an ensuite hosting it.

## Supersedes

`docs/ROOM_PROPORTION_REPARTITION_REPORT.md` (the investigation that found the one legal fix
within the existing access model — this page's mechanism).

## Known follow-ups

The next levers here are semantic (what counts as pairable), not search — a further search-side
fix for the topology ceiling above is not expected to yield more "for free."

## Evidence/history

`docs/ROOM_PROPORTION_REPARTITION_REPORT.md` (why: the topology-ceiling measurement, 1,770 lone
private/service rows, at most 283 pairable, 149 of 432 briefs with no ensuite at all),
`docs/ROOM_PROPORTION_QUALITY_TIER_REPORT.md` (the implementation record itself, phases 1 and 2
measured against the 432-context corpus).

## Last verified against git

`1d648c3` (main HEAD). `be8c0ca`, `f2092af` confirmed on `main` via `git log --oneline main`.
