from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from agent_team import prompts
from agent_team.agent_runner import AgentRunResult, AgentRunSpec, ClaudeCliRunner, FakeAgentRunner, redact, resolve_claude_binary
from agent_team.schemas import REVIEW_VERDICT_SCHEMA, WORKER_REPORT_SCHEMA
from agent_team.tests.helpers import make_contract


def _fake_claude(tmp_path: Path, script: str) -> str:
    p = tmp_path / "claude"
    p.write_text("#!/usr/bin/env bash\n" + script)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_command_construction(tmp_path):
    binary = _fake_claude(tmp_path, "cat > /dev/null; echo '{}'")
    runner = ClaudeCliRunner(binary, heartbeat_interval=0.01, poll_interval=0.01)
    spec = AgentRunSpec(role="worker", issue_id=3, attempt=1, model="sonnet", cwd=tmp_path, prompt="hi",
                        timeout_seconds=10, json_schema=WORKER_REPORT_SCHEMA, allowed_tools=("Read", "Bash(git add *)"),
                        disallowed_tools=("Bash(git push*)",), permission_mode="acceptEdits", add_dirs=(tmp_path,),
                        session_name="agent-3-worker", system_prompt="rules")
    cmd = runner.build_command(spec)
    assert cmd[:3] == [binary, "-p", "--model"] and "sonnet" in cmd
    assert "--permission-prompts" in cmd and cmd[cmd.index("--permission-prompts") + 1] == "none"
    assert "--json-schema" in cmd and json.loads(cmd[cmd.index("--json-schema") + 1]) == WORKER_REPORT_SCHEMA
    assert "--allowedTools" in cmd and "Bash(git add *)" in cmd
    assert "--disallowedTools" in cmd and "Bash(git push*)" in cmd
    assert "--permission-mode" in cmd and "acceptEdits" in cmd
    assert "--append-system-prompt" in cmd
    reviewer = AgentRunSpec(role="reviewer", issue_id=3, attempt=1, model="sonnet", cwd=tmp_path, prompt="p",
                            timeout_seconds=10, json_schema=REVIEW_VERDICT_SCHEMA, tools=("Read", "Grep", "Glob"),
                            restricted=True, persist_session=False)
    rcmd = runner.build_command(reviewer)
    assert "--restricted" in rcmd and "--tools" in rcmd and "Read,Grep,Glob" in rcmd and "--no-session-persistence" in rcmd


def test_run_parses_json_result_and_structured_output(tmp_path):
    out = json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "duration_ms": 12,
                      "total_cost_usd": 0.01, "session_id": "sess-1", "permission_denials": [],
                      "result": "{\"status\":\"done\"}", "structured_output": {"status": "done"}})
    binary = _fake_claude(tmp_path, f"cat > /dev/null; echo '{out}'")
    runner = ClaudeCliRunner(binary, heartbeat_interval=0.01, poll_interval=0.01)
    beats = []
    res = runner.run(AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=tmp_path, prompt="go",
                                  timeout_seconds=10, json_schema={"type": "object"}), heartbeat=beats.append)
    assert res.ok and res.structured == {"status": "done"} and res.session_id == "sess-1" and res.num_turns == 3
    assert res.cost_usd == 0.01


def test_run_reports_error_result(tmp_path):
    out = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "ran out", "session_id": "s"})
    binary = _fake_claude(tmp_path, f"cat > /dev/null; echo '{out}'")
    res = ClaudeCliRunner(binary, poll_interval=0.01).run(
        AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=tmp_path, prompt="go", timeout_seconds=10))
    assert not res.ok and res.is_error and "ran out" in res.error


def test_run_without_json_is_a_failure(tmp_path):
    binary = _fake_claude(tmp_path, "cat > /dev/null; echo 'not json'; exit 3")
    res = ClaudeCliRunner(binary, poll_interval=0.01).run(
        AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=tmp_path, prompt="go", timeout_seconds=10))
    assert not res.ok and res.exit_code == 3 and "no JSON result" in res.error


def test_timeout_kills_process(tmp_path):
    binary = _fake_claude(tmp_path, "cat > /dev/null; sleep 30; echo '{}'")
    res = ClaudeCliRunner(binary, poll_interval=0.05).run(
        AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=tmp_path, prompt="go", timeout_seconds=1))
    assert res.timed_out and not res.ok


def test_prompt_is_delivered_on_stdin(tmp_path):
    binary = _fake_claude(tmp_path, "P=$(cat); echo \"{\\\"type\\\":\\\"result\\\",\\\"subtype\\\":\\\"success\\\",\\\"result\\\":\\\"$P\\\"}\"")
    res = ClaudeCliRunner(binary, poll_interval=0.01).run(
        AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=tmp_path, prompt="the-prompt", timeout_seconds=10))
    assert res.ok and res.result_text == "the-prompt"


def test_redaction():
    s = "token ghp_abcdefghijklmnopqrstuvwxyz0123 and sk-ant-api03-xxxxxxxxxxxx and Authorization: Bearer abcdefghijklmnopqrstu api_key=abcdefghijklmnop"
    r = redact(s)
    assert "ghp_" not in r and "sk-ant" not in r and "Bearer abcdefghijklmnopqrstu" not in r and "api_key=[REDACTED]" in r


def test_resolve_binary_prefers_env(tmp_path, monkeypatch):
    p = _fake_claude(tmp_path, "true")
    monkeypatch.setenv("CLAUDE_BIN", p)
    assert resolve_claude_binary("auto") == p
    monkeypatch.delenv("CLAUDE_BIN")
    with pytest.raises(FileNotFoundError):
        resolve_claude_binary(str(tmp_path / "missing"))


def test_fake_runner_scripts_by_role_and_issue():
    fake = FakeAgentRunner(script={("worker", 1): {"status": "done"}, "reviewer": {"verdict": "APPROVE"}})
    r = fake.run(AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=Path("."), prompt="", timeout_seconds=1))
    assert r.ok and r.structured == {"status": "done"}
    r = fake.run(AgentRunSpec(role="reviewer", issue_id=9, attempt=1, model="sonnet", cwd=Path("."), prompt="", timeout_seconds=1))
    assert r.structured == {"verdict": "APPROVE"}
    fake2 = FakeAgentRunner(script={"worker": AgentRunResult(ok=False, exit_code=1, error="boom")})
    assert not fake2.run(AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=Path("."), prompt="", timeout_seconds=1)).ok


def test_prompts_render_contract():
    c = make_contract(42, title="[agent] Do the thing")
    p = prompts.worker_prompt(c, worktree="/wt", branch="agent/42-do-the-thing", base_ref="origin/main")
    assert "Issue #42" in p and "AC-1:" in p and "grep:backend/README.md:Autonomous workflow" in p and "/wt" in p
    assert "Never" in p and "do not open a PR" in p
    rp = prompts.repair_prompt(c, worktree="/wt", branch="b", attempt=1, max_attempts=2, failure_class="TEST_FAILURE",
                               failure_summary="x failed", evidence="log")
    assert "repair attempt 1 of 2" in rp and "TEST_FAILURE" in rp
    rv = prompts.reviewer_prompt(c, ci_evidence="all green", regression_report="n/a", worker_report="{}", files_changed="a.py", diff="+x")
    assert "INDEPENDENT REVIEWER" in rv and "+x" in rv
    dl = prompts.domain_lead_prompt(domain="geometry", question="why?", worktree="/wt")
    assert "geometry" in dl and "why?" in dl
    with pytest.raises(KeyError):
        prompts.render("worker", issue_number="1")
