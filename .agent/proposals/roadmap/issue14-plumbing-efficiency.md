# [agent] Plumbing / wet-core efficiency: a soft preference for shared wet walls, bathroom clustering and kitchen proximity, with an estimated plumbing complexity

### Goal

Add a SOFT architectural/engineering preference for efficient wet-service organization — shared wet walls,
bathroom clustering, kitchen/wet-room proximity where sensible, vertical alignment later, an estimated plumbing
complexity — as a quality/cost preference, never a hard constraint.

### Current behavior

M5 measures wet adjacency (share of wet rooms adjacent to another wet room) and the quality tier prefers
pairable rows; there is no complexity estimate, no kitchen proximity term, no vertical alignment data.

### Required behavior

1. `backend/app/vertical_slice/wet_core.py`: shared wet walls (length), clusters, kitchen proximity, an
   estimated plumbing complexity index (number of wet stacks/runs), multi-level alignment when levels exist.
2. A non-blocking ranking preference and `QualityOut.metrics` fields; no new blocking check.
3. Rubric section J signals documented.

### Acceptance Criteria

- AC-1: the wet-core record is computed for the canonical fixtures and a two-level fixture
- AC-2: the ranking prefers the clustered sibling on a two-candidate fixture; no candidate is refused for wet-core reasons
- AC-3: corpus regression: LOST 0; no status changes

### Out of scope

Fixture placement (Issue 9), privacy (Issue 6), real plumbing engineering.

### Affected domains

backend, geometry, qa, knowledge

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

#37

### Required locks

geometry-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_wet_core.py::test_records_for_canonical_and_two_level_fixtures
- AC-2 -> pytest:backend/tests/vertical_slice/test_wet_core.py::test_ranking_prefers_clustered_and_never_refuses
- AC-3 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/quality_rubric.md (J), docs/wiki/features/wet-rooms.md.

### Knowledge check

Consulted: `quality_metrics.py` M5, wet-rooms Wiki page, multi-level Phase 1 notes (stair seat coupling). Depends on Issue 6.
