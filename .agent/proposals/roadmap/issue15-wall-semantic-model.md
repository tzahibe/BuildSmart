# [agent] Wall semantic model: EXTERIOR / INTERIOR / WET-SERVICE / PROTECTED wall classes carried from geometry to contract and renderer

### Goal

Walls are represented semantically (class, thickness, what they host: doors, windows, fixtures) rather than
only visually, as the base for compliance, fixtures and technical drawing output — without claiming structural
engineering the system does not perform.

### Current behavior

`geometry_core.engine.WallMap` types wall sides (PARTITION / OPEN / exterior via `envelope_sides`), the demo
contract emits `WallSegment`s with a construction type and boundary context, and `RoomOut.walls` carries
per-side construction/boundary/window eligibility. There is no wall class enum covering WET/SERVICE or
PROTECTED (safe room), no per-wall thickness policy, and no single wall list that doors/windows/fixtures
reference by id.

### Required behavior

1. `backend/app/vertical_slice/walls.py`: `Wall(id, class=EXTERIOR|INTERIOR|WET_SERVICE|PROTECTED, thickness_m,
   segment, hosts: [door ids, window ids, fixture ids], zones)` derived from the realized geometry (safe-room
   walls PROTECTED, wet-room shared walls WET_SERVICE, envelope EXTERIOR, else INTERIOR); a `structural_candidate`
   flag only where a later engine sets it — documented as not engineering.
2. The contract emits `walls: [WallOut]` and doors/windows reference wall ids; the renderer draws thickness by
   class from the contract; `RoomOut.walls` stays for compatibility.
3. C33 asserts every door/window sits on a wall that hosts it and that safe-room walls are PROTECTED.

### Acceptance Criteria

- AC-1: walls are classified for the canonical fixtures (exterior count equals the envelope sides; safe-room walls PROTECTED; wet shared walls WET_SERVICE)
- AC-2: every door and window of every PLANNED corpus design references a hosting wall id (C33 green)
- AC-3: the frontend draws wall thickness from the contract's class (snapshot test); corpus regression: LOST 0, no status/primary changes

### Out of scope

Structural engineering, DXF output, compliance rules.

### Affected domains

backend, geometry, validator, frontend, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#38, #19

### Required locks

geometry-core (exclusive), validator-core (shared), frontend-review (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_walls.py::test_classes_on_canonical_fixtures
- AC-2 -> pytest:backend/tests/test_demo_quality.py::test_every_door_and_window_hosts_on_a_wall ; grep:backend/app/vertical_slice/validation.py:C33 ; regression:corpus
- AC-3 -> vitest:frontend/src/components/plan/Walls.test.tsx ; regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (wall model, C33), docs/wiki/features/interior-layout.md.

### Knowledge check

Consulted: `geometry_core/engine.py` WallMap, `app/demo/contract.py` WallSegment/_open_corridor_to_public, `RoomOut.walls`. Depends on Issue 4 and #19.
