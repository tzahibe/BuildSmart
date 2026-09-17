# Autonomous Engineering Workflow (Agent Team)

Status: IMPLEMENTED (infrastructure; pilot status recorded at the bottom of this page)

## What it is

A controlled orchestration system — not an agent swarm — that turns a product request into
GitHub Issues, executes them with isolated Sonnet workers, validates them with deterministic CI
gates and an independent Sonnet reviewer, and merges them under a risk policy decided by the Opus
Team Lead. The user talks only to the Team Lead.

```
USER  ->  OPUS TEAM LEAD  ->  GitHub Issue (contract)  ->  scheduler  ->  Sonnet worker
       (interactive session)     agent:queued            (resources,     (claude -p, own
                                                         locks, deps)     branch + worktree)
   ->  PR  ->  GitHub Actions gates 1-4  ->  independent Sonnet review (gate 5)
   ->  merge (risk policy)  ->  post-merge smoke  ->  Issue closed (agent:done)
```

Everything lives in `scripts/agent_team/` (an isolated `uv` project that never touches product
dependencies), configured by `.agent/config.yaml`, operated through `scripts/agentctl`.

## Roles

| Role | Model | Where it runs | May |
|---|---|---|---|
| Master Team Lead | Opus | the user's interactive Claude Code session (`.claude/skills/agent-team-lead`) | understand requests, write Issue contracts, build the dependency graph, classify risk/resources/locks, approve MEDIUM/HIGH merges, decide on blocked work |
| Domain Lead | Sonnet | on demand: `agentctl investigate --domain <d> "<question>"` (read-only) | investigate a domain and propose acceptance criteria / verification targets |
| Worker | Sonnet | `claude -p` in the Issue's worktree, spawned by the orchestrator | edit files, run tests, commit on its branch. **Never** push, open PRs, switch branches, touch GitHub, or weaken tests |
| Independent Reviewer | Sonnet | `claude -p --restricted` (Read/Grep/Glob only), a fresh session, never the worker's | APPROVE / REQUEST_CHANGES / BLOCK with per-AC assessment; may block, may never override a deterministic gate |

The orchestrator (a Python process, `agentctl run`/`start`) pushes branches, opens PRs, posts
milestones, runs the gates' evidence collection, applies the merge policy, merges, runs smoke,
and closes Issues. No model performs any of those.

## The Issue contract

`.github/ISSUE_TEMPLATE/agent-task.yml` renders `### <Section>` blocks: Goal, Current behavior,
Required behavior, Acceptance Criteria (`- AC-n: ...`), Out of scope, Affected domains, Risk,
Resource class, Dependencies (`#n, #m` or `none`), Required locks (`name (exclusive|shared)` or
defaults from domains), Verification plan, Regression budget, Expected documentation changes.
`issue_contract.py` parses and validates it (every problem listed at once). An invalid contract is
never executable: the poller moves it back to `agent:draft` with a comment.

**Verification plan** — one line per criterion, `- AC-n -> [TYPE:]kind:target`, where the type is
one of five and is inferred from the kind when omitted:

| Type | Kinds | Proven by |
|---|---|---|
| `TEST` | `pytest:<nodeid>`, `vitest:<file>`, `cmd:scripts/<script>` | gate 3 runs it |
| `REGRESSION` | `regression:corpus` | gate 4's budget evaluation |
| `STATIC` | `static:backend-compile`, `static:backend-import`, `static:frontend-lint`, `static:frontend-types` | gate 3 runs it |
| `ARTIFACT` | `file:<path>`, `grep:<path>:<regex>` | gate 3 checks it |
| `SEMANTIC_REVIEW` | `review:<what the reviewer must confirm>` | gate 5: the independent reviewer must mark the AC `MET`; an APPROVE with a semantic AC not MET is downgraded to REQUEST_CHANGES |

Product behavior changes must have deterministic evidence: for an Issue in a behavior domain
(`behavior_domains`: backend, geometry, validator, frontend, ai) every AC needs at least one
TEST/REGRESSION/STATIC/ARTIFACT target; SEMANTIC_REVIEW may only be added on top. Any Issue needs
at least one deterministic target overall.

