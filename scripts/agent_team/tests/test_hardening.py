"""Hardening behaviors: enforceable review status, LOST allowance policy, verification types,
break-glass detection. Same fakes as the lifecycle tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_team import cli
from agent_team import state_machine as sm
from agent_team.agent_runner import FakeAgentRunner
from agent_team.ci import verify
from agent_team.ci.regression_gate import evaluate as gate4_evaluate
from agent_team.github_client import FakeGitHub
from agent_team.issue_contract import numbered_title, parse_budget_value, render_body
from agent_team.labels import metadata_labels
from agent_team.regression_budget import evaluate as evaluate_budget
from agent_team.tests.helpers import KNOWN_LOCKS, make_contract
from agent_team.tests.test_orchestrator_lifecycle import APPROVE, _add_issue, _git, _green, _orch, _owner_merge, _red, _tick, _worker_that_commits, env  # noqa: F401

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
    assert _tick(orch).advanced[1] == "REVIEW -> READY_FOR_OWNER"
    assert _owner_merge(orch, 1)["result"] == "SUCCESS"      # GitHub (fake protection) let it through
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


def test_owner_merge_refused_until_github_shows_every_required_context(env):
    """Never merge through the admin exemption: if GitHub does not show the review status green,
    the owner's merge is refused (and the status re-published from the store) — never forced."""
    config, gh, clock, _ = env
    _add_issue(gh, 4, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(4)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch); _tick(orch)
    assert orch.store.get(4).state == sm.READY_FOR_OWNER
    gh.statuses[head].pop(REVIEW_CTX)
    real_set = gh.set_commit_status
    gh.set_commit_status = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("github down"))
    res = _owner_merge(orch, 4)
    assert res["result"] == "REFUSED" and "gates not green" in res["reason"] and REVIEW_CTX + "=missing" in res["reason"]
    assert gh.merged == [] and orch.store.get(4).state == sm.READY_FOR_OWNER
    assert any(e["kind"] == "owner_merge_refused" for e in orch.store.events(4))
    gh.set_commit_status = real_set
    assert _owner_merge(orch, 4)["result"] == "SUCCESS"     # re-published from the store, then merged
    assert _statuses(gh, head) == "success"


def test_ci_check_missing_on_github_refuses_owner_merge(env):
    config, gh, clock, _ = env
    _add_issue(gh, 5, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(5)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch); _tick(orch)
    assert orch.store.get(5).state == sm.READY_FOR_OWNER
    gh.checks[head] = [c for c in gh.checks[head] if c["name"] != "agent-ci-result"]   # aggregate check vanished
    res = _owner_merge(orch, 5)
    assert res["result"] == "REFUSED" and "gates not green" in res["reason"]
    assert gh.merged == [] and orch.store.get(5).state == sm.READY_FOR_OWNER


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


def test_lost_allowance_needs_medium_risk_and_explicit_acknowledgement(env):
    config, gh, clock, _ = env
    c = make_contract(6, title="[agent] Task 6", risk="MEDIUM", resource="MEDIUM")
    body = render_body(c).replace("LOST: 0", "LOST: tagged:bedrooms>=6")
    gh.add_issue(6, c.title, body, ["agent:queued", "owner:approved", *metadata_labels(c.domains, c.risk, c.resource_class)])
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(6)
    assert orch._contract(rec).lost_allowance
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch)
    out = _tick(orch).advanced[6]
    assert "awaiting lost_allowance" in out and "lead_approval" not in out
    orch.store.add_approval(6, "lost_allowance", "opus", "6-bedroom contexts are intentionally refused now")
    assert _tick(orch).advanced[6] == "REVIEW -> READY_FOR_OWNER"


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
    gh.add_issue(8, c.title, body, ["agent:queued", "owner:approved", *metadata_labels(c.domains, c.risk, c.resource_class)])
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
# 3b. reviewer integration: architectural reference, overfits_one_plan, red-gate authority
# ---------------------------------------------------------------------------------------------

