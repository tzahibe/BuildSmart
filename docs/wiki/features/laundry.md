# Laundry

Status: INTEGRATED on `integration/laundry-into-main` (commit `3d8b9243a575034ca013e4aa0eb0d95c173cda78`); not yet merged to `main`

## Current behavior

**Explicit requirement, not appliance inference.** The parser (`OpenAIRequirementParser`,
`app/requirements/parser.py`) extracts `LaundryRoomDemand` (the `laundry` field on parsed
requirements), distinguishing a named laundry ROOM request (חדר כביסה, חדר שירות לכביסה, מקום/חדר
נפרד למכונת כביסה) from a bare appliance mention inside another room (e.g. "מכונת כביסה במטבח"),
which is explicitly NOT a room request — that case falls through to `other_requests` like any
other unsupported mention. `Project.laundry_requested` / `laundry_source_text` persist the parsed
value; `set_parsed_requirements`/`ProjectRepository` and `requirements_view._laundry_of` carry it
through to the engine as `LaundryRequirement(demand, source_text)`.

**Room program.** Gated by `LAUNDRY_ROOM_ENABLED = True` (`app/vertical_slice/concept_generator.py`).
When `program.laundry.demand is LaundryDemand.ROOM`, `build_room_program` emits exactly one
`ProgramRole.LAUNDRY` room (template: min 2.5m², target 4.0m², preferred max 8.0m², elasticity
0.10 — deliberately low, since a laundry room has little reason to grow with surplus).

**Allocation policy — service-headroom-first (Policy B).** When adding the laundry room creates an
area deficit, `_laundry_deficit_targets` draws the deficit from `_LAUNDRY_DEFICIT_SOURCE_ROLES =
(BATHROOM, TOILET)` headroom first, then cascades any remainder proportionally across the other
rooms — chosen over a FLEX-first policy that was measured structurally inert (FLEX needs ~2x the
deficit's capacity to matter and rarely coincides with one) and over a flat percentage refusal
threshold that was measured too blunt (7/9 representative cases misclassified) — see
`docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md`.

**Row-sharing (tier-1 rescue).** `_ROW_RESCUE_ROLES = (ProgramRole.TOILET, ProgramRole.LAUNDRY)` in
`_rows_for_width`: a lone LAUNDRY room that can't be shaped at a column's width and isn't itself a
dependent shares an ensuite's row, the same mechanism the WC fix (2026-09-14) established. Narrowed
to exactly these two roles rather than the full `ZoneGroup.SERVICE` — widening to the group was
measured to also rescue a lone BATHROOM in 1/404 real-corpus briefs, a real deviation from this
phase's own "no change to an existing brief" bar; BATHROOM's own eligibility is a separate,
already-in-motion decision (the row-sharing quality initiative) and deliberately isn't entered as a
side effect here.

**Disclosure notice.** `QualityOut.laundry_notice` (`app/demo/contract.py`,
`_laundry_redistribution_notice`) is informational only — never a validation error, no flat refusal
threshold. It compares each room's realized area against its own FIXED template target (not a
second "without laundry" solve — the footprint-proportion search can land on a materially different
candidate between two nominally-identical runs, confirmed directly on one case where a HALL's depth
alone moved 7.75m → 15.55m between runs) and flags rooms realized below `target *
LAUNDRY_REDISTRIBUTION_NOTICE_RATIO` (0.90). `_LAUNDRY_NOTICE_EXCLUDED_ROLES = (SAFE_ROOM,)`
excludes SAFE_ROOM: it realizes below its own template target from ordinary row-depth geometry
regardless of any laundry room (elasticity 0, never receives surplus either way) — a false positive
found post-activation by the e2e smoke test, not by the 31-cell activation measurement matrix
(none of its cells used `safe_room=True`).

**Not wired to product.** Backend/demo-pipeline only — no ReviewPage UI surfaces the
`laundry_notice` disclosure or an explicit laundry toggle (same pattern as Multi-Level Phase 1:
backend implemented, not yet wired to the product surface).

