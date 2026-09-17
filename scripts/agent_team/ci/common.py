from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GateReport:
    gate: str
    ok: bool = True
    checks: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            self.ok = False

    def to_dict(self) -> dict:
        return {"gate": self.gate, "ok": self.ok, "checks": self.checks, **self.extra}

    def markdown(self) -> str:
        rows = ["| Check | Result | Detail |", "|---|---|---|"]
        for c in self.checks:
            detail = c["detail"].replace("|", "\\|").replace("\n", " ")[:300]
            rows.append(f"| {c['name']} | {'✅' if c['ok'] else '❌'} | {detail} |")
        return f"## {self.gate}: {'PASS' if self.ok else 'FAIL'}\n\n" + "\n".join(rows) + "\n"


def write_report(report: GateReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report.markdown() + "\n")
    print(report.markdown())


def set_output(name: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    print(f"::notice::{name}={value}")


def event_payload() -> dict:
    p = os.environ.get("GITHUB_EVENT_PATH")
    if p and Path(p).exists():
        return json.loads(Path(p).read_text(encoding="utf-8"))
    return {}


def run(cmd: str, cwd: Path, timeout: int = 1800, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **(env or {})})


def repo_root() -> Path:
    return Path(os.environ.get("GITHUB_WORKSPACE") or os.environ.get("AGENT_TEAM_REPO_ROOT") or Path.cwd()).resolve()
