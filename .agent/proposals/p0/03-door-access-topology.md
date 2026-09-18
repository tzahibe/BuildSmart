# [agent] Door and access-topology rules: every enclosed room has one proper door from circulation, no private-to-private doors, service doors, deterministic check

### Goal

Every room is reachable through a sensible door: private and service rooms open from a hall /
circulation space (or, for an ensuite, from its own bedroom), never from another bedroom or
through a chain of rooms; wet and service rooms get proper service doors; and a deterministic
validation check makes these rules impossible to violate silently on any planner path.

### Current behavior

Interior doors are generated only from the declared `DesiredAccessTopology`
(`backend/app/vertical_slice/doors.py::generate_interior_doors`, one door per DOOR /
CASED_OPENING edge; OPEN_CONNECTION never gets a door — proof P8). The generator
(`concept_generator.py` ~2479–2509) gives every PRIVATE/SERVICE room exactly one edge from the
hall/circulation, or from `entered_from` for an ensuite hosted by its bedroom, so bedroom-to-
bedroom doors and room chains do not occur today — by omission only: no validation check would
catch such an edge if a new planner path emitted one (C13 verifies declared edges are realized,
C17 bathroom access per requirements, C6 no artificial doors in open-plan, C7 placeability).
There is no explicit role-pair rule, no distinction between a room door and a service door, and
no check that every enclosed room has at least one door.

### Required behavior

1. A typed door-rule table `backend/app/vertical_slice/access_rules.py`: for each `ProgramRole`
   the allowed "entered from" role sets (PRIVATE rooms: HALL/CIRCULATION, plus the hosting bedroom
   for an ensuite BATHROOM; SERVICE rooms LAUNDRY/STORAGE: HALL/CIRCULATION/KITCHEN; wet rooms:
   HALL/CIRCULATION or hosting bedroom; public rooms: any public/circulation room). Door kinds:
   `ROOM_DOOR` 0.9 m, `SERVICE_DOOR` 0.8 m (LAUNDRY, STORAGE, TOILET), `ENTRANCE_DOOR` 1.0 m.
2. A new validation check C24 "access topology obeys the door rules": every enclosed (non-open)
   room has ≥ 1 DOOR/CASED_OPENING edge; every edge's role pair is allowed by the table; no
   PRIVATE→PRIVATE edge except the ensuite host; no room is reachable from the entrance only
   through another PRIVATE room (chain detection over the realized access graph). Fails closed.
3. `generate_interior_doors` uses the door kind's width; existing widths for ROOM/ENTRANCE doors
   are unchanged so no realized geometry moves; SERVICE_DOOR applies only to LAUNDRY, STORAGE and
   TOILET doors.
4. C24 passes on every currently planning corpus context (the rules are additive) and the two
   negative fixtures (bedroom→bedroom door; room reachable only through a bedroom) fail it.

### Acceptance Criteria

- AC-1: `access_rules.py` defines the allowed entered-from roles per role and the three door kinds with widths; `generate_interior_doors` reads widths from it
- AC-2: C24 fails on a fixture with a BEDROOM→BEDROOM DOOR edge and on a fixture whose only path to a room passes through a bedroom, and passes on the canonical fixtures
- AC-3: every enclosed room in every planning corpus context has at least one door edge (C24 green corpus-wide; report lists any exceptions instead of relaxing the rule)
- AC-4: TOILET/LAUNDRY/STORAGE doors are 0.8 m wide and ROOM/ENTRANCE door widths are unchanged (unit test on `Door.width_m` per kind)
- AC-5: corpus outcomes and primary signatures unchanged except door widths on service doors (doors are not part of the room signature)
- AC-6: the Wiki page documents the door-rule table and C24

### Out of scope

Door swing direction changes, furniture clearance around doors, open-plan interfaces (C6/P8),
entrance placement (own Issue), corridor width (C14), any generator re-ranking.

### Affected domains

backend, geometry, validator, knowledge

### Risk

HIGH

### Resource class

MEDIUM

### Dependencies

#17

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> grep:backend/app/vertical_slice/access_rules.py:SERVICE_DOOR ; grep:backend/app/vertical_slice/doors.py:access_rules
- AC-2 -> pytest:backend/tests/vertical_slice/test_access_rules.py::test_c24_rejects_bedroom_to_bedroom_door ; pytest:backend/tests/vertical_slice/test_access_rules.py::test_c24_rejects_a_room_reachable_only_through_a_bedroom ; pytest:backend/tests/vertical_slice/test_access_rules.py::test_c24_passes_on_canonical_fixtures
- AC-3 -> regression:corpus ; review:the PR states that C24 is green on every planning corpus context and lists exceptions, if any, without relaxing the rule
- AC-4 -> pytest:backend/tests/vertical_slice/test_access_rules.py::test_service_doors_are_narrower_and_room_doors_unchanged
- AC-5 -> regression:corpus
- AC-6 -> grep:docs/wiki/architecture/geometry-validation.md:C24

### Regression budget

LOST: 0
GAINED: 0
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (door-rule table, door kinds, C24).

### Knowledge check

Consulted: `docs/REALIZED_CONNECTIVITY_INVARIANT_REPORT.md` (C13), `docs/ROOM_RELATIONSHIP_IMPLEMENTATION_REPORT.md`,
`docs/GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md`, `app/vertical_slice/doors.py`,
`app/vertical_slice/concept_generator.py` (edge generation ~2479–2509), validation C6/C7/C13/C17.
What exists: declared-topology doors, realizability and open-plan proofs. What remains (this
Issue): an explicit role-pair door rule table, door kinds/widths, a fail-closed check (C24) for
private-to-private doors, room chains and doorless enclosed rooms.
