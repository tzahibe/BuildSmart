# [agent] Concept Engine v2 (5/5): generator-level pattern compilers — HUB_LOBBY and BRANCHED circulation classes independent of the legacy hub template, cross-outline concept search — raising the measured diversity ceiling to the 40 % bar

### Goal

Child 4 (#78) measured the ceiling of the current generator: with Concept Engine v2 on, only 17.6 % of PLANNED
briefs (71/404) show two circulation classes, HUB_LOBBY is never realized, and `plans_per_class` already
realizes ~84 % of what the generator offers — the bottleneck is `concept_generator.py`'s per-outline hub /
front-band acceptance (a second class exists in only ~25 % of briefs) and the single-outline scope of
`run_general`. Owner decision (2026-09-21, option b): give Concept Engine v2 its own pattern compilers (stage S2
of `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md` §9) and let it search across the outlines the service surveys,
so that ≥ 40 % of PLANNED briefs show ≥ 2 verified circulation classes. Flag stays OFF; the primary plan stays
unchanged.

### Current behavior

`concept_engine_v2.plans_per_class` (child 4) works inside one `run_general` call on the candidate list
`concept_generator.generate_concepts` produced for that outline; HUB_LOBBY candidates come only from
`_hub_concept` (the 005 template with fixed seats, eligible on 4/432 corpus contexts), FRONT_BAND from
`_front_band_concept`, TWO_WING from `l_parti`; BRANCHED and RING cannot be expressed (an open group must be one
subtree — `geometry_core/engine.py::_mark_open_interfaces`). Massing / outline choice belongs to
`demo/service.py::_plan_outlines`, outside `run_general` (see `docs/reports/concept-engine-v2-massing-multilevel-proposal.md`).

### Required behavior

1. `backend/app/vertical_slice/concept_compilers.py`: one interface (`compile(pattern, programme, outline) ->
   list[ConceptCandidate]`) with compilers for SPINE and FRONT_BAND (wrapping the existing builders), TWO_WING
   (wrapping `l_parti`), **HUB_LOBBY** — a compact lobby (aspect ≤ 1.5, ≥ 4 doors) with rooms on ≥ 3 sides and
   the shared wet rooms at its head, sized from the programme by a bound/witness search (the 008 pattern), NOT
   the 005 template's fixed seats — and **BRANCHED** — two HALL leaves in adjacent subtrees joined by a
   `CASED_OPENING` edge realized as a seam-level opening (the `contract.py` corridor-opening precedent), accepted
   by C5, C14 and C24 with no hard limit relaxed. Every emitted candidate carries its `circulation_class`, and
   `realized_circulation_class` verifies it on the realized plan; a mismatch drops the candidate.
2. Cross-outline search: with the flag on, `plans_per_class` may take candidates from every outline the
   service surveys (`_plan_outlines` results), choosing one best verified plan per class across outlines; the
   primary selection rule and the flag-off path are untouched.
3. The flag-on diversity report is re-measured on the frozen corpus and committed; HUB_LOBBY appears as a
   shown class; the wallclock budget test still bounds the flag-on cost.
4. Flag OFF: byte-identical corpus; flag ON: LOST 0, primary_signature_changes 0.

### Acceptance Criteria

- AC-1: every compiler emits candidates whose declared class is verified on the realized plan on the canonical fixtures (SPINE, FRONT_BAND, TWO_WING, HUB_LOBBY, BRANCHED), and a mismatching candidate is dropped
- AC-2: a canonical 4-bedroom fixture realizes a BRANCHED concept with every bedroom door on a hall segment and C5, C14, C24 green
- AC-3: the committed flag-on diversity report shows ≥ 40 % of PLANNED briefs with ≥ 2 circulation classes among shown plans and HUB_LOBBY among the shown classes, with LOST 0 and primary_signature_changes 0
- AC-4: flag off — the frozen corpus snapshot is identical to the base (LOST 0, primary_signature_changes 0, refusal codes identical)
- AC-5: a brief whose primary outline offers a single class receives a second verified class from another surveyed outline (cross-outline search)
- AC-6: the flag-on wallclock budget test passes and is a no-op under WALLCLOCK_BUDGETS=off

### Out of scope

Changing the primary plan (owner decision after this child's report); RING / courtyard circulation; Geometry Core
changes; multi-level; relaxing any validator hard limit.

### Affected domains

backend, geometry, validator, qa

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

#78

### Required locks

planner-core, geometry-core, validator-core

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_concept_compilers.py::test_every_compiler_emits_verified_classes_and_drops_mismatches
- AC-2 -> pytest:backend/tests/vertical_slice/test_concept_compilers.py::test_branched_concept_realizes_with_all_bedrooms_on_a_hall
- AC-3 -> file:docs/reports/concept-engine-v2-diversity-report.md ; grep:docs/reports/concept-engine-v2-diversity-report.md:HUB_LOBBY
- AC-4 -> regression:corpus
- AC-5 -> pytest:backend/tests/test_concept_engine_v2.py::test_cross_outline_search_adds_a_second_class
- AC-6 -> pytest:backend/tests/test_concept_engine_v2_budget.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/wiki/features/concept-engine-v2.md (compilers, cross-outline search, measured diversity), docs/reports/concept-engine-v2-diversity-report.md (re-measured), docs/ROADMAP.md (child 5 expanded).

### Knowledge check

Consulted: `docs/reports/concept-engine-v2-owner-benchmark.md` (#78: 17.6 %, cause, options), `concept_engine_v2.py::plans_per_class`, `concept_score.py`, `concept_generator.py` (`_hub_concept`, `hub_bound` witness, `_front_band_concept`), `l_parti.py`, `geometry_core/engine.py::_mark_open_interfaces`, `contract.py` corridor opening, `demo/service.py::_plan_outlines/_select_plans`, `docs/reports/concept-engine-v2-massing-multilevel-proposal.md`, `specs/005/RESULTS.md` §7–§9, `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md` §3.4/§6/§9.
