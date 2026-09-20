"""ROOT-scoped integration branches (governance §42, owner 2026-09-20): a ROOT such as Concept Engine
v2 works against its own `integration/<slug>` branch — children start from it, their PRs target it,
the Team Lead merges every fully validated child into it, and main is reached only through ONE
final rollup PR the owner merges. Also the owner's ROOT priority order and per-domain caps."""
from __future__ import annotations

import dataclasses

from agent_team import state_machine as sm
from agent_team.tests.helpers import make_contract
from agent_team.tests.test_governance_parallel import _child, _root, _runner  # noqa: F401
from agent_team.tests.test_integration_mode import _to_ready_or_integrated  # noqa: F401
from agent_team.tests.test_orchestrator_lifecycle import _add_issue, _git, _green, _orch, _owner_merge, _tick, env  # noqa: F401


def _with(config, **over):
    return dataclasses.replace(config, **over)


def test_children_of_a_root_with_an_integration_branch_start_from_it_target_it_and_are_merged_into_it(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh, 200, locks="docs (shared)")
    _child(gh, 201, root=200)
    _child(gh, 202, root=200, deps="#201")
    sha = orch.set_root_integration(200, "integration/concept-engine-v2", label="Concept Engine v2")
    assert orch.worktrees.branch_exists("integration/concept-engine-v2", remote=True)
    assert orch.root_integration_for(200)["branch"] == "integration/concept-engine-v2"
    _tick(orch)
    rec = orch.store.get(201)
    assert rec.state == sm.PR_OPEN and rec.base_sha == sha
    assert gh.get_pr(rec.pr_number)["base"]["ref"] == "integration/concept-engine-v2"     # never main
    _to_ready_or_integrated(orch, gh, 201)
    rec = orch.store.get(201)
    assert rec.state == sm.INTEGRATED and gh.merged == [rec.pr_number]
    root = config.repo_root
    _git(["fetch", "-q", "origin"], root)
    assert "work-201.txt" not in _git(["ls-tree", "--name-only", "origin/main"], root).stdout
    assert "work-201.txt" in _git(["ls-tree", "--name-only", "origin/integration/concept-engine-v2"], root).stdout
    assert orch.integrations()[0]["issue"] == 201 and orch.integrations()[0]["branch"] == "integration/concept-engine-v2"
    assert any(e["kind"] == "integration_smoke" and e["payload"]["ok"] for e in orch.store.events(201))
    assert _owner_merge(orch, 201, sha=rec.validated_commit)["result"] == "REFUSED"       # nothing is READY for main
    # the dependent child starts from the integration branch and sees the integrated work
    if orch.store.get(202).state == sm.QUEUED:
        _tick(orch)
    rec2 = orch.store.get(202)
    assert rec2.state != sm.QUEUED
    assert "work-201.txt" in _git(["ls-tree", "--name-only", "HEAD"], rec2.worktree).stdout
    _to_ready_or_integrated(orch, gh, 202)
    assert [i["issue"] for i in orch.integrations()] == [201, 202]
    # an unrelated ROOT still goes the normal way: PR against main, READY_FOR_OWNER
    _add_issue(gh, 210)
    _tick(orch)
    rec3 = orch.store.get(210)
    assert gh.get_pr(rec3.pr_number)["base"]["ref"] == "main"
    _to_ready_or_integrated(orch, gh, 210)
    assert orch.store.get(210).state == sm.READY_FOR_OWNER
    # the registry survives a restart and can be closed
    orch2 = _orch(config, gh, clock, _runner())
    assert orch2.root_integration_for(200)["branch"] == "integration/concept-engine-v2"
    orch2.close_root_integration(200)
    assert orch2.root_integration_for(200) is None


def test_root_integration_branch_name_is_validated_and_the_owner_is_told(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    try:
        orch.set_root_integration(200, "feature/x")
    except ValueError as exc:
        assert "integration/" in str(exc)
    else:
        raise AssertionError("a non-integration branch name was accepted")
    orch.set_root_integration(200, "integration/x", label="X")
    assert any(e["kind"] == "ROOT_INTEGRATION_SET" for e in orch.store.events(200))


def test_owner_priority_order_and_per_domain_caps(env):
    config, gh, clock, origin = env
    # three ROOT tasks queued: the owner's priority list puts 302 first, then 301; 300 is unlisted.
    # `qa` implies no lock, so the only thing holding the others back is the per-domain cap.
    for n in (300, 301, 302):
        _add_issue(gh, n, domains="qa", locks="none")
    orch = _orch(_with(config, priority_roots=(302, 301), max_active_by_domain={"qa": 1}, max_active_issues=6), gh, clock, _runner())
    rep = _tick(orch)
    assert rep.started == [302]                                  # priority first, and only ONE qa Issue in flight
    assert all("domain cap" in v for k, v in rep.waiting.items() if k in (300, 301)), rep.waiting
