# [agent] Realized area and dimension consistency: every displayed width, depth and area derives from one authoritative realized geometry

### Goal

All dimensions and areas shown to the user derive from the authoritative realized geometry with one
documented definition each (realized polygon area, net usable area, gross area, wall treatment); the renderer
never shows contradictory measurements and the validator detects inconsistent metadata.

### Current behavior

`app/demo/contract.py::RoomOut` carries `width_m`/`depth_m` from the room's GROSS rectangle (`r.rect_m`,
including the wall allocation) while `area_m2 = r.net_area_m2` (net of walls, `geometry_core.engine.net_rect_m`)
— so the displayed width × depth does not equal the displayed area (the owner's observed mismatch). The
frontend draws the rectangle from x/y/width/depth and prints area_m2; nothing checks the two agree, and the
definitions (gross vs net, wall thickness treatment) are not documented for the user-facing fields.

### Required behavior

1. Definitions in `docs/wiki/architecture/geometry-validation.md` and in the `RoomOut` docstring: `gross_rect`
   (allocation incl. walls), `net_rect` (usable, wall-adjusted), `net_area_m2 = net_w × net_d`, `gross_area_m2`,
   and which one each user-facing field shows.
2. `RoomOut` becomes self-consistent: `width_m`/`depth_m` are the NET dimensions that multiply to `area_m2`
   (additive `gross_width_m`/`gross_depth_m`/`gross_area_m2` keep the drawing rectangle), or the drawing uses
   the gross rectangle explicitly and labels the net area as such — one rule, applied everywhere.
3. New check C27 "displayed dimensions consistent with realized geometry": for every RoomOut, |width×depth −
   area| ≤ 0.05 m² and the rectangle equals the realized net/gross rect as declared; also `building.gross_area`
   equals the sum of realized zones + walls within tolerance. Fails closed on the product path.
4. The frontend renders only backend-provided numbers (no client-side area recomputation) — an audit test
   greps the ReviewPage/plan components for local `* height` area math.

### Acceptance Criteria

- AC-1: the definitions are documented and RoomOut's fields state which definition they carry
- AC-2: for every PLANNED corpus design, every room's width×depth equals its area within 0.05 m² (C27 green)
- AC-3: a fixture with tampered room metadata fails C27 and the demo path refuses with `INCONSISTENT_GEOMETRY`
- AC-4: the frontend computes no area or dimension on its own (audit test) and the plan drawing still matches the backend rectangles (existing frontend tests green)

### Out of scope

Room-area maxima policy, area fidelity vs requested area (separate roadmap topic), renderer styling, DXF.

### Affected domains

backend, validator, frontend, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

none

### Required locks

validator-core (exclusive), frontend-review (shared)

### Verification plan

- AC-1 -> grep:docs/wiki/architecture/geometry-validation.md:net_area_m2 ; grep:backend/app/demo/contract.py:gross_area_m2
- AC-2 -> pytest:backend/tests/test_demo_quality.py::test_every_room_width_depth_matches_its_area ; regression:corpus
- AC-3 -> pytest:backend/tests/vertical_slice/test_dimension_consistency.py::test_c27_fails_tampered_metadata_and_demo_refuses ; grep:backend/app/vertical_slice/validation.py:C27
- AC-4 -> pytest:backend/tests/test_frontend_contract_audit.py::test_frontend_does_not_recompute_areas ; vitest:frontend/src/components/plan/PlanCanvas.test.tsx

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (definitions, C27), docs/PROJECT_STATE.md (refusal code).

### Knowledge check

Consulted: `app/demo/contract.py` (RoomOut: width/depth from rect_m, area from net_area_m2 — the mismatch root cause), `geometry_core/engine.net_rect_m`, `validation.py` C3 (areas/dimensions valid — checks minima, not display consistency), memory 'room-area-two-level-maxima'. What remains: definitions, self-consistent RoomOut, C27, frontend audit.
