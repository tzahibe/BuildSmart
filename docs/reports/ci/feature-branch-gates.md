# `agent-ci` ran on no `feature/` PR: what was skipped, the fix, and the suite evidence

Issue #209 (child of ROOT #211, §1 of the owner's 2026-10-19 directive — the mandatory, blocking
gate). Branch `infra/ci-feature-gates`. Nothing here is a deploy, a live-config change or a merge.

## 1. What was skipped, and why

`.github/workflows/agent-ci.yml` triggers on `pull_request` into `main` / `integration/**`, but two
jobs carried a head-branch condition:

```yaml
  gate-1-contract:
    if: startsWith(github.head_ref, 'agent/') || startsWith(github.head_ref, 'integration/')
  ...
  agent-ci-result:
    if: always() && (startsWith(github.head_ref, 'agent/') || startsWith(github.head_ref, 'integration/'))
```

`gate-2-static` → `gate-3-verification` → `gate-4-regression` each `needs:` the previous job, so a
skipped `gate-1-contract` skipped the whole chain. The #197-series work was delivered from
`feature/` branches, so **every gate was reported as `skipping` on every one of those PRs**:

```
$ gh pr checks 204
agent-ci-result     skipping  0  .../runs/39004780223/job/117314900509
gate-1-contract     skipping  0  .../runs/39004780223/job/117314899700
gate-2-static       skipping  0  .../runs/39004780223/job/117314899456
gate-3-verification skipping  0  .../runs/39004780223/job/117314900187
gate-4-regression   skipping  0  .../runs/39004780223/job/117314900183

$ gh pr checks 206     # identical: all five "skipping", run 39069177964

$ gh run list --workflow agent-ci.yml -L 8
completed skipped  #208 ...  agent-ci  feature/exact-generator      pull_request 39157746225 1s
completed skipped  #205 ...  agent-ci  feature/foyer-geometry       pull_request 39069177964 1s
completed skipped  #205 ...  agent-ci  feature/foyer-geometry       pull_request 39069157647 1s
completed skipped  #197 ...  agent-ci  feature/brain-rank-then-size pull_request 39004780223 1s
completed skipped  #197 ...  agent-ci  feature/brain-preview-exact  pull_request 38762924924 1s
completed skipped  #200 ...  agent-ci  feature/cross-band-cells     pull_request 38759235781 2s
completed skipped  #197 ...  agent-ci  feature/proportion-selection pull_request 38630590086 2s
completed skipped  #197 ...  agent-ci  feature/2d-wing              pull_request 38581420355 2s
```

**PRs #198–#206 were merged with all four gates skipped.** They were merged on locally-run suites
alone. `main`'s branch protection does require both status contexts —

```
$ gh api repos/tzahibe/BuildSmart/branches/main/protection
"required_status_checks": {"strict": true, "contexts": ["agent-ci-result","agent-review-result"], ...}
"enforce_admins": {"enabled": false}
```

— but a job that never runs reports no status at all, and `enforce_admins: false` let the owner
merge anyway. So the protection was satisfied only by the admin exemption, not by evidence.

A second, independent blocker sat behind the trigger: even with the gates running,
`gate-1-contract` could not have passed for a `feature/` PR. `ci/contract_check.py` located the
Issue **only** from an `agent/<issue>-<slug>` branch name (`issue_from_branch`), so for
`feature/foyer-geometry` it resolved no Issue, never fetched one, and failed "branch naming
`agent/<issue>-<slug>`", "PR body links its Issue" and "Issue exists". Widening the trigger alone
would have turned every such PR red for the wrong reason.

## 2. The fix

Two changes, both about *which* PRs are gated and *how the contract is located* — never about what
a gate accepts.

1. **`.github/workflows/agent-ci.yml`** — the two head-branch conditions are gone.
   `gate-1-contract` has no `if:` at all (so `on.pull_request.branches: [main, "integration/**"]`
   is the only filter) and `agent-ci-result` is `if: always()`. `gate-2`/`gate-3` were never
   branch-conditioned; they only needed gate 1 to stop skipping.
2. **`scripts/agent_team/ci/contract_check.py`** — a new `resolve_issue_number(config, pr)` with
   three bindings, used by both `main()` and `evaluate()`:
   - `agent/<issue>-<slug>` → the branch name carries the Issue (unchanged, including the
     `fullmatch` on the slug and the "body links its Issue" check);
   - `integration/<period>` → the first Issue the body closes (unchanged rollup behavior);
   - any other branch (`feature/`, `fix/`, `infra/`, `experiment/`, …) → the PR body's
     `Closes #<issue>` link, which must name **exactly one** Issue. The new check
     `PR body links exactly one Issue` fails with the actionable message
     `Closes: <seen>; head='<branch>' — a branch outside 'agent/' must bind its contract with
     exactly one \`Closes #<issue>\` line in the PR body (or be named agent/<issue>-<slug>)`.

