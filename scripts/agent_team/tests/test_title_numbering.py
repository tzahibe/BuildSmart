"""Issue #25: every open agent Issue's title carries its own number, `[agent] #N Title`.

This repo has no Telegram/remote-control gateway on `main` (`scripts/agent_team/remote/gateway.py`
does not exist here — it lives only on the separate, unmerged `infra/telegram-control-plane`
branch). The two real entry points that create/display Issue titles on this branch are
`agentctl issue create` (`cli.cmd_issue`) and `agentctl status` (`status.render`); this file proves
the title-numbering contract against those.
"""
from __future__ import annotations

from pathlib import Path

from agent_team import cli
from agent_team import state_machine as sm
from agent_team.issue_contract import render_body
from agent_team.resource_manager import ResourceManager
from agent_team.state_store import StateStore
from agent_team.status import render as status_render
from agent_team.tests.helpers import make_contract
from agent_team.tests.test_orchestrator_lifecycle import env  # noqa: F401


def _write_contract_file(path: Path, c) -> Path:
    f = path / "contract.md"
    f.write_text(f"# {c.title}\n\n{render_body(c)}")
    return f


def test_create_issue_numbers_title(env, tmp_path):  # noqa: F811
    config, gh, _, _ = env
    c = make_contract(0, title="[agent] Work reports and structured failure recovery")
    contract_file = _write_contract_file(tmp_path, c)
    cli._github = lambda cfg, require_auth=True: gh   # type: ignore[assignment]
    args = type("A", (), {"issue_cmd": "create", "from_file": str(contract_file), "title": None, "queue": False})()
    assert cli.cmd_issue(config, args) == 0
    issue = gh.get_issue(gh.next_number - 1)
    assert issue["title"] == f"[agent] #{issue['number']} Work reports and structured failure recovery"


def test_status_lines_show_number_once(env):  # noqa: F811
    config, gh, _, _ = env
    store = StateStore(config.state_db_path)
    store.track(24, title="[agent] #24 Work reports", risk="LOW", resource_class="LIGHT",
               domains=["backend"], dependencies=[], contract={}, state=sm.QUEUED)
    out = status_render(config, store, ResourceManager(config, store), probe_machine=False)
    line = [l for l in out.splitlines() if l.strip().startswith("#24")][0]
    assert line.count("#24") == 1
    assert "Work reports" in line
