# [agent] Concept Engine v2 (3/5): concept-level score from existing realized metrics and the bounded realize–measure–adapt loop per circulation class

### Goal

The quality feedback loop of the hybrid stage as pure, offline-measured functions: a `concept_score` that
reads a realized plan's existing deterministic metrics, and an `adapt(concept_spec, plan, score)` step that
changes the CONCEPT (wet-core clustering, witness-based sizing, zoning flip) — never the geometry — inside a
bounded number of realizations per circulation class.

Execution order inside the ROOT: after CE2-1 (the Issue numbers are filled in by `agentctl issue decompose` at creation).

### Current behavior

Every deterministic signal runs on realized geometry (M1–M6, `hub_guard.proportions_of`, `l_massing_guard`,
`wet_privacy`, `wet_core`, C24/C19); realization costs ≈ 165 ms per candidate. The only feedback loops are
one-pair comparisons after selection (`_guard_demoted_hub`, `_prefer_quality_twin`, `l_massing_guard`) and the
hub witness sizing (`hub_bound` → `_plan_hub_wing(witness=…)`, 008 follow-up: 4/4 eligible hubs pass all
gates after re-sizing). Nothing scores a plan as a concept or adapts a concept from what its realization
measured.

### Required behavior

1. `backend/app/vertical_slice/concept_score.py`: `concept_score(plan) -> ConceptScore` — a pure function of
   `RealizedPlan`/`DemoDesign` data: M1 bedroom/master aspects, M3, M4 (class verification), M5 wet adjacency,
   `wet_core` grouping, entrance rank (#20), `hub_guard.PlanProportions`; extensible hooks for #36 circulation
   metrics and #43 residual pockets when they land; documented weights and a total order with a deterministic
   tie-break (index). C24/C19 symbolic pre-checks on the access edges / envelope leaves reject a concept
   before solving.
2. `adapt(spec, plan, score) -> ConceptSpec | None`: the bounded adaptation ladder — cluster the shared wet
   rooms (the `SPINE_SERVICE_CLUSTER` move / hub head), re-size from a witness (008 pattern), flip the zoning
   split, or give up; at most `ADAPT_LIMIT` (proposal: 2) re-realizations per class.
3. `spikes/failure_log_sweep/concept_adaptation_report.py`: offline, for the frozen corpus, per class: how
   often the first realization is accepted, adapted, or dropped, and the score deltas; committed as
   `docs/reports/concept-engine-v2-adaptation-report.md`.
4. No runtime behavior change: not wired into `run_general`.

### Acceptance Criteria

- AC-1: `concept_score` is deterministic across runs and process restarts on the canonical fixtures and orders a verified hub-lobby plan above a spine plan of the same programme when its M4/M5 are better and its M1 is not worse
- AC-2: `adapt` never returns a spec whose class differs from the input's class and stops after `ADAPT_LIMIT`
- AC-3: the adaptation report exists with the per-class accept/adapt/drop counts on the frozen corpus
- AC-4: the frozen corpus is unchanged

### Out of scope

Wiring into the pipeline (CE2-4); changing `hub_guard`/`l_massing_guard`/quality-twin decisions; new
validators; multi-level.

### Affected domains

backend, geometry, validator, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#75

### Required locks

planner-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_concept_score.py::test_score_is_deterministic_and_prefers_verified_lobby_over_spine
- AC-2 -> pytest:backend/tests/vertical_slice/test_concept_score.py::test_adapt_keeps_class_and_respects_limit
- AC-3 -> file:docs/reports/concept-engine-v2-adaptation-report.md
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/concept-engine-v2-adaptation-report.md (new); docs/CONCEPT_ENGINE_V2_INVESTIGATION.md §5 link.

### Knowledge check

Consulted: `quality_metrics.py` (M1–M6 on the `DemoDesign` shape), `hub_guard.py`, `l_massing_guard.py`,
`wet_privacy.py`, `wet_core.py`, `access_rules.py` (C24 table), `exposure_policy.py` (C19 table),
`concept_generator.py` (`hub_bound`, `_plan_hub_wing(witness)`, `_allocations` wet-cluster move),
`general_pipeline.py` cost comment (:114–121), `specs/005/RESULTS.md` §7–§9, backend domain-lead brief.
