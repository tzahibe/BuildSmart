# [agent] Reviewer integration: independent reviews consult the rubric, annotations and anti-pattern library; deterministic checks stay authoritative

### Goal

Geometry/circulation/interior-layout PRs are reviewed against the accepted architectural principles, with
the explicit six questions of the reference-based review, without ever overriding deterministic validation.

### Current behavior

`scripts/agent_team/prompts/reviewer.md` gives the reviewer the contract, CI evidence, regression report,
worker report, files and diff, and its SEMANTIC_REVIEW criteria. It has no architectural reference material.

### Required behavior

1. The reviewer prompt gets a `# Architectural reference` block for PRs whose domains include geometry,
   validator or backend planner modules: pointers to `quality_rubric.md`, the anti-pattern library and the
   annotations, plus the six questions (satisfies the Issue; improves the identified principle; consistent
   with the rubric; avoids overfitting one plan; deterministic evidence supports the behavior; regressions
   expected and within budget). The reviewer's structured verdict gains `architectural_assessment`
   (section → note) and `overfits_one_plan: bool`.
2. The orchestrator downgrades an APPROVE to REQUEST_CHANGES when `overfits_one_plan` is true, and never
   upgrades a failing deterministic gate — the merge policy is unchanged.
3. Orchestrator tests cover both rules with the fake reviewer.

### Acceptance Criteria

- AC-1: the reviewer prompt names the rubric, the anti-pattern library and the six questions for geometry/validator/backend PRs
- AC-2: the verdict schema has `architectural_assessment` and `overfits_one_plan`, and an APPROVE with `overfits_one_plan: true` becomes REQUEST_CHANGES
- AC-3: a red deterministic gate is never turned green by any review outcome (existing merge-policy test extended)

### Out of scope

Changing what deterministic gates require; the rubric content itself.

### Affected domains

infra

### Risk

LOW

### Resource class

LIGHT

### Dependencies

#29

### Required locks

ci-infra (shared)

### Verification plan

- AC-1 -> grep:scripts/agent_team/prompts/reviewer.md:quality_rubric ; grep:scripts/agent_team/prompts/reviewer.md:overfitting
- AC-2 -> pytest:scripts/agent_team/tests/test_hardening.py::test_overfit_verdict_is_downgraded
- AC-3 -> pytest:scripts/agent_team/tests/test_hardening.py::test_review_never_overrides_a_red_gate

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md (review section).

### Knowledge check

Consulted: `prompts/reviewer.md`, `schemas.py` (REVIEW_VERDICT_SCHEMA), `orchestrator._reviewer_run` (semantic downgrade exists for unmet SEMANTIC_REVIEW ACs). What remains: the reference block, the two new fields and the downgrade rule.
