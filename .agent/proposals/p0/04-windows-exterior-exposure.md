# [agent] Windows and exterior exposure: exposure check decoupled from window fit (C19), a declared exposure policy per room type, window placement report

### Goal

Windows are a real planning constraint: the rules say which room types must touch an exterior
wall and which must have a window, the validator checks each rule separately (an interior room
is a planning error; a too-short exterior wall is a window-sizing error), the policy covers every
room type instead of a subset, and every plan reports which rooms got a window on which wall.

### Current behavior

Windows are a backend stage (`backend/app/vertical_slice/windows.py::generate_windows`): every
zone in `DAYLIGHT_ROLES = {LIVING, DINING, KITCHEN, BEDROOM, MASTER_BEDROOM, SAFE_ROOM}` gets one
window centered on its widest exterior wall (`geometry_adapter.envelope_sides`), sized by
placeholder constants self-documented as "PARAMETER · UNVERIFIED"; BATHROOM/TOILET get a
best-effort smaller window that never gates; FAMILY_ROOM, STUDY, DRESSING_ROOM, LAUNDRY, STORAGE,
CIRCULATION are skipped entirely. The only gate is C8 ("daylight/window exposure present where
required"), which conflates "touches an exterior wall" with "a window of minimum width fits", so
a bedroom on an exterior wall that is 0.8 m long fails the same way as an interior bedroom. The
measurement script's M2 counts STUDY and FAMILY as habitable — broader than C8. Both renderers
draw only backend windows.

### Required behavior

1. `backend/app/vertical_slice/exposure_policy.py`: a typed table per `ProgramRole` with
   `exterior_wall: REQUIRED | PREFERRED | NONE` and `window: REQUIRED | PREFERRED | NONE`. Default
   policy (owner's decision recorded in the contract): REQUIRED/REQUIRED for LIVING, DINING,
   KITCHEN, BEDROOM, MASTER_BEDROOM, SAFE_ROOM, FAMILY_ROOM, STUDY; PREFERRED/PREFERRED for
   BATHROOM, TOILET, DRESSING_ROOM; NONE for HALL, CIRCULATION, STORAGE. (LAUNDRY is set by the
   Laundry Issue.) `DAYLIGHT_ROLES` and `WET_ROOM_PREFERRED_ROLES` are derived from this table.
2. New check C19 "required rooms touch an exterior wall" (uses `envelope_sides` only) — separate
   from C8, which keeps meaning "a window of at least the minimum width is placed where required".
   Both fail closed. C19 runs before C8 so a refusal names the real cause.
3. `generate_windows` handles every role in the table (PREFERRED roles best-effort, REQUIRED roles
   gated), records `ventilation_status` for all of them, and places the window on the longest
   exterior segment not shared with a declared seam.
4. `QualityOut` gains an additive `exposure` report per room: exterior sides, window side/width or
   the reason none was placed. The placeholder sizing constants stay as they are, flagged in the
   Wiki as still unverified.
5. Because FAMILY_ROOM and STUDY become REQUIRED, corpus contexts that only plan by leaving such a
   room interior may now refuse: they are listed in the PR with the room and the wall situation;
   LOST is budgeted at 0 — if any context is lost, the PR must propose the planner-side fix as a
   PROPOSED FOLLOW-UP and the owner decides before merge (the contract's `LOST: 0` is not relaxed
   by the worker).

### Acceptance Criteria

- AC-1: `exposure_policy.py` defines the table and `windows.py` derives `DAYLIGHT_ROLES` and `WET_ROOM_PREFERRED_ROLES` from it
- AC-2: C19 fails on a fixture with an interior BEDROOM and passes on the canonical fixtures; C8 still fails on an exterior bedroom whose wall is shorter than the minimum window
- AC-3: FAMILY_ROOM and STUDY rooms get windows on the corpus contexts that contain them (fixture test + regression report)
- AC-4: every PLANNED demo design carries `QualityOut.exposure` with one entry per room
- AC-5: corpus LOST=0, no primary-signature changes; any FAMILY_ROOM/STUDY context that would be lost is listed in the PR as a PROPOSED FOLLOW-UP instead of merged
- AC-6: the Wiki page documents the exposure policy table, C19 vs C8, and the unverified sizing constants

### Out of scope

Window sizing/glazing ratios from regulation, orientation/solar reasoning (P2), balconies, the
LAUNDRY policy (own Issue), renderer changes, ReviewPage.

### Affected domains

backend, geometry, validator, knowledge

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

#17

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> grep:backend/app/vertical_slice/exposure_policy.py:FAMILY_ROOM ; grep:backend/app/vertical_slice/windows.py:exposure_policy
- AC-2 -> pytest:backend/tests/vertical_slice/test_exposure_policy.py::test_c19_fails_on_interior_bedroom_and_passes_on_canonical_fixtures ; pytest:backend/tests/vertical_slice/test_exposure_policy.py::test_c8_still_fails_when_the_exterior_wall_is_too_short
- AC-3 -> pytest:backend/tests/vertical_slice/test_exposure_policy.py::test_family_room_and_study_get_windows ; regression:corpus
- AC-4 -> pytest:backend/tests/test_demo_quality.py
- AC-5 -> regression:corpus ; review:the PR lists every FAMILY_ROOM/STUDY context affected and proposes the planner-side fix as a follow-up rather than relaxing LOST
- AC-6 -> grep:docs/wiki/architecture/geometry-validation.md:C19

### Regression budget

LOST: 0
GAINED: 0
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (exposure policy, C19/C8 split, unverified constants).

### Knowledge check

Consulted: `app/vertical_slice/windows.py` (DAYLIGHT_ROLES, best-effort wet-room windows,
unverified sizing constants), `app/vertical_slice/geometry_adapter.py::envelope_sides`,
validation C8, `docs/GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`, `specs/007-wet-room-semantics/`,
M2 in `quality_metrics.py`. What exists: a real window stage with one conflated gate. What
remains (this Issue): a per-role exposure policy covering every room type, C19 (exterior wall)
separated from C8 (window fit), FAMILY_ROOM/STUDY policy, per-room exposure report. Follow-ups:
regulation-sourced glazing ratios (P2 compliance), orientation/solar (P2).
