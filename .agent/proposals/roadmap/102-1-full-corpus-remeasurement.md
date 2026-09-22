# [agent] Non-rectangular geometry ROOT (1/3): re-measure room/envelope shapes against the POC's full 199-plan corpus

### Goal

Firm up Issue #102's directional shape measurement (19-plan sample) by re-running its own
deterministic script against the POC Architectural Brain's full 199-plan real-ResPlan corpus, once
an integration branch carries both this ROOT's work and `integration/poc-architectural-brain`.
First measurable milestone named in the investigation report before either A/B spike commits
engineering time to its own result.

### Current behavior

`backend/spikes/geometry_shapes/measure_real_plan_shapes.py` (Issue #102) runs deterministically
against a committed 20-plan fixture (`backend/tests/spikes/fixtures/geometry_shapes/plans/`) and
reports: 41.9% of real rooms are rectangles, 19.6% simple L-shapes; 0/19 real plans' room layouts
are guillotine-separable; 0/19 plans have a rectangular envelope. The report explicitly flags this
19-plan sample as chosen for circulation-class diversity, not footprint-regularity
representativeness (fixture median fill-ratio ~0.74 vs the full corpus's documented ~0.82), and
names the full 199-plan corpus (`backend/spikes/architectural_brain/corpus/` on branch
`integration/poc-architectural-brain`, not present on this branch) as the natural next measurement.

### Required behavior

1. On an integration branch (or worktree) where `backend/spikes/architectural_brain/corpus/` is
   reachable, run `measure_real_plan_shapes.py --corpus-dir backend/spikes/architectural_brain/corpus`
   (both the default 1.0 m² artefact filter and `--min-room-area-m2 0`) and commit the resulting
   report alongside the 20-plan sample's own numbers for direct comparison.
2. State explicitly, per share (room rectangle/L/other, envelope rectangle/L/other,
   guillotine-separable true/false), whether the full-corpus number confirms or revises the 19-plan
   sample's directional finding, with the delta and its likely cause (sample-size noise vs a real
   selection-bias effect from the fixture's own circulation-class-diversity curation).
3. No change to the measurement script's own logic unless the full-corpus run surfaces a bug the
   19-plan sample did not exercise (e.g. a shape or edge case absent from the smaller fixture) — if
   so, fix it, re-run BOTH corpora, and record the fix in the report.

### Acceptance Criteria

- AC-1: the full-corpus measurement report exists, states every share from Issue #102's report §3 recomputed on n=199 (or whatever subset the corpus yields after the same synthetic-plan exclusion), with the 19-plan sample's numbers shown alongside for comparison
- AC-2: the report states explicitly whether the 0/19 guillotine-separability finding holds, weakens, or strengthens at full-corpus scale
- AC-3: if the measurement script needed a fix to run on the full corpus, `tests/spikes/test_measure_real_plan_shapes.py` still passes unchanged (the 19-plan fixture's frozen numbers are untouched) and the fix is documented in the report

### Out of scope

Any architecture decision (that is child 2/3's job); any change to `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`'s own recommendation (this child only firms up its evidence); copying the full 199-plan corpus into this repo's committed fixtures (read it from wherever the integration branch/worktree makes it reachable; do not duplicate ~5 MB of licensed data into a second location without a separate decision).

### Affected domains

knowledge, qa

### Risk

LOW

### Resource class

LIGHT

### Dependencies

none

### Required locks

knowledge-index (shared)

### Verification plan

- AC-1 -> TEST:pytest:backend/tests/spikes/test_measure_real_plan_shapes.py
- AC-1 -> ARTIFACT:file:docs/reports/non-rectangular-geometry-full-corpus-remeasurement.md
- AC-2 -> ARTIFACT:grep:docs/reports/non-rectangular-geometry-full-corpus-remeasurement.md:guillotine-separable
- AC-3 -> TEST:pytest:backend/tests/spikes/test_measure_real_plan_shapes.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/reports/non-rectangular-geometry-full-corpus-remeasurement.md (new).

### Knowledge check

Consulted: `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §3 (Issue #102), `backend/spikes/geometry_shapes/measure_real_plan_shapes.py`, `docs/reports/poc-architectural-brain/dataset.md` (branch `integration/poc-architectural-brain`, corpus provenance/size). Depends on the ROOT (`root-102-non-rectangular-geometry.md`) being queued.
