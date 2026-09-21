# [agent] POC — Architectural Brain from Real Floor Plans (ResPlan): retrieve real plans, extract architectural patterns, synthesize and adapt concepts, realize with the existing engine, compare visually against the current generator

### Goal

Prove visually and measurably that BuildSmart can use real architectural plans as experience / reference and
produce a better architectural concept than the current generator. A POC on an isolated branch
(`integration/poc-architectural-brain`, never merged to main), not production work. The final deliverable lets
the owner LOOK at side-by-side plans for 3 fixed briefs and answer: "does this actually look more like an
architect designed it?" — plus a clear GO / MODIFY / STOP recommendation. The final question: "Did access to
real architectural experience give BuildSmart an architectural brain that is visibly better than the current
hand-designed concept generator?" Owner specification: 2026-09-21 (chat), reproduced in the child contracts.

### Current behavior

Concepts come from `concept_generator.py`'s hand-written partis (SPINE / FRONT_BAND / HUB / L); Concept Engine v2
(#74, its own branch) adds ConceptSpec, priors from 36 synthetic archetypes, scoring and per-class alternatives,
but measured diversity stays at 17.6 % because the generator offers one topology. No real plan has ever been a
reference: the 36-entry reference set is metadata-only archetypes derived from our own census.

Verified 2026-09-21 by the Team Lead (dataset verification, done): ResPlan (Abouagour & Garyfallidis 2025,
arXiv 2508.14006; data CC BY 4.0, code MIT) = 17,107 single-floor residential plans from South Asian real-estate
listings — Apartment 15,854 / BuilderFloor 821 / Villa 384 / IndependentHouse 48; bedrooms 1: 1713, 2: 8454,
3: 5879, 4: 794, 5: 253, 6: 13; gross area median ~110 m². Each plan is a dict of Shapely (multi)polygons in
PIXEL coordinates (256-px canvas) keyed by the 17-class taxonomy — functional: living, bedroom, bathroom,
kitchen, balcony, storage, stair, garden, parking, pool, veranda; structural: wall, door, window, front_door;
boundary: inner (inhabitable envelope), land, neighbor (party walls) — plus `area` (gross m²), `net_area` (m²),
`wall_depth` (px), `unitType`, `id`, and a networkx `graph` (nodes living_i / kitchen_i / bedroom_i / bathroom_i /
balcony_i / front_door_0 with geometry, type, area; edges typed direct / adjacency / via_door / via_window). NO
hall/corridor category: circulation must be derived as `inner − rooms − walls`. The metric scale must be inferred
(`sqrt(area / inner.area_px)`, cross-checked with `wall_depth` ≈ 21 cm median). Front door present in ~99.9 %.
Downloaded to `/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl` (297 MB; read-only; never committed) with
LICENSE, README, `resplan_utils.py`. Typology gap to state honestly: South Asian apartments vs Israeli private
houses (site, street side, SAFE_ROOM, plot) — the references supply topology/zoning/wet-core/circulation priors
only; Site, Brief, hard constraints, SAFE_ROOM, geometry feasibility and validators stay authoritative.

### Required behavior

Executed through three child Issues sharing the contracts below (A → B ∥ C):

- **A — data / architectural representation:** ResPlan normalization into `PlanReference` JSON (metric scale,
  footprint, rooms with type / polygon / area / width / depth / exterior exposure, walls, doors, windows,
  adjacency and access graphs, entrance), derived semantics (zoning, circulation structure and class, public
  composition, bedroom grouping, wet-core strategy, entrance relationship, exposure pattern, circulation ratio)
  with explicit UNKNOWN, `ArchitecturalPattern` per plan by measurable rules, a 100–300-plan POC corpus biased to
  3–5 bedrooms + a 20-plan committed fixture, and the dataset/schema description.
- **B — architectural brain:** deterministic weighted retrieval (Brief + Site + hard requirements → 5–10 references
  with WHY), synthesis of 2–3 candidate `ConceptSpec`s combining patterns from several references (never one
  copied plan), semantic/topological adaptation to the target brief (resize / add-remove nodes / move wet zone /
  mirror / shorten circulation; reject with a reason when a reference cannot be adapted), and a read-only
  investigation of the existing Architect Model as a non-authoritative hint source.
- **C — realization / evaluation / demo:** the pipeline through the EXISTING Geometry Core, doors / windows /
  entrance logic, validators, quality metrics and candidate ranking (Concept Engine v2's `plans_per_class`,
  `concept_score`, `realized_circulation_class`); 3 fixed benchmark briefs (one challenging family home at the
  scale already tested); side-by-side SVG demo (A current engine vs B real-plan brain) with the retrieved
  references and WHY, the extracted ideas, and what adaptation changed; the measurements table; the
  GO / MODIFY / STOP report.

**Shared contracts (agents implement against these; A publishes the schema + fixture first):**
- `backend/spikes/architectural_brain/plan_reference.py`: `PlanReference` (id, source, unit_type, scale_m_per_px,
  footprint_polygon_m, rooms[{id, type ∈ BuildSmart ProgramRole vocabulary or UNKNOWN, polygon_m, area_m2, width_m,
  depth_m, exterior_exposure: N/E/S/W sides or UNKNOWN}], walls, doors[{polygon_m, rooms}], windows, entrance
  {room_id, side} or UNKNOWN, adjacency_edges, access_edges, derived{zoning, circulation_structure, circulation_class
  ∈ concept_spec.CirculationClass ∪ {OTHER, UNKNOWN}, public_composition, bedroom_grouping, wet_core_strategy,
  entrance_relationship, exposure_pattern, circulation_ratio, corridor_length_m, circulation_nodes, topology_depth},
  provenance{dataset: "ResPlan", license: "CC BY 4.0", attribution}) — JSON-serialisable, versioned `schema_version`.
- `ArchitecturalPattern` (the compact per-plan pattern: the derived block above + relationships
  living↔dining/kitchen, entrance↔public, bedrooms↔private circulation, wet↔bedrooms/public) — measurable rules only.
- `ConceptSpec`: REUSED from `backend/app/vertical_slice/concept_spec.py` (Concept Engine v2, branch
  `integration/concept-engine-v2`) — extended, not forked, with `references: list[ReferenceUse{plan_id, pattern_used,
  why}]` and `adaptations: list[Adaptation{kind, before, after, reason}]`.
- Retrieval result: `list[RetrievedReference{plan_id, score, terms{...}, why: str}]`; deterministic.
- Demo output: `docs/reports/poc-architectural-brain/{brief-1,brief-2,brief-3}/{current.svg, brain-A.svg, brain-B.svg,
  brain-C.svg, references.md, comparison.md}` + `docs/reports/poc-architectural-brain/README.md` (the visual
  before/after page, measurements table, recommendation).

### Acceptance Criteria

- AC-1: real plans are represented as structured architectural data: the committed 20-plan fixture validates against the PlanReference schema and ≥ 100 normalised plans are produced by the corpus script with UNKNOWN marked explicitly where semantics could not be derived
- AC-2: a Brief retrieves architecturally relevant references: for the 3 benchmark briefs the top-5 references share the brief's room programme class (bedroom count ± 1, wet-room count ± 1) and at least 3 of the 5 share its circulation class or zoning, each with a printed WHY
- AC-3: the references affect concept generation observably: for each benchmark brief the synthesized ConceptSpecs cite ≥ 2 references and ≥ 1 adaptation each, and differ in circulation class or zoning from the current generator's primary concept for at least 2 of the 3 briefs
- AC-4: for at least one benchmark brief, ≥ 2 genuinely different topological alternatives are realized and pass every existing hard validator (different `realized_circulation_class`, e.g. HUB_LOBBY vs TWO_WING vs BRANCHED — not two spines)
- AC-5: every realized POC plan passes the existing hard validators with no validator disabled or weakened (the validation report has 0 failures)
- AC-6: the side-by-side visual demo exists for the 3 briefs with the retrieved references and WHY, the extracted ideas and the adaptation changes, and the measurements table compares current vs POC on circulation ratio, longest corridor, dead space, public/private separation, wet-room clustering, exterior exposure, entrance integration, circulation nodes, topology class, room-area compliance and validator failures
- AC-7: the final report answers the final question with a GO / MODIFY / STOP recommendation and names every failure criterion that applied (retrieval by area only, no material effect, collapse to SPINE, adaptation destroyed topology, metrics-only improvement, validators disabled, semantics not extractable)

### Out of scope

Production ingestion, scalability, fine-tuning, deployment; merging into main; changing Geometry Core or validators;
weakening constraints; touching Concept Engine v2's own branch.

### Affected domains

knowledge, backend, geometry, validator, ai, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

none

### Required locks

knowledge-index (shared), planner-core (shared), geometry-core (shared), validator-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_plan_reference.py
- AC-2 -> pytest:backend/tests/architectural_brain/test_retrieval.py
- AC-3 -> pytest:backend/tests/architectural_brain/test_synthesis.py
- AC-4 -> pytest:backend/tests/architectural_brain/test_demo_alternatives.py
- AC-5 -> pytest:backend/tests/architectural_brain/test_demo_alternatives.py
- AC-6 -> file:docs/reports/poc-architectural-brain/README.md ; grep:docs/reports/poc-architectural-brain/README.md:Retrieved references
- AC-7 -> grep:docs/reports/poc-architectural-brain/README.md:Recommendation

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/ (demo, measurements, recommendation, dataset/schema description), docs/wiki/architecture/knowledge-system.md (ResPlan attribution + where the data lives, POC status only).

### Knowledge check

Consulted: the owner's POC specification (2026-09-21), `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md`, Concept Engine v2 branch
(`concept_spec.py`, `concept_patterns.py`, `concept_score.py`, `concept_engine_v2.py`, `docs/reports/concept-engine-v2-*.md`),
`docs/architecture_reference/references/README.md` (rights policy), `app/architect/gateway.py` (`ArchitectModelGateway`,
`authoritative_merge`), ResPlan paper + LICENSE + `resplan_utils.py` + the pickle itself (schema and statistics above).
