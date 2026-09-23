# [agent] Concept Engine v2 rollup repair: the flag-ON path must pass against current main before #74 lands

### Goal

The owner asked for ROOT #74 to reach `main` as ONE rollup, entirely behind
`CONCEPT_ENGINE_V2_ENABLED = False`, with zero behaviour change (2026-09-23), so the branch stops
rotting. The lead merged current `main` into `integration/concept-engine-v2` (commit `145f582`,
six conflicts, all "keep both sides"). Flag OFF is clean; flag ON, eight of the branch's own tests
now fail because `main` moved underneath it. Make the flag-on path pass again so rollup PR #129
can merge on green gates rather than on a promise.

### Current behavior

`backend/tests/vertical_slice/test_concept_compilers.py` fails 8 tests against the merged branch.
The head failure is `test_branched_concept_realizes_with_all_bedrooms_on_a_hall`: the realized
BRANCHED plan is refused with `3 corridor dead ends exceeds 2` — C26's dead-end rule (Issue #36,
and the entrance-sequence work of #22, both merged to main after this branch was cut) counts the
BRANCHED parti's two hall segments as producing three dead ends. `compile_branched`'s own two-hall
geometry (HALL_A under the public band, HALL_B beside the bedroom stack, meeting at a corner over
a partial shared edge) was authored before that rule existed. The other failures are the same
fixture family (`branched_open`, `branched_safe_open`, and the variants around them).

### Required behavior

1. The flag-on tests pass against current `main` — the compiled BRANCHED geometry satisfies C26 as
   it now stands, or the compiler declines that programme with a stated reason instead of emitting
   a plan the validators refuse. Both are acceptable outcomes; silently loosening C26 is not.
2. No validator, threshold or hard limit is changed, and `CONCEPT_ENGINE_V2_ENABLED` stays `False`.
3. The flag-off corpus stays byte-identical: this branch must land as zero behaviour change.
4. If the honest outcome is that `compile_branched` cannot satisfy the current circulation rules
   for its own canonical fixture, say so in the diversity report and let the compiler refuse —
   Issue #111 already measured that these compilers never fire on any real benchmark brief, so a
   narrower compiler costs the product nothing and a false green costs it trust.

### Acceptance Criteria

- AC-1: `backend/tests/vertical_slice/test_concept_compilers.py` passes in full against the merged branch
- AC-2: `backend/tests/test_concept_engine_v2.py` passes in full
- AC-3: with the flag OFF the frozen 432-context corpus is byte-identical to main (LOST 0, primary_signature_changes 0)
- AC-4: no validator, threshold or hard limit is changed by this Issue (review target), and any compiler that now declines a programme states its reason

### Out of scope

Generalizing the compilers' programme preconditions (owner 2026-09-23: they stay as
reference/fallback candidates); switching the flag on; anything in ROOT #127's Stage 2 scope.

### Affected domains

backend, geometry, validator, qa

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

none

### Required locks

geometry-core (shared), validator-core (shared), planner-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_concept_compilers.py
- AC-2 -> pytest:backend/tests/test_concept_engine_v2.py
- AC-3 -> regression:corpus
- AC-4 -> pytest:backend/tests/vertical_slice/test_concept_compilers.py
- AC-4 -> review:no validator, threshold or hard limit was changed, and a compiler that declines a programme states its reason

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/concept-engine-v2-diversity-report.md (if the compiler's supported programme narrows), docs/wiki/features/concept-engine-v2.md (the same, once it lands).

### Knowledge check

Consulted: `concept_compilers.py` and its own docstring on why HALL_A/HALL_B use a CASED_OPENING rather than an
open group; `circulation_metrics.py`'s dead-end rule (#36) and `entrance_sequence.py` (#22), both merged to main
after this branch was cut; `docs/reports/concept-engine-v2-diversity-report.md`; #111's measurement that neither
compiler fires on any of the three fixed benchmark briefs.
