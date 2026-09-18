# [agent] Entrance policy: the front door opens into a hall, foyer or living room — never a kitchen, dining, private or wet room

### Goal

A real entrance to the house: the exterior door is always on the street wall of a room a visitor
may arrive in (hall / circulation, or the living room), never a kitchen, dining room, bedroom or
wet room; when the winning arrangement has no acceptable street-fronting room, the candidate is
re-ranked below one that has, and the plan is refused rather than fabricated when none does.

### Current behavior

`backend/app/vertical_slice/doors.py::resolve_entrance` derives the entrance zone from realized
geometry on the product path (`general_pipeline.py`): the street-fronting zone with the best rank
in `ENTRANCE_ZONE_PRIORITY = (HALL, CIRCULATION, LIVING, DINING, KITCHEN)`; `build_entrance_door`
places the 1.0 m door; C7 (placeable), C11 (walk from street to door), C16 (door on the wall of
the room it names) and C5 (reachability) gate it. Consequences today: a plan whose only
street-fronting public room is the DINING room or the KITCHEN gets its front door there — "a
random room" — and nothing prefers a candidate with a proper arrival room. The frozen
vertical-slice pipeline (`pipeline.py::run_once`, tests only) still hardcodes `HALL_MAIN`. The
entrance-sequence defect (an L-massing bedroom arm fronting the street so the visitor walks past
the private wing) is documented in `docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md`
§0.5/§5.1 and stays a separate P2 topic.

### Required behavior

1. `ENTRANCE_ZONE_PRIORITY` becomes an explicit policy: ALLOWED arrival roles = HALL, CIRCULATION,
   LIVING (in that order); DINING and KITCHEN are removed; private (BEDROOM, MASTER_BEDROOM,
   SAFE_ROOM, STUDY, DRESSING) and wet/service roles are never eligible. `resolve_entrance`
   returns `None` when no allowed room fronts the street.
2. Candidate ranking (`general_pipeline`'s selection) prefers a candidate whose entrance resolves
   to HALL/CIRCULATION over one resolving to LIVING, and any resolving candidate over a refusing
   one; the refusal code for "no acceptable entrance room fronts the street" is explicit and
   distinct (`ENTRANCE_NO_ARRIVAL_ROOM`), with a message naming the street-fronting rooms found.
3. A new validation check C23 "entrance opens into an allowed arrival room" fails closed on any
   realized plan whose entrance zone role is outside the allowed set (defense in depth for every
   path, including the frozen pipeline, which is switched to `resolve_entrance` at its single call
   site).
4. Every change of a corpus primary caused by the re-ranking is listed in the PR (context, old
   entrance room → new entrance room); a context that loses its plan because its only entrance was
   through the kitchen/dining is reported as a PROPOSED FOLLOW-UP for the foyer synthesis work
   (a small street-side foyer added by the planner within the area budget) — not hidden by
   keeping the old policy.

### Acceptance Criteria

- AC-1: `ENTRANCE_ZONE_PRIORITY` contains exactly HALL, CIRCULATION, LIVING, and `resolve_entrance` returns None on a fixture whose only street-fronting rooms are DINING and KITCHEN
- AC-2: a realized plan whose entrance zone is a KITCHEN/DINING/BEDROOM/BATHROOM fails C23 (fixture-level unit test), and every plan on the frozen corpus that still plans passes C23
- AC-3: candidate selection ranks a HALL/CIRCULATION entrance above a LIVING entrance for the same brief (deterministic test on two fixtures)
- AC-4: the refusal code `ENTRANCE_NO_ARRIVAL_ROOM` exists with a message naming the fronting rooms, and the frozen pipeline calls `resolve_entrance`
- AC-5: the regression corpus keeps LOST=0; primary-signature changes are only contexts whose entrance room changed, each listed in the PR with before/after room
- AC-6: the Wiki page documents the arrival-room policy and the foyer follow-up

### Out of scope

Foyer synthesis (a new zone added by the planner), the entrance-sequence/arrival-path quality
for L-massings (P2), door swing or width changes, parking or walk geometry, ReviewPage.

### Affected domains

backend, geometry, validator, knowledge

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

#17, #18

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_entrance_policy.py::test_priority_and_none_when_only_kitchen_or_dining_front_the_street
- AC-2 -> pytest:backend/tests/vertical_slice/test_entrance_policy.py::test_c23_fails_closed_on_disallowed_entrance_room ; regression:corpus
- AC-3 -> pytest:backend/tests/vertical_slice/test_entrance_policy.py::test_hall_entrance_outranks_living_entrance
- AC-4 -> grep:backend/app/demo/service.py:ENTRANCE_NO_ARRIVAL_ROOM ; grep:backend/app/vertical_slice/pipeline.py:resolve_entrance
- AC-5 -> regression:corpus ; review:the PR lists every primary-signature change with its before/after entrance room and the count matches the regression report
- AC-6 -> grep:docs/wiki/architecture/geometry-validation.md:C23

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 40

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (arrival-room policy, C23, refusal code, foyer follow-up).

### Knowledge check

Consulted: `app/vertical_slice/doors.py` (`resolve_entrance`, `ENTRANCE_ZONE_PRIORITY`,
`build_entrance_door`), `app/vertical_slice/validation.py` (C5, C7, C11, C16),
`docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md` §0.5/§5.1 (entrance-sequence
defect), `docs/wiki/features/l-massing.md`, `specs/009-guest-wc-placement/spec.md`. What exists:
geometry-derived entrance on the product path with placeability/walk/label gates. What remains
(this Issue): an arrival-room policy (no kitchen/dining/private entrance), ranking by entrance
quality, an explicit refusal, a fail-closed check on every path. Follow-ups: foyer synthesis;
entrance-sequence quality for L-massings (P2).
