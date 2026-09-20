# [agent] C24 door rules: LIVING is an allowed entered-from room for a wet room (spec 009 decision C), with the tests that pin it

### Goal

Align the door-rule table with the approved guest-WC policy: a wet room (BATHROOM/TOILET, incl. GUEST_WC) may be
entered from circulation, from its hosting bedroom, or — as the last public-access fallback — from LIVING, exactly
as `specs/009-guest-wc-placement` decision C states. KITCHEN and DINING stay forbidden.

### Current behavior

`backend/app/vertical_slice/access_rules.py::ALLOWED_ENTERED_FROM` maps `WET_ROLES` to `CIRCULATION_ROLES |
BEDROOM_HOST_ROLES` only, so C24 fails closed on a wet room entered from LIVING; `wet_privacy.py` (Issue #37) and
spec 009 §PublicAccess ("foyer/HALL → public circulation → LIVING. Never BEDROOM, never KITCHEN") treat LIVING as
legitimate. The corpus shows no such plan today (gate-4: 0 status changes), so the contradiction is latent — found
by the rollup's combined-diff review.

### Required behavior

1. `ALLOWED_ENTERED_FROM[wet role] = CIRCULATION_ROLES | BEDROOM_HOST_ROLES | {LIVING}`; KITCHEN and DINING remain
   disallowed; the docstring cites spec 009 decision C.
2. Tests: a fixture with a WC entered from LIVING passes C24; a WC entered from KITCHEN and one from DINING still fail C24
   naming the rule; `wet_privacy` scores the LIVING-entered WC as public-soft exposure (unchanged behaviour, pinned).
3. Wiki: the C24 table row for wet rooms lists LIVING with the spec reference.

### Acceptance Criteria

- AC-1: a WC entered from LIVING passes C24 on a hand-built fixture; from KITCHEN and from DINING it fails C24
- AC-2: the canonical fixtures and the corpus are unchanged (LOST 0, status changes 0, primary-signature changes 0)
- AC-3: the Wiki C24 table lists LIVING for wet rooms with the spec 009 reference

### Out of scope

Any other rule of the table, GUEST_WC placement itself, C29.

### Affected domains

backend, validator, knowledge

### Risk

LOW

### Resource class

LIGHT

### Dependencies

none

### Required locks

validator-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_access_rules.py::test_c24_allows_wet_room_from_living_but_not_kitchen_or_dining
- AC-2 -> pytest:backend/tests/vertical_slice/test_access_rules.py::test_c24_passes_on_canonical_fixtures ; regression:corpus
- AC-3 -> grep:docs/wiki/architecture/geometry-validation.md:decision C

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (C24 row).

### Knowledge check

Consulted: the rollup #62 combined review (major finding), `access_rules.py`, `wet_privacy.py` docstring, `specs/009-guest-wc-placement/spec.md` §PublicAccess / decision C, gate-4 report of the rollup (0 changes → latent). What remains: the one table entry, tests, Wiki row.
