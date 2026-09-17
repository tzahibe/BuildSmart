"""Pilot finding (PR #7, gate-2 job 105194679091): isolated environments need a dummy OPENAI_API_KEY
because backend/app/main.py constructs OpenAI clients at import time. These tests pin the fix."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import yaml

from agent_team import cli
from agent_team import state_machine as sm
from agent_team.agent_runner import AgentRunSpec, ClaudeCliRunner, FakeAgentRunner
from agent_team.failure_classifier import ENVIRONMENT_FAILURE, FailureInput, classify
from agent_team.orchestrator import _sh
from agent_team.tests.conftest import CONFIG_PATH
from agent_team.tests.test_orchestrator_lifecycle import APPROVE, _add_issue, _git, _orch, _tick, _worker_that_commits, env  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_LOG = """
  File "/home/runner/work/BuildSmart/BuildSmart/backend/app/main.py", line 40, in <module>
    assistant: ChatAssistant = OpenAIChatAssistant()
    self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    raise OpenAIError(
openai.OpenAIError: Missing credentials. Please pass an `api_key`, `workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY` or `OPENAI_ADMIN_KEY` environment variable.
##[error]Process completed with exit code 1.
"""


def test_missing_openai_credentials_is_environment_failure_not_repairable():
    c = classify(FailureInput(gate_results={"gate-1-contract / contract": "success", "gate-2-static": "failure"},
                              logs={"gate-2-static": CI_LOG}, changed_files=["backend/README.md"]))
    assert c.kind == ENVIRONMENT_FAILURE and "credential" in c.summary and not c.repairable


def test_config_declares_the_dummy_key_and_workflows_export_it(repo_config):
    assert repo_config.command_env["OPENAI_API_KEY"] == "not-a-real-key-agent-only"
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/agent-ci.yml").read_text())
    for job in ("gate-2-static", "gate-3-verification"):
        assert ci["jobs"][job]["env"]["OPENAI_API_KEY"].startswith("not-a-real-key")
    reg = yaml.safe_load((REPO_ROOT / ".github/workflows/agent-regression.yml").read_text())
    assert reg["jobs"]["regression"]["env"]["OPENAI_API_KEY"].startswith("not-a-real-key")


def test_sh_injects_command_env_without_overriding(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = _sh("printf '%s' \"$OPENAI_API_KEY\"", tmp_path, 30, {"OPENAI_API_KEY": "dummy"}).stdout
    assert out == "dummy"
    monkeypatch.setenv("OPENAI_API_KEY", "real-from-shell")
    out = _sh("printf '%s' \"$OPENAI_API_KEY\"", tmp_path, 30, {"OPENAI_API_KEY": "dummy"}).stdout
    assert out == "real-from-shell"


def test_runner_passes_extra_env_to_the_agent_process(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    binary = tmp_path / "claude"
    binary.write_text("#!/usr/bin/env bash\ncat >/dev/null; printf '{\"type\":\"result\",\"subtype\":\"success\",\"result\":\"%s\"}' \"$OPENAI_API_KEY\"\n")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    res = ClaudeCliRunner(str(binary), poll_interval=0.01).run(
        AgentRunSpec(role="worker", issue_id=1, attempt=1, model="sonnet", cwd=tmp_path, prompt="x", timeout_seconds=10,
                     extra_env=(("OPENAI_API_KEY", "dummy-for-agent"),)))
    assert res.ok and res.result_text == "dummy-for-agent"


def test_worker_and_smoke_get_the_env(env, monkeypatch):
    """The orchestrator threads config.commands.env into worker specs and smoke commands."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config, gh, clock, _ = env
    raw = yaml.safe_load((config.repo_root / ".agent/config.yaml").read_text())
    raw["commands"]["env"] = {"OPENAI_API_KEY": "dummy-smoke"}
    raw["commands"]["smoke"] = [{"cwd": ".", "cmd": "test \"$OPENAI_API_KEY\" = dummy-smoke"}]
    (config.repo_root / ".agent/config.yaml").write_text(yaml.safe_dump(raw))
    from agent_team.config import load_config
    config = load_config(repo_root=config.repo_root)
    _add_issue(gh, 1, risk="LOW")
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    _tick(orch)
    assert dict(runner.calls[0].extra_env)["OPENAI_API_KEY"] == "dummy-smoke"
    _tick(orch)
    rec = orch.store.get(1)
    from agent_team.tests.test_orchestrator_lifecycle import _green
    _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    for _ in range(5):
        _tick(orch)
    assert orch.store.get(1).state == sm.DONE                # smoke saw the injected variable


def test_resume_pr_update_base_merges_main_and_pushes(env, capsys):
    config, gh, clock, origin = env
    _add_issue(gh, 2, risk="LOW")
    orch = _orch(config, gh, clock, FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE}))
    _tick(orch); _tick(orch)
    rec = orch.store.get(2)
    orch.store.release_locks(2)
    orch.store.transition(2, sm.BLOCKED, failure_class="ENVIRONMENT_FAILURE", last_error="missing credential")
    # main advances (the environment fix landed)
    other = config.repo_root.parent / "other"
    _git(["clone", "-q", str(origin), str(other)], config.repo_root.parent)
    _git(["config", "user.email", "o@example.com"], other); _git(["config", "user.name", "other"], other)
    (other / "fix.txt").write_text("fixed\n")
    _git(["add", "."], other); _git(["commit", "-q", "-m", "env fix"], other); _git(["push", "-q", "origin", "main"], other)
    cli._github = lambda cfg, require_auth=True: gh   # type: ignore[assignment]
    args = type("A", (), {"number": 2, "update_base": True})()
    assert cli.cmd_resume_pr(config, args) == 0
    out = capsys.readouterr().out
    assert "merged origin/main" in out and "-> PR_OPEN" in out
    rec = orch.store.get(2)
    assert rec.state == sm.PR_OPEN and rec.validated_commit is None
    assert (Path(rec.worktree) / "fix.txt").exists()
    remote_head = _git(["ls-remote", "--heads", str(origin), rec.branch], config.repo_root).stdout.split()[0]
    assert remote_head == orch.worktrees.head_sha(Path(rec.worktree))
    assert any(e["kind"] == "base_updated_by_lead" for e in orch.store.events(2))
    # a second call with nothing to merge is a no-op that still resumes
    orch.store.transition(2, sm.CI); orch.store.transition(2, sm.BLOCKED)
    assert cli.cmd_resume_pr(config, args) == 0
    assert "already up to date" in capsys.readouterr().out
