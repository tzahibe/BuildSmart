"""AC-1..AC-4: failure_record events, the per-Issue work report, `agentctl report`/`audit`, and the
fixed failure-milestone template. Same fake-GitHub + fake-runner + temp-git-origin harness as
`test_orchestrator_lifecycle.py`."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from agent_team import state_machine as sm
from agent_team.agent_runner import AgentRunResult, FakeAgentRunner
from agent_team.cli import cmd_audit, cmd_report
from agent_team.config import load_config
from agent_team.github_client import FakeGitHub
from agent_team.issue_contract import render_body
from agent_team.labels import metadata_labels
from agent_team.orchestrator import Orchestrator
from agent_team.resource_manager import FakeProbe
from agent_team.state_store import StateStore
from agent_team.tests.conftest import CONFIG_PATH
from agent_team.tests.helpers import make_contract
from agent_team.work_reports import FAILURE_TEMPLATE, report_path


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
    clock = Clock()
    return config, gh, clock


def _worker_that_commits(report_overrides=None):
    def run(spec):
        p = Path(spec.cwd) / f"work-{spec.issue_id}.txt"
        p.write_text(p.read_text() + "x\n" if p.exists() else "work\n")
        _git(["add", "-A"], spec.cwd)
        _git(["commit", "-q", "-m", f"feat: work for #{spec.issue_id} attempt {spec.attempt}"], spec.cwd)
        report = {"status": "done", "summary": "did the thing", "what_changed": ["added work file"], "why": "asked",
                  "implementation": "wrote file", "ac_evidence": [{"ac": "AC-1", "evidence": "grep", "result": "PASS"}],
                  "tests_run": [{"command": "pytest", "result": "1 passed"}], "regression": "n/a", "known_limitations": ["none yet"],
                  "files_changed": [f"work-{spec.issue_id}.txt"], "blockers": []}
        report.update(report_overrides or {})
        return report
    return run


APPROVE = {"verdict": "APPROVE", "summary": "fine", "ac_assessment": [{"ac": "AC-1", "verdict": "MET", "note": ""}], "findings": [],
           "unrelated_changes": False, "hidden_behavior_changes": False, "tolerance_hacks": False, "silent_fallback": False,
           "tests_meaningful": True, "architecture_appropriate": True}


def _add_issue(gh: FakeGitHub, number: int, **kw):
    c = make_contract(number, title=f"[agent] Task {number}", **kw)
    gh.add_issue(number, c.title, render_body(c), ["agent:queued", *metadata_labels(c.domains, c.risk, c.resource_class)])
    return c


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


def _failure_events(store: StateStore, issue_id: int) -> list[dict]:
    return [e for e in store.events(issue_id) if e["kind"] == "failure_record"]


# -- AC-1: one failure_record event per failure transition --------------------------------------

def test_failure_record_event_on_worker_ci_and_blocked_failures(env):
    config, gh, clock = env

    # (a) a worker run crash
    _add_issue(gh, 1, risk="LOW")
    runner = FakeAgentRunner(script={"worker": AgentRunResult(ok=False, exit_code=1, error="boom")})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)
    events = _failure_events(orch.store, 1)
    assert len(events) == 1, events
    p = events[0]["payload"]
    assert p["stage"] == "worker" and p["failure_class"] == "WORKER_FAILED" and p["attempt"] == 1
    assert "boom" in p["root_cause"] and p["evidence_ref"] and p["next_action"] == "requeue"
    assert p["attempts_left"] >= 1

    # (b) a CI red run
    _add_issue(gh, 2, risk="LOW")
    runner2 = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch2 = _orch(config, gh, clock, runner2)
    _tick(orch2); _tick(orch2)
    rec = orch2.store.get(2)
    _red(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch2)
    events2 = _failure_events(orch2.store, 2)
    assert len(events2) == 1, events2
    p2 = events2[0]["payload"]
    assert p2["stage"] == "ci" and p2["failure_class"] == "IMPLEMENTATION_FAILURE" and p2["attempt"] == 1
    assert p2["evidence_ref"] and p2["next_action"] == "repair"

    # (c) a blocked worker report (needs_decision)
    _add_issue(gh, 3, risk="LOW")
    blocked = _worker_that_commits({"status": "needs_decision", "summary": "spec ambiguous", "blockers": ["which wall?"]})
    orch3 = _orch(config, gh, clock, FakeAgentRunner(script={"worker": blocked}))
    _tick(orch3)
    events3 = _failure_events(orch3.store, 3)
    assert len(events3) == 1, events3
    p3 = events3[0]["payload"]
    assert p3["stage"] == "worker" and p3["failure_class"] == "NEEDS_DECISION" and p3["next_action"] == "blocked"
    assert "spec ambiguous" in p3["root_cause"]


# -- AC-2: the per-Issue report is regenerated with work + failure history -----------------------

def test_issue_report_regenerated_with_work_and_failure_history(env):
    config, gh, clock = env
    _add_issue(gh, 4, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(4)
    path = report_path(config, 4)
    assert path.exists()          # written on the very first state change

    _red(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch)                    # CI -> FIX_REQUIRED (one failure_record)
    _tick(orch)                    # repair -> PR_OPEN (a second worker_report)
    rec = orch.store.get(4)
    _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch); _tick(orch)       # -> REVIEW -> READY (approve)

    text = path.read_text(encoding="utf-8")
    assert "# Issue #4:" in text
    assert "## What was done" in text and "### Attempt 1" in text and "### Attempt 2" in text
    assert "did the thing" in text and "added work file" in text
    assert "## Failure history" in text
    assert "| Time | Stage | Class | Root cause | Evidence | Outcome |" in text
    assert "IMPLEMENTATION_FAILURE" in text
    assert "## Event timeline" in text and "worker_report" in text


# -- AC-3: agentctl report / audit --------------------------------------------------------------

def test_agentctl_report_and_audit_failure_history(env, capsys):
    config, gh, clock = env
    _add_issue(gh, 5, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch); _tick(orch)
    rec = orch.store.get(5)
    _red(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch)

    capsys.readouterr()
    assert cmd_report(config, argparse.Namespace(number=5)) == 0
    out = capsys.readouterr().out
    assert "## What was done" in out and "## Failure history" in out and "IMPLEMENTATION_FAILURE" in out

    assert cmd_audit(config, argparse.Namespace(number=5, limit=200)) == 0
    out = capsys.readouterr().out
    fh_idx = out.index("failure history:")
    events_idx = out.index("transition")
    assert fh_idx < events_idx        # failure history printed before the raw event timeline
    failure_history_block = out[fh_idx: out.index("\n\n", fh_idx)]
    assert "IMPLEMENTATION_FAILURE" in failure_history_block


# -- AC-4: every failure milestone comment matches the fixed template ----------------------------

_TEMPLATE_RE = re.compile(
    r"\*\*Failure record\*\*\n"
    r"- stage: (?P<stage>\w+)\n"
    r"- class: (?P<failure_class>\w+)\n"
    r"- attempt: (?P<attempt>\d+)/(?P<total>\d+)\n"
    r"- root cause: (?P<root_cause>.*)\n"
    r"- evidence: (?P<evidence>.*)\n"
    r"- next action: (?P<next_action>\w+)"
)


def _extract_templates(comments: list[tuple[int, str]], issue_id: int) -> list[re.Match]:
    matches = []
    for i, text in comments:
        if i != issue_id:
            continue
        m = _TEMPLATE_RE.search(text)
        if m:
            matches.append(m)
    return matches


def test_failure_milestone_template(env):
    config, gh, clock = env

    _add_issue(gh, 6, risk="LOW")
    runner = FakeAgentRunner(script={"worker": AgentRunResult(ok=False, exit_code=1, error="boom")})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)
    matches = _extract_templates(gh.comments, 6)
    assert len(matches) == 1
    assert matches[0]["stage"] == "worker" and matches[0]["failure_class"] == "WORKER_FAILED"
    assert matches[0]["next_action"] == "requeue"

    _add_issue(gh, 7, risk="LOW")
    runner2 = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch2 = _orch(config, gh, clock, runner2)
    _tick(orch2); _tick(orch2)
    rec = orch2.store.get(7)
    _red(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch2)
    matches2 = _extract_templates(gh.comments, 7)
    assert len(matches2) == 1
    assert matches2[0]["stage"] == "ci" and matches2[0]["next_action"] == "repair"

    reject = {**APPROVE, "verdict": "REQUEST_CHANGES", "summary": "test is tautological", "tests_meaningful": False}
    _add_issue(gh, 8, risk="LOW")
    runner3 = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": reject})
    orch3 = _orch(config, gh, clock, runner3)
    _tick(orch3); _tick(orch3)
    rec3 = orch3.store.get(8)
    _green(gh, gh.get_pr(rec3.pr_number)["head"]["sha"])
    _tick(orch3); _tick(orch3)
    matches3 = _extract_templates(gh.comments, 8)
    assert len(matches3) == 1
    assert matches3[0]["stage"] == "review" and matches3[0]["failure_class"] == "REVIEW_REJECTED"
    assert matches3[0]["next_action"] == "repair"

    # the template itself is the single source of truth every callsite renders through
    assert "**Failure record**" in FAILURE_TEMPLATE
