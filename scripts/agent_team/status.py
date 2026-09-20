"""The operator view: "What are my agents doing?" in one screen."""
from __future__ import annotations

import json

import time

from agent_team import state_machine as sm
from agent_team.config import Config
from agent_team.issue_contract import strip_title_number
from agent_team.resource_manager import ResourceManager
from agent_team.state_store import IssueRecord, StateStore
from agent_team.work_reports import short_root_cause


_AGENT_TAG = "[agent] "


def _title(rec: IssueRecord, n: int = 50) -> str:
    """The title for a status line that already shows `#{issue_id}` itself, so the Issue's own
    number is not repeated, and the `[agent] ` tag (every tracked Issue's) is not repeated
    either — matches the pre-#25 `r.title[8:...]` display within the same char budget."""
    t = strip_title_number(rec.title)
    if t.startswith(_AGENT_TAG):
        t = t[len(_AGENT_TAG):]
    return t[:n]


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

    open_recs = [r for r in recs if r.state != sm.DONE]
    roots: dict[int, list[IssueRecord]] = {}
    for r in open_recs:
        roots.setdefault(r.root, []).append(r)
    root_rows = []
    for root_n, members in sorted(roots.items()):
        if len(members) == 1 and members[0].issue_id == root_n:
            r = members[0]
            root_rows.append(f"#{root_n} {_title(r, 60)} — {r.state}")
        else:
            states = ", ".join(f"#{m.issue_id} {m.state}" for m in members)
            root_rows.append(f"#{root_n} — {len(members)} child task(s): {states}")
    section("ROOT ISSUES", root_rows)

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
        review_rows.append(f"#{r.issue_id} PR #{r.pr_number} / {r.risk} / review {verdict} — {_title(r)}")
    for r in by_state.get(sm.MERGED, []):
        review_rows.append(f"#{r.issue_id} PR #{r.pr_number} / merged by the owner, smoke pending — {_title(r)}")
    section("REVIEW / MERGE", review_rows)
    ready_rows = []
    for r in by_state.get(sm.READY_FOR_OWNER, []):
        sha = r.validated_commit or ""
        note = store.notification(f"pr:{r.pr_number}:READY_FOR_OWNER:{sha}") if sha else None
        if note is None:
            tg = "Telegram: not queued" if not config.notify_ready_for_owner else "Telegram: PENDING"
        elif note["status"] == "sent":
            tg = "Telegram: SENT"
        elif note["status"] == "failed":
            tg = f"Telegram: FAILED after {note['attempts']} attempts — {note.get('last_error') or ''}"[:90]
        else:
            tg = f"Telegram: PENDING (attempt {note['attempts']} of {config.notify_max_attempts})" if note["attempts"] else "Telegram: PENDING (remote service not running?)"
        verdict = (r.review_verdict or "-").split("@")[0]
        ready_rows.append(f"#{r.issue_id} / PR #{r.pr_number} / SHA {sha[:12]}\n    CI: PASS  Regression: PASS  Review: {verdict}  {tg}\n    {_title(r, 60)}")
    section("READY FOR OWNER", ready_rows)
    section("BLOCKED", [f"#{r.issue_id} / {r.failure_class or 'BLOCKED'} / {(r.last_error or '')[:80]} — {_title(r)}"
                        for r in by_state.get(sm.BLOCKED, [])])
    done = by_state.get(sm.DONE, [])
    section(f"DONE ({len(done)})", [f"#{r.issue_id} PR #{r.pr_number} `{(r.validated_commit or '')[:12]}` — {_title(r)}" for r in done[-5:]])
    if store.get_meta("scheduler_paused", "0") == "1":
        src = store.get_meta("scheduler_pause_source", "") or "owner"
        lines.insert(0, f"*** SCHEDULER PAUSED ({'usage guard — resumes automatically' if src == 'usage_guard' else 'by the owner'}) — no new claims, no new repairs ***\n")
    if store.get_meta("claims_frozen", "0") == "1":
        lines.insert(0, "*** NEW CLAIMS FROZEN by the owner — in-flight work (reviews, repairs, integrations, rollup) continues ***\n")
    period_raw = store.get_meta("protected_period")
    rollup_raw = store.get_meta("rollup")
    if period_raw or rollup_raw:
        try:
            pr_line = ""
            if period_raw:
                pd = json.loads(period_raw)
                pr_line = f"PROTECTED PERIOD: {pd['kind']} {pd['name']} {pd['start']} → {pd['end']} — integrating into {pd['branch']} (main untouched)"
            if rollup_raw:
                rd = json.loads(rollup_raw)
                pr_line += (" | " if pr_line else "") + f"ROLLUP: Issue #{rd['issue']} / PR #{rd['pr']} ({len(rd.get('children', []))} Issues)"
            lines.insert(0, pr_line + "\n")
        except Exception:  # noqa: BLE001
            pass
    section("INTEGRATED (in the period's branch, land with the rollup)",
            [f"#{r.issue_id} PR #{r.pr_number} `{(r.validated_commit or '')[:12]}` — {r.title[:50]}" for r in by_state.get(sm.INTEGRATED, [])])
    usage_raw = store.get_meta("usage_last")
    if usage_raw:
        try:
            u = json.loads(usage_raw)
            lines.append(f"USAGE\n  session {u.get('session_percent')}% (resets {u.get('session_resets') or '?'})  week {u.get('week_percent')}% (resets {u.get('week_resets') or '?'})\n")
        except Exception:  # noqa: BLE001
            pass
    snap = resources.snapshot(probe_machine=probe_machine)
    locks = store.locks_held()
    section("AVAILABLE WORKERS", [f"{max(0, config.max_worker_agents - snap.workers_running)} / {config.max_worker_agents}  "
                                  f"(reviewers {snap.reviewers_running}/{config.max_reviewer_agents})"])
    section("RESOURCES", [f"weighted capacity {snap.weighted_used} / {config.weighted_capacity}",
                          f"heavy jobs {snap.heavy_running} / {config.heavy_job_concurrency}",
                          snap.describe(config),
                          "locks: " + (", ".join(f"{l.name}({l.mode})#{l.issue_id}" for l in locks) or "none")])
    blockers = []
    for r in by_state.get(sm.QUEUED, []):
        deps = [d for d in r.dependencies if (store.get(d) is None or store.get(d).state != sm.DONE)]
        if deps:
            blockers.append(f"#{r.issue_id} waits for #{', #'.join(map(str, deps))}")
    for l in locks:
        blockers.append(f"{l.name} locked ({l.mode}) by #{l.issue_id}")
    section("BLOCKERS", blockers)
    last = store.get_meta("last_tick")
    lines.append(f"last tick: {_age(float(last), now) + ' ago' if last else 'never'}")
    return "\n".join(lines)


