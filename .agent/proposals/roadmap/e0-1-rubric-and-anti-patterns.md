# [agent] Quality rubric A–O and the anti-pattern library (docs/architecture_reference)

### Goal

Write the canonical architectural quality rubric and the anti-pattern library that every later
geometry/circulation/interior Issue and every reviewer refers to.

### Current behavior

No `docs/architecture_reference/` exists. Quality knowledge is scattered: M1–M6 metrics and their measured
gaps (`docs/wiki/architecture/geometry-validation.md`), the guest-WC spec's PublicAccess/EntranceZone/Pocket
vocabulary, the L-massing and wet-room investigation reports, memories of measured gaps (hub topology, wet
adjacency, strip-shaped public rooms).

### Required behavior

1. `docs/architecture_reference/quality_rubric.md` with sections A–O exactly as the EPIC lists them; for each
   section: the principle in two sentences, the deterministic signals that exist today (check id / metric)
   or are planned (Issue reference), what reference comparison adds, what only semantic review can judge,
   and a short "how a reviewer applies it" line. Signals are measured on realized geometry.
2. `docs/architecture_reference/anti_patterns.md`: one entry per anti-pattern in the EPIC's list, with:
   description, why it is bad, the detection signal (existing C-check/metric, or "proposed: Issue N"), an
   example from the corpus where one exists (context id), and the rubric section it violates.
3. Cross-links from `docs/wiki/INDEX.md` and the geometry-validation Wiki page.

### Acceptance Criteria

- AC-1: the rubric file has headings `## A.` through `## O.` and every section contains the words `Deterministic signal`, `Reference comparison` and `Semantic review`
- AC-2: the anti-pattern file has an entry for each of the 14 listed anti-patterns with a `Detection:` line
- AC-3: the Wiki index links to both files

### Out of scope

Reference plans, benchmark code, reviewer prompt changes (sibling Issues).

### Affected domains

knowledge

### Risk

LOW

### Resource class

LIGHT

### Dependencies

none

### Required locks

docs (shared)

### Verification plan

- AC-1 -> grep:docs/architecture_reference/quality_rubric.md:## O\. ; grep:docs/architecture_reference/quality_rubric.md:Semantic review
- AC-2 -> grep:docs/architecture_reference/anti_patterns.md:door-fixture ; grep:docs/architecture_reference/anti_patterns.md:Detection:
- AC-3 -> grep:docs/wiki/INDEX.md:architecture_reference

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/quality_rubric.md, docs/architecture_reference/anti_patterns.md, docs/wiki/INDEX.md.

### Knowledge check

Consulted: the EPIC 0 knowledge check; `docs/wiki/architecture/geometry-validation.md`; memories of measured gaps. Nothing of the rubric exists yet.
