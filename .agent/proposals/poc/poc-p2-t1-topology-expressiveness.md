# [agent] POC Phase 2 — Track 1: topology expressiveness — bring #79's HUB_LOBBY / BRANCHED compilers into the POC and re-run the three fixed briefs

### Goal

Answer one question with pictures: do the additional topology compilers let real-plan patterns SURVIVE
realization? Owner decision (2026-09-23, Phase 2 spec, TRACK 1): as soon as Concept Engine child #79 is genuinely
integrated and verified, bring its HUB_LOBBY and BRANCHED compilers into the POC branch, keep the SAME three
fixed benchmark briefs, re-run retrieval → synthesis → adaptation → realization, and try to realize SPINE /
HUB_LOBBY / BRANCHED / TWO_WING where appropriate — never forcing a topology onto an unsuitable site, never
changing a benchmark brief to manufacture a pass. Success is visual/topological difference, not a green test.

### Current behavior

`spikes/architectural_brain/realize.py` has two compilers of its own (SPINE, TWO_WING). Phase 1 measured: brief 1
realizes two brain alternatives that both come out SPINE, brief 2's alternatives fail C19/C8, brief 3 realizes
TWO_WING where the production generator refuses the site. Concept Engine v2 child #79 (branch
`integration/concept-engine-v2`) builds `concept_compilers.py` with HUB_LOBBY and BRANCHED (SAFE_ROOM-aware and
open-plan-aware variants, witness-based sizing in progress) plus cross-outline search; its measured flag-on
diversity on the production corpus is 27.0 % of PLANNED briefs with ≥ 2 circulation classes (HUB_LOBBY shown 34
times, from 0 before). The Team Lead merges that branch into `integration/poc-architectural-brain` once #79 is
integrated; this Issue starts from that merge.

### Required behavior

1. `realize.py` uses `concept_compilers.py`'s HUB_LOBBY and BRANCHED compilers (imported, not copied) beside its
   own SPINE / TWO_WING, driven by the `ConceptSpec`'s declared circulation class and Track 3's
   `RealizationIntent`; a compiler that cannot honour the brief's site or programme REFUSES with a stated reason
   (no forcing, no site reshaping).
2. Re-run the full demo for the same three fixed briefs, per plan (each call bounded; a plan that exceeds the
   budget is recorded as "not realized within budget"), producing new side-by-side SVGs and updated
   `references.md` / `comparison.md` per brief.
3. Report per brief which circulation classes were ATTEMPTED, which REALIZED and which REFUSED with the reason —
   and whether a retrieved reference's own topology survived into the realized plan (Track 3's preservation
   report is the evidence).
4. No benchmark brief, site or corpus is modified; no validator or hard limit is relaxed; the flag-off production
   path is untouched.

### Acceptance Criteria

- AC-1: the POC realizes at least three distinct circulation classes across the three briefs (measured by `realized_circulation_class`), each passing every existing hard validator, or the report names for every missing class the exact compiler/site reason it was refused
- AC-2: for at least one brief, two realized alternatives have different `realized_circulation_class` values (the Phase-1 AC-1 gap) — or the report names the constraint that prevented it, measured, not assumed
- AC-3: no benchmark brief, site definition or corpus fixture changed in the diff (review target), and no validator or hard limit was relaxed
- AC-4: new side-by-side SVGs and updated references/comparison docs are committed for all three briefs, with the ATTEMPTED / REALIZED / REFUSED table per brief

### Out of scope

Changing #79's compilers themselves (they are Concept Engine v2's), Geometry Core, validators; polygon geometry;
merging to main.

### Affected domains

backend, geometry, validator, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

#109

### Required locks

planner-core (shared), geometry-core (shared), validator-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_demo_alternatives.py
- AC-2 -> pytest:backend/tests/architectural_brain/test_demo_alternatives.py
- AC-3 -> pytest:backend/tests/architectural_brain/test_benchmark_briefs.py
- AC-3 -> review:the diff changes no benchmark brief, site definition or corpus fixture, and relaxes no validator or hard limit
- AC-4 -> file:docs/reports/poc-architectural-brain/brief-1/comparison.md ; grep:docs/reports/poc-architectural-brain/brief-1/comparison.md:REFUSED

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/poc-architectural-brain/brief-*/ (new SVGs, references.md, comparison.md).

### Knowledge check

Consulted: the owner's Phase 2 specification (2026-09-23, TRACK 1), `docs/reports/poc-architectural-brain/README.md`,
`concept_compilers.py` and `docs/reports/concept-engine-v2-diversity-report.md` on `integration/concept-engine-v2`,
`spikes/architectural_brain/realize.py`, `concept_spec.py::realized_circulation_class`, Track 3's `RealizationIntent`.