def render_compact(config: Config, store: StateStore, resources: ResourceManager, *, probe_machine: bool = False, now: float | None = None) -> str:
    """The Telegram-sized status: one line per item."""
    now = now or time.time()
    recs = store.list()
    by: dict[str, list[IssueRecord]] = {}
    for r in recs:
        by.setdefault(r.state, []).append(r)
    out: list[str] = []
    if store.get_meta("scheduler_paused", "0") == "1":
        src = store.get_meta("scheduler_pause_source", "") or "owner"
        out.append("⏸ מושהה אוטומטית — מכסת השימוש; יחודש לבד כשהיא תתחדש\n" if src == "usage_guard" else "⏸ מושהה — אין claims/תיקונים חדשים (/resume להמשך)\n")
    period_raw = store.get_meta("protected_period")
    if period_raw:
        try:
            pd = json.loads(period_raw)
            out.append(f"📅 מצב {'סוף שבוע' if pd['kind'] == 'SHABBAT' else 'חג'} ({pd['start']} → {pd['end']}): מיזוגים ל-{pd['branch']}, main לא נגע\n")
        except Exception:  # noqa: BLE001
            pass
    usage_raw = store.get_meta("usage_last")
    if usage_raw:
        try:
            u = json.loads(usage_raw)
            out.append(f"מכסה: session {u.get('session_percent')}% · שבועי {u.get('week_percent')}% (מתחדש {u.get('week_resets') or '?'})\n")
        except Exception:  # noqa: BLE001
            pass

    def block(title: str, rows: list[str]) -> None:
        out.append(title)
        out.extend(rows or ["(אין)"])
        out.append("")

    block("רץ עכשיו", [f"#{r.issue_id} {_title(r, 50)} / {(r.assigned_agent or 'worker').split(':')[-1]} / {r.risk} / {_age(r.started_at, now)}"
                      for r in by.get(sm.WORKING, [])])
    waiting = []
    for r in by.get(sm.QUEUED, []):
        deps = [d for d in r.dependencies if (store.get(d) is None or store.get(d).state != sm.DONE)]
        waiting.append(f"#{r.issue_id} {_title(r, 45)} / " + (f"ממתין ל-#{', #'.join(map(str, deps))}" if deps else "ממתין למקום פנוי"))
    for r in by.get(sm.FIX_REQUIRED, []):
        cause = f" — {short_root_cause(r.last_error)}" if r.last_error else ""
        waiting.append(f"#{r.issue_id} {_title(r, 45)} / ממתין לתיקון ({r.failure_class}){cause}")
    block("ממתינים", waiting)
    block("CI", [f"#{r.issue_id} / PR #{r.pr_number} / {r.state.lower().replace('_', ' ')}" for r in by.get(sm.PR_OPEN, []) + by.get(sm.CI, []) + by.get(sm.REVIEW, [])])
    block("מוכן לאישורך (READY FOR OWNER)", [f"PR #{r.pr_number} / #{r.issue_id} {_title(r, 45)} / SHA {(r.validated_commit or '')[:8]}" for r in by.get(sm.READY_FOR_OWNER, [])])
    block("אוחד לענף האינטגרציה (יגיע ב-rollup)", [f"#{r.issue_id} / PR #{r.pr_number}" for r in by.get(sm.INTEGRATED, [])])
    block("מוזג (smoke רץ)", [f"#{r.issue_id} / PR #{r.pr_number}" for r in by.get(sm.MERGED, [])])
    blocked_rows = []
    for r in by.get(sm.BLOCKED, []):
        cause = f" — {short_root_cause(r.last_error)}" if r.last_error else ""
        blocked_rows.append(f"#{r.issue_id} / {r.failure_class or 'BLOCKED'}{cause}")
    block("חסומים", blocked_rows)
    snap = resources.snapshot(probe_machine=probe_machine)
    machine = "" if snap.free_memory_gb == float("inf") else f"\nCPU {snap.cpu_percent:.0f}%  free RAM {snap.free_memory_gb:.1f} GiB"
    out.append(f"משאבים\nworkers {snap.workers_running}/{config.max_worker_agents}  reviewers {snap.reviewers_running}/{config.max_reviewer_agents}  "
               f"heavy jobs {snap.heavy_running}/{config.heavy_job_concurrency}{machine}")
    done = by.get(sm.DONE, [])
    if done:
        out.append(f"\nהושלמו: {len(done)} (אחרון #{done[-1].issue_id})")
    return "\n".join(out).strip()
