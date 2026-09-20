# [agent] EPIC 0 — Architectural reference set, quality rubric, anti-pattern library and reference benchmark (P0 / foundation)

### Goal

Give the Team Lead, the Sonnet workers and the independent reviewers a real architectural reference
framework — what a good residential plan looks like — instead of learning only from BuildSmart's own
output. Strictly architectural references (what good planning looks like); regulation/compliance
knowledge stays a separate corpus. Executed through child Issues (rubric + anti-patterns, reference
collection with metadata, annotations, benchmark framework, reviewer integration).

### Current behavior

Architectural quality is measured today only by the M1–M6 corpus metrics
(`backend/app/vertical_slice/quality_metrics.py`, Issue #17: habitable aspect, envelope exposure,
circulation share, hall door count/aspect, wet adjacency, public-zone contiguity) against a frozen
no-regression baseline, plus the `hub_guard`/`l_massing_guard` comparators. There is no reference set of
good plans, no metadata schema for them, no written rubric (`docs/architecture_reference/` does not
exist), no anti-pattern library, and reviewers get only the diff, the contract and CI evidence — nothing
that says what "better architecture" means.

### Required behavior

1. `docs/architecture_reference/quality_rubric.md`: the canonical rubric with sections A–O (entrance
   sequence, circulation efficiency, public/private zoning, public-zone composition, bedroom privacy,
   furnishability, door usability, window/exterior exposure, wet-room privacy/access, wet-core efficiency,
   dead-space minimization, area/dimension consistency, master-suite quality, outdoor relationship,
   architectural clarity), each with: principle, deterministic signal(s) that exist or are planned, what
   reference comparison adds, what only semantic review can judge. Never LLM opinion alone.
2. `docs/architecture_reference/anti_patterns.md`: the anti-pattern library (long corridor, entrance
   facing an arbitrary wall, dead entrance pocket, corridor extended to façade, door–door / door–fixture
   collisions, unusable bedroom proportions, no practical furniture layout, isolated wet room, unnecessary
   turns, sliver space, circulation crossing furniture zones, window on a non-exterior wall, area labels
   inconsistent with geometry), each with a detection signal (existing check/metric or a proposed one).
3. `docs/architecture_reference/references/`: a curated V1 set of ~30–50 residential plans (private houses
   first, single-level first, footprints rectangle / wide / narrow-deep / L / irregular) with the metadata
   schema (`references/README.md` + `references/index.json`) — source id, built area, bedrooms, bathrooms,
   floors, footprint family, entrance location, zoning, kitchen/dining/living relationships, circulation
   structure, wet-room grouping, bedroom exposure, master-suite organization, service spaces, parking,
   outdoor connection, strengths, trade-offs. Only owner-provided, public-domain or openly licensed
   material is copied; otherwise metadata + link + notes. No model is trained on unlicensed plans.
4. Annotations: for each useful reference a short "WHY THIS PLAN WORKS" note tied to rubric sections.
5. Benchmark framework (`backend/app/vertical_slice/reference_benchmark.py` + `agentctl`/script entry):
   compares a generated plan against the rubric's deterministic signals and the relevant reference
   patterns (by footprint family / programme) and prints findings per section (e.g. "Circulation:
   dedicated circulation 16.9 m², ratio X% — high relative dedicated circulation"). References teach
   principles, never exact geometry: no generated plan is compared coordinate-by-coordinate to a reference.
6. Reviewer integration: the independent reviewer's prompt points at the rubric, the annotations and the
   anti-pattern library for geometry/circulation/interior PRs and asks "does this change improve
   architectural behavior according to the accepted principles?"; deterministic tests remain
   authoritative — a failing deterministic validation is never turned into PASS by the semantic review.

### Acceptance Criteria

- AC-1: `docs/architecture_reference/quality_rubric.md` exists with sections A–O, each naming its deterministic signal(s), reference comparison and semantic-review part
- AC-2: `docs/architecture_reference/anti_patterns.md` lists every anti-pattern above with a detection signal
- AC-3: `docs/architecture_reference/references/index.json` validates against `references/schema.json` and holds ≥ 30 entries with the metadata fields, each with a rights status (owner / public-domain / open-license / metadata-only)
- AC-4: every entry in the index has an annotation file with a WHY THIS PLAN WORKS section referencing rubric sections
- AC-5: `reference_benchmark.py` produces a per-section report for a corpus plan and a unit test proves the circulation and entrance findings on a fixture
- AC-6: the reviewer prompt template references the rubric, annotations and anti-pattern library and states that deterministic validation stays authoritative

### Out of scope

Regulatory/compliance knowledge (separate corpus and Issue), training any model, changing planner
behavior (the benchmark measures; product Issues change behavior), copying plans whose rights are unclear.

### Affected domains

knowledge, qa, backend, infra

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

none

### Required locks

docs (shared), knowledge-index (shared), ci-infra (shared)

### Verification plan

- AC-1 -> file:docs/architecture_reference/quality_rubric.md ; grep:docs/architecture_reference/quality_rubric.md:## O\.
- AC-2 -> grep:docs/architecture_reference/anti_patterns.md:dead entrance pocket ; grep:docs/architecture_reference/anti_patterns.md:door-fixture
- AC-3 -> pytest:backend/tests/reference/test_reference_index.py::test_index_validates_and_has_at_least_thirty_entries
- AC-4 -> pytest:backend/tests/reference/test_reference_index.py::test_every_entry_has_an_annotation_with_why_it_works
- AC-5 -> pytest:backend/tests/reference/test_reference_benchmark.py::test_benchmark_reports_circulation_and_entrance_findings
- AC-6 -> grep:scripts/agent_team/prompts/reviewer.md:quality_rubric ; grep:scripts/agent_team/prompts/reviewer.md:deterministic

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/* (new), docs/wiki/INDEX.md (link), docs/PROJECT_STATE.md (capability row), docs/wiki/architecture/agent-team-workflow.md (reviewer integration).

### Knowledge check

Consulted: `docs/PROJECT_STATE.md`, `docs/wiki/architecture/geometry-validation.md` (C-checks, M1–M6 baseline
from #17), `docs/wiki/architecture/knowledge-system.md` (Wiki-first + RAG; regulation corpus is separate),
`backend/app/vertical_slice/quality_metrics.py`, `hub_guard.py`, `l_massing_guard.py`,
`scripts/agent_team/prompts/reviewer.md`, memory "architectural-quality-gaps-measured" (21 professional plans
were measured once for hub aspect / wet adjacency / strip rooms — evidence, not a curated set). What exists:
deterministic metrics and a no-regression baseline. What remains: everything in Required behavior. Nothing
here is implemented, so the ROOT is opened and decomposed.
