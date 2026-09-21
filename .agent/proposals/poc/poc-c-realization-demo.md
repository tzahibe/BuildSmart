# [agent] POC Architectural Brain (C/3): realization through the existing engine and validators, 3 fixed benchmark briefs, measurements, side-by-side visual demo and the GO / MODIFY / STOP report

### Goal

Close the loop and make the POC judgeable by eye: run the brain's ConceptSpecs through the EXISTING Geometry Core,
doors / windows / entrance logic, validators, quality metrics and ranking; define 3 fixed benchmark briefs; render
side-by-side SVGs (A current engine vs B real-plan brain, ≥ 2 genuinely different alternatives for one brief);
measure current vs POC; write the report that answers the final question with GO / MODIFY / STOP.

### Current behavior

`general_pipeline.run_general` realizes `ConceptCandidate`s (`_realize`, doors, windows, validation, assembly);
Concept Engine v2's `plans_per_class` / `concept_score` / `realized_circulation_class` (branch
`integration/concept-engine-v2`) score and verify realized plans; `render(design, path)` writes SVG; `quality_metrics`
(M1–M6), `circulation_metrics` (#36), `entrance_sequence`, `wet_core`, `reference_benchmark` exist. Nothing
realizes a concept that did not come from `concept_generator`.

### Required behavior

1. `backend/spikes/architectural_brain/realize.py`: `realize_concept(concept: ConceptSpec, brief, site) ->
   RealizedPlan | Refusal` — compiles the adapted ConceptSpec into a Geometry Core `Fixture` (slicing tree + zones +
   access) using Concept Engine v2's compilers where they exist and a minimal spike compiler otherwise, then the
   unchanged `_realize` chain and validators; `realized_circulation_class` verifies the class; no validator is
   disabled, no hard limit relaxed; refusals carry the failing checks.
2. `backend/tests/architectural_brain/briefs.py`: 3 FIXED benchmark briefs (contexts in the demo request shape):
   (1) the challenging family home — 4 bedrooms + SAFE_ROOM + 3 wet rooms, ~200 m², plot 17×30.5 m, street north;
   (2) the owner's own brief — 4 bedrooms (3 + master ensuite), 2 wet rooms, laundry, open plan, 130 m², plot
   15×17 m; (3) a wide 5-bedroom home, 200 m², plot 27×20.5 m; each with the current engine's result recorded as
   the baseline.
3. `backend/spikes/architectural_brain/demo.py`: for each brief renders `current.svg` and `brain-A/B/C.svg` (one per
   synthesized alternative that realized), plus `references.md` (the retrieved references with WHY, the extracted
   ideas: circulation / zoning / public-private / wet-core / entrance strategy) and `comparison.md` (what adaptation
   changed, the measurements table) under `docs/reports/poc-architectural-brain/brief-N/`.
4. Measurements (existing signals wherever they exist): circulation-area ratio (M3), longest corridor / path
   (`circulation_metrics`), dead space (residual pockets), public/private separation, wet-room clustering (M5 /
   `wet_core`), exterior exposure (M2), entrance integration (`entrance_sequence`), circulation nodes, topology
   class (`realized_circulation_class`), room-area compliance, hard-validator failures, furnishability if available.
5. `docs/reports/poc-architectural-brain/README.md`: the visual before/after page (all SVGs inline), the measurements
   table, the honest failure-criteria checklist and the recommendation GO / MODIFY / STOP, answering: "Did access to
   real architectural experience give BuildSmart an architectural brain that is visibly better than the current
   hand-designed concept generator?"

### Acceptance Criteria

- AC-1: for at least one benchmark brief ≥ 2 realized alternatives have different `realized_circulation_class` values, none SPINE-only duplicates, and all pass every existing hard validator (0 failures in the validation report)
- AC-2: every realized POC plan is produced by the unchanged `_realize` chain — the diff touches no file under `app/vertical_slice/validation.py`, `geometry_core/`, `doors.py`, `windows.py` (review target) — and the demo lists each realized plan's validation result
- AC-3: the 3 benchmark briefs are fixed fixtures whose current-engine baseline is recorded and re-rendered deterministically
- AC-4: `docs/reports/poc-architectural-brain/README.md` shows the side-by-side SVGs for all 3 briefs with references + WHY, extracted ideas and adaptation changes, the measurements table, and a GO / MODIFY / STOP recommendation with the failure-criteria checklist

### Out of scope

Changing Geometry Core, validators, doors/windows logic; merging anything to main; production UI integration.

### Affected domains

backend, geometry, validator, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#94

### Required locks

planner-core (shared), geometry-core (shared), validator-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_demo_alternatives.py::test_one_brief_yields_two_different_verified_topologies_that_pass_every_validator
- AC-2 -> pytest:backend/tests/architectural_brain/test_demo_alternatives.py::test_poc_plans_come_from_the_unchanged_realize_chain ; review:the diff changes nothing under app/vertical_slice/validation.py, geometry_core/, doors.py or windows.py, and no validator or hard limit is bypassed for the POC plans
- AC-3 -> pytest:backend/tests/architectural_brain/test_benchmark_briefs.py
- AC-4 -> file:docs/reports/poc-architectural-brain/README.md ; grep:docs/reports/poc-architectural-brain/README.md:Recommendation

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/README.md, brief-1..3/ (new).

### Knowledge check

Consulted: `general_pipeline.py` (`_realize`, `render`, `RealizedPlan`), Concept Engine v2 branch (`concept_engine_v2.py::plans_per_class`,
`concept_score.py`, `concept_spec.py::realized_circulation_class`, the compilers if #79 landed), `quality_metrics.py`,
`circulation_metrics.py`, `entrance_sequence.py`, `wet_core.py`, `reference_benchmark.py`, `spikes/failure_log_sweep/sweep.py`
(`project_from_context`), the diversity measurements in `docs/reports/concept-engine-v2-owner-benchmark.md`, agent A's fixture and
agent B's interfaces.
