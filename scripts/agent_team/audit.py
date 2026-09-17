"""Structured, redacted run records so every autonomous task can be reconstructed later.

Two sinks: the state store's `events` table (queryable timeline per issue) and JSON files under
`.agent/logs/runs/<issue>/` (one per agent run: command, model, cost, turns, permission denials,
structured output). Secrets are redacted before anything is written.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from agent_team.agent_runner import AgentRunResult, AgentRunSpec, redact
from agent_team.config import Config

log = logging.getLogger("agent_team")


def setup_logging(config: Config, *, verbose: bool = False) -> Path:
    logs = config.path(config.logs_dir)
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "orchestrator.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "_agent_team", False) for h in root.handlers):
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        fh._agent_team = True  # type: ignore[attr-defined]
        root.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh._agent_team = True  # type: ignore[attr-defined]
        root.addHandler(sh)
    return path


class _Redacting(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        return True


logging.getLogger().addFilter(_Redacting())


def write_run_record(config: Config, spec: AgentRunSpec, result: AgentRunResult, *, extra: dict | None = None) -> Path:
    d = config.path(config.logs_dir) / "runs" / str(spec.issue_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{int(time.time())}-{spec.role}-attempt{spec.attempt}.json"
    record = {
        "ts": time.time(), "issue": spec.issue_id, "role": spec.role, "model": spec.model, "attempt": spec.attempt,
        "cwd": str(spec.cwd), "timeout_seconds": spec.timeout_seconds, "resume_session_id": spec.resume_session_id,
        "prompt_chars": len(spec.prompt), "result": result.audit_record(), **(extra or {}),
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def write_contract_snapshot(config: Config, number: int, contract: dict, manifest: dict) -> Path:
    d = config.path(config.contracts_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{number}.json"
    path.write_text(json.dumps({"contract": contract, "manifest": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
