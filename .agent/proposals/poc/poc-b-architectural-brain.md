# [agent] POC Architectural Brain (B/3): retrieval of real references, ConceptSpec synthesis from several references, semantic adaptation to the brief, and the Architect Model hint investigation

### Goal

The brain: given a BuildSmart Brief + Site + hard requirements, retrieve 5–10 architecturally relevant real plans
from the POC corpus (with WHY), synthesize 2–3 candidate ConceptSpecs that combine patterns from several
references (never one copied or scaled plan), adapt at least one concept to the target brief by semantic /
topological operations, and report whether the existing Architect Model can supply non-authoritative hints.

### Current behavior

Concept Engine v2's `concept_patterns.py` orders SPINE / FRONT_BAND / HUB_LOBBY patterns from 36 synthetic
archetypes; `plans_per_class` realizes one plan per class from the generator's own candidates; no real plan
informs anything. `ConceptSpec` / `CirculationClass` / `ZoningSplit` exist in `concept_spec.py`;
`ArchitectModelGateway` exists in `app/architect/gateway.py` with `authoritative_merge` (requirements always win).

### Required behavior

1. `backend/spikes/architectural_brain/retrieval.py`: `retrieve(brief, site, corpus, k=8) -> list[RetrievedReference]`
   — a deterministic weighted score over architectural terms, NOT text embeddings: built area, room count and types,
   footprint aspect / shape, adjacency requirements (`ProgramSpec.relationships`), public/private organisation,
   circulation class, floors, wet-room requirements, exterior-exposure constraints; each result carries the per-term
   contributions and a one-paragraph WHY. Weights documented; a brief with an L outline must not retrieve only by area.
2. `backend/spikes/architectural_brain/synthesis.py`: `synthesize(brief, references) -> list[ConceptSpec]` — 2–3
   candidates whose zoning / circulation class / wet-core strategy / entrance relationship / bedroom grouping are
   taken from DIFFERENT references' patterns and recorded in `ConceptSpec.references` (plan_id, pattern_used, why);
   candidates must be pairwise `topologically_distinct`; a synthesized concept is never a single reference's room
   list. Authoritative requirements always win: SAFE_ROOM, wet-room kinds, corridor width, relationships, the site.
3. `backend/spikes/architectural_brain/adaptation.py`: `adapt(concept, brief, site) -> AdaptedConcept | Rejection` —
   semantic/topological operations only (resize rooms preserving topology, add/remove a bedroom node, move the wet
   zone relationship, change public/private proportions, adapt footprint proportions to the buildable region,
   mirror/rotate by street side, shorten circulation), each recorded as `Adaptation{kind, before, after, reason}`;
   global scaling of a reference is forbidden (a test asserts room-area ratios change non-uniformly); a reference
   that cannot be adapted (e.g. no place for the SAFE_ROOM, wet core unreachable) is rejected with a stated reason.
4. `docs/reports/poc-architectural-brain/architect-model.md`: read-only investigation of `app/architect` — which of
   brief interpretation / zoning suggestion / relationship suggestion / choosing among retrieved patterns / ConceptSpec
   hints the existing gateway could serve, as `ArchitectModelHints` (Concept Engine child 1) — non-authoritative, no
   fine-tuning; a fake-gateway test shows a hint contradicting a requirement is dropped and reported.

### Acceptance Criteria

- AC-1: on the fixture corpus, retrieval for each of the 3 benchmark briefs returns 5–10 references with per-term scores and WHY, deterministic across runs, and never orders by area alone (a test brief with the same area but a different programme retrieves a different top-3)
- AC-2: synthesis produces 2–3 pairwise topologically distinct ConceptSpecs per benchmark brief, each citing ≥ 2 references with pattern_used and why, and every authoritative requirement of the brief (SAFE_ROOM, wet-room kinds, bedrooms) is present in every candidate
- AC-3: adaptation records ≥ 1 semantic operation per adapted concept, changes room-area ratios non-uniformly (no global scaling), and rejects an unadaptable reference with a reason on a synthetic case
- AC-4: the Architect Model investigation is committed and a fake-gateway test proves hints never override authoritative requirements

### Out of scope

Realization, validators, SVG demo (C); new fine-tuning; text-embedding retrieval; changing `app/`.

### Affected domains

backend, ai, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#94

### Required locks

planner-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_retrieval.py
- AC-2 -> pytest:backend/tests/architectural_brain/test_synthesis.py
- AC-3 -> pytest:backend/tests/architectural_brain/test_adaptation.py
- AC-4 -> file:docs/reports/poc-architectural-brain/architect-model.md ; pytest:backend/tests/architectural_brain/test_architect_hints.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/architect-model.md (new), docs/reports/poc-architectural-brain/brain.md (retrieval weights, synthesis and adaptation rules).

### Knowledge check

Consulted: the ROOT's shared contracts, `concept_spec.py` (`ConceptSpec`, `CirculationClass`, `topologically_distinct`),
`concept_patterns.py`, `app/vertical_slice/spec.py` (`ProgramSpec.relationships`, `HouseConcept`), `app/architect/gateway.py`,
`app/architect/authoritative_merge.py`, `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md` §4–§6, agent A's `plan_reference.py` and fixture.
