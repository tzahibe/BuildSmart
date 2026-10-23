# #252 — the independent-review status reports for any pull request into `main`

**Issue:** #252 (child of ROOT #211, parent #209) · **PR:** #253 · **Branch:** `infra/review-status-any-pr`
· **Date:** 2026-10-23 · **Verdict: the check is sound and stays required; the recognition in front of it was widened.**

---

## 1. The defect, stated exactly

`agent-review-result` is a required status context on `main` (`config.protection_required_contexts`
= `ci_required_checks` + `review_status_context`) and **nothing but the orchestrator publishes it**.

The check itself was never broken, and nothing was missing from it:

| producer | behavior | where |
|---|---|---|
| `orchestrator._publish_review_status` | writes the context through `github_client.set_commit_status` | `orchestrator.py` |
| the verdict mapping | `success` **only** for an APPROVE whose recorded SHA equals the head, `failure` for `REQUEST_CHANGES`/`BLOCK`, `pending` otherwise | `_reviewer_run`, `_ensure_review_status` |
| after a restart | `_ensure_review_status` re-publishes from the state store, so a lost status is repaired | `_step_ci`, `_step_merged` |

What was too narrow is the **recognition** in front of it. `worktree_manager.issue_from_branch`
returns an Issue number only when the branch starts with `config.branch_prefix` (`agent/`) and
continues `<issue>-`:

```python
def issue_from_branch(config: Config, branch: str) -> int | None:
    if not branch.startswith(config.branch_prefix):
        return None
    m = re.match(r"^(\d+)-", branch[len(config.branch_prefix):])
    return int(m.group(1)) if m else None
```

