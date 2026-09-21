# [agent] POC Architectural Brain (A/3): ResPlan → PlanReference — normalisation, PlanGraph, measurable architectural patterns, the 100–300-plan reference corpus and the schema description

### Goal

Turn real ResPlan floor plans into structured BuildSmart architectural data: a versioned `PlanReference` JSON per
plan (metric geometry, rooms, walls/doors/windows, adjacency and access graphs, entrance), derived architectural
semantics by measurable rules with explicit UNKNOWN, an `ArchitecturalPattern` per plan, a committed 20-plan
fixture, a 100–300-plan POC corpus biased to 3–5 bedrooms, and the dataset/schema description — the shared
contract agents B and C build on. POC branch only.

### Current behavior

No real plan is represented anywhere. The Team Lead verified ResPlan (2026-09-21): `/Users/mymacbook/projects/
datasets/resplan/ResPlan.pkl` (list of 17,107 dicts; Shapely (multi)polygons in PIXEL coordinates keyed by
living, bedroom, bathroom, kitchen, balcony, storage, stair, garden, parking, pool, veranda, wall, door, window,
front_door, inner, land, neighbor; plus `area` (gross m²), `net_area`, `wall_depth` (px), `unitType`, `id`,
networkx `graph` with typed edges direct / adjacency / via_door / via_window). No hall/corridor category; the
metric scale is not stored. CC BY 4.0 (attribution: ResPlan, Abouagour & Garyfallidis 2025, arXiv 2508.14006).
The pickle is outside the repo and is never committed; CI has no access to it.

### Required behavior

1. `backend/spikes/architectural_brain/plan_reference.py`: the `PlanReference` dataclasses + JSON schema
   (`schema_version`), exactly the shape the ROOT #93 contract lists (footprint, rooms with type in the
   BuildSmart `ProgramRole` vocabulary or UNKNOWN, polygon/area/width/depth/exterior exposure, walls, doors with
   the rooms they join, windows, entrance room + side or UNKNOWN, adjacency_edges, access_edges, derived block,
   provenance). `to_json` / `from_json` round-trip.
2. `backend/spikes/architectural_brain/resplan_ingest.py`: `normalise(plan_dict) -> PlanReference`: metric scale
   from `sqrt(area / inner.area_px)` cross-checked against `wall_depth` (reject plans whose implied wall thickness
   is outside 8–45 cm and record why), footprint = `inner`, rooms from the functional categories (each polygon
   part = one room; living = LIVING (or LIVING+DINING+KITCHEN when the kitchen polygon is inside/open to it —
   rule-based), bathroom → BATHROOM/TOILET by area rule, storage → STORAGE), circulation = `inner − rooms −
   walls` residual components (type CIRCULATION, each component a node), doors → access edges between the rooms
   whose polygons they touch, windows → exterior exposure per room side (a room side within wall_depth of the
   footprint boundary with a window polygon = exposed), entrance from `front_door` (the room it opens into, the
   footprint side), unit type, provenance. Everything not derivable = UNKNOWN, never guessed.
3. `backend/spikes/architectural_brain/patterns.py`: `derive_pattern(ref) -> ArchitecturalPattern` by MEASURABLE
   rules only: circulation class (SPINE: one residual component with long/short > 3 and ≥ 3 doors; HUB_LOBBY:
   residual component aspect ≤ 1.5 with ≥ 4 doors and rooms on ≥ 3 sides; BRANCHED: ≥ 2 residual components joined
   by an opening; TWO_WING: footprint with two rectangles (L) or rooms in two separated groups; FRONT_BAND: public
   rooms span the entrance side; OTHER; UNKNOWN), zoning (public-front/private-rear, public/private wings,
   central public, OTHER) from centroid geometry, public composition (living/dining/kitchen open or closed),
   bedroom grouping (share of bedrooms reachable from the same circulation node), wet-core strategy (wet rooms
   sharing a wall / distance between wet clusters), entrance relationship (entrance → living / hall / kitchen),
   exposure pattern (share of habitable rooms with an exposed side), circulation ratio, corridor length (longest
   residual skeleton), circulation nodes, topology depth (max door-hops from the entrance), and the relationships
   living↔dining, dining↔kitchen, entrance↔public, bedrooms↔private circulation, wet↔bedrooms/public.
4. `backend/spikes/architectural_brain/build_corpus.py`: selects 100–300 plans — all Villa / IndependentHouse /
   BuilderFloor with ≥ 3 bedrooms plus apartments with 3–5 bedrooms, deduplicated (the dataset has near-
   duplicates), normalised, patterned — into `backend/spikes/architectural_brain/corpus/` as JSON (committed; a
   few MB) with an `ATTRIBUTION.md` (CC BY 4.0), and a 20-plan fixture `backend/tests/architectural_brain/fixtures/
   plans/*.json` chosen to cover every derived circulation class present; `RESPLAN_PKL` env var (default the path
   above) — the tests never open the pickle.
5. `docs/reports/poc-architectural-brain/dataset.md`: the dataset/schema description — fields, scale inference,
   what is derived by which rule, what stays UNKNOWN and how often (counts over the corpus), the typology gap
   (South Asian apartments vs Israeli houses, no plot/street/SAFE_ROOM), licence and attribution.

### Acceptance Criteria

- AC-1: every fixture plan round-trips through the PlanReference JSON schema and every room, door and entrance carries metric coordinates with an implied wall thickness between 8 and 45 cm
- AC-2: `derive_pattern` assigns a circulation class by the stated measurable rules, is deterministic, and the fixture contains at least SPINE, HUB_LOBBY and one of TWO_WING/BRANCHED/FRONT_BAND, each verified against a hand-checked expectation file
- AC-3: derived semantics never guess: a plan without a detectable entrance or without windows reports UNKNOWN for entrance / exposure, tested on a synthetic plan
- AC-4: the committed corpus holds ≥ 100 plans with the class / zoning / wet-core distribution and the UNKNOWN counts printed in dataset.md, and every corpus file cites the ResPlan attribution

### Out of scope

Retrieval, synthesis, adaptation (B); realization and demo (C); the full 17k ingestion; any change to `app/`.

### Affected domains

knowledge, backend, qa

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

none

### Required locks

knowledge-index (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_plan_reference.py::test_fixture_plans_round_trip_with_metric_scale
- AC-2 -> pytest:backend/tests/architectural_brain/test_plan_reference.py::test_derived_circulation_classes_match_the_hand_checked_expectations
- AC-3 -> pytest:backend/tests/architectural_brain/test_plan_reference.py::test_underivable_semantics_are_unknown_never_guessed
- AC-4 -> file:docs/reports/poc-architectural-brain/dataset.md ; grep:backend/spikes/architectural_brain/corpus/ATTRIBUTION.md:CC BY 4.0

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/dataset.md (new).

### Knowledge check

Consulted: the ROOT's verified ResPlan schema and statistics, `/Users/mymacbook/projects/datasets/resplan/resplan_utils.py`
(`plan_to_graph`, `get_plan_width`, `normalize_keys`), `backend/app/vertical_slice/geometry_core/model.py` (`ProgramRole`),
`concept_spec.py` (`CirculationClass`) on the Concept Engine branch, `docs/architecture_reference/references/README.md`.
