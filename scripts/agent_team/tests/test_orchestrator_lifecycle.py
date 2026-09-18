"""End-to-end orchestration over fakes: FakeGitHub + FakeAgentRunner + a real temp git origin."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from agent_team import state_machine as sm
from agent_team.agent_runner import AgentRunResult, FakeAgentRunner
from agent_team.config import load_config
from agent_team.github_client import FakeGitHub
from agent_team.issue_contract import render_body
from agent_team.labels import metadata_labels
from agent_team.orchestrator import Orchestrator, OrchestratorAlreadyRunning
from agent_team.resource_manager import FakeProbe
from agent_team.tests.conftest import CONFIG_PATH
from agent_team.tests.helpers import make_contract


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path: Path):
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-q", "--initial-branch=main", str(origin)], tmp_path)
    root = tmp_path / "repo"
    _git(["clone", "-q", str(origin), str(root)], tmp_path)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "tester"], root)
    (root / ".agent").mkdir()
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    raw["commands"]["worktree_setup"] = {"always": []}
    raw["commands"]["smoke"] = [{"cwd": ".", "cmd": "test -f README.md"}]
    raw["resources"]["probe_window_seconds"] = 0
    (root / ".agent" / "config.yaml").write_text(yaml.safe_dump(raw))
    (root / "README.md").write_text("hello\n")
    _git(["add", "."], root)
    _git(["commit", "-q", "-m", "init"], root)
    _git(["push", "-q", "-u", "origin", "main"], root)
    config = load_config(repo_root=root)
    gh = FakeGitHub(repo=config.repo)

    def real_merge(pr):
        """Fast-forward the PR branch into the temp origin's main, like GitHub would."""
        _git(["fetch", "-q", "origin"], root)
        _git(["push", "-q", "origin", f"origin/{pr['head']['ref']}:main"], root)
        _git(["fetch", "-q", "origin"], root)
        return _git(["rev-parse", "origin/main"], root).stdout.strip()

    def real_head(branch):
        out = _git(["ls-remote", "--heads", str(origin), branch], root).stdout.split()
        return out[0] if out else None

    gh.on_merge = real_merge
    gh.on_head_sha = real_head
    clock = Clock()
    return config, gh, clock, origin


def _worker_that_commits(report_overrides=None):
    def run(spec):
        p = Path(spec.cwd) / f"work-{spec.issue_id}.txt"
        p.write_text(p.read_text() + "x\n" if p.exists() else "work\n")
        _git(["add", "-A"], spec.cwd)
        _git(["commit", "-q", "-m", f"feat: work for #{spec.issue_id} attempt {spec.attempt}"], spec.cwd)
        report = {"status": "done", "summary": "did the thing", "what_changed": ["added work file"], "why": "asked",
                  "implementation": "wrote file", "ac_evidence": [{"ac": "AC-1", "evidence": "grep", "result": "PASS"}],
                  "tests_run": [{"command": "pytest", "result": "1 passed"}], "regression": "n/a", "known_limitations": [],
                  "files_changed": [f"work-{spec.issue_id}.txt"], "blockers": []}
        report.update(report_overrides or {})
        return report
    return run


APPROVE = {"verdict": "APPROVE", "summary": "fine", "ac_assessment": [{"ac": "AC-1", "verdict": "MET", "note": ""}], "findings": [],
           "unrelated_changes": False, "hidden_behavior_changes": False, "tolerance_hacks": False, "silent_fallback": False,
           "tests_meaningful": True, "architecture_appropriate": True, "architectural_assessment": {}, "overfits_one_plan": False}


def _add_issue(gh: FakeGitHub, number: int, approved: bool = True, **kw):
    """A queued Issue. `approved=True` adds the owner's label — without it nothing may execute."""
    c = make_contract(number, title=f"[agent] Task {number}", **kw)
    labels = ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)] + (["owner:approved"] if approved else [])
    gh.add_issue(number, c.title, render_body(c), labels)
    return c


