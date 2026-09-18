# [agent] Record the Phase H pilot outcome on the agent-team Wiki page

### Goal

The canonical Wiki page for the autonomous workflow states, from real data, that the first pilot
completed end-to-end and what it found, so a reader knows the workflow has been exercised for real.

### Current behavior

docs/wiki/architecture/agent-team-workflow.md has a "## Pilot record" section that only says the
record is filled in once the first low-risk Issue has gone through, and a "## Last verified
against git" section naming the infra branch.

### Required behavior

Replace the body of "## Pilot record" with a compact record (a short paragraph plus a bullet
list, no more than 25 lines) stating exactly these facts, verbatim numbers included:
pilot Issue #6 (LOW, docs-only, `backend/README.md`) ran Issue → poll → claim → Sonnet worker
(1 attempt, 31 turns, $0.60, 151 s) → branch `agent/6-document-the-autonomous-workflow-entry-p`
→ PR #7 → gates → independent Sonnet review APPROVE (incl. one SEMANTIC_REVIEW criterion) →
LOW auto-merge (squash `64f0fd70`) → post-merge smoke (164 passed) → closed `agent:done`;
total agent cost ≈ $0.67; two red gate-2 runs on the way were both environment defects of the
workflow (not the product) and were fixed through the workflow itself: Issue #8 / PR #9 (squash
`0f4bb586`; dummy `OPENAI_API_KEY` for isolated environments, `gh api --allow-escape-sequences`
for logs/artifacts, contract refresh from the live Issue before review/merge, stale-lock
heartbeat fallback, skipped gate-4 == regression_green) and Issue #10 / PR #11 (squash
`3edb7d07`; CPU-only torch in gate 2, documented CI deselect of the wall-clock budget test,
`backend_changed` only for backend code, local-model extra in worktrees); no admin bypass
occurred (`merge_gate_audit` bypass=false for all three merges); the merge policy waited for
the Team Lead's recorded approval on both MEDIUM Issues. Update "## Last verified against git"
to `64f0fd70` (main). Change nothing else on the page.

### Acceptance Criteria

- AC-1: the Pilot record section names Issue #6, PR #7 and merge commit 64f0fd70
- AC-2: the Pilot record section names the two follow-up Issues #8 (PR #9) and #10 (PR #11) as workflow environment fixes
- AC-3: the Pilot record section states that no admin bypass occurred
- AC-4: the Last verified against git section names 64f0fd70
- AC-5: the record is accurate, compact and written for a reader of the Wiki page

### Out of scope

Any other section of the page; any other file.

### Affected domains

knowledge

### Risk

LOW

### Resource class

LIGHT

### Dependencies

#6, #8, #10

### Required locks

docs (shared)

### Verification plan

- AC-1 -> grep:docs/wiki/architecture/agent-team-workflow.md:#6 ; grep:docs/wiki/architecture/agent-team-workflow.md:PR #7 ; grep:docs/wiki/architecture/agent-team-workflow.md:64f0fd70
- AC-2 -> grep:docs/wiki/architecture/agent-team-workflow.md:#8 ; grep:docs/wiki/architecture/agent-team-workflow.md:#10
- AC-3 -> grep:docs/wiki/architecture/agent-team-workflow.md:no admin bypass
- AC-4 -> grep:docs/wiki/architecture/agent-team-workflow.md:## Last verified against git\n\n`64f0fd70`
- AC-5 -> review:the Pilot record is factually consistent with the Required behavior, at most 25 lines, and reads well for a Wiki reader

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md only.
