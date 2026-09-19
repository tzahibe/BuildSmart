# [agent] Reference annotations: WHY THIS PLAN WORKS for every reference entry, tied to the rubric

### Goal

Every reference entry gets a short architectural annotation that names the principles it demonstrates
(rubric sections) and its trade-offs, so workers and reviewers learn principles, not geometry.

### Current behavior

No annotations exist (the reference set is created by the sibling Issue).

### Required behavior

1. `docs/architecture_reference/references/<id>/annotation.md` for every index entry: `## Why this plan works`
   (3–8 bullets, each ending with the rubric section it demonstrates, e.g. `[A]`), `## Trade-offs`,
   `## Anti-patterns avoided` (links into the anti-pattern library).
2. `references/index.json` entries gain `annotation: true`; the index test checks every entry has one.

### Acceptance Criteria

- AC-1: every index entry has an `annotation.md` with a `## Why this plan works` section whose bullets carry rubric tags
- AC-2: each annotation lists at least one trade-off

### Out of scope

Changing the reference set or the rubric.

### Affected domains

knowledge

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

#29, #30

### Required locks

docs (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/reference/test_reference_index.py::test_every_entry_has_an_annotation_with_why_it_works
- AC-2 -> pytest:backend/tests/reference/test_reference_index.py::test_every_annotation_lists_a_trade_off

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/references/*/annotation.md.

### Knowledge check

Consulted: EPIC 0 knowledge check. Depends on the collection and the rubric.