def _owner_merge(orch, issue_id: int, sha: str | None = None, **kw):
    rec = orch.store.get(issue_id)
    return orch.owner_merge(issue_id, sha or rec.validated_commit, source=kw.get("source", "test-owner"), owner_id=kw.get("owner_id", 1),
                            command_id=kw.get("command_id", f"cmd-{issue_id}-{sha or rec.validated_commit}"))


def _green(gh: FakeGitHub, sha: str):
    gh.checks[sha] = [{"id": 1, "name": "gate-1-contract / contract", "status": "completed", "conclusion": "success"},
                      {"id": 2, "name": "gate-2-static", "status": "completed", "conclusion": "success"},
                      {"id": 3, "name": "gate-3-verification", "status": "completed", "conclusion": "success"},
                      {"id": 4, "name": "agent-ci-result", "status": "completed", "conclusion": "success"}]


def _red(gh: FakeGitHub, sha: str, gate="gate-3-verification"):
    gh.checks[sha] = [{"id": 1, "name": "gate-1-contract / contract", "status": "completed", "conclusion": "success"},
                      {"id": 2, "name": "gate-2-static", "status": "completed", "conclusion": "success"},
                      {"id": 3, "name": gate, "status": "completed", "conclusion": "failure"},
                      {"id": 4, "name": "agent-ci-result", "status": "completed", "conclusion": "failure"}]


def _orch(config, gh, clock, runner, **kw):
    return Orchestrator(config, github=gh, runner=runner, probe=FakeProbe(), clock=clock, **kw)


def _tick(orch):
    rep = orch.tick()
    orch.wait_for_threads(timeout=30)
    return rep


def test_happy_path_low_risk_ends_at_ready_for_owner_then_owner_merges(env):
    config, gh, clock, origin = env
    _add_issue(gh, 1, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)

    rep = _tick(orch)                                   # poll + claim + worker -> PR_OPEN
    assert rep.polled == [1] and rep.started == [1]
    rec = orch.store.get(1)
    assert rec.state == sm.PR_OPEN and rec.pr_number and rec.branch == "agent/1-task-1"
    assert gh.issue_labels(1).count("agent:pr-open") == 1
    assert "Closes #1" in gh.prs[rec.pr_number]["body"] and "| AC-1 |" in gh.prs[rec.pr_number]["body"]
    assert _git(["ls-remote", "--heads", str(origin), "agent/1-task-1"], config.repo_root).stdout.strip()

    _tick(orch)                                         # PR_OPEN -> CI
    assert orch.store.get(1).state == sm.CI
    assert "CI pending" in _tick(orch).advanced[1]      # no checks yet
    sha = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, sha)
    assert _tick(orch).advanced[1] == "CI -> REVIEW"
    assert _tick(orch).advanced[1] == "review started"  # reviewer thread ran and approved
    assert orch.store.get(1).review_verdict == f"APPROVE@{sha}"
    assert any(r[0] == rec.pr_number and r[1] == "COMMENT" for r in gh.reviews)
    assert _tick(orch).advanced[1] == "REVIEW -> READY_FOR_OWNER"
    # the orchestrator never merges: ticks leave it waiting, with the READY report + notification queued once
    for _ in range(3):
        assert _tick(orch).advanced[1] == "awaiting owner"
    assert gh.merged == [] and orch.store.get(1).state == sm.READY_FOR_OWNER
    assert "agent:ready-for-owner" in gh.issue_labels(1)
    assert any("READY FOR OWNER" in c[1] and "Opus recommendation" in c[1] for c in gh.comments if c[0] == 1)
    assert orch.store.notification(f"pr:{rec.pr_number}:READY_FOR_OWNER:{sha}") is not None
    # explicit owner merge command
    res = _owner_merge(orch, 1)
    assert res["result"] == "SUCCESS" and res["actual_validated_sha"] == sha and gh.merged == [rec.pr_number]
    assert orch.store.get(1).state == sm.MERGED
    assert _tick(orch).advanced[1] == "smoke started"
    final = orch.store.get(1)
    assert final.state == sm.DONE and gh.issues[1]["state"] == "closed"
    assert orch.store.locks_held() == []
    assert not Path(final.worktree).exists()
    assert "agent/1-task-1" in gh.deleted_branches
    kinds = [e["kind"] for e in orch.store.events(1)]
    for k in ("tracked", "locks_acquired", "agent_run", "worker_report", "review_verdict", "merged", "smoke", "done"):
        assert k in kinds, kinds
    assert any("Done." in c[1] for c in gh.comments if c[0] == 1)


