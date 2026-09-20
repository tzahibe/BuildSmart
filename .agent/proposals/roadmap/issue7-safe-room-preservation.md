# [agent] SAFE_ROOM / MAMAD requirement preservation: the authoritative requirement survives requirement → constraint → concept → geometry → validator → renderer, never silently dropped

### Goal

When SAFE_ROOM/MAMAD is an authoritative project requirement it survives the whole pipeline as a typed
constraint and is proven present at every stage; a silent disappearance is a failure, never a warning.
Compliance applicability stays separate — no brief is assumed to carry the legal requirement automatically.

### Current behavior

SAFE_ROOM flows through `requirements/parser.py` (safe_room flag), `spec.py` (ProgramRoom SAFE_ROOM),
`concept.py`/`concept_generator.py` (a SAFE_ROOM room), `geometry_adapter.py` and C4 ("safe room valid: RC
envelope + regulated minimum"), `renderer.py` (label), `hub_guard`/`l_massing_guard` (safe-room aspect term).
There is no single typed constraint object carried end to end, no stage-by-stage assertion that the requirement
is still present (a fallback ladder or a candidate swap could drop the room before C4 sees the design), and
the notice/ReviewPage do not state where the requirement came from (user request vs compliance assumption).

### Required behavior

1. `backend/app/vertical_slice/constraints.py`: `TypedConstraint(kind=SAFE_ROOM, source=USER|COMPLIANCE|NONE,
   authoritative: bool, min_area_m2, ...)` derived once from the requirements; carried on the spec, the concept,
   the realized design and the demo contract (`QualityOut.constraints`).
2. Stage assertions: after concept generation, after geometry realization and in the validator (C4 extended:
   "an authoritative SAFE_ROOM constraint is realized") the constraint's presence is checked; any path that
   drops it (fallback ladder, candidate swap, alternative selection) refuses with `SAFE_ROOM_DROPPED` instead of
   delivering a plan without it.
3. The renderer/contract shows the safe room and the constraint's source; a brief without a safe-room
   requirement never gets one invented (source NONE → no room, no warning about compliance).
4. A pipeline trace test walks a safe-room brief through every stage and asserts the constraint at each.

### Acceptance Criteria

- AC-1: TypedConstraint is derived from the parser output with the correct source for a user-requested safe room, and NONE for a brief without one
- AC-2: removing the safe room at any stage (fixture-injected fault after concept / after geometry / in alternatives) makes the pipeline refuse with SAFE_ROOM_DROPPED
- AC-3: every PLANNED corpus design with a safe-room requirement carries the constraint in QualityOut and the room in the drawing; briefs without it get none
- AC-4: corpus regression: LOST 0, no status changes

### Out of scope

The legal applicability rules (compliance corpus), RC envelope sizing changes, multi-level safe-room placement policy.

### Affected domains

backend, geometry, validator, ai, qa, knowledge

### Risk

HIGH

### Resource class

MEDIUM

### Dependencies

none

### Required locks

planner-core (exclusive), validator-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_safe_room_constraint.py::test_constraint_source_user_and_none
- AC-2 -> pytest:backend/tests/vertical_slice/test_safe_room_constraint.py::test_dropping_the_room_at_any_stage_refuses ; grep:backend/app/demo/service.py:SAFE_ROOM_DROPPED
- AC-3 -> pytest:backend/tests/test_demo_quality.py::test_safe_room_constraint_survives_to_the_contract ; regression:corpus
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (typed constraints, C4 extension, refusal code), docs/wiki/architecture/requirements-parsing.md.

### Knowledge check

Consulted: grep of SAFE_ROOM across requirements/vertical_slice/demo (12 modules), `validation.py` C4, memory 'laundry-room-activation' (a SAFE_ROOM false-positive in the notice was found once — evidence the chain is not asserted), `hub_guard` safe-room aspect term. What remains: typed constraint, stage assertions, refusal, trace test.
