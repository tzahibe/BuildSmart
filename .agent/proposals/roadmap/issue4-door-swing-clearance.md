# [agent] Door placement, swing and clearance validation: door–wall, door–door, door–fixture and circulation conflicts, authoritative swing in the renderer

### Goal

Doors are physically and functionally usable: no door–wall, door–door or door–fixture conflicts, a usable
swing direction, the required access width, and no obstruction of circulation; the renderer draws exactly the
engine's placement and swing.

### Current behavior

`doors.py::Door` already carries `swings_into` and `hinge_at` decided by the engine, and C7 checks
placeability (clearance from corners on the shared wall). Issue #18 adds the access-topology rules and C24.
Nothing checks two doors swinging into each other, a door swinging into a fixture or a furniture envelope, the
clear opening width against the access requirement, or a door leaf blocking a corridor; the frontend's door
symbol is drawn from `DoorOut` without a swing arc contract test.

### Required behavior

1. `backend/app/vertical_slice/door_clearance.py`: swing envelope per door (quarter circle from `hinge_at`,
   width, `swings_into`); conflicts: door–door (overlapping swing envelopes or leaves colliding in a corner),
   door–fixture (envelope intersects a wet-room fixture footprint from `wet_rooms`/fixture data), door–furniture
   (when a furniture layer exists, Issue 9 — optional now), door–wall (leaf cannot open ≥ 90° because of an
   adjacent perpendicular wall within the leaf's width), corridor obstruction (leaf reduces a corridor below
   the C14 width when open); required access width per role (0.9 m rooms / 0.8 m service / 1.0 m entrance from
   #18's table).
2. New check C28 "doors usable" (fails closed: door–door, door–wall, door–fixture, access width) and a
   non-blocking quality note for corridor obstruction. The engine chooses the swing to avoid conflicts before
   failing (flip `swings_into`/`hinge_at` deterministically), so valid plans keep passing.
3. `DoorOut` exposes `swings_into`, `hinge` and `swing_deg`; the frontend draws the arc from those fields only
   (contract test with a fixture snapshot).

### Acceptance Criteria

- AC-1: door_clearance detects each conflict class on hand-built fixtures and reports none on the canonical fixtures
- AC-2: C28 fails a fixture with two doors colliding in a corner and one with a door swinging into a toilet fixture; the engine's swing choice resolves the resolvable cases first
- AC-3: DoorOut carries hinge/swing fields for every door of every PLANNED corpus design and the frontend renders the arc from them
- AC-4: corpus regression: LOST 0; primary-signature changes only where a swing flip changed a door (listed)

### Out of scope

Furniture layer itself (Issue 9), door styling, regulation clear-width rules (compliance corpus).

### Affected domains

backend, geometry, validator, frontend, qa, knowledge

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

#18

### Required locks

geometry-core (exclusive), validator-core (exclusive), frontend-review (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_door_clearance.py::test_conflict_classes_on_fixtures_and_none_on_canonical
- AC-2 -> pytest:backend/tests/vertical_slice/test_door_clearance.py::test_c28_fails_door_door_and_door_fixture_and_engine_flips_swing_first ; grep:backend/app/vertical_slice/validation.py:C28
- AC-3 -> pytest:backend/tests/test_demo_p0.py::test_every_door_out_carries_hinge_and_swing ; vitest:frontend/src/components/plan/DoorSymbol.test.tsx
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 20

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (C28, swing policy), frontend plan docs.

### Knowledge check

Consulted: `doors.py` (Door.swings_into/hinge_at — engine-owned already), `validation.py` C7, Issue #18 contract (C24, door kinds/widths), `contract.py` DoorOut. What exists: engine-decided swing, placeability. What remains: conflict detection, C28, frontend arc from authoritative fields.