def test_medium_and_high_risk_end_at_ready_for_owner_and_never_auto_merge(env):
    config, gh, clock, _ = env
    _add_issue(gh, 2, risk="MEDIUM", resource="MEDIUM")
    _add_issue(gh, 3, risk="HIGH", resource="MEDIUM", domains="qa", locks="none")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    for n in (2, 3):
        rec = orch.store.get(n)
        _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    for _ in range(7):                                        # one reviewer slot: reviews run one after the other
        _tick(orch)
    assert gh.merged == [] and {orch.store.get(n).state for n in (2, 3)} == {sm.READY_FOR_OWNER}
    for risk in ("LOW", "MEDIUM", "HIGH"):
        assert config.risk_policy[risk].auto_merge is False


def test_ci_failure_repairs_then_blocks_after_budget(env):
    config, gh, clock, _ = env
    _add_issue(gh, 3, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(3)
    sha = gh.get_pr(rec.pr_number)["head"]["sha"]
    _red(gh, sha)
    assert _tick(orch).advanced[3] == "CI -> FIX_REQUIRED (IMPLEMENTATION_FAILURE)"
    assert orch.store.get(3).failure_class == "IMPLEMENTATION_FAILURE"
    assert any("classified **IMPLEMENTATION_FAILURE**" in c[1] for c in gh.comments if c[0] == 3)
    assert _tick(orch).advanced[3] == "FIX_REQUIRED -> WORKING (repair)"
    rec = orch.store.get(3)
    assert rec.state == sm.PR_OPEN and rec.attempt_number == 2
    repair_spec = runner.calls[-1]
    assert "repair attempt 1 of 2" in repair_spec.prompt and repair_spec.resume_session_id == "fake-worker-3-1"
    _tick(orch)                                          # -> CI
    _red(gh, gh.get_pr(rec.pr_number)["head"]["sha"])     # the repair push moved the head; CI red again
    assert _tick(orch).advanced[3] == "CI -> FIX_REQUIRED (IMPLEMENTATION_FAILURE)"
    _tick(orch)                                          # second repair -> PR_OPEN (attempt 3)
    assert orch.store.get(3).attempt_number == 3
    _tick(orch)                                          # -> CI
    _red(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    assert _tick(orch).advanced[3] == "CI -> BLOCKED (IMPLEMENTATION_FAILURE)"
    assert orch.store.get(3).state == sm.BLOCKED and orch.store.locks_held() == []
    assert gh.issue_labels(3).count("agent:blocked") == 1


def test_reviewer_request_changes_and_block(env):
    config, gh, clock, _ = env
    _add_issue(gh, 4, risk="LOW")
    reject = {**APPROVE, "verdict": "REQUEST_CHANGES", "summary": "test is tautological", "tests_meaningful": False}
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": reject})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(4)
    _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch); _tick(orch)
    assert orch.store.get(4).state == sm.FIX_REQUIRED and orch.store.get(4).failure_class == "REVIEW_REJECTED"
    assert any(r[1] == "REQUEST_CHANGES" for r in gh.reviews)
    runner.script["reviewer"] = {**APPROVE, "verdict": "BLOCK", "summary": "hidden behavior change", "hidden_behavior_changes": True}
    _tick(orch)                                          # repair -> PR_OPEN
    _tick(orch)                                          # -> CI
    _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])   # new head after the repair push
    _tick(orch)                                          # -> REVIEW
    _tick(orch)                                          # reviewer BLOCK
    assert orch.store.get(4).state == sm.BLOCKED


