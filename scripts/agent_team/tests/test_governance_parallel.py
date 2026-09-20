"""Owner/Team-Lead governance and safe parallel execution (fakes only).

The rules under test (docs/wiki/architecture/agent-team-workflow.md, "Governance"):
- a ROOT Issue is authorized by the owner's `owner:approved` label and executes in full without
  further approval; a child Issue inherits that authorization from its ROOT and cannot escape the
  ROOT's scope; the Team Lead may create children but never ROOT authorization;
- the scheduler saturates workers safely: dependency-aware, lock-aware, resource-aware, and a PR
  waiting for the owner never stops unrelated work;
- nothing merges automatically — only the owner's explicit merge command does.
"""
from __future__ import annotations

import dataclasses

import pytest

from agent_team import state_machine as sm
from agent_team.agent_runner import FakeAgentRunner
from agent_team.config import ConfigError, load_config
from agent_team.issue_contract import Authorization, ContractError, child_scope_problems, numbered_title, parse_contract, render_body
from agent_team.labels import CHILD_LABEL, DECOMPOSED_LABEL, HOLD_LABEL, metadata_labels
from agent_team.tests.helpers import KNOWN_LOCKS, make_contract
from agent_team.tests.test_orchestrator_lifecycle import (  # noqa: F401
    APPROVE, _add_issue, _green, _orch, _owner_merge, _tick, _worker_that_commits, env,
)

ROOT = 120


def _root(gh, number=ROOT, *, approved=True, decomposed=True, domains="knowledge, backend",
          locks="docs (shared), planner-core (exclusive)", **kw):
    """An owner-approved ROOT product Issue (created/approved by the owner). Decomposed roots are not
    executed as tasks themselves."""
    c = make_contract(number, title=f"[agent] ROOT {number}", domains=domains, locks=locks, **kw)
    labels = metadata_labels(c.domains, c.risk, c.resource_class) + (["owner:approved"] if approved else []) + \
             ([DECOMPOSED_LABEL] if decomposed else [])
    gh.add_issue(number, c.title, render_body(c), labels)
    return c


def _child(gh, number, root=ROOT, *, domains="knowledge", locks="docs (shared)", deps="none", queued=True, **kw):
    """A child Issue derived by the Team Lead: `agent:child` + inherited authorization, NO owner:approved."""
    c = make_contract(number, title=f"[agent] Child {number}", domains=domains, locks=locks, deps=deps, **kw)
    c = c.with_authorization(Authorization(source="inherited", root_issue=root, parent_issue=root, derived_by="team-lead", scope_inherited=True))
    labels = [CHILD_LABEL, "agent:queued" if queued else "agent:draft", *metadata_labels(c.domains, c.risk, c.resource_class)]
    gh.add_issue(number, c.title, render_body(c), labels)
    return c


def _runner():
    return FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})


def _with(config, **over):
    return dataclasses.replace(config, **over)


def _to_ready(orch, gh, issue_id):
    """Green CI for the current head, then tick until the review verdict makes it READY_FOR_OWNER."""
    for _ in range(6):
        rec = orch.store.get(issue_id)
        if rec.state == sm.READY_FOR_OWNER:
            return rec
        _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
        _tick(orch)
    rec = orch.store.get(issue_id)
    assert rec.state == sm.READY_FOR_OWNER, rec.state
    return rec


def _finish(orch, gh, issue_id):
    """Drive one Issue from PR_OPEN to DONE: green CI, review, owner merge, smoke. When a sibling
    merged first the base advanced: the merge is refused, the orchestrator updates the branch and
    re-validates the new head, and the owner merges that — exactly the production path."""
    for _ in range(3):
        _to_ready(orch, gh, issue_id)
        res = _owner_merge(orch, issue_id)
        if res["result"] == "SUCCESS":
            break
        assert "base" in res["reason"], res
        _tick(orch)                               # branch updated from base, readiness invalidated -> CI
    else:
        raise AssertionError(f"#{issue_id} never merged")
    for _ in range(3):                            # smoke -> DONE
        _tick(orch)
        if orch.store.get(issue_id).state == sm.DONE:
            break
    assert orch.store.get(issue_id).state == sm.DONE


# ---------------------------------------------------------------------------------------------
# authorization
# ---------------------------------------------------------------------------------------------

