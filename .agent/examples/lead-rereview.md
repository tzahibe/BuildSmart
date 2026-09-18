# [agent] Let the Team Lead request a fresh independent review after an incorrect verdict

### Goal

When the independent reviewer's verdict is shown to be factually wrong (as on PR #13: it rejected a
correct commit hash), the Team Lead can order a fresh review of the same head with a recorded
reason, instead of editing the state store by hand or pushing a commit just to move the SHA.

### Current behavior

`agentctl resume-pr N` moves a BLOCKED Issue back to PR_OPEN but keeps `review_verdict`
(`VERDICT@sha`). Because the verdict is bound to the unchanged head, the orchestrator's REVIEW step
reports "review verdict REQUEST_CHANGES (awaiting decision)" forever; the `agent-review-result`
status stays `failure`. Issue #12 is stuck this way after the repair worker correctly declined to
"fix" an accurate hash (its report: "no legitimate fix exists to apply").

### Required behavior

`agentctl resume-pr N --rereview --reason "<text>"`: the reason is mandatory with `--rereview`
(the command exits non-zero without it); it clears the stored `review_verdict`, records a
`review_reset_by_lead` event whose payload holds the reason and the previous verdict, posts an
Issue milestone comment with the reason, publishes the review commit status for the PR head as
`pending` (description "re-review ordered by the Team Lead"), and then resumes at PR_OPEN as
today. On the following ticks the orchestrator runs a fresh independent review for the current
head (the reviewer sees no prior verdict). `--rereview` composes with `--update-base`. The
orchestrator's review step is unchanged otherwise; product code is untouched.

### Acceptance Criteria

- AC-1: `agentctl resume-pr N --rereview --reason "..."` clears review_verdict, records review_reset_by_lead with the reason and previous verdict, and posts a milestone comment
- AC-2: `--rereview` without `--reason` fails with a non-zero exit and a clear message
- AC-3: after the reset the orchestrator runs a fresh independent review for the same head on its next REVIEW step
- AC-4: the review commit status for the head is set to pending when the reset happens
- AC-5: the orchestrator test suite passes with the new tests
- AC-6: the Wiki page's operating commands list `resume-pr N --rereview --reason` and the lead skill mentions when to use it

### Out of scope

Any change to the reviewer prompt or the review verdict schema. Any file under backend or frontend.

### Affected domains

infra

### Risk

MEDIUM

### Resource class

LIGHT

### Dependencies

#10

### Required locks

ci-infra (exclusive)

### Verification plan

- AC-1 -> grep:scripts/agent_team/cli.py:review_reset_by_lead ; grep:scripts/agent_team/tests/test_isolated_env.py:test_resume_pr_rereview_clears_the_verdict_and_records_the_reason
- AC-2 -> grep:scripts/agent_team/tests/test_isolated_env.py:test_rereview_requires_a_reason
- AC-3 -> grep:scripts/agent_team/tests/test_isolated_env.py:test_fresh_review_runs_after_a_lead_reset
- AC-4 -> grep:scripts/agent_team/cli.py:re-review ordered by the Team Lead
- AC-5 -> cmd:scripts/agent_team/ci/run_orchestrator_tests.sh
- AC-6 -> grep:docs/wiki/architecture/agent-team-workflow.md:--rereview --reason ; grep:.claude/skills/agent-team-lead/SKILL.md:--rereview

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md (operating commands), .claude/skills/agent-team-lead/SKILL.md (Decide section).