def test_overfit_verdict_is_downgraded(env):
    """A geometry/validator/backend PR gets the architectural reference block (rubric + anti-pattern
    library + the six questions); an APPROVE that marks overfits_one_plan True is downgraded by the
    orchestrator before it reaches GitHub, exactly like an unmet SEMANTIC_REVIEW AC."""
    config, gh, clock, _ = env
    c = make_contract(11, title="[agent] Task 11", domains="geometry")
    gh.add_issue(11, c.title, render_body(c), ["agent:queued", "owner:approved", *metadata_labels(c.domains, c.risk, c.resource_class)])
    overfit = {**APPROVE, "overfits_one_plan": True,
               "architectural_assessment": {"A. Room Proportion & Aspect Ratio": "only fixes the repro context"}}
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": overfit})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(11)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch)
    reviewer_prompt = [call for call in runner.calls if call.role == "reviewer"][-1].prompt
    assert "quality_rubric.md" in reviewer_prompt and "anti_patterns.md" in reviewer_prompt and "overfitting" in reviewer_prompt
    rec = orch.store.get(11)
    assert rec.state == sm.FIX_REQUIRED and rec.review_verdict == f"REQUEST_CHANGES@{head}"
    assert _statuses(gh, head) == "failure"
    ev = [e for e in orch.store.events(11) if e["kind"] == "review_verdict"][-1]
    assert ev["payload"]["overfits_one_plan"] is True
    # a domain outside geometry/validator/backend does not get the elaborated block
    c2 = make_contract(12, title="[agent] Task 12", domains="knowledge")
    gh.add_issue(12, c2.title, render_body(c2), ["agent:queued", "owner:approved", *metadata_labels(c2.domains, c2.risk, c2.resource_class)])
    runner2 = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch2 = _orch(config, gh, clock, runner2)
    _tick(orch2); _tick(orch2)
    rec2 = orch2.store.get(12)
    head2 = gh.get_pr(rec2.pr_number)["head"]["sha"]
    _green(gh, head2)
    _tick(orch2); _tick(orch2)
    reviewer_prompt2 = [call for call in runner2.calls if call.role == "reviewer"][-1].prompt
    assert "do not include geometry, validator or backend" in reviewer_prompt2
    assert "A–O quality rubric" not in reviewer_prompt2                   # the elaborated block is domain-gated
    assert orch2.store.get(12).review_verdict == f"APPROVE@{head2}"       # overfits_one_plan False: a real approval


def test_review_never_overrides_a_red_gate(env):
    """A red CI gate keeps the PR out of REVIEW and merge regardless of what a reviewer would say
    — the reviewer never even runs — and merge_policy.decide() refuses on ci_green alone even when
    an APPROVE is recorded for the exact head SHA."""
    config, gh, clock, _ = env
    _add_issue(gh, 13, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)                                  # -> PR_OPEN -> CI
    rec = orch.store.get(13)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _red(gh, head)
    assert _tick(orch).advanced[13] == "CI -> FIX_REQUIRED (IMPLEMENTATION_FAILURE)"
    assert not [call for call in runner.calls if call.role == "reviewer"]     # the review never ran
    assert orch.store.get(13).review_verdict is None
    assert _statuses(gh, head) != "success"

    from agent_team import merge_policy
    from agent_team.ci_evidence import CiEvidence, FAILURE
    orch.store.update(13, review_verdict=f"APPROVE@{head}")                   # simulate a recorded APPROVE anyway
    rec = orch.store.get(13)
    ev = CiEvidence(head_sha=head, status=FAILURE, checks={"agent-ci-result": {"status": "completed", "conclusion": "failure"}},
                     statuses={"agent-review-result": {"state": "success"}})
    d = merge_policy.decide(rec, ev, config, review_sha=head)
    assert "reviewer_green" in d.satisfied                                    # the review itself checks out
    assert not d.ok and "ci_green" in d.missing                               # but the red gate still blocks the merge


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
    _tick(orch); _tick(orch); _tick(orch)                    # READY_FOR_OWNER with review success published
    gh.merge_pr(rec.pr_number)                               # the owner pressed Merge on GitHub (gates green)
    _tick(orch)                                              # reconciliation sees the owner's merge -> smoke
    kinds = [e["kind"] for e in orch.store.events(10)]
    assert "merge_gate_audit" in kinds and "admin_bypass_detected" not in kinds
    assert orch.store.get(10).state in (sm.MERGED, sm.DONE)
    assert any(e["kind"] == "transition" and e["payload"].get("to") == "MERGED" and "owner on GitHub" in e["payload"].get("note", "")
               for e in orch.store.events(10))


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


