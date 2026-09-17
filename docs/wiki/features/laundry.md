# Laundry

Status: NOT_IMPLEMENTED on `main`

## Current behavior

There is no laundry-room capability on `main` at all. `LAUNDRY_ROOM_ENABLED` does not exist
anywhere in this branch's code (confirmed via `git grep "LAUNDRY_ROOM_ENABLED"` on `main` —
zero matches). `docs/WET_ROOM_QUALITY_TIER_IMPLEMENTATION_REPORT.md` (a real, merged, current
capability) explicitly excludes `LAUNDRY` from its scope for exactly this reason.

**This page deliberately does not describe a "gated but implemented" laundry design as current
truth.** An earlier version of `docs/PROJECT_STATE.md` did, describing a laundry-room design that
was never merged — that description belonged to a separate, locked, never-merged worktree
(`worktree-015-laundry-room-option`), not `main`. Treat any older report claiming laundry is
"implemented but disabled" as describing that separate worktree, not this codebase's current
state, unless you've independently confirmed it against `main`.

## Authoritative implementation

None on `main`.

## Current constraints/invariants

N/A — the capability does not exist.

## Supersedes

N/A.

## Known follow-ups (explicitly NOT current)

- `integration/laundry-into-main` — an active, unmerged branch (checked out in another worktree)
  bringing a laundry-room capability to `main` for the first time, including `LAUNDRY_ROOM_ENABLED`,
  an allocation policy in `concept_generator.py`, and a `QualityOut.laundry_notice` disclosure
  field. That branch's own report describes a "post-approval verification" pass with a fix
  (`SAFE_ROOM` explicitly excluded from `laundry_notice`'s checked room set, because `SAFE_ROOM`
  realizes under its own template target from ordinary geometry regardless of laundry, which would
  otherwise be a false positive). **None of this is canonical until merged to `main`** — per this
  Wiki's own authority hierarchy (code + tests + current git state outranks everything else), an
  unmerged branch's self-reported "approved" status is not binding on `main` until the merge
  actually happens. This page will be rewritten, not merely amended, once that lands.
- `worktree-015-laundry-room-option` — a separate, older, also-never-merged laundry design.

## Evidence/history

`docs/LAUNDRY_ROOM_OPTION_REVIEW.md`, `docs/LAUNDRY_ROOM_PHASE1_REPORT.md`,
`docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md`, `docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md` — all exist
only on the unmerged `integration/laundry-into-main` branch as of this writing, not in this
repo's indexed corpus (they are not present in this checkout's working tree). Referenced here for
traceability only; do not cite them as retrievable evidence until merged.

## Last verified against git

`1d648c3` (main HEAD). `git grep -c LAUNDRY_ROOM_ENABLED` on `main` returns nothing; confirmed
`integration/laundry-into-main` is a real, unmerged branch via `git log main..integration/laundry-into-main`.
