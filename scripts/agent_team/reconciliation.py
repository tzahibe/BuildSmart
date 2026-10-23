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
- Open pull requests into the base branch that the orchestrator did not create are ADOPTED, so the
  independent review (and the commit status branch protection requires) reports for them too.
"""
from __future__ import annotations

import logging
import os

from agent_team import audit
from agent_team import state_machine as sm
from agent_team.ci.contract_check import resolve_issue_number
from agent_team.issue_contract import ContractError, parse_contract, verification_manifest
from agent_team.labels import DECOMPOSED_LABEL, HOLD_LABEL, STATE_LABEL_PREFIX, label_to_state
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
            if rec.state in (sm.PR_OPEN, sm.CI, sm.REVIEW, sm.READY_FOR_OWNER) and rec.pr_number:
                try:
                    pr = orch.github.get_pr(rec.pr_number)
                except Exception as exc:  # noqa: BLE001
                    log.warning("#%s: cannot read PR #%s: %s", n, rec.pr_number, exc)
                    pr = None
                if pr is not None:
                    if pr.get("merged"):
                        orch.audit_external_merge(rec, pr)
                        if rec.state == sm.READY_FOR_OWNER:
                            # the owner pressed Merge on GitHub while every gate was green: legitimate
                            orch._set_state(store, n, sm.MERGED, note="merged by the owner on GitHub", validated_commit=pr.get("merge_commit_sha"))
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
                    if rec.state == sm.BLOCKED:
                        if rec.kind == "root" and store.get_meta(f"root_closed:{n}") == "1":
                            orch._set_state(store, n, sm.DONE, note="ROOT closed: every child done")
                            actions.append(f"#{n}: closed ROOT -> DONE")
                        continue                       # already blocked: nothing to re-block
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

    try:
        actions.extend(adopt_open_prs(orch))
    except Exception as exc:  # noqa: BLE001
        log.exception("PR adoption failed")
        actions.append(f"PR adoption error {str(exc)[:120]}")
    return actions


def adopt_open_prs(orch) -> list[str]:
    """Recognise open pull requests into the base branch that the orchestrator did not create.

    The independent review is enforceable only through the `review_status_context` commit status
    that branch protection requires, and nothing but the orchestrator publishes it. Until Issue
    #252 the orchestrator recognised work on its own branches only (`issue_from_branch`: the
    `agent/<issue>-<slug>` prefix), so a pull request raised on a `feature/` branch was never
    adopted, never independently reviewed and its status never reported at all — branch protection
    then refused the merge forever, **correctly**, because the code had never had the review the
    check stands for. Same defect shape as the one #209 fixed for CI: the gate was sound and the
    recognition in front of it was too narrow for the way the work is actually delivered.

    The binding is the one gate 1 already implements (`ci.contract_check.resolve_issue_number`):
    the branch name for `agent/<issue>-<slug>`, otherwise the body's single `Closes #<issue>` line.
    An adopted pull request enters the state machine at PR_OPEN and from there runs exactly the
    native path: the same deterministic CI evidence, the same reviewer with the same live contract
    and the same criteria, and the same status for the same exact head SHA. Nothing about the
    review is relaxed — adoption widens only *which* pull requests are reviewed. It differs from
    native work in one direction only, and that direction is stricter: an adopted PR has no repair
    budget (`Orchestrator.attempts_remaining`), because the branch is not the orchestrator's to
    push to, so a red gate or a rejected review blocks it for a human.

    Whatever cannot be adopted still reports `pending` with the reason, never nothing at all, so a
    human can tell "not yet reviewed" from "nothing will ever report".
    """
    actions: list[str] = []
    try:
        prs = orch.github.open_prs_for_base(orch.config.base_branch)
    except Exception as exc:  # noqa: BLE001
        log.warning("cannot list open PRs into %s: %s", orch.config.base_branch, exc)
        return [f"PR adoption skipped: cannot list open PRs ({str(exc)[:120]})"]
    known = {r.pr_number for r in orch.store.list() if r.pr_number}
    for pr in prs:
        try:
            note = adopt_pr(orch, pr, known=known)
        except Exception as exc:  # noqa: BLE001
            log.exception("PR #%s: adoption failed", pr.get("number"))
            note = f"PR #{pr.get('number')}: adoption error {str(exc)[:160]}"
        if note:
            actions.append(note)
    return actions


def adopt_pr(orch, pr: dict, *, known: set[int] | None = None) -> str:
    """Adopt one open pull request, or report why it cannot be adopted — never silently.

    Returns a one-line action note, or "" when there was nothing to do.
    """
    from agent_team.orchestrator import _contract_to_dict   # local: orchestrator imports this module

    config, store = orch.config, orch.store
    pr_no = pr.get("number")
    head = pr.get("head") or {}
    head_ref, head_sha = head.get("ref") or "", head.get("sha") or ""
    url = pr.get("html_url")
    if not pr_no or not head_sha or pr.get("merged") or pr.get("state") != "open":
        return ""
    if known is None:
        known = {r.pr_number for r in store.list() if r.pr_number}
    if pr_no in known:
        return ""      # the orchestrator's own work, or adopted on an earlier tick: untouched

    def not_adopted(why: str, issue_id: int | None = None) -> str:
        published = orch.ensure_pending_review_status(head_sha, f"not reviewed: {why}"[:140],
                                                      issue_id=issue_id, target_url=url)
        if not published:
            return ""
        return f"PR #{pr_no} ({head_ref}): not adopted — {why}; {config.review_status_context}=pending"

    if pr.get("draft"):
        return not_adopted("the pull request is still a draft")
    issue_no = resolve_issue_number(config, pr)
    if issue_no is None:
        return not_adopted("no contract bound: the body must link exactly one `Closes #<issue>`")
    rec = store.get(issue_no)
    if rec is not None:
        if rec.pr_number and rec.pr_number != pr_no:
            return not_adopted(f"#{issue_no} is already delivered by PR #{rec.pr_number}", issue_no)
        if rec.state not in (sm.QUEUED, sm.BLOCKED):
            # an agent holds this Issue (CLAIMED/WORKING/FIX_REQUIRED) or it is already further
            # along: its own path publishes the status and adoption must not race it
            return not_adopted(f"#{issue_no} is tracked and {rec.state}", issue_no)
    try:
        issue = orch.github.get_issue(issue_no)
    except Exception as exc:  # noqa: BLE001
        return not_adopted(f"Issue #{issue_no} cannot be read ({str(exc)[:60]})", issue_no)
    labels = {l["name"] for l in issue.get("labels", [])}
    # exactly the Issue conditions gate 1 applies, on exactly the Issue the binding resolved
    if issue.get("state") != "open":
        return not_adopted(f"Issue #{issue_no} is closed", issue_no)
    assoc = issue.get("author_association", "NONE")
    if assoc not in config.executable_author_associations:
        return not_adopted(f"Issue #{issue_no}'s author association {assoc} is not trusted", issue_no)
    if HOLD_LABEL in labels:
        return not_adopted(f"Issue #{issue_no} is on hold by the owner", issue_no)
    if DECOMPOSED_LABEL in labels:
        return not_adopted(f"Issue #{issue_no} is a decomposed ROOT; a PR belongs to one of its children", issue_no)
    try:
        contract = parse_contract(issue_no, issue.get("title", ""), issue.get("body") or "",
                                  known_locks=config.known_locks, behavior_domains=config.behavior_domains)
    except ContractError as exc:
        return not_adopted(f"Issue #{issue_no}'s contract does not validate: {'; '.join(exc.problems)[:60]}", issue_no)
    if orch.dry_run:
        return f"PR #{pr_no} ({head_ref}): would be adopted for #{issue_no}"
    try:
        # the listing is a snapshot: re-read the one PR about to be adopted, so the status is
        # published for the head it really has now and a PR closed in between is not adopted
        fresh = orch.github.get_pr(pr_no)
    except Exception as exc:  # noqa: BLE001
        return not_adopted(f"PR #{pr_no} cannot be re-read ({str(exc)[:60]})", issue_no)
    if fresh.get("merged") or fresh.get("state") != "open":
        return ""
    head_ref = (fresh.get("head") or {}).get("ref") or head_ref
    head_sha = (fresh.get("head") or {}).get("sha") or head_sha
    try:
        # a real local checkout of the PR's own branch: the reviewer reads the real diff, exactly as
        # it does for native work — a review without the diff would be a weaker review
        info = orch.worktrees.ensure_named(issue_no, head_ref, slug=f"pr{pr_no}")
    except Exception as exc:  # noqa: BLE001
        return not_adopted(f"no local checkout of {head_ref} ({str(exc)[:60]})", issue_no)

    auth = contract.authorization
    kind = "child" if auth.inherited and auth.root_issue else "root"
    root = auth.root_issue or issue_no
    parent = auth.parent_issue or (root if kind == "child" else None)
    store.track(issue_no, title=contract.title, risk=contract.risk, resource_class=contract.resource_class,
                domains=list(contract.domains), dependencies=list(contract.dependencies),
                contract=_contract_to_dict(contract), state=sm.QUEUED, root_issue=root, parent_issue=parent, kind=kind)
    audit.write_contract_snapshot(config, issue_no, contract.to_dict(),
                                  verification_manifest(contract, regression_domains=config.regression_domains))
    if store.get(issue_no).state == sm.QUEUED:
        # CLAIMED -> PR_OPEN is the documented "reconciled an existing PR" path
        orch._set_state(store, issue_no, sm.CLAIMED, note=f"adopting PR #{pr_no} on {head_ref}")
    orch._set_state(store, issue_no, sm.PR_OPEN, note=f"adopted PR #{pr_no} (a branch the orchestrator did not create)",
                    adopted_pr=pr_no, pr_number=pr_no, pr_url=url, branch=head_ref, worktree=str(info.path),
                    attempt_number=1, failure_class=None, last_error=None, validated_commit=None, review_verdict=None)
    store.record_event(issue_no, "pr_adopted", {"pr": pr_no, "head": head_sha, "branch": head_ref,
                                                "binding": "branch-name" if head_ref.startswith(config.branch_prefix) else "closes-line"})
    known.add(pr_no)
    # AC-3: the required check reports from the moment the PR is recognised, not only after a review
    orch.ensure_pending_review_status(head_sha, "independent review not yet run (adopted pull request)",
                                      issue_id=issue_no, target_url=url)
    orch._milestone(issue_no, f"Adopted PR #{pr_no} (`{head_ref}`, head `{head_sha[:12]}`) — a branch this orchestrator did not "
                              f"create, bound to this contract by the PR body's `Closes #{issue_no}` line. It now gets the same "
                              f"deterministic gates and the same independent review as native work, and "
                              f"`{config.review_status_context}` reports for that exact head SHA (`pending` until the review "
                              f"runs, `failure` on REQUEST_CHANGES/BLOCK). The fixer is not dispatched for an adopted branch: "
                              f"a red gate or a rejected review blocks it for a human.")
    return f"PR #{pr_no} ({head_ref}): adopted for #{issue_no} -> PR_OPEN"
