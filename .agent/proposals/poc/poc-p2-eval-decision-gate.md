# [agent] POC Phase 2 — fixed evaluation and decision gate: current engine vs brain Phase 1 vs brain Phase 2 on the three briefs, with the GO-A / GO-B / GO-C-LATER / STOP recommendation

### Goal

Give the owner the evidence to choose, by the rules he set (2026-09-23): a three-way visual and measured
comparison on the SAME three fixed benchmark briefs — CURRENT ENGINE vs REAL-PLAN BRAIN PHASE 1 vs REAL-PLAN
BRAIN PHASE 2 — with the retrieved real references shown for every brain result, the full measurement table, the
visual judgement of whether the organisation is genuinely different, and one recommendation: **GO-A** (existing
slicing solver + selective merged rooms is expressive enough), **GO-B** (a non-guillotine rectangular realizer is
needed as the next Geometry Core), **GO-C-LATER** (polygon geometry eventually, not yet) or **STOP** (real-plan
retrieval is not materially influencing realized architecture). The choice is made on evidence from the fixed
benchmark and the real-plan corpus, never on implementation effort.

### Current behavior

Phase 1's report (`docs/reports/poc-architectural-brain/README.md`) compares the current engine with one brain
column and recommends MODIFY. Phase 2 adds Track 1 (topology compilers), Track 3 (RealizationIntent +
PRESERVED/LOST) and, from ROOT #105, the geometry spikes' own findings; nothing yet compares all three columns or
states a decision-gate verdict.

### Required behavior

1. `docs/reports/poc-architectural-brain/phase2.md` + the rebuilt `index.html`: for each of the three fixed
   briefs, three columns side by side — CURRENT ENGINE · BRAIN PHASE 1 (the committed Phase-1 SVGs, kept as the
   baseline) · BRAIN PHASE 2 — each brain column showing the retrieved real references and WHY.
2. The measurement table per plan: realized circulation class, adjacency preservation %, access-graph
   preservation %, zoning preservation, wet-core preservation, circulation ratio, dead space, exterior exposure,
   hard validator failures, room-area compliance (preservation figures from Track 3's `PreservationReport`).
3. The visual judgement stated plainly: for each brief, whether the Phase-2 result is a genuinely different
   architectural organisation — and where two donors still collapse to the same drawing, the exact realization
   constraint that caused it.
4. The decision-gate section: GO-A / GO-B / GO-C-LATER / STOP with the evidence for the choice, including what
   ROOT #105's spikes (full-corpus remeasurement, Architecture A, Architecture B) reported by then, and what
   would change the answer.
5. Everything stays on the POC branch; nothing is merged to main.

### Acceptance Criteria

- AC-1: `phase2.md` and `index.html` show all three columns for all three briefs, with the retrieved references and WHY under each brain column
- AC-2: the measurement table carries every metric the owner listed, per plan, with the preservation percentages taken from the PreservationReport (UNKNOWN where a metric genuinely does not apply)
- AC-3: for every pair of plans that realized to the same geometry, the report names the causing realization constraint
- AC-4: the decision-gate section states exactly one of GO-A / GO-B / GO-C-LATER / STOP with its evidence and what would change it

### Out of scope

Implementing any GO; changing the benchmark briefs; merging to main.

### Affected domains

qa, backend, knowledge

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

#109, #110

### Required locks

planner-core (shared)

### Verification plan

- AC-1 -> file:docs/reports/poc-architectural-brain/phase2.md ; grep:docs/reports/poc-architectural-brain/phase2.md:PHASE 2
- AC-2 -> grep:docs/reports/poc-architectural-brain/phase2.md:adjacency preservation
- AC-3 -> grep:docs/reports/poc-architectural-brain/phase2.md:collapse
- AC-4 -> grep:docs/reports/poc-architectural-brain/phase2.md:GO-

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/phase2.md (new), index.html (three columns), README.md (pointer to Phase 2).

### Knowledge check

Consulted: the owner's Phase 2 specification (2026-09-23: fixed evaluation + decision gate), Phase 1's README and
per-brief comparison docs, Track 1 and Track 3's outputs, ROOT #105's spike reports, `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`.