**Source.** Built on `worktree-015-laundry-room-option` (tip `da5b007`) — that worktree is not a
separate rival design; it IS the source branch this capability was implemented on, merged whole
into `integration/laundry-into-main` at `b678967`. It stays checked out/locked as a historical
artifact, not for further changes. (An earlier version of this page described it as "a separate,
older, also-never-merged laundry design" — that was inaccurate; corrected here.)

## Authoritative implementation

- `app/requirements/parser.py` (`LaundryRoomDemand` extraction), `app/projects/models.py`
  (`Project.laundry_requested`, `laundry_source_text`), `app/projects/repository.py`
  (`set_parsed_requirements`), `app/requirements/router.py`, `app/demo/requirements_view.py`
  (`_laundry_of`).
- `app/vertical_slice/concept_generator.py`: `LAUNDRY_ROOM_ENABLED`, the `ProgramRole.LAUNDRY`
  `RoomTemplate`, `_LAUNDRY_DEFICIT_SOURCE_ROLES`, `_laundry_deficit_targets`,
  `_ROW_RESCUE_ROLES`.
- `app/demo/contract.py`: `QualityOut.laundry_notice`, `LAUNDRY_REDISTRIBUTION_NOTICE_RATIO`,
  `_LAUNDRY_NOTICE_EXCLUDED_ROLES`, `_laundry_redistribution_notice`.
- Commits (`worktree-015-laundry-room-option`, merged via `b678967`): `b3a1161` (feasibility
  review), `c8020d4` (phase 1, gated off), `64453c8` (row-rescue narrowing fix, restored 0/404),
  `ec672a8` (area-budget investigation, measurement only), `27fabb5` (activation — service-first
  allocation + disclosure notice), `5261b0b` (corpus-count fix + activation e2e smoke),
  `a1dd3a8` (SAFE_ROOM notice false-positive fix), `da5b007` (SAFE_ROOM regression test).
- Integration: `b678967` (Laundry into a fresh branch off then-current `main`), `3d8b924`
  (current `main`, through the Knowledge Wiki-first/RAG-hybrid pivot, merged in — zero file
  overlap, no conflicts).
- Tests: `tests/vertical_slice/test_laundry_room.py` (551 lines — parsing, allocation, row-rescue,
  notice logic), `tests/test_laundry_activation_e2e.py` (225 lines — end-to-end through
  requirements/review/API), plus additions to `tests/test_requirements.py` and
  `tests/test_demo_p0.py`.

## Current constraints/invariants

- `LAUNDRY` is NOT in `_QUALITY_TIER_GROUP` and has no `preferred_aspect_ratio` — deliberately
  excluded from the wet/service-room quality-tier extension (`f2092af`); see the Room Proportion /
  Quality Tier and Wet Rooms pages.
- Row-rescue eligibility is exactly `(TOILET, LAUNDRY)`, not the full `ZoneGroup.SERVICE` — see
  Current behavior above for why.
- A bare appliance mention never creates a room; only an explicit named-room request does.
- `laundry_notice` is informational only — it never blocks generation and has no refusal threshold.
- Real-corpus validation: 0/404 previously-planned briefs changed by the row-rescue narrowing
  (Phase 1); 404/432 distinct-context match confirmed at activation (`docs/
  LAUNDRY_ROOM_ACTIVATION_REPORT.md`) — 432 distinct contexts is the reconciled, current
  denominator (750 raw → 472 reproducible → 432 distinct; 404 planned / 28 refused / 0 crashed).
  The full frozen 432-context corpus has not been re-swept against `3d8b924` specifically — focused
  Laundry tests (170) and the full backend suite were run post-integration instead; the full sweep
  is deferred to final release validation per standing instruction.

## Supersedes

N/A — first implementation of this capability; nothing prior existed on `main`.

## Known follow-ups

- Land `integration/laundry-into-main` to `main` — integrated and verified, pending final
  main-advancement approval.
- The full frozen 432-context corpus regression sweep against the final `main` HEAD, as part of
  final release validation (not yet run against `3d8b924`).
- BATHROOM's own row-rescue eligibility — a separate, already-in-motion decision (the row-sharing
  quality initiative), deliberately not addressed here.
- Wiring `laundry_notice` (and an explicit laundry toggle) into the ReviewPage/product surface —
  not started, same status as Multi-Level Phase 1's product wiring.

## Evidence/history

`docs/LAUNDRY_ROOM_OPTION_REVIEW.md` (feasibility review), `docs/LAUNDRY_ROOM_PHASE1_REPORT.md`
(phase 1 measurement + row-rescue narrowing), `docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md`
(allocation-policy measurement, four candidates A–D), `docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md`
(activation matrix, corpus-count reconciliation, SAFE_ROOM fix).

## Last verified against git

`3d8b9243a575034ca013e4aa0eb0d95c173cda78` (`integration/laundry-into-main` HEAD, current main
`ccadc33` merged in). `LAUNDRY_ROOM_ENABLED = True`, `_ROW_RESCUE_ROLES`,
`_LAUNDRY_NOTICE_EXCLUDED_ROLES`, and `_QUALITY_TIER_GROUP` (LAUNDRY absent) all confirmed present
by direct `grep` against this commit; focused Laundry tests (170) and the full backend suite
(1376 passed, 4 pre-existing/unrelated failures — see the Knowledge System page) run clean at this
commit.

`backend/app/knowledge/doc_status.json`'s entry for this page previously still read
`capability_status: NOT_IMPLEMENTED` even after this rewrite — that table is a hand-curated
authoritative source, deliberately not derived from a page's own prose (see
`docs/wiki/architecture/knowledge-system.md`), so editing this page alone never updates it.
Corrected alongside this note to `capability_status: IMPLEMENTED`, `branch:
integration/laundry-into-main`, `merged_to_main: false`.
