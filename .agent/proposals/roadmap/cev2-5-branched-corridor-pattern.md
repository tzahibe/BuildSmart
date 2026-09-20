# [agent] Concept Engine v2 (5/5, decision-gated): BRANCHED circulation class — two hall segments joined by a seam-level opening, accepted by C5/C24

### Goal

Add the one census-relevant circulation class the engine cannot express today: a branched (L/T) hall made of
two HALL leaves in different subtrees, joined by an opening created at the seam level, so the access graph
and the walls agree. Gated on the owner's decision after CE2-4's diversity numbers.

Execution order inside the ROOT: after CE2-4 and the owner's decision (the Issue numbers are filled in by `agentctl issue decompose` at creation).

### Current behavior

`geometry_core/engine.py::_mark_open_interfaces` opens a boundary only inside a subtree whose leaves all
belong to one open group, so two hall leaves that are not siblings keep a wall between them ("connected on
paper, walled in fact" — `concept_generator.py:2992`). The hall↔LDK wall is already opened at segment level as
a contract post-process (`contract.py`, 2026-09-14) — the precedent for a seam-level opening. `_front_band
_concept` changes the plan's shape instead of the corridor's shape for exactly this reason.

### Required behavior

1. A `BRANCHED` compiler in the concept stage: two HALL leaves (main + spur) in adjacent subtrees, the spur
   serving a second bedroom group; the junction declared as a `CASED_OPENING` edge.
2. The seam-level opening for a declared hall–hall `CASED_OPENING`: applied where the corridor post-process
   already runs, with the width rule of `access_rules`; C5 (realized access graph), C14 (corridor rectangle),
   C24 and the entrance walk accept it; no validator hard limit is relaxed.
3. `realized_circulation_class` recognises BRANCHED from the realized geometry (two hall rectangles sharing an
   opening, angle ≠ 0).
4. Behind the same `CONCEPT_ENGINE_V2_ENABLED` flag; measured in the flag-on diversity report.

### Acceptance Criteria

- AC-1: a canonical 4-bedroom fixture realizes a BRANCHED concept with both hall segments reachable from the entrance and every bedroom door on a hall segment (C5, C24 pass)
- AC-2: the realized plan's `realized_circulation_class` is BRANCHED and M3 circulation share stays ≤ the spine plan's for the same programme
- AC-3: flag off — corpus unchanged; flag on — LOST 0, primary_signature_changes 0, diversity report updated

### Out of scope

RING/courtyard circulation; Geometry Core changes; changing the primary.

### Affected domains

backend, geometry, validator, qa

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

none

### Required locks

planner-core, geometry-core, validator-core

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_branched_corridor.py::test_branched_concept_realizes_with_all_bedrooms_on_a_hall
- AC-2 -> pytest:backend/tests/vertical_slice/test_branched_corridor.py::test_realized_class_is_branched_and_circulation_not_worse
- AC-3 -> regression:corpus ; file:docs/reports/concept-engine-v2-diversity-report.md

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/wiki/features/concept-engine-v2.md (BRANCHED), docs/wiki/architecture/geometry-validation.md (seam-level
opening rule).

### Knowledge check

Consulted: `geometry_core/engine.py::_mark_open_interfaces` (:97–116), `concept_generator.py:2992` (bent
corridor limit), `docs/CONCEPT_GENERATOR_REFINE_V1_REPORT.md` §"bent corridor", memory `corridor-opening-is-a-
contract-post-process`, `validation.py` C5/C14/C24, `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md` §3.4/§6.
