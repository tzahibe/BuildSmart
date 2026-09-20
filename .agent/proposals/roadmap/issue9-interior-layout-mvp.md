# [agent] Architectural interior layout MVP: engine-owned semantic layout objects (bed, wardrobe, sofa zone, dining table, kitchen runs, fixtures) rendered as-is

### Goal

Plans begin to look and behave like architectural plans: structured semantic layout objects per room type
placed by the backend layout engine, rendered by the SVG renderer without invention — no decorative fake
furniture.

### Current behavior

Stage 6 furniture is a bounding-box inscribe test only (`furniture.py::check_furniture_feasibility` over the
frozen Geometry Core's `min_furniture_envelope_m`, C9) — no placement, no objects. Wet-room fixtures exist as
layout intent in `wet_rooms.py` but are not emitted as placed objects; the renderer draws rooms, doors and
windows only.

### Required behavior

1. `backend/app/vertical_slice/interior_layout.py`: typed objects (`LayoutObject(kind, room_id, rect_m,
   rotation, clearance_rect_m)`) and per-role placers: BEDROOM bed + wardrobe; MASTER bed + wardrobe (+ suite
   elements when present); LIVING sofa zone + coffee table + focal wall; DINING table + chair clearance; KITCHEN
   counter runs + refrigerator + sink + cooktop/oven (+ island only when requested/appropriate); BATHROOM/WC
   toilet + sink + shower/bath. Placement is deterministic, uses door swings and windows as constraints, and
   reports `unplaceable` instead of forcing.
2. `QualityOut`/contract gains `layout: [LayoutObjectOut]`; the frontend renders them from the contract only.
3. Placement failures are data (for Issue 10), not refusals.

### Acceptance Criteria

- AC-1: every role placer produces objects with clearances on the canonical fixtures and reports unplaceable on a too-small fixture without raising
- AC-2: objects never overlap walls, doors' swing envelopes or each other on the canonical fixtures
- AC-3: the contract exposes the layout for every PLANNED corpus design and the frontend draws it from the contract (snapshot test)
- AC-4: corpus regression: LOST 0, no status/primary changes (layout is additive)

### Out of scope

Furnishability scoring (Issue 10), public-zone composition (Issue 11), decorative furniture, DXF symbols.

### Affected domains

backend, geometry, frontend, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#19, #38

### Required locks

geometry-core (shared), frontend-review (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_interior_layout.py::test_role_placers_on_canonical_and_too_small_fixtures
- AC-2 -> pytest:backend/tests/vertical_slice/test_interior_layout.py::test_objects_avoid_walls_doors_and_each_other
- AC-3 -> pytest:backend/tests/test_demo_quality.py::test_layout_objects_present_for_planned_designs ; vitest:frontend/src/components/plan/InteriorLayout.test.tsx
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/features/interior-layout.md (new), docs/architecture_reference/quality_rubric.md (F signals).

### Knowledge check

Consulted: `furniture.py` (envelope screen only), `geometry_core.model.min_furniture_envelope_m`, `wet_rooms.py`, `renderer.py`. What exists: feasibility envelopes. What remains: placed objects, contract, rendering.