def test_root_issue_authorization_is_the_owner_label_and_executes_in_full(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    # owner-approved, but nobody queued it: the owner's approval alone authorizes execution
    c = make_contract(30, title="[agent] Task 30")
    gh.add_issue(30, c.title, render_body(c), ["agent:draft", "owner:approved", *metadata_labels(c.domains, c.risk, c.resource_class)])
    _add_issue(gh, 31, approved=False)            # queued by the lead, never approved by the owner
    rep = _tick(orch)
    assert rep.started == [30]
    assert orch.store.get(30).kind == "root" and orch.store.get(30).root == 30
    assert "agent:queued" in gh.issue_labels(30) or orch.store.get(30).state != sm.QUEUED
    assert orch.store.get(31) is None and 31 in orch.awaiting_owner
    assert any(e["kind"] == "authorized" and e["payload"]["source"] == "owner" for e in orch.store.events(30))


def test_child_inherits_authorization_from_an_approved_root(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh)
    _child(gh, 121)
    rep = _tick(orch)
    assert rep.started == [121]
    rec = orch.store.get(121)
    assert rec.kind == "child" and rec.root_issue == ROOT and rec.parent_issue == ROOT
    assert "owner:approved" not in gh.issue_labels(121)
    assert orch.store.get(ROOT) is None            # a decomposed ROOT is never run as a task
    assert any(e["kind"] == "authorized" and e["payload"]["source"] == "inherited" for e in orch.store.events(121))


def test_child_of_an_unapproved_root_never_executes(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh, 130, approved=False)
    _child(gh, 131, root=130)
    rep = _tick(orch)
    assert rep.started == []
    rec = orch.store.get(131)
    assert rec.state == sm.BLOCKED and rec.failure_class == "SCOPE_ESCAPE"
    assert "not owner-approved" in rec.last_error
    assert any(n == 131 and "refused" in body for n, body in gh.comments)


def test_child_cannot_escape_root_scope(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    root = _root(gh)                                       # domains knowledge, backend; locks docs(shared), planner-core(exclusive)
    wide = _child(gh, 122, domains="knowledge, geometry")  # geometry is not in the ROOT
    lock = _child(gh, 123, locks="validator-core (exclusive)")
    rep = _tick(orch)
    assert rep.started == []
    for n, needle in ((122, "domains outside the ROOT"), (123, "lock validator-core not declared")):
        rec = orch.store.get(n)
        assert rec.state == sm.BLOCKED and rec.failure_class == "SCOPE_ESCAPE" and needle in rec.last_error
    # the pure check: budget may not widen either
    loose = make_contract(124, title="[agent] loose", risk="MEDIUM").with_authorization(Authorization("inherited", ROOT, ROOT, "team-lead", True))
    body = render_body(loose).replace("LOST: 0", "LOST: 3")
    loose = parse_contract(124, loose.title, body, known_locks=KNOWN_LOCKS)
    assert any("regression budget LOST" in p for p in child_scope_problems(loose, root))
    assert child_scope_problems(wide, root) and child_scope_problems(lock, root)
    # a child inside the scope has no problems
    ok = make_contract(125, title="[agent] ok").with_authorization(Authorization("inherited", ROOT, ROOT, "team-lead", True))
    assert child_scope_problems(ok, root) == []


def test_authorization_section_is_validated():
    c = make_contract(140, title="[agent] bad auth")
    body = render_body(c) + "\n### Authorization\n\nsource: inherited\nscope_inherited: true\n"
    with pytest.raises(ContractError) as exc:
        parse_contract(140, c.title, body, known_locks=KNOWN_LOCKS)
    assert any("root_issue" in p for p in exc.value.problems)
    body = render_body(c) + "\n### Authorization\n\nsource: inherited\nroot_issue: #140\nscope_inherited: true\n"
    with pytest.raises(ContractError) as exc:
        parse_contract(140, c.title, body, known_locks=KNOWN_LOCKS)
    assert any("inherit from itself" in p for p in exc.value.problems)


def test_owner_hold_keeps_an_authorized_issue_out_of_execution(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _add_issue(gh, 32)
    gh.add_labels(32, [HOLD_LABEL])
    rep = _tick(orch)
    assert rep.started == [] and 32 in orch.on_hold and orch.store.get(32) is None
    gh.remove_label(32, HOLD_LABEL)
    assert _tick(orch).started == [32]


# ---------------------------------------------------------------------------------------------
# parallelism
# ---------------------------------------------------------------------------------------------

def test_multiple_workers_scheduled_from_one_root(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh)
    for n in (121, 122, 123):
        _child(gh, n)
    rep = _tick(orch)
    assert rep.started == [121, 122, 123]
    assert all(orch.store.get(n).state in (sm.PR_OPEN, sm.CI) for n in (121, 122, 123))
    assert len({orch.store.get(n).branch for n in (121, 122, 123)}) == 3          # own branch + worktree each
    assert len({orch.store.get(n).worktree for n in (121, 122, 123)}) == 3
    assert orch.active_roots() == {ROOT}


def test_dependency_aware_parallelism_follows_the_dag(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh)
    _child(gh, 121)                                  # domain model
    _child(gh, 122, deps="#121")                     # planner
    _child(gh, 123, deps="#121")                     # validator
    _child(gh, 124, deps="#122, #123")               # integration
    rep = _tick(orch)
    assert rep.started == [121]
    assert "waiting for #121" in rep.waiting[122] and "waiting for #121" in rep.waiting[123]
    _finish(orch, gh, 121)
    rep = _tick(orch)
    assert rep.started == [122, 123]                 # both start as soon as their one dependency is green
    assert "waiting" in rep.waiting[124]
    _finish(orch, gh, 122)
    assert "waiting for #123" in _tick(orch).waiting[124]
    _finish(orch, gh, 123)
    assert _tick(orch).started == [124]


def test_work_stealing_a_finished_run_wakes_the_scheduler_and_the_next_task_starts(env):
    config, gh, clock, origin = env
    orch = _orch(_with(config, max_worker_agents=1), gh, clock, _runner())
    _root(gh)
    _child(gh, 121)
    _child(gh, 122)
    orch._wake.clear()
    rep = _tick(orch)
    assert rep.started == [121] and "worker slots full" in rep.waiting[122]
    assert orch._wake.is_set()                       # the finished run asked the loop to re-plan at once
    assert _tick(orch).started == [122]              # the free worker takes the next independent task


def test_safe_resource_saturation_respects_slots_and_weighted_capacity(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())      # 3 workers, weighted capacity 7 (real config)
    _root(gh)
    for n in (121, 122, 123, 124):
        _child(gh, n)
    rep = _tick(orch)
    assert rep.started == [121, 122, 123] and "worker slots full" in rep.waiting[124]


def test_weighted_capacity_limits_heavy_work_even_with_free_slots(env):
    config, gh, clock, origin = env
    orch = _orch(_with(config, max_worker_agents=5), gh, clock, _runner())   # capacity 7: HEAVY=3 each
    _root(gh, 200, locks="docs (shared)")
    for n in (201, 202, 203):
        _child(gh, n, root=200, resource="HEAVY")
    rep = _tick(orch)
    assert rep.started == [201, 202] and "weighted capacity" in rep.waiting[203]


def test_lock_aware_scheduling_serializes_the_same_exclusive_lock(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh)
    _child(gh, 121, locks="planner-core (exclusive)")
    _child(gh, 122, locks="planner-core (exclusive)")
    _child(gh, 123, locks="docs (shared)")
    # keep 121 running so its lock stays held
    orch.runner.script["worker"] = lambda spec: (_ for _ in ()).throw(RuntimeError("hold")) if spec.issue_id == 121 else _worker_that_commits()(spec)
    rep = orch.tick()
    assert rep.started == [121, 123]
    assert "planner-core" in rep.waiting[122] and "#121" in rep.waiting[122]
    orch.wait_for_threads(timeout=30)


def test_ready_pr_does_not_stop_unrelated_work(env):
    config, gh, clock, origin = env
    orch = _orch(_with(config, max_active_issues=1), gh, clock, _runner())
    _add_issue(gh, 40, locks="planner-core (exclusive)")
    _tick(orch)
    rec = orch.store.get(40)
    _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    for _ in range(4):
        _tick(orch)
        if orch.store.get(40).state == sm.READY_FOR_OWNER:
            break
    assert orch.store.get(40).state == sm.READY_FOR_OWNER
    assert not any(l.issue_id == 40 for l in orch.store.locks_held())      # locks released at READY
    assert orch.active_roots() == set()                                    # waiting for the owner is not "active"
    _add_issue(gh, 41, locks="planner-core (exclusive)")                   # same lock, another ROOT
    rep = _tick(orch)
    assert rep.started == [41]
    assert orch.store.get(40).state == sm.READY_FOR_OWNER and gh.merged == []


def test_drain_stops_new_work_and_completes_when_idle(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _add_issue(gh, 50)
    _add_issue(gh, 51)
    orch.request_drain()
    rep = _tick(orch)
    assert rep.started == [] and all("draining" in w for w in rep.waiting.values())
    assert orch.draining and orch.drain_complete()
    orch.request_drain()                             # a second request means "stop now"
    assert orch._stop.is_set()


# ---------------------------------------------------------------------------------------------
# Team Lead authority (tools) and the single owner gate
# ---------------------------------------------------------------------------------------------

def test_team_lead_may_create_child_issues_but_not_root_authorization(env, capsys):
    from agent_team.cli import _create_child
    config, gh, clock, origin = env
    _root(gh, decomposed=False)
    c = make_contract(0, title="[agent] a child")
    assert _create_child(config, gh, c, ROOT, queue=True) == 0
    n = gh.next_number - 1                         # the created child (FakeGitHub numbers new issues from 100)
    labels = gh.issue_labels(n)
    assert CHILD_LABEL in labels and "agent:queued" in labels and "owner:approved" not in labels
    assert gh.get_issue(n)["title"] == numbered_title(n, "a child")    # #25: child Issues are numbered on creation too
    body = gh.get_issue(n)["body"]
    assert "### Authorization" in body and f"root_issue: #{ROOT}" in body and "derived_by: team-lead" in body
    # ... but never for a ROOT the owner did not approve
    _root(gh, 130, approved=False, decomposed=False)
    before = len(gh.issues)
    assert _create_child(config, gh, make_contract(0, title="[agent] orphan"), 130, queue=True) == 1
    assert len(gh.issues) == before and "not owner-approved" in capsys.readouterr().err
    # ... and never outside the ROOT's scope
    assert _create_child(config, gh, make_contract(0, title="[agent] wide", domains="knowledge, geometry"), ROOT, queue=True) == 1
    assert len(gh.issues) == before


def test_no_automatic_merge_under_any_circumstance(env, tmp_path):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _add_issue(gh, 60, risk="LOW")                  # the lowest risk still waits for the owner
    _tick(orch)
    _green(gh, gh.get_pr(orch.store.get(60).pr_number)["head"]["sha"])
    for _ in range(4):
        _tick(orch)
        clock.t += 3600
    assert orch.store.get(60).state == sm.READY_FOR_OWNER and gh.merged == []
    # the config loader refuses an auto-merge policy outright
    import yaml
    raw = yaml.safe_load((config.repo_root / ".agent" / "config.yaml").read_text())
    for risk in raw["risk_policy"].values():
        if isinstance(risk, dict) and "auto_merge" in risk:
            risk["auto_merge"] = True
    bad = tmp_path / "bad"; (bad / ".agent").mkdir(parents=True)
    (bad / ".agent" / "config.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError):
        load_config(repo_root=bad)


def test_only_the_owner_merge_command_merges_and_revalidates_the_sha(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _add_issue(gh, 61)
    _tick(orch)
    _green(gh, gh.get_pr(orch.store.get(61).pr_number)["head"]["sha"])
    for _ in range(4):
        _tick(orch)
        if orch.store.get(61).state == sm.READY_FOR_OWNER:
            break
    rec = orch.store.get(61)
    assert rec.state == sm.READY_FOR_OWNER
    assert _owner_merge(orch, 61, sha="deadbeef")["result"] == "REFUSED"
    assert gh.merged == []
    assert _owner_merge(orch, 61)["result"] == "SUCCESS"
    assert gh.merged == [rec.pr_number]


def test_decomposed_root_closes_when_every_child_is_done(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _root(gh)
    _child(gh, 121)
    _child(gh, 122)
    _tick(orch)
    _finish(orch, gh, 121)
    assert gh.get_issue(ROOT)["state"] == "open"
    _finish(orch, gh, 122)
    rep = _tick(orch)
    assert gh.get_issue(ROOT)["state"] == "closed" and "agent:done" in gh.issue_labels(ROOT)
    assert any("ROOT #120 closed" in r for r in rep.reconciled) or orch.store.get_meta("root_closed:120") == "1"
    assert any(n == ROOT and "Every child Issue" in body for n, body in gh.comments)


def test_frozen_claims_stop_new_issues_but_in_flight_work_continues(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _add_issue(gh, 80)
    _tick(orch)                                              # #80 is in flight (PR open)
    _add_issue(gh, 81)
    orch.set_claims_frozen(True, who="owner", reason="review the app first")
    rep = _tick(orch)
    assert rep.started == [] and "frozen" in rep.waiting[81]
    rec = _to_ready(orch, gh, 80)                            # CI + review of the in-flight PR still run
    assert rec.state == sm.READY_FOR_OWNER
    orch.set_claims_frozen(False)
    assert _tick(orch).started == [81]
