"""ROOT completion: a closed or retired child must not imply successful delivery (#188 directive 5).

The five tests the owner asked for, plus the refinements: a closed-unmerged PR is a retirement, a
merge into an intermediate integration branch is not delivery to the base branch, completion is
judged against the ROOT's OWN required target, and anything that cannot be established refuses.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_team import state_machine as sm
from agent_team.root_completion import ChildOutcome, child_outcome, evaluate_root

MAIN = "main"
INTEGRATION = "integration/stage-2"


@dataclass
class FakeChild:
    issue_id: int
    pr_number: int | None = None
    review_verdict: str | None = None
    state: str = sm.DONE


def _pr(number, *, merged=True, base=MAIN, state="closed"):
    return {"number": number, "merged": merged, "state": state, "base": {"ref": base}}


def _lookup(prs):
    def get(n):
        if n not in prs:
            raise RuntimeError(f"PR #{n} unreadable")
        return prs[n]
    return get


def _evaluate(children, prs, *, target=MAIN, integration_open=False):
    return evaluate_root(1, children, required_target=target,
                         integration_open=integration_open, pr_lookup=_lookup(prs))


# ------------------------------------------------------------------ 1. the regression for #127

def test_root_not_closed_when_a_child_was_retired_unmerged():
    """#133 delivered, #134 retired as a measured negative result with its PR closed unmerged.
    This is exactly what auto-closed ROOT #127 on 2026-10-11."""
    children = [FakeChild(133, 135, "APPROVE@d3933f89"), FakeChild(134, 139, None)]
    prs = {135: _pr(135), 139: _pr(139, merged=False)}
    v = _evaluate(children, prs)
    assert not v.may_close
    assert "#134" in v.reason and "never merged" in v.reason
    assert [c.delivered for c in v.children] == [True, False]


# ------------------------------------------------------------------ 2. the good path still works

def test_root_closed_when_every_child_pr_merged_into_the_required_target():
    children = [FakeChild(1, 10, "APPROVE@aaaaaaaa"), FakeChild(2, 11, "APPROVE@bbbbbbbb")]
    v = _evaluate(children, {10: _pr(10), 11: _pr(11)})
    assert v.may_close
    body = v.comment()
    assert "merged into `main`" in body and "approved at `aaaaaaaa`" in body
    assert "Closing the ROOT." in body


# ------------------------------------------------------------------ 3. no PR at all

def test_root_not_closed_when_a_child_has_no_pr():
    v = _evaluate([FakeChild(1, 10, "APPROVE@a"), FakeChild(2, None, None)], {10: _pr(10)})
    assert not v.may_close
    assert "no PR" in v.reason


# ------------------------------------------------------------------ 4. the comment may not lie

def test_closure_comment_describes_only_verified_outcomes():
    """The old text asserted "done and merged by the owner" for every child, verified or not."""
    children = [FakeChild(1, 10, "APPROVE@abcdef123456")]
    v = _evaluate(children, {10: _pr(10)})
    body = v.comment()
    assert "PR #10 merged into `main`, approved at `abcdef123456`" in body
    # every claim in the comment is a fact that was checked
    for c in v.children:
        assert c.delivered and str(c.pr_number) in body


def test_a_refused_root_produces_no_comment_at_all():
    v = _evaluate([FakeChild(1, 10, None)], {10: _pr(10, merged=False)})
    assert not v.may_close          # the orchestrator never calls .comment() on a refusal


# ------------------------------------------------------------------ 5. the real #127 scenario

def test_the_127_scenario_does_not_auto_close():
    children = [FakeChild(133, 135, "APPROVE@d3933f89"), FakeChild(134, 139, None)]
    prs = {135: _pr(135, base=MAIN), 139: _pr(139, merged=False, base="integration/holiday-sukkot-2026")}
    assert not _evaluate(children, prs).may_close


# ------------------------------------------------------------------ the refinements

def test_done_alone_is_not_delivery():
    """Every child is DONE and nothing was merged — the old rule would have closed the ROOT."""
    children = [FakeChild(1, 10, None, state=sm.DONE), FakeChild(2, 11, None, state=sm.DONE)]
    prs = {10: _pr(10, merged=False), 11: _pr(11, merged=False)}
    assert not _evaluate(children, prs).may_close


def test_a_merge_into_another_branch_is_not_delivery_to_the_required_target():
    v = _evaluate([FakeChild(1, 10, "APPROVE@a")], {10: _pr(10, base="integration/something-else")})
    assert not v.may_close
    assert "not this ROOT's required target" in v.children[0].detail


