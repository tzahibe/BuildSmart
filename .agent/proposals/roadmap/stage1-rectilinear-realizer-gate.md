# [agent] Stage 1 (2/2, THE GATE): a non-guillotine realizer for every rectilinear shape family — proven on 10 real corpus layouts through the unchanged validators, or the programme stops here

### Goal

Build the missing piece the measurements point at: a realizer that takes a LAYOUT (which room touches which,
relative placement, exposure requirements) and produces axis-aligned rooms whose union fills the envelope
WITHOUT a guillotine partition — so a room may be any rectilinear polygon (L, U, T, cross, Z) and a wall may
stop in the middle. Prove it on 10 real corpus layouts through the unchanged validator chain, behind its own
flag, with the production path untouched. This Issue is a GATE: if the 10 layouts cannot be realized inside its
budget, the programme stops at Stage 0 and says so — no validator is relaxed to make it pass.

### Current behavior

`geometry_core.engine.solve_fixture` assigns rectangles by walking a binary slicing tree: every partition is a
straight cut across a subtree, so only guillotine layouts exist (measured: 1/199 real plans qualify; the POC
loses 12/14 adjacency facts to `GUILLOTINE_IMPOSSIBLE`). Spike #108 hand-encoded a real non-guillotine layout
and ran it through doors, windows, furniture, validation, assembly, metrics and the renderer: the pipeline
accepts it, with two small solver-output requirements (`Wing.tree`, `Wing.seam_leaf_sides`) and one real failure
(C26's circulation ratio) documented in `docs/reports/non-rectangular-geometry-architecture-b-spike.md`.
No solver produces such a layout today.

### Required behavior

1. `backend/app/vertical_slice/rectilinear_realizer.py` (new, flag `RECTILINEAR_REALIZER_ENABLED = False`):
   `realize_layout(layout, programme, buildable) -> RealizedLayout | Refusal` — input is the adjacency /
   placement / exposure layout (the POC's `RealizationIntent` shape, imported or mirrored as a dataclass, not
   forked); output is one axis-aligned rectilinear polygon per zone whose union is the envelope with no residual
   area, plus the walls and seam facts the existing chain needs. A layout it cannot realize is REFUSED with the
   failing constraint named — never approximated silently.
2. The output feeds the UNCHANGED chain: `doors.py`, `windows.py`, `furniture`, `validation.py` (C-checks),
   `design_output.assemble`, `quality_metrics`, the SVG renderer. Where a check genuinely cannot run on a
   rectilinear polygon, the report records it as a NEEDS-POLYGON-VARIANT finding — it is not disabled.
3. `backend/spikes/geometry_shapes/stage1_gate.py` + `docs/reports/rectilinear-realizer/stage1-gate.md`: the 10
   real corpus layouts (covering L, U/T/cross/Z and at least one non-rectangular envelope), each with: realized
   or refused, which validators ran and their result, which architectural facts of the source layout survived
   (adjacency / placement / exposure counts), the wall time, and the rendered SVG.
4. The production path is untouched with the flag OFF (the frozen corpus is byte-identical), and no validator,
   threshold or hard limit is changed anywhere in the diff.

### Acceptance Criteria

- AC-1: `realize_layout` produces, for a hand-built layout fixture, rooms that are rectilinear polygons (at least one L, one U/T/cross/Z) whose union equals the envelope with zero residual area, and refuses an impossible layout with the failing constraint named
- AC-2: at least 10 real corpus layouts are attempted and the committed gate report states per layout: realized/refused, the validator results, the surviving adjacency/placement/exposure counts, the wall time and the SVG path
- AC-3: of those 10, the ones that realize pass every existing hard validator that can run, with zero validator/threshold changes in the diff; any check that cannot run on a polygon is listed as a finding, not disabled
- AC-4: with `RECTILINEAR_REALIZER_ENABLED = False` the frozen 432-context corpus is byte-identical to the base (LOST 0, primary_signature_changes 0)

### Out of scope

Making the realizer the default; wiring the brain's retrieved layouts into it (Stage 2); courtyard envelopes with
holes, diagonal walls, curves; changing Geometry Core's existing solver; merging to main.

### Affected domains

geometry, backend, validator, qa

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

none

### Required locks

geometry-core, validator-core, planner-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_rectilinear_realizer.py
- AC-2 -> file:docs/reports/rectilinear-realizer/stage1-gate.md ; grep:docs/reports/rectilinear-realizer/stage1-gate.md:U/T/cross
- AC-3 -> pytest:backend/tests/vertical_slice/test_rectilinear_realizer.py
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/rectilinear-realizer/stage1-gate.md (new, with the per-layout SVGs), docs/wiki/architecture/geometry-validation.md (the realizer, flag OFF, once it lands).

### Knowledge check

Consulted: `docs/reports/non-rectangular-geometry-architecture-b-spike.md` (what the pipeline accepts, `Wing.tree` /
`Wing.seam_leaf_sides`, the C26 failure), `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §4.B, `geometry_core/{model,engine}.py`,
`validation.py`, `design_output.py`, the POC's `realization_intent.py` and its preservation figures, the shape-family
measurement (U/T/cross/Z 47 vs L 31 rooms in the 20-plan fixture).
