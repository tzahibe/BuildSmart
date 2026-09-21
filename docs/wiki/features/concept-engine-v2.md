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
   own declared `circulation_class` matches. When that leaves nothing — a class the generator's
   own strategies cannot produce at all — `concept_compilers.compile_hub_lobby`/`compile_branched`
   (Issue #79) are tried instead, on the SAME outline `chosen_plan` was fit to: a hand-authored,
   bound/witness-sized HUB_LOBBY tree (compact lobby, rooms on ≥3 sides, the shared wet room at its
   head) and a hand-authored BRANCHED tree (two HALL leaves in adjacent, non-sibling subtrees,
   joined by a `CASED_OPENING`), each scoped to exactly the programme shape it was calibrated and
   verified against (see `concept_compilers.py`'s own module docstring) and `[]` otherwise.
3. The first matching candidate is realized through the EXISTING `_realize` pipeline
   (doors/windows/furniture/validation, unchanged), VERIFIED (`concept_spec.verify_class` — a
   candidate whose declared class disagrees with what it realized to is DROPPED, never
   re-labelled) and scored (`concept_score.concept_score`, Issue #76); when the bounded adaptation
   ladder (`concept_score.adapt`) names a target concept, a SIBLING candidate already in the same
   filtered list matching that target is realized too, and the better-scoring `.ok` verified plan
   of the two wins the class.
4. One verified plan per REALIZED circulation class (`concept_spec.realized_circulation_class`)
   becomes an alternative; the massing-representation slot rule
   (`general_pipeline._massing_representation_plans`, shared code with the flag-off path) still
   runs afterward, so an L massing keeps its guaranteed slot either way.
5. Bounded by `concept_engine_v2.CONCEPT_ENGINE_V2_MAX_REALIZATIONS` (10) realizations per brief —
   the only added cost, since `patterns_for`/`concept_score`/`adapt` are pure/pre-solve/read-only.
6. **Cross-outline search (Issue #79, AC-5)**: after the ordinary per-outline search above,
   `app.demo.service._augment_cross_outline_classes` looks for a circulation class still missing
   from the primary outline's own shown plans on every OTHER outline the service already surveyed
   (`_plan_outlines`'s own results — never a second generator call: each surveyed outline's
   `generated.candidates` sits on `GeneralSliceResult.candidates`, Issue #79, unused until now).
   `concept_engine_v2.plans_per_class_cross_outline` searches those outlines' own candidates (plus
   the same generator-level compilers where a class has no generator candidate on that outline
   either), in outline order, stopping at the first outline that verifies each still-missing
   class. Additive only: the primary plan, `plans_per_class`'s own alternatives and the flag-off
   path are all untouched; this only appends new alternatives, bounded by the same `_SHOWN_LIMIT`
   the ordinary selection already holds to.

Every shown plan (primary and alternatives) carries a `DemoDesign.concept` label
(`concept_engine_v2.concept_label`: a Hebrew name and one-sentence rationale per
`concept_spec.CirculationClass`) **only when the flag is ON** — `None` otherwise, so a flag-off
payload is unaffected. The ReviewPage's plan workspace (`frontend/src/design/ConceptLabel.tsx`)
renders it beside the plan title when present.

## Authoritative implementation

- `app/vertical_slice/concept_engine_v2.py` (S1-S3, the flag-on alternatives path, the label
  vocabulary, `plans_per_class_cross_outline`, `OutlineCandidates`).
- `app/vertical_slice/concept_compilers.py` (Issue #79): `compile` (SPINE/FRONT_BAND/TWO_WING
  wrap the existing generator, HUB_LOBBY/BRANCHED are hand-authored trees), `compile_hub_lobby`,
  `compile_branched`.
- `app/vertical_slice/concept_spec.py`: `realized_circulation_class` extended (Issue #79) to
  recognise BRANCHED — two HALL/CIRCULATION zones directly connected to each other.
- `app/vertical_slice/general_pipeline.py`: `CONCEPT_ENGINE_V2_ENABLED`, the flag branch in
  `run_general`, `_massing_representation_plans` (extracted from `_alternative_plans`'s own former
  tail so both paths share it), `GeneralSliceResult.candidates` (Issue #79 — every concept
  candidate the generator built for this run, exposed for the cross-outline search to reuse).
- `app/demo/contract.py`: `ConceptOut`, `DemoDesign.concept`.
- `app/demo/service.py`: `_concept_of` (attaches the label to every shown `DemoDesign` when the
  flag is on); `_augment_cross_outline_classes` (Issue #79, AC-5).
- `frontend/src/design/ConceptLabel.tsx` (+`.css`), `demoDesign.ts`'s `DemoConcept`, wired into
  `DemoWorkspace.tsx` beside both the large plan's title and each thumbnail's label.
- Built on Issues #75 (`concept_spec.py`: `ConceptSpec`, `realized_circulation_class`,
  `topologically_distinct`), #77 (`concept_patterns.py`: `patterns_for`), #76 (`concept_score.py`:
  `concept_score`, `adapt`).
- Tests: `backend/tests/test_concept_engine_v2.py` (AC-3, AC-6, label-vocabulary completeness,
  AC-5 cross-outline search), `backend/tests/test_concept_engine_v2_budget.py` (AC-4/AC-6,
  `tests/wallclock.py` pattern), `backend/tests/vertical_slice/test_concept_compilers.py` (Issue
  #79 AC-1/AC-2), `frontend/src/design/ConceptLabel.test.tsx` (AC-5 of Issue #78).

## Current constraints/invariants

- **The flag defaults to `False`.** Nothing described above as "flag ON" is live product behavior
  until an owner decision turns it on — see the owner benchmark report below.
- The primary is never touched by this flag, in either state — only the alternatives set changes.
- Flag ON never removes the massing-representation guarantee: `_massing_representation_plans` is
  the SAME function both paths call.
- **Measured diversity ceiling, Issue #78 (single-outline)**: within ONE outline/`run_general`
  call, most briefs' generator output for the winning outline did not contain a second circulation
  class to compile (a narrow-deep outline structurally has no room for a hub; a rectangle
  outline's hub builder rejects far more often than it accepts on this corpus). Measured 71/404
  (17.6%) of PLANNED briefs showing ≥2 classes (`docs/reports/concept-engine-v2-diversity-
  baseline.md`).
- **Measured diversity, Issue #79 (generator-level compilers + cross-outline search)**: the current
  measurement, over the same frozen 432-context corpus's PLANNED cases, with `concept_compilers.
  compile_hub_lobby`/`compile_branched` and `app.demo.service._augment_cross_outline_classes`
  both wired in behind the same flag — see `docs/reports/concept-engine-v2-diversity-report.md`
  for the current share of PLANNED briefs showing ≥2 classes, whether HUB_LOBBY/BRANCHED appear
  among the shown classes, and the LOST/GAINED/primary_signature_changes regression counts.
  `compile_hub_lobby`/`compile_branched` are each scoped to exactly ONE programme shape (see
  `concept_compilers.py`'s own module docstring for why a general arbitrary-programme version of
  either is out of scope here) — they contribute wherever a brief's programme matches that shape,
  never elsewhere.
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
- `compile_hub_lobby`/`compile_branched` (Issue #79) each serve exactly one programme shape; a
  general arbitrary-programme version of either (a real bound/witness search over widths/depths/
  bedroom counts, the way `concept_generator.plan_layout` does for SPINE) is named but not
  attempted in `concept_compilers.py`'s own module/function docstrings — a real follow-up if the
  owner wants HUB_LOBBY/BRANCHED coverage beyond that one shape each.
- RING circulation is still not produced by any builder — explicitly out of scope for Issue #79 as
  it was for #75-#78.

## Evidence/history

`docs/reports/concept-engine-v2-diversity-baseline.md` (Issue #75, flag-off baseline: 49/404,
12.1%), `docs/reports/concept-engine-v2-adaptation-report.md` (Issue #76, offline `adapt` ladder
measurement), `docs/reports/concept-engine-v2-diversity-report.md` (Issue #78's single-outline
flag-on measurement, then re-measured by Issue #79 with the compilers + cross-outline search
wired in), `docs/reports/concept-engine-v2-owner-benchmark.md`,
`docs/reports/concept-engine-v2-massing-multilevel-proposal.md`.

## Last verified against git

Branch `agent/79-concept-engine-v2-5-5-generator-level-pa`, based on
`origin/integration/concept-engine-v2` at the commit this Issue's work sits on top of (`84207d5`,
`14f556b`, `8c850ed`, `1ac5970`).
