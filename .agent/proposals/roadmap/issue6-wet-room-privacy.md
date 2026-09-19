# [agent] Wet-room privacy and access quality: exposure, door orientation, zone relationship and circulation evaluated — corridor-access wet rooms stay valid

### Goal

Bathrooms and WCs are placed and entered with sensible privacy and access: evaluated by direct visual
exposure, door orientation, door conflicts, public-zone exposure, private-zone relationship, circulation
obstruction and adjacency quality — not by a blunt "no bathroom may open to a corridor" rule.

### Current behavior

Wet rooms are shaped and grouped by the quality tier and the wet-room strip fix (`wet_rooms.py`, C17 bathroom
access per requirements, M5 wet adjacency), the guest-WC pocket policy (spec 009) decides where a GUEST_WC may
be entered from (foyer → public circulation → living, never bedroom/kitchen). Nothing evaluates the door's
orientation relative to public rooms (a WC door facing the dining table), the sight line from a public room
into the bathroom, or the door's interaction with corridor circulation; ensuite privacy is only structural
(entered from the bedroom).

### Required behavior

1. `backend/app/vertical_slice/wet_privacy.py`: per wet room a deterministic `WetPrivacy` record — entered-from
   zone class (private/circulation/public), door facing (the zone the open door faces across the corridor or
   room, from `swings_into`/orientation), direct sight line from the nearest public room's centre through the
   door opening (segment test on realized geometry), public exposure score, circulation obstruction (door leaf
   vs corridor width), adjacency quality (shared wall with another wet room / kitchen).
2. New check C29 "wet-room privacy" fails closed only on hard violations (wet room entered directly from
   KITCHEN or DINING, door opening straight onto a public seating/dining zone with a direct sight line);
   everything else is a tiered quality score joining the candidate ranking. Corridor-access wet rooms remain
   valid.
3. `QualityOut` gains the per-wet-room privacy record; the rubric section I lists the signals.

### Acceptance Criteria

- AC-1: WetPrivacy is computed for every wet room of the canonical fixtures and of a guest-WC fixture, from realized geometry
- AC-2: C29 fails a fixture whose WC opens straight into the dining zone with a direct sight line and passes the canonical corridor-access bathrooms
- AC-3: the ranking prefers the sibling with the better privacy score on a two-candidate fixture
- AC-4: corpus regression: LOST 0; primary-signature changes listed and expected (privacy-driven) only

### Out of scope

Fixture placement inside wet rooms (Issue 9), plumbing efficiency (Issue 14), regulation.

### Affected domains

backend, geometry, validator, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#18

### Required locks

geometry-core (exclusive), validator-core (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_wet_privacy.py::test_records_for_canonical_and_guest_wc_fixtures
- AC-2 -> pytest:backend/tests/vertical_slice/test_wet_privacy.py::test_c29_fails_dining_facing_wc_and_passes_corridor_access ; grep:backend/app/vertical_slice/validation.py:C29
- AC-3 -> pytest:backend/tests/vertical_slice/test_wet_privacy.py::test_ranking_prefers_better_privacy
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 30

### Expected documentation changes

docs/wiki/features/wet-rooms.md (privacy signals, C29), docs/architecture_reference/quality_rubric.md (section I).

### Knowledge check

Consulted: `docs/wiki/features/wet-rooms.md`, `wet_rooms.py`, `validation.py` C17, `specs/009-guest-wc-placement` (PublicAccess order), `quality_metrics.py` M5. What exists: grouping, proportions, guest-WC entry order. What remains: door orientation, sight lines, exposure score, C29, ranking term.
