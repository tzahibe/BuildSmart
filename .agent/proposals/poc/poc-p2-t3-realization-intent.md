# [agent] POC Phase 2 — Track 3: RealizationIntent / SpatialGraph — carry the retrieved plan's structure into realization, and report PRESERVED vs LOST per plan

### Goal

Phase 1 proved real-plan knowledge can change the result (brief 3: a retrieved TWO_WING reference realized where
the production generator refused the site) and located the failure downstream: the architectural information is
lost or collapsed during realization — different donors with different proportions and different reasoning
collapse into identical realized geometry (brief 1), and concepts that do realize fail C19/C8 where production
succeeds (brief 2). Owner decision (2026-09-23, Phase 2 spec, TRACK 3): add a POC-only `RealizationIntent` /
`SpatialGraph` between the retrieved `PlanReference` and realization that PRESERVES the reference's structure,
make the realizer attempt to honour it, and report per realized plan exactly what was preserved and what was
lost. "We need to see exactly where architectural information disappears."

### Current behavior

`spikes/architectural_brain/`: `retrieval.py` → `synthesis.py` (`ConceptSpec` with `references` / `adaptations`)
→ `adaptation.py` → `realize.py` compiles a `ConceptSpec` into a Geometry Core `Fixture` (slicing tree) and runs
the unchanged `_realize` chain. What survives into realization today is only: room types, room areas (each type
resized to a fixed per-type target — the measured cause of brief 1's collapse), the circulation label, zoning and
the wet-core pattern. The adjacency graph, the access graph, exposure requirements, relative placement, clusters,
circulation nodes, the entrance relationship and the donor's own proportions are all dropped; the ConceptSpec
carries no field for them and the compiler has no way to honour them.

### Required behavior

1. `backend/spikes/architectural_brain/realization_intent.py`: `RealizationIntent` (POC-only, versioned,
   JSON-serialisable) carrying, where the reference provides them (UNKNOWN otherwise, never invented):
   `adjacency_edges` (room-pair must-touch), `access_edges` (must be reachable through a door/opening),
   `exterior_exposure` per room (which sides must be on the envelope), `relative_placement` (front/rear/left/
   right, above/below in plan coordinates), `public_private_clusters`, `circulation_nodes` (the corridor/lobby
   nodes and what each serves), `wet_core_groups`, `entrance_relationship` (entrance → which room), 
   `room_proportions` (each room's own aspect/area share FROM THE DONOR, not a fixed per-type constant) and
   `footprint_relationships` (wing/band proportions). Built from `PlanReference` + `ConceptSpec` by
   `intent_from(reference, concept, brief)`.
2. `realize.py` takes the intent and ATTEMPTS to honour it: the slicing tree is built to satisfy as many
   adjacency/access/exposure/placement facts as the guillotine language allows; the donor's own room proportions
   replace the fixed per-type targets (brief 1's collapse); a fact that cannot be honoured is recorded, never
   silently dropped. Authoritative requirements still win (Site, Brief, SAFE_ROOM, validators, geometry
   feasibility) — a conflict is recorded as LOST with the reason.
3. `preservation.py`: `measure_preservation(intent, realized_plan) -> PreservationReport` — for each fact class,
   which facts survived in the REALIZED geometry (adjacency measured on realized rects, access on the realized
   door graph, exposure on the realized envelope, placement on realized centroids, clusters/wet groups/entrance
   as in `patterns.py`), as counts and percentages plus the explicit list of lost facts with the reason
   (`GUILLOTINE_IMPOSSIBLE`, `VALIDATOR_CONFLICT:C19`, `REQUIREMENT_CONFLICT:SAFE_ROOM`, `BUDGET`, …).
4. Every demo plan writes its `PreservationReport` into `brief-N/<plan>.json` and a PRESERVED / LOST block into
   `comparison.md`; the Phase-2 report (Track 1's evaluation child) aggregates them.
5. When two plans of the same brief realize to the same geometry, the report must name the constraint that caused
   the collapse (the owner's explicit requirement).

### Acceptance Criteria

- AC-1: `RealizationIntent` is built from a fixture `PlanReference` + `ConceptSpec` with every field populated or explicitly UNKNOWN, round-trips through JSON, and never invents a fact the reference does not carry (unit test on the committed 20-plan fixture)
- AC-2: `realize.py` consumes the intent: the donor's own room proportions drive room sizing (a test proves two different donors for the SAME brief produce different realized `layout_signature`s — brief 1's collapse is closed or the blocking constraint is named in the report)
- AC-3: `measure_preservation` reports per fact class the preserved count/percentage and every lost fact with a machine-readable reason, measured on the REALIZED geometry, on at least two realized plans of different briefs
- AC-4: each brief's `comparison.md` carries the PRESERVED / LOST block, and when two plans collapse to the same drawing the report names the causing constraint

### Out of scope

Changing Geometry Core, validators, doors/windows, the production pipeline; polygon rooms (Track 2's spikes);
HUB_LOBBY / BRANCHED compilers (Track 1); merging anything to main.

### Affected domains

backend, geometry, validator, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

none

### Required locks

planner-core (shared), geometry-core (shared), validator-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_realization_intent.py::test_intent_is_built_from_the_reference_and_never_invents_facts
- AC-2 -> pytest:backend/tests/architectural_brain/test_realization_intent.py::test_two_donors_for_one_brief_realize_to_different_layouts
- AC-3 -> pytest:backend/tests/architectural_brain/test_preservation.py
- AC-4 -> grep:docs/reports/poc-architectural-brain/brief-1/comparison.md:PRESERVED ; grep:docs/reports/poc-architectural-brain/brief-1/comparison.md:LOST

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/brief-*/comparison.md (PRESERVED/LOST blocks), docs/reports/poc-architectural-brain/preservation.md (the fact taxonomy and how each is measured).

### Knowledge check

Consulted: the owner's Phase 2 specification (2026-09-23), `docs/reports/poc-architectural-brain/README.md` (Phase 1's
measured collapse: brief 1 identical geometry, brief 2 C19/C8 refusals), `spikes/architectural_brain/{plan_reference,patterns,
retrieval,synthesis,adaptation,realize}.py`, `concept_spec.py`, `geometry_core/model.py`, `validation.py` (C8/C19),
`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §2 (what the slicing language can and cannot express).
