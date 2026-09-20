"""Per-Issue work reports and structured failure records.

Every failure transition in `orchestrator.py` (worker failed/blocked, publish failed, CI red,
review rejected) calls `record_failure()`: it appends one `failure_record` event to the state
store (`stage`, `failure_class`, `attempt`, `attempts_left`, `root_cause`, `evidence_ref`,
`next_action`), regenerates the Issue's Markdown work report, and returns the fixed-template
milestone text for the Issue comment (`failure_milestone_text`).

`write_report()` is called on every state change (`Orchestrator._set_state` and the few call
sites that transition the store directly) and renders `.agent/logs/reports/<issue>.md`: a header,
"What was done" per worker-report event, a "Failure history" table built from `failure_record`
events, and the raw event timeline — all redacted the same way `audit.py` redacts run records.

Evidence notes are kept per attempt (`.agent/logs/evidence/<issue>-attempt<n>.md`, replacing the
old single overwritten `<issue>.md` note) so a later report can link the exact evidence an attempt
saw; `load_latest_evidence_note` still returns the most recent one for a repair prompt.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from agent_team.agent_runner import redact
from agent_team.config import Config
from agent_team.state_store import StateStore

#: `stage` values a failure_record may carry: worker/publish/ci/review are worker-lifecycle
#: failures, `owner` is an owner reject/change-request, `usage` is a rate-limit pause.
FAILURE_STAGES = ("worker", "publish", "ci", "review", "merge", "owner", "usage")
NEXT_ACTIONS = ("requeue", "repair", "rerun_ci", "blocked", "paused")

_ROOT_CAUSE_LIMIT = 500


# -- paths --------------------------------------------------------------------------------------

def _reports_dir(config: Config) -> Path:
    return config.path(config.logs_dir) / "reports"


def report_path(config: Config, issue_id: int) -> Path:
    return _reports_dir(config) / f"{issue_id}.md"


def _evidence_dir(config: Config) -> Path:
    return config.path(config.logs_dir) / "evidence"


def evidence_path(config: Config, issue_id: int, attempt: int) -> Path:
    return _evidence_dir(config) / f"{issue_id}-attempt{attempt}.md"


def save_evidence_note(config: Config, issue_id: int, attempt: int, text: str) -> Path:
    p = evidence_path(config, issue_id, attempt)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(redact(text), encoding="utf-8")
    return p


def _attempt_of(name: str) -> int:
    try:
        return int(name.rsplit("attempt", 1)[1][: -len(".md")])
    except (ValueError, IndexError):
        return -1


def load_latest_evidence_note(config: Config, issue_id: int) -> str:
    """The most recent per-attempt evidence note, falling back to the legacy single-file note."""
    d = _evidence_dir(config)
    if d.exists():
        candidates = sorted((p for p in d.glob(f"{issue_id}-attempt*.md")), key=lambda p: _attempt_of(p.name))
        if candidates:
            return candidates[-1].read_text(encoding="utf-8")
    legacy = d / f"{issue_id}.md"
    return legacy.read_text(encoding="utf-8") if legacy.exists() else "(no evidence recorded)"


# -- failure records ------------------------------------------------------------------------------

def _short(text: str, limit: int = _ROOT_CAUSE_LIMIT) -> str:
    text = redact((text or "").strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


FAILURE_TEMPLATE = (
    "**Failure record**\n"
    "- stage: {stage}\n"
    "- class: {failure_class}\n"
    "- attempt: {attempt}/{total_attempts}\n"
    "- root cause: {root_cause}\n"
    "- evidence: {evidence_ref}\n"
    "- next action: {next_action}"
)


def failure_milestone_text(*, stage: str, failure_class: str, attempt: int, attempts_left: int,
                           root_cause: str, evidence_ref: str, next_action: str) -> str:
    """The one fixed template every failure milestone comment uses (AC-4)."""
    return FAILURE_TEMPLATE.format(
        stage=stage, failure_class=failure_class, attempt=attempt, total_attempts=attempt + max(attempts_left, 0),
        root_cause=_short(root_cause) or "(none recorded)", evidence_ref=evidence_ref or "n/a", next_action=next_action)


def record_failure(store: StateStore, config: Config, issue_id: int, *, stage: str, failure_class: str,
                   attempt: int, attempts_left: int, root_cause: str, evidence_ref: str | Path | None,
                   next_action: str) -> str:
    """Emit exactly one `failure_record` event, regenerate the Issue's work report, and return the
    fixed-template milestone text ready to post as the Issue comment."""
    assert stage in FAILURE_STAGES, f"unknown failure stage {stage!r}"
    assert next_action in NEXT_ACTIONS, f"unknown next_action {next_action!r}"
    root_cause = _short(root_cause)
    evidence_ref = str(evidence_ref) if evidence_ref else ""
    attempts_left = max(attempts_left, 0)
    payload = {"stage": stage, "failure_class": failure_class, "attempt": attempt, "attempts_left": attempts_left,
              "root_cause": root_cause, "evidence_ref": evidence_ref, "next_action": next_action}
    store.record_event(issue_id, "failure_record", payload)
    write_report(store, config, issue_id)
    return failure_milestone_text(stage=stage, failure_class=failure_class, attempt=attempt, attempts_left=attempts_left,
                                  root_cause=root_cause, evidence_ref=evidence_ref, next_action=next_action)


def short_root_cause(text: str, limit: int = 80) -> str:
    """The <=80 char form used next to the failure class in the Telegram compact status."""
    return _short(text, limit)


# -- the per-Issue Markdown report --------------------------------------------------------------

def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


def _bulleted(items) -> list[str]:
    items = [redact(str(i).strip()) for i in (items or []) if str(i).strip()]
    return [f"  - {i}" for i in items] if items else ["  - none"]


def _attempt_section(attempt, ts: float, report: dict) -> list[str]:
    tests = report.get("tests_run") or []
    test_lines = [f"  - `{redact(str(t.get('command', '')))}` — {redact(str(t.get('result', '')))}"
                 for t in tests if isinstance(t, dict)] or ["  - none recorded"]
    return [
        f"### Attempt {attempt} ({_fmt_ts(ts)})", "",
        f"- Summary: {redact(str(report.get('summary', '')))}",
        "- What changed:", *_bulleted(report.get("what_changed")),
        f"- Why: {redact(str(report.get('why', '')))}",
        f"- Implementation: {redact(str(report.get('implementation', '')))}",
        "- Files changed:", *_bulleted(report.get("files_changed")),
        "- Tests run:", *test_lines,
        "- Known limitations:", *_bulleted(report.get("known_limitations")),
        "",
    ]


def render_report(store: StateStore, config: Config, issue_id: int) -> str:
    rec = store.get(issue_id)
    if rec is None:
        return f"# Issue #{issue_id}\n\n(not tracked)\n"
    events = store.events(issue_id, limit=5000)
    lines = [
        f"# Issue #{issue_id}: {redact(rec.title)}", "",
        f"- State: {rec.state}",
        f"- Risk: {rec.risk}",
        f"- PR: {f'#{rec.pr_number} ({rec.pr_url})' if rec.pr_number else 'none'}",
        f"- Branch: {rec.branch or 'none'}",
        f"- Validated SHA: {rec.validated_commit or 'none'}",
        f"- Attempts: {rec.attempt_number}",
        "",
        "## What was done", "",
    ]
    worker_events = [e for e in events if e["kind"] == "worker_report"]
    if not worker_events:
        lines += ["(no worker report yet)", ""]
    for e in worker_events:
        lines += _attempt_section(e["payload"].get("attempt", "?"), e["ts"], e["payload"].get("report", {}))
    lines += ["## Failure history", ""]
    failures = [e for e in events if e["kind"] == "failure_record"]
    if not failures:
        lines += ["(none)", ""]
    else:
        lines += ["| Time | Stage | Class | Root cause | Evidence | Outcome |", "|---|---|---|---|---|---|"]
        for e in failures:
            p = e["payload"]
            root = str(p.get("root_cause", "")).replace("|", "/").replace("\n", " ")[:200]
            lines.append(f"| {_fmt_ts(e['ts'])} | {p.get('stage')} | {p.get('failure_class')} | {root} | "
                         f"{p.get('evidence_ref') or 'n/a'} | {p.get('next_action')} |")
        lines.append("")
    lines += ["## Event timeline", ""]
    for e in events:
        payload = redact(json.dumps(e["payload"], ensure_ascii=False, default=str))
        lines.append(f"- {_fmt_ts(e['ts'])} `{e['kind']}` {payload[:300]}")
    return "\n".join(lines) + "\n"


def write_report(store: StateStore, config: Config, issue_id: int) -> Path:
    path = report_path(config, issue_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(store, config, issue_id), encoding="utf-8")
    return path
