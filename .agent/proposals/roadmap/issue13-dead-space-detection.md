# [agent] Dead space / residual pocket detection: entrance pockets, slivers, corridor-end voids and leftover regions measured by size, shape, accessibility and ownership

### Goal

Detect geometry that belongs to the plan but has no useful architectural function — entrance pockets, narrow
leftover strips, unusable corners, corridor-end voids, leftover regions between rooms, oversized transition
areas — measured by size, shape, accessibility, functional ownership and relation to circulation, without
treating every open transition area as dead space.

### Current behavior

C2 guarantees no residual area OUTSIDE rooms (every cell belongs to a zone), so `dead_space_m2` is 0 by
construction in `quality_metrics.py`. Dead space INSIDE zones — a corridor stub past the last door, a sliver of
a room behind a door, an oversized hall — is not measured; Issue #22 adds the entrance pocket case only.

### Required behavior

1. `backend/app/vertical_slice/dead_space.py`: per zone, residual regions computed from realized geometry and
   layout objects/door swings — corridor cells beyond the last opening (stub), room regions narrower than a
   usable width (sliver), corners unreachable behind swings, hall area above a transition-node budget;
   each with area, shape (aspect), accessibility (reachable from a door) and ownership (zone, role).
2. Thresholds as PARAMETER constants calibrated on the corpus; a `dead_space_m2` and `dead_space_share` in
   `QualityOut.metrics` (replacing the constant 0), a ranking penalty, and C32 fails closed only for a residual
   region above the hard limit (e.g. a corridor stub ≥ 1.5 m).
3. Rubric section K signals documented.

### Acceptance Criteria

- AC-1: dead_space finds the stub on a corridor-stub fixture, the sliver on a sliver fixture and nothing on the canonical fixtures; an open transition hall within budget is not flagged
- AC-2: C32 fails the stub fixture and passes the canonical fixtures; QualityOut.metrics reports the measured dead space
- AC-3: corpus regression: LOST 0; primary changes listed and dead-space-driven only

### Out of scope

Entrance pocket rule (#22 owns C25), circulation metrics (Issue 1).

### Affected domains

backend, geometry, validator, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#36, #22

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_dead_space.py::test_finds_stub_and_sliver_not_transition_hall
- AC-2 -> pytest:backend/tests/vertical_slice/test_dead_space.py::test_c32_fails_stub_fixture_and_passes_canonical ; grep:backend/app/vertical_slice/validation.py:C32
- AC-3 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 30

### Expected documentation changes

docs/architecture_reference/quality_rubric.md (K), docs/wiki/architecture/geometry-validation.md (C32, metrics).

### Knowledge check

Consulted: `validation.py` C2, `quality_metrics.py` (`dead_space_m2 = 0 by C2`), Issue #22 (entrance pocket). Depends on Issues 1 and #22.