# ---------------------------------------------------------------------------------------------
# 5. Issue titles carry their own number (#25)
# ---------------------------------------------------------------------------------------------

def test_update_issue_patches_title():
    gh = FakeGitHub()
    gh.add_issue(24, "[agent] Old title", "body", ["agent:working"])
    gh.update_issue(24, title="[agent] #24 New title")
    assert gh.get_issue(24)["title"] == "[agent] #24 New title"
    assert gh.get_issue(24)["body"] == "body"                # body untouched: only the given field is patched


def test_renumber_titles_idempotent(env, capsys):  # noqa: F811
    config, gh, _, _ = env
    gh.add_issue(17, "[agent] Unnumbered title", "b", ["agent:working"])
    gh.add_issue(18, "[agent] #18 Already numbered", "b", ["agent:queued"])
    gh.add_issue(19, "[agent] #5 Stale number", "b", ["agent:blocked"])
    gh.add_issue(20, "Not an agent issue", "b", [])
    cli._github = lambda c, require_auth=True: gh   # type: ignore[assignment]

    args = type("A", (), {"issue_cmd": "renumber-titles", "dry_run": True, "all_states": False})()
    assert cli.cmd_issue(config, args) == 0
    out = capsys.readouterr().out
    assert "#17: '[agent] Unnumbered title' -> '[agent] #17 Unnumbered title'" in out
    assert "#19: '[agent] #5 Stale number' -> '[agent] #19 Stale number'" in out
    assert "#18" not in out and "#20" not in out
    assert gh.get_issue(17)["title"] == "[agent] Unnumbered title"    # --dry-run touched nothing

    args = type("A", (), {"issue_cmd": "renumber-titles", "dry_run": False, "all_states": False})()
    assert cli.cmd_issue(config, args) == 0
    assert gh.get_issue(17)["title"] == numbered_title(17, "Unnumbered title")
    assert gh.get_issue(18)["title"] == "[agent] #18 Already numbered"    # untouched
    assert gh.get_issue(19)["title"] == numbered_title(19, "Stale number")
    assert gh.get_issue(20)["title"] == "Not an agent issue"              # untouched: no agent label

    capsys.readouterr()
    assert cli.cmd_issue(config, args) == 0                     # second run: no further changes
    assert "no titles need renumbering" in capsys.readouterr().out


def test_renumber_titles_all_states(env, capsys):  # noqa: F811
    config, gh, _, _ = env
    gh.add_issue(21, "[agent] Closed unnumbered title", "b", ["agent:done"], state="closed")
    cli._github = lambda c, require_auth=True: gh   # type: ignore[assignment]

    args = type("A", (), {"issue_cmd": "renumber-titles", "dry_run": False, "all_states": False})()
    assert cli.cmd_issue(config, args) == 0
    assert gh.get_issue(21)["title"] == "[agent] Closed unnumbered title"    # closed, not touched without --all-states

    args = type("A", (), {"issue_cmd": "renumber-titles", "dry_run": False, "all_states": True})()
    assert cli.cmd_issue(config, args) == 0
    assert gh.get_issue(21)["title"] == numbered_title(21, "Closed unnumbered title")    # --all-states covers it


def test_cli_issue_create_numbers_title(env, tmp_path, capsys):  # noqa: F811
    config, gh, _, _ = env
    cli._github = lambda c, require_auth=True: gh   # type: ignore[assignment]
    c = make_contract(0, title="[agent] Work reports and structured failure recovery")
    contract_file = tmp_path / "contract.md"
    contract_file.write_text(f"# {c.title}\n\n{render_body(c)}")
    args = type("A", (), {"issue_cmd": "create", "from_file": str(contract_file), "title": None, "queue": False})()
    assert cli.cmd_issue(config, args) == 0
    issue = gh.get_issue(gh.next_number - 1)
    assert issue["title"] == numbered_title(issue["number"], "Work reports and structured failure recovery")
    assert f"title={issue['title']!r}" in capsys.readouterr().out
