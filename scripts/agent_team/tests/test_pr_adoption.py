"""#252 — the independent-review status reports for ANY pull request into main.

The check (`agent-review-result`) was never broken: `worktree_manager.issue_from_branch` only ever
recognised the orchestrator's own `agent/<issue>-<slug>` branches, so a pull request raised on a
`feature/` branch was never adopted, never independently reviewed, and its status never reported at
all — and branch protection then refused the merge, correctly. These tests cover the widened
recognition and, just as importantly, that the review itself is not widened with it.

Same fakes as the lifecycle tests, plus a real second clone that pushes a human-named branch into
the temp origin, so the adopted branch is really checked out and really diffed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_team import state_machine as sm
from agent_team.agent_runner import FakeAgentRunner
from agent_team.github_client import GitHubError
from agent_team.issue_contract import render_body
from agent_team.labels import metadata_labels
from agent_team.reconciliation import adopt_open_prs, adopt_pr
from agent_team.tests.helpers import make_contract, track
from agent_team.tests.test_orchestrator_lifecycle import (  # noqa: F401
    APPROVE, _add_issue, _git, _green, _orch, _owner_merge, _red, _tick, _worker_that_commits, env)

REVIEW_CTX = "agent-review-result"


def _status(gh, sha: str) -> str | None:
    return gh.statuses.get(sha, {}).get(REVIEW_CTX, {}).get("state")


def _description(gh, sha: str) -> str:
    return gh.statuses.get(sha, {}).get(REVIEW_CTX, {}).get("description") or ""


def _issue(gh, number: int, *, approved: bool = False, **kw):
    """An Issue with a valid contract. `approved=False` on purpose: a review is not an execution,
    so the absence of the owner's execution label must not stop the check from reporting."""
    c = make_contract(number, title=f"[agent] Task {number}", **kw)
    labels = ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)] + (["owner:approved"] if approved else [])
    gh.add_issue(number, c.title, render_body(c), labels)
    return c


def _human_pr(config, gh, origin, issue_no: int | None, *, branch: str = "feature/human-work",
              body: str | None = None, file: str = "human.txt", draft: bool = False) -> dict:
    """A real branch pushed by someone else, and a pull request into main for it."""
    tmp = Path(origin).parent
    clone = tmp / f"human-{branch.replace('/', '-')}"
    if not clone.exists():
        _git(["clone", "-q", str(origin), str(clone)], tmp)
        _git(["config", "user.email", "human@example.com"], clone)
        _git(["config", "user.name", "a human"], clone)
        _git(["checkout", "-q", "-b", branch], clone)
    (clone / file).write_text("work done by hand\n")
    _git(["add", "-A"], clone)
    _git(["commit", "-q", "-m", f"feat: {file}"], clone)
    _git(["push", "-q", "-u", "origin", branch], clone)
    if body is None:
        body = f"## Issue\n\nCloses #{issue_no}\n\n## What changed\n\nA file.\n"
    pr = gh.create_pr(head=branch, base=config.base_branch, title=f"human work for #{issue_no}", body=body, draft=draft)
    return gh.get_pr(pr["number"])


def _push_more(origin, branch: str, file: str = "more.txt"):
    clone = Path(origin).parent / f"human-{branch.replace('/', '-')}"
    (clone / file).write_text("more\n")
    _git(["add", "-A"], clone)
    _git(["commit", "-q", "-m", f"feat: {file}"], clone)
    _git(["push", "-q", "origin", branch], clone)


# ---------------------------------------------------------------------------------------------
# AC-1 / AC-2: adopted, reviewed, and the status published for the exact head SHA
# ---------------------------------------------------------------------------------------------

