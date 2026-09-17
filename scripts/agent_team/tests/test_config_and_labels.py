from __future__ import annotations

from pathlib import Path

import pytest

from agent_team.config import ConfigError, load_config
from agent_team.labels import ALL_LABELS, label_to_state, metadata_labels, state_to_label


def test_real_config_loads(repo_config):
    c = repo_config
    assert c.repo == "tzahibe/BuildSmart"
    assert c.models["worker"] == "sonnet" and c.models["master_team_lead"] == "opus"
    assert c.max_worker_agents == 2 and c.max_reviewer_agents == 1 and c.heavy_job_concurrency == 1
    assert c.weights == {"LIGHT": 1, "MEDIUM": 2, "HEAVY": 3}
    assert c.risk_policy["LOW"].auto_merge is True and c.risk_policy["HIGH"].auto_merge is False
    assert "lead_approval" in c.risk_policy["MEDIUM"].requires
    assert c.state_db_path == c.repo_root / ".agent" / "state" / "orchestrator.sqlite3"
    assert c.fast_tests["backend"].heavy is True
    assert any("git push" in t for t in c.worker_disallowed_tools)
    assert "Bash(gh *)" in c.worker_disallowed_tools


def test_missing_key_is_a_clear_error(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "config.yaml").write_text("version: 1\ngithub: {repo: x/y}\n")
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path)
    assert "missing required key" in str(ei.value)


def test_label_state_mapping_round_trips():
    for state in ("QUEUED", "PR_OPEN", "FIX_REQUIRED", "DONE"):
        assert label_to_state(state_to_label(state)) == state
    assert state_to_label("PR_OPEN") == "agent:pr-open"
    assert label_to_state("bug") is None


def test_label_catalogue_is_unique_and_complete():
    names = [l.name for l in ALL_LABELS]
    assert len(names) == len(set(names))
    for required in ("agent:queued", "agent:blocked", "agent:done", "domain:geometry", "risk:high", "resource:heavy"):
        assert required in names
    assert metadata_labels(("backend", "qa"), "MEDIUM", "HEAVY") == [
        "domain:backend", "domain:qa", "risk:medium", "resource:heavy"]