def test_duplicate_polling_never_starts_twice(env):
    config, gh, clock, _ = env
    _add_issue(gh, 5, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)
    gh.add_labels(5, ["agent:queued"])                  # someone re-adds the label by hand
    rep = _tick(orch)
    assert rep.polled == [] and rep.started == []
    assert len([c for c in runner.calls if c.role == "worker"]) == 1
    assert len(orch.worktrees.agent_worktrees()) == 1
    # reconciliation repairs the label drift
    assert gh.issue_labels(5).count("agent:queued") == 0


def test_dependency_gates_scheduling(env):
    config, gh, clock, _ = env
    _add_issue(gh, 10, risk="LOW")
    _add_issue(gh, 11, risk="LOW", deps="#10")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    rep = _tick(orch)
    assert rep.started == [10] and "waiting for #10" in rep.waiting[11]


def test_lock_conflict_serializes_issues(env):
    config, gh, clock, _ = env
    _add_issue(gh, 20, risk="LOW", locks="planner-core (exclusive)")
    _add_issue(gh, 21, risk="LOW", locks="planner-core (exclusive)")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    rep = _tick(orch)
    assert rep.started == [20] and "planner-core(exclusive) held by #20" in rep.waiting[21]
    assert [l.issue_id for l in orch.store.locks_held()] == [20]


def test_worker_blocked_status_blocks_issue(env):
    config, gh, clock, _ = env
    _add_issue(gh, 6, risk="LOW")
    blocked = _worker_that_commits({"status": "needs_decision", "summary": "spec ambiguous", "blockers": ["which wall?"]})
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": blocked}))
    _tick(orch)
    rec = orch.store.get(6)
    assert rec.state == sm.BLOCKED and rec.failure_class == "NEEDS_DECISION"
    assert any("which wall?" in c[1] for c in gh.comments)


def test_worker_crash_requeues_then_blocks(env):
    config, gh, clock, _ = env
    _add_issue(gh, 7, risk="LOW")
    runner = FakeAgentRunner(script={"worker": AgentRunResult(ok=False, exit_code=1, error="boom")})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)
    assert orch.store.get(7).state == sm.QUEUED and orch.store.get(7).attempt_number == 1
    _tick(orch)
    assert orch.store.get(7).state == sm.QUEUED and orch.store.get(7).attempt_number == 2
    _tick(orch)
    assert orch.store.get(7).state == sm.BLOCKED
    assert len(orch.worktrees.agent_worktrees()) == 1   # reconciled, never duplicated


def test_invalid_contract_goes_back_to_draft(env):
    config, gh, clock, _ = env
    gh.add_issue(8, "[agent] Broken", "### Goal\n\nno other sections\n", ["agent:queued"])
    orch = _orch(config, gh, clock, FakeAgentRunner())
    rep = _tick(orch)
    assert rep.polled == [] and orch.store.get(8) is None
    assert "agent:draft" in gh.issue_labels(8) and "agent:queued" not in gh.issue_labels(8)
    assert any("does not validate" in c[1] for c in gh.comments if c[0] == 8)


def test_untrusted_author_is_ignored(env):
    config, gh, clock, _ = env
    c = make_contract(9, title="[agent] Task 9")
    gh.add_issue(9, c.title, render_body(c), ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)], author_association="NONE")
    orch = _orch(config, gh, clock, FakeAgentRunner())
    rep = _tick(orch)
    assert rep.polled == [] and orch.store.get(9) is None