def test_feature_branch_pr_is_adopted_reviewed_and_its_exact_head_sha_gets_the_status(env):
    config, gh, clock, origin = env
    _issue(gh, 7, risk="LOW")
    pr = _human_pr(config, gh, origin, 7)
    head = pr["head"]["sha"]
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"reviewer": APPROVE}))

    rep = _tick(orch)                     # reconciliation adopts it, then the same tick advances it
    assert any("adopted for #7" in a for a in rep.reconciled), rep.reconciled
    assert rep.advanced[7] == "PR_OPEN -> CI"
    rec = orch.store.get(7)
    assert (rec.state, rec.pr_number, rec.adopted_pr, rec.branch) == (sm.CI, pr["number"], pr["number"], "feature/human-work")
    assert Path(rec.worktree).is_dir()                      # a real checkout: the reviewer sees the real diff
    assert _status(gh, head) == "pending"                   # AC-3: it reports from the moment it is recognised
    assert [e for e in orch.store.events(7) if e["kind"] == "pr_adopted"][0]["payload"]["binding"] == "closes-line"

    _green(gh, head)
    assert _tick(orch).advanced[7] == "CI -> REVIEW"
    assert _status(gh, head) == "pending"                   # still only pending: nothing green before a verdict
    _tick(orch)                                             # the SAME reviewer runs
    assert _status(gh, head) == "success"
    assert gh.status_log[-1][:3] == (head, REVIEW_CTX, "success")
    assert orch.store.get(7).review_verdict == f"APPROVE@{head}"
    assert head == gh.get_pr(pr["number"])["head"]["sha"]   # the exact head of the real PR, not a derived sha


def test_adopted_pr_review_uses_the_same_contract_criteria_and_the_real_diff(env):
    """AC-6: the reviewer is given exactly what it is given for native work — the contract's
    acceptance criteria and the branch's own diff. Nothing is skipped for a branch name."""
    config, gh, clock, origin = env
    _issue(gh, 8, risk="LOW")
    pr = _human_pr(config, gh, origin, 8)
    head = pr["head"]["sha"]
    runner = FakeAgentRunner(script={"reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    _green(gh, head)
    _tick(orch); _tick(orch)
    call = [c for c in runner.calls if c.role == "reviewer"][-1]
    assert call.issue_id == 8
    for ac in ("AC-1", "AC-2", "AC-3"):
        assert ac in call.prompt                            # every acceptance criterion of the live contract
    assert "Autonomous workflow" in call.prompt             # the contract text itself
    assert "human.txt" in call.prompt                       # the real file list / diff of the adopted branch
    assert "+work done by hand" in call.prompt


# ---------------------------------------------------------------------------------------------
# AC-3: never nothing at all
# ---------------------------------------------------------------------------------------------

def test_unbound_pr_reports_pending_with_the_reason_and_is_not_adopted(env):
    config, gh, clock, origin = env
    pr = _human_pr(config, gh, origin, None, body="## Issue\n\nnothing linked here\n")
    head = pr["head"]["sha"]
    orch = _orch(config, gh, clock, FakeAgentRunner())
    notes = adopt_open_prs(orch)
    assert _status(gh, head) == "pending"
    assert "Closes #<issue>" in _description(gh, head)
    assert any("no contract bound" in n for n in notes), notes
    assert orch.store.list() == []
    assert adopt_open_prs(orch) == []                       # published once per reason, not every tick
    assert len([e for e in gh.status_log if e[0] == head]) == 1


@pytest.mark.parametrize("why, prepare", [
    ("already delivered by PR", lambda gh, orch, c: orch.store.update(9, pr_number=4242)),
    ("is closed", lambda gh, orch, c: gh.issues[9].update({"state": "closed"})),
    ("is not trusted", lambda gh, orch, c: gh.issues[9].update({"author_association": "NONE"})),
    ("on hold by the owner", lambda gh, orch, c: gh.issues[9]["labels"].append({"name": "agent:hold"})),
    ("decomposed ROOT", lambda gh, orch, c: gh.issues[9]["labels"].append({"name": "agent:decomposed"})),
    ("does not validate", lambda gh, orch, c: gh.issues[9].update({"body": "free-form text, not a contract"})),
])
def test_a_pr_that_cannot_be_adopted_still_reports_pending(env, why, prepare):
    config, gh, clock, origin = env
    c = _issue(gh, 9, risk="LOW")
    pr = _human_pr(config, gh, origin, 9)
    head = pr["head"]["sha"]
    orch = _orch(config, gh, clock, FakeAgentRunner())
    if "already delivered" in why:
        track(orch.store, c)
    prepare(gh, orch, c)
    notes = adopt_open_prs(orch)
    assert _status(gh, head) == "pending", notes
    assert why in _description(gh, head), _description(gh, head)
    rec = orch.store.get(9)
    assert rec is None or (rec.state != sm.PR_OPEN and rec.adopted_pr is None)


def test_draft_pr_reports_pending_and_is_not_adopted(env):
    config, gh, clock, origin = env
    _issue(gh, 10, risk="LOW")
    pr = _human_pr(config, gh, origin, 10, draft=True)
    adopt_open_prs(_orch(config, gh, clock, FakeAgentRunner()))
    assert _status(gh, pr["head"]["sha"]) == "pending"
    assert "draft" in _description(gh, pr["head"]["sha"])


# ---------------------------------------------------------------------------------------------
# AC-4: a rejected review leaves the merge refused — adoption is not a way to turn red green
# ---------------------------------------------------------------------------------------------

def test_block_verdict_on_an_adopted_pr_publishes_failure_and_the_merge_is_refused(env):
    config, gh, clock, origin = env
    gh.required_contexts_for_merge = config.protection_required_contexts     # simulate branch protection
    _issue(gh, 11, risk="LOW")
    pr = _human_pr(config, gh, origin, 11)
    head = pr["head"]["sha"]
    block = {**APPROVE, "verdict": "BLOCK", "summary": "unsafe"}
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"reviewer": block}))
    _tick(orch); _tick(orch)
    _green(gh, head)
    _tick(orch); _tick(orch)
    assert _status(gh, head) == "failure"
    assert gh.status_log[-1][:3] == (head, REVIEW_CTX, "failure")
    # no repair budget on a branch the orchestrator does not own: BLOCKED for a human, not a fixer
    assert orch.store.get(11).state == sm.BLOCKED
    assert not any(c.role in ("fixer", "worker") for c in orch.runner.calls)
    with pytest.raises(GitHubError):
        gh.merge_pr(pr["number"])                            # branch protection refuses the merge
    assert gh.merged == []
    # and no later adoption pass can overwrite that failure with pending
    assert adopt_open_prs(orch) == [] and _status(gh, head) == "failure"
    orch.store.update(11, pr_number=None, adopted_pr=None)   # even if the binding were lost and it re-adopted
    adopt_pr(orch, gh.get_pr(pr["number"]))
    assert _status(gh, head) == "failure"


