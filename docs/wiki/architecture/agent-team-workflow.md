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
scripts/agentctl approve N --kind lost_allowance --note "..."     # the only lead acknowledgement left
scripts/agentctl pause | resume                                     # also available to the owner on Telegram
scripts/agentctl remote doctor | pair | unpair | start | stop | status   # the Telegram control plane
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
dependency order, keep the daemon running, answer `agentctl status`, approve or redirect blocked
work, and report the outcome to the user. The Team Lead does not implement product code itself.

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

**Owner pairing.** Only one numeric Telegram user id is the owner; usernames, display names and
message text claiming ownership are never trusted. `agentctl remote pair` prints a random six-digit
code valid `pairing_ttl_seconds` (10 min) for one use; the owner sends `/pair <code>` in a private
chat; the service stores the numeric user id + chat id (`owner_paired` event) and deletes the
code. Re-pair: run `pair` again (a new user replaces the old). Unpair: `agentctl remote unpair`.
Every other user gets "Not authorized" and a `remote_denied` audit event.

**Conversation.** The owner writes naturally in Hebrew or English. Slash commands (`/status`,
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

## Pilot record

See the "Pilot" section of `docs/AGENT_TEAM_PHASE_0_ENVIRONMENT_REPORT.md` — filled in when the
first low-risk Issue has gone Issue → poll → worker → PR → gates → review → merge → smoke → closed.

## Last verified against git

Branch `infra/agent-team` (this page lands with the Phase F commit).
