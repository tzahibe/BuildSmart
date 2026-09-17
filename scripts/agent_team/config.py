"""Load and validate `.agent/config.yaml` — the single source of every tunable.

Nothing else in the package hard-codes an interval, a limit, a model name, a command, or a path.
The loader is strict about the keys the orchestrator relies on (a typo in the YAML fails at
startup with a clear message, not at 3 a.m. inside the scheduler).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RISKS = ("LOW", "MEDIUM", "HIGH")
RESOURCE_CLASSES = ("LIGHT", "MEDIUM", "HEAVY")
DOMAINS = ("frontend", "backend", "geometry", "validator", "knowledge", "ai", "qa", "infra")


class ConfigError(ValueError):
    """The config file is missing something the orchestrator cannot run without."""


def find_repo_root(start: Path | None = None) -> Path:
    """The repo root is the directory holding `.agent/config.yaml` (or `$AGENT_TEAM_REPO_ROOT`)."""
    env = os.environ.get("AGENT_TEAM_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".agent" / "config.yaml").exists():
            return candidate
    raise ConfigError("could not find .agent/config.yaml above the current directory")


@dataclass(frozen=True)
class Command:
    cmd: str
    cwd: str = "."
    heavy: bool = False


@dataclass(frozen=True)
class RiskPolicy:
    requires: tuple[str, ...]
    auto_merge: bool
    regression: str  # always | required_if_backend


@dataclass(frozen=True)
class Config:
    repo_root: Path
    raw: dict[str, Any]

    # github
    repo: str
    base_branch: str
    poll_interval_seconds: int
    poll_labels: tuple[str, ...]
    executable_author_associations: tuple[str, ...]
    merge_method: str
    delete_branch_after_merge: bool
    ci_wait_seconds: int
    ci_poll_interval_seconds: int
    required_checks: tuple[str, ...]

    # paths (relative to repo_root unless absolute)
    worktree_root: Path
    branch_prefix: str
    state_dir: Path
    logs_dir: Path
    contracts_dir: Path

    # models
    models: dict[str, str]

    # claude
    claude_binary: str
    claude_effort: str
    worker_timeout_seconds: int
    repair_timeout_seconds: int
    reviewer_timeout_seconds: int
    domain_lead_timeout_seconds: int
    heartbeat_interval_seconds: int
    stale_after_seconds: int
    worker_permission_mode: str
    worker_allowed_tools: tuple[str, ...]
    worker_disallowed_tools: tuple[str, ...]
    reviewer_tools: tuple[str, ...]
    domain_lead_tools: tuple[str, ...]

    # resources
    max_worker_agents: int
    max_reviewer_agents: int
    max_domain_leads: int
    weighted_capacity: int
    weights: dict[str, int]
    cpu_threshold_percent: float
    min_free_memory_gb: float
    probe_window_seconds: float
    heavy_job_concurrency: int
    heavy_job_stale_after_seconds: int

    # locks
    known_locks: tuple[str, ...]
    implied_locks_by_domain: dict[str, tuple[str, ...]]
    lock_stale_after_seconds: int

    # repair / policy
    max_repair_attempts: int
    risk_policy: dict[str, RiskPolicy]
    regression_domains: tuple[str, ...]

    # commands
    worktree_setup: dict[str, tuple[Command, ...]]
    fast_tests: dict[str, Command]
    smoke: tuple[Command, ...]
    regression_commands: dict[str, Command]

    # timeouts
    command_timeout_seconds: int
    regression_timeout_seconds: int
    merge_wait_seconds: int

    def path(self, p: Path) -> Path:
        return p if p.is_absolute() else self.repo_root / p

    @property
    def state_db_path(self) -> Path:
        return self.path(self.state_dir) / "orchestrator.sqlite3"


def _need(d: dict, key: str, section: str):
    if key not in d:
        raise ConfigError(f"config section '{section}' is missing required key '{key}'")
    return d[key]


def _cmd(spec: Any) -> Command:
    if isinstance(spec, str):
        return Command(cmd=spec)
    if isinstance(spec, dict) and "cmd" in spec:
        return Command(cmd=str(spec["cmd"]), cwd=str(spec.get("cwd", ".")), heavy=bool(spec.get("heavy", False)))
    raise ConfigError(f"invalid command spec: {spec!r}")


def load_config(repo_root: Path | None = None, path: Path | None = None) -> Config:
    root = repo_root or find_repo_root()
    cfg_path = path or (root / ".agent" / "config.yaml")
    if not cfg_path.exists():
        raise ConfigError(f"missing config file {cfg_path}")
    with open(cfg_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if raw.get("version") != 1:
        raise ConfigError("config 'version' must be 1")

    gh = _need(raw, "github", "root")
    paths = _need(raw, "paths", "root")
    models = _need(raw, "models", "root")
    cl = _need(raw, "claude", "root")
    res = _need(raw, "resources", "root")
    locks = _need(raw, "locks", "root")
    repair = _need(raw, "repair", "root")
    policy = _need(raw, "risk_policy", "root")
    cmds = _need(raw, "commands", "root")
    tmo = _need(raw, "timeouts", "root")

    for role in ("master_team_lead", "domain_lead", "worker", "reviewer"):
        _need(models, role, "models")
    weights = dict(_need(res, "weights", "resources"))
    for rc in RESOURCE_CLASSES:
        if rc not in weights:
            raise ConfigError(f"resources.weights is missing {rc}")
    risk_policy = {}
    for risk in RISKS:
        p = _need(policy, risk, "risk_policy")
        risk_policy[risk] = RiskPolicy(
            requires=tuple(p.get("requires", ())),
            auto_merge=bool(p.get("auto_merge", False)),
            regression=str(p.get("regression", "required_if_backend")),
        )
    implied = {k: tuple(v) for k, v in (locks.get("implied_by_domain") or {}).items()}
    for dom in implied:
        if dom not in DOMAINS:
            raise ConfigError(f"locks.implied_by_domain has unknown domain '{dom}'")

    setup = {k: tuple(_cmd(c) for c in v) for k, v in (cmds.get("worktree_setup") or {}).items()}
    fast = {k: _cmd(v) for k, v in (cmds.get("fast_tests") or {}).items()}
    smoke = tuple(_cmd(c) for c in (cmds.get("smoke") or ()))
    regression = {k: _cmd(v) for k, v in (cmds.get("regression") or {}).items()}

    return Config(
        repo_root=root,
        raw=raw,
        repo=str(_need(gh, "repo", "github")),
        base_branch=str(gh.get("base_branch", "main")),
        poll_interval_seconds=int(_need(gh, "poll_interval_seconds", "github")),
        poll_labels=tuple(gh.get("poll_labels") or ("agent:queued",)),
        executable_author_associations=tuple(gh.get("executable_author_associations") or ("OWNER",)),
        merge_method=str(gh.get("merge_method", "squash")),
        delete_branch_after_merge=bool(gh.get("delete_branch_after_merge", True)),
        ci_wait_seconds=int(gh.get("ci_wait_seconds", 5400)),
        ci_poll_interval_seconds=int(gh.get("ci_poll_interval_seconds", 60)),
        required_checks=tuple(gh.get("required_checks") or ()),
        worktree_root=Path(str(_need(paths, "worktree_root", "paths"))),
        branch_prefix=str(_need(paths, "branch_prefix", "paths")),
        state_dir=Path(str(_need(paths, "state_dir", "paths"))),
        logs_dir=Path(str(_need(paths, "logs_dir", "paths"))),
        contracts_dir=Path(str(_need(paths, "contracts_dir", "paths"))),
        models={k: str(v) for k, v in models.items()},
        claude_binary=str(cl.get("binary", "auto")),
        claude_effort=str(cl.get("effort", "high")),
        worker_timeout_seconds=int(_need(cl, "worker_timeout_seconds", "claude")),
        repair_timeout_seconds=int(cl.get("repair_timeout_seconds", cl.get("worker_timeout_seconds"))),
        reviewer_timeout_seconds=int(_need(cl, "reviewer_timeout_seconds", "claude")),
        domain_lead_timeout_seconds=int(cl.get("domain_lead_timeout_seconds", 1200)),
        heartbeat_interval_seconds=int(cl.get("heartbeat_interval_seconds", 30)),
        stale_after_seconds=int(_need(cl, "stale_after_seconds", "claude")),
        worker_permission_mode=str(cl.get("worker_permission_mode", "acceptEdits")),
        worker_allowed_tools=tuple(cl.get("worker_allowed_tools") or ()),
        worker_disallowed_tools=tuple(cl.get("worker_disallowed_tools") or ()),
        reviewer_tools=tuple(cl.get("reviewer_tools") or ("Read", "Grep", "Glob")),
        domain_lead_tools=tuple(cl.get("domain_lead_tools") or ("Read", "Grep", "Glob")),
        max_worker_agents=int(_need(res, "max_worker_agents", "resources")),
        max_reviewer_agents=int(_need(res, "max_reviewer_agents", "resources")),
        max_domain_leads=int(res.get("max_domain_leads", 1)),
        weighted_capacity=int(_need(res, "weighted_capacity", "resources")),
        weights={k: int(v) for k, v in weights.items()},
        cpu_threshold_percent=float(_need(res, "cpu_threshold_percent", "resources")),
        min_free_memory_gb=float(_need(res, "min_free_memory_gb", "resources")),
        probe_window_seconds=float(res.get("probe_window_seconds", 3)),
        heavy_job_concurrency=int(_need(res, "heavy_job_concurrency", "resources")),
        heavy_job_stale_after_seconds=int(res.get("heavy_job_stale_after_seconds", 5400)),
        known_locks=tuple(locks.get("known") or ()),
        implied_locks_by_domain=implied,
        lock_stale_after_seconds=int(locks.get("stale_after_seconds", 7200)),
        max_repair_attempts=int(_need(repair, "max_attempts", "repair")),
        risk_policy=risk_policy,
        regression_domains=tuple(raw.get("regression_domains") or ("backend", "geometry", "validator")),
        worktree_setup=setup,
        fast_tests=fast,
        smoke=smoke,
        regression_commands=regression,
        command_timeout_seconds=int(tmo.get("command_seconds", 1800)),
        regression_timeout_seconds=int(tmo.get("regression_seconds", 3600)),
        merge_wait_seconds=int(tmo.get("merge_wait_seconds", 600)),
    )
