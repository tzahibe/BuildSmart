# [agent] Provide a dummy OPENAI_API_KEY to isolated environments and classify credential errors

### Goal

Every isolated environment the workflow creates — GitHub Actions gate jobs, agent worktrees and the
post-merge smoke worktree — can import `app.main` and collect the backend test suite without a real
OpenAI credential, and a missing-credential failure in CI is classified as an environment problem
rather than an implementation failure.

### Current behavior

`backend/app/main.py` constructs OpenAI clients at import time (`OpenAIChatAssistant()`), so any
environment without `OPENAI_API_KEY` fails with `openai.OpenAIError: Missing credentials`. The
pilot PR #7 failed gate-2-static for exactly this reason (job 105194679091); the worker had to
invent a local `.env` in its worktree; the post-merge smoke would fail the same way. The failure
classifier does not recognise this error and would report IMPLEMENTATION_FAILURE. A blocked
Issue whose environment was fixed afterwards cannot be resumed on an updated base.

### Required behavior

The gate-2, gate-3 and regression jobs export a dummy `OPENAI_API_KEY` (a literal that is
obviously not a key; the deterministic suites never call OpenAI — `production_ai` tests stay
skipped). The orchestrator injects `commands.env` from `.agent/config.yaml` into setup/test/smoke
commands and into worker/reviewer processes unless the variable is already set. The classifier
maps `openai.OpenAIError: Missing credentials` (and `OPENAI_API_KEY`-missing messages) to
ENVIRONMENT_FAILURE. `agentctl resume-pr N --update-base` merges `origin/main` into the Issue's
branch and pushes, so CI re-runs with the fixed workflow. Product code is untouched.

### Acceptance Criteria

- AC-1: the gate-2-static and gate-3-verification jobs in agent-ci.yml and the regression job in agent-regression.yml set OPENAI_API_KEY to a dummy literal
- AC-2: .agent/config.yaml declares commands.env.OPENAI_API_KEY and the orchestrator injects commands.env into shell commands and agent processes
- AC-3: the failure classifier returns ENVIRONMENT_FAILURE for an `openai.OpenAIError: Missing credentials` log
- AC-4: `agentctl resume-pr N --update-base` merges the base branch into the Issue branch and pushes before resuming at PR_OPEN
- AC-5: the orchestrator test suite passes with the new tests

### Out of scope

Any file under backend/app, backend/tests, frontend. Making the product construct OpenAI clients
lazily (a product change; separate Issue if wanted). Real OpenAI calls in CI.

### Affected domains

infra

### Risk

MEDIUM

### Resource class

LIGHT

### Dependencies

none

### Required locks

ci-infra (exclusive)

### Verification plan

- AC-1 -> grep:.github/workflows/agent-ci.yml:OPENAI_API_KEY: not-a-real-key ; grep:.github/workflows/agent-regression.yml:OPENAI_API_KEY: not-a-real-key
- AC-2 -> grep:.agent/config.yaml:OPENAI_API_KEY ; grep:scripts/agent_team/orchestrator.py:command_env ; grep:scripts/agent_team/agent_runner.py:extra_env
- AC-3 -> grep:scripts/agent_team/failure_classifier.py:Missing credentials ; cmd:scripts/agent_team/ci/run_orchestrator_tests.sh
- AC-4 -> grep:scripts/agent_team/cli.py:update_base ; cmd:scripts/agent_team/ci/run_orchestrator_tests.sh
- AC-5 -> cmd:scripts/agent_team/ci/run_orchestrator_tests.sh

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md (isolated-environment note + resume-pr --update-base); .agent/config.yaml comments.
