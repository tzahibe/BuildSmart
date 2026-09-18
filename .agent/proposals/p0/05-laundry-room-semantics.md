# [agent] Laundry room semantics: an enclosed room with its own door, a usable machine bay, and a mandatory exterior window

### Goal

The definition already decided for the laundry room is guaranteed by the generator and the
validator, not assumed: an enclosed room a person can enter, with its own door from circulation
or the kitchen, a usable bay for a washing machine (and dryer) with clearance, and an exterior
wall with a window — a laundry brief that cannot be given all of that is refused with a clear
reason rather than delivered without one of them.

### Current behavior

`LAUNDRY_ROOM_ENABLED = True`; `build_room_program` emits one `ProgramRole.LAUNDRY` room
(`RoomTemplate(2.5, 4.0, 8.0, …, elasticity 0.10)`, `ZoneGroup.SERVICE`) with service-first
area allocation, row-sharing rescue with TOILET, and a disclosure notice (Wiki: Laundry). It gets
one door edge from the hall/circulation like every SERVICE room. It is in neither
`DAYLIGHT_ROLES` nor `WET_ROOM_PREFERRED_ROLES`, so `generate_windows` skips it: a laundry room
never gets a window and nothing requires an exterior wall. The template constrains area and
aspect only — nothing guarantees a bay wide enough for a 0.6 m machine plus working clearance,
and no test asserts door / bay / window together.

### Required behavior

1. Exposure policy for LAUNDRY: `exterior_wall: REQUIRED`, `window: REQUIRED` (added to the
   exposure table of the Windows Issue), with a service-window minimum width of 0.6 m; C19/C8
   therefore gate it, and the planner's placement must put the laundry room on an exterior wall
   (the SERVICE column/row placement gains an exterior preference for LAUNDRY the same way
   DAYLIGHT roles are placed today).
2. Machine bay: the LAUNDRY template's minimum short side becomes 1.7 m (0.6 m machine + 0.6 m
   optional dryer + 0.5 m circulation) — recorded in `ROOM_TEMPLATES` with the reasoning; C3
   enforces it; the furniture stage places a `WASHING_MACHINE` footprint (0.6 × 0.6 m) against a
   wall with 0.9 m clearance in front (C9 furniture-envelope feasibility covers it).
3. Door: the access rules (Doors Issue) list LAUNDRY as entered from HALL/CIRCULATION/KITCHEN with
   a SERVICE_DOOR; C24 covers it.
4. Refusal: when a laundry brief cannot satisfy exterior wall + window + bay, the plan is refused
   with `LAUNDRY_UNPLACEABLE` naming which requirement failed — never delivered with a windowless
   or too-narrow laundry room. Corpus impact is confined to laundry-requesting contexts; each
   affected context is listed in the PR (context, requirement that failed or the new placement).
5. `tests/test_laundry_activation_e2e.py` gains an end-to-end assertion: a laundry brief that plans
   delivers a LAUNDRY room with a door, a window with `ventilation_status == EXTERIOR_WINDOW`, a
   short side ≥ 1.7 m and a placed washing-machine footprint.

### Acceptance Criteria

- AC-1: LAUNDRY has `exterior_wall: REQUIRED` and `window: REQUIRED` in the exposure table, and a delivered laundry room always has a window with EXTERIOR_WINDOW status
- AC-2: the LAUNDRY template's minimum short side is 1.7 m and a washing-machine footprint with 0.9 m clearance is placed in every delivered laundry room
- AC-3: a laundry brief that cannot satisfy exterior wall + window + bay is refused with `LAUNDRY_UNPLACEABLE` and a message naming the failed requirement
- AC-4: the end-to-end laundry test asserts door + window + bay + machine on a planning brief
- AC-5: non-laundry corpus contexts are untouched (LOST=0, no signature change outside laundry-requesting contexts); laundry contexts affected are listed in the PR
- AC-6: the Laundry Wiki page states the guaranteed semantics and the refusal code

### Out of scope

Dryer venting, plumbing, a laundry toggle in the ReviewPage, changing the service-first area
policy, the disclosure notice.

### Affected domains

backend, geometry, validator, knowledge

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

#18, #19

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> grep:backend/app/vertical_slice/exposure_policy.py:LAUNDRY ; pytest:backend/tests/vertical_slice/test_laundry_room.py
- AC-2 -> grep:backend/app/vertical_slice/concept_generator.py:ProgramRole.LAUNDRY: RoomTemplate ; pytest:backend/tests/vertical_slice/test_laundry_room.py
- AC-3 -> grep:backend/app/demo/service.py:LAUNDRY_UNPLACEABLE ; pytest:backend/tests/test_laundry_activation_e2e.py
- AC-4 -> pytest:backend/tests/test_laundry_activation_e2e.py
- AC-5 -> regression:corpus ; review:the PR lists every laundry-requesting corpus context whose outcome or primary changed, with the requirement that failed or the new placement
- AC-6 -> grep:docs/wiki/features/laundry.md:LAUNDRY_UNPLACEABLE

### Regression budget

LOST: 0
GAINED: 0
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 12

### Expected documentation changes

docs/wiki/features/laundry.md (guaranteed semantics, template change, refusal code).

### Knowledge check

Consulted: `docs/wiki/features/laundry.md`, `docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md`,
`docs/LAUNDRY_ROOM_OPTION_REVIEW.md`, `docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md`,
`app/vertical_slice/concept_generator.py` (LAUNDRY template, service-first allocation, row
rescue), `app/vertical_slice/windows.py`, `tests/test_laundry_activation_e2e.py`,
`tests/vertical_slice/test_laundry_room.py`. What exists: the room, its door edge, area policy
and disclosure notice. What remains (this Issue): mandatory exterior wall + window, a usable
machine bay with clearance, an explicit refusal, an end-to-end guarantee test.
