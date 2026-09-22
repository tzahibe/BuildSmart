# [agent] Non-rectangular geometry ROOT (3/3): 2-week spike — prove or kill the reuse claim for a non-guillotine rectangular layout

### Goal

Prove or kill Architecture B (non-guillotine rectangular layout) from Issue #102's investigation on
its own narrowest, cheapest question: does the EXISTING rectangle-typed pipeline (validators,
M1-M6, hub/L-massing/wet-core guards, both renderers) really accept a `dict[str, Rect]` that is NOT
a slicing-tree output, with zero code changes, as the investigation report's reuse table claims —
before committing engineering weeks to an actual non-guillotine solver.

### Current behavior

Every existing rectangular room layout `app/vertical_slice/geometry_core/engine.py` produces is a
slicing-tree tiling (`solve_fixture`); nothing in the current codebase has ever handed the
validator/metrics/renderer pipeline a set of rectangles that was NOT produced this way. Issue #102's
report claims (§4.B) that this pipeline needs no room-shape-level change for architecture B, only a
new adjacency-graph layer for checks that currently assume tree-leaf adjacency — an untested claim.

### Required behavior

1. Pick ONE reference archetype already flagged non-rectangular envelope in
   `docs/architecture_reference/references/index.json` (`footprint_family: "L"` or `"irregular"`,
   e.g. `l-3br-corner` or `irr-4br-courtyard`) and hand-encode its known real room layout as a
   `dict[str, Rect]` — by hand, NOT solver-generated, and deliberately NOT constructible by any
   sequence of guillotine cuts (i.e. genuinely non-guillotine, per the same recognition test
   `measure_real_plan_shapes.py::is_guillotine_separable` implements).
2. Feed this hand-encoded layout into the EXISTING pipeline entry points one at a time — C1, C3,
   C9, C20, C27 validation; M1-M6 quality metrics; the backend SVG renderer; the frontend plan
   canvas — WITHOUT changing any of their code first. Record exactly which ones accept it as-is and
   which ones crash, silently mis-measure, or assume something about tree-leaf adjacency that a
   general rectangle set does not provide (this is the actual test — not whether the layout
   "looks right", but whether each module's current code path even runs against a non-tree input).
3. For any module that fails, make the SMALLEST possible fix that lets it accept a general
   `dict[str, Rect]` (not a broader refactor) and re-run; record what changed.
4. Report, per module named in Issue #102's report §4.B "reused unchanged" claim, whether it held.

### Acceptance Criteria

- AC-1: the hand-encoded layout is committed as a test fixture, and a test proves it is genuinely non-guillotine via the same recognition function the investigation's measurement script uses
- AC-2: the spike report states, per pipeline module (C1, C3, C9, C20, C27, M1-M6, both renderers), whether it accepted the hand-encoded layout unchanged, and names the exact change made for any that did not
- AC-3: the spike report revises Issue #102's Architecture B effort estimate up or down based on what was actually found, with the reasoning stated

### Out of scope

Building an actual non-guillotine solver (this spike hand-encodes ONE layout, it does not generate
one); any change to how a real plan gets generated in product code paths; Architecture A or C; the
corpus regression signature's own definition (out of scope for a single hand-encoded fixture, though
the spike report should still name what a real signature redesign for B would need, per §4.B).

### Affected domains

geometry, validator, backend, frontend, qa

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

none

### Required locks

geometry-core (shared), validator-core (shared), frontend-review (shared)

### Verification plan

- AC-1 -> TEST:pytest:backend/tests/vertical_slice/test_non_guillotine_reuse_spike.py::test_fixture_layout_is_genuinely_non_guillotine
- AC-2 -> ARTIFACT:file:docs/reports/non-rectangular-geometry-architecture-b-spike.md
- AC-3 -> ARTIFACT:grep:docs/reports/non-rectangular-geometry-architecture-b-spike.md:effort

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/reports/non-rectangular-geometry-architecture-b-spike.md (new),
docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md (cross-referenced, not rewritten).

### Knowledge check

Consulted: `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §2, §4.B (Issue #102),
`backend/spikes/geometry_shapes/measure_real_plan_shapes.py` (the guillotine-recognition function
this spike's fixture must fail), `docs/architecture_reference/references/index.json` (the L/
irregular reference archetypes this spike draws its one layout from). Depends on the ROOT
(`root-102-non-rectangular-geometry.md`) being queued.
