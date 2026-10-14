# [agent] ROOT — Stage 0+1 of the architectural brain: ship the merged public room, then a non-guillotine realizer for EVERY rectilinear shape family (L, U, T, cross, Z), gated on 10 real corpus layouts

### Goal

Owner approval 2026-09-23 ("מאשר", after the staged roadmap and the shape-family measurement): make the two
steps that turn measured findings into visible architecture. **Stage 0** — ship Architecture A (the merged
LIVING+KITCHEN public room) as a real flagged feature and flip it on once measured, so a public room stops
coming out as a strip. **Stage 1 (the gate)** — build a non-guillotine realizer whose target is EVERY
rectilinear shape family (L, U, T, cross, Z — measured: 47 U/T/cross/Z rooms vs 31 L in the 20-plan real-plan
fixture, so L alone is a minority of what real plans need), proven on 10 real corpus layouts through the
unchanged validators, behind a flag, without touching the production path. If the gate fails, we stop at Stage 0.
Courtyards (envelope with a hole) come after Stage 1; diagonal walls only on demand (5 % of measured rooms);
curved/circular is NOT in scope and needs its own product decision (0 occurrences measured, 0 in the Israeli
census). Later stages (brain → realizer, architectural quality loop, default switch) open only after this gate.

### Current behavior

`geometry_core` tiles rectangular wings with a binary slicing tree: every room is an axis-aligned rectangle and
every partition is a straight cut across the whole subtree. Measured on the real-plan corpus (#102, #106):
1/199 plans are guillotine-separable, 1 % of envelopes are rectangular, 51 % of rooms are rectangles, 17 % are
L, the rest U/T/cross/Z, complex rectilinear or angled. Measured on the POC (#109): of the adjacency facts a
retrieved plan dictates, 2/14 survive realization and 0/10 relative placements, most losses tagged
`GUILLOTINE_IMPOSSIBLE`. `room_merge.py` (spike #107, branch `integration/non-rectangular-geometry`) merges an
adjacent LIVING+KITCHEN leaf pair into one L-shaped room behind `LIVING_KITCHEN_MERGE_ENABLED = False`:
measured flag-on over 432 contexts — 191 candidates found, 168 applied (88 %), LOST 0, crashes 0, 168/404 primary
signatures changed. Spike #108 showed the downstream pipeline (validators, metrics, contract, renderer) mostly
accepts a hand-encoded non-guillotine layout; the solver itself is the missing, unbuilt part.

### Required behavior

Executed through child Issues:

1. **Stage 0 — ship the merged public room** (from #107's spike): the merge becomes a supported feature —
   `RoomOut.shape`, the renderer and the frontend already handle it; add the owner-visible quality reporting
   (the merged room's own proportions in M1, no strip penalty), keep the flag, run the 432-context A/B, and flip
   the default ON only if LOST 0, crashes 0, refusal codes unchanged and the quality metrics do not regress.
2. **Stage 1 — the rectilinear realizer** (the gate): a solver that takes a LAYOUT (which room is next to which,
   relative placement, exposure requirements — the POC's `RealizationIntent` shape) plus the programme and the
   buildable region, and produces axis-aligned rooms whose union is the envelope, WITHOUT requiring a guillotine
   partition — so a room may be any rectilinear polygon (L, U, T, cross, Z) and a wall may stop in the middle.
   Behind its own flag, additive, the production path untouched. It must emit exactly the artefacts the existing
   chain consumes (rects/polygons per zone, walls, seam facts) so doors, windows, furniture, validation,
   assembly, metrics and the renderer run unchanged wherever they already can (#108 named the two small
   solver-output requirements: `Wing.tree` and `Wing.seam_leaf_sides`).
3. **The gate**: 10 real layouts taken from the POC corpus (chosen to cover L, U/T/cross/Z and at least one
   non-rectangular envelope) are realized by the new solver and pass every existing hard validator; the report
   states per layout what was realized, what was refused and why. Failing the gate = Stage 1 stops and the
   program stays at Stage 0 — an honest, recorded outcome, not a reason to relax a validator.
4. Nothing merges to `main` from this ROOT without the owner's explicit approval; the frozen-corpus regression
   stays at LOST 0 with the flags OFF.

### Acceptance Criteria

- AC-1: with both flags OFF the frozen 432-context corpus is byte-identical to the base (LOST 0, primary_signature_changes 0, refusal codes unchanged)
- AC-2: Stage 0's 432-context A/B is committed (candidates found, applied, LOST/crashes, signature changes, quality-metric deltas) and the default flip decision follows its stated rule
- AC-3: the Stage 1 solver realizes at least 10 real corpus layouts covering L, U/T/cross/Z and a non-rectangular envelope, each passing every existing hard validator, with the per-layout report committed
- AC-4: no validator, hard limit or production code path is relaxed or bypassed for either stage (review target), and every new behaviour sits behind its own flag

### Out of scope

Curved/circular geometry and arcs (separate product decision); diagonal/non-axis-aligned walls; courtyard
envelopes with holes (after this gate); wiring the brain's retrieved layouts into the new solver (Stage 2);
making the new realizer the default (Stage 4); merging to main.

### Affected domains

geometry, backend, validator, frontend, qa, knowledge

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

none

### Required locks

geometry-core, validator-core, planner-core (shared), frontend-review (shared)

### Verification plan

- AC-1 -> regression:corpus
- AC-2 -> file:docs/reports/rectilinear-realizer/stage0-merge-ab.md ; grep:docs/reports/rectilinear-realizer/stage0-merge-ab.md:LOST
- AC-3 -> file:docs/reports/rectilinear-realizer/stage1-gate.md ; grep:docs/reports/rectilinear-realizer/stage1-gate.md:U/T/cross
- AC-4 -> pytest:backend/tests/vertical_slice/test_rectilinear_realizer_flags.py
- AC-4 -> review:no validator, hard limit or production path is relaxed or bypassed, and every new behaviour is flag-gated and OFF by default

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 200

### Expected documentation changes

docs/reports/rectilinear-realizer/ (stage0-merge-ab.md, stage1-gate.md), docs/wiki/architecture/geometry-validation.md (the realizer and the merge, once either lands), docs/ROADMAP.md (the staged programme).

### Knowledge check

Consulted: the owner's staged roadmap approval (2026-09-23) and the shape-family measurement (20 real plans, 183 rooms:
rectangle 75, U/T/cross/Z 47, L 31, complex rectilinear 16, angled 9, courtyards 0), `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`,
`docs/reports/non-rectangular-geometry-{full-corpus-remeasurement,architecture-a-spike,architecture-b-spike}.md`,
`room_merge.py` and its 432-context A/B, `geometry_core/{model,engine}.py`, `validation.py`, the POC's `realization_intent.py`
and its preservation figures (#109), `docs/reports/poc-architectural-brain/`.