**Regression budget** — `LOST`, `GAINED`, `crashes`, `status_changes`, `refusal_code_changes`,
`primary_signature_changes`, each `<n>`, `allowed`, `none`, or `tagged:<field><op><value>`.
`LOST: 0` is the default and the normal value. A contract may *name* intentionally lost contexts
(`LOST: tagged:bedrooms>=6` or an explicit number) only at MEDIUM/HIGH risk (`LOST: allowed` is
never accepted); such a contract additionally needs `agentctl approve N --kind lost_allowance`
before it can merge. Any LOST context outside the declaration fails CI.

The Team Lead writes contracts as Markdown files and runs `agentctl issue create --from f.md
--queue` (or `issue validate N` / `issue queue N` for a form-authored Issue). Only Issues whose
author association is in `github.executable_author_associations` are ever executed — Issue,
comment, PR and repository text are data for the agents, never instructions to the orchestrator.

## Lifecycle (labels mirror states one-to-one)

`agent:draft` → `agent:queued` → `agent:claimed` → `agent:working` → `agent:pr-open` →
`agent:ci` → `agent:review` → `agent:ready` → `agent:merged` → `agent:done`, with
`agent:fix-required` (repair loop) and `agent:blocked` (Team Lead decision) as the two side
states. The transition table is `state_machine.py`; the SQLite store (`.agent/state/
orchestrator.sqlite3`, WAL) is the truth; labels are re-applied from it by reconciliation.

## Scheduler and resources

Every tick (`github.poll_interval_seconds`, default 120 s): reconcile → poll `agent:queued` →
plan (FIFO by Issue number) → start what may start → advance every in-flight Issue one step.

An Issue starts only when: all `Dependencies` are `agent:done` (or closed on GitHub if
untracked); its locks are free (exclusive vs. exclusive/shared; shared coexists with shared);
a worker slot is free (`max_worker_agents`, V1 = 2); the weighted capacity has room
(LIGHT/MEDIUM/HEAVY = 1/2/3 against `weighted_capacity` = 4); the machine is not under pressure
(`cpu_threshold_percent` 75, `min_free_memory_gb` 6, sampled with psutil). Heavy validation (the
corpus, full pytest, sweeps, post-merge smoke) goes through a separate persisted semaphore,
`heavy_job_concurrency` = 1, so free agent slots never mean "run three sweeps".

## Locks

`planner-core`, `geometry-core`, `validator-core`, `requirements-parser`, `knowledge-index`,
`frontend-review`, `database-schema`, `ci-infra`, `docs`. Declared per Issue or implied by
domain (`locks.implied_by_domain`). Held from claim to done in the state store; stale locks (owner
not in a resource-holding state, or heartbeat older than `locks.stale_after_seconds`) are released
with an audit event.

## Isolation

