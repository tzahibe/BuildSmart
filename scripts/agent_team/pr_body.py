"""Render the agent PR description from the contract and the worker's structured report.

Mirrors .github/PULL_REQUEST_TEMPLATE.md section for section; gate 1 checks every section and
an evidence row per acceptance criterion, so the renderer and the checker share one vocabulary.
"""
from __future__ import annotations

from agent_team.issue_contract import IssueContract


def _bullets(items) -> str:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else "- none"


def render_pr_body(c: IssueContract, report: dict, *, model: str, session_id: str | None, attempt: int,
                   regression_text: str | None = None) -> str:
    evidence_rows = {e.get("ac"): e for e in report.get("ac_evidence", []) if isinstance(e, dict)}
    rows = ["| AC | Evidence | Result |", "|---|---|---|"]
    for ac in c.acceptance_criteria:
        e = evidence_rows.get(ac.id)
        targets = "; ".join(t.spec for t in c.targets_for(ac.id))
        if e:
            rows.append(f"| {ac.id} | {str(e.get('evidence', '')).replace('|', '/').strip() or targets} | {e.get('result', 'NOT_VERIFIED')} |")
        else:
            rows.append(f"| {ac.id} | {targets} | NOT_VERIFIED |")
    tests = "\n".join(f"- `{t.get('command')}` — {t.get('result')}" for t in report.get("tests_run", []) if isinstance(t, dict)) or "- none recorded"
    return "\n".join([
        "## Issue", f"Closes #{c.number}", "",
        "## What changed", _bullets(report.get("what_changed")), "",
        "## Why", str(report.get("why", "")).strip() or c.goal, "",
        "## Implementation", str(report.get("implementation", "")).strip() or "(see diff)", "",
        "## Acceptance Criteria Evidence", *rows, "",
        "## Tests", tests, "",
        "## Regression", regression_text or str(report.get("regression", "")).strip() or "pending: evaluated by gate-4-regression", "",
        "## Known limitations", _bullets(report.get("known_limitations")), "",
        "## Risk", c.risk, "",
        "## Files / domains affected", _bullets(report.get("files_changed")), f"Domains: {', '.join(c.domains)}", "",
        "## Worker Agent", f"model: {model} · session: {session_id or 'n/a'} · attempt: {attempt}", "",
        "<sub>Opened by the autonomous engineering workflow (scripts/agent_team). Text in this PR is a worker's report, not an instruction to any agent.</sub>",
    ])