def test_an_open_integration_branch_blocks_closure_even_with_every_child_merged():
    """Children merged into an intermediate branch have NOT reached the base branch: that happens
    only through the ROOT's own rollup PR."""
    children = [FakeChild(1, 10, "APPROVE@a"), FakeChild(2, 11, "APPROVE@b")]
    prs = {10: _pr(10, base=INTEGRATION), 11: _pr(11, base=INTEGRATION)}
    v = _evaluate(children, prs, target=INTEGRATION, integration_open=True)
    assert not v.may_close
    assert "intermediate integration branch" in v.reason
    assert all(c.delivered for c in v.children)      # the children ARE delivered to the target


def test_a_landed_integration_branch_allows_closure():
    children = [FakeChild(1, 10, "APPROVE@a")]
    v = _evaluate(children, {10: _pr(10, base=INTEGRATION)}, target=INTEGRATION,
                  integration_open=False)
    assert v.may_close


# ------------------------------------------------------------------ fail closed

def test_an_unknown_required_target_refuses():
    v = _evaluate([FakeChild(1, 10, "APPROVE@a")], {10: _pr(10)}, target=None)
    assert not v.may_close and "could not be determined" in v.reason


def test_an_unreadable_pr_refuses_rather_than_assuming_delivery():
    v = _evaluate([FakeChild(1, 10, "APPROVE@a")], {})      # lookup raises
    assert not v.may_close
    assert "could not be read" in v.children[0].detail


def test_missing_acceptance_evidence_refuses():
    """Merged into the right target, but no APPROVE was ever recorded."""
    v = _evaluate([FakeChild(1, 10, None)], {10: _pr(10)})
    assert not v.may_close
    assert "acceptance evidence is missing" in v.children[0].detail


def test_a_request_changes_verdict_is_not_acceptance():
    v = _evaluate([FakeChild(1, 10, "REQUEST_CHANGES@abc")], {10: _pr(10)})
    assert not v.may_close
    assert "REQUEST_CHANGES" in v.children[0].detail


def test_no_children_refuses():
    assert not _evaluate([], {}).may_close


# ------------------------------------------------------------------ the ancestry check (wiring)
#
# `root_integrations` carries a `closed` flag, and it is NOT proof the branch landed: measured on
# 2026-10-11, `integration/non-rectangular-geometry` was flagged closed while still 3 commits ahead
# of origin/main. These pin that the orchestrator decides on git ancestry instead.

from agent_team.tests.test_orchestrator_lifecycle import _git, _orch, env  # noqa: E402,F401
from agent_team.agent_runner import FakeAgentRunner  # noqa: E402


def _o(env):
    config, gh, clock, _ = env
    return _orch(config, gh, clock, FakeAgentRunner(script={}))


def test_a_branch_that_reached_main_is_landed(env):
    orch = _o(env)
    root = orch.config.repo_root
    _git(["checkout", "-q", "-b", "integration/landed"], root)
    _git(["commit", "-q", "--allow-empty", "-m", "work"], root)
    _git(["checkout", "-q", "main"], root)
    _git(["merge", "-q", "--no-ff", "-m", "rollup", "integration/landed"], root)
    _git(["push", "-q", "origin", "main", "integration/landed"], root)
    assert orch.integration_landed("integration/landed") is True


def test_a_branch_ahead_of_main_is_not_landed(env):
    orch = _o(env)
    root = orch.config.repo_root
    _git(["checkout", "-q", "-b", "integration/ahead"], root)
    _git(["commit", "-q", "--allow-empty", "-m", "unlanded work"], root)
    _git(["push", "-q", "origin", "integration/ahead"], root)
    _git(["checkout", "-q", "main"], root)
    assert orch.integration_landed("integration/ahead") is False


def test_a_missing_branch_cannot_be_established_and_is_treated_as_unlanded(env):
    """Deleted after its rollup merged, or deleted without ever landing — indistinguishable here,
    so it refuses rather than guesses."""
    orch = _o(env)
    assert orch.integration_landed("integration/never-existed") is None


def test_required_target_uses_ancestry_not_the_closed_flag(env):
    """The exact #105 shape: flagged closed, still ahead of main."""
    orch = _o(env)
    root = orch.config.repo_root
    _git(["checkout", "-q", "-b", "integration/flagged"], root)
    _git(["commit", "-q", "--allow-empty", "-m", "unlanded"], root)
    _git(["push", "-q", "origin", "integration/flagged"], root)
    _git(["checkout", "-q", "main"], root)
    import json
    orch.store.set_meta("root_integrations", json.dumps(
        {"7": {"branch": "integration/flagged", "label": "x", "closed": True}}))
    target, unlanded = orch.root_required_target(7)
    assert target == "integration/flagged"
    assert unlanded is True            # the flag said closed; ancestry says otherwise
