# [agent] Circulation efficiency: dedicated-circulation metrics from realized geometry, deterministic penalty for extreme corridors, valid corridors preserved

### Goal

Prevent excessive dedicated circulation (very long, high-area corridors) without penalizing corridors as
such: measure corridor area/length/dead ends/turns/duplication from realized geometry, fail or penalize only
extreme cases deterministically, prefer branching/compact circulation nodes and shared transition zones.

### Current behavior

Circulation is measured only as M3 `circulation_share` (hall area / built area) and M4 hall door count /
aspect in `quality_metrics.py`; C14 checks corridor width against the request; nothing measures corridor
length, dead ends, turns or duplicated circulation, and no check or ranking term penalizes an extreme
corridor. In the spine parti the hall spans the full depth by construction (`concept_generator._concept_from`),
so long corridors are common; the hub parti was introduced to fix corridor proportion, not to measure it.

### Required behavior

1. `backend/app/vertical_slice/circulation_metrics.py`: from realized geometry — dedicated circulation area
   and ratio, corridor segment lengths (longest segment, total), dead-end count (corridor cells with a single
   open neighbour and no door), turn count along the entrance→farthest-room path, duplicated circulation
   (parallel corridor segments serving the same rooms), width×length extremes. Pure, deterministic, unit-tested
   on fixtures (spine, hub, L partis).
2. Thresholds as named PARAMETER constants with rationale: an `extreme corridor` is one where ratio, longest
   segment or dead-end count exceed the documented limits (calibrated on the corpus distribution so that
   today's median plans pass).
3. New check C26 "no extreme dedicated circulation" fails closed only for extreme cases; a non-blocking
   `circulation_quality` term joins the candidate ranking (hub_guard-style) so compact/branching circulation is
   preferred among otherwise-valid candidates. Valid corridor-based plans stay supported.
4. `QualityOut.metrics` gains the circulation fields; the rubric section B lists them.

### Acceptance Criteria

- AC-1: `circulation_metrics.measure(design)` returns area, ratio, longest segment, total length, dead ends, turns and duplication for the canonical fixture, from realized geometry only
- AC-2: a long-corridor fixture is classified extreme and C26 fails it; the canonical fixtures and a compact-hub fixture pass
- AC-3: the candidate ranking prefers the compact-circulation sibling on a two-candidate fixture without changing any corpus primary unexpectedly
- AC-4: no coordinate literal or fixture-name branch appears in the new modules
- AC-5: corpus regression: LOST 0, every primary-signature change is listed and classified as expected (extreme corridor replaced) or unexpected (must be 0)

### Out of scope

Entrance sequence (Issue #22 / #20), dead-space pockets (dead-space Issue), corridor width policy (C14), furniture.

### Affected domains

backend, geometry, validator, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#29

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_circulation_metrics.py::test_measures_from_realized_geometry_on_the_canonical_fixture
- AC-2 -> pytest:backend/tests/vertical_slice/test_circulation_metrics.py::test_c26_fails_an_extreme_corridor_and_passes_compact_plans ; grep:backend/app/vertical_slice/validation.py:C26
- AC-3 -> pytest:backend/tests/vertical_slice/test_circulation_metrics.py::test_ranking_prefers_compact_circulation ; regression:corpus
- AC-4 -> review:the diff of circulation_metrics.py and the C26 check contains no coordinate literals or fixture-name branches ; static:backend-import
- AC-5 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 40

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (C26, metrics, thresholds), docs/architecture_reference/quality_rubric.md (section B signals).

### Knowledge check

Consulted: `quality_metrics.py` (M3/M4), `validation.py` (C14), `concept_generator._concept_from` / `_hub_concept` docstrings (corridor proportion history), `docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md`. What exists: share and aspect metrics. What remains: length/dead-end/turn/duplication metrics, the extreme-case check, the ranking term.
