# [agent] Public-zone composition: kitchen, dining and living as a coherent composition — relationships, entrance, exposure and circulation paths evaluated without penalizing openness

### Goal

Kitchen + dining + living form a coherent architectural composition rather than three rectangular strips:
kitchen↔dining, dining↔living, entrance and outdoor/window relationships, furniture circulation and paths
crossing furniture zones are evaluated; open plan is valid and never penalized as such.

### Current behavior

M6 reports whether the public zone is contiguous; the hub parti and the strip-room quality tier shape public
rooms; `_open_corridor_to_public` opens the hall↔LDK wall visually. Nothing evaluates the kitchen–dining–living
relationships, the entrance's relation to the public zone, or circulation paths crossing furniture zones.

### Required behavior

1. `backend/app/vertical_slice/public_composition.py`: from realized geometry and the layout objects —
   kitchen↔dining adjacency/opening, dining↔living relation, entrance→public path, window/outdoor relation of
   the living zone, circulation paths crossing furniture zones (path from entrance/hall to each public room vs
   sofa/dining clearances), zoning coherence.
2. A composition score joins the candidate ranking (non-blocking); hard failures only for a public room
   reachable solely through a furniture zone with no path (C31).
3. Rubric section D signals documented.

### Acceptance Criteria

- AC-1: the composition record is computed on the canonical fixtures and on an open-plan fixture, and the open-plan fixture is not penalized for openness
- AC-2: a fixture whose only path to the living room crosses the dining table's clearance fails C31; the canonical fixtures pass
- AC-3: corpus regression: LOST 0; primary changes listed and composition-driven only

### Out of scope

Furniture placement (Issue 9), kitchen fixture policy, outdoor spaces (roadmap topic).

### Affected domains

backend, geometry, validator, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#39

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_public_composition.py::test_open_plan_is_not_penalized
- AC-2 -> pytest:backend/tests/vertical_slice/test_public_composition.py::test_c31_fails_path_only_through_furniture ; grep:backend/app/vertical_slice/validation.py:C31
- AC-3 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 30

### Expected documentation changes

docs/architecture_reference/quality_rubric.md (D), docs/wiki/architecture/geometry-validation.md (C31).

### Knowledge check

Consulted: `quality_metrics.py` M6, `hub_guard`, `app/demo/contract.py::_open_corridor_to_public`, memory 'strip-rooms-root-cause-and-fix-cost'. Depends on Issue 9 (layout objects).
