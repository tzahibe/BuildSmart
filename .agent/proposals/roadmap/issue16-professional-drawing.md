# [agent] Professional architectural drawing representation: line weights, authoritative doors/windows/furniture/fixtures, labels, dimensions, north arrow, scale and plot context — rendered only from authoritative data

### Goal

The final plan visually resembles a professional architectural drawing because the underlying data is real:
wall line weights by class, authoritative doors and windows, furniture and fixtures, room labels, dimensions,
north arrow, scale, room symbols and exterior/plot context — never by inventing information in the renderer.

### Current behavior

The SVG renderer (`renderer.py` + frontend plan components) draws rooms, doors, windows (backend-provided) and
labels; walls have one weight; no dimensions, north arrow, scale or plot context; furniture/fixtures do not exist
yet (Issue 9).

### Required behavior

1. Rendering is extended field by field, each strictly from the contract: wall thickness by class (Issue 15),
   door arcs (Issue 4), windows (#19), layout objects (Issue 9), dimension strings computed by the backend
   (Issue 3 definitions), north arrow from the site orientation field (no orientation → no arrow), scale bar,
   room symbols by role, plot outline/setbacks when the site model provides them.
2. A renderer audit test asserts every drawn element maps to a contract field (no renderer-side geometry
   invention) and a golden SVG snapshot per canonical fixture.
3. DXF is out of scope; SVG only.

### Acceptance Criteria

- AC-1: every drawn element class maps to a contract field (audit test) and the golden SVG snapshots of the canonical fixtures render walls by class, doors with arcs, windows, layout, labels, dimensions, north arrow and scale
- AC-2: a design without site orientation renders no north arrow and without a site model no plot context (no invention)
- AC-3: frontend build/lint/types and the plan component tests stay green; corpus regression unchanged (rendering only)

### Out of scope

DXF output, PDF report, styling preferences beyond the professional conventions.

### Affected domains

frontend, backend, qa, knowledge

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

#45, #39, #40

### Required locks

frontend-review (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/test_renderer_audit.py::test_every_element_maps_to_a_contract_field ; vitest:frontend/src/components/plan/PlanCanvas.test.tsx
- AC-2 -> pytest:backend/tests/test_renderer_audit.py::test_no_north_arrow_without_orientation_and_no_plot_without_site
- AC-3 -> static:frontend-lint ; static:frontend-types ; regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/features/interior-layout.md, frontend README (drawing conventions).

### Knowledge check

Consulted: `renderer.py`, frontend plan components, roadmap topic 'SVG/DXF production quality'. Depends on Issues 15, 9, 10.
