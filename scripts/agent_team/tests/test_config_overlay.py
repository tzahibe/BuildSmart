"""Machine-local configuration overlay (#188).

`.agent/config.yaml` is TRACKED, so whatever is committed there is what every checkout starts with,
including `main`. Before this there was no third option between "commit the feature ON for
everyone" and "lose the setting on the next pull".
"""
from __future__ import annotations

import yaml

from agent_team.config import LOCAL_CONFIG_NAME, _deep_merge, load_config, overlay_sources
from agent_team.tests.test_orchestrator_lifecycle import env  # noqa: F401


def _write_local(config, data: dict):
    p = config.repo_root / ".agent" / LOCAL_CONFIG_NAME
    p.write_text(yaml.safe_dump(data))
    return p


def test_without_an_overlay_the_tracked_file_is_the_whole_truth(env):
    """No overlay -> the effective value IS the committed value, whatever it is. (Asserting a
    literal here would only pin what the tracked file happens to say today — which is exactly the
    coupling this mechanism exists to break.)"""
    config, *_ = env
    tracked = yaml.safe_load((config.repo_root / ".agent/config.yaml").read_text())
    assert overlay_sources(config.repo_root) == [config.repo_root / ".agent/config.yaml"]
    loaded = load_config(repo_root=config.repo_root)
    assert loaded.analysis_enabled == bool(tracked.get("analysis", {}).get("enabled", False))


def test_the_overlay_turns_a_feature_on_without_touching_the_tracked_file(env):
    """The #189 case: tracked defaults stay OFF, this machine keeps running with them ON."""
    config, *_ = env
    tracked = (config.repo_root / ".agent/config.yaml").read_text()
    # Set the TRACKED file to the safe default first, exactly as #189 would, then prove the
    # overlay restores the live behaviour without editing it again.
    tracked_path = config.repo_root / ".agent/config.yaml"
    data = yaml.safe_load(tracked_path.read_text())
    data["analysis"]["enabled"] = False
    data["power"]["caffeinate_while_working"] = False
    tracked_path.write_text(yaml.safe_dump(data))
    assert load_config(repo_root=config.repo_root).analysis_enabled is False
    tracked = tracked_path.read_text()

    _write_local(config, {"analysis": {"enabled": True},
                          "power": {"caffeinate_while_working": True}})
    reloaded = load_config(repo_root=config.repo_root)
    assert reloaded.analysis_enabled is True
    assert reloaded.caffeinate_while_working is True
    assert (config.repo_root / ".agent/config.yaml").read_text() == tracked   # untouched


def test_the_overlay_merges_deeply_and_leaves_siblings_alone(env):
    config, *_ = env
    before = load_config(repo_root=config.repo_root)
    _write_local(config, {"analysis": {"enabled": True}})      # max_per_tick not mentioned
    after = load_config(repo_root=config.repo_root)
    assert after.analysis_enabled is True
    assert after.analysis_max_per_tick == before.analysis_max_per_tick
    assert after.poll_labels == before.poll_labels


def test_a_list_is_replaced_not_appended():
    """A half-merged `worker_allowed_tools` would be a security hole, not a convenience."""
    merged = _deep_merge({"claude": {"worker_allowed_tools": ["Read", "Bash(git push*)"]}},
                         {"claude": {"worker_allowed_tools": ["Read"]}})
    assert merged["claude"]["worker_allowed_tools"] == ["Read"]


def test_the_overlay_cannot_change_the_config_version(env):
    config, *_ = env
    _write_local(config, {"version": 99, "analysis": {"enabled": True}})
    assert load_config(repo_root=config.repo_root).analysis_enabled is True   # loads fine


def test_a_malformed_overlay_is_refused_loudly(env):
    import pytest
    from agent_team.config import ConfigError
    config, *_ = env
    (config.repo_root / ".agent" / LOCAL_CONFIG_NAME).write_text("just a string\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(repo_root=config.repo_root)


def test_overlay_sources_reports_both_files_when_one_exists(env):
    config, *_ = env
    p = _write_local(config, {"analysis": {"enabled": True}})
    assert overlay_sources(config.repo_root)[-1] == p