def test_request_changes_on_an_adopted_pr_stays_failure_after_a_restart(env):
    """_ensure_review_status repairs the status from the store, for an adopted PR like any other."""
    config, gh, clock, origin = env
    _issue(gh, 12, risk="LOW")
    pr = _human_pr(config, gh, origin, 12)
    head = pr["head"]["sha"]
    reject = {**APPROVE, "verdict": "REQUEST_CHANGES", "summary": "weak test"}
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"reviewer": reject}))
    _tick(orch); _tick(orch)
    _green(gh, head)
    _tick(orch); _tick(orch)
    assert _status(gh, head) == "failure" and orch.store.get(12).state == sm.BLOCKED
    gh.statuses[head].pop(REVIEW_CTX)                        # GitHub lost it / a failed publish
    assert orch._ensure_review_status(orch.store, orch.store.get(12), head) == "failure"
    assert _status(gh, head) == "failure"


def test_a_new_commit_on_an_adopted_pr_makes_the_status_pending_again(env):
    config, gh, clock, origin = env
    _issue(gh, 13, risk="LOW")
    pr = _human_pr(config, gh, origin, 13)
    head1 = pr["head"]["sha"]
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    _green(gh, head1)
    _tick(orch); _tick(orch)
    assert _status(gh, head1) == "success"
    _push_more(origin, "feature/human-work")
    head2 = gh.get_pr(pr["number"])["head"]["sha"]
    assert head2 != head1
    assert _tick(orch).advanced[13] == "REVIEW -> CI (head moved, review stale)"
    assert _status(gh, head2) == "pending" and _status(gh, head1) == "success"