def test_restart_reconciles_stale_worker_without_duplicating(env):
    config, gh, clock, _ = env
    _add_issue(gh, 12, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)
    rec = orch.store.get(12)
    # simulate a crash mid-run: force the row back into WORKING with a dead pid and an old heartbeat
    orch.store.transition(12, sm.CI)  # (get it into a state from which we can rewrite fields)
    orch.store._conn.execute("UPDATE issues SET state='WORKING', agent_pid=999999, heartbeat_at=? WHERE issue_id=12", (clock() - 10_000,))
    orch.store.try_acquire_locks(12, [("docs", "shared")])
    orch.shutdown()

    orch2 = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    rep = _tick(orch2)
    assert any("stale WORKING -> QUEUED" in a for a in rep.reconciled)
    assert rep.started == [12]                             # resumed in the same tick, same worktree
    assert len(orch2.worktrees.agent_worktrees()) == 1
    assert orch2.store.get(12).state in (sm.PR_OPEN, sm.CI) and orch2.store.get(12).pr_number == rec.pr_number  # PR reused, not duplicated
    assert len(gh.prs) == 1


def test_singleton_lock_prevents_two_orchestrators(env):
    config, gh, clock, _ = env
    a = _orch(config, gh, clock, FakeAgentRunner())
    a.acquire_singleton()
    b = _orch(config, gh, clock, FakeAgentRunner())
    with pytest.raises(OrchestratorAlreadyRunning):
        b.acquire_singleton()
    a.release_singleton()
    b.acquire_singleton()
    b.release_singleton()


def test_dry_run_makes_no_side_effects(env):
    config, gh, clock, _ = env
    _add_issue(gh, 13, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits()})
    orch = _orch(config, gh, clock, runner, dry_run=True)
    rep = _tick(orch)
    assert rep.polled == [13] and rep.started == [13]
    assert runner.calls == [] and gh.comments == [] and gh.prs == {}
    assert "agent:queued" in gh.issue_labels(13)
    assert orch.worktrees.agent_worktrees() == []
    assert orch.store.path.name == "dry-run.sqlite3"


def test_base_advanced_at_ready_revalidates(env):
    config, gh, clock, origin = env
    _add_issue(gh, 14, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(14)
    sha = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, sha)
    _tick(orch); _tick(orch); _tick(orch)
    assert orch.store.get(14).state == sm.READY_FOR_OWNER
    other = config.repo_root.parent / "other"
    _git(["clone", "-q", str(origin), str(other)], config.repo_root.parent)
    _git(["config", "user.email", "o@example.com"], other)
    _git(["config", "user.name", "other"], other)
    (other / "other.txt").write_text("o")
    _git(["add", "."], other); _git(["commit", "-q", "-m", "other"], other); _git(["push", "-q", "origin", "main"], other)
    assert _tick(orch).advanced[14] == "READY_FOR_OWNER -> CI (base advanced, readiness invalidated)"
    assert (Path(rec.worktree) / "other.txt").exists()
    assert any("Readiness for" in c[1] and "invalidated" in c[1] for c in gh.comments if c[0] == 14)


def test_ci_timeout_reruns_once_then_blocks(env):
    config, gh, clock, _ = env
    _add_issue(gh, 15, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    clock.t += config.ci_wait_seconds + 1
    out = _tick(orch).advanced[15]
    assert out == "CI -> BLOCKED (INFRA_FAILURE)"      # nothing to rerun (no runs) -> blocked, not repaired
    assert orch.store.get(15).failure_class == "INFRA_FAILURE"


def test_status_renders(env):
    from agent_team.status import render
    config, gh, clock, _ = env
    _add_issue(gh, 16, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits()}))
    _tick(orch)
    text = render(config, orch.store, orch.resources, probe_machine=False, now=clock())
    assert "RUNNING" in text and "#16 PR #" in text and f"workers 0/{config.max_worker_agents}" in text
    assert "ROOT ISSUES" in text and "AVAILABLE WORKERS" in text and f"{config.max_worker_agents} / {config.max_worker_agents}" in text
    assert "RESOURCES" in text and f"weighted capacity 0 / {config.weighted_capacity}" in text and "BLOCKERS" in text
