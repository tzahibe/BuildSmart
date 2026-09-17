# Agent Team — Phase 0 Environment Discovery & Implementation Plan

Status: INVESTIGATION (Phase 0 of the autonomous engineering workflow). Written 2026-09-17 before
any infrastructure was implemented. The canonical description of the system as built lives in
`docs/wiki/architecture/agent-team-workflow.md` once the pilot has passed; this report is the
evidence for the decisions made there.

## 1. What was inspected

| Area | Finding |
|---|---|
| Repository | Monorepo: `backend/` (FastAPI, Python 3.11, `uv`, `[tool.uv] package = false`), `frontend/` (Vite + React 19 + vitest + oxlint + Playwright), `docs/` (raw reports + `docs/wiki/` canonical pages), `specs/` (spec-kit features 001–009), `.specify/`. |
| Agent config | `CLAUDE.md` (mandatory `knowledge-refresh` preflight for non-trivial work), `.claude/skills/` (knowledge-refresh, speckit-*, taste-skill), `.claude/settings.local.json` (gitignored, two `uv` allow rules), `.claude/worktrees/015-…` (a locked historical Claude worktree). No `.claude/agents/`, no hooks. |
| GitHub | Remote `origin` = `https://github.com/tzahibe/sddproject.git`, which now **redirects to `tzahibe/BuildSmart`** (renamed; public; default branch `main`; issues enabled). 4 PRs (#1, #2, #4 closed; **#3 open**: `008-hub-eligibility`). Only GitHub's default labels. **No `.github/` directory: zero workflows, no issue templates, no PR template. `main` is not protected.** |
| GitHub CLI | `gh` **not installed** at investigation time (installed via Homebrew during Phase 0; authentication is a one-time interactive user action — see §6). Git pushes use the `osxkeychain` credential helper; the orchestrator never reads that credential. |
| Claude Code CLI | Not on `PATH`; the native binary ships with the VS Code extension: `~/.vscode/extensions/anthropic.claude-code-2.1.274-darwin-arm64/resources/native-binary/claude` (v2.1.274). Auth: `claude.ai` OAuth, Pro subscription (`claude auth status`). |
| Test commands | Backend FAST tier: `cd backend && .venv/bin/pytest` → **1380 passed, 477 skipped (TEST_MODE-gated), 9 xfailed in ~9 min** single-process while two other regression sweeps were pinning cores (see §3). `pytest-xdist` is in the dev group. Frontend: `npm run lint` (oxlint), `npm run build` (`tsc -b && vite build`), `npm test` (vitest, 12 test files), `npm run test:e2e` (Playwright). |
| Regression harnesses | (a) `backend/tests/regression_corpus/` — the frozen, committed **432-context corpus** (`corpus.json`, 404 planned / 28 refused), gated by `TEST_MODE=REGRESSION`; asserts outcome + refusal code per context. (b) `backend/spikes/failure_log_sweep/snapshot.py --save/--compare` — the cross-commit **primary-signature gate** (LOST/GAINED/byte-identical primaries/refusal-code table) but it reads the gitignored production log `app/data/failures.json`, so it cannot run in CI as-is. (c) `ab.py`, `outline_ab.py`, `envelope.py` (~8.5 min), `quality_metrics.py` — mechanism-level sweeps. |
| Knowledge workflow | Wiki-first + RAG-hybrid (`docs/wiki/`, `backend/app/knowledge/`), `python -m app.knowledge.cli index --changed` is single-writer-locked and concurrency-safe. Indexer globs are `docs/**/*.md` + `specs/*/{spec,plan,research}.md` relative to the repo root, so a `.worktrees/` directory inside the repo is never indexed. |
| Branch / worktree conventions | Feature branches `NNN-slug` (`006-engine-chosen-outline`, `017-multi-level-phase1`), integration branches `integration/*`, knowledge branches `knowledge/*`. Worktrees as sibling directories `../sddproject-NNN` plus many scratchpad worktrees from concurrent agent sessions (13 at inspection time). Project rule (memory + PROJECT_STATE): **never mutate git in the main checkout** — the user runs git in the IDE on it concurrently. |
| Native subagents | This session has the `Agent` tool (subagent types `claude`, `general-purpose`, `Explore`, `Plan`). Those exist only *inside* an LLM session; a standalone scheduler process cannot use them. `claude --bg` background sessions exist but are TUI-oriented (`claude agents` needs a TTY). |

## 2. Claude Code headless capabilities actually verified

Read from `claude --help` of the real binary (no invented flags) and exercised with one Sonnet call:

```
claude -p "<prompt>" --model sonnet --output-format json --tools "" \
  --no-session-persistence --permission-prompts none \
  --json-schema '{"type":"object","properties":{"status":{"type":"string"},"message":{"type":"string"}},"required":["status","message"]}'
```

Returned a single JSON document with `type=result`, `subtype=success`, `is_error=false`,
`num_turns`, `duration_ms`, `total_cost_usd`, `session_id`, `permission_denials=[]`,
`structured_output={"status":"ok","message":"ready"}`, `modelUsage` (sonnet-5 + haiku-4.5 helper).
Wall time ~6 s.

Flags the adapter relies on (all present in 2.1.274): `-p/--print`, `--model`, `--output-format
json`, `--json-schema`, `--allowedTools`, `--disallowedTools`, `--tools`, `--permission-mode
{acceptEdits,plan,…}`, `--permission-prompts none` (anything that would prompt is denied — no
hangs), `--add-dir`, `--append-system-prompt`, `--settings <file-or-json>`, `--session-id`,
`--resume`, `--restricted` (removes Bash/code-running tools — used for the read-only reviewer),
`--name`, `--no-session-persistence`. There is **no `--max-turns`** in this version; run bounds
are enforced by the orchestrator (wall-clock timeout + process kill).

## 3. Machine

Apple M1 Pro, **10 cores (8 performance + 2 efficiency)**, **32 GiB RAM**, 225 GiB free disk,
macOS 25.2. At inspection: load average ≈ 5.0 with **two `snapshot.py` regression sweeps from other
Claude sessions each at 99 % CPU**, Chrome + VS Code resident. This is the normal condition of this
machine — several agent sessions share it — which is exactly why agent slots and heavy-test slots
must be separate pools and why the resource manager must look at real CPU/memory before spawning.

Normal project test cost (single process): FAST tier ≈ 9 min (contended) — one full core; the
432-context corpus sweep ≈ 10–20 min single-threaded (pure CPU, embarrassingly parallel per
context); `envelope.py` ≈ 8.5 min.

## 4. Spawning mechanism decision

**Chosen: `claude -p` headless subprocesses driven by a Python orchestrator, behind an
`AgentRunner` adapter.** Reasons:

1. The spec requires a real scheduler *process* that polls GitHub; native in-session subagents
   (`Agent` tool / Agent Teams) cannot be driven from outside an LLM session, so they cannot be the
   worker mechanism of a standalone orchestrator. They remain available to the Opus Team Lead
   interactively (on-demand domain leads inside the lead's own session).
2. `-p` gives a deterministic contract: exit code, one JSON result, `structured_output` validated
   against a schema, `session_id` for resumable repair attempts, `permission_denials` for audit.
3. `--permission-prompts none` + explicit `--allowedTools`/`--disallowedTools` give a least-privilege,
   non-interactive tool boundary (no `git push`, no `gh`, no `git checkout/reset`, no web access
   for workers; no Bash at all for reviewers).
4. Auth reuses the user's existing `claude.ai` login (keychain) — no API key is ever written to
   disk, config, or logs by this system.

The adapter interface (`agent_runner.AgentRunner`) is the only thing coupled to the CLI; a
`FakeAgentRunner` implements the same interface for unit tests and dry-run, and a future
`--bg`/SDK/Agent-Teams runner can be added without touching the scheduler.

## 5. Key design consequences for this repository

- **Worktree root**: `.worktrees/<issue>-<slug>` inside the repo (gitignored). Safe for the knowledge
  indexer (globs are `docs/**`), outside `backend/tests` collection, and never touches the main
  checkout's HEAD/index (only `git worktree add/remove`, `git branch`, `git fetch` are used).
- **Regression in CI**: a corpus-backed signature harness is needed (`snapshot.py` depends on the
  gitignored `failures.json`). `backend/spikes/failure_log_sweep/corpus_snapshot.py` reuses
  `project_from_context`/`signature`/`generate_demo_design` over `tests/regression_corpus/corpus.json`
  (the same 432 contexts) with a worker pool, and `--compare` emits the machine-readable report the
  regression budget is evaluated against. This is a spike-directory addition, not a product change.
- **Gate 5 (independent AI review) runs locally**, launched by the orchestrator only after the
  deterministic GitHub checks are green: the Anthropic credential is the user's local OAuth login,
  and no API key exists to put into GitHub Actions secrets. The verdict is posted to the PR as a
  review comment and persisted in the state store.
- **GitHub auth for automation**: `gh` must be authenticated once by the user (`gh auth login`,
  browser flow). The orchestrator refuses to leave dry-run unless `gh auth status` succeeds. Reading
  the git keychain credential programmatically was deliberately not done.
- **Two workers + one reviewer + one heavy job** is the V1 ceiling, given the machine is shared with
  interactive sessions.

## 6. Blockers that require the product owner

1. `gh auth login` — one-time interactive authentication (cannot and should not be automated).
2. Whether `main` may be protected with required status checks now (open PR #3 and the user's own
   direct pushes to `main` would then need PRs). Recommended: protect `main` with the agent checks
   *required only for `agent/**` PRs* is not expressible in GitHub; so the recommendation is to
   enable protection with required checks + "include administrators = false" so the owner keeps an
   escape hatch while agents cannot bypass it.

## 7. Implementation plan (phases, each a reviewable commit on `infra/agent-team`)

| Phase | Deliverable | Verification |
|---|---|---|
| A | `.agent/config.yaml`, `.github/ISSUE_TEMPLATE/agent-task.yml`, `PULL_REQUEST_TEMPLATE.md`, label catalogue, `issue_contract.py` (parser + validation + verification manifest), `config.py`, `agentctl labels` bootstrap | unit tests: parsing, invalid rejection, manifest |
| B | `state_store.py` (SQLite, WAL), `state_machine.py`, `locks.py`, `resource_manager.py`, `scheduler.py` | tests: transitions, double-claim, resource exhaustion, dependency blocking, lock conflict, stale lock recovery |
| C | `worktree_manager.py`, `agent_runner.py` (`ClaudeCliRunner` + `FakeAgentRunner`), prompts, structured output schemas | tests with real temp git repos + fake runner |
| D | `.github/workflows/agent-contract.yml`, `agent-ci.yml`, `agent-regression.yml`; `ci/contract_check.py`, `ci/verify.py`, `corpus_snapshot.py`, `regression_budget.py` | unit tests for classifier/budget; workflow lint |
| E | `github_client.py` (gh-backed + fake), `failure_classifier.py`, repair loop, `merge_policy.py`, reviewer step | tests: retry limit, classification, merge policy |
| F | `reconciliation.py`, heartbeat/stale detection, orchestrator singleton lock, `audit.py`, `status` | tests: restart/reconcile |
| G | `orchestrator.py` end-to-end in `--dry-run` against real GitHub (read-only) | dry-run transcript |
| H | pilot: one docs-only Issue through the full lifecycle | Issue closed, audit record |
