"""Collect deterministic CI evidence for a PR head SHA: check runs, gate reports, failed-job logs.

The evidence object is what the orchestrator decides on (green / red / pending), what the
failure classifier reads, and what the independent reviewer is shown. It is built only from
GitHub's own records (check runs, workflow-run artifacts, job logs) — never from anything a model
said.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field

from agent_team.config import Config

PENDING = "pending"
SUCCESS = "success"
FAILURE = "failure"
MISSING = "missing"

_ARTIFACT_REPORTS = {
    "agent-contract": ("contract_report.json", "manifest.json"),
    "agent-verification": ("verification_report.json",),
    "agent-regression": ("regression_report.json", "regression_gate_report.json"),
}


@dataclass
class CiEvidence:
    head_sha: str
    status: str                                  # pending | success | failure | missing
    checks: dict[str, dict] = field(default_factory=dict)      # name -> {status, conclusion, url}
    reports: dict[str, dict] = field(default_factory=dict)     # report name -> parsed json
    logs: dict[str, str] = field(default_factory=dict)         # failed check name -> log tail
    run_ids: list[int] = field(default_factory=list)

    def gate_results(self) -> dict[str, str]:
        return {n: (c.get("conclusion") or c.get("status") or "") for n, c in self.checks.items()}

    def summary_markdown(self) -> str:
        rows = ["| Check | Status | Conclusion |", "|---|---|---|"]
        for name, c in sorted(self.checks.items()):
            rows.append(f"| {name} | {c.get('status')} | {c.get('conclusion') or '—'} |")
        lines = [f"CI for `{self.head_sha[:12]}`: **{self.status.upper()}**", "", *rows]
        v = self.reports.get("verification_report")
        if v:
            failed = [c["name"] for c in v.get("checks", []) if not c.get("ok")]
            lines += ["", f"Gate 3 verification: {'PASS' if v.get('ok') else 'FAIL'}" + (f" — failed: {failed}" if failed else "")]
        r = self.reports.get("regression_report")
        if r:
            b, a = r.get("before", {}), r.get("after", {})
            lines += ["", "Gate 4 regression: "
                      f"planned {b.get('planned')}→{a.get('planned')}, refused {b.get('refused')}→{a.get('refused')}, "
                      f"crashes {b.get('crashes')}→{a.get('crashes')}, LOST {len(r.get('lost', []))}, GAINED {len(r.get('gained', []))}, "
                      f"status changes {len(r.get('status_changes', []))}, refusal-code changes {len(r.get('refusal_code_changes', []))}, "
                      f"primary-signature changes {len(r.get('primary_signature_changes', []))}, "
                      f"byte-identical primaries {r.get('byte_identical_primaries')}"]
            g = self.reports.get("regression_gate_report")
            if g:
                lines.append(f"Regression budget: {'OK' if g.get('ok') else 'VIOLATED'}")
        return "\n".join(lines)

    def regression_markdown(self) -> str:
        r = self.reports.get("regression_report")
        if not r:
            return "not run (not required for this PR, or not yet available)"
        return self.summary_markdown().split("Gate 4 regression: ", 1)[-1] if "Gate 4 regression: " in self.summary_markdown() else "n/a"


def collect(github, config: Config, head_sha: str, *, fetch_logs: bool = True, fetch_artifacts: bool = True) -> CiEvidence:
    runs = github.check_runs(head_sha)
    checks: dict[str, dict] = {}
    for r in runs:
        name = r.get("name", "")
        # keep the latest run per check name (re-runs create new check runs with the same name)
        prev = checks.get(name)
        if prev is None or (r.get("id", 0) or 0) >= (prev.get("id", 0) or 0):
            checks[name] = {"id": r.get("id"), "status": r.get("status"), "conclusion": r.get("conclusion"),
                            "url": r.get("html_url"), "check_suite_id": (r.get("check_suite") or {}).get("id")}
    required = list(config.required_checks)
    if not checks:
        status = MISSING
    elif any(checks.get(n, {}).get("status") != "completed" for n in required) or any(
            c.get("status") != "completed" for c in checks.values() if c.get("status")):
        status = PENDING if all(n in checks for n in required) or any(c.get("status") != "completed" for c in checks.values()) else MISSING
    else:
        status = SUCCESS if all(checks.get(n, {}).get("conclusion") == "success" for n in required) else FAILURE
    ev = CiEvidence(head_sha=head_sha, status=status, checks=checks)
    if status in (SUCCESS, FAILURE):
        try:
            wruns = github.workflow_runs(head_sha)
        except Exception:  # noqa: BLE001 — evidence collection must never crash the loop
            wruns = []
        ev.run_ids = [w["id"] for w in wruns if w.get("id")]
        if fetch_artifacts:
            for run_id in ev.run_ids:
                _load_artifacts(github, run_id, ev)
        if fetch_logs and status == FAILURE:
            for run_id in ev.run_ids:
                _load_failed_logs(github, run_id, ev)
    return ev


def _load_artifacts(github, run_id: int, ev: CiEvidence) -> None:
    try:
        artifacts = github.run_artifacts(run_id)
    except Exception:  # noqa: BLE001
        return
    for art in artifacts:
        name = art.get("name", "")
        if name not in _ARTIFACT_REPORTS or art.get("expired"):
            continue
        try:
            blob = github.download_artifact(art["id"])
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for member in zf.namelist():
                    base = member.rsplit("/", 1)[-1]
                    if base in _ARTIFACT_REPORTS[name]:
                        ev.reports[base.removesuffix(".json")] = json.loads(zf.read(member).decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue


def _load_failed_logs(github, run_id: int, ev: CiEvidence) -> None:
    try:
        jobs = github.run_jobs(run_id)
    except Exception:  # noqa: BLE001
        return
    for job in jobs:
        if job.get("conclusion") in ("failure", "timed_out", "cancelled"):
            try:
                ev.logs[job.get("name", str(job.get("id")))] = github.job_logs(job["id"])
            except Exception:  # noqa: BLE001
                continue
