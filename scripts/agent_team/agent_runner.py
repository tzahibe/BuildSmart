"""The agent-spawning adapter. The orchestrator only ever talks to `AgentRunner`.

`ClaudeCliRunner` runs Claude Code headless (`claude -p`) as a child process in the issue's
worktree — the mechanism verified in Phase 0 (docs/AGENT_TEAM_PHASE_0_ENVIRONMENT_REPORT.md §2):
one JSON result on stdout, `structured_output` validated against a schema, `session_id` for a
resumable repair attempt, `permission_denials` for the audit trail. Least privilege is enforced by
the CLI itself (`--allowedTools`/`--disallowedTools`/`--tools`/`--restricted`, `--permission-prompts
none` so nothing can hang on a prompt). Wall-clock limits are enforced here (no `--max-turns` in
this CLI version).

`FakeAgentRunner` implements the same contract for tests and dry-run. Adding another mechanism
(the SDK, `claude --bg`, a remote runner) means one new class, nothing else.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

WORKER = "worker"
FIXER = "fixer"          # fix-and-resubmit worker: CI red / review findings / merge conflicts / amended contract
REVIEWER = "reviewer"
DOMAIN_LEAD = "domain_lead"

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{16,}=*"),
    re.compile(r"(?i)(api[_-]?key|token|secret)(\"?\s*[:=]\s*\"?)([A-Za-z0-9\-._~+/]{12,})"),
]


def redact(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS[:-1]:
        out = pat.sub("[REDACTED]", out)
    out = _SECRET_PATTERNS[-1].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", out)
    return out


def resolve_claude_binary(configured: str = "auto") -> str:
    """$CLAUDE_BIN, an explicit config path, `claude` on PATH, then the newest VS Code extension binary."""
    env = os.environ.get("CLAUDE_BIN")
    if env and Path(env).exists():
        return env
    if configured and configured != "auto":
        if Path(configured).exists():
            return configured
        raise FileNotFoundError(f"configured claude binary not found: {configured}")
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    candidates = glob.glob(os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"))

    def version_key(p: str) -> tuple[int, ...]:
        m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0,)

    candidates = [c for c in candidates if os.access(c, os.X_OK)]
    if candidates:
        return max(candidates, key=version_key)
    raise FileNotFoundError("no Claude Code binary found: set CLAUDE_BIN or claude.binary in .agent/config.yaml")


@dataclass(frozen=True)
class AgentRunSpec:
    role: str
    issue_id: int
    attempt: int
    model: str
    cwd: Path
    prompt: str
    timeout_seconds: int
    system_prompt: str = ""
    json_schema: dict | None = None
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    tools: tuple[str, ...] | None = None       # restrict the built-in tool set (reviewer: Read,Grep,Glob)
    permission_mode: str | None = None
    restricted: bool = False
    add_dirs: tuple[Path, ...] = ()
    effort: str = "high"
    resume_session_id: str | None = None
    session_name: str = ""
    persist_session: bool = True
    settings_json: dict | None = None
    extra_env: tuple[tuple[str, str], ...] = ()   # applied to the agent process unless already set

    @property
    def label(self) -> str:
        return f"{self.role}:{self.model}#{self.issue_id}.{self.attempt}"


@dataclass
class AgentRunResult:
    ok: bool
    exit_code: int
    structured: dict | None = None
    result_text: str = ""
    session_id: str | None = None
    cost_usd: float | None = None
    num_turns: int | None = None
    duration_ms: int | None = None
    is_error: bool = False
    error: str = ""
    timed_out: bool = False
    permission_denials: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    command: list[str] = field(default_factory=list)
    pid: int | None = None

    def audit_record(self) -> dict:
        return {
            "ok": self.ok, "exit_code": self.exit_code, "session_id": self.session_id, "cost_usd": self.cost_usd,
            "num_turns": self.num_turns, "duration_ms": self.duration_ms, "is_error": self.is_error,
            "error": redact(self.error)[:4000], "timed_out": self.timed_out,
            "permission_denials": self.permission_denials, "structured": self.structured,
            "result_text": redact(self.result_text)[:20000], "command": [redact(c) for c in self.command],
        }


class AgentRunner(Protocol):
    def run(self, spec: AgentRunSpec, *, heartbeat: Callable[[int | None], None] | None = None) -> AgentRunResult: ...


class ClaudeCliRunner:
    def __init__(self, binary: str = "auto", *, heartbeat_interval: float = 30.0, poll_interval: float = 1.0):
        self.binary = resolve_claude_binary(binary)
        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval
        self._active: set[subprocess.Popen] = set()
        self._active_lock = threading.Lock()

    def terminate_all(self) -> int:
        """Kill every live agent process group (orchestrator shutdown). Returns how many were signalled."""
        with self._active_lock:
            procs = list(self._active)
        for p in procs:
            if p.poll() is None:
                self._kill(p)
        return len(procs)

    def build_command(self, spec: AgentRunSpec) -> list[str]:
        cmd = [self.binary, "-p", "--model", spec.model, "--output-format", "json", "--permission-prompts", "none",
               "--effort", spec.effort]
        if spec.json_schema:
            cmd += ["--json-schema", json.dumps(spec.json_schema)]
        if spec.system_prompt:
            cmd += ["--append-system-prompt", spec.system_prompt]
        if spec.restricted:
            cmd.append("--restricted")
        if spec.tools is not None:
            cmd += ["--tools", ",".join(spec.tools) if spec.tools else ""]
        if spec.allowed_tools:
            cmd += ["--allowedTools", *spec.allowed_tools]
        if spec.disallowed_tools:
            cmd += ["--disallowedTools", *spec.disallowed_tools]
        if spec.permission_mode:
            cmd += ["--permission-mode", spec.permission_mode]
        for d in spec.add_dirs:
            cmd += ["--add-dir", str(d)]
        if spec.resume_session_id:
            cmd += ["--resume", spec.resume_session_id]
        if spec.session_name:
            cmd += ["--name", spec.session_name]
        if not spec.persist_session:
            cmd.append("--no-session-persistence")
        if spec.settings_json:
            cmd += ["--settings", json.dumps(spec.settings_json)]
        return cmd

    def run(self, spec: AgentRunSpec, *, heartbeat: Callable[[int | None], None] | None = None) -> AgentRunResult:
        cmd = self.build_command(spec)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GH_TOKEN", "GITHUB_TOKEN"))}
        for k, v in spec.extra_env:
            env.setdefault(k, v)
        env["CLAUDE_AGENT_TEAM_ROLE"] = spec.role
        env["CLAUDE_AGENT_TEAM_ISSUE"] = str(spec.issue_id)
        started = time.time()
        try:
            proc = subprocess.Popen(cmd, cwd=str(spec.cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
        except OSError as exc:
            return AgentRunResult(ok=False, exit_code=-1, error=f"failed to spawn: {exc}", command=cmd)
        with self._active_lock:
            self._active.add(proc)

        out_buf: list[str] = []
        err_buf: list[str] = []

        def pump(stream, buf):
            for line in stream:
                buf.append(line)
            stream.close()

        t_out = threading.Thread(target=pump, args=(proc.stdout, out_buf), daemon=True)
        t_err = threading.Thread(target=pump, args=(proc.stderr, err_buf), daemon=True)
        t_out.start()
        t_err.start()
        try:
            proc.stdin.write(spec.prompt)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

        timed_out = False
        last_beat = 0.0
        while proc.poll() is None:
            now = time.time()
            if heartbeat and now - last_beat >= self.heartbeat_interval:
                heartbeat(proc.pid)
                last_beat = now
            if now - started > spec.timeout_seconds:
                timed_out = True
                self._kill(proc)
                break
            time.sleep(self.poll_interval)
        t_out.join(timeout=30)
        t_err.join(timeout=30)
        with self._active_lock:
            self._active.discard(proc)
        stdout, stderr = "".join(out_buf), "".join(err_buf)
        return self._parse(spec, cmd, proc.returncode if proc.returncode is not None else -9, stdout, stderr, timed_out, proc.pid)

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            os.killpg(proc.pid, 15)
            time.sleep(3)
            if proc.poll() is None:
                os.killpg(proc.pid, 9)
        except ProcessLookupError:
            pass

    @staticmethod
    def _parse(spec: AgentRunSpec, cmd: list[str], code: int, stdout: str, stderr: str, timed_out: bool, pid: int | None) -> AgentRunResult:
        data: dict | None = None
        text = stdout.strip()
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # stream noise before the final JSON object: take the last line that parses
                for line in reversed(text.splitlines()):
                    try:
                        candidate = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(candidate, dict) and candidate.get("type") == "result":
                        data = candidate
                        break
        if timed_out:
            return AgentRunResult(ok=False, exit_code=code, timed_out=True, error=f"timed out after {spec.timeout_seconds}s",
                                  result_text=text[-4000:], raw=data or {}, command=cmd, pid=pid)
        if data is None:
            return AgentRunResult(ok=False, exit_code=code, error=f"no JSON result on stdout (exit {code}): {redact(stderr.strip()[-2000:])}",
                                  result_text=text[-4000:], command=cmd, pid=pid)
        structured = data.get("structured_output")
        if structured is None and spec.json_schema and isinstance(data.get("result"), str):
            try:
                structured = json.loads(data["result"])
            except json.JSONDecodeError:
                structured = None
        is_error = bool(data.get("is_error")) or data.get("subtype", "success") != "success"
        ok = code == 0 and not is_error and (structured is not None or not spec.json_schema)
        error = "" if ok else (data.get("result") if is_error and isinstance(data.get("result"), str) else "") or (
            f"subtype={data.get('subtype')} exit={code}" if not ok else "")
        if not ok and spec.json_schema and structured is None and not is_error:
            error = "agent finished without structured output"
        return AgentRunResult(
            ok=ok, exit_code=code, structured=structured if isinstance(structured, dict) else None,
            result_text=str(data.get("result", ""))[:20000], session_id=data.get("session_id"),
            cost_usd=data.get("total_cost_usd"), num_turns=data.get("num_turns"), duration_ms=data.get("duration_ms"),
            is_error=is_error, error=str(error), permission_denials=list(data.get("permission_denials") or []),
            raw={k: v for k, v in data.items() if k not in ("result",)}, command=cmd, pid=pid,
        )


@dataclass
class FakeAgentRunner:
    """Scripted runner for tests and dry-run. `script` maps (role, issue_id) or role to a result or callable."""
    script: dict = field(default_factory=dict)
    calls: list[AgentRunSpec] = field(default_factory=list)
    default_ok: bool = True
    heartbeats: int = 0

    def run(self, spec: AgentRunSpec, *, heartbeat: Callable[[int | None], None] | None = None) -> AgentRunResult:
        self.calls.append(spec)
        if heartbeat:
            heartbeat(4242)
            self.heartbeats += 1
        entry = self.script.get((spec.role, spec.issue_id), self.script.get(spec.role))
        if entry is None and spec.role == FIXER:      # tests script "worker" once for both roles
            entry = self.script.get((WORKER, spec.issue_id), self.script.get(WORKER))
        if callable(entry):
            entry = entry(spec)
        if isinstance(entry, AgentRunResult):
            return entry
        if isinstance(entry, dict):
            return AgentRunResult(ok=True, exit_code=0, structured=entry, session_id=f"fake-{spec.role}-{spec.issue_id}-{spec.attempt}",
                                  cost_usd=0.0, num_turns=1, duration_ms=1)
        if entry is None and self.default_ok:
            return AgentRunResult(ok=True, exit_code=0, structured={}, session_id=f"fake-{spec.role}-{spec.issue_id}-{spec.attempt}",
                                  cost_usd=0.0, num_turns=1, duration_ms=1)
        return AgentRunResult(ok=False, exit_code=1, error="scripted failure")