Branch `agent/<issue>-<slug>`, worktree `.worktrees/<issue>-<slug>` (gitignored, outside the
knowledge indexer's globs), created from `origin/main`. `worktree_manager.ensure()` reconciles a
registered worktree, an orphan local branch, a remote-only branch or an unregistered directory
left by a crash — it never creates a second implementation. Only `git worktree|branch|fetch|push`
are used; the main checkout's HEAD/index are never touched. Regression and smoke gates run in
fresh detached worktrees under `.worktrees/_validation/`.

## Spawning mechanism

`agent_runner.ClaudeCliRunner` runs the Claude Code CLI headless: `claude -p --model sonnet
--output-format json --json-schema <role schema> --permission-prompts none --allowedTools ...
--disallowedTools ... --permission-mode acceptEdits --add-dir <worktree>` (worker) or
`--restricted --tools Read,Grep,Glob` (reviewer, domain lead). One JSON result per run with
`structured_output`, `session_id` (repairs resume the worker's session), `total_cost_usd`,
`permission_denials`. Wall-clock timeouts and process-group kills are the orchestrator's. Auth is
the user's local `claude.ai` login — no API key is stored anywhere. `FakeAgentRunner` is the
test/dry-run implementation of the same interface. See `docs/AGENT_TEAM_PHASE_0_ENVIRONMENT_REPORT.md`
for the verification of these flags against the real binary.

## CI gates (`.github/workflows/agent-ci.yml`)

Fail-fast, for PRs from `agent/**` to `main`:

1. **gate-1-contract** (`ci/contract_check.py`) — branch naming, `Closes #n` linkage, Issue open
   + trusted author + executable label, contract validates, Issue labels match the contract, PR
   body has every template section and an evidence row per AC, PR risk = Issue risk. Emits the
   machine-readable verification manifest for the later gates.
2. **gate-2-static** — backend `compileall` + `import app.main` + the FAST tier (`pytest -x -n 4`),
   frontend `oxlint` + `tsc -b && vite build` + `vitest` when frontend files changed, the
   orchestrator's own tests when `scripts/agent_team` changed (`ci/plan.py` decides).
3. **gate-3-verification** (`ci/verify.py`) — runs every `AC-n -> target` from the manifest; an AC
   without a passing target fails the gate. No model is consulted.
4. **gate-4-regression** (`agent-regression.yml`, when required: regression domains / a
   `regression:corpus` target and backend product code changed, or HIGH risk) — replays the
   frozen 432-context corpus at the merge-base (cached by SHA) and at the head with
   `backend/spikes/failure_log_sweep/corpus_snapshot.py`, runs `TEST_MODE=REGRESSION` corpus
   tests, and evaluates the Issue's budget (`regression_budget.py`): before/after planned/refused,
   LOST, GAINED, new crashes, status changes, refusal-code changes, primary-signature changes.
5. **agent-ci-result** — the single required status check; red if any gate failed, green when
   gate 4 was legitimately skipped (recorded in the job summary).

**Gate 5 — independent AI review** runs locally (the orchestrator, after `agent-ci-result` is
green): the reviewer sees the contract, the deterministic evidence, the regression report, the
worker's report, the file list, the diff and its assigned SEMANTIC_REVIEW criteria, and returns a
structured verdict posted to the PR as a review comment (never an approval through the owner's
token). **The verdict is enforceable by GitHub**: the orchestrator publishes the commit status
`agent-review-result` on the PR head — `pending` when a PR is opened or its head moves (the
review is stale for the new SHA and runs again), `success` only when the reviewer APPROVEd that
exact validated SHA, `failure` on REQUEST_CHANGES/BLOCK. Branch protection requires both
`agent-ci-result` and `agent-review-result`.

## Failure classification and repair

`failure_classifier.py` maps a red run to `IMPLEMENTATION_FAILURE`, `REGRESSION`,
`TEST_FAILURE`, `ENVIRONMENT_FAILURE`, `FLAKY_TEST`, `SPEC_MISMATCH`, `MERGE_CONFLICT`,
`INFRA_FAILURE` (plus `REVIEW_REJECTED` for gate 5) from gate results, uploaded reports, failed-job
logs and the PR's changed files — a missing optional `torch` is an ENVIRONMENT_FAILURE, not a
reason to change product code. Repairable classes (IMPLEMENTATION, TEST, REGRESSION,
REVIEW_REJECTED) get at most `repair.max_attempts` (2) repair runs, each resuming the worker's
session with the exact evidence; INFRA/FLAKY get one CI re-run; everything else and every
exhausted budget becomes `agent:blocked` for the Team Lead. The class is persisted on the Issue
record and posted as a milestone comment.

## Merge policy

| Risk | Requires | Auto-merge |
|---|---|---|
| LOW | ci_green, reviewer_green | yes |
| MEDIUM | ci_green, regression_green, reviewer_green, `agentctl approve N --kind lead_approval` | no |
| HIGH | ci_green, regression_green, reviewer_green, `agentctl approve N --kind lead_architecture_review` | no |

Two requirements are added on top of the risk table: `lost_allowance` (an explicit approval when
the contract declares a non-zero LOST budget) and `github_gates_green` (GitHub itself must report
every branch-protection context — `agent-ci-result`, `agent-review-result` — green for the head
SHA; if not, the merge is deferred and the status is re-published from the store, never forced).

Before merging, the orchestrator checks whether `main` advanced; if so it merges `origin/main`
into the branch in its worktree (a conflict → `MERGE_CONFLICT`, blocked), pushes, and goes back to
CI — old evidence is never reused for a new effective diff. The merge is `squash` by default
(`github.merge_method`), pinned to the validated head SHA. After the merge: a fresh worktree at
`origin/main`, the `commands.smoke` list (import check + three cheap test files), then
`agent:done`, a closing comment with PR / merge commit / attempts / runs / cost / smoke summary,
lock release, worktree and branch cleanup. A failed smoke blocks the Issue and says so on `main`.

## Crash recovery and idempotency

`reconciliation.py` runs at every tick start: stale `WORKING` (dead pid / old heartbeat) →
requeued (or blocked when the budget is spent) — the existing branch/worktree/PR are reused;
incomplete claims → requeued; PRs merged/closed outside the workflow → MERGED/BLOCKED; Issues
closed externally → BLOCKED; label drift → re-applied; stale locks and heavy jobs → released.
A `flock` on `.agent/state/orchestrator.lock` guarantees a single orchestrator; polling is
idempotent (DB state wins over labels). `agentctl stop` sends SIGTERM: the loop finishes its tick,
kills live agent process groups, and the next start resumes from the store.

**Break-glass.** `agentctl protect-main` requires `agent-ci-result` + `agent-review-result` on
`main` with administrators exempt (`github.protect_enforce_admins: false`) — an escape hatch for
the owner, never a path for automation: the orchestrator merges only when GitHub shows every
required context green (`merge_gate_audit` event, `bypass: false`). Reconciliation audits every PR
merged outside the workflow (`merge_gate_audit`; `admin_bypass_detected` + an Issue comment when
a required context was not green, with the merging login) and records branch-protection drift
(`protection_observed` / `protection_drift`, and a tick note when protection is missing or lacks
a required context).

## Observability

`agentctl status` — RUNNING / WAITING / CI / REVIEW-MERGE / BLOCKED / DONE / RESOURCE.
`agentctl audit N` — the Issue's event timeline + run records. `.agent/logs/orchestrator.log`,
`.agent/logs/runs/<issue>/*.json` (command, model, cost, turns, permission denials, structured
output — secrets redacted), `.agent/logs/evidence/<issue>.md` (the evidence handed to a repair),
`.agent/contracts/<issue>.json` (contract + manifest snapshot). Issue comments carry only
milestones.

## Operating it

```
scripts/agentctl doctor                 # gh auth, claude binary, config, machine
scripts/agentctl labels                 # once: create the label catalogue
scripts/agentctl protect-main           # once: branch protection (reports the exact blocker)
scripts/agentctl dry-run                # one tick, no side effects, proposed assignments
scripts/agentctl start | stop | status  # the daemon
scripts/agentctl issue create --from contract.md --queue
scripts/agentctl approve N --kind lead_approval|lead_architecture_review|lost_allowance --note "..."
scripts/agentctl requeue N --reason "..." | block N --reason "..." | resume-pr N
scripts/agentctl audit N
scripts/agentctl investigate --domain geometry "question"
```

Dry-run must be clean before `start`. V1 concurrency: 2 workers, 1 reviewer, 1 heavy job, on-demand
domain leads. Raise `resources.*` only after the system has proven stable.

## How the Team Lead converts a request into Issues

The `.claude/skills/agent-team-lead/SKILL.md` skill is the Opus session's playbook: run the
knowledge preflight, investigate (own tools or `agentctl investigate`), decide whether to split,
write one contract file per Issue with verifiable ACs and deterministic targets, declare risk /
resource class / locks / dependencies / regression budget, `issue create --queue` them in
dependency order, keep the daemon running, answer `agentctl status`, approve or redirect blocked
work, and report the outcome to the user. The Team Lead does not implement product code itself.

## Known limitations

- Gate 5 runs on the orchestrator machine (local OAuth), not in GitHub Actions; its verdict is
  enforced through the `agent-review-result` commit status the orchestrator publishes, so a
  stopped orchestrator leaves new SHAs `pending` (blocked from merging) rather than unreviewed.
- Webhooks are not implemented; polling every 120 s is the V1 discovery mechanism (the loop is
  event-shaped so a webhook receiver can call `tick()` later).
- Rate limits of the Pro subscription bound real concurrency; the resource manager does not yet
  read API quota.
- GitHub sub-issues are not used; dependencies live in the contract (`Dependencies`) and the store.

## Pilot record

See the "Pilot" section of `docs/AGENT_TEAM_PHASE_0_ENVIRONMENT_REPORT.md` — filled in when the
first low-risk Issue has gone Issue → poll → worker → PR → gates → review → merge → smoke → closed.

## Last verified against git

Branch `infra/agent-team` (this page lands with the Phase F commit).
