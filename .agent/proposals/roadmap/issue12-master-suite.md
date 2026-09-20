# [agent] Master-suite access and privacy: bedroom, ensuite and wardrobe relationships with sensible access, privacy and routes — no single mandated arrangement

### Goal

Bedroom / ensuite / wardrobe relationships have sensible access and privacy: ensuite access, door placement,
privacy from circulation, wardrobe relationship, no unnecessary exit/re-entry, no awkward routes — without
requiring one universal arrangement.

### Current behavior

The ensuite is hosted by its bedroom (`entered_from`, quality tier 'one ensuite = one pairable row'); nothing
evaluates door placement inside the suite, the wardrobe relationship, sight lines from the corridor into the
bedroom/ensuite, or awkward routes (bedroom door → ensuite door through the bed's clearance).

### Required behavior

1. `backend/app/vertical_slice/master_suite.py`: per master suite a record — ensuite access (direct / via
   corridor), door placement relative to the bed zone and wardrobe, privacy (sight line from the hall through
   the bedroom door to the bed / ensuite door), wardrobe relationship (in room / dressing room / none), route
   quality (path bedroom door → ensuite → wardrobe without crossing the bed clearance).
2. A suite quality score in the ranking (non-blocking); hard failure only for an ensuite reachable solely
   through another private room (already C24) — no new blocking rule.
3. Rubric section M signals documented.

### Acceptance Criteria

- AC-1: the record is computed for the canonical master suite and for a dressing-room fixture, from realized geometry and layout objects
- AC-2: a fixture where the ensuite door forces a route across the bed clearance scores lower than its sibling and the ranking prefers the sibling
- AC-3: corpus regression: LOST 0; no status changes

### Out of scope

Ensuite hosting rules (#18/C24), wet-room privacy (Issue 6) beyond the suite.

### Affected domains

backend, geometry, qa, knowledge

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

#37, #38

### Required locks

geometry-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_master_suite.py::test_records_for_canonical_and_dressing_room_fixtures
- AC-2 -> pytest:backend/tests/vertical_slice/test_master_suite.py::test_ranking_prefers_the_better_route
- AC-3 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/quality_rubric.md (M), docs/wiki/features/wet-rooms.md (ensuite notes).

### Knowledge check

Consulted: memory 'row-sharing-topology-limit-and-quality-tier' (one ensuite per pairable row), `concept_generator` entered_from for ensuites, Issue #18 (C24). Depends on Issues 6 and 4 for door/privacy data.