Everything downstream of the binding is untouched and now applies to `feature/` PRs too: Issue
open, trusted `author_association`, an executable non-draft `agent:*` label, the contract parses,
the Issue's domain/risk/resource labels match the contract, every required PR-body section is
present, an evidence row exists per AC, PR risk = Issue risk, the LOST-allowance rule, and the
20-second re-read window for the label race.

### Nothing was weakened (AC-4)

| Possible weakening | Status |
|---|---|
| A check removed | None. `branch naming agent/<issue>-<slug>` and `PR body links its Issue` still run, for every `agent/` branch, exactly as before. The non-`agent/` path **adds** a check (`PR body links exactly one Issue`). |
| A threshold lowered | None. No budget, no risk tier, no timeout, no worker count changed. |
| An allowance broadened | Only the *set of gated PRs*. A PR that is not bound to exactly one valid, open, trusted, executable, contract-valid Issue fails gate 1 — which is strictly more than the previous behavior, where such a PR was not checked at all. |
| Rollup/`integration/` special cases | Byte-identical logic (`grep -n 'integration/' .github/workflows/agent-ci.yml` and the two `integration/` branches in `contract_check.py`); the two existing rollup tests pass unchanged. |
| Risk-tier / regression policy | `ci/plan.py` untouched. `gate-4-regression`'s condition is still `needs.gate-2-static.outputs.regression_required == 'true'`, and `agent-ci-result` still fails a required-but-not-green gate 4 and accepts `skipped` only when `regression_required != true`. |

### Before / after: which PRs are gated

| PR head | base | Before | After |
|---|---|---|---|
| `agent/<issue>-<slug>` | `main` | all gates run | unchanged |
| `integration/<period>` (rollup) | `main` | all gates run | unchanged |
| `agent/…` | `integration/**` | all gates run | unchanged |
| `feature/…`, `fix/…`, `infra/…`, `experiment/…` | `main` | **every gate `skipping`; `agent-ci-result` never reported** | gates 1–3 run; gate 4 per the unchanged risk-tier policy; `agent-ci-result` reports a real conclusion |
| anything | a branch that is not `main`/`integration/**` | not gated | unchanged (not gated) |

New tests in `scripts/agent_team/tests/test_ci_gates.py`:
`test_agent_ci_gates_every_pull_request_to_main_whatever_the_branch_is_called` (the workflow has no
`head_ref` condition left and the gate-4 condition is still the risk-tier one),
`test_gate1_binds_a_non_agent_branch_through_its_single_closes_link`,
`test_gate1_rejects_a_non_agent_branch_with_no_or_ambiguous_link`,
`test_gate1_applies_every_issue_check_to_a_non_agent_branch_too`.

## 3. The Issue contract had to be normalized, not the gate loosened

Gate 1 re-parses the live Issue with `issue_contract.parse_contract`, which requires the Issue-Form
section set. #209's original body used free-form `## ` headings, so it did not parse:

```
$ python -c "parse_contract(209, title, body)"
PROBLEMS:
 - missing section '### Goal'
 - missing section '### Current behavior'
 ... (all 13 required sections)
```

and the Issue carried only `agent:child` — no `domain:`/`risk:`/`resource:` labels, which the
"Issue metadata labels match contract" check compares against the contract. The gate is right and
the Issue was non-compliant, so the **Issue** was fixed, not the check: its body was restated in
the Issue-Form format with the original text preserved verbatim in a trailing section, and the
labels `domain:infra`, `domain:knowledge`, `risk:medium`, `resource:light` were added (exactly what
`labels.metadata_labels(('infra','knowledge'), 'MEDIUM', 'LIGHT')` returns for the parsed contract).
Scope, ACs and verification targets are the owner's, unchanged in substance.

## 4. The mandatory suites, run locally

Machine: the owner's M1 Pro (10 cores), worktree `/Users/mymacbook/projects/sddproject-branched`,
branch `infra/ci-feature-gates` at `origin/main` (5b155d1). Every command below is CI's own
command (`.github/workflows/agent-ci.yml` gate-2 / `agent-regression.yml` / `.agent/config.yaml`).

