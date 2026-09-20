# Laundry

Status: IMPLEMENTED on `main` (commit `6499604aeda6b5b044398308ffd9fd2334b755b4`, fast-forwarded from `integration/laundry-into-main`)

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

**Guaranteed semantics (Issue #21, 2026-09-18).** The definition already decided for the laundry
room — an enclosed room with its own door, a usable machine bay, and a mandatory exterior window —
is now enforced by the generator and the validator, not merely assumed:

- **Exterior wall + window, REQUIRED tier.** `exposure_policy.EXPOSURE_POLICY[ProgramRole.LAUNDRY]`
  is `(exterior_wall=REQUIRED, window=REQUIRED)` — the same tier as LIVING/BEDROOM/KITCHEN, gated
  closed by C19 (exterior wall) and C8 (window) like any other REQUIRED role. The window is sized
  at a SERVICE-window minimum, narrower than a habitable room's: `windows.py::
  LAUNDRY_WINDOW_MIN_WIDTH_M` (0.6 m, vs 0.9 m for LIVING/BEDROOM/…), `LAUNDRY_WINDOW_MAX_WIDTH_M`
  (1.2 m), `LAUNDRY_WINDOW_WALL_FRACTION` (0.25) — same PLACEHOLDER disclosure as every other
  window constant. Because LAUNDRY is REQUIRED-tier, the SERVICE column/row placement gains the
  same exterior-preference ordering DAYLIGHT roles already had (`_needs_column_end`/
  `_daylight_order` key off `role in DAYLIGHT_ROLES`, which LAUNDRY now derives into) — no separate
  placement code was needed.
- **Machine bay.** `ROOM_TEMPLATES[ProgramRole.LAUNDRY].min_short_side_m` is 1.7 m (was 1.5 m): 0.6 m
  washing machine + 0.6 m optional dryer beside it + 0.5 m circulation — the bay a person can
  actually stand a machine (and dryer) in, not just wide enough to open a door. C3 enforces it on
  every realized room. The `MIN_FURNITURE_ENVELOPE_M[LAUNDRY]` furniture-feasibility screen (C9,
  a WASHING_MACHINE footprint 0.6 m wide with 0.9 m clearance in front, `(0.6, 1.5)`) is now
  satisfied by construction: both sides of a template-conforming room are >= 1.7 m, which
  comfortably inscribes the envelope's own longer side (1.5 m).
- **Door.** Unchanged from Issue #18: LAUNDRY is entered from HALL/CIRCULATION/KITCHEN only
  (`access_rules.ALLOWED_ENTERED_FROM`), via a `SERVICE_DOOR` (0.8 m, `access_rules.
  SERVICE_DOOR_ROLES`), enforced by C24.
- **Refusal.** `app.demo.service._laundry_unplaceable_message` names the failed requirement
  (exterior wall / window / machine bay) and raises `DemoGenerationError("LAUNDRY_UNPLACEABLE", …)`
  from `_finish`, but ONLY when EVERY outline the brief tried failed for a reason naming the
  LAUNDRY zone specifically (C19/C8/C3, or a pre-solve `ROOM_SHAPE_INFEASIBLE` naming the zone) —
  never when an unrelated room or the footprint's own capacity was also in play; those keep their
  existing refusal codes (e.g. `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`) unchanged. A plan is
  never delivered with a windowless or too-narrow laundry room: the same hard validation gate every
  other room is held to.
- **Corpus impact.** The frozen 432-context regression corpus requests no laundry room at all (see
  `spikes/failure_log_sweep/laundry_activation_corpus_check.py`'s own documented reasoning), so
  LOST/GAINED/crashes/status/refusal-code/primary-signature all stayed at 0 there — confirmed by a
  direct sweep (404 planned/28 refused/0 crashed, an exact match to the pre-existing baseline). The
  dedicated 31-cell laundry-requesting matrix (`spikes/failure_log_sweep/
  laundry_activation_matrix.py`) went from 29/31 to 28/31 planned: one additional context (a 3BR/
  2-wet deep-footprint brief already near its programme's area capacity) is now refused
  `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` rather than delivered, because the larger machine
  bay pushed its total required area over that ceiling — an honest refusal, not a degraded plan,
  and not `LAUNDRY_UNPLACEABLE` (the capacity check runs first). The other 27 planned cells are
  unaffected in outcome; every one of the 28 planned+requested cells' LAUNDRY rooms now also carries
  a verified exterior window and machine bay, which nothing verified before this Issue.

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
  `RoomTemplate` (`min_short_side_m` 1.7, Issue #21), `_LAUNDRY_DEFICIT_SOURCE_ROLES`,
  `_laundry_deficit_targets`, `_ROW_RESCUE_ROLES`.
- `app/demo/contract.py`: `QualityOut.laundry_notice`, `LAUNDRY_REDISTRIBUTION_NOTICE_RATIO`,
  `_LAUNDRY_NOTICE_EXCLUDED_ROLES`, `_laundry_redistribution_notice`.
- Issue #21 (guaranteed semantics): `app/vertical_slice/exposure_policy.py`
  (`EXPOSURE_POLICY[ProgramRole.LAUNDRY]`), `app/vertical_slice/windows.py`
  (`LAUNDRY_WINDOW_MIN_WIDTH_M`/`_MAX_WIDTH_M`/`_WALL_FRACTION`), `app/vertical_slice/
  geometry_core/model.py` (`MIN_FURNITURE_ENVELOPE_M[LAUNDRY]`, unchanged value, updated
  reasoning), `app/demo/service.py` (`_laundry_unplaceable_message`, `_LAUNDRY_REQUIREMENT_CHECKS`,
  wired into `_finish`). Door/access unchanged from Issue #18
  (`app/vertical_slice/access_rules.py`).
- Commits (`worktree-015-laundry-room-option`, merged via `b678967`): `b3a1161` (feasibility
  review), `c8020d4` (phase 1, gated off), `64453c8` (row-rescue narrowing fix, restored 0/404),
  `ec672a8` (area-budget investigation, measurement only), `27fabb5` (activation — service-first
  allocation + disclosure notice), `5261b0b` (corpus-count fix + activation e2e smoke),
  `a1dd3a8` (SAFE_ROOM notice false-positive fix), `da5b007` (SAFE_ROOM regression test).
- Integration: `b678967` (Laundry into a fresh branch off then-current `main`), `3d8b924` (current
  `main` at the time, through the Knowledge Wiki-first/RAG-hybrid pivot, merged in — zero file
  overlap, no conflicts), `6499604` (fast-forwarded onto `main` — no merge commit, linear history).
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
- `laundry_notice` is informational only — it never blocks generation and has no refusal threshold;
  Issue #21's `LAUNDRY_UNPLACEABLE` is a separate, unrelated refusal (a hard gate on exterior
  wall/window/bay, never on realized area) — the two do not interact.
- LAUNDRY is REQUIRED/REQUIRED in `EXPOSURE_POLICY` (Issue #21) — a delivered laundry room always
  has an exterior wall and a real window; a brief that cannot deliver both, together with the 1.7 m
  machine bay, is refused `LAUNDRY_UNPLACEABLE` rather than delivered incomplete.
- Real-corpus validation: 0/404 previously-planned briefs changed by the row-rescue narrowing
  (Phase 1); 404/432 distinct-context match confirmed at activation (`docs/
  LAUNDRY_ROOM_ACTIVATION_REPORT.md`) — 432 distinct contexts is the reconciled, current
  denominator (750 raw → 472 reproducible → 432 distinct; 404 planned / 28 refused / 0 crashed).
  At `6499604` itself this full sweep had not yet been re-run (release validation used focused
  Laundry tests plus the full backend suite instead); it has since been run directly, at Issue
  #21's own HEAD — same 404/28/0 result, confirming the corpus (which requests no laundry room at
  all) is unaffected by that Issue's changes too — see Current behavior above.

## Supersedes

N/A — first implementation of this capability; nothing prior existed on `main`.

## Known follow-ups

- BATHROOM's own row-rescue eligibility — a separate, already-in-motion decision (the row-sharing
  quality initiative), deliberately not addressed here.
- Wiring `laundry_notice` (and an explicit laundry toggle) into the ReviewPage/product surface —
  not started, same status as Multi-Level Phase 1's product wiring.
- The full frozen 432-context corpus regression sweep is now run routinely (Issue #21 confirms it
  is unaffected — see Current behavior above); the historical "not yet run" note above this line
  is superseded.

## Evidence/history

`docs/LAUNDRY_ROOM_OPTION_REVIEW.md` (feasibility review), `docs/LAUNDRY_ROOM_PHASE1_REPORT.md`
(phase 1 measurement + row-rescue narrowing), `docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md`
(allocation-policy measurement, four candidates A–D), `docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md`
(activation matrix, corpus-count reconciliation, SAFE_ROOM fix).

## Last verified against git

`6499604aeda6b5b044398308ffd9fd2334b755b4` — `main` HEAD, after `integration/laundry-into-main`
was fast-forwarded onto `main` (no merge commit; `main` and the integration branch tip are
identical at this commit). `LAUNDRY_ROOM_ENABLED = True`, `_ROW_RESCUE_ROLES`,
`_LAUNDRY_NOTICE_EXCLUDED_ROLES`, and `_QUALITY_TIER_GROUP` (LAUNDRY absent) all confirmed present
by direct `grep` against `main` at this commit; focused Laundry tests (170) and the full backend
suite (1376 passed, 4 pre-existing/unrelated failures — see the Knowledge System page) ran clean
against this history before the fast-forward.

`backend/app/knowledge/doc_status.json`'s entry for this page has gone through two corrections: it
previously read `capability_status: NOT_IMPLEMENTED` even after this page was first rewritten
(that table is a hand-curated authoritative source, deliberately not derived from a page's own
prose — see `docs/wiki/architecture/knowledge-system.md` — so editing this page alone never
updates it), corrected then to `capability_status: IMPLEMENTED` with `branch:
integration/laundry-into-main`, `merged_to_main: false`; now corrected again to `branch: main`,
`merged_to_main: true`, `commit: 6499604`, reflecting the actual fast-forward onto `main`.

**Issue #21 (guaranteed semantics, 2026-09-18)**, branch `agent/21-laundry-room-semantics-an-
enclosed-room`, based on `origin/integration/holiday-yom-kippur-2026` (which already carries
Issues #18/#19, doors and windows/exposure): `EXPOSURE_POLICY[LAUNDRY]` REQUIRED/REQUIRED,
`min_short_side_m` 1.7, `_laundry_unplaceable_message`/`LAUNDRY_UNPLACEABLE` all confirmed present
by direct `grep` at this session's own HEAD. Verified by this session's own test runs: the full
`tests/vertical_slice/test_laundry_room.py` (30 tests) and `tests/test_laundry_activation_e2e.py`
(16 tests), `tests/vertical_slice/test_concept_generator.py`'s template snapshot, and a direct
sweep of the frozen 432-context corpus (`spikes/failure_log_sweep/corpus_snapshot.py`: 404
planned/28 refused/0 crashed, unchanged) plus the 31-cell laundry-requesting activation matrix
(`spikes/failure_log_sweep/laundry_activation_matrix.py`: 28/31 planned, one new capacity refusal
— see Current behavior above) — not independently re-verified beyond this session.
