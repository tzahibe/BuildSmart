# [agent] Concept Engine v2 (4/5): the stage wired behind CONCEPT_ENGINE_V2_ENABLED — alternatives become one best plan per circulation class, labelled on the ReviewPage, latency-budgeted

### Goal

Put the prior (CE2-2), the compilers and the score/adaptation loop (CE2-3) into `run_general` behind a
module flag, so that with the flag on the person sees genuinely different organisations — one best plan per
circulation class — each labelled with its concept, while the primary plan and every flag-off output stay
byte-identical.

Execution order inside the ROOT: after CE2-2 and CE2-3 (the Issue numbers are filled in by `agentctl issue decompose` at creation).

### Current behavior

`run_general` realizes the first valid candidate, then `_alternative_plans` adds up to 3 plans of unseen
`family_signature` (all spines in practice) plus one massing slot; `_select_plans` de-duplicates by massing →
family → outline. The ReviewPage shows the plans without a concept name. Measured: 0/60 briefs show two
circulation classes.

### Required behavior

1. `CONCEPT_ENGINE_V2_ENABLED = False` in `general_pipeline.py` (the `LAUNDRY_ROOM_ENABLED` pattern). With
   the flag off nothing changes.
2. Flag on: after the existing selection (guards included, untouched), `concept_engine_v2.plans_per_class(…)`
   runs S1–S3: `patterns_for(brief, outline)` → compile each pattern class through the existing builders →
   realize / score / adapt within the class (CE2-3) → the best verified plan per class; these replace the
   alternatives (the primary is untouched; the massing-representation slot rule is kept). Bounded by
   `CONCEPT_ENGINE_V2_MAX_REALIZATIONS` per brief.
3. `DemoDesign.concept` (label + one-sentence rationale in Hebrew, e.g. "מבואת חדרים — החדרים נפתחים סביב
   מבואה קומפקטית") for every shown plan; the ReviewPage shows it beside the plan title (small frontend change
   in `frontend/src/design/`).
4. A wallclock budget test bounding the flag-on cost per brief (`tests/wallclock.py` pattern).
5. The flag-on corpus report: diversity share, alternative-set changes per brief, LOST/primary numbers —
   committed as `docs/reports/concept-engine-v2-diversity-report.md`.

### Acceptance Criteria

- AC-1: flag off — the frozen corpus snapshot is identical to the base (LOST 0, primary_signature_changes 0, refusal codes identical)
- AC-2: flag on — the committed report shows ≥ 40 % of PLANNED briefs with ≥ 2 circulation classes among shown plans, LOST 0, primary_signature_changes 0
- AC-3: every shown plan carries a `concept` label whose class equals `realized_circulation_class(plan)`
- AC-4: the flag-on wallclock budget test passes on the developer machine and is a no-op under `WALLCLOCK_BUDGETS=off`
- AC-5: the ReviewPage renders the concept label for each plan

### Out of scope

Changing the primary; BRANCHED/RING classes; removing the old `_alternative_plans` path (stays as the flag-off
path); multi-level.

### Affected domains

backend, geometry, validator, frontend, qa

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

none

### Required locks

planner-core, frontend-review (shared)

### Verification plan

- AC-1 -> regression:corpus
- AC-2 -> file:docs/reports/concept-engine-v2-diversity-report.md ; grep:docs/reports/concept-engine-v2-diversity-report.md:briefs with
- AC-3 -> pytest:backend/tests/test_concept_engine_v2.py::test_every_shown_plan_label_matches_its_realized_class
- AC-4 -> pytest:backend/tests/test_concept_engine_v2_budget.py
- AC-5 -> vitest:frontend/src/design/ConceptLabel.test.tsx

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/wiki/features/concept-engine-v2.md (new, flag documented as OFF), docs/wiki/features/review-page.md (label),
docs/PROJECT_STATE.md, docs/reports/concept-engine-v2-diversity-report.md.

### Knowledge check

Consulted: `general_pipeline.py::run_general` (:479–604, guards, `_alternative_plans`), `demo/service.py::
_select_plans`, `demo/contract.py::DemoDesign.family`, `frontend/src/design/DemoWorkspace.tsx` (#63 panels),
`concept_generator.LAUNDRY_ROOM_ENABLED` (flag pattern + activation report discipline), `tests/wallclock.py`,
`spikes/failure_log_sweep/corpus_snapshot.py --compare`, backend and geometry domain-lead briefs.
