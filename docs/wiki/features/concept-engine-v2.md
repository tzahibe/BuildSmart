# Concept Engine v2

Status: IMPLEMENTED, flag OFF (`CONCEPT_ENGINE_V2_ENABLED = False`) — not the live product behavior

## Current behavior

A module flag in `app/vertical_slice/general_pipeline.py`, `CONCEPT_ENGINE_V2_ENABLED` (the same
single-flag-gates-the-whole-path pattern `concept_generator.LAUNDRY_ROOM_ENABLED` uses), decides
which code `run_general` uses to build a plan's ALTERNATIVES (the primary is never affected by this
flag, in either state).

**Flag OFF (today's live behavior, byte-identical to before this Issue)**: `general_pipeline.
_alternative_plans` — the family-nearest-area walk plus the massing-representation slot
(`_massing_representation_plans`) — exactly as it worked before Issue #78.

**Flag ON**: `app.vertical_slice.concept_engine_v2.plans_per_class` replaces `_alternative_plans`.
For the brief and the realized footprint of the plan `run_general` already chose as primary:

1. `concept_patterns.patterns_for(brief, outline)` (Issue #77) names the 2-3 concept patterns most
   worth trying, best first, plus every OTHER circulation class the generator's own candidates for
   this outline actually carry (a class `patterns_for` does not name for this footprint family is
   never skipped merely because the architectural-reference table does not cite it — see
   `concept_engine_v2.plans_per_class`'s own docstring for why this union exists).
2. Each named class is "compiled" by filtering `concept_generator.generate_concepts`'s own output
   for THIS outline (never a new generator call, never new geometry) down to the candidates whose
   own declared `circulation_class` matches.
3. The first matching candidate is realized through the EXISTING `_realize` pipeline
   (doors/windows/furniture/validation, unchanged) and scored (`concept_score.concept_score`,
   Issue #76); when the bounded adaptation ladder (`concept_score.adapt`) names a target concept, a
   SIBLING candidate already in the same filtered list matching that target is realized too, and
   the better-scoring `.ok` plan of the two wins the class.
4. One verified plan per REALIZED circulation class (`concept_spec.realized_circulation_class`)
   becomes an alternative; the massing-representation slot rule
   (`general_pipeline._massing_representation_plans`, shared code with the flag-off path) still
   runs afterward, so an L massing keeps its guaranteed slot either way.
5. Bounded by `concept_engine_v2.CONCEPT_ENGINE_V2_MAX_REALIZATIONS` (10) realizations per brief —
   the only added cost, since `patterns_for`/`concept_score`/`adapt` are pure/pre-solve/read-only.

Every shown plan (primary and alternatives) carries a `DemoDesign.concept` label
(`concept_engine_v2.concept_label`: a Hebrew name and one-sentence rationale per
`concept_spec.CirculationClass`) **only when the flag is ON** — `None` otherwise, so a flag-off
payload is unaffected. The ReviewPage's plan workspace (`frontend/src/design/ConceptLabel.tsx`)
renders it beside the plan title when present.

## Authoritative implementation

- `app/vertical_slice/concept_engine_v2.py` (S1-S3, the flag-on alternatives path, the label
  vocabulary).
- `app/vertical_slice/general_pipeline.py`: `CONCEPT_ENGINE_V2_ENABLED`, the flag branch in
  `run_general`, `_massing_representation_plans` (extracted from `_alternative_plans`'s own former
  tail so both paths share it).
- `app/demo/contract.py`: `ConceptOut`, `DemoDesign.concept`.
- `app/demo/service.py`: `_concept_of` (attaches the label to every shown `DemoDesign` when the
  flag is on).
- `frontend/src/design/ConceptLabel.tsx` (+`.css`), `demoDesign.ts`'s `DemoConcept`, wired into
  `DemoWorkspace.tsx` beside both the large plan's title and each thumbnail's label.
- Built on Issues #75 (`concept_spec.py`: `ConceptSpec`, `realized_circulation_class`,
  `topologically_distinct`), #77 (`concept_patterns.py`: `patterns_for`), #76 (`concept_score.py`:
  `concept_score`, `adapt`).
- Tests: `backend/tests/test_concept_engine_v2.py` (AC-3, AC-6, label-vocabulary completeness),
  `backend/tests/test_concept_engine_v2_budget.py` (AC-4, `tests/wallclock.py` pattern),
  `frontend/src/design/ConceptLabel.test.tsx` (AC-5).

## Current constraints/invariants

- **The flag defaults to `False`.** Nothing described above as "flag ON" is live product behavior
  until an owner decision turns it on — see the owner benchmark report below.
- The primary is never touched by this flag, in either state — only the alternatives set changes.
- Flag ON never removes the massing-representation guarantee: `_massing_representation_plans` is
  the SAME function both paths call.
- **Measured diversity ceiling** (`docs/reports/concept-engine-v2-diversity-report.md`): within
  ONE outline/`run_general` call — the scope this Issue wires — most briefs' generator output for
  the winning outline simply does not contain a second circulation class to compile (a narrow-deep
  outline structurally has no room for a hub; a rectangle outline's hub builder rejects far more
  often than it accepts on this corpus, consistent with Issue #76's own finding that a realized
  HUB_LOBBY plan does not appear anywhere in the flag-off 404-brief baseline). The measured
  flag-on share of PLANNED briefs showing ≥2 classes is reported in that file; see the owner
  benchmark for what would be needed to raise it further (cross-outline search, or generator/
  template changes — both explicitly out of scope for this Issue).
- `CONCEPT_ENGINE_V2_MAX_REALIZATIONS` bounds cost, not correctness: a class that genuinely has no
  realizable candidate contributes nothing to the alternatives set regardless of budget.

## Supersedes

Nothing — this is additive; `_alternative_plans` stays the flag-off path and is not removed
(explicitly out of scope for this Issue).

## Known follow-ups

- The owner decision on whether/when to turn the flag on, and on the two open scope questions the
  ROOT Issue named: whether the new engine may influence the primary, and how Rectangle/L/Irregular
  massing, massing selection, Multi-Level Phase 2 and stairs/vertical core fit this architecture —
  see `docs/reports/concept-engine-v2-owner-benchmark.md` and
  `docs/reports/concept-engine-v2-massing-multilevel-proposal.md`.
- CE2-5 (the ROOT Issue's 5th child, if scheduled): whatever the owner's decision above implies.

## Evidence/history

`docs/reports/concept-engine-v2-diversity-baseline.md` (Issue #75, flag-off baseline: 49/404,
12.1%), `docs/reports/concept-engine-v2-adaptation-report.md` (Issue #76, offline `adapt` ladder
measurement), `docs/reports/concept-engine-v2-diversity-report.md` (this Issue's flag-on
measurement), `docs/reports/concept-engine-v2-owner-benchmark.md`,
`docs/reports/concept-engine-v2-massing-multilevel-proposal.md`.

## Last verified against git

Branch `agent/78-concept-engine-v2-4-5-the-stage-wired-be`, based on
`origin/integration/concept-engine-v2` at the commit this Issue's work sits on top of (`14f556b`,
`8c850ed`, `1ac5970`).
