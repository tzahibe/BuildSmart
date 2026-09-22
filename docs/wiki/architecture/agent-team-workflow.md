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
| **Owner** (the user) | — | Telegram (`@buildsmart_teamlead_bot`, paired) or the GitHub UI | the only authority over the backlog (which Issues exist), `owner:approved`, and the final merge |
| Master Team Lead | Opus | the user's interactive Claude Code session (`.claude/skills/agent-team-lead`) and the Telegram interpreter | understand requests, **propose** Issue contracts/decomposition/dependencies/criteria/risk, execute approved Issues, recommend merges, decide on blocked work — never create product Issues, add `owner:approved` or merge on its own |
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

**Title convention.** Every agent Issue's title carries its own number right after the `[agent]`
prefix: `[agent] #N Title` (`issue_contract.numbered_title`/`strip_title_number`, Issue #25). This
is purely cosmetic — GitHub list views, Telegram status lines, and notifications show the number
without opening the Issue — and is orthogonal to the branch/worktree slug: `slugify()` strips both
`[agent]` and a leading `#N` before slugifying, so `[agent] #17 X` and `[agent] X` yield the same
slug and retitling an in-flight Issue never changes its branch/worktree lookup. `agentctl issue
create` retitles the Issue with its own number immediately after `create_issue` returns it.
`agentctl issue renumber-titles [--dry-run] [--all-states]` is the idempotent one-off pass over
already-open Issues (or all states, with `--all-states`): it rewrites any open Issue carrying an
`agent:*` label whose title does not already start with `[agent] #<its own number> `, replacing a
stale `#<other number>` prefix where present; running it twice makes no further changes.

## Lifecycle (labels mirror states one-to-one)

`agent:draft` → `agent:queued` **+ `owner:approved`** → `agent:claimed` → `agent:working` →
`agent:pr-open` → `agent:ci` → `agent:review` → **`agent:ready-for-owner`** → (owner merges) →
`agent:merged` → `agent:done`, with `agent:fix-required` (repair loop / owner change request) and
`agent:blocked` (Team Lead decision / owner reject) as the side states. An Issue is executable only
with BOTH `agent:queued` and `owner:approved`; the orchestrator and the Team Lead never add
`owner:approved` (the owner does: Telegram "Create & Queue" / "approve", or the GitHub UI). At
`READY_FOR_OWNER` every gate is green for the validated SHA, a READY FOR OWNER report is posted on
the Issue and sent to Telegram, and the workflow waits: the orchestrator never merges. The transition table is `state_machine.py`; the SQLite store (`.agent/state/
orchestrator.sqlite3`, WAL) is the truth; labels are re-applied from it by reconciliation.

## Scheduler and resources

Every tick (`github.poll_interval_seconds`, default 120 s): reconcile → poll `agent:queued` →
plan (FIFO by Issue number) → start what may start → advance every in-flight Issue one step.

An Issue starts only when: all `Dependencies` are `agent:done` (or closed on GitHub if
untracked); its locks are free (exclusive vs. exclusive/shared; shared coexists with shared);
a worker slot is free (`max_worker_agents`: 2 at V1, raised to 3 on 2026-09-17 with the owner's
permission on the M1 Pro 10-core/32 GB machine; `max_active_issues` 3); the weighted capacity has
room (LIGHT/MEDIUM/HEAVY = 1/2/3 against `weighted_capacity` = 7); the machine is not under
pressure (`cpu_threshold_percent` 75, `min_free_memory_gb` 6, sampled with psutil). Heavy
validation (the corpus, full pytest, sweeps, post-merge smoke) goes through a separate persisted
semaphore, `heavy_job_concurrency` = 1, so free agent slots never mean "run three sweeps".
Config is read at orchestrator start: a concurrency change takes effect at the next restart
(`launchctl kickstart -k gui/$UID/com.buildsmart.agent-team.orchestrator`, done only while no
worker/reviewer subprocess is running).

**Subscription usage guard** (`scripts/agent_team/usage_guard.py`, owner rule of 2026-09-17: "at
98 % stop the agents and tell them to wait; resume when the session renews"). Every
`usage_guard.probe_every_seconds` (120 s) the orchestrator runs `claude -p "/usage"` — a
zero-cost local command that prints the real session/week percentages and reset times — and
stores the snapshot in `meta.usage_last` (shown by `agentctl status` and the Telegram status).
At `pause_at_percent` (98, session *or* week) it pauses itself with source `usage_guard`: no new
claims, workers, reviewers or repair loops; running subprocesses finish their current run; the
owner gets a Telegram notice with the reset times. Below `resume_below_percent` (90 — i.e. after
the window reset) it resumes automatically and notifies again. An automatic pause never lifts a
pause the owner set (`scheduler_pause_source` distinguishes them), and the owner's `/resume`
still works during an automatic pause. A worker run that fails with a rate-limit message
(`looks_rate_limited`: "usage limit", "rate limit", 429, "resets at", "overloaded"…) is requeued
**without consuming a repair attempt** (`failure_class RATE_LIMITED`, event `rate_limited`) and
also triggers the pause; a rate-limited reviewer run is retried after the pause. Events:
`usage_pause`, `usage_resume`.

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
   **O1, shadow mode (Issue #66)**: the frozen-outcome invariants (status + refusal code per
   context) are also evaluated straight from the head snapshot via
   `backend/spikes/failure_log_sweep/snapshot_invariants.py evaluate` — no corpus replay, near
   zero cost. The old `TEST_MODE=REGRESSION` replay stays as the ground truth (this is *not* yet
   the third replay's removal); a "Compare invariants verdicts" step fails the job if the two
   verdicts (pass/fail + the set of failing contexts) ever disagree, or if the replay itself
   failed. `test_frozen_context_reproduces_expected_outcome` now also supports a `CORPUS_SNAPSHOT`
   env-var snapshot mode (failing loudly on a stale/short snapshot) for exactly this purpose, but
   the replay step runs `test_frozen_regression_corpus.py` in its own pytest invocation with
   `CORPUS_SNAPSHOT` unset, so it keeps genuinely replaying; `test_quality_baseline.py`'s own,
   pre-existing snapshot mode (Issue #17) still gets `CORPUS_SNAPSHOT` via a second invocation in
   the same step, scoped to just that command — only removing the first invocation's replay once
   several real PRs show identical verdicts turns the frozen test's snapshot mode on for CI too.

   **O3, shadow mode (Issue #67)**: each of the two corpus snapshots (base, head) is computed two
   ways. `corpus_snapshot.py --shard I/N` replays a deterministic partition of the corpus (sorted by
   context key, `index % N == I`, N=4 — a workflow constant); the `snapshot` job runs this as a
   matrix (`shard: [0,1,2,3]`, plus `ref: head` always and `ref: base` only on a cache miss) and the
   `merge` job unions the N shard documents via `corpus_snapshot.py --merge` into
   `head_snapshot.json`/`base_snapshot.json` — refusing (never silently) a shard set missing a
   context, duplicating one, or disagreeing on `head_sha`/`corpus_hash`. The pre-existing
   single-node replay still runs, unchanged, in its own `single_node` job — concurrently with
   `snapshot`/`merge` (both depend only on the early `resolve` job), so sharding adds no wall time
   of its own while shadow mode is on — writing `head_snapshot_single.json`/
   `base_snapshot_single.json`. In the final `regression` job, a "Compare head snapshots" /
   "Compare base snapshots" step (`corpus_snapshot.py --assert-equal`) fails the job if the merged
   and single-node documents differ after normalising volatile fields (`ms`/`seconds` timings,
   `written_at`) — status/code/sig/area/metrics per context, `sha`, `corpus_hash` and `workers`
   must be identical. Budget evaluation and every existing assertion (including O1's invariants)
   consume the merged `head_snapshot.json`/`base_snapshot.json` only after the relevant compare
   step passed; the base snapshot cache now holds the merged document, saved only after that
   compare passes. Both the `snapshot` matrix job and the `single_node` job's base-snapshot step
   vendor the HEAD checkout's corpus_snapshot.py over the base checkout before running it, so a
   merge-base that predates `--shard`/`corpus_hash` (true of every real PR until this Issue reaches
   main) still shards correctly and its single-node snapshot still carries a comparable
   `corpus_hash`. **Removal criterion**: the single-node path is only deleted after several real
   PRs show the two paths always agree — not scheduled by this Issue.

   **O2, the trusted corpus-snapshot store, shadow mode (Issue #68)**: a separate `push`-triggered
   workflow, `agent-snapshot.yml` (`on: push: branches: [main, "integration/**"]` — never
   `pull_request`, which cannot write to a branch's cache scope), computes the snapshot of every
   commit that lands on `main`/an integration branch, validates it
   (`scripts/agent_team/ci/snapshot_store.py validate_snapshot`: `head_sha` equals the pushed SHA,
   exactly 432 contexts, `corpus_hash` matches the corpus file on disk — an invalid snapshot is
   never saved or uploaded), and stores it two ways: the Actions cache under
   `corpus-snapshot-v2-<sha>-<corpus-hash>` (that branch's cache scope, restorable by any PR whose
   base is that branch — GitHub's documented base-branch rule) and a 30-day workflow artifact
   `corpus-snapshot-<sha>`. Gate-4's `resolve` job looks up that store for the merge-base snapshot,
   in order: (a) the v2 cache (lookup-only), (b) on a miss, the `push` run's artifact (found via
   `gh api …/actions/runs?head_sha=…&event=push`, filtered to `agent-snapshot` runs on
   `main`/`integration/**`). `select_base_snapshot` (same module) applies (a) → (b) → "compute
   locally", validating each candidate the same way and rejecting an invalid or missing one with a
   named reason (written to the job summary) rather than silently falling through. **Shadow mode**:
   a hit at (a) or (b) never skips the local base computation above (O3's `merge`/`single_node`
   jobs always run) — the `regression` job's "Compare base snapshots (trusted store vs local
   compute)" step (`corpus_snapshot.py --assert-equal`) additionally compares a valid trusted
   candidate against the freshly computed `base_snapshot.json` and fails the job on any difference.
   The old v1 cache key (`corpus-snapshot-v1-*`, scoped to the PR's own merge ref — never actually
   shared across PRs, confirmed by the repository's cache list before this Issue) is removed; a
   `pull_request` run never writes the v2 key itself. **Removal criterion**: the local base
   computation is only skipped once several real PRs show the trusted store always agrees with it —
   not scheduled by this Issue. See `docs/CI_SNAPSHOT_CACHE_DESIGN.md` for the full design.
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

**Architectural reference** — a PR whose domains include `geometry`, `validator` or `backend`
also gets an `# Architectural reference` block in the reviewer prompt pointing at
`docs/architecture_reference/quality_rubric.md` (the A–O rubric) and `anti_patterns.md` (the
anti-pattern library), and asking six explicit questions: does the change satisfy the Issue;
does it improve the targeted principle; is it consistent with the rubric; does it avoid
overfitting one plan; does the deterministic evidence support the behavior; are the regressions
expected and within budget. The structured verdict carries `architectural_assessment` (rubric
section → note) and `overfits_one_plan: bool`. The orchestrator downgrades an APPROVE with
`overfits_one_plan: true` to REQUEST_CHANGES, the same way it downgrades an unmet SEMANTIC_REVIEW
AC — this never upgrades a red deterministic gate: `ci_green`/`regression_green` are evaluated by
`merge_policy.decide()` independently of the review verdict, so a red gate blocks the merge
regardless of what the reviewer says.

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

## Governance: owner vs Team Lead authority (since 2026-09-18)

**Maximize safe parallel execution. The Team Lead is fully authorized to execute. Only merge
requires owner approval.**

| Who | Decides |
|---|---|
| OWNER | the product backlog — creates/approves **ROOT Issues** (`owner:approved`); product priorities; genuine product decisions; the configured maxima (`resources.*`, `max_active_issues`); the final **merge** |
| TEAM LEAD (Opus) | everything else: claiming, queueing, investigation, decomposition into child Issues, the dependency DAG, worker assignment, branches/worktrees, code within scope, tests, PRs, CI, regression, independent review, repair/retry, base updates and conflicts, docs, closing children, resource allocation, pausing/restarting workers, implementation details |
| Sonnet workers / reviewers | implementation / independent review |

**Roadmap authority (2026-09-18).** `docs/ROADMAP.md` is owner-approved: the Team Lead creates ROOT
Issues from it with `owner:approved`, moves work between Issues and pulls the next topics as capacity
frees up; product goals not on the roadmap still need the owner. The Team Lead keeps every worker
busy — free slot + no executable task ⇒ pull, decompose or unblock.

**ROOT Issue = scope boundary.** A ROOT (owner-approved product goal) authorizes its own
execution *and* any child Issue derived from it. A child carries a `### Authorization` section
(`source: inherited`, `root_issue: #N`, `parent_issue: #N`, `derived_by: team-lead`,
`scope_inherited: true`), the `agent:child` label and **no** `owner:approved` of its own.
`Orchestrator.authorization_of()` executes a child only when its ROOT is owner-approved and the
child stays inside the ROOT: `issue_contract.child_scope_problems()` refuses extra domains, locks
the ROOT does not declare (explicit or domain-implied), and a wider regression budget —
`SCOPE_ESCAPE`, the child is blocked with a comment and never runs. Work a ROOT does not require
is reported as PROPOSED PRODUCT FOLLOW-UP and waits for the owner. `agentctl issue decompose ROOT
--children …` / `issue create --child-of ROOT` create children (the ROOT gets `agent:decomposed`
and is not run as a task; `close_completed_roots()` closes it when every child is `agent:done`).
`agentctl issue create` without `--child-of` can only produce `agent:draft` — the Team Lead's
tools cannot mint ROOT authorization. `agent:hold` (owner, Telegram "don't work on it yet")
parks an authorized Issue; "queue it" lifts the hold.

**Utilization.** The scheduler polls `owner:approved` and `agent:queued` Issues (any of), queues
executable ones itself, orders candidates by ROOT then number, and starts every node whose
dependencies are `agent:done`, whose locks are free and whose weight fits — up to the configured
worker maximum (`max_worker_agents`, `weighted_capacity`, CPU/RAM thresholds; heavy validation
still serializes through `heavy_job_concurrency`). `max_active_issues` counts ROOTs in flight
(children count toward their ROOT). A finished run wakes the loop at once so the freed worker
takes the next executable task (work stealing) instead of waiting a poll interval. Locks are
released when a PR reaches `READY_FOR_OWNER` (`release_locks_at_ready`), and `READY_FOR_OWNER`
does not count as active: a PR waiting for the owner never stops unrelated work; a repair on such
a PR re-acquires its locks first. Sibling PRs whose base advanced after a merge are updated and
re-validated automatically. Idle is legitimate when no executable task exists, a dependency or
lock blocks, or the resource budget is spent — the objective is maximum safe *useful*
parallelism, never process count.

**Graceful restart.** SIGTERM (launchd `kickstart -k`, `agentctl stop`) drains: nothing new
starts, running agents finish (up to `drain_timeout_seconds`), then the process exits and launchd
restarts it; the plist's `ExitTimeOut` matches. SIGINT / `agentctl stop --now` / a second SIGTERM
stops immediately. Before 2026-09-18 a restart killed running workers mid-run (#17 lost two
attempts that way).

**Team Lead status** (`agentctl status`): ROOT ISSUES (each ROOT with its children's states),
RUNNING, WAITING, CI, REVIEW / MERGE, READY FOR OWNER, BLOCKED, AVAILABLE WORKERS `n / max`,
RESOURCES (weighted capacity, heavy jobs, machine, locks) and BLOCKERS (dependencies, held locks).

Tests: `tests/test_governance_parallel.py` — ROOT authorization, child inheritance, scope escape,
Authorization validation, owner hold, N workers from one ROOT, DAG parallelism, work stealing,
slot/capacity saturation, lock serialization, READY not blocking unrelated work, drain, child
creation by the Team Lead (and refusal for unapproved ROOTs / out-of-scope children), no automatic
merge (loader + lifecycle), owner merge with SHA re-validation, ROOT auto-close.

## Weekend / Jewish-holiday autonomous integration mode (since 2026-09-18, §26–§41)

When the owner does not manage individual merges — Fridays, Saturdays, and Yom Kippur, Sukkot
(incl. Chol HaMoed), Shemini Atzeret and Shavuot from Erev Chag to the last day, all in
`Asia/Jerusalem` (`scripts/agent_team/protected_periods.py`, Hebrew dates from `pyluach`, never
hard-coded Gregorian dates; `protected_periods` in `.agent/config.yaml`) — the orchestrator:

1. **starts a period** on the first protected day (adjacent weekend + holiday days form ONE
   period, named after the holiday when one is included): creates ONE integration branch from
   `main` (`integration/weekend-<date>` / `integration/holiday-<name>-<year>`), makes it the base
   for new worktrees and PRs, audits `PROTECTED_PERIOD_STARTED`, tells the owner; the period is
   persisted in meta and survives restarts;
2. **integrates autonomously**: a PR whose gates are all green (CI, regression within budget,
   independent APPROVE at the exact head, dependencies satisfied, ROOT authorized) is
   squash-merged by the Team Lead into the integration branch — state `INTEGRATED`, locks
   released, dependents start from the integrated base (INTEGRATED satisfies dependencies). Every
   internal merge is followed by the smoke commands on the combined head; red smoke reverts the
   squash commit and sends the Issue back for repair (`INTEGRATION_FAILURE`), recorded as a lead
   decision. Nothing lowers engineering quality; only the owner's merge is deferred;
3. **ends the period** the day after its last day: one rollup Issue (`agent:rollup`, contract
   `### Authorization: source: rollup`) and ONE rollup PR (integration branch → main) with the
   Hebrew owner summary (§32: what was done, PRs, product decisions, behavior changes, tests,
   regression, limitations, recommendation) and the technical traceability table. The rollup
   goes through the normal gates on its combined head — fast tier, corpus regression against the
   `main` merge-base with the strictest included budget, independent review of the combined diff
   — and becomes the single `READY_FOR_OWNER` item with ONE Telegram message (§34). Nothing
   integrated → the branch is deleted quietly. `PROTECTED_PERIOD_ENDED` carries the rollup PR.
4. **the owner merges the rollup** (CONFIRM MERGE / "מזג PR N"); post-merge smoke on main;
   every integrated child becomes `DONE` and closes; the branch and the mode state go away.

Owner drill-down (§35): `/rollup` or "איזה PRs נכנסו לחבילת סוף השבוע?" → the traceability text
(ROOT → children → PRs → commits → review); every child keeps its own milestone comments. Owner
change request on the rollup (§36): "לא רוצה את השינוי של Issue N" → `rollup_exclude` reverts that
Issue's squash commit on the integration branch (child → `OWNER_EXCLUDED`), the rollup's head
moves and re-validates; a free-text change request blocks the rollup for a Team Lead decision
(no worker owns a rollup). Work still running when the period ends stays in the normal
lifecycle on its current base and is never added unvalidated. `agentctl period status|start|end`,
`agentctl rollup exclude N`, `agentctl decide "…"` (records a decision for the rollup body).
**Main is never merged autonomously — the rollup PR is the owner's single merge for the period.**
Tests: `tests/test_integration_mode.py` (calendar on real 2026 dates; period start/restart;
integration instead of READY; dependents on the integrated base; rollup creation, validation,
single notification, owner merge, children done; smoke-failure revert; exclude; change request;
normal owner gate outside a period).

## Merge policy (owner-controlled)

| Risk | Required before `READY_FOR_OWNER` | Auto-merge |
|---|---|---|
| LOW / MEDIUM / HIGH | ci_green, regression_green, reviewer_green (+ `lost_allowance` acknowledgement when the contract declares a LOST budget) | **never** — `auto_merge: true` is refused by the config loader |

The orchestrator recommends (the READY FOR OWNER report ends with an Opus recommendation) and
stops. The only merge path is `Orchestrator.owner_merge()`, invoked exclusively by the owner's
explicit command — Telegram **Merge → CONFIRM MERGE** (button-bound to PR + validated SHA + a
short-lived nonce) — or the owner pressing Merge on GitHub (detected by reconciliation, audited).
Immediately before merging, `owner_merge` re-reads authoritative state and refuses unless: the
Issue is `READY_FOR_OWNER`; the requested SHA equals the validated SHA; the PR head still equals it
(otherwise readiness is invalidated and re-validation starts: "PR changed since validation.
Revalidation required."); `agent-ci-result` and `agent-review-result` are success on GitHub for that
exact SHA; the regression policy and review are green; the base has not advanced (stale-base
check); the live contract still validates. Every merge request is audited (`OWNER_COMMAND`:
source, owner id, PR, Issue, requested SHA, actual validated SHA, command id, timestamp, result,
merge commit; plus `merge_gate_audit`). A new commit on the PR at any time invalidates readiness
(`readiness_invalidated`), marks the review status stale and re-runs the gates; a new validated
SHA produces a new READY notification. After the owner's merge: a fresh worktree at
`origin/main`, the `commands.smoke` list, then `agent:done`, lock release, worktree and branch
cleanup. Reject → `BLOCKED (OWNER_REJECTED)`; an owner change request → `FIX_REQUIRED
(OWNER_CHANGE_REQUEST)` with the feedback handed to the repair worker.

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
`agentctl audit N` — the Issue's failure history, then its event timeline + run records.
`agentctl report N` — prints the Issue's work report. `.agent/logs/orchestrator.log`,
`.agent/logs/runs/<issue>/*.json` (command, model, cost, turns, permission denials, structured
output — secrets redacted), `.agent/logs/evidence/<issue>-attempt<n>.md` (the evidence handed to
that attempt's repair, one file per attempt), `.agent/contracts/<issue>.json` (contract + manifest
snapshot). Issue comments carry only milestones.

**Work reports and structured failure records** (`work_reports.py`). Every failure transition —
a worker run failing or reporting `blocked`/`needs_decision`, a publish (push/PR) failure, a CI
red run, an independent-review rejection, an owner reject/change-request over Telegram, a rate
limit (the run is requeued without consuming an attempt), or a Team Lead `agentctl block` — emits
exactly one `failure_record` event: `stage` (`worker`/`publish`/`ci`/`review`/`owner`/`usage`),
`failure_class`, `attempt`, `attempts_left`, `root_cause` (<=500 chars, redacted), `evidence_ref`
(the run record or evidence-note path), `next_action` (`requeue`/`repair`/`rerun_ci`/`blocked`/
`paused`). The same fields render the one fixed template every failure milestone comment uses
(`failure_milestone_text`), so an Issue's comments are scannable without opening a run record.

Each state change regenerates `.agent/logs/reports/<issue>.md`: a header (title, state, risk, PR,
branch, validated SHA, attempts), a "What was done" section per worker-report event (summary,
what_changed, why, implementation, files_changed, tests_run, known_limitations), a "Failure
history" table built from every `failure_record` event (time, stage, class, root cause, evidence
ref, outcome), and the redacted raw event timeline. `agentctl report N` prints it directly;
`agentctl audit N` prints the same failure-history table before the raw events. The Telegram
compact status (`status.render_compact`, the owner control plane's `scripts/agent_team/remote/`)
appends the same <=80-char root cause next to the failure class for BLOCKED and repair-pending
(`FIX_REQUIRED`) lines.

## Operating it

```
scripts/agentctl doctor                 # gh auth, claude binary, config, machine
scripts/agentctl labels                 # once: create the label catalogue
scripts/agentctl protect-main           # once: branch protection (reports the exact blocker)
scripts/agentctl dry-run                # one tick, no side effects, proposed assignments
scripts/agentctl start | stop | status  # the daemon
scripts/agentctl issue create --from contract.md --queue
scripts/agentctl issue renumber-titles [--dry-run] [--all-states]   # one-off `[agent] #N Title` pass
scripts/agentctl approve N --kind lost_allowance --note "..."     # the only lead acknowledgement left
scripts/agentctl pause | resume                                     # also available to the owner on Telegram
scripts/agentctl remote doctor | pair [--user-id N] | unpair | start | stop | status   # Telegram control plane
scripts/agentctl install | uninstall [all|orchestrator|remote]    # permanent launchd user agents (macOS)
scripts/agentctl notify "📋 עדכון: ..."                              # a Hebrew progress update to the owner's Telegram
scripts/agentctl requeue N --reason "..." | block N --reason "..." | resume-pr N [--update-base]
scripts/agentctl resume-pr N --rereview --reason "..."   # order a fresh review of the same head
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
dependency order — as `agent:draft` proposals for new product goals, or as children of an
owner-approved ROOT (`issue decompose`) that execute at once — keep the daemon running, answer
`agentctl status`, approve or redirect blocked work, and report the outcome to the user. The Team
Lead does not implement product code itself and never mints ROOT authorization or merges.

## Isolated environments

`backend/app/main.py` constructs OpenAI clients at import time, so every environment the workflow
creates without the developer's `.env` — GitHub Actions jobs, agent worktrees, smoke worktrees —
would fail at `import app.main`. The workflow therefore exports an obviously fake
`OPENAI_API_KEY` (`commands.env` in `.agent/config.yaml` for worktrees, workers, reviewers and
smoke; a job-level `env` in the gate workflows). The deterministic suites never call OpenAI and
`production_ai` tests stay skipped, so the value is never used for a request. A
`Missing credentials` failure in CI is classified `ENVIRONMENT_FAILURE` (not repairable by a
worker). After an environment fix lands on `main`, `agentctl resume-pr N --update-base` merges
the base into the blocked Issue's branch and pushes, so CI re-runs against the fixed workflow.
(Found by the Phase H pilot, PR #7, gate-2 job 105194679091.)

**CI fast-tier environment policy.** The pilot PR #7 also failed gate-2-static twice for
environment reasons unrelated to `OPENAI_API_KEY` (job 105213930461): `tests/test_local_gateway.py`
imports `torch` (a lazy import inside `app/architect/local_gateway.py`, exercised even with an
injected fake model/tokenizer), which `uv sync --group dev` alone does not install — the
`local-model` extra is not part of the `dev` group, and even if it were, the lockfile resolves
`torch` to the full CUDA stack on Linux. And `tests/test_architectural_concepts.py::
test_scenario_plans_before_geometry_and_realizes_it` asserts a wall-clock budget
(`_MAX_RUNTIME_S = 8.0`, calibrated on the developer's M1 Pro) that a shared 4-vCPU GitHub runner
under `-n 4` does not reliably meet. Fixed by:

- **CPU torch, CI-only.** After `uv sync --group dev`, gate-2-static installs CPU-only torch from
  the PyTorch CPU index (`uv pip install --index-url https://download.pytorch.org/whl/cpu
  torch`), with `astral-sh/setup-uv@v6`'s `enable-cache: true` so the download is cached across
  runs. `uv run` calls that follow use `--no-sync` so the implicit project sync doesn't remove
  this extraneous (not lock-declared) package before the tests run.
- **Wall-clock deselect, CI-only.** gate-2-static's fast tier runs with `--deselect tests/
  test_architectural_concepts.py::test_scenario_plans_before_geometry_and_realizes_it`, with a
  comment explaining why: a shared runner is not a performance reference. The test is left fully
  in place and enforced in the developer/worker fast tier (`.agent/config.yaml`'s
  `fast_tests.backend`) — this is a CI-only exception, not a change to the test or its budget.
- **Docs-only backend changes skip the fast tier.** `ci/plan.py`'s `backend_changed` (which gates
  gate-2-static's backend step) now matches only backend code/tests/deps (`backend/app/`,
  `backend/tests/`, `backend/spikes/`, `backend/pyproject.toml`, `backend/uv.lock`), not
  `backend/` as a whole — a `backend/README.md`-only PR no longer pays for `compileall` + the
  import check + the fast pytest tier. Regression-gate eligibility (`BACKEND_PRODUCT`) is
  unchanged, since it was already narrower than the old `backend_changed` and isn't the criterion
  this Issue targets.
- **Worktrees match the developer environment.** Agent worktrees and the post-merge smoke
  worktree run `uv sync --group dev --extra local-model` (`.agent/config.yaml`'s
  `worktree_setup.always`), so a worker's environment has the same `torch`/`transformers`/`peft`
  the developer machine has and can run `tests/test_local_gateway.py` itself.

(Issue #10, found via the pilot PR #7's second and third gate-2 failures.)

## Remote owner control plane (Telegram)

**Architecture.** `scripts/agent_team/remote/`: `transport.py` (Telegram Bot API, V1 = long
polling from the orchestrator machine — no public HTTP server, inbound port, webhook or tunnel; the
transport is an interface so a webhook/cloud deployment can be added later), `service.py` (a
deterministic polling *process*, `agentctl remote start|run|stop|status`, single instance via
flock + pid file, replay protection by Telegram `update_id`, offset persisted in the store),
`commands.py` (the typed owner command vocabulary and the callback-button encoding
`v1|ACTION|entity|sha-prefix|nonce`), `interpreter.py` (natural language → one typed command: the
Team Lead model runs headless with read-only tools and returns a schema-validated intent; it never
executes anything), `gateway.py` (authorization → replay protection → authoritative state re-read →
action → audit), `voice.py` (transcription adapter). Notifications go through the store's `outbox`
table, which the service drains with bounded retries (`notifications.telegram.max_attempts`,
backoff) and a dedup key `pr:<n>:READY_FOR_OWNER:<sha>` — one message per validated SHA, never
resent on scheduler ticks or restarts; a failed notification never changes the PR's state and is
visible in `agentctl status` ("Telegram: FAILED after N attempts").

**Owner pairing.** Only one numeric Telegram user id is the owner (the operator may also pair it directly at the terminal with `agentctl remote pair --user-id <id>`, audited as `owner_paired_by_operator`); usernames, display names and
message text claiming ownership are never trusted. `agentctl remote pair` prints a random six-digit
code valid `pairing_ttl_seconds` (10 min) for one use; the owner sends `/pair <code>` in a private
chat; the service stores the numeric user id + chat id (`owner_paired` event) and deletes the
code. Re-pair: run `pair` again (a new user replaces the old). Unpair: `agentctl remote unpair`.
Every other user gets "Not authorized" and a `remote_denied` audit event.

**Conversation.** The owner writes naturally in Hebrew or English; every reply is in Hebrew. Replies are fast by design: 'typing…' is sent on receipt, a fast model (`interpreter_fast_model`, no tools) classifies the intent in seconds, and only Issue drafting runs the Team Lead model with read-only repository access after an explicit '⏳' acknowledgement; updates are handled on a worker thread so polling never blocks. Slash commands (`/status`,
`/ready`, `/issue N`, `/pr N`, `/merge N`, `/reject N`, `/approve N`, `/queue N`, `/unqueue N`,
`/pause`, `/resume`, `/draft`, `/cancel`, `/help`) are parsed deterministically; everything else
goes to the interpreter with minimal structured context (current draft, current PR, ready PRs,
compact status, recent Issues) — the raw chat transcript is never the source of truth. Every
mutating action becomes a typed command (`GET_STATUS`, `LIST_ISSUES`, `GET_ISSUE`,
`CREATE_ISSUE_DRAFT`, `UPDATE_ISSUE_DRAFT`, `CREATE_ISSUE`, `APPROVE_ISSUE`, `QUEUE_ISSUE`,
`UNQUEUE_ISSUE`, `LIST_READY_PRS`, `GET_PR_DETAILS`, `PR_QUESTION`, `MERGE_PR`, `CONFIRM_MERGE`,
`REJECT_PR`, `CONFIRM_REJECT`, `OWNER_CHANGE_REQUEST`, `PAUSE_SCHEDULER`, `RESUME_SCHEDULER`,
…) that the gateway validates; there is no BASH/GIT/GH/SQL/filesystem command — Telegram is never
a remote shell.

**Issue workflow.** "תפתח issue חדש: …" → the interpreter (with read-only access to the repo) writes
a full contract → the gateway validates it (`issue_contract`) and shows the ISSUE DRAFT with
buttons **[Create only] [Create & Queue] [Edit] [Cancel]**. Follow-up messages edit the current
draft (`ISSUE_DRAFT` conversation state is persisted per chat). *Create only* creates the GitHub
Issue with `agent:draft` (no approval, no queue). *Create & Queue* creates it with `owner:approved`
+ `agent:queued` — the only place where `owner:approved` is added programmatically, and only on
the paired owner's explicit action. Existing Issues: "תאשר את 42 ותכניס אותו לתור" → approve +
queue; "אל תעבוד כרגע על 42" → unqueue. Duplicate deliveries of the same button/message cannot
create, approve or queue twice (persisted command ids).

**PR workflow.** `READY_FOR_OWNER` → Telegram message "PR #n READY FOR OWNER" (Issue, risk, CI,
regression, review, head SHA, summary, retries, limitations, recommendation) with **[Details]
[Merge] [Reject]**. "מה בדיוק שונה ב-PR 57?" / "מה אמר ה-reviewer?" are answered from the
authoritative evidence pack (contract, diff, CI evidence, reviewer verdict, audit trail) — never
invented. **Merge:** "תבצע merge ל-PR 57" or [Merge] → CONFIRM MERGE message (PR, Issue, risk,
validated SHA, CI/regression/review) with **[CONFIRM MERGE] [Cancel]**; only the button
confirmation — bound to the PR, the SHA prefix and a nonce that expires after
`merge_confirmation_ttl_seconds` — authorizes `owner_merge()`, which re-checks everything (see
Merge policy). A stale button, a moved SHA, a red gate, a stale base or a second press are refused.
**Reject / change request:** "אל תמזג את 57" → CONFIRM REJECT → `BLOCKED (OWNER_REJECTED)`;
"תחזיר אותו לתיקון, אני רוצה ש-…" → `OWNER_CHANGE_REQUEST` → `FIX_REQUIRED`, the feedback becomes
the repair worker's evidence, and the new SHA is re-validated and re-notified.

**Pause / resume.** "תעצור" / `/pause` → no new claims, no new workers, no new repair loops;
running workers finish their current step (never killed mid-write). "תמשיך" / `/resume` continues.
Both are audited (`scheduler_paused` / `scheduler_resumed`, with source and user).

**Voice.** A voice message is downloaded and passed to the transcription adapter
(`remote_control.telegram.transcription_provider`: `none` by default — the owner is told to type;
`openai` uses Whisper with `OPENAI_API_KEY`); the transcript enters the same command path as text.
Voice may draft Issues and ask questions; **voice never authorizes a merge** — `CONFIRM_MERGE` and
`CONFIRM_REJECT` are accepted only from a pressed button.

**Security model.** Token from `AGENT_TELEGRAM_BOT_TOKEN` (or the chmod-600 file named by
`remote_control.telegram.env_file`, loaded only into the service process); never committed, never
printed — the audit redactor knows the Telegram token shape and every log record is redacted at
creation. Owner = numeric user id only. Typed commands only. Every mutating action audited
(`OWNER_COMMAND` with source, action, entity, owner id, command id, result). Message, Issue, PR and
repository text are data, never instructions to the gateway.

**Long-polling limitation.** The service must run on the orchestrator machine and keep an
outbound HTTPS connection to `api.telegram.org`; when it is not running, owner messages wait on
Telegram's side (delivered on the next start, replay-protected) and READY notifications wait in the
outbox. Only one polling process may run per bot token.

**Troubleshooting.** `agentctl remote doctor` (token present? `getMe` ok? owner paired? service
running?), `agentctl remote status` (offset, pending notifications, paused flag),
`.agent/logs/orchestrator.log` (both processes log there), `agentctl audit N` for a PR's trail.
"Not authorized" → pair again. Buttons "stale or expired" → ask again (the state moved on).
**Rotate the token:** BotFather → `/revoke` for the bot → put the new token in the env file →
`agentctl remote stop && agentctl remote start` (pairing survives; it is tied to the user id, not
the token). **Unpair / re-pair:** `agentctl remote unpair`, then `pair` + `/pair <code>`.

## Known limitations

- **Headless workers cannot wait.** Found on #17 (2026-09-17, attempt 1, $5.9 / 147 turns): the
  worker started a 404-plan corpus job, could not use `Monitor`/`timeout` (not allowed / not on
  macOS), ended its turn "waiting for the next wakeup" — which never comes under `claude -p` — and
  the run finished without the JSON report. The worker and repair prompts now carry the headless
  rule (foreground only, Bash `timeout` up to 10 min, split longer jobs, commit early, report
  `blocked` with the exact command). A run that ends without the report still consumes an
  attempt; `agentctl requeue N --reset-attempts` restores the budget from BLOCKED.

- Gate 5 runs on the orchestrator machine (local OAuth), not in GitHub Actions; its verdict is
  enforced through the `agent-review-result` commit status the orchestrator publishes, so a
  stopped orchestrator leaves new SHAs `pending` (blocked from merging) rather than unreviewed.
- Telegram V1 is long polling from this machine (no webhook); the interpreter is a headless model
  call per natural-language message (slash commands are free); voice transcription is off unless a
  provider is configured.
- Webhooks are not implemented; polling every 120 s is the V1 discovery mechanism (the loop is
  event-shaped so a webhook receiver can call `tick()` later).
- Rate limits of the Pro subscription bound real concurrency; the resource manager does not yet
  read API quota.
- GitHub sub-issues are not used; dependencies live in the contract (`Dependencies`) and the store.
- The Telegram/remote-control gateway (`scripts/agent_team/remote/gateway.py`, merged to `main` via
  #16) applies the title-numbering convention above: its `CREATE_ISSUE` handler retitles a new
  Issue with `numbered_title()` right after `create_issue` returns the number, and its
  status/`LIST_ISSUES` lines use `strip_title_number()` so the Issue's own number is not shown
  twice.

## Pilot record (2026-09-17)

Pilot Issue #6 (LOW, docs-only, `backend/README.md`) completed end-to-end: Issue → poll → claim
→ Sonnet worker (1 attempt, 31 turns, $0.60, 151 s) → branch `agent/6-document-the-autonomous-workflow-entry-p`
→ PR #7 → gates → independent Sonnet review APPROVE (incl. one SEMANTIC_REVIEW criterion) →
LOW-policy merge (squash `64f0fd70`) → post-merge smoke (164 passed) → closed `agent:done`;
total agent cost ≈ $0.67. Two red gate-2 runs on the way were environment defects of the
workflow, not of the product, fixed through the workflow itself: Issue #8 / PR #9 (`0f4bb586`:
dummy `OPENAI_API_KEY` for isolated environments, `gh api --allow-escape-sequences` for
logs/artifacts, contract refresh from the live Issue before review/merge, stale-lock heartbeat
fallback, skipped gate-4 == regression_green) and Issue #10 / PR #11 (`3edb7d07`: CPU-only torch
in gate 2, documented CI deselect of the wall-clock budget test, `backend_changed` only for
backend code, local-model extra in worktrees); Issue #14 / PR #15 (`7814dc1b`) added the lead's
re-review command after a factually wrong reviewer verdict (the repair worker correctly refused
to "fix" a correct commit hash). No admin bypass occurred (`merge_gate_audit` bypass=false for
every merge). The merges of that day were made by the orchestrator under the then-current policy;
since the governance change the orchestrator never merges (see Merge policy).

## First ROOT Issue under the new governance: #17 (2026-09-18)

PR #23 (`d7c79a3`) reached READY_FOR_OWNER at 08:2x after 3 worker runs, 1 lead-ordered repair
and 5 CI cycles. What the workflow learned, all fixed on the Issue branch and on PR #16:
- workers cannot wait in headless mode (prompt rule); a run that ends without the report costs
  an attempt — `requeue --reset-attempts` restores the budget;
- wall-clock budgets are not CI evidence: `backend/tests/wallclock.py` + `WALLCLOCK_BUDGETS=off`
  in gate-2 (functional assertions keep running; budgets enforced locally);
- gate-4 costs two corpus passes (~23 min each on the runner): 120-min job budget, the merge-base
  snapshot cache is saved right after it is computed, the orchestrator waits up to 150 min;
  regression-tier tests must consume `CORPUS_SNAPSHOT` instead of replaying the corpus;
- the classifier called a timing failure IMPLEMENTATION_FAILURE: the lead pauses, blocks, fixes
  the infra and `resume-pr`s; a wrong-scope finding is sent back with `agentctl repair`;
- restarting the orchestrator mid-run killed two attempts before the drain existed.

## First protected period (Yom Kippur 2026, started Fri 2026-09-18) — what changed on day one

- CI: `agent-ci.yml` triggers for PRs into `integration/**` (it was `main` only, so the first three
  worker PRs had no CI); gate-2's plan and gate-4's merge-base use the PR's base (`github.base_ref`);
  gate 1 accepts an `integration/**` base. Fixes were cherry-picked onto the integration branch so they
  reach `main` with the rollup.
- Locks: released at PR open (`release_locks_at: pr_open`; repairs re-acquire first); repairs advance
  before new claims in a tick; `agentctl locks list|release`. The P0 check-style ROOTs (#34–#38) were
  relaxed to shared `validator-core`/`geometry-core` — every P0 Issue adds a check to `validation.py`
  and exclusive locks serialized the wave with two idle workers; the integration branch validates each
  combination and conflicts on registration lines resolve at base update.
- `max_active_issues` 6 (ROOTs in CI/review starved the slots at 3); worker timeout 90 min; the
  reviewer's `ac_assessment` is keyed by the leading `AC-n` (an APPROVE on #18 was downgraded because
  the reviewer wrote `AC-3: text`); a decomposed ROOT tracked before its label appeared is blocked, not run.
- Lead levers used: `agentctl repair` (targeted repairs on #24/#25 with the review findings spelled
  out), contract amendments for engineering constraints (#24 gate-3 routing, #25 dry-run evidence as a
  committed file), manual base merges when the integration branch gained fixes.
- Integrated by 13:50: #18, #24, #25, #29, #30, #31, #33 (7); PR CI ~50 min each with a warm base cache.

## Last verified against git

`7244159` (main) — owner-controlled governance + Telegram owner control plane (PR #16) is merged.
