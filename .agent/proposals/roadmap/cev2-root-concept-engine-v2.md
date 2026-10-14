# [agent] Concept Engine v2: hybrid pattern-prior concept stage — 2–3 topologically different concepts per brief, feature-flagged

### Goal

Replace "one hall spine, ranked by area" with a concept stage that (1) asks a structured architectural
prior which circulation structures / zoning splits / wet-core groupings fit this brief and this outline,
(2) compiles them into concepts through the existing pattern builders, (3) realizes, measures and adapts
each concept with the engine's own deterministic metrics, and (4) shows the person one best plan per
circulation class. Behind a flag; the primary plan is byte-identical until the owner decides otherwise.
Evidence and architecture: `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md`. Executed through child Issues.

### Current behavior

`concept_generator.generate_concepts` builds ~28 candidates per brief from five `_allocations` that share
ONE tree shape (`V[column, HALL, column]`) plus a front-band tree; the hub is offered as a peer on 4/432
corpus contexts and the L only with two safe wings; the ranking is `|used_area − target|` with no topology
term; `run_general` takes the first realizable candidate. Measured on 60 PLANNED corpus contexts through
the real service: 0 briefs show a plan with a compact hall (M4 ≤ 1.5) or a hub, hall long/short median
9.07, every shown plan's family signature has the spine root; M5 wet adjacency median 0.0. The census
of 21 professional plans has a room lobby in ~18/21 and a straight corridor in 0/21.

### Required behavior

1. A `ConceptSpec` contract and an explicit `circulation_class` on every concept candidate, verified on
   the realized plan (CE2-1).
2. A structured concept prior (`concept_patterns`) derived from the census aggregates and the reference
   archetypes' tags — descriptive metadata only, rights-safe — with a deterministic lookup by footprint
   family, width/depth band, bedrooms and wet rooms (CE2-2).
3. A pure `concept_score` over existing realized metrics and a bounded realize–measure–adapt loop per
   circulation class (wet-core clustering, witness sizing, zoning flip) (CE2-3).
4. The stage wired into `run_general` behind `CONCEPT_ENGINE_V2_ENABLED` (default False): flag-off
   byte-identical; flag-on, the alternatives become one best plan per circulation class with a concept
   label the ReviewPage shows (CE2-4). A BRANCHED class is a decision-gated child (CE2-5).
   **Owner conditions (approval of 2026-09-20):** (a) the PRIMARY plan stays unchanged until the owner has
   seen CE2-4's results — no child of this ROOT may change which plan is primary; (b) CE2-5 is conditional
   only: it exists as a draft child and is queued solely on the owner's explicit decision after CE2-4.
5. Acceptance number of the ROOT: on the frozen corpus with the flag on, the share of PLANNED briefs whose
   shown set contains ≥ 2 distinct circulation classes rises from 0 % to ≥ 40 %, with LOST 0 and
   primary_signature_changes 0.

### Acceptance Criteria

- AC-1: `topologically_distinct(a, b)` and the `circulation_class` verifier exist as pure functions with unit tests (spine vs hub distinct; two spine relabelings not distinct)
- AC-2: `concept_patterns` returns a deterministic ordered list of pattern classes for a brief, covered by tests for every footprint family
- AC-3: `concept_score` and the adaptation loop are pure, deterministic and unit-tested; the offline corpus report of CE2-3 is committed
- AC-4: with `CONCEPT_ENGINE_V2_ENABLED = False` the frozen-corpus snapshot is identical to the base (LOST 0, primary_signature_changes 0, refusal codes identical)
- AC-5: with the flag on, the committed corpus diversity report shows ≥ 40 % of PLANNED briefs with ≥ 2 circulation classes among the shown plans, LOST 0 and primary_signature_changes 0
- AC-6: the wallclock budget test bounds the flag-on cost per brief

### Out of scope

Changing which plan is the PRIMARY (owner decision after CE2-4's report); Geometry Core changes; ring /
courtyard circulation; multi-level wiring; curating the 21 census plans into per-plan records (optional
knowledge follow-up); any change to validators' hard limits.

### Affected domains

backend, geometry, validator, knowledge, frontend, qa

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

#28, #17

### Required locks

planner-core, geometry-core, validator-core, knowledge-index (shared), frontend-review (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_concept_topology.py
- AC-2 -> pytest:backend/tests/vertical_slice/test_concept_patterns.py
- AC-3 -> pytest:backend/tests/vertical_slice/test_concept_score.py ; file:docs/reports/concept-engine-v2-adaptation-report.md
- AC-4 -> regression:corpus
- AC-5 -> file:docs/reports/concept-engine-v2-diversity-report.md ; regression:corpus
- AC-6 -> pytest:backend/tests/test_concept_engine_v2_budget.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/CONCEPT_ENGINE_V2_INVESTIGATION.md (evidence, exists), docs/wiki/features/concept-engine-v2.md (new, when
flipped), docs/wiki/architecture/geometry-validation.md (concept stage pointer), docs/PROJECT_STATE.md,
docs/ROADMAP.md (replaces "Concept Quality / Decomposition Engine" and "Alternative Plans / Diversity").

### Knowledge check

Consulted: `docs/PROJECT_STATE.md`, `docs/wiki/architecture/geometry-validation.md`, `docs/wiki/features/
{l-massing,wet-rooms,room-proportion-quality-tier,review-page}.md`, `concept_generator.py` (`_allocations`,
`_build`, `_front_band_concept`, `_hub_concept`, `hub_bound`, ranking), `general_pipeline.py` (`run_general`,
`_realize`, `_alternative_plans`, `_family_signature`), `demo/service.py::_select_plans`, `geometry_core/
engine.py::_mark_open_interfaces` (open groups are subtrees), `quality_metrics.py`, `hub_guard.py`,
`l_massing_guard.py`, `wet_core.py`, `reference_benchmark.py`, `spec.py::HouseConcept`, `specs/005/
{spec,RESULTS}.md`, `specs/008`, `docs/MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md`, memories
`repetition-root-and-outline-sweep`, `architectural-quality-gaps-measured`, `corridor-opening-is-a-contract-
post-process`; two corpus measurements (80 + 60 contexts) and three read-only domain-lead briefs. What exists:
the concept contract (`ConceptCandidate`/`Fixture`), the pattern builders, all metrics, the comparators, the
flag pattern, the corpus tooling. What is missing: the class tag + verifier, the prior, the score/loop, the
per-class shown set. Nothing of this is implemented.