def test_a_head_that_moves_while_ci_is_red_still_reports_pending(env):
    """AC-3 at the one place a SHA could carry no status at all: a new commit while the gates are
    red. GitHub evaluates the current head, so "nothing" there is the state #252 exists to remove."""
    config, gh, clock, origin = env
    _issue(gh, 18, risk="LOW")
    pr = _human_pr(config, gh, origin, 18, branch="feature/moving-head")
    head1 = pr["head"]["sha"]
    orch = _orch(config, gh, clock, FakeAgentRunner())
    _tick(orch)
    assert _status(gh, head1) == "pending" and orch.store.get(18).state == sm.CI
    _push_more(origin, "feature/moving-head")
    head2 = gh.get_pr(pr["number"])["head"]["sha"]
    _red(gh, head2)
    _tick(orch)
    assert _status(gh, head2) == "pending"                   # never nothing at all
    assert orch.store.get(18).state == sm.BLOCKED            # red gates, no repair budget: a human
    assert not any(c.role in ("fixer", "worker") for c in orch.runner.calls)


# ---------------------------------------------------------------------------------------------
# AC-5: the branch-name recognition still works and native work is untouched
# ---------------------------------------------------------------------------------------------

def test_native_work_is_not_adopted_and_runs_exactly_as_before(env):
    config, gh, clock, origin = env
    _add_issue(gh, 14, risk="LOW")                           # owner-approved: the normal path
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch)                                              # worker -> PR opened by the orchestrator
    rec = orch.store.get(14)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    assert rec.branch.startswith(config.branch_prefix) and rec.adopted_pr is None
    rep = _tick(orch)
    assert not any("adopted" in a for a in rep.reconciled), rep.reconciled
    _green(gh, head)
    _tick(orch); _tick(orch)
    assert _status(gh, head) == "success" and orch.store.get(14).adopted_pr is None
    assert orch.attempts_remaining(orch.store.get(14)) is True     # native work keeps its repair budget
    assert _tick(orch).advanced[14] == "REVIEW -> READY_FOR_OWNER"


def test_an_agent_branch_pr_opened_outside_the_orchestrator_is_adopted_by_its_branch_name(env):
    """The existing rule is unchanged and is still the binding when it applies."""
    config, gh, clock, origin = env
    _issue(gh, 15, risk="LOW")
    pr = _human_pr(config, gh, origin, 15, branch="agent/15-recovered", body="## Issue\n\nno link at all\n")
    orch = _orch(config, gh, clock, FakeAgentRunner())
    notes = adopt_open_prs(orch)
    assert any("adopted for #15" in n for n in notes), notes
    assert orch.store.get(15).state == sm.PR_OPEN
    assert [e for e in orch.store.events(15) if e["kind"] == "pr_adopted"][0]["payload"]["binding"] == "branch-name"


def test_adoption_never_races_an_agent_that_holds_the_issue(env):
    config, gh, clock, origin = env
    c = _issue(gh, 16, risk="LOW")
    pr = _human_pr(config, gh, origin, 16)
    orch = _orch(config, gh, clock, FakeAgentRunner())
    track(orch.store, c)
    orch.store.transition(16, sm.CLAIMED)
    notes = adopt_open_prs(orch)
    assert orch.store.get(16).state == sm.CLAIMED             # untouched
    assert _status(gh, pr["head"]["sha"]) == "pending" and "tracked and CLAIMED" in _description(gh, pr["head"]["sha"])
    assert any("not adopted" in n for n in notes), notes


def test_adoption_is_idempotent_and_dry_run_changes_nothing(env):
    config, gh, clock, origin = env
    _issue(gh, 17, risk="LOW")
    pr = _human_pr(config, gh, origin, 17)
    dry = _orch(config, gh, clock, FakeAgentRunner(), dry_run=True)
    notes = adopt_open_prs(dry)
    assert any("would be adopted for #17" in n for n in notes), notes
    assert dry.store.get(17) is None and gh.statuses.get(pr["head"]["sha"], {}) == {}
    orch = _orch(config, gh, clock, FakeAgentRunner())
    assert len(adopt_open_prs(orch)) == 1
    assert adopt_open_prs(orch) == []                        # already recognised: nothing repeats
    assert len([e for e in orch.store.events(17) if e["kind"] == "pr_adopted"]) == 1
