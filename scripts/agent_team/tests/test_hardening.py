"""Hardening behaviors: enforceable review status, LOST allowance policy, verification types,
break-glass detection. Same fakes as the lifecycle tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_team import state_machine as sm
from agent_team.agent_runner import FakeAgentRunner
from agent_team.ci import verify
from agent_team.ci.regression_gate import evaluate as gate4_evaluate
from agent_team.issue_contract import parse_budget_value, render_body
from agent_team.labels import metadata_labels
from agent_team.regression_budget import evaluate as evaluate_budget
from agent_team.tests.helpers import KNOWN_LOCKS, make_contract
from agent_team.tests.test_orchestrator_lifecycle import APPROVE, _add_issue, _git, _green, _orch, _tick, _worker_that_commits, env  # noqa: F401

REVIEW_CTX = "agent-review-result"


def _statuses(gh, sha):
    return gh.statuses.get(sha, {}).get(REVIEW_CTX, {}).get("state")


# ---------------------------------------------------------------------------------------------
# 1. independent review is enforceable by GitHub
# ---------------------------------------------------------------------------------------------

def test_review_status_pending_then_success_on_validated_sha(env):
    config, gh, clock, _ = env
    gh.required_contexts_for_merge = config.protection_required_contexts   # simulate branch protection
    _add_issue(gh, 1, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)                                              # PR opened -> pending on the head
    rec = orch.store.get(1)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    assert _statuses(gh, head) == "pending"
    _tick(orch)                                              # -> CI
    _green(gh, head)
    _tick(orch)                                              # -> REVIEW (still pending)
    assert _statuses(gh, head) == "pending"
    _tick(orch)                                              # reviewer APPROVE -> success on the exact SHA
    assert _statuses(gh, head) == "success"
    assert gh.status_log[-1][:3] == (head, REVIEW_CTX, "success")
    _tick(orch)                                              # -> READY
    assert _tick(orch).advanced[1] == "READY -> MERGED"     # GitHub (fake protection) let it through
    events = [e for e in orch.store.events(1) if e["kind"] == "merge_gate_audit"]
    assert events and events[-1]["payload"]["bypass"] is False
    assert events[-1]["payload"]["contexts"] == {"agent-ci-result": "success", REVIEW_CTX: "success"}


def test_review_status_failure_on_request_changes(env):
    config, gh, clock, _ = env
    _add_issue(gh, 2, risk="LOW")
    reject = {**APPROVE, "verdict": "REQUEST_CHANGES", "summary": "weak test"}
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": reject}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(2)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch)
    assert _statuses(gh, head) == "failure" and orch.store.get(2).state == sm.FIX_REQUIRED


def test_sha_change_after_review_makes_status_stale_and_reruns_review(env):
    config, gh, clock, origin = env
    _add_issue(gh, 3, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(3)
    head1 = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head1)
    _tick(orch); _tick(orch)                                 # reviewed + approved head1
    assert _statuses(gh, head1) == "success" and orch.store.get(3).review_verdict == f"APPROVE@{head1}"
    # someone pushes another commit to the PR branch
    wt = Path(rec.worktree)
    (wt / "extra.txt").write_text("more\n")
    _git(["add", "-A"], wt); _git(["commit", "-q", "-m", "extra"], wt); _git(["push", "-q", "origin", rec.branch], wt)
    head2 = gh.get_pr(rec.pr_number)["head"]["sha"]
    assert head2 != head1
    out = _tick(orch).advanced[3]
    assert out == "REVIEW -> CI (head moved, review stale)"
    assert _statuses(gh, head2) == "pending" and "stale" in gh.status_log[-1][3]
    assert _statuses(gh, head1) == "success"                 # the old SHA keeps its own record; it is not the head any more
    _green(gh, head2)
    _tick(orch)                                              # -> REVIEW again
    assert orch.store.get(3).state == sm.REVIEW
    reviews_before = len([c for c in runner.calls if c.role == "reviewer"])
    _tick(orch)                                              # review runs again for head2
    assert len([c for c in runner.calls if c.role == "reviewer"]) == reviews_before + 1
    assert orch.store.get(3).review_verdict == f"APPROVE@{head2}" and _statuses(gh, head2) == "success"


def test_merge_is_deferred_until_github_shows_every_required_context(env):
    """Never merge through the admin exemption: if GitHub does not show the review status green,
    the orchestrator waits (and re-publishes from the store) instead of merging."""
    config, gh, clock, _ = env
    _add_issue(gh, 4, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(4)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch); _tick(orch)
    assert orch.store.get(4).state == sm.READY
    # simulate GitHub losing the status (or a failed publish): the store still says APPROVE@head
    gh.statuses[head].pop(REVIEW_CTX)
    real_set = gh.set_commit_status
    gh.set_commit_status = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("github down"))
    out = _tick(orch).advanced[4]
    assert out.startswith("merge deferred") and REVIEW_CTX + "=missing" in out
    assert gh.merged == [] and orch.store.get(4).state == sm.READY
    assert any(e["kind"] == "merge_deferred" for e in orch.store.events(4))
    gh.set_commit_status = real_set
    assert _tick(orch).advanced[4] == "READY -> MERGED"     # re-published from the store, then merged
    assert _statuses(gh, head) == "success"


def test_ci_check_missing_on_github_defers_merge(env):
    config, gh, clock, _ = env
    _add_issue(gh, 5, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(5)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch); _tick(orch)
    assert orch.store.get(5).state == sm.READY
    gh.checks[head] = [c for c in gh.checks[head] if c["name"] != "agent-ci-result"]   # aggregate check vanished
    out = _tick(orch).advanced[5]
    assert "policy re-check failed" in out or out.startswith("merge deferred")
    assert gh.merged == []


# ---------------------------------------------------------------------------------------------
# 2. regression policy: LOST default 0, explicit allowance, Opus approval, undeclared LOST fails
# ---------------------------------------------------------------------------------------------

def _ctx(**kw):
    c = {"footprint_width_m": 12.0, "footprint_depth_m": 14.0, "bedrooms": 3, "wet_rooms": 2, "safe_room": True, "open_plan": False}
    c.update(kw)
    return c


def _report(**overrides):
    base = {"before": {"planned": 404, "refused": 28, "crashes": 0, "total": 432},
            "after": {"planned": 403, "refused": 29, "crashes": 0, "total": 432},
            "lost": [], "gained": [], "crashes": [], "status_changes": [], "refusal_code_changes": [],
            "primary_signature_changes": [], "byte_identical_primaries": 403}
    base.update(overrides)
    return base


def test_undeclared_lost_always_fails_ci_and_declared_lost_passes():
    lost_big = {"context": _ctx(bedrooms=6), "after": "REFUSED", "after_code": "X"}
    lost_small = {"context": _ctx(bedrooms=3), "after": "REFUSED", "after_code": "X"}
    default_budget = {"LOST": "0", "GAINED": "allowed"}
    assert not gate4_evaluate(_report(lost=[lost_big]), default_budget).ok
    tagged = {"LOST": "tagged:bedrooms>=6", "GAINED": "allowed"}
    assert gate4_evaluate(_report(lost=[lost_big]), tagged).ok
    assert not gate4_evaluate(_report(lost=[lost_big, lost_small]), tagged).ok      # one outside the declaration
    numeric = {"LOST": "1"}
    assert gate4_evaluate(_report(lost=[lost_big]), numeric).ok
    assert not gate4_evaluate(_report(lost=[lost_big, lost_small]), numeric).ok
    # a missing LOST rule in the manifest is the strict default
    ev = evaluate_budget(_report(lost=[lost_big]), (parse_budget_value("GAINED", "allowed"),))
    assert not ev.ok and ev.violations[0].key == "LOST"


def test_lost_allowance_needs_medium_risk_and_explicit_opus_approval(env):
    config, gh, clock, _ = env
    c = make_contract(6, title="[agent] Task 6", risk="MEDIUM", resource="MEDIUM")
    body = render_body(c).replace("LOST: 0", "LOST: tagged:bedrooms>=6")
    gh.add_issue(6, c.title, body, ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)])
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(6)
    assert orch._contract(rec).lost_allowance
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch)
    out = _tick(orch).advanced[6]
    assert "lead_approval" in out and "lost_allowance" in out
    orch.store.add_approval(6, "lead_approval", "opus", "ok")
    assert "awaiting lost_allowance" in _tick(orch).advanced[6]
    orch.store.add_approval(6, "lost_allowance", "opus", "6-bedroom contexts are intentionally refused now")
    assert _tick(orch).advanced[6] == "REVIEW -> READY"


def test_low_risk_contract_with_lost_allowance_is_not_executable(env):
    config, gh, clock, _ = env
    c = make_contract(7, title="[agent] Task 7", risk="LOW")
    body = render_body(c).replace("LOST: 0", "LOST: 1")
    gh.add_issue(7, c.title, body, ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)])
    orch = _orch(config, gh, clock, FakeAgentRunner())
    _tick(orch)
    assert orch.store.get(7) is None and "agent:draft" in gh.issue_labels(7)
    assert any("requires Risk MEDIUM or HIGH" in cm[1] for cm in gh.comments if cm[0] == 7)


# ---------------------------------------------------------------------------------------------
# 3. verification types
# ---------------------------------------------------------------------------------------------

def test_verify_gate_defers_semantic_and_runs_static(tmp_path: Path):
    calls = []

    def fake_runner(kind, target, root):
        calls.append((kind, target))
        return verify.run_target(kind, target, root) if kind == "review" else (True, "fake")

    manifest = {"issue": 1, "acceptance_criteria": [{"id": "AC-1", "text": "t"}, {"id": "AC-2", "text": "t"}],
                "targets": [{"ac": "AC-1", "type": "STATIC", "kind": "static", "target": "backend-import"},
                            {"ac": "AC-2", "type": "SEMANTIC_REVIEW", "kind": "review", "target": "the wording is accurate"}]}
    rep = verify.evaluate(manifest, tmp_path, runner=fake_runner)
    by = {c["name"]: c for c in rep.checks}
    assert by["AC-1 -> static:backend-import"]["ok"]
    assert by["AC-2 -> review:the wording is accurate"]["ok"] and "deferred to gate-5" in by["AC-2 -> review:the wording is accurate"]["detail"]
    assert rep.ok
    ok, detail = verify.run_static("nope", tmp_path)
    assert not ok and "unknown static check" in detail


def test_semantic_review_ac_not_met_downgrades_an_approve(env):
    """A docs-only contract with one SEMANTIC_REVIEW criterion: the reviewer's APPROVE only counts
    when that criterion is MET; otherwise the orchestrator treats it as REQUEST_CHANGES."""
    config, gh, clock, _ = env
    c = make_contract(8, title="[agent] Task 8", domains="knowledge")
    body = render_body(c).replace("- AC-2 -> ARTIFACT:grep:backend/README.md:agentctl status",
                                  "- AC-2 -> review:the section explains when to run dry-run")
    gh.add_issue(8, c.title, body, ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)])
    verdict = {**APPROVE, "ac_assessment": [{"ac": "AC-1", "verdict": "MET", "note": ""}, {"ac": "AC-2", "verdict": "UNCLEAR", "note": "cannot tell"},
                                            {"ac": "AC-3", "verdict": "MET", "note": ""}]}
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": verdict})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(8)
    assert orch._contract(rec).semantic_review_acs == ("AC-2",)
    assert "Semantic criteria assigned to you" not in runner.calls[0].prompt      # worker prompt
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch)
    reviewer_prompt = [c for c in runner.calls if c.role == "reviewer"][-1].prompt
    assert "AC-2: the section explains when to run dry-run" in reviewer_prompt
    rec = orch.store.get(8)
    assert rec.state == sm.FIX_REQUIRED and rec.review_verdict == f"REQUEST_CHANGES@{head}"
    assert _statuses(gh, head) == "failure"
    ev = [e for e in orch.store.events(8) if e["kind"] == "review_verdict"][-1]
    assert ev["payload"]["semantic_unmet"] == ["AC-2"]
    # the same reviewer marking it MET is a real approval
    runner.script["reviewer"] = {**verdict, "ac_assessment": [{"ac": a, "verdict": "MET", "note": ""} for a in ("AC-1", "AC-2", "AC-3")]}
    _tick(orch); _tick(orch)                                 # repair -> PR_OPEN -> CI
    head2 = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head2)
    _tick(orch); _tick(orch)
    assert orch.store.get(8).review_verdict == f"APPROVE@{head2}" and _statuses(gh, head2) == "success"


# ---------------------------------------------------------------------------------------------
# 4. admin exemption is break-glass only: detect and log bypasses
# ---------------------------------------------------------------------------------------------

def test_external_merge_without_green_gates_is_recorded_as_bypass(env):
    config, gh, clock, _ = env
    _add_issue(gh, 9, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)                                 # PR open, in CI; nothing green yet
    rec = orch.store.get(9)
    pr = gh.get_pr(rec.pr_number)
    # an admin merges the PR by hand (branch protection exempts admins)
    pr["merged"] = True; pr["state"] = "closed"; pr["merge_commit_sha"] = "deadbeef"; pr["merged_by"] = {"login": "tzahibe"}
    rep = _tick(orch)
    assert any("merged externally -> BLOCKED" in a for a in rep.reconciled)
    events = {e["kind"]: e for e in orch.store.events(9)}
    assert "admin_bypass_detected" in events
    assert events["admin_bypass_detected"]["payload"]["bypass"] is True
    assert events["admin_bypass_detected"]["payload"]["merged_by"] == "tzahibe"
    assert events["admin_bypass_detected"]["payload"]["contexts"]["agent-ci-result"] == "missing"
    assert any("break-glass bypass" in c[1] for c in gh.comments if c[0] == 9)


def test_external_merge_with_green_gates_is_not_a_bypass(env):
    config, gh, clock, _ = env
    _add_issue(gh, 10, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(10)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch); _tick(orch)                    # READY with review success published
    pr = gh.get_pr(rec.pr_number)
    pr["merged"] = True; pr["state"] = "closed"; pr["merge_commit_sha"] = "cafe"
    _tick(orch)
    kinds = [e["kind"] for e in orch.store.events(10)]
    assert "merge_gate_audit" in kinds and "admin_bypass_detected" not in kinds
    assert orch.store.get(10).state in (sm.MERGED, sm.DONE, sm.BLOCKED)


def test_branch_protection_drift_is_audited(env):
    config, gh, clock, _ = env
    orch = _orch(config, gh, clock, FakeAgentRunner())
    gh.protection["main"] = {"required_status_checks": {"contexts": list(config.protection_required_contexts)}, "enforce_admins": {"enabled": False}}
    notes = orch.check_branch_protection()
    assert any("exempts admins" in n for n in notes) and not any("missing" in n for n in notes)
    assert [e["kind"] for e in orch.store.events(None, limit=10)][-1] == "protection_observed"
    gh.protection["main"]["required_status_checks"]["contexts"] = ["agent-ci-result"]     # someone dropped the review status
    notes = orch.check_branch_protection()
    assert any("changed" in n for n in notes) and any("missing required contexts ['agent-review-result']" in n for n in notes)
    assert any(e["kind"] == "protection_drift" for e in orch.store.events(None, limit=10))
    gh.protection.pop("main")
    assert any("NOT protected" in n for n in orch.check_branch_protection())
    rep = _tick(orch)                                        # reconciliation surfaces the defect every tick
    assert any("NOT protected" in a for a in rep.reconciled)


def test_protect_main_records_break_glass_note(env, capsys):
    from agent_team import cli
    config, gh, clock, _ = env
    cli._github = lambda cfg, require_auth=True: gh   # type: ignore[assignment]
    args = type("A", (), {"show": False, "enforce_admins": False})()
    assert cli.cmd_protect_main(config, args) == 0
    out = capsys.readouterr().out
    assert "enforce_admins=False" in out and "break-glass only" in out
    assert gh.protection["main"]["required_status_checks"]["contexts"] == ["agent-ci-result", "agent-review-result"]
    from agent_team.state_store import StateStore
    events = StateStore(config.state_db_path).events(None, limit=5)
    assert events[-1]["kind"] == "protection_set" and events[-1]["payload"]["enforce_admins"] is False