A pull request raised on a `feature/`, `fix/`, `infra/` or `investigate/` branch could therefore
never be adopted by reconciliation, never received an independent review, and its status stayed
**unreported forever** — not red, not yellow: absent. Branch protection then refused the merge,
and it was **right** to: it was refusing to merge code that had never had the review the check
stands for. At the time of writing, six of the eight open pull requests into `main` are on such
branches (#234, #230, #228, #219, #215, #210).

This is the same defect shape #209 fixed for CI (`docs/reports/ci/feature-branch-gates.md`): the
gate was sound, and the recognition in front of it was too narrow for the way the work is actually
delivered. **#209 widened which pull requests are *tested*; this widens which are *reviewed*.** It
is also the reason the three admin merges of 2026-10-21 (#225, #244, #241) bypassed a **real**
review rather than a broken check — recorded, not left implicit.

---

## 2. What changed

`reconciliation.adopt_open_prs(orch)` runs on every tick (and once, on demand, through
`agentctl adopt-prs [--pr N] [--dry-run]`). It lists the open pull requests into
`config.base_branch`, skips every PR number the state store already knows — native work, or a PR
adopted on an earlier tick, so the pass is idempotent — and hands the rest to `adopt_pr`.

**The binding is the one gate 1 already implements, reused rather than reimplemented:**
`ci.contract_check.resolve_issue_number(config, pr)` — the branch name for `agent/<issue>-<slug>`,
the first `Closes` line for an `integration/<period>` rollup, and otherwise the PR body's **single**
`Closes #<issue>` line. The existing branch-name rule keeps working unchanged and still binds when
it applies (proved by `test_an_agent_branch_pr_opened_outside_the_orchestrator_is_adopted_by_its_branch_name`,
whose body links nothing at all).

`adopt_pr` then applies **exactly the Issue conditions gate 1 applies**, to exactly the Issue the
binding resolved: the Issue exists, is open, has a trusted `author_association`, is not a decomposed
ROOT, is not on `agent:hold`, and its contract validates. It also refuses to race: an Issue an agent
holds (`CLAIMED`/`WORKING`/`FIX_REQUIRED`), or one already delivered by a different PR, is left
alone.

On adoption: the Issue is tracked with its live contract, the PR's own branch is checked out with
`worktrees.ensure_named` (the reviewer must read the **real** diff — a review without it would be a
weaker review), the record moves `QUEUED → CLAIMED → PR_OPEN` (`CLAIMED → PR_OPEN` is the
state machine's documented "reconciled an existing PR" edge), `pending` is published for the head
SHA, and a milestone comment on the Issue states what was adopted and what now gates it. From
`PR_OPEN` onwards the code path is the existing one, untouched: the same deterministic gates, the
same reviewer prompt built from the same live contract, the same criteria, the same status for the
same exact head SHA.

**Never silent.** Every exit that does not adopt publishes `pending` **with its reason** through
`Orchestrator.ensure_pending_review_status`, so a human reading the pull request can tell "not yet
reviewed" from "nothing will ever report". That helper publishes only when the context is absent or
pending for a different reason, and it **refuses to touch a `success` or `failure` already published
for that SHA** — adoption cannot turn a red review green.

**Adoption does not require the owner's `owner:approved` execution label.** Reviewing code already
proposed for `main` is not executing an Issue, and the published status can only be `pending` or
`failure` until a reviewer APPROVEs that exact SHA. `agent:hold` is still honoured, so the owner's
stop still stops it.

**The one difference from native work is stricter, not looser.** `Orchestrator.attempts_remaining`
returns `False` for an adopted PR (the new, additively migrated `issues.adopted_pr` column), and
that is the single choke point every fixer dispatch already goes through — red CI, a merge
conflict, a `REQUEST_CHANGES`/`BLOCK` verdict, a worker failure. So an adopted pull request is
**blocked for a human** instead of a fixer being dispatched onto a branch the orchestrator does not
own and must not push to.

---

## 3. Evidence on a real pull request (AC-7)

PR **#253** (`infra/review-status-any-pr` → `main`), head `93ab9f76b5306df2305e7e72141033872c55fa3c`.
Under the old code this branch name alone guaranteed the required context would never report.

**Before** — the head carried no statuses at all, which is exactly the defect:

```
$ gh api repos/tzahibe/BuildSmart/commits/93ab9f76b530.../status -q '{state:.state,contexts:[.statuses[].context]}'
{"contexts":[],"state":"pending"}
```

**The adoption pass**, dry run first, then for real:

```
$ ./scripts/agentctl adopt-prs --pr 253 --dry-run
PR #253 (infra/review-status-any-pr): would be adopted for #252

$ ./scripts/agentctl adopt-prs --pr 253
INFO agent_team.orchestrator: #252: Adopted PR #253 (`infra/review-status-any-pr`, head `93ab9f76b530`) — a branch this
orchestrator did not create, bound to this contract by the PR body's `Closes #252` line. [...]
PR #253 (infra/review-status-any-pr): adopted for #252 -> PR_OPEN
```

**After** — the required context reports, on the pull request's exact head SHA:

```
$ gh api repos/tzahibe/BuildSmart/commits/93ab9f76b5306df2305e7e72141033872c55fa3c/status \
    -q '.state, (.statuses[] | .context+" "+.state+" "+.description+" "+.target_url)'
pending
agent-review-result pending independent review not yet run (adopted pull request) https://github.com/tzahibe/BuildSmart/pull/253
```

The full status list for that head, as `gh pr checks` prints it:

```
$ gh pr checks 253
agent-ci-result             fail       4s   .../runs/39942106764/job/120375886222
gate-1-contract / contract  fail      13s   .../runs/39942106764/job/120375793540
gate-2-static               skipping   0    .../runs/39942106764/job/120375885925
gate-3-verification         skipping   0    .../runs/39942106764/job/120375886905
gate-4-regression           skipping   0    .../runs/39942106764/job/120375887577
agent-review-result         pending    0    https://github.com/tzahibe/BuildSmart/pull/253   independent review not yet run (adopted pull request)
```

Read that last line against the "before" block: the context branch protection requires now
**reports** on a branch that is neither `agent/` nor `integration/`, where before it reported
nothing at all — and it reports `pending`, which is the honest value, because no review has run for
this SHA yet. The merge stays refused, for the right reason and with the reason visible.

The state store agrees, and records the binding it used:

```
$ ./scripts/agentctl report 252
- State: PR_OPEN
- PR: #253 (https://github.com/tzahibe/BuildSmart/pull/253)
- Branch: infra/review-status-any-pr
- Validated SHA: none
```

`gate-1-contract`'s own failure on that first run is **not** this change: its one red row was
`Issue metadata labels match contract — expected ['domain:knowledge', 'domain:qa', 'resource:light',
'risk:medium'], have []`. Issue #252 was opened without the labels its own contract declares (the
same thing #209 found for itself). The labels were added to match the contract; the gate was not
loosened, and every other row of gate 1 — including `PR body links exactly one Issue | ✅ | Closes:
[252]` — was already green. On the next head gate 1 passed (`pass 10s`).

### The same thing on a second, later head — and the one gate defect found doing it

Pushing the report moved the head to `859320c13727cf6a5ee2d4dd775f0ea2c1c280e9`, which landed with
**no status again**: a record sitting in `CI` published `pending` only at the moment the PR was
opened, and GitHub evaluates the *current* head. Two things were fixed for it, both the Issue's own
shape (a SHA with no status is unreadable — it looks exactly like a check that will never report):
`_step_ci` now ensures `pending` for the head it is validating, and `agentctl adopt-prs --pr N` on
an already-adopted PR makes GitHub agree with the store through the existing restart-repair path
`_ensure_review_status` (which republishes the store's recorded verdict for that exact SHA, and
`pending` when there is none — it can never invent one):

```
$ gh api repos/tzahibe/BuildSmart/commits/859320c13727.../status -q '{state:.state,contexts:[.statuses[].context]}'
{"contexts":[],"state":"pending"}

$ ./scripts/agentctl adopt-prs --pr 253
PR #253: already adopted for #252; agent-review-result=pending on 859320c13727

$ gh api repos/tzahibe/BuildSmart/commits/859320c13727.../status -q '.state, (.statuses[] | .context+" | "+.state+" | "+.description)'
pending
agent-review-result | pending | independent review not yet run

$ gh pr checks 253
agent-ci-result             fail      3s     .../runs/39942879335/job/120378944115
gate-3-verification         fail     12s     .../runs/39942879335/job/120378849581
gate-4-regression           skipping  0      .../runs/39942879335/job/120378946289
gate-1-contract / contract  pass     10s     .../runs/39942879335/job/120378357034
gate-2-static               pass     1m5s    .../runs/39942879335/job/120378428348
agent-review-result         pending   0      https://github.com/tzahibe/BuildSmart/pull/253   independent review not yet run
```

`gate-3-verification`'s failure on that head was a **real gate defect, not a missing artifact**, and
it is instructive for exactly the reason this Issue exists — a check that cannot execute its target
is not evidence of anything:

```
| AC-1 -> pytest:scripts/agent_team/tests | ❌ | no tests ran in 0.00s |
| AC-2 -> file:docs/reports/ci/review-status-for-any-pr.md | ✅ | exists, non-empty |
| AC-6 -> grep:docs/reports/ci/review-status-for-any-pr.md:weakened | ✅ | pattern found |
| AC-7 -> grep:docs/reports/ci/review-status-for-any-pr.md:status | ✅ | pattern found |
```

`ci/verify.py` special-cased `scripts/agent_team/tests/` **with a trailing slash**, so the suite
*directory* — the form every orchestrator Issue's verification plan uses — fell through to the
backend branch and ran `uv run pytest scripts/agent_team/tests` from `backend/`, collected nothing
and failed. The prefix is now `scripts/agent_team`, covering the directory, a file and a nodeid
(`test_run_target_resolves_orchestrator_and_backend_pytest_targets` asserts the exact command for
all three). Gate 2 was already running that suite correctly on this PR (`pass 1m5s`, including the
18 new tests), so this only moves a target from "cannot run" to "runs" — no target was weakened or
removed, and nothing was skipped to make the gate green.

With the target executing, the next run showed the second half of the same lesson. Four of #252's
criteria name that one target, so gate 3 ran the identical 80-second command four times and the
**pre-existing state-store flake** (§5) hit one of the four:

```
| AC-1 -> pytest:scripts/agent_team/tests | ✅ | 301 passed in 77.82s |
| AC-3 -> pytest:scripts/agent_team/tests | ❌ | 1 failed, 300 passed in 95.80s |
| AC-4 -> pytest:scripts/agent_team/tests | ✅ | 301 passed in 64.16s |
| AC-5 -> pytest:scripts/agent_team/tests | ✅ | 301 passed in 61.01s |
```

`evaluate` now executes each distinct `(kind, target)` **once** and applies that one verdict to
every criterion naming it, saying so in the reused rows ("same target as an earlier criterion:
executed once"). A deterministic target cannot disagree with itself, so this is the same evidence —
at a quarter of the wall time and a quarter of the exposure to a flake the suite already carried. A
failing shared target still fails **every** criterion that names it
(`test_gate3_a_repeated_target_that_fails_fails_every_criterion_that_names_it`). Nothing was
bypassed and no red result was ignored: the flake was identified as #209's documented one, and the
gate was made to run its target once rather than four times.

### What is **not** demonstrated live, and is marked unverified rather than implied

- **The `success`/`failure` half of the status on a live pull request.** Reaching it means running
  the reviewer agent, which is a spend this Issue is not authorized for. It is covered by tests
  that drive the real orchestrator code paths over the fakes (§5): an APPROVE publishes `success`
  on the exact head SHA, a `BLOCK` publishes `failure`.
- **GitHub's own refusal of a merge while the status is red.** Testing that live would mean
  attempting a merge, which is out of scope and not authorized. The test asserts it against
  `FakeGitHub.required_contexts_for_merge`, which raises a 405 exactly as GitHub does.
- **The daemon ticking with this code.** The live orchestrator runs from a different worktree under
  launchd and was neither restarted nor reconfigured. The demonstration above is a one-shot
  `agentctl adopt-prs` from this worktree, against real GitHub, using the same
  `reconciliation.adopt_open_prs` the tick calls.
- **A fork pull request** cannot be checked out locally; it reports `pending` with that reason
  rather than being adopted. Not exercised against a real fork.

---

## 4. Nothing about the review was weakened (AC-6)

Stated criterion by criterion, because the whole point of the Issue is that this must not be the
place where the review quietly gets cheaper:

| what | before | after |
|---|---|---|
| reviewer prompt | contract + CI evidence + regression report + worker report + file list + diff + SEMANTIC_REVIEW criteria | **identical** — `_reviewer_run` is untouched |
| APPROVE must name its SHA | `review_verdict = f"{v}@{head}"`, `success` only when `rec.validated_commit == head` | **unchanged** |
| `overfits_one_plan` downgrade | APPROVE → REQUEST_CHANGES | **unchanged** |
| SEMANTIC_REVIEW criteria not MET | APPROVE → REQUEST_CHANGES | **unchanged** |
| deterministic gates before review | `agent-ci-result` green on the head | **unchanged** — an adopted PR goes through `PR_OPEN → CI` like any other |
| a branch-name skip | none | **still none** — no code path reads the branch name to decide *what* the review accepts |
| repair after a red review | fixer dispatched while the budget lasts | **stricter for an adopted PR**: no budget, so it blocks for a human |

The diff widens only **which** pull requests are reviewed. The three producers of a `success`
(`_reviewer_run`, `_ensure_review_status`, and nothing else) were not touched, and the only new
publisher — `ensure_pending_review_status` — can publish `pending` and nothing else, and refuses to
overwrite an existing verdict for the SHA.

---

## 5. Tests

`scripts/agent_team/tests/test_pr_adoption.py`, 17 tests over the lifecycle fakes plus a **real**
second clone that pushes a human-named branch into the temp origin, so the adopted branch is really
checked out and really diffed.

| AC | test |
|---|---|
| AC-1 | `test_feature_branch_pr_is_adopted_reviewed_and_its_exact_head_sha_gets_the_status`, `test_an_agent_branch_pr_opened_outside_the_orchestrator_is_adopted_by_its_branch_name` |
| AC-2 | the same test asserts `status_log[-1] == (head, "agent-review-result", "success")` for the PR's real head SHA, and `head == gh.get_pr(n)["head"]["sha"]` |
| AC-3 | `test_unbound_pr_reports_pending_with_the_reason_and_is_not_adopted`, `test_a_pr_that_cannot_be_adopted_still_reports_pending` (6 parametrised reasons), `test_draft_pr_reports_pending_and_is_not_adopted`, `test_a_new_commit_on_an_adopted_pr_makes_the_status_pending_again` |
| AC-4 | `test_block_verdict_on_an_adopted_pr_publishes_failure_and_the_merge_is_refused` — `failure` published, record `BLOCKED`, **no fixer or worker run**, `GitHubError` raised by the simulated branch protection, and a further adoption pass leaves the `failure` untouched; `test_request_changes_on_an_adopted_pr_stays_failure_after_a_restart` |
| AC-5 | `test_native_work_is_not_adopted_and_runs_exactly_as_before` (native work keeps its repair budget and reaches `READY_FOR_OWNER`), `test_adoption_never_races_an_agent_that_holds_the_issue`, `test_adoption_is_idempotent_and_dry_run_changes_nothing` |
| AC-6 | `test_adopted_pr_review_uses_the_same_contract_criteria_and_the_real_diff` — every AC id of the live contract and the branch's real diff (`+work done by hand`) are in the reviewer's prompt |
| AC-3 (second head) | `test_a_head_that_moves_while_ci_is_red_still_reports_pending` — a commit pushed while the gates are red leaves the new SHA `pending`, not blank, and the record goes `BLOCKED` with no fixer or worker dispatched |
| gate 3 | `test_run_target_resolves_orchestrator_and_backend_pytest_targets` — the suite directory, a file and a nodeid each resolve to the orchestrator's own project from the repository root |

Counts, verbatim:

Run from `scripts/agent_team`:

```
$ uv run --project . python -m pytest tests -q        # first full run, with the new tests
1 failed, 299 passed in 401.31s (0:06:41)

$ uv run --project . python -m pytest tests/test_governance_parallel.py -q
19 passed in 62.64s (0:01:02)

$ uv run --project . python -m pytest tests -q        # final full run
301 passed in 408.92s (0:06:48)

$ uv run --project . python -m pytest tests/test_pr_adoption.py tests/test_hardening.py tests/test_orchestrator_lifecycle.py -q
57 passed in 122.03s (0:02:02)
```

The first run's one failure is
`test_governance_parallel.py::test_dependency_aware_parallelism_follows_the_dag` with
`sqlite3.InterfaceError: bad parameter or other API misuse` raised in `state_store.get_meta` from a
worker thread. That is the **pre-existing** full-suite flake documented in
`docs/reports/ci/feature-branch-gates.md` §4.1 ("the signature of a connection used after close /
across threads… pre-existing behavior of the state store, out of scope for #209, and worth its own
Issue"); the file passes 19/19 alone, the second full run of the same code passes 301/301, and this
diff adds no cross-thread store access — `attempts_remaining` reads a field of the record it is
already given. It was not chased.

---

## 6. Limitations and consequences

- **Out of scope and untouched**: branch protection itself, the required-contexts list, and the
  content of any pull request under review. Nothing was merged, deployed, restarted, or paid for.
- Adopting the six pull requests already open on human-named branches will, once this lands, give
  each of them a real independent review. Several of them will go red. **That is the feature**: the
  check will be reporting the truth instead of nothing.
- `close_completed_roots` counts `kind == "child"` records, so an adopted child does not hold its
  ROOT open. Noted, not changed.
- An adopted PR with no CI run at all ends `BLOCKED` after `ci_wait_seconds` with the status still
  `pending`, which is honest but means a human must act. There is no automatic repair, by design.
