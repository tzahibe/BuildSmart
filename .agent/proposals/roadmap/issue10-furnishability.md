# [agent] Furnishability / usability validation: rooms judged by furniture footprints, clearances, access path, door swing, windows and usable walls — tiered, not blunt

### Goal

Room area alone does not prove room quality: usability is checked from the placed layout objects (Issue 9),
clearance zones, the access path from the door, door swings, windows and usable wall surfaces, with quality
tiers rather than hard failures for preferences.

### Current behavior

Only C9's bounding-box envelope test exists; a 12 m² bedroom that cannot hold a bed, a wardrobe and a walking
path passes as long as the envelope inscribes.

### Required behavior

1. `backend/app/vertical_slice/furnishability.py`: per room a `Usability` record — required objects placed,
   clearance satisfied, access path from the door to each object without crossing another object, usable wall
   length, window not blocked; a tier (GOOD / ACCEPTABLE / POOR / UNUSABLE).
2. UNUSABLE (required object cannot be placed at all) fails closed via a new check C30; POOR is a ranking
   penalty and a QualityOut warning; the tiers are documented with their thresholds (PARAMETER · calibrated on
   the corpus so today's plans keep their status).
3. Rubric section F lists the signals.

### Acceptance Criteria

- AC-1: Usability is computed for every room of the canonical fixtures; a bedroom fixture without room for a bed + wardrobe is UNUSABLE and C30 fails it
- AC-2: a bedroom with the objects placed but no clear path from the door is POOR, not failed
- AC-3: corpus regression: LOST 0, status changes 0; the tier distribution is reported in the PR

### Out of scope

Placement itself (Issue 9), public-zone composition (Issue 11).

### Affected domains

backend, validator, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#39

### Required locks

validator-core (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_furnishability.py::test_unusable_bedroom_fails_c30 ; grep:backend/app/vertical_slice/validation.py:C30
- AC-2 -> pytest:backend/tests/vertical_slice/test_furnishability.py::test_blocked_path_is_poor_not_failed
- AC-3 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/features/interior-layout.md (usability tiers), docs/architecture_reference/quality_rubric.md (F).

### Knowledge check

Consulted: `furniture.py`, C9. Depends on Issue 9's layout objects.
