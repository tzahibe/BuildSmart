# [agent] Concept Engine v2 (2/5): structured concept pattern prior — pattern records from the census aggregates and the reference archetypes, deterministic lookup per brief

### Goal

Turn the architectural references into a real prior for the concept stage: a small structured table of
concept *patterns* (circulation class × zoning split × wet-core grouping × master placement × applicability)
with frequencies, and a deterministic lookup that returns, for a brief and an outline, the ordered list of
2–3 pattern classes to try. Descriptive metadata only — never geometry, never images.

Execution order inside the ROOT: after CE2-1 (the Issue numbers are filled in by `agentctl issue decompose` at creation).

### Current behavior

`docs/architecture_reference/references/index.json` has 36 metadata-only archetype entries (footprint family,
bedrooms, bathrooms, levels, area, tags, prose annotations) and no structured concept fields; the benchmark
(`reference_benchmark.py`) uses references only by footprint family and area range. The 21-plan census exists
as aggregates in `specs/005-hub-private-wing/spec.md` §1 (room lobby ~18/21, straight corridor 0/21, wet
back-to-back ~20/21, 13/21 non-rectangular). Nothing in the product asks "which organisation do architects
use for this kind of brief".

### Required behavior

1. `references/schema.json` gains an optional `concept` block per entry: `circulation_class`, `zoning_split`,
   `wet_core_grouping`, `master_placement`, `entrance_side` (enums shared with `concept_spec.py`); the 36
   archetype entries are filled from their own annotations/tags (a `test_reference_index` check keeps the
   block consistent with the annotation's stated organisation).
2. `backend/app/vertical_slice/concept_patterns.py`: pattern records with `applicability` (footprint
   family, width band, depth band, bedrooms range, wet-rooms range, single/multi level) and a `frequency`
   sourced from the census aggregates (documented per record with its source line); `patterns_for(brief,
   outline) -> tuple[Pattern, ...]` — deterministic, keyed by `reference_benchmark.classify_footprint_family`,
   the outline's width/depth and the programme counts; ties broken by documented order.
3. A rights note in `references/README.md`: structured concept records are descriptive metadata under the
   existing policy; per-plan records for the census plans are an optional owner-supplied follow-up.
4. No runtime behavior change: nothing in the pipeline calls `patterns_for` yet.

### Acceptance Criteria

- AC-1: every entry of `index.json` validates against the extended schema and carries a `concept` block consistent with its annotation
- AC-2: `patterns_for` returns ≥ 2 distinct circulation classes for every footprint family × programme combination present in the frozen corpus, deterministically (same result across runs)
- AC-3: every pattern record cites its evidence source (census line or archetype ids)
- AC-4: the frozen corpus is unchanged

### Out of scope

Curating the 21 census plans into per-plan records (owner decision); any ML/embedding retrieval; using the
prior in selection (CE2-4).

### Affected domains

knowledge, backend, qa

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

none

### Required locks

knowledge-index (shared), docs (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/reference/test_reference_index.py
- AC-2 -> pytest:backend/tests/vertical_slice/test_concept_patterns.py::test_patterns_for_returns_two_classes_for_every_corpus_family
- AC-3 -> pytest:backend/tests/vertical_slice/test_concept_patterns.py::test_every_pattern_cites_its_source
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/architecture_reference/references/{README,schema.json,index.json} (concept block), docs/wiki/architecture/
knowledge-system.md (the prior is product data, not the RAG), docs/CONCEPT_ENGINE_V2_INVESTIGATION.md §4 link.

### Knowledge check

Consulted: `references/README.md` (rights policy, V1 provenance: archetypes, not real plans), `index.json`
profile (36 entries; tags spine 5 / hub-lobby 4 / front-band 3 / two-wing 6 / courtyard 2; annotations mention
lobby/hub in 19, corridor in 25), `reference_benchmark.py::classify_footprint_family`, `specs/005/spec.md` §1,
memory `architectural-quality-gaps-measured`, `backend/app/knowledge` (document search — not the tool for a
structured table).
