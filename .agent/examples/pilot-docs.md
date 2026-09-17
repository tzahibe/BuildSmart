# [agent] Document the autonomous workflow entry points in the backend README

### Goal

A new engineer opening backend/README.md learns in one short section that the repository has an
autonomous engineering workflow, where its canonical documentation lives, and which three
commands show its state.

### Current behavior

backend/README.md documents setup, run, tests and endpoints. It does not mention
scripts/agentctl or docs/wiki/architecture/agent-team-workflow.md at all.

### Required behavior

backend/README.md gains a section titled exactly "## Autonomous workflow" (placed after the
"## Tests" section) of at most 12 lines that: links to docs/wiki/architecture/agent-team-workflow.md,
lists `scripts/agentctl status`, `scripts/agentctl dry-run` and `scripts/agentctl audit <issue>`,
and states that agent PRs come from `agent/<issue>-<slug>` branches and are validated by the
`agent-ci` GitHub Actions workflow. No other file changes.

### Acceptance Criteria

- AC-1: backend/README.md contains a heading line `## Autonomous workflow`
- AC-2: the new section links to docs/wiki/architecture/agent-team-workflow.md
- AC-3: the new section mentions `scripts/agentctl status`, `scripts/agentctl dry-run` and `scripts/agentctl audit`
- AC-4: the new section mentions the `agent/` branch prefix and the `agent-ci` workflow
- AC-5: the existing backend fast test tests/test_projects.py still passes (no code was touched)

### Out of scope

Any file other than backend/README.md. Any change under backend/app, backend/tests, frontend,
scripts or .github. Rewording existing README sections.

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

- AC-1 -> grep:backend/README.md:^## Autonomous workflow$
- AC-2 -> grep:backend/README.md:docs/wiki/architecture/agent-team-workflow\.md
- AC-3 -> grep:backend/README.md:scripts/agentctl status ; grep:backend/README.md:scripts/agentctl dry-run ; grep:backend/README.md:scripts/agentctl audit
- AC-4 -> grep:backend/README.md:agent/ ; grep:backend/README.md:agent-ci
- AC-5 -> pytest:backend/tests/test_projects.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

backend/README.md only (the new section).