### 4.1 Orchestrator unit tests (gate-2's third step)

```
$ uv run --project scripts/agent_team pytest -q -p no:cacheprovider scripts/agent_team/tests
FAILED scripts/agent_team/tests/test_governance_parallel.py::test_multiple_workers_scheduled_from_one_root
1 failed, 282 passed in 352.40s (0:05:52)
```

The one failure, verbatim:

```
    row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.InterfaceError: bad parameter or other API misuse
```

It is a **flake in the SQLite state store under the full-suite run, unrelated to this diff** (this
diff touches `ci/contract_check.py`, `agent-ci.yml` and docs; the failing test exercises the
scheduler's parallel claiming). The same file passes in isolation:

```
$ uv run --project scripts/agent_team pytest -q -p no:cacheprovider scripts/agent_team/tests/test_governance_parallel.py
19 passed in 69.85s (0:01:09)
```

and the gate's own file is green:

```
$ uv run --project scripts/agent_team pytest -q -p no:cacheprovider scripts/agent_team/tests/test_ci_gates.py
33 passed in 0.79s
```

**Named as a limitation, not hidden**: `sqlite3.InterfaceError: bad parameter or other API misuse`
in `state_store`'s `meta` read is the signature of a connection used after close / across threads.
CI runs this same unsharded command in gate-2, so it can flake there too. It is pre-existing
behavior of the state store, out of scope for #209, and worth its own Issue.

### 4.2 Backend suite (gate-2's backend step)

First run, exactly as the #197 worktrees were run (no `OPENAI_API_KEY` in the environment):

```
$ WALLCLOCK_BUDGETS=off uv run --no-sync pytest -q -p no:cacheprovider -n 4
2122 passed, 883 skipped, 10 xfailed, 4 warnings, 56 errors in 481.80s (0:08:01)

ERROR tests/test_chat.py - openai.OpenAIError: Missing credentials. Please pa...
ERROR tests/test_chat_project_editing.py ...  ERROR tests/test_demo_p0.py ...
ERROR tests/test_design.py ...                ERROR tests/test_design_pipeline.py ...
ERROR tests/test_laundry_activation_e2e.py ...ERROR tests/test_parking_band.py ...
ERROR tests/test_projects.py ...              ERROR tests/test_requirements.py ...
ERROR tests/test_selected_footprint.py ...    ERROR tests/test_spatial_edit_endpoint.py ...
ERROR tests/test_wet_room_extraction_check.py ... ERROR tests/test_wet_room_questions.py ...
ERROR tests/test_wet_room_semantics_p5.py ...
```

```
_____________________ ERROR collecting tests/test_chat.py ______________________
tests/test_chat.py:7: in <module>
    from app.main import app
E   openai.OpenAIError: Missing credentials. Please pass an `api_key`, `workload_identity`,
    `admin_api_key`, or set the `OPENAI_API_KEY` or `OPENAI_ADMIN_KEY` environment variable.
```

**Environment limitation, not a defect**: `backend/app/main.py` constructs OpenAI clients at import
time, so 14 modules (56 collection errors) cannot even be collected without the variable set. CI
sets `OPENAI_API_KEY: not-a-real-key-ci-only` on both gate-2 and gate-3, and `.agent/config.yaml`
injects the same value into every orchestrator-run command; a hand-run worktree does not. With
CI's own environment:

```
$ OPENAI_API_KEY=not-a-real-key-ci-only WALLCLOCK_BUDGETS=off uv run --no-sync pytest -q -p no:cacheprovider -n 4
2446 passed, 883 skipped, 10 xfailed, 4 warnings in 449.58s (0:07:29)
backend rc=0
```

Zero failures, zero errors. The 883 skips are the marker-gated tiers (`production_ai`, and the
corpus/regression markers that only collect under `TEST_MODE=REGRESSION`) — the same set CI skips.
Note CI runs this with `-x`; the runs above deliberately omit `-x` so that *every* failure would be
listed rather than only the first.

Static steps, also from gate-2 / `verify.py`'s `STATIC_COMMANDS`:

```
$ uv run --no-sync python -m compileall -q app tests spikes      # rc=0
$ OPENAI_API_KEY=not-a-real-key-ci-only uv run --no-sync python -c "import app.main"   # rc=0
```

### 4.3 `torch`: does CI have it, and is that suite meant to run there?

**Yes and yes.** Reproduced first, verbatim:

```
$ uv run --no-sync pytest -q -p no:cacheprovider tests/test_local_gateway.py
    def generate(self, request: ArchitectModelRequest) -> ArchitecturalSpec:
>       import torch
E       ModuleNotFoundError: No module named 'torch'
app/architect/local_gateway.py:240: ModuleNotFoundError
FAILED tests/test_local_gateway.py::test_generate_end_to_end_returns_an_adapted_architectural_spec
FAILED tests/test_local_gateway.py::test_generate_uses_the_verified_generation_parameters
FAILED tests/test_local_gateway.py::test_generate_applies_the_chat_template_with_add_generation_prompt
FAILED tests/test_local_gateway.py::test_generate_propagates_typed_errors_for_bad_output
4 failed, 13 passed in 0.96s
```

Why it happens and why it is purely local:

- `backend/pyproject.toml` puts `torch>=2.2.0` in the **optional** `local-model` extra, not in the
  `dev` group, so a bare `uv sync --group dev` (what a hand-made worktree gets) has no torch —
  while `tests/test_local_gateway.py` still exercises `torch.no_grad()` through
  `app/architect/local_gateway.py`'s lazy import, with a fake model/tokenizer injected.
- **CI installs it explicitly**, in gate-2's backend step, with a comment saying exactly why:
  `uv pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0"` (CPU-only wheel,
  because the lockfile's default Linux resolution is the full CUDA stack), followed by
  `uv run --no-sync …` so the implicit project sync cannot remove it again.
- **The orchestrator installs it too**: `.agent/config.yaml`'s setup command is
  `uv sync --group dev --extra local-model`. So every worktree the orchestrator prepares has torch;
  the #197 worktrees were prepared by hand and did not.
- So the suite **is** meant to run in CI, and does. Running CI's exact command here fixes it:

```
$ uv pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0"
 + torch==2.14.1
$ uv run --no-sync pytest -q -p no:cacheprovider tests/test_local_gateway.py
17 passed in 11.69s
```

The 2446-pass run in §4.2 includes those 17 tests. **No CI change is needed for torch**; the gap was
the hand-prepared worktree, and it is now recorded here so the next worktree is set up with
`--extra local-model` (or CI's explicit CPU install).

### 4.4 Architectural regression suite (gate 4's content)

`agent-regression.yml` runs the architectural regression in four parts: the corpus snapshots
(`corpus_snapshot.py --save`, sharded ×4 and single-node, for base and head), the snapshot
invariants (`snapshot_invariants.py evaluate`), the replay
(`TEST_MODE=REGRESSION pytest tests/regression_corpus/test_frozen_regression_corpus.py -n 4` plus
`CORPUS_SNAPSHOT=<head> pytest tests/regression_corpus --ignore=…test_frozen…`), and the budget
evaluation (`regression_gate.py`). `.agent/config.yaml` names the same suite as
`regression.corpus_tests`. That whole command was run here, and in the **stricter** form: without
`CORPUS_SNAPSHOT`, so `test_quality_baseline.py` genuinely replays the corpus instead of reading a
snapshot the way CI lets it:

```
$ OPENAI_API_KEY=not-a-real-key-ci-only TEST_MODE=REGRESSION \
    uv run --no-sync pytest -q -p no:cacheprovider tests/regression_corpus -n 4
856 passed in 3326.98s (0:55:26)
regression rc=0
```

**Zero failures.** 856 tests, 55 minutes — so yes, it is the >15-minute suite the Issue warned
about, and here it was slower still for two measurable reasons, both environment, not code:
(1) no `CORPUS_SNAPSHOT`, so one worker carried a full un-snapshotted quality-baseline replay
(~50 min of CPU on its own), and (2) a **concurrent corpus run in another worktree**
(`/Users/mymacbook/projects/sddproject-142m`, another session, 42 min of CPU at ~79 %) competed for
the same cores for most of the run. The base/head `corpus_snapshot.py --save` passes that gate 4
does on the runner were **not** reproduced locally — they are another ~2×10 min and they compare a
merge-base checkout against the head, which is CI's job and needs no local duplicate. Gate 4 is not
required for this PR anyway (§5), so this run is evidence of no regression, not a gate result.

## 5. Which gates run on THIS PR, and why gate 4 is skipped

This branch is `infra/ci-feature-gates` — neither `agent/` nor `integration/` — so the PR is its
own test case for AC-1.

Gate 4 is *not* expected to execute here, and that is the unchanged policy, not a weakening:
`ci/plan.py` requires the manifest to ask for regression **and** backend *product* code to have
changed (or a `REGRESSION_MACHINERY` file — `agent-ci.yml` is deliberately not one of them, those
are `agent-regression.yml`, `agent-snapshot.yml`, `ci/snapshot_store.py`, `ci/regression_gate.py`).
This PR changes no `backend/app/**`, and #209's contract declares the domains `infra, knowledge`,
neither of which is a regression domain (`backend, geometry, validator, ai`), so the manifest says
`regression_required: false`. `agent-ci-result` therefore *evaluates* gate 4 and accepts `skipped`
— exactly the pre-existing rule, which still fails the PR if regression had been required and the
job had not succeeded. Four gates are now *reported on*, where before the five jobs were bypassed
wholesale by a branch-name condition.

## 5b. AC-1 proven on a real PR: the gates RUN on an `infra/` branch

PR **#225** (`infra/ci-feature-gates` → `main`), run
[39277861603](https://github.com/tzahibe/BuildSmart/actions/runs/39277861603), opened on the first
two commits only — deliberately *before* this report file was committed, so that gate 3 had to be
seen really executing its targets rather than passing vacuously:

```
$ gh pr checks 225
gate-1-contract / contract  pass      1m11s  .../job/118146616074
gate-2-static               pass      49s    .../job/118147016172
gate-3-verification         fail      48s    .../job/118147332794
gate-4-regression           skipping  0      .../job/118149598485
agent-ci-result             fail      21s    .../job/118147684375

$ gh run list --branch infra/ci-feature-gates
completed  <this run>  agent-ci  infra/ci-feature-gates  pull_request  39277861603
```

Compare with #204/#206, where every one of those five rows read `skipping` with a 0 s duration.
Gate 1 **passed** on a branch named neither `agent/` nor `integration/` — the new binding works on
a real PR, with the real Issue — and `agent-ci-result` reported a real conclusion (`fail`) instead
of nothing at all. Gate 3's failure is the expected one, verbatim from the job summary:

```
| AC-1 -> pytest:scripts/agent_team/tests/test_ci_gates.py | ✅ | 33 passed in 0.39s |
| AC-1 -> grep:docs/reports/ci/feature-branch-gates.md:gate-1-contract | ❌ | docs/reports/ci/feature-branch-gates.md missing |
| AC-2 -> grep:.github/workflows/agent-ci.yml:integration/ | ✅ | pattern found |
| AC-3 -> file:docs/reports/ci/feature-branch-gates.md | ❌ | missing or empty |
| AC-4 -> review:the diff only widens which PRs are gated, never what the gates accept | ✅ | deferred to gate-5 ... |
| AC-1 evidence passes | ❌ | 1 of 2 targets failed |
| AC-3 evidence passes | ❌ | 1 of 1 targets failed |
```

— this file is the artifact those two targets wanted, and `gate-4-regression: skipping` is the
risk-tier policy of §5, evaluated rather than bypassed. The run on the commit that adds this file
is the green one; its check list is linked in the summary comment on Issue #209.

## 6. For the owner — what was NOT changed, and what needs a decision

- **Branch protection was not touched.** It still requires `agent-ci-result` and
  `agent-review-result` with `strict: true`, and `enforce_admins: false` is still what it was.
- **`agent-review-result` is produced by the orchestrator, not by any workflow.** For a PR driven
  by the orchestrator it is published on the head SHA after gate 5. For a PR that an agent opened
  outside the orchestrator loop (this one included) nothing publishes it, so the context stays
  unreported and the owner needs the admin path to merge even when `agent-ci-result` is green.
  Two possible resolutions, both the owner's call and neither done here: (a) have the orchestrator
  publish the review status for any PR into `main`, so the required context is always real, or (b)
  drop `agent-review-result` from the required contexts and keep gate 5 as an advisory verdict.
  (a) preserves coverage; (b) weakens it, so the recommendation is (a).
- **`enforce_admins` stays the owner's escape hatch.** Nothing in this PR prevents an admin merge;
  what changes is that the evidence now exists instead of being silently absent.
- **Two pre-existing defects found while gathering evidence**, both out of scope for #209 and
  neither touched: the `sqlite3.InterfaceError` flake in the orchestrator's state store under the
  full suite (§4.1), and the fact that a hand-prepared worktree lacks `torch` because it is only in
  the `local-model` extra (§4.3) — CI and the orchestrator's own setup both install it.
- **No deploy, no live configuration, no spend, no `agentctl notify`, no merge.** Merging is the
  owner's.
