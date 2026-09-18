"""The operator view: "What are my agents doing?" in one screen."""
from __future__ import annotations

import time

from agent_team import state_machine as sm
from agent_team.config import Config
from agent_team.issue_contract import strip_title_number
from agent_team.resource_manager import ResourceManager
from agent_team.state_store import IssueRecord, StateStore


def _title(rec: IssueRecord, n: int = 50) -> str:
    """The title for a status line that already shows `#{issue_id}` itself, so the Issue's own
    number is not repeated."""
    return strip_title_number(rec.title)[:n]


def _age(ts: float | None, now: float) -> str:
    if not ts:
        return "-"
    s = int(now - ts)
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _dom(rec: IssueRecord) -> str:
    return ",".join(rec.domains) or "-"


def render(config: Config, store: StateStore, resources: ResourceManager, *, probe_machine: bool = True, now: float | None = None) -> str:
    now = now or time.time()
    recs = store.list()
    by_state: dict[str, list[IssueRecord]] = {}
    for r in recs:
        by_state.setdefault(r.state, []).append(r)
    lines: list[str] = []

    def section(title: str, rows: list[str]) -> None:
        lines.append(title)
        lines.extend(("  " + r) for r in rows) if rows else lines.append("  (none)")
        lines.append("")

    section("RUNNING", [f"#{r.issue_id} {_dom(r)} / {r.assigned_agent or 'worker'} / {r.resource_class} / attempt {r.attempt_number} / "
                        f"{_age(r.started_at, now)} (heartbeat {_age(r.heartbeat_at, now)} ago) — {_title(r)}"
                        for r in by_state.get(sm.WORKING, [])])
    waiting_rows = []
    for r in by_state.get(sm.QUEUED, []):
        deps = [d for d in r.dependencies if (store.get(d) is None or store.get(d).state != sm.DONE)]
        why = f"blocked by #{', #'.join(map(str, deps))}" if deps else "waiting for a slot / locks"
        waiting_rows.append(f"#{r.issue_id} {_dom(r)} / {r.resource_class} / {why} — {_title(r)}")
    for r in by_state.get(sm.CLAIMED, []):
        waiting_rows.append(f"#{r.issue_id} {_dom(r)} / claimed, preparing worktree — {_title(r)}")
    for r in by_state.get(sm.FIX_REQUIRED, []):
        waiting_rows.append(f"#{r.issue_id} {_dom(r)} / repair pending ({r.failure_class}) — {_title(r)}")
    section("WAITING", waiting_rows)
    section("CI", [f"#{r.issue_id} PR #{r.pr_number} / {r.state.lower()} / {_age(r.updated_at, now)} — {_title(r)}"
                   for r in by_state.get(sm.PR_OPEN, []) + by_state.get(sm.CI, [])])
    review_rows = []
    for r in by_state.get(sm.REVIEW, []):
        verdict = (r.review_verdict or "pending").split("@")[0]
        approvals = ",".join(a["kind"] for a in r.approvals) or "none"
        review_rows.append(f"#{r.issue_id} PR #{r.pr_number} / {r.risk} / review {verdict} / approvals {approvals} — {_title(r)}")
    for r in by_state.get(sm.READY, []):
        review_rows.append(f"#{r.issue_id} PR #{r.pr_number} / READY to merge — {_title(r)}")
    for r in by_state.get(sm.MERGED, []):
        review_rows.append(f"#{r.issue_id} PR #{r.pr_number} / merged, smoke pending — {_title(r)}")
    section("REVIEW / MERGE", review_rows)
    section("BLOCKED", [f"#{r.issue_id} / {r.failure_class or 'BLOCKED'} / {(r.last_error or '')[:80]} — {_title(r)}"
                        for r in by_state.get(sm.BLOCKED, [])])
    done = by_state.get(sm.DONE, [])
    section(f"DONE ({len(done)})", [f"#{r.issue_id} PR #{r.pr_number} `{(r.validated_commit or '')[:12]}` — {_title(r)}" for r in done[-5:]])
    snap = resources.snapshot(probe_machine=probe_machine)
    locks = store.locks_held()
    section("RESOURCE", [snap.describe(config),
                         "locks: " + (", ".join(f"{l.name}({l.mode})#{l.issue_id}" for l in locks) or "none"),
                         "heavy jobs: " + (", ".join(f"{j.kind}#{j.issue_id}" for j in resources.heavy_jobs()) or "none")])
    last = store.get_meta("last_tick")
    lines.append(f"last tick: {_age(float(last), now) + ' ago' if last else 'never'}")
    return "\n".join(lines)
