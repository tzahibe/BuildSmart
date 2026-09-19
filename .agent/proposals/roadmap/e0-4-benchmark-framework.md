# [agent] Reference benchmark: generated plan vs quality rubric vs reference patterns, per-section findings

### Goal

A benchmark that reports, per rubric section, deterministic findings for a generated BuildSmart plan and
compares them with the relevant reference patterns (same footprint family / programme) — principles, not
geometry.

### Current behavior

`quality_metrics.py` computes M1–M6 per plan and a corpus summary; `spikes/failure_log_sweep/quality_metrics.py`
prints them. Nothing maps metrics to rubric sections, produces findings, or compares to references.

### Required behavior

1. `backend/app/vertical_slice/reference_benchmark.py`: `benchmark(design, references) -> BenchmarkReport` with
   one `SectionFinding` per rubric section that has a deterministic signal today (A entrance: arrival zone and
   first public opening; B circulation: dedicated circulation m², ratio, corridor length; C zoning; H exposure
   (C8/C19 data); K dead space (C2 residual + pockets when Issue 13 lands); L consistency (RoomOut width×depth
   vs area); others `not_measured`), each with value, reference range from the matching reference entries,
   and a finding sentence like the EPIC's example.
2. `backend/scripts/reference_benchmark.py --context <id>` and `agentctl benchmark <context>` print the report;
   the corpus sweep can emit it for every PLANNED context.
3. Reference comparison uses only metadata and derived ratios from `references/index.json` — never geometry.

### Acceptance Criteria

- AC-1: `benchmark()` returns findings for sections A, B, C, H, K, L on the canonical fixture with numeric values from realized geometry
- AC-2: a fixture with a long corridor yields the B finding `high relative dedicated circulation` and the canonical fixture does not
- AC-3: the reference range for a section comes from index entries of the same footprint family and the report names the entries used
- AC-4: the script prints the report for a corpus context

### Out of scope

Changing planner behavior; new validation checks (product Issues own those).

### Affected domains

backend, qa, knowledge

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

#29, #30

### Required locks

knowledge-index (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/reference/test_reference_benchmark.py::test_sections_with_signals_are_measured_on_the_canonical_fixture
- AC-2 -> pytest:backend/tests/reference/test_reference_benchmark.py::test_benchmark_reports_circulation_and_entrance_findings
- AC-3 -> pytest:backend/tests/reference/test_reference_benchmark.py::test_reference_range_uses_same_footprint_family
- AC-4 -> file:backend/scripts/reference_benchmark.py ; static:backend-import

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/quality_rubric.md (which signals are measured), docs/wiki/architecture/geometry-validation.md.

### Knowledge check

Consulted: `quality_metrics.py` (M1–M6, `measure_design`), the corpus snapshot (`corpus_snapshot.py` carries per-plan metrics since PR #23), `hub_guard.proportions_of`. What exists: metrics. What remains: rubric mapping, findings, reference ranges, CLI.
