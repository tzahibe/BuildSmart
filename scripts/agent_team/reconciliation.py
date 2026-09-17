"""Restart safety: reconcile the state store with GitHub, branches, worktrees and live processes.

Runs at the start of every tick (cheap) and therefore also on startup. It never duplicates work
and never deletes work it does not know about:

- WORKING with no live agent thread/process (a crashed or restarted orchestrator): requeue if
  the retry budget allows, else BLOCKED. The branch/worktree keep whatever was committed and are
  reconciled, not recreated, on the next start.
- CLAIMED with no thread: the claim never completed -> QUEUED.
- REVIEW with a reviewer marked assigned but no thread: clear it, the review re-runs.
- PR_OPEN/CI/REVIEW/READY whose PR was merged or closed outside the workflow: MERGED / BLOCKED.
- Issues closed on GitHub while still active here: BLOCKED (never silently continue).
- Label drift: the `agent:*` label is re-applied from the state store.
- Stale domain locks and stale heavy jobs are released (see locks.py / state_store.py).
- Worktrees of DONE issues are removed; unknown worktrees under the agent root are reported only.
"""
from __future__ import annotations

import logging
import os

from agent_team import state_machine as sm
from agent_team.labels import STATE_LABEL_PREFIX, label_to_state
from agent_team.worktree_manager import issue_from_branch

log = logging.getLogger("agent_team.reconcile")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def reconcile(orch) -> list[str]:
    actions: list[str] = []
    store = orch.store
    now = orch.clock()
    active = set(orch.active_threads())

    for rec in store.list(tuple(s for s in sm.STATES if s not in sm.TERMINAL_STATES)):
        n = rec.issue_id
        try:
            if rec.state == sm.WORKING and f"worker:{n}" not in active:
                stale_hb = (now - (rec.heartbeat_at or rec.started_at or 0)) > orch.config.stale_after_seconds
                if not _pid_alive(rec.agent_pid) or stale_hb:
                    store.update(n, agent_pid=None, assigned_agent=None)
                    if orch.attempts_remaining(rec):
                        orch.locks.release(n, "stale-worker")
                        orch._set_state(store, n, sm.QUEUED, note="stale worker requeued by reconciliation",
                                        last_error="worker process lost (orchestrator restart or crash)")
                        actions.append(f"#{n}: stale WORKING -> QUEUED (attempt {rec.attempt_number})")
                    else:
                        orch.locks.release(n, "stale-worker-blocked")
                        orch._set_state(store, n, sm.BLOCKED, note="stale worker, retry budget exhausted", failure_class="WORKER_LOST")
                        actions.append(f"#{n}: stale WORKING -> BLOCKED")
                    orch._milestone(n, actions[-1].split(": ", 1)[1] + " (reconciliation).")
                continue
            if rec.state == sm.CLAIMED and f"worker:{n}" not in active:
                orch.locks.release(n, "incomplete-claim")
                orch._set_state(store, n, sm.QUEUED, note="incomplete claim requeued by reconciliation")
                actions.append(f"#{n}: incomplete CLAIMED -> QUEUED")
                continue
            if rec.state == sm.REVIEW and rec.assigned_agent and f"reviewer:{n}" not in active:
                store.update(n, assigned_agent=None, agent_pid=None)
                actions.append(f"#{n}: reviewer slot cleared (no live reviewer)")
            if rec.state in (sm.PR_OPEN, sm.CI, sm.REVIEW, sm.READY) and rec.pr_number:
                try:
                    pr = orch.github.get_pr(rec.pr_number)
                except Exception as exc:  # noqa: BLE001
                    log.warning("#%s: cannot read PR #%s: %s", n, rec.pr_number, exc)
                    pr = None
                if pr is not None:
                    if pr.get("merged"):
                        orch.audit_external_merge(rec, pr)
                        if rec.state == sm.READY:
                            orch._set_state(store, n, sm.MERGED, note="merged externally", validated_commit=pr.get("merge_commit_sha"))
                        else:
                            orch._set_state(store, n, sm.BLOCKED, note="PR merged outside the workflow", failure_class="EXTERNAL_MERGE")
                        actions.append(f"#{n}: PR #{rec.pr_number} merged externally -> {store.get(n).state}")
                        continue
                    if pr.get("state") == "closed":
                        orch.locks.release(n, "pr-closed")
                        orch._set_state(store, n, sm.BLOCKED, note="PR closed without merge", failure_class="PR_CLOSED")
                        actions.append(f"#{n}: PR #{rec.pr_number} closed -> BLOCKED")
                        continue
            if not orch.dry_run:
                try:
                    issue = orch.github.get_issue(n)
                except Exception as exc:  # noqa: BLE001
                    log.warning("#%s: cannot read issue: %s", n, exc)
                    continue
                if issue.get("state") == "closed" and rec.state not in (sm.MERGED, sm.DONE):
                    orch.locks.release(n, "issue-closed")
                    orch._set_state(store, n, sm.BLOCKED, note="issue closed externally", failure_class="ISSUE_CLOSED")
                    actions.append(f"#{n}: issue closed externally -> BLOCKED")
                    continue
                labels = [l["name"] for l in issue.get("labels", [])]
                states = [label_to_state(l) for l in labels if l.startswith(STATE_LABEL_PREFIX)]
                if states != [rec.state]:
                    orch.github.set_state_label(n, rec.state)
                    actions.append(f"#{n}: label {states} -> {rec.state}")
        except Exception as exc:  # noqa: BLE001
            log.exception("#%s: reconciliation step failed", n)
            actions.append(f"#{n}: reconcile error {str(exc)[:120]}")

    if not orch.dry_run:
        drift = orch.check_branch_protection()
        # only report a change or a defect, not the steady state, to keep tick logs quiet
        actions.extend(n for n in drift if "changed" in n or "missing" in n or "NOT protected" in n)

    released = orch.locks.recover_stale(now)
    if released:
        actions.append("stale locks released: " + ", ".join(f"{r.name}(#{r.issue_id})" for r in released))
    orch.resources.heavy_jobs()  # expires stale heavy rows as a side effect of the query path

    try:
        for entry in orch.worktrees.agent_worktrees():
            if entry.path.name.startswith("_"):
                continue
            issue_no = issue_from_branch(orch.config, entry.branch or "")
            rec = store.get(issue_no) if issue_no else None
            if rec is None:
                actions.append(f"unknown agent worktree {entry.path.name} (branch {entry.branch}) left untouched")
            elif rec.state == sm.DONE and not orch.dry_run:
                d = rec.contract_dict()
                orch.worktrees.remove(issue_no, d.get("slug", entry.path.name.split("-", 1)[1]), delete_branch=True, force=True)
                actions.append(f"removed worktree of done #{issue_no}")
    except Exception as exc:  # noqa: BLE001
        log.warning("worktree reconciliation failed: %s", exc)
    return actions
