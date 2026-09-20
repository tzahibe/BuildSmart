# [agent] Concept Engine v2 (1/5): ConceptSpec contract, circulation-class tag verified on the realized plan, topological distinctness and the corpus diversity report

### Goal

Make "topologically different" a deterministic, testable fact before any new concept is generated: a
`ConceptSpec` contract, an explicit `circulation_class` on every concept candidate that is verified against
the realized plan, a `topologically_distinct(a, b)` function, and a corpus diversity report that gives the
ROOT its acceptance number.

### Current behavior

A concept is a `ConceptCandidate` around a Geometry Core `Fixture`; `family_signature`
(`general_pipeline.py:211`) separates arrangements and prefixes `HUB:` but no circulation class exists as a
value; `massing_signature` is 1W/2W. Measured on 60 PLANNED corpus contexts: every shown plan has the spine
root `V[column, HALL, column]`, hall long/short median 9.07, 0 compact halls. Nothing reports how many
circulation classes a brief's shown set contains.

### Required behavior

1. `backend/app/vertical_slice/concept_spec.py`: `CirculationClass` enum (SPINE, FRONT_BAND, HUB_LOBBY,
   BRANCHED, RING, TWO_WING), `ZoningSplit` enum, `ConceptSpec` dataclass (class, zoning, wet-core grouping,
   programme reference, outline reference) and `ConceptCandidate.circulation_class` populated by the existing
   builders (spine allocations → SPINE, `_front_band_concept` → FRONT_BAND, `_hub_concept` → HUB_LOBBY,
   `l_parti` → TWO_WING). `HouseConcept.circulation_style` is mapped onto the same enum, not duplicated.
2. `realized_circulation_class(plan)` classifies a realized plan from its geometry (hall aspect via M4, door
   count, hall–room adjacency from `validation_stage.realized_connections`, wing count) and
   `verify_class(candidate, plan)` returns the mismatch, if any. Never inferred from the tree alone.
3. `topologically_distinct(a, b) -> bool` over (class, zoning split, `wet_core.WetCoreAlignment.groups()`
   partition); pure, deterministic, documented tie rules.
4. `spikes/failure_log_sweep/concept_diversity.py`: for the frozen corpus, per PLANNED brief the classes of
   the shown plans and the share of briefs with ≥ 2 classes; the report is committed as
   `docs/reports/concept-engine-v2-diversity-baseline.md` (the "before" number).
5. No behavior change: the tag is metadata; nothing in selection reads it.

### Acceptance Criteria

- AC-1: every candidate produced by `generate_concepts` on the canonical fixtures carries a `circulation_class` and `verify_class` finds no mismatch on the realized primaries of the corpus sample used in the tests
- AC-2: `topologically_distinct` returns True for a spine vs a hub candidate and False for two spine relabelings that share a `layout_signature`
- AC-3: the diversity baseline report exists and states the share of PLANNED briefs with ≥ 2 classes
- AC-4: the frozen corpus is unchanged (LOST 0, primary_signature_changes 0)

### Out of scope

Generating new concepts; changing ranking, selection or the shown set; the BRANCHED/RING classifiers beyond
"not produced today"; multi-level.

### Affected domains

backend, geometry, qa

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

none

### Required locks

planner-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_concept_topology.py::test_every_candidate_carries_a_verified_circulation_class
- AC-2 -> pytest:backend/tests/vertical_slice/test_concept_topology.py::test_topologically_distinct_spine_vs_hub_and_relabelings
- AC-3 -> file:docs/reports/concept-engine-v2-diversity-baseline.md ; grep:docs/reports/concept-engine-v2-diversity-baseline.md:briefs with
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/concept-engine-v2-diversity-baseline.md (new); docs/wiki/architecture/geometry-validation.md
(pointer to the concept contract, metadata only).

### Knowledge check

Consulted: `general_pipeline.py` (`RealizedPlan.family_signature/massing_signature`, `_family_signature`,
`realized_connections`), `concept_generator.py` (`ConceptCandidate`, builders), `quality_metrics.py` (M4),
`wet_core.py` (`WetCoreAlignment.groups`), `spec.py::HouseConcept.circulation_style` (read by nothing today),
`spikes/failure_log_sweep/{sweep,corpus_snapshot}.py`, `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md` §6.
