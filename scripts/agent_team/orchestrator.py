"""The orchestrator: a deterministic loop over the issue state machine.

    tick():  reconcile -> poll (agent:queued) -> schedule (start workers) -> advance (every
             tracked issue one step: PR_OPEN -> CI -> REVIEW -> READY_FOR_OWNER -> (owner merges) -> MERGED -> DONE, or
             FIX_REQUIRED -> WORKING, or -> BLOCKED)

Long-running agent runs (worker, repair, reviewer) execute in threads with their own SQLite
connection; the main loop never blocks on a model. Every state change is a compare-and-set in
the state store and is mirrored to the Issue's `agent:*` label; every milestone is a concise
Issue comment; every agent run is a redacted JSON record under `.agent/logs/runs/`.

DRY_RUN: polls and schedules against a separate state file, prints the proposed assignments,
and performs no GitHub write, no spawn, no push, no merge.

Governance: an Issue runs only with `agent:queued` AND the owner's `owner:approved`; the loop
stops at READY_FOR_OWNER and never merges — `owner_merge()` is the only merge path and it is
invoked exclusively by an explicit owner command (Telegram CONFIRM MERGE); an owner merge on
GitHub is detected and audited. The owner can pause new claims/repairs at any time.
"""
from __future__ import annotations

import fcntl
import json
import re
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_team import audit, ci_evidence, merge_policy, prompts, scheduler
from agent_team import state_machine as sm
from agent_team.agent_runner import DOMAIN_LEAD, REVIEWER, WORKER, AgentRunner, AgentRunResult, AgentRunSpec
from agent_team.config import Config
from agent_team.failure_classifier import (
    ENVIRONMENT_FAILURE, FLAKY_TEST, INFRA_FAILURE, MERGE_CONFLICT, REVIEW_REJECTED, Classification, FailureInput, classify,
)
from agent_team.issue_contract import ContractError, IssueContract, parse_contract, verification_manifest, child_scope_problems
from agent_team import integration_mode as im
from agent_team.labels import DECOMPOSED_LABEL, HOLD_LABEL, ROLLUP_LABEL, STATE_LABEL_PREFIX, metadata_labels
from agent_team.protected_periods import Calendar, Period
from agent_team.locks import LockManager, effective_locks
from agent_team.pr_body import render_pr_body
from agent_team.resource_manager import ResourceManager, ResourceProbe
from agent_team.schemas import DOMAIN_LEAD_BRIEF_SCHEMA, REVIEW_VERDICT_SCHEMA, WORKER_REPORT_SCHEMA
from agent_team.state_store import IssueRecord, StateStore, TransitionConflict
from agent_team.usage_guard import UsageGuard, UsageSnapshot, looks_rate_limited, probe_usage
from agent_team.github_client import GitHubError
from agent_team.worktree_manager import GitError, MergeConflict, WorktreeManager, run_git

log = logging.getLogger("agent_team.orchestrator")


class OrchestratorAlreadyRunning(RuntimeError):
    pass


@dataclass
class TickReport:
    polled: list[int] = field(default_factory=list)
    started: list[int] = field(default_factory=list)
    waiting: dict[int, str] = field(default_factory=dict)
    advanced: dict[int, str] = field(default_factory=dict)
    reconciled: list[str] = field(default_factory=list)
    errors: dict[int, str] = field(default_factory=dict)

    def summary(self) -> str:
        parts = []
        if self.reconciled:
            parts.append("reconciled: " + "; ".join(self.reconciled))
        parts.append(f"polled {self.polled or '-'}")
        parts.append(f"started {self.started or '-'}")
        if self.waiting:
            parts.append("waiting " + ", ".join(f"#{k} ({v})" for k, v in self.waiting.items()))
        if self.advanced:
            parts.append("advanced " + ", ".join(f"#{k}: {v}" for k, v in self.advanced.items()))
        if self.errors:
            parts.append("errors " + ", ".join(f"#{k}: {v}" for k, v in self.errors.items()))
        return " | ".join(parts)


@dataclass
class AuthDecision:
    ok: bool
    kind: str                 # root | child
    root: int
    parent: int | None
    source: str               # owner | inherited | none
    problems: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(self, config: Config, *, github, runner: AgentRunner, dry_run: bool = False,
                 probe: ResourceProbe | None = None, clock=time.time, worktrees: WorktreeManager | None = None,
                 store_path: Path | None = None):
        self.config = config
        self.github = github
        self.runner = runner
        self.dry_run = dry_run
        self.clock = clock
        db = store_path or (config.path(config.state_dir) / ("dry-run.sqlite3" if dry_run else "orchestrator.sqlite3"))
        self._db_path = db
        self.store = StateStore(db, clock=clock)
        self.worktrees = worktrees or WorktreeManager(config)
        self.resources = ResourceManager(config, self.store, probe)
        self.locks = LockManager(self.store, config)
        self.threads: dict[str, threading.Thread] = {}
        self._threads_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()        # set when a run finishes: the loop re-plans immediately (work stealing)
        self._draining = False                # SIGTERM: finish running agents, start nothing new, then exit
        self._drain_started = 0.0
        self._lock_fh = None
        self._ci_started: dict[int, float] = {}
        self.blocking_decisions: list[str] = []
        self.usage = UsageGuard(config.usage_pause_at_percent, config.usage_resume_below_percent, enabled=config.usage_guard_enabled)
        self.usage_prober = None          # callable() -> UsageSnapshot; None = the real `claude -p /usage`
        self._last_usage_probe = 0.0
        # Weekend / holiday integration mode (governance §26–§41). The active period is persisted in
        # meta so a restart resumes it; the integration branch becomes the base for new work.
        self.calendar = Calendar.from_config(config.protected_periods_raw)
        self.period: Period | None = self._load_period()
        if self.period:
            self.worktrees.base_override = self.period.branch

    # -- process singleton --------------------------------------------------------------------
    def acquire_singleton(self) -> None:
        path = self.config.path(self.config.state_dir) / ("dry-run.lock" if self.dry_run else "orchestrator.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise OrchestratorAlreadyRunning(f"another orchestrator holds {path}") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._lock_fh = fh

    def release_singleton(self) -> None:
        if self._lock_fh:
            try:
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_fh.close()
                self._lock_fh = None

    def thread_store(self) -> StateStore:
        return StateStore(self._db_path, clock=self.clock)

    # -- helpers ------------------------------------------------------------------------------
    def _contract(self, rec: IssueRecord) -> IssueContract:
        d = rec.contract_dict()
        return parse_contract(rec.issue_id, d["title"], _body_from_dict(d), known_locks=self.config.known_locks,
                              behavior_domains=self.config.behavior_domains)

    def refresh_contract(self, store: StateStore, rec: IssueRecord) -> IssueContract | None:
        """Re-read the live Issue and adopt an amended contract (the Team Lead may extend/clarify it
        while the PR is open — gate 1 validates the live Issue, so review and merge must use it too).
        Returns None (and blocks the Issue) when the live contract no longer validates."""
        try:
            issue = self.github.get_issue(rec.issue_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("#%s: cannot re-read the Issue (%s); using the stored contract", rec.issue_id, exc)
            return self._contract(rec)
        try:
            live = parse_contract(rec.issue_id, issue.get("title", ""), issue.get("body") or "", known_locks=self.config.known_locks,
                                  behavior_domains=self.config.behavior_domains)
        except ContractError as exc:
            self.locks.release(rec.issue_id, "contract-invalid")
            self._set_state(store, rec.issue_id, sm.BLOCKED, note="live contract no longer validates", failure_class="SPEC_MISMATCH",
                            last_error="; ".join(exc.problems)[:1000])
            self._milestone(rec.issue_id, "Blocked: the Issue contract was edited and no longer validates:\n" + "\n".join(f"- {p}" for p in exc.problems))
            return None
        new_dict = _contract_to_dict(live)
        if new_dict != rec.contract_dict():
            before = rec.contract_dict()
            store.track(rec.issue_id, title=live.title, risk=live.risk, resource_class=live.resource_class, domains=list(live.domains),
                        dependencies=list(live.dependencies), contract=new_dict)
            audit.write_contract_snapshot(self.config, rec.issue_id, live.to_dict(),
                                          verification_manifest(live, regression_domains=self.config.regression_domains))
            store.record_event(rec.issue_id, "contract_updated", {
                "acs_before": before.get("body", "").count("\n- AC-"), "acs_after": len(live.acceptance_criteria),
                "risk": [before.get("risk"), live.risk], "resource_class": [before.get("resource_class"), live.resource_class]})
            self._milestone(rec.issue_id, f"Contract refreshed from the live Issue: {len(live.acceptance_criteria)} acceptance criteria, "
                                          f"risk {live.risk}, resource {live.resource_class}. Review and merge use this version.")
        return live

    def _set_state(self, store: StateStore, issue_id: int, state: str, *, note: str = "", **fields_to_set) -> IssueRecord:
        rec = store.transition(issue_id, state, note=note or None, **fields_to_set)
        if not self.dry_run:
            try:
                self.github.set_state_label(issue_id, state)
            except Exception as exc:  # noqa: BLE001 — label drift is repaired by reconciliation
                log.warning("label update for #%s -> %s failed: %s", issue_id, state, exc)
        return rec

    def _milestone(self, issue_id: int, text: str) -> None:
        log.info("#%s: %s", issue_id, text.splitlines()[0][:200])
        if self.dry_run:
            return
        try:
            self.github.comment(issue_id, f"**[agent-team]** {text}")
        except Exception as exc:  # noqa: BLE001
            log.warning("comment on #%s failed: %s", issue_id, exc)

    # -- the independent-review commit status (enforced by branch protection) ----------------
    def _publish_review_status(self, store: StateStore, issue_id: int, sha: str, state: str, description: str) -> None:
        """success only for an APPROVE of this exact SHA; failure for REQUEST_CHANGES/BLOCK; pending otherwise."""
        ctx = self.config.review_status_context
        store.record_event(issue_id, "review_status", {"sha": sha, "state": state, "description": description})
        if self.dry_run:
            log.info("DRY-RUN would set status %s=%s on %s (%s)", ctx, state, sha[:12], description)
            return
        try:
            rec = store.get(issue_id)
            self.github.set_commit_status(sha, state, ctx, description, target_url=rec.pr_url if rec else None)
        except Exception as exc:  # noqa: BLE001
            log.warning("#%s: publishing %s=%s on %s failed: %s", issue_id, ctx, state, sha[:12], exc)

    def _ensure_review_status(self, store: StateStore, rec: IssueRecord, head: str) -> str:
        """Make GitHub's status for `head` agree with the store (after restarts / failed publishes)."""
        verdict, _, sha = (rec.review_verdict or "").partition("@")
        try:
            current = self.github.combined_status(head).get(self.config.review_status_context, {}).get("state")
        except Exception:  # noqa: BLE001
            current = None
        if verdict == "APPROVE" and sha == head:
            if current != "success":
                self._publish_review_status(store, rec.issue_id, head, "success", f"independent review APPROVE for {head[:12]}")
            return "success"
        if verdict in ("REQUEST_CHANGES", "BLOCK") and sha == head:
            if current != "failure":
                self._publish_review_status(store, rec.issue_id, head, "failure", f"independent review {verdict} for {head[:12]}")
            return "failure"
        if current != "pending":
            self._publish_review_status(store, rec.issue_id, head, "pending",
                                        "stale: review required for this SHA" if rec.review_verdict else "independent review not yet run")
        return "pending"

    def _thread_active(self, key: str) -> bool:
        with self._threads_lock:
            t = self.threads.get(key)
            return bool(t and t.is_alive())

    def _spawn(self, key: str, target, *args) -> None:
        with self._threads_lock:
            if key in self.threads and self.threads[key].is_alive():
                raise RuntimeError(f"{key} already running")
            t = threading.Thread(target=self._guard, args=(key, target, *args), name=key, daemon=True)
            self.threads[key] = t
            t.start()

    def _guard(self, key: str, target, *args) -> None:
        try:
            target(*args)
            # A finished run frees a slot: wake the loop so the next executable task starts at once
            # instead of waiting for the poll interval (work stealing).
            self._wake.set()
        except Exception:  # noqa: BLE001
            log.exception("thread %s crashed", key)

    def active_threads(self) -> list[str]:
        with self._threads_lock:
            return [k for k, t in self.threads.items() if t.is_alive()]

    def wait_for_threads(self, timeout: float = 5.0) -> None:
        with self._threads_lock:
            threads = list(self.threads.values())
        for t in threads:
            t.join(timeout=timeout)

    def attempts_remaining(self, rec: IssueRecord) -> bool:
        """attempt_number counts worker runs; repairs allowed on top of the first run."""
        return max(0, rec.attempt_number - 1) < self.config.max_repair_attempts

    # -- tick ---------------------------------------------------------------------------------
    def tick(self) -> TickReport:
        report = TickReport()
        from agent_team.reconciliation import reconcile  # local import: reconciliation imports this module's names
        try:
            report.reconciled = reconcile(self)
        except Exception as exc:  # noqa: BLE001
            log.exception("reconciliation failed")
            report.reconciled = [f"reconcile error: {exc}"]
        try:
            self.check_usage()
        except Exception as exc:  # noqa: BLE001
            log.warning("usage probe failed: %s", exc)
        try:
            changed = self.check_period()
            if changed:
                report.reconciled.append(changed)
        except Exception as exc:  # noqa: BLE001
            log.exception("protected-period check failed")
            report.errors[-2] = f"period: {exc}"
        try:
            report.polled = self.poll()
        except Exception as exc:  # noqa: BLE001
            log.exception("poll failed")
            report.errors[0] = f"poll: {exc}"
        try:
            for d in self.schedule():
                if d.starts:
                    report.started.append(d.issue_id)
                else:
                    report.waiting[d.issue_id] = d.reason
        except Exception as exc:  # noqa: BLE001
            log.exception("schedule failed")
            report.errors[-1] = f"schedule: {exc}"
        for rec in self.store.list((sm.PR_OPEN, sm.CI, sm.REVIEW, sm.FIX_REQUIRED, sm.READY_FOR_OWNER, sm.MERGED)):
            try:
                outcome = self.advance(rec)
                if outcome:
                    report.advanced[rec.issue_id] = outcome
            except TransitionConflict as exc:
                log.warning("#%s: %s", rec.issue_id, exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("advance #%s failed", rec.issue_id)
                report.errors[rec.issue_id] = str(exc)[:200]
        try:
            report.reconciled.extend(self.close_completed_roots())
        except Exception as exc:  # noqa: BLE001
            log.warning("root completion check failed: %s", exc)
        self.store.set_meta("last_tick", str(self.clock()))
        return report

    def close_completed_roots(self) -> list[str]:
        """A decomposed ROOT is done when every child is done: close it with the summary (the ROOT was
        never a task itself). Idempotent — a closed ROOT is skipped."""
        out: list[str] = []
        roots = {r.root for r in self.store.list() if r.kind == "child"}
        for root_n in sorted(roots):
            children = self.store.children_of(root_n)
            if not children or any(c.state != sm.DONE for c in children):
                continue
            if self.store.get_meta(f"root_closed:{root_n}") == "1":
                continue
            try:
                root = self.github.get_issue(root_n)
            except Exception:  # noqa: BLE001
                continue
            if root.get("state") != "open":
                self.store.set_meta(f"root_closed:{root_n}", "1")
                continue
            summary = "\n".join(f"- #{c.issue_id} — PR #{c.pr_number} `{(c.validated_commit or '')[:12]}`" for c in children)
            if not self.dry_run:
                try:
                    self.github.comment(root_n, f"**[agent-team]** Every child Issue of this ROOT is done and merged by the owner:\n{summary}\n\nClosing the ROOT.")
                    self.github.set_state_label(root_n, sm.DONE)
                    self.github.close_issue(root_n)
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not close ROOT #%s: %s", root_n, exc)
                    continue
            self.store.set_meta(f"root_closed:{root_n}", "1")
            self.store.record_event(root_n, "root_done", {"children": [c.issue_id for c in children]})
            out.append(f"ROOT #{root_n} closed: all {len(children)} children done")
        return out

    def run(self, *, once: bool = False) -> None:
        self.acquire_singleton()
        previous = {}
        try:
            if not once:
                # SIGTERM (launchd restart, `agentctl stop`) drains: running agents finish, nothing new starts.
                # SIGINT (Ctrl-C, `agentctl stop --now`) or a second SIGTERM stops immediately.
                previous[signal.SIGTERM] = signal.signal(signal.SIGTERM, lambda *_: self.request_drain())
                previous[signal.SIGINT] = signal.signal(signal.SIGINT, lambda *_: self.request_stop())
            while True:
                report = self.tick()
                log.info("tick: %s", report.summary())
                if once or self._stop.is_set():
                    break
                if self._draining and self.drain_complete():
                    log.info("drain complete: no agent running — exiting for restart")
                    break
                self._wake.wait(5.0 if self._draining else self.config.poll_interval_seconds)
                self._wake.clear()
                if self._stop.is_set():
                    break
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            self.shutdown()

    def request_drain(self) -> None:
        """Graceful stop: no new claims/repairs/reviews; running agents finish; then exit."""
        if self._draining:
            self.request_stop()       # a second request means "now"
            return
        self._draining = True
        self._drain_started = self.clock()
        log.info("drain requested: finishing running agents, starting nothing new")
        self._wake.set()

    def request_stop(self) -> None:
        self._stop.set()
        self._wake.set()

    @property
    def draining(self) -> bool:
        return self._draining

    def drain_complete(self) -> bool:
        with self._threads_lock:
            alive = [n for n, t in self.threads.items() if t.is_alive()]
        if not alive:
            return True
        if self.clock() - self._drain_started > self.config.drain_timeout_seconds:
            log.warning("drain timeout after %ss with %s still running — stopping now", self.config.drain_timeout_seconds, alive)
            return True
        return False

    def shutdown(self) -> None:
        self._stop.set()
        term = getattr(self.runner, "terminate_all", None)
        if callable(term):
            term()
        self.wait_for_threads(timeout=10)
        self.release_singleton()

    # -- poll ---------------------------------------------------------------------------------
    def poll(self) -> list[int]:
        """Track every executable Issue exactly once. Idempotent.

        Executable means: a ROOT Issue carrying the owner's `owner:approved` label (the owner defines the
        product backlog by creating/approving ROOT Issues), or a child Issue whose contract inherits its
        authorization from an owner-approved ROOT and stays inside that ROOT's scope. `agent:hold`
        (owner) keeps an authorized Issue out of execution. The orchestrator queues executable Issues
        itself — the Team Lead needs no further owner approval to claim, queue or run them."""
        new: list[int] = []
        self.awaiting_owner: list[int] = []
        self.on_hold: list[int] = []
        seen: set[int] = set()
        candidates: list[dict] = []
        for label in self.config.poll_labels:
            for issue in self.github.list_issues(labels=(label,), state="open"):
                if issue["number"] not in seen:
                    seen.add(issue["number"])
                    candidates.append(issue)
        for issue in sorted(candidates, key=lambda i: i["number"]):
            number = issue["number"]
            existing = self.store.get(number)
            if existing is not None and existing.state != sm.QUEUED:
                continue  # already claimed or further along: the label is stale, reconciliation fixes it
            if issue.get("author_association", "NONE") not in self.config.executable_author_associations:
                log.warning("#%s ignored: author association %s is not executable", number, issue.get("author_association"))
                continue
            labels = {l["name"] for l in issue.get("labels", [])}
            if DECOMPOSED_LABEL in labels:
                # a ROOT executed through its children is never run as a task itself — including one
                # that was tracked before the label appeared
                if existing is not None and existing.state == sm.QUEUED:
                    self._set_state(self.store, number, sm.BLOCKED, note="decomposed ROOT: executed through its children",
                                    failure_class="DECOMPOSED")
                continue
            try:
                contract = parse_contract(number, issue.get("title", ""), issue.get("body") or "", known_locks=self.config.known_locks,
                                          behavior_domains=self.config.behavior_domains)
            except ContractError as exc:
                if existing is None:
                    self._reject_contract(number, exc.problems)
                continue
            auth = self.authorization_of(number, labels, contract)
            if not auth.ok:
                if auth.kind == "child":
                    self._reject_child(number, contract, auth.problems, existing)
                else:
                    self.awaiting_owner.append(number)
                continue
            if HOLD_LABEL in labels:
                self.on_hold.append(number)
                if existing is not None and existing.state == sm.QUEUED:
                    self._set_state(self.store, number, sm.BLOCKED, note="on hold by the owner", failure_class="OWNER_HOLD")
                continue
            manifest = verification_manifest(contract, regression_domains=self.config.regression_domains)
            self.store.track(number, title=contract.title, risk=contract.risk, resource_class=contract.resource_class,
                             domains=list(contract.domains), dependencies=list(contract.dependencies),
                             contract=_contract_to_dict(contract), root_issue=auth.root, parent_issue=auth.parent, kind=auth.kind)
            audit.write_contract_snapshot(self.config, number, contract.to_dict(), manifest)
            if "agent:queued" not in labels and not self.dry_run:
                try:
                    self.github.set_state_label(number, sm.QUEUED)
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not label #%s queued: %s", number, exc)
            if existing is None:
                self.store.record_event(number, "authorized", {"kind": auth.kind, "root": auth.root, "source": auth.source})
                new.append(number)
        return new

    def authorization_of(self, number: int, labels: set[str], contract: IssueContract) -> "AuthDecision":
        """Deterministic execution authorization: ROOT by the owner's label, child by inheritance."""
        if self.config.owner_approval_label in labels:
            return AuthDecision(True, "root", number, None, "owner")
        auth = contract.authorization
        if not auth.inherited or not auth.root_issue:
            return AuthDecision(False, "root", number, None, "none", ["no owner:approved label and no inherited authorization"])
        root_n = auth.root_issue
        problems: list[str] = []
        try:
            root = self.github.get_issue(root_n)
        except Exception as exc:  # noqa: BLE001
            return AuthDecision(False, "child", root_n, auth.parent_issue, "inherited", [f"ROOT #{root_n} cannot be read: {exc}"])
        root_labels = {l["name"] for l in root.get("labels", [])}
        if self.config.owner_approval_label not in root_labels:
            problems.append(f"ROOT #{root_n} is not owner-approved")
        if root.get("state") != "open" and DECOMPOSED_LABEL not in root_labels:
            problems.append(f"ROOT #{root_n} is {root.get('state')}")
        try:
            root_contract = parse_contract(root_n, root.get("title", ""), root.get("body") or "", known_locks=self.config.known_locks,
                                           behavior_domains=self.config.behavior_domains)
        except ContractError as exc:
            problems.append(f"ROOT #{root_n} contract invalid: {'; '.join(exc.problems[:3])}")
            root_contract = None
        if root_contract is not None:
            problems.extend(child_scope_problems(contract, root_contract, effective=lambda c: effective_locks(c, self.config)))
        return AuthDecision(not problems, "child", root_n, auth.parent_issue or root_n, "inherited", problems)

    def _reject_child(self, number: int, contract: IssueContract, problems: list[str], existing: IssueRecord | None) -> None:
        """A child that escapes its ROOT's scope (or whose ROOT is not authorized) never executes."""
        text = "Child Issue refused — it does not inherit valid authorization from its ROOT:\n\n" + \
               "\n".join(f"- {p}" for p in problems) + \
               "\n\nNarrow the child to the ROOT's domains/locks/budget, or ask the owner to create/approve a new ROOT for the extra scope (PROPOSED PRODUCT FOLLOW-UP)."
        log.warning("#%s: child refused: %s", number, problems)
        if existing is not None:
            self._set_state(self.store, number, sm.BLOCKED, note="child outside ROOT scope", failure_class="SCOPE_ESCAPE", last_error="; ".join(problems)[:1000])
        else:
            self.store.track(number, title=contract.title, risk=contract.risk, resource_class=contract.resource_class,
                             domains=list(contract.domains), dependencies=list(contract.dependencies), contract=_contract_to_dict(contract),
                             state=sm.BLOCKED, root_issue=contract.authorization.root_issue, parent_issue=contract.authorization.parent_issue, kind="child")
            self.store.update(number, failure_class="SCOPE_ESCAPE", last_error="; ".join(problems)[:1000])
        self.store.record_event(number, "child_refused", {"problems": problems})
        if self.dry_run:
            return
        try:
            self.github.set_state_label(number, sm.BLOCKED)
            self.github.comment(number, f"**[agent-team]** {text}")
        except Exception as exc:  # noqa: BLE001
            log.warning("could not mark #%s blocked: %s", number, exc)

    def _reject_contract(self, number: int, problems: list[str]) -> None:
        text = "Contract does not validate — moved back to `agent:draft`. Fix and re-queue with `agentctl issue queue`.\n\n" + \
               "\n".join(f"- {p}" for p in problems)
        log.warning("#%s: invalid contract: %s", number, problems)
        if self.dry_run:
            return
        try:
            self.github.set_state_label(number, "DRAFT")
            self.github.comment(number, f"**[agent-team]** {text}")
        except Exception as exc:  # noqa: BLE001
            log.warning("could not mark #%s as draft: %s", number, exc)

    # -- schedule -----------------------------------------------------------------------------
    def paused(self) -> bool:
        return self.store.get_meta("scheduler_paused", "0") == "1"

    def set_paused(self, paused: bool, *, source: str, who: str | None = None, reason: str = "") -> None:
        self.store.set_meta("scheduler_paused", "1" if paused else "0")
        self.store.set_meta("scheduler_pause_source", source if paused else "")
        self.store.record_event(None, "scheduler_paused" if paused else "scheduler_resumed",
                                {"source": source, "by": who, "reason": reason})

    def pause_source(self) -> str:
        return self.store.get_meta("scheduler_pause_source", "") or ""

    # -- subscription usage guard -------------------------------------------------------------
    def check_usage(self, *, force: bool = False) -> UsageSnapshot | None:
        """Probe `/usage`; pause at the threshold, resume automatically after the window resets.
        Never lifts a pause the owner set by hand."""
        if not self.config.usage_guard_enabled or self.dry_run and self.usage_prober is None:
            return None
        now = self.clock()
        if not force and now - self._last_usage_probe < self.config.usage_probe_every_seconds:
            return None
        self._last_usage_probe = now
        snap = self.usage_prober() if self.usage_prober else probe_usage(self._claude_binary())
        self.store.set_meta("usage_last", json.dumps(snap.to_dict()))
        auto_paused = self.paused() and self.pause_source() == "usage_guard"
        decision = self.usage.evaluate(snap, auto_paused=auto_paused)
        if decision == "pause":
            self.set_paused(True, source="usage_guard", who="orchestrator", reason=snap.describe())
            self.store.record_event(None, "usage_pause", snap.to_dict())
            self._owner_notice("usage_pause:" + str(int(now)),
                               f"⛔ מכסת השימוש הגיעה ל-{snap.worst_percent:.0f}% ({snap.describe()}).\n"
                               f"עצרתי: אין claims/workers/reviews/תיקונים חדשים; סוכנים שרצים מסיימים את הריצה הנוכחית. "
                               f"אחדש אוטומטית כשהמכסה תתחדש (session: {snap.session_resets or '?'}; week: {snap.week_resets or '?'}).")
            log.warning("usage guard: paused at %s", snap.describe())
        elif decision == "resume":
            self.set_paused(False, source="usage_guard", who="orchestrator", reason=snap.describe())
            self.store.record_event(None, "usage_resume", snap.to_dict())
            self._owner_notice("usage_resume:" + str(int(now)), f"▶️ המכסה התחדשה ({snap.describe()}). הסוכנים ממשיכים.")
            log.info("usage guard: resumed at %s", snap.describe())
        return snap

    def _claude_binary(self) -> str:
        from agent_team.agent_runner import resolve_claude_binary
        try:
            return resolve_claude_binary(self.config.claude_binary)
        except FileNotFoundError:
            return "claude"

    def _owner_notice(self, key: str, text: str) -> None:
        """A Telegram note to the owner through the outbox (deduplicated by key)."""
        try:
            self.store.enqueue_notification("lead_update", key, None, text)
        except Exception:  # noqa: BLE001
            pass

    def rate_limited_run(self, result: AgentRunResult) -> bool:
        return (not result.ok) and looks_rate_limited(result.error or result.result_text)

    ACTIVE_STATES = (sm.CLAIMED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.REVIEW, sm.FIX_REQUIRED, sm.MERGED)

    def active_issue_count(self) -> int:
        return len(self.store.list(self.ACTIVE_STATES))

    def active_roots(self) -> set[int]:
        """ROOT Issues with work in flight. Children count toward their ROOT; READY_FOR_OWNER does not
        count — a PR waiting for the owner's merge must never stop unrelated work."""
        return {r.root for r in self.store.list(self.ACTIVE_STATES)}

    def schedule(self) -> list[scheduler.Decision]:
        queued = []
        for rec in self.store.list((sm.QUEUED,)):
            try:
                queued.append((rec, self._contract(rec)))
            except ContractError as exc:
                log.error("#%s: stored contract no longer parses: %s", rec.issue_id, exc)
        if not queued:
            return []
        if self.paused():
            return [scheduler.Decision(rec.issue_id, "wait", "scheduler paused by the owner") for rec, _ in queued]
        if self._draining:
            return [scheduler.Decision(rec.issue_id, "wait", "draining for restart") for rec, _ in queued]
        active_roots = self.active_roots()
        free_roots = self.config.max_active_issues - len(active_roots)
        snap = self.resources.snapshot(probe_machine=True)
        external = set()
        for _, c in queued:
            for dep in c.dependencies:
                if self.store.get(dep) is None:
                    try:
                        if self.github.get_issue(dep).get("state") == "closed":
                            external.add(dep)
                    except Exception:  # noqa: BLE001
                        pass
        decisions = scheduler.plan(queued, config=self.config, store=self.store, locks=self.locks, resources=self.resources,
                                   snapshot=snap, external_satisfied=external)
        by_id = {rec.issue_id: (rec, c) for rec, c in queued}
        new_roots: set[int] = set()
        for d in decisions:
            if d.starts:
                rec, contract = by_id[d.issue_id]
                if rec.root not in active_roots and rec.root not in new_roots:
                    if len(new_roots) >= max(0, free_roots):
                        decisions[decisions.index(d)] = scheduler.Decision(d.issue_id, "wait", f"max active ROOT issues reached ({self.config.max_active_issues})", d.locks)
                        continue
                    new_roots.add(rec.root)
                if self.dry_run:
                    log.info("DRY-RUN would start #%s: branch %s worktree %s locks %s", d.issue_id,
                             f"{self.config.branch_prefix}{d.issue_id}-{contract.slug}",
                             self.config.worktree_root / f"{d.issue_id}-{contract.slug}", [l.name for l in d.locks])
                    continue
                self._claim_and_start(rec, contract, d)
        return decisions

    def _claim_and_start(self, rec: IssueRecord, contract: IssueContract, d: scheduler.Decision) -> None:
        if self._thread_active(f"worker:{rec.issue_id}"):
            return
        try:
            self.store.transition(rec.issue_id, sm.CLAIMED, allowed_from=(sm.QUEUED,), note="claimed by scheduler")
        except TransitionConflict:
            return  # someone (another tick) already claimed it
        lock_decision = self.locks.acquire(rec.issue_id, d.locks)
        if not lock_decision.ok:
            self.store.transition(rec.issue_id, sm.QUEUED, note=lock_decision.reason)
            return
        try:
            self.github.set_state_label(rec.issue_id, sm.CLAIMED)
        except Exception as exc:  # noqa: BLE001
            log.warning("label for #%s failed: %s", rec.issue_id, exc)
        try:
            info = self.worktrees.ensure(rec.issue_id, contract.slug)
            self.store.update(rec.issue_id, branch=info.branch, worktree=str(info.path), base_sha=self.worktrees.base_sha())
            existing_pr = self.github.find_pr_for_branch(info.branch)
            if existing_pr:
                self._set_state(self.store, rec.issue_id, sm.PR_OPEN, note="reconciled existing PR",
                                pr_number=existing_pr["number"], pr_url=existing_pr.get("html_url"))
                self._milestone(rec.issue_id, f"Reconciled existing PR #{existing_pr['number']} for branch `{info.branch}`; resuming at CI.")
                return
            self._run_setup(info.path, contract)
        except Exception as exc:  # noqa: BLE001
            log.exception("#%s: worktree setup failed", rec.issue_id)
            self.locks.release(rec.issue_id, "setup-failed")
            self._set_state(self.store, rec.issue_id, sm.BLOCKED, note="worktree setup failed", last_error=str(exc)[:1000],
                            failure_class=ENVIRONMENT_FAILURE)
            self._milestone(rec.issue_id, f"Blocked: worktree/setup failed — `{str(exc)[:300]}`")
            return
        self._milestone(rec.issue_id, f"Claimed. Branch `{info.branch}`, worktree `{info.path.name}` ({info.note}). Starting a {self.config.models['worker']} worker.")
        self._spawn(f"worker:{rec.issue_id}", self._worker_run, rec.issue_id, False)

    def _run_setup(self, path: Path, contract: IssueContract) -> None:
        cmds = list(self.config.worktree_setup.get("always", ()))
        for domain in contract.domains:
            cmds.extend(self.config.worktree_setup.get(domain, ()))
        for cmd in cmds:
            proc = _sh(cmd.cmd, path / cmd.cwd, self.config.command_timeout_seconds, self.config.command_env)
            if proc.returncode != 0:
                raise RuntimeError(f"setup `{cmd.cmd}` in {cmd.cwd} failed: {proc.stderr[-800:]}")

    # -- worker / repair ----------------------------------------------------------------------
    def _worker_run(self, issue_id: int, repair: bool) -> None:
        store = self.thread_store()
        rec = store.get(issue_id)
        if rec is None:
            return
        contract = self._contract(rec)
        src = sm.FIX_REQUIRED if repair else sm.CLAIMED
        attempt = rec.attempt_number + 1
        try:
            rec = store.transition(issue_id, sm.WORKING, allowed_from=(src,), attempt_number=attempt,
                                   assigned_agent=f"{WORKER}:{self.config.models['worker']}", started_at=self.clock(),
                                   heartbeat_at=self.clock(), note=("repair" if repair else "worker") + f" attempt {attempt}")
        except TransitionConflict as exc:
            log.warning("#%s worker not started: %s", issue_id, exc)
            return
        try:
            self.github.set_state_label(issue_id, sm.WORKING)
        except Exception:  # noqa: BLE001
            pass
        path = Path(rec.worktree)
        base_ref = self.worktrees.base_ref()
        if repair:
            prompt = prompts.repair_prompt(contract, worktree=str(path), branch=rec.branch, attempt=attempt - 1,
                                           max_attempts=self.config.max_repair_attempts, failure_class=rec.failure_class or "UNKNOWN",
                                           failure_summary=rec.last_error or "", evidence=_load_evidence_note(self.config, issue_id))
            timeout = self.config.repair_timeout_seconds
        else:
            prompt = prompts.worker_prompt(contract, worktree=str(path), branch=rec.branch, base_ref=base_ref)
            if attempt > 1:
                prompt += "\n\nNOTE: this worktree may hold committed or uncommitted work from an earlier attempt that did not finish. Inspect `git log`, `git status` and `git diff` first and continue from it rather than starting over."
            timeout = self.config.worker_timeout_seconds
        spec = AgentRunSpec(
            role=WORKER, issue_id=issue_id, attempt=attempt, model=self.config.models["worker"], cwd=path, prompt=prompt,
            timeout_seconds=timeout, system_prompt=prompts.ROLE_SYSTEM_PROMPTS[WORKER], json_schema=WORKER_REPORT_SCHEMA,
            allowed_tools=self.config.worker_allowed_tools, disallowed_tools=self.config.worker_disallowed_tools,
            permission_mode=self.config.worker_permission_mode, add_dirs=(path,), effort=self.config.claude_effort,
            resume_session_id=rec.session_id if repair else None, session_name=f"agent-{issue_id}-worker-{attempt}",
            extra_env=tuple(self.config.command_env.items()),
        )

        def heartbeat(pid: int | None) -> None:
            store.update(issue_id, heartbeat_at=self.clock(), agent_pid=pid)

        result = self.runner.run(spec, heartbeat=heartbeat)
        record = audit.write_run_record(self.config, spec, result)
        store.record_event(issue_id, "agent_run", {"role": WORKER, "attempt": attempt, "ok": result.ok, "cost_usd": result.cost_usd,
                                                    "turns": result.num_turns, "record": str(record), "session": result.session_id})
        self._complete_worker(store, issue_id, contract, spec, result, repair)

    def _complete_worker(self, store: StateStore, issue_id: int, contract: IssueContract, spec: AgentRunSpec,
                         result: AgentRunResult, repair: bool) -> None:
        rec = store.get(issue_id)
        if rec is None or rec.state != sm.WORKING:
            return
        if result.session_id:
            store.update(issue_id, session_id=result.session_id)
        if not result.ok:
            if self.rate_limited_run(result):
                # Not the worker's fault: give the attempt back, pause new work until the window resets.
                store.update(issue_id, attempt_number=max(0, rec.attempt_number - 1), agent_pid=None, assigned_agent=None)
                self.locks.release(issue_id, "rate-limited-requeue")
                self._set_state(store, issue_id, sm.QUEUED, note="rate limited: requeued without consuming an attempt",
                                last_error=(result.error or "")[:500], failure_class="RATE_LIMITED")
                store.record_event(issue_id, "rate_limited", {"error": (result.error or "")[:300]})
                if not self.paused():
                    self.set_paused(True, source="usage_guard", who="orchestrator", reason="agent run hit a rate limit")
                    self._owner_notice("usage_pause:ratelimit:" + str(int(self.clock())),
                                       f"⛔ סוכן נתקל ב-rate limit (Issue #{issue_id}). עצרתי עבודה חדשה; ה-Issue חזר לתור בלי לשרוף ניסיון. אחדש אוטומטית כשהמכסה תתחדש.")
                self._milestone(issue_id, "Worker run hit a rate limit — requeued without consuming a repair attempt; new work is paused until the usage window resets.")
                return
            self._worker_failed(store, rec, f"worker run failed: {result.error or 'unknown'}"[:1000])
            return
        report = result.structured or {}
        status = report.get("status", "done")
        if status != "done":
            self.locks.release(issue_id, "worker-blocked")
            self._set_state(store, issue_id, sm.BLOCKED, note=f"worker reported {status}", last_error=(report.get("summary") or "")[:1000],
                            failure_class="NEEDS_DECISION" if status == "needs_decision" else "WORKER_BLOCKED")
            blockers = "\n".join(f"- {b}" for b in report.get("blockers", []))
            self._milestone(issue_id, f"Worker stopped with `{status}`: {report.get('summary', '')}\n{blockers}\n\nTeam Lead decision required.")
            return
        path = Path(rec.worktree)
        try:
            if self.worktrees.is_dirty(path) or _has_untracked(path):
                run_git(["add", "-A"], path)
                run_git(["commit", "-q", "-m", f"chore(agent): commit remaining changes for #{issue_id}"], path)
                store.record_event(issue_id, "leftover_commit", {"note": "orchestrator committed uncommitted worker changes"})
            if self.worktrees.commits_ahead(path) == 0:
                self._worker_failed(store, rec, "worker reported done but produced no commits")
                return
            self.worktrees.push(path, rec.branch)
            head = self.worktrees.head_sha(path)
            body = render_pr_body(contract, report, model=spec.model, session_id=result.session_id, attempt=spec.attempt)
            pr = self.github.find_pr_for_branch(rec.branch)
            if pr is None:
                pr = self.github.create_pr(head=rec.branch, base=self.worktrees.base_branch(), title=f"{contract.title} (#{issue_id})", body=body)
                self._milestone(issue_id, f"PR opened: {pr.get('html_url', pr['number'])} (attempt {spec.attempt}, head `{head[:12]}`).")
            else:
                self.github.update_pr(pr["number"], body=body)
                self._milestone(issue_id, f"Repair attempt {spec.attempt - 1} pushed to PR #{pr['number']} (head `{head[:12]}`).")
            store.update(issue_id, agent_pid=None, assigned_agent=None)
            self._set_state(store, issue_id, sm.PR_OPEN, note="PR ready", pr_number=pr["number"], pr_url=pr.get("html_url"),
                            validated_commit=None)
            if self.config.release_locks_at == "pr_open":
                # The code changes are done: CI/review hold no locks, so the next Issue on the same core can
                # start now (owner rule: never let a worker rest). A repair re-acquires them first.
                self.locks.release(issue_id, "pr-open")
                self._wake.set()
            store.record_event(issue_id, "worker_report", {"report": report})
            self._publish_review_status(store, issue_id, head, "pending", "independent review not yet run (awaiting CI gates)")
        except (GitError, Exception) as exc:  # noqa: BLE001
            log.exception("#%s: publishing failed", issue_id)
            self._worker_failed(store, rec, f"publishing the branch/PR failed: {str(exc)[:800]}")

    def _worker_failed(self, store: StateStore, rec: IssueRecord, error: str) -> None:
        rec = store.get(rec.issue_id) or rec
        store.update(rec.issue_id, agent_pid=None, assigned_agent=None)
        if self.attempts_remaining(rec):
            self.locks.release(rec.issue_id, "worker-failed-requeue")
            self._set_state(store, rec.issue_id, sm.QUEUED, note="requeued after worker failure", last_error=error)
            self._milestone(rec.issue_id, f"Worker attempt {rec.attempt_number} failed ({error[:300]}); requeued — "
                                           f"{self.config.max_repair_attempts - max(0, rec.attempt_number - 1)} attempt(s) left.")
        else:
            self.locks.release(rec.issue_id, "worker-failed-blocked")
            self._set_state(store, rec.issue_id, sm.BLOCKED, note="retry budget exhausted", last_error=error, failure_class="WORKER_FAILED")
            self._milestone(rec.issue_id, f"Blocked: worker failed and the retry budget is exhausted — {error[:300]}. Team Lead decision required.")

    # -- advance ------------------------------------------------------------------------------
    def advance(self, rec: IssueRecord) -> str:
        if rec.state == sm.PR_OPEN:
            self._ci_started[rec.issue_id] = self.clock()
            self._set_state(self.store, rec.issue_id, sm.CI, note="awaiting deterministic gates")
            return "PR_OPEN -> CI"
        if rec.state == sm.CI:
            return self._step_ci(rec)
        if rec.state == sm.FIX_REQUIRED:
            return self._step_fix_required(rec)
        if rec.state == sm.REVIEW:
            return self._step_review(rec)
        if rec.state == sm.READY_FOR_OWNER:
            return self._step_ready_for_owner(rec)
        if rec.state == sm.MERGED:
            return self._step_merged(rec)
        return ""

    def _pr_head(self, rec: IssueRecord) -> tuple[dict, str]:
        pr = self.github.get_pr(rec.pr_number)
        return pr, pr["head"]["sha"]

    def _step_ci(self, rec: IssueRecord) -> str:
        pr, head = self._pr_head(rec)
        if pr.get("merged"):
            self._set_state(self.store, rec.issue_id, sm.BLOCKED, note="PR merged outside the workflow", failure_class="EXTERNAL_MERGE")
            return "CI -> BLOCKED (merged externally)"
        ev = ci_evidence.collect(self.github, self.config, head)
        if ev.status in (ci_evidence.PENDING, ci_evidence.MISSING):
            started = self._ci_started.setdefault(rec.issue_id, self.clock())
            if self.clock() - started > self.config.ci_wait_seconds:
                cls = Classification(INFRA_FAILURE, "CI did not report within the configured wait", "", "")
                return self._ci_failed(rec, ev, cls, pr)
            return f"CI pending ({ev.status})"
        if ev.status == ci_evidence.SUCCESS:
            self._ci_started.pop(rec.issue_id, None)
            if self.refresh_contract(self.store, rec) is None:
                return "CI -> BLOCKED (live contract invalid)"
            self.store.update(rec.issue_id, validated_commit=head, failure_class=None)
            self._set_state(self.store, rec.issue_id, sm.REVIEW, note="deterministic gates green")
            self._ensure_review_status(self.store, self.store.get(rec.issue_id), head)
            self._milestone(rec.issue_id, f"Deterministic gates green for `{head[:12]}`.\n\n{ev.summary_markdown()}\n\nStarting independent review.")
            _save_evidence_note(self.config, rec.issue_id, ev.summary_markdown())
            return "CI -> REVIEW"
        cls = classify(FailureInput(gate_results=ev.gate_results(), logs=ev.logs, reports=ev.reports,
                                    changed_files=self._changed_files(rec), mergeable=pr.get("mergeable"),
                                    mergeable_state=pr.get("mergeable_state", "")))
        return self._ci_failed(rec, ev, cls, pr)

    def _changed_files(self, rec: IssueRecord) -> list[str]:
        try:
            return self.github.pr_files(rec.pr_number)
        except Exception:  # noqa: BLE001
            try:
                return self.worktrees.changed_files(Path(rec.worktree), self._base_ref_for(rec))
            except Exception:  # noqa: BLE001
                return []

    def _ci_failed(self, rec: IssueRecord, ev: ci_evidence.CiEvidence, cls: Classification, pr: dict) -> str:
        self._ci_started.pop(rec.issue_id, None)
        note = f"CI red for `{ev.head_sha[:12]}` — classified **{cls.kind}**: {cls.summary}\n\n{ev.summary_markdown()}"
        if cls.evidence:
            note += f"\n\n<details><summary>evidence</summary>\n\n```\n{cls.evidence[:3000]}\n```\n</details>"
        _save_evidence_note(self.config, rec.issue_id, note)
        self.store.record_event(rec.issue_id, "ci_failed", {"class": cls.kind, "summary": cls.summary, "head": ev.head_sha})
        if cls.kind in (INFRA_FAILURE, FLAKY_TEST) and not _already_rerun(self.store, rec.issue_id, ev.head_sha):
            self.store.record_event(rec.issue_id, "ci_rerun", {"head": ev.head_sha, "class": cls.kind})
            rerun_ok = self._rerun_ci(ev)
            self._milestone(rec.issue_id, note + f"\n\nRe-running CI once ({'requested' if rerun_ok else 'request failed'}).")
            if rerun_ok:
                self._ci_started[rec.issue_id] = self.clock()
                return f"CI red ({cls.kind}) -> rerun requested"
        if cls.repairable and self.attempts_remaining(rec):
            self._set_state(self.store, rec.issue_id, sm.FIX_REQUIRED, note=cls.kind, failure_class=cls.kind, last_error=cls.summary[:1000])
            self._milestone(rec.issue_id, note + f"\n\nScheduling repair attempt {rec.attempt_number} of {self.config.max_repair_attempts}.")
            return f"CI -> FIX_REQUIRED ({cls.kind})"
        self.locks.release(rec.issue_id, "blocked")
        self._set_state(self.store, rec.issue_id, sm.BLOCKED, note=cls.kind, failure_class=cls.kind, last_error=cls.summary[:1000])
        why = "not automatically repairable" if not cls.repairable else "retry budget exhausted"
        self._milestone(rec.issue_id, note + f"\n\nBlocked ({why}). Team Lead decision required.")
        return f"CI -> BLOCKED ({cls.kind})"

    def _rerun_ci(self, ev: ci_evidence.CiEvidence) -> bool:
        ok = False
        for run_id in ev.run_ids:
            try:
                self.github.transport.request("POST", f"/repos/{self.config.repo}/actions/runs/{run_id}/rerun-failed-jobs")
                ok = True
            except Exception as exc:  # noqa: BLE001
                log.warning("rerun of run %s failed: %s", run_id, exc)
        return ok

    def _step_fix_required(self, rec: IssueRecord) -> str:
        if self._thread_active(f"worker:{rec.issue_id}"):
            return "repair running"
        if self.paused():
            return "repair waiting: scheduler paused by the owner"
        if self._draining:
            return "repair waiting: draining for restart"
        snap = self.resources.snapshot(probe_machine=True)
        adm = self.resources.can_start_worker(rec.resource_class, snap)
        if not adm.ok:
            return f"repair waiting: {adm.reason}"
        live = self.refresh_contract(self.store, rec)      # the Team Lead may have amended the contract
        if live is None:
            return "FIX_REQUIRED -> BLOCKED (live contract invalid)"
        reqs = effective_locks(live, self.config)
        if not any(l.issue_id == rec.issue_id for l in self.store.locks_held()):
            lock_decision = self.locks.acquire(rec.issue_id, reqs)
            if not lock_decision.ok:
                return f"repair waiting: {lock_decision.reason}"
        if self.dry_run:
            return "DRY-RUN would start repair"
        self._spawn(f"worker:{rec.issue_id}", self._worker_run, rec.issue_id, True)
        return "FIX_REQUIRED -> WORKING (repair)"

    # -- review -------------------------------------------------------------------------------
    def _step_review(self, rec: IssueRecord) -> str:
        pr, head = self._pr_head(rec)
        if pr.get("merged"):
            self._set_state(self.store, rec.issue_id, sm.BLOCKED, note="PR merged outside the workflow", failure_class="EXTERNAL_MERGE")
            return "REVIEW -> BLOCKED (merged externally)"
        if head != rec.validated_commit:
            # new commits appeared: the review (if any) is stale for this SHA; re-validate deterministically first
            self._ci_started[rec.issue_id] = self.clock()
            self._publish_review_status(self.store, rec.issue_id, head, "pending", "stale: head moved, review must run again")
            self._set_state(self.store, rec.issue_id, sm.CI, note="head moved during review: review stale, re-validating",
                            validated_commit=None)
            self._milestone(rec.issue_id, f"PR head moved to `{head[:12]}` during review — review marked stale; re-running the gates.")
            return "REVIEW -> CI (head moved, review stale)"
        reviewed_sha = _review_sha(rec)
        if rec.review_verdict is None or reviewed_sha != head:
            if self._thread_active(f"reviewer:{rec.issue_id}"):
                return "review running"
            if self.paused():
                return "review waiting: scheduler paused"
            if self._draining:
                return "review waiting: draining for restart"
            snap = self.resources.snapshot(probe_machine=True)
            adm = self.resources.can_start_reviewer(snap)
            if not adm.ok:
                return f"review waiting: {adm.reason}"
            if self.dry_run:
                return "DRY-RUN would start review"
            self.store.update(rec.issue_id, assigned_agent=f"{REVIEWER}:{self.config.models['reviewer']}")
            self._spawn(f"reviewer:{rec.issue_id}", self._reviewer_run, rec.issue_id, head)
            return "review started"
        verdict = rec.review_verdict.split("@", 1)[0]
        if verdict != "APPROVE":
            return f"review verdict {verdict} (awaiting decision)"
        ev = ci_evidence.collect(self.github, self.config, head, fetch_logs=False)
        decision = merge_policy.decide(rec, ev, self.config, review_sha=reviewed_sha,
                                       lost_allowance=self._contract(rec).lost_allowance)
        if decision.ok:
            if self.period is not None and rec.kind != "rollup":
                return self._integrate(rec, head, ev, verdict)
            self._set_state(self.store, rec.issue_id, sm.READY_FOR_OWNER, note=f"every gate green: {decision.describe()}")
            self.store.record_event(rec.issue_id, "ready_for_owner", {"head": head, "policy": decision.describe()})
            if self.config.release_locks_at in ("ready", "pr_open"):
                self.locks.release(rec.issue_id, "ready-for-owner")
            self._publish_ready_report(self.store.get(rec.issue_id), head, ev)
            return "REVIEW -> READY_FOR_OWNER"
        return f"awaiting {', '.join(decision.missing)}"

    # -- weekend / holiday integration mode (§26–§41) -------------------------------------------
    def _load_period(self) -> Period | None:
        raw = self.store.get_meta("protected_period")
        return Period.from_dict(json.loads(raw)) if raw else None

    def _save_period(self, p: Period | None) -> None:
        self.store.set_meta("protected_period", json.dumps(p.to_dict()) if p else "")

    def integrations(self) -> list[dict]:
        raw = self.store.get_meta("integrations")
        return json.loads(raw) if raw else []

    def _add_integration(self, entry: dict) -> None:
        items = [i for i in self.integrations() if i["issue"] != entry["issue"]]
        items.append(entry)
        self.store.set_meta("integrations", json.dumps(items))

    def decisions(self, since: float | None = None) -> list[dict]:
        out = []
        for e in self.store.events(None, limit=1000):
            if e["kind"] == "lead_decision" and (since is None or e["ts"] >= since):
                out.append({"ts": e["ts"], "issue": e["issue_id"], "text": e["payload"].get("text", ""), "by": e["payload"].get("by", "")})
        return out

    def record_decision(self, text: str, *, issue_id: int | None = None, by: str = "team-lead") -> None:
        """A product/engineering decision the Team Lead took autonomously — listed in the rollup PR."""
        self.store.record_event(issue_id, "lead_decision", {"text": text[:1000], "by": by})

    def rollup(self) -> dict | None:
        raw = self.store.get_meta("rollup")
        return json.loads(raw) if raw else None

    def _base_ref_for(self, rec: IssueRecord) -> str:
        """The base a record's PR targets: the rollup targets main; otherwise the PR's own base."""
        if rec.kind == "rollup":
            return self.worktrees.base_ref(self.config.base_branch)
        if rec.pr_number:
            try:
                base = (self.github.get_pr(rec.pr_number).get("base") or {}).get("ref")
                if base:
                    return self.worktrees.base_ref(base)
            except Exception:  # noqa: BLE001
                pass
        return self.worktrees.base_ref()

    def check_period(self) -> str | None:
        """Start the period when today is protected (Asia/Jerusalem), end it the day after it ends."""
        if not self.config.protected_periods_enabled or self.dry_run:
            return None
        today = self.calendar.today(self.clock)
        if self.period is None:
            p = self.calendar.period_containing(today)
            if p:
                return self.start_period(p)
            return None
        if today > self.period.end:
            return self.end_period()
        return None

    def start_period(self, p: Period) -> str:
        base = self.worktrees.base_ref(self.config.base_branch)
        sha = self.worktrees.create_branch_from(p.branch, base)
        self.period = p
        self.worktrees.base_override = p.branch
        self._save_period(p)
        self.store.set_meta("period_started_at", str(self.clock()))
        self.store.record_event(None, "PROTECTED_PERIOD_STARTED", {"type": p.kind, "name": p.name, "integration_branch": p.branch,
                                                                    "start": p.start.isoformat(), "end": p.end.isoformat(), "base_sha": sha})
        self._owner_notice(f"period_start:{p.branch}",
                           f"📅 נכנסנו למצב {im.period_hebrew(p)} ({p.start} → {p.end}): PRs שעוברים את כל השערים מתמזגים על ידי ה-team lead "
                           f"ל-`{p.branch}` — לא ל-main. בסוף התקופה תקבל rollup PR אחד לאישור. main נשאר שלך.")
        log.info("protected period started: %s (%s)", p.label, p.branch)
        return f"protected period started: {p.label} -> {p.branch}"

    def _integrate(self, rec: IssueRecord, head: str, ev, verdict: str) -> str:
        """Team-Lead merge into the period's integration branch (never main) after every gate is green."""
        p = self.period
        assert p is not None
        pr = self.github.get_pr(rec.pr_number)
        if (pr.get("base") or {}).get("ref") != p.branch:
            self.github.update_pr(rec.pr_number, base=p.branch)
        try:
            res = self.github.merge_pr(rec.pr_number, method=self.config.merge_method, sha=head, title=f"{rec.title} (#{rec.issue_id})")
        except GitHubError as exc:
            self.locks.release(rec.issue_id, "integration-failed")
            self._set_state(self.store, rec.issue_id, sm.BLOCKED, note="integration merge refused", failure_class="INTEGRATION_FAILURE", last_error=str(exc)[:1000])
            self._milestone(rec.issue_id, f"Integration merge into `{p.branch}` refused by GitHub: {str(exc)[:300]}. Team Lead attention required.")
            return "REVIEW -> BLOCKED (integration merge refused)"
        merge_sha = res.get("sha") or res.get("merge_commit_sha") or ""
        self._set_state(self.store, rec.issue_id, sm.INTEGRATED, note=f"integrated into {p.branch}", validated_commit=merge_sha)
        self.locks.release(rec.issue_id, "integrated")
        entry = {"issue": rec.issue_id, "pr": rec.pr_number, "sha": merge_sha, "head": head, "title": rec.title.replace("[agent] ", "", 1),
                 "root": rec.root, "review": verdict, "branch": p.branch, "ts": self.clock()}
        self._add_integration(entry)
        self.store.record_event(rec.issue_id, "integrated", entry)
        self._milestone(rec.issue_id, f"Integrated by the Team Lead into `{p.branch}` (`{merge_sha[:12]}`) — {im.period_hebrew(p)} mode: "
                                      f"CI, regression and independent review were green at `{head[:12]}`. Lands on main with the period's rollup PR.")
        self._owner_notice(f"integrated:{rec.issue_id}:{merge_sha[:8]}",
                           f"🧩 #{rec.issue_id} אוחד ל-`{p.branch}` (PR #{rec.pr_number}, review {verdict}). main לא נגע; יגיע אליך ב-rollup בסוף {im.period_hebrew(p)}.")
        self._wake.set()
        if not self.dry_run:
            job = self.resources.try_acquire_heavy(rec.issue_id, "integration-smoke")
            if job is not None:
                self._spawn(f"smoke:{rec.issue_id}", self._integration_smoke_run, rec.issue_id, job, p.branch, merge_sha)
        return f"REVIEW -> INTEGRATED ({p.branch})"

    def _integration_smoke_run(self, issue_id: int, job, branch: str, merge_sha: str) -> None:
        """Integration-aware validation (§30): smoke on the combined branch head right after the merge.
        Red smoke reverts the merge and sends the Issue back for repair — recorded as a decision."""
        store = self.thread_store()
        results: list[str] = []
        ok = True
        path = None
        try:
            self.worktrees.fetch()
            path = self.worktrees.validation_worktree(self.worktrees.base_ref(branch))
            for cmd in self.config.worktree_setup.get("always", ()):
                proc = _sh(cmd.cmd, path / cmd.cwd, self.config.command_timeout_seconds, self.config.command_env)
                if proc.returncode != 0:
                    raise RuntimeError(f"setup `{cmd.cmd}` failed: {proc.stderr[-500:]}")
            for cmd in self.config.smoke:
                self.resources.heartbeat_heavy(job)
                proc = _sh(cmd.cmd, path / cmd.cwd, self.config.command_timeout_seconds, self.config.command_env)
                tail = (proc.stdout.strip().splitlines() or [""])[-1][:200]
                results.append(f"{'✅' if proc.returncode == 0 else '❌'} `{cmd.cmd}` — {tail or proc.stderr[-200:]}")
                if proc.returncode != 0:
                    ok = False
        except Exception as exc:  # noqa: BLE001
            ok = False
            results.append(f"❌ integration smoke setup failed: {str(exc)[:300]}")
        finally:
            if path is not None:
                try:
                    self.worktrees.remove_validation_worktree(path)
                except Exception:  # noqa: BLE001
                    pass
            self.resources.release_heavy(job, "done" if ok else "failed")
        summary = "\n".join(results)
        store.record_event(issue_id, "integration_smoke", {"ok": ok, "branch": branch, "results": results})
        if ok:
            return
        # revert the squash commit on the integration branch and send the Issue back for repair
        try:
            wt = self.worktrees.ensure_named(0, branch, slug="integration")
            proc = run_git(["revert", "--no-edit", merge_sha], wt.path, check=False)
            if proc.returncode != 0:
                run_git(["revert", "--abort"], wt.path, check=False)
                raise RuntimeError(proc.stderr[-400:])
            self.worktrees.push(wt.path, branch)
            reverted = self.worktrees.head_sha(wt.path)
        except Exception as exc:  # noqa: BLE001
            self._set_state(store, issue_id, sm.BLOCKED, note="integration smoke failed; revert failed", failure_class="INTEGRATION_FAILURE",
                            last_error=(summary + "\nrevert failed: " + str(exc))[:1000])
            self._milestone(issue_id, f"Integration smoke FAILED on `{branch}` and the revert of `{merge_sha[:12]}` failed too:\n{summary}\n{exc}\nTeam Lead attention required.")
            return
        self.store.set_meta("integrations", json.dumps([i for i in self.integrations() if i["issue"] != issue_id]))
        _save_evidence_note(self.config, issue_id, f"INTEGRATION SMOKE FAILED on {branch} after merging this PR (reverted as {reverted[:12]}):\n\n{summary}")
        self._set_state(store, issue_id, sm.FIX_REQUIRED, note="integration smoke failed; merge reverted", failure_class="INTEGRATION_FAILURE",
                        last_error=summary[:1000], validated_commit=None)
        self.record_decision(f"#{issue_id}: reverted from {branch} — integration smoke failed after the merge ({summary[:120]}); sent back for repair", issue_id=issue_id, by="orchestrator")
        self._milestone(issue_id, f"Integration smoke FAILED on `{branch}` after merging this PR — merge `{merge_sha[:12]}` reverted (`{reverted[:12]}`); "
                                  f"a repair run gets the smoke output as evidence.\n{summary}")

    def end_period(self) -> str:
        """Period over: one rollup PR (integration branch -> main) validated as a whole, or nothing."""
        p = self.period
        assert p is not None
        children = [i for i in self.integrations() if i.get("branch") == p.branch]
        self.period = None
        self.worktrees.base_override = None
        self._save_period(None)
        if not children:
            self.worktrees.delete_remote_branch(p.branch)
            self.store.record_event(None, "PROTECTED_PERIOD_ENDED", {"integration_branch": p.branch, "rollup_pr": None, "integrated": 0})
            self._owner_notice(f"period_end:{p.branch}", f"📅 {im.period_hebrew(p)} הסתיים — לא אוחדה עבודה ב-`{p.branch}`; הענף נמחק. חוזרים למצב הרגיל.")
            return f"protected period ended: {p.label} (nothing integrated)"
        started = float(self.store.get_meta("period_started_at") or 0) or None
        decisions = self.decisions(since=started)
        recs = [self.store.get(c["issue"]) for c in children]
        domains = sorted({d for r in recs if r for d in r.domains})
        risk = "HIGH" if any(r and r.risk == "HIGH" for r in recs) else ("MEDIUM" if any(r and r.risk == "MEDIUM" for r in recs) else "LOW")
        primary = "none"
        limits = []
        for r in recs:
            if not r:
                continue
            try:
                rule = self._contract(r).budget_rule("primary_signature_changes")
            except Exception:  # noqa: BLE001
                continue
            if rule.kind == "max" and rule.limit > 0:
                primary = str(max(int(primary) if primary.isdigit() else 0, rule.limit))
            elif rule.kind == "tagged":
                limits.append(rule.spec())
        if limits and primary == "none":
            primary = limits[0]
        title = f"[agent] {im.period_title(p)}"
        body = im.rollup_contract_body(p, children, domains=domains or ["infra"], risk=risk, primary_changes=primary, decisions=decisions)
        contract = parse_contract(0, title, body, known_locks=self.config.known_locks, behavior_domains=self.config.behavior_domains)
        issue = self.github.create_issue(title, body, [ROLLUP_LABEL, "agent:pr-open", *metadata_labels(contract.domains, contract.risk, contract.resource_class)])
        n = issue["number"]
        contract = parse_contract(n, title, body, known_locks=self.config.known_locks, behavior_domains=self.config.behavior_domains)
        info = self.worktrees.ensure_named(n, p.branch)
        pr_body = im.rollup_pr_body(p, children, decisions=decisions, behavior_changes=[], regression=None, tests_ok=None, review=None,
                                    limitations=[], recommendation="pending: the combined state is being validated")
        pr = self.github.create_pr(head=p.branch, base=self.config.base_branch, title=f"{title} (#{n})", body=pr_body)
        manifest = verification_manifest(contract, regression_domains=self.config.regression_domains)
        self.store.track(n, title=title, risk=contract.risk, resource_class=contract.resource_class, domains=list(contract.domains),
                         dependencies=[], contract=_contract_to_dict(contract), state=sm.PR_OPEN, kind="rollup", root_issue=n)
        audit.write_contract_snapshot(self.config, n, contract.to_dict(), manifest)
        self.store.update(n, branch=p.branch, worktree=str(info.path), pr_number=pr["number"], pr_url=pr.get("html_url"),
                          base_sha=self.worktrees.base_sha(), review_verdict=None)
        self.store.set_meta("rollup", json.dumps({"issue": n, "pr": pr["number"], "period": p.to_dict(), "children": [c["issue"] for c in children]}))
        self.store.record_event(None, "PROTECTED_PERIOD_ENDED", {"integration_branch": p.branch, "rollup_pr": pr["number"], "rollup_issue": n,
                                                                  "integrated": [c["issue"] for c in children]})
        for c in children:
            self._milestone(c["issue"], f"Included in the {im.period_title(p)} rollup: Issue #{n} / PR #{pr['number']} — the owner merges that PR; this Issue closes with it.")
        self._owner_notice(f"period_end:{p.branch}",
                           f"📦 {im.period_hebrew(p)} הסתיים: {len(children)} Issues אוחדו ב-`{p.branch}`. פתחתי rollup PR #{pr['number']} ל-main; "
                           f"עכשיו רץ אימות של המצב המשולב (CI, רגרסיה מול main, review של ה-diff המשולב). תקבל הודעה אחת כשהוא מוכן.")
        log.info("protected period ended: %s -> rollup PR #%s (Issue #%s)", p.label, pr["number"], n)
        return f"protected period ended: {p.label} -> rollup PR #{pr['number']}"

    def _rollup_ready(self, rec: IssueRecord, r: dict, head: str) -> str:
        info = self.rollup() or {}
        p = Period.from_dict(info["period"]) if info.get("period") else None
        children = [i for i in self.integrations() if p is None or i.get("branch") == p.branch]
        decisions = self.decisions(since=float(self.store.get_meta("period_started_at") or 0) or None)
        if p is not None:
            body = im.rollup_pr_body(p, children, decisions=decisions, behavior_changes=[], regression=r.get("regression"),
                                     tests_ok=r.get("ci") == "PASS", review=r.get("review"), limitations=list(r.get("limitations") or []),
                                     recommendation="MERGE RECOMMENDED" if str(r.get("recommendation", "")).startswith("MERGE") else "CHANGES RECOMMENDED — " + str(r.get("recommendation", "")))
            try:
                self.github.update_pr(rec.pr_number, body=body)
            except Exception as exc:  # noqa: BLE001
                log.warning("rollup PR body update failed: %s", exc)
            return im.rollup_notification(p, rec.pr_number, children, decisions=decisions, ci=r.get("ci", "?"), regression=r.get("regression", "?"),
                                          review=r.get("review", "?"), head=head, pr_url=r.get("pr_url") or "")
        return render_ready_notification(r)

    def _finish_rollup(self, store: StateStore, rec: IssueRecord) -> None:
        """The owner merged the rollup: every integrated child is done, the branch and the mode state go away."""
        info = self.rollup() or {}
        children = info.get("children") or [i["issue"] for i in self.integrations()]
        for n in children:
            c = store.get(n)
            if c is None or c.state != sm.INTEGRATED:
                continue
            self._set_state(store, n, sm.DONE, note="rollup merged by the owner")
            self._milestone(n, f"Done — landed on main with rollup PR #{rec.pr_number} (`{str(rec.validated_commit)[:12]}`).")
            if not self.dry_run:
                try:
                    self.github.close_issue(n)
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not close #%s: %s", n, exc)
        branch = info.get("period", {}).get("branch") or rec.branch
        if branch and not self.dry_run:
            try:
                self.worktrees.delete_remote_branch(branch)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not delete %s: %s", branch, exc)
        store.set_meta("rollup", "")
        store.set_meta("integrations", json.dumps([i for i in self.integrations() if i.get("branch") != branch]))
        store.record_event(rec.issue_id, "ROLLUP_MERGED", {"children": children, "branch": branch, "merge_commit": rec.validated_commit})

    def rollup_exclude(self, child_issue: int, *, source: str, who, reason: str = "") -> dict:
        """Owner change request on the rollup (§36): take one Issue's change out of the integration
        branch by reverting its squash commit; the rollup re-validates from the new head."""
        info = self.rollup()
        entry = next((i for i in self.integrations() if i["issue"] == child_issue), None)
        if info is None or entry is None:
            return {"result": "REFUSED", "reason": f"#{child_issue} אינו חלק מחבילת האינטגרציה"}
        branch = entry["branch"]
        try:
            wt = self.worktrees.ensure_named(0, branch, slug="integration")
            proc = run_git(["revert", "--no-edit", entry["sha"]], wt.path, check=False)
            if proc.returncode != 0:
                run_git(["revert", "--abort"], wt.path, check=False)
                return {"result": "REFUSED", "reason": f"ה-revert של #{child_issue} מתנגש עם שינויים מאוחרים יותר ({proc.stderr[-200:]}) — נדרשת החלטה של ה-team lead"}
            self.worktrees.push(wt.path, branch)
            reverted = self.worktrees.head_sha(wt.path)
        except Exception as exc:  # noqa: BLE001
            return {"result": "REFUSED", "reason": str(exc)[:300]}
        self.store.set_meta("integrations", json.dumps([i for i in self.integrations() if i["issue"] != child_issue]))
        info["children"] = [c for c in info.get("children", []) if c != child_issue]
        self.store.set_meta("rollup", json.dumps(info))
        rec = self.store.get(child_issue)
        if rec is not None and rec.state == sm.INTEGRATED:
            self._set_state(self.store, child_issue, sm.BLOCKED, note="excluded from the rollup by the owner", failure_class="OWNER_EXCLUDED",
                            last_error=reason[:500] or "excluded by the owner", validated_commit=None)
        self.record_decision(f"#{child_issue} excluded from {branch} on the owner's request ({reason or 'no reason given'}); reverted as {reverted[:12]}",
                             issue_id=child_issue, by=f"owner:{source}")
        self.store.record_event(child_issue, "rollup_excluded", {"source": source, "owner_id": who, "reason": reason, "reverted": reverted})
        self._milestone(child_issue, f"Excluded from the rollup on the owner's request: its integration commit was reverted on `{branch}` (`{reverted[:12]}`). The rollup re-validates from the new head.")
        return {"result": "SUCCESS", "issue": child_issue, "reverted": reverted, "rollup_pr": info.get("pr")}

    # -- READY FOR OWNER ----------------------------------------------------------------------
    def ready_report(self, rec: IssueRecord, head: str, ev: ci_evidence.CiEvidence | None = None) -> dict:
        """The decision-oriented facts the owner sees (comment + Telegram). Built only from the store,
        GitHub evidence and run records — never from a model's free text alone."""
        if ev is None:
            ev = ci_evidence.collect(self.github, self.config, head, fetch_logs=False)
        contract = None
        try:
            contract = self._contract(rec)
        except Exception:  # noqa: BLE001
            pass
        report = _last_worker_report(self.store, rec.issue_id)
        events = self.store.events(rec.issue_id, limit=500)
        failures = [e for e in events if e["kind"] in ("ci_failed", "review_failed", "worker_failed")]
        verdicts = [e for e in events if e["kind"] == "review_verdict"]
        ok_reg, reg_note = merge_policy.regression_status(ev, self.config)
        v = self.store.get(rec.issue_id)
        verdict = (v.review_verdict or "").split("@")[0] or "-"
        acs = []
        if contract:
            evidence = {e.get("ac"): e for e in report.get("ac_evidence", []) if isinstance(e, dict)}
            for a in contract.acceptance_criteria:
                e = evidence.get(a.id, {})
                acs.append(f"{a.id}: {e.get('result', 'see gate-3')} — {str(e.get('evidence', ''))[:90]}")
        gates = ev.required_contexts_green(self.config.protection_required_contexts)[1]
        return {
            "issue": rec.issue_id, "root": rec.root, "kind": rec.kind, "title": rec.title, "pr": rec.pr_number, "pr_url": rec.pr_url, "branch": rec.branch,
            "head": head, "risk": rec.risk,
            "summary": (report.get("summary") or "").strip()[:400],
            "what_changed": [str(x)[:160] for x in (report.get("what_changed") or [])][:6],
            "acceptance": acs,
            "ci": "PASS" if ev.status == ci_evidence.SUCCESS else ev.status.upper(),
            "gates": gates,
            "tests": "; ".join(f"{t.get('command', '')[:60]} -> {t.get('result', '')[:40]}" for t in (report.get("tests_run") or [])[:3]) or "see gate-2/gate-3",
            "regression": ("PASS" if ok_reg else "FAIL") + f" ({reg_note})",
            "review": verdict, "review_count": len(verdicts),
            "failures": [f"{e['payload'].get('class', e['kind'])}: {str(e['payload'].get('summary', e['payload'].get('error', '')))[:100]}" for e in failures][-4:],
            "attempts": rec.attempt_number,
            "limitations": [str(x)[:160] for x in (report.get("known_limitations") or [])][:4],
            "recommendation": "MERGE — כל השערים ירוקים ל-SHA הזה בדיוק" if verdict == "APPROVE" and ev.status == ci_evidence.SUCCESS else "HOLD — ראה ראיות",
        }

    def _publish_ready_report(self, rec: IssueRecord, head: str, ev: ci_evidence.CiEvidence | None = None) -> None:
        r = self.ready_report(rec, head, ev)
        text = render_ready_report(r)
        self._milestone(rec.issue_id, text)
        notification = render_ready_notification(r)
        if rec.kind == "rollup":
            notification = self._rollup_ready(rec, r, head)
        if self.config.notify_ready_for_owner:
            key = f"pr:{rec.pr_number}:READY_FOR_OWNER:{head}"
            buttons = [[{"text": "סיכום" if rec.kind == "rollup" else "פרטים", "data": f"v1|GET_PR_DETAILS|{rec.pr_number}|{head[:8]}|"},
                        {"text": "מזג", "data": f"v1|MERGE_PR|{rec.pr_number}|{head[:8]}|"},
                        {"text": "בקש שינוי" if rec.kind == "rollup" else "דחה", "data": f"v1|{'OWNER_CHANGE_REQUEST' if rec.kind == 'rollup' else 'REJECT_PR'}|{rec.pr_number}|{head[:8]}|"}]]
            created = self.store.enqueue_notification("ready_for_owner", key, rec.issue_id, notification, buttons)
            if not created:
                log.info("#%s: READY notification for %s already queued/sent (dedup)", rec.issue_id, head[:12])

    def _reviewer_run(self, issue_id: int, head: str) -> None:
        store = self.thread_store()
        rec = store.get(issue_id)
        if rec is None or rec.state != sm.REVIEW:
            return
        contract = self.refresh_contract(store, rec)
        if contract is None:
            return
        rec = store.get(issue_id)
        path = Path(rec.worktree)
        ev = ci_evidence.collect(self.github, self.config, head, fetch_logs=False)
        worker_report = _last_worker_report(store, issue_id)
        try:
            base_ref = self._base_ref_for(rec)
            files = "\n".join(self.worktrees.changed_files(path, base_ref))
            diff = self.worktrees.diff(path, base_ref)
        except GitError as exc:
            files, diff = "", f"(diff unavailable: {exc})"
        prompt = prompts.reviewer_prompt(contract, ci_evidence=ev.summary_markdown(), regression_report=ev.regression_markdown(),
                                         worker_report=json.dumps(worker_report, indent=2, ensure_ascii=False), files_changed=files, diff=diff)
        spec = AgentRunSpec(role=REVIEWER, issue_id=issue_id, attempt=rec.attempt_number, model=self.config.models["reviewer"], cwd=path,
                            prompt=prompt, timeout_seconds=self.config.reviewer_timeout_seconds, system_prompt=prompts.ROLE_SYSTEM_PROMPTS[REVIEWER],
                            json_schema=REVIEW_VERDICT_SCHEMA, tools=self.config.reviewer_tools, restricted=True, add_dirs=(path,),
                            effort=self.config.claude_effort, session_name=f"agent-{issue_id}-review", persist_session=False,
                            extra_env=tuple(self.config.command_env.items()))
        result = self.runner.run(spec, heartbeat=lambda pid: store.update(issue_id, heartbeat_at=self.clock(), agent_pid=pid))
        record = audit.write_run_record(self.config, spec, result, extra={"head": head})
        store.record_event(issue_id, "agent_run", {"role": REVIEWER, "ok": result.ok, "cost_usd": result.cost_usd, "turns": result.num_turns,
                                                    "record": str(record), "head": head})
        store.update(issue_id, assigned_agent=None, agent_pid=None)
        rec = store.get(issue_id)
        if rec is None or rec.state != sm.REVIEW:
            return
        if not result.ok or not result.structured:
            store.update(issue_id, last_error=f"reviewer run failed: {result.error}"[:1000])
            store.record_event(issue_id, "review_failed", {"error": result.error[:500]})
            self._publish_review_status(store, issue_id, head, "pending", "independent review run failed; will retry")
            if self.rate_limited_run(result) and not self.paused():
                self.set_paused(True, source="usage_guard", who="orchestrator", reason="reviewer run hit a rate limit")
                self._owner_notice("usage_pause:ratelimit:" + str(int(self.clock())),
                                   f"⛔ ה-reviewer נתקל ב-rate limit (Issue #{issue_id}). עצרתי עבודה חדשה עד חידוש המכסה.")
            log.warning("#%s: reviewer failed (%s); will retry next tick", issue_id, result.error[:200])
            return
        verdict = result.structured
        v = verdict.get("verdict", "BLOCK")
        # SEMANTIC_REVIEW criteria are evidence only when the reviewer marked them MET.
        semantic = contract.semantic_review_acs
        # Reviewers write the id alone ("AC-3") or with the criterion text ("AC-3: C24 green …"):
        # key the assessment by the leading AC id.
        assessed = {}
        for a in verdict.get("ac_assessment", []):
            if isinstance(a, dict):
                m = re.match(r"\s*(AC-\d+)", str(a.get("ac", "")))
                if m:
                    assessed[m.group(1)] = a.get("verdict")
        unmet = [ac for ac in semantic if assessed.get(ac) != "MET"]
        if v == "APPROVE" and unmet:
            v = "REQUEST_CHANGES"
            verdict = {**verdict, "verdict": v, "summary": f"downgraded by the orchestrator: semantic criteria not MET {unmet}. " + verdict.get("summary", "")}
        current_head = None
        try:
            current_head = self.github.get_pr(rec.pr_number)["head"]["sha"]
        except Exception:  # noqa: BLE001
            pass
        body = _verdict_markdown(verdict)
        if not self.dry_run:
            try:
                self.github.review_pr(rec.pr_number, body, event="REQUEST_CHANGES" if v != "APPROVE" else "COMMENT")
            except Exception as exc:  # noqa: BLE001
                log.warning("posting review on PR #%s failed: %s", rec.pr_number, exc)
        store.update(issue_id, review_verdict=f"{v}@{head}")
        store.record_event(issue_id, "review_verdict", {"verdict": v, "head": head, "summary": verdict.get("summary", "")[:500],
                                                         "semantic_unmet": unmet})
        if current_head is not None and current_head != head:
            # the PR moved while the reviewer was reading: the verdict is already stale
            self._publish_review_status(store, issue_id, current_head, "pending", "stale: head moved during review")
            log.info("#%s: review verdict %s for %s is stale (head now %s)", issue_id, v, head[:12], current_head[:12])
            return
        if v == "APPROVE" and rec.validated_commit == head:
            self._publish_review_status(store, issue_id, head, "success", f"independent review APPROVE for {head[:12]}")
        else:
            self._publish_review_status(store, issue_id, head, "failure", f"independent review {v} for {head[:12]}")
        if v == "APPROVE":
            self._milestone(issue_id, f"Independent review: **APPROVE** — {verdict.get('summary', '')[:400]}")
            return
        cls = Classification(REVIEW_REJECTED, f"independent review {v}: {verdict.get('summary', '')[:300]}", body[:3000], "review")
        _save_evidence_note(self.config, issue_id, body)
        if v == "REQUEST_CHANGES" and self.attempts_remaining(rec):
            self._set_state(store, issue_id, sm.FIX_REQUIRED, note=REVIEW_REJECTED, failure_class=REVIEW_REJECTED, last_error=cls.summary[:1000])
            self._milestone(issue_id, f"Independent review: **REQUEST_CHANGES** — {verdict.get('summary', '')[:400]}\n\nScheduling repair attempt {rec.attempt_number} of {self.config.max_repair_attempts}.")
        else:
            self.locks.release(issue_id, "review-blocked")
            self._set_state(store, issue_id, sm.BLOCKED, note=f"review {v}", failure_class=REVIEW_REJECTED, last_error=cls.summary[:1000])
            self._milestone(issue_id, f"Independent review: **{v}** — {verdict.get('summary', '')[:400]}\n\nBlocked; Team Lead decision required.")

    # -- ready / merge ------------------------------------------------------------------------
    def _step_ready_for_owner(self, rec: IssueRecord) -> str:
        """Wait for the owner. Keep the readiness honest: a moved head or an advanced base invalidates
        it (back to CI, new SHA -> new validation -> new notification); an owner merge on GitHub is
        detected and audited; the orchestrator itself never merges here."""
        pr, head = self._pr_head(rec)
        if pr.get("merged"):
            self.audit_external_merge(rec, pr)
            self._set_state(self.store, rec.issue_id, sm.MERGED, note="merged by the owner on GitHub", validated_commit=pr.get("merge_commit_sha"))
            self._milestone(rec.issue_id, f"PR #{rec.pr_number} merged by the owner (`{str(pr.get('merge_commit_sha'))[:12]}`). Running post-merge smoke.")
            return "READY_FOR_OWNER -> MERGED (owner merged on GitHub)"
        if pr.get("state") == "closed":
            self.locks.release(rec.issue_id, "pr-closed")
            self._set_state(self.store, rec.issue_id, sm.BLOCKED, note="PR closed by the owner", failure_class="OWNER_REJECTED")
            return "READY_FOR_OWNER -> BLOCKED (PR closed)"
        if head != rec.validated_commit:
            self._invalidate_readiness(rec, head, "head moved")
            return "READY_FOR_OWNER -> CI (head moved, readiness invalidated)"
        path = Path(rec.worktree)
        self.worktrees.fetch()
        pr_base = (pr.get("base") or {}).get("ref") or self.config.base_branch
        try:
            behind = self.worktrees.behind_base(path, pr_base)
        except GitError:
            behind = 0
        if behind > 0:
            if self.dry_run:
                return f"DRY-RUN would update branch ({behind} behind) and re-validate"
            try:
                self.worktrees.update_from_base(path, pr_base)
                self.worktrees.push(path, rec.branch)
            except MergeConflict as exc:
                self.locks.release(rec.issue_id, "merge-conflict")
                self._set_state(self.store, rec.issue_id, sm.BLOCKED, note=MERGE_CONFLICT, failure_class=MERGE_CONFLICT, last_error=str(exc)[:1000])
                self._milestone(rec.issue_id, f"Blocked: base advanced and the branch conflicts — {str(exc)[:400]}")
                return "READY_FOR_OWNER -> BLOCKED (merge conflict)"
            new_head = self.worktrees.head_sha(path)
            self._invalidate_readiness(rec, new_head, f"base advanced by {behind} commit(s); merged base into the branch")
            return "READY_FOR_OWNER -> CI (base advanced, readiness invalidated)"
        return "awaiting owner"

    def _invalidate_readiness(self, rec: IssueRecord, new_head: str, why: str) -> None:
        self.store.record_event(rec.issue_id, "readiness_invalidated", {"old_head": rec.validated_commit, "new_head": new_head, "why": why})
        self._publish_review_status(self.store, rec.issue_id, new_head, "pending", f"stale: {why}; re-validating")
        self._ci_started[rec.issue_id] = self.clock()
        self._set_state(self.store, rec.issue_id, sm.CI, note=f"readiness invalidated: {why}", validated_commit=None)
        self._milestone(rec.issue_id, f"Readiness for `{str(rec.validated_commit)[:12]}` invalidated ({why}); re-running the gates for `{new_head[:12]}`.")

    def owner_merge(self, issue_id: int, requested_sha: str, *, source: str, owner_id, command_id: str) -> dict:
        """The ONLY merge path. Re-reads authoritative state immediately before merging and refuses
        on any mismatch. Returns a result dict that is also the audit payload."""
        store = self.thread_store()
        rec = store.get(issue_id)
        base = {"source": source, "owner_id": owner_id, "command_id": command_id, "issue": issue_id,
                "requested_sha": requested_sha, "ts": self.clock()}
        def refuse(reason: str, **extra) -> dict:
            res = {**base, "result": "REFUSED", "reason": reason, **extra}
            store.record_event(issue_id, "owner_merge_refused", res)
            return res
        if rec is None or not rec.pr_number:
            return refuse("ה-Issue אינו במעקב או שאין לו PR")
        if rec.state != sm.READY_FOR_OWNER:
            return refuse(f"ה-Issue במצב {rec.state}, לא READY_FOR_OWNER")
        if not rec.validated_commit or not requested_sha or not rec.validated_commit.startswith(requested_sha):
            return refuse("ה-SHA המבוקש אינו תואם ל-SHA המאומת — נדרש אימות מחדש",
                          validated_sha=rec.validated_commit)
        pr = self.github.get_pr(rec.pr_number)
        head = pr["head"]["sha"]
        if pr.get("merged"):
            return refuse("ה-PR כבר מוזג", merge_commit=pr.get("merge_commit_sha"))
        if head != rec.validated_commit:
            self._invalidate_readiness(rec, head, "head moved before the owner's merge")
            return refuse("ה-PR השתנה מאז האימות. נדרש אימות מחדש.", pr_head=head, validated_sha=rec.validated_commit)
        contract = self.refresh_contract(store, rec)
        if contract is None:
            return refuse("החוזה החי אינו תקין")
        rec = store.get(issue_id)
        self._ensure_review_status(store, rec, head)
        ev = ci_evidence.collect(self.github, self.config, head, fetch_logs=False)
        decision = merge_policy.decide(rec, ev, self.config, review_sha=_review_sha(rec), lost_allowance=contract.lost_allowance,
                                       require_github_gates=True)
        if not decision.ok:
            return refuse(f"השערים אינם ירוקים ל-{head[:12]} (gates not green): {decision.describe()}")
        self.worktrees.fetch()
        try:
            behind = self.worktrees.behind_base(Path(rec.worktree))
        except GitError:
            behind = 0
        if behind > 0:
            return refuse(f"ה-base התקדם ב-{behind} קומיט(ים) — נדרש אימות מחדש על base עדכני (base advanced; האורקסטרטור יעדכן את הענף)")
        _, gate_states = ev.required_contexts_green(self.config.protection_required_contexts)
        try:
            res = self.github.merge_pr(rec.pr_number, method=self.config.merge_method, title=f"{rec.title} (#{rec.pr_number})", sha=head)
        except Exception as exc:  # noqa: BLE001
            return refuse(f"GitHub סירב למיזוג: {str(exc)[:300]}")
        merge_sha = res.get("sha")
        self._set_state(store, issue_id, sm.MERGED, note=f"merged by the owner via {source}", validated_commit=merge_sha)
        result = {**base, "result": "SUCCESS", "actual_validated_sha": head, "pr": rec.pr_number, "merge_commit": merge_sha}
        store.record_event(issue_id, "merged", {"pr": rec.pr_number, "merge_sha": merge_sha, "method": self.config.merge_method, "by": f"owner via {source}"})
        store.record_event(issue_id, "merge_gate_audit", {"head": head, "contexts": gate_states, "bypass": False, "policy": decision.describe(),
                                                          "source": source, "owner_id": owner_id, "command_id": command_id})
        self._milestone(issue_id, f"Merged PR #{rec.pr_number} into `{self.config.base_branch}` on the owner's command ({source}; {self.config.merge_method}, `{str(merge_sha)[:12]}`). Running post-merge smoke.")
        return result

    def owner_reject(self, issue_id: int, *, source: str, owner_id, command_id: str, reason: str) -> dict:
        store = self.thread_store()
        rec = store.get(issue_id)
        if rec is None or rec.state != sm.READY_FOR_OWNER:
            return {"result": "REFUSED", "reason": f"issue is {rec.state if rec else 'untracked'}, not READY_FOR_OWNER"}
        self.locks.release(issue_id, "owner-reject")
        self._set_state(store, issue_id, sm.BLOCKED, note="rejected by the owner", failure_class="OWNER_REJECTED", last_error=reason[:1000])
        self._milestone(issue_id, f"Rejected by the owner ({source}): {reason[:400]}")
        return {"result": "SUCCESS", "issue": issue_id, "pr": rec.pr_number}

    def owner_change_request(self, issue_id: int, *, source: str, owner_id, command_id: str, feedback: str) -> dict:
        store = self.thread_store()
        rec = store.get(issue_id)
        if rec is None or rec.state not in (sm.READY_FOR_OWNER, sm.BLOCKED):
            return {"result": "REFUSED", "reason": f"issue is {rec.state if rec else 'untracked'}"}
        store.record_event(issue_id, "owner_change_request", {"source": source, "owner_id": owner_id, "feedback": feedback[:2000]})
        _save_evidence_note(self.config, issue_id, f"OWNER CHANGE REQUEST ({source}):\n\n{feedback}")
        if rec.kind == "rollup":
            # No single worker owns a rollup: the Team Lead decides (exclude a child, return a worker
            # to implementation, or modify the integration branch) and the rollup re-validates.
            self._set_state(store, issue_id, sm.BLOCKED, note="owner change request on the rollup", failure_class="OWNER_CHANGE_REQUEST",
                            last_error=feedback[:1000])
            self._milestone(issue_id, f"Owner change request on the rollup ({source}): {feedback[:400]}\n\nTeam Lead decision required "
                                      f"(rollup_exclude / return a worker / modify the integration branch), then `resume-pr`.")
            return {"result": "SUCCESS", "issue": issue_id, "pr": rec.pr_number, "rollup": True}
        self._set_state(store, issue_id, sm.FIX_REQUIRED, note="owner change request", failure_class="OWNER_CHANGE_REQUEST",
                        last_error=feedback[:1000])
        self._milestone(issue_id, f"Owner change request ({source}): {feedback[:400]}\n\nA repair attempt will address it; the PR will be re-validated and re-reported when ready.")
        return {"result": "SUCCESS", "issue": issue_id, "pr": rec.pr_number}

    # -- post-merge ---------------------------------------------------------------------------
    def _step_merged(self, rec: IssueRecord) -> str:
        if self.dry_run:
            return "DRY-RUN would run smoke"
        if self._thread_active(f"smoke:{rec.issue_id}"):
            return "smoke running"
        job = self.resources.try_acquire_heavy(rec.issue_id, "smoke")
        if job is None:
            return "smoke waiting for the heavy pool"
        self._spawn(f"smoke:{rec.issue_id}", self._smoke_run, rec.issue_id, job)
        return "smoke started"

    def _smoke_run(self, issue_id: int, job) -> None:
        store = self.thread_store()
        rec = store.get(issue_id)
        if rec is None or rec.state != sm.MERGED:
            self.resources.release_heavy(job, "skipped")
            return
        results: list[str] = []
        ok = True
        path = None
        try:
            self.worktrees.fetch()
            main_ref = self.worktrees.base_ref(self.config.base_branch)
            path = self.worktrees.validation_worktree(main_ref)
            if rec.validated_commit:
                anc = run_git(["merge-base", "--is-ancestor", rec.validated_commit, "HEAD"], path, check=False)
                if anc.returncode != 0:
                    raise RuntimeError(f"merge commit {rec.validated_commit[:12]} is not on {main_ref} yet")
            for cmd in self.config.worktree_setup.get("always", ()):
                proc = _sh(cmd.cmd, path / cmd.cwd, self.config.command_timeout_seconds, self.config.command_env)
                if proc.returncode != 0:
                    raise RuntimeError(f"setup `{cmd.cmd}` failed: {proc.stderr[-500:]}")
            for cmd in self.config.smoke:
                self.resources.heartbeat_heavy(job)
                proc = _sh(cmd.cmd, path / cmd.cwd, self.config.command_timeout_seconds, self.config.command_env)
                tail = (proc.stdout.strip().splitlines() or [""])[-1][:200]
                results.append(f"{'✅' if proc.returncode == 0 else '❌'} `{cmd.cmd}` — {tail or proc.stderr[-200:]}")
                if proc.returncode != 0:
                    ok = False
        except Exception as exc:  # noqa: BLE001
            ok = False
            results.append(f"❌ smoke setup failed: {str(exc)[:300]}")
        finally:
            if path is not None:
                try:
                    self.worktrees.remove_validation_worktree(path)
                except Exception:  # noqa: BLE001
                    pass
            self.resources.release_heavy(job, "done" if ok else "failed")
        summary = "\n".join(results)
        store.record_event(issue_id, "smoke", {"ok": ok, "results": results})
        if not ok:
            self._set_state(store, issue_id, sm.BLOCKED, note="post-merge smoke failed", failure_class="SMOKE_FAILED", last_error=summary[:1000])
            self._milestone(issue_id, f"Post-merge smoke FAILED on `{self.config.base_branch}`:\n{summary}\n\nTeam Lead attention required.")
            return
        self._finish(store, rec, summary)

    def _finish(self, store: StateStore, rec: IssueRecord, smoke_summary: str) -> None:
        events = store.events(rec.issue_id, limit=500)
        runs = [e for e in events if e["kind"] == "agent_run"]
        cost = sum((e["payload"].get("cost_usd") or 0) for e in runs)
        record = (f"Done.\n\n- PR: #{rec.pr_number} ({rec.pr_url})\n- merge commit: `{rec.validated_commit}`\n"
                  f"- worker attempts: {rec.attempt_number}\n- agent runs: {len(runs)} (≈ ${cost:.2f})\n"
                  f"- review: {rec.review_verdict}\n- post-merge smoke:\n{smoke_summary}\n- completed: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(self.clock()))}")
        self._set_state(store, rec.issue_id, sm.DONE, note="smoke green")
        self._milestone(rec.issue_id, record)
        if rec.kind == "rollup":
            self._finish_rollup(store, rec)
        try:
            self.github.close_issue(rec.issue_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("closing #%s failed: %s", rec.issue_id, exc)
        self.locks.release(rec.issue_id, "done")
        try:
            contract = self._contract(rec)
            self.worktrees.remove(rec.issue_id, contract.slug, delete_branch=True, force=True)
            if self.config.delete_branch_after_merge and rec.branch:
                self.github.delete_branch(rec.branch)
        except Exception as exc:  # noqa: BLE001
            log.warning("cleanup for #%s failed: %s", rec.issue_id, exc)
        store.record_event(rec.issue_id, "done", {"pr": rec.pr_number, "merge_sha": rec.validated_commit})

    # -- break-glass detection ----------------------------------------------------------------
    def audit_external_merge(self, rec: IssueRecord, pr: dict) -> dict:
        """A PR merged outside the workflow: record whether every required context was green on its
        head SHA. If not, someone used the admin exemption (break-glass) — logged, commented, never hidden."""
        head = pr.get("head", {}).get("sha", "")
        try:
            ev = ci_evidence.collect(self.github, self.config, head, fetch_logs=False, fetch_artifacts=False)
            ok, states = ev.required_contexts_green(self.config.protection_required_contexts)
        except Exception as exc:  # noqa: BLE001
            ok, states = False, {"error": str(exc)[:200]}
        payload = {"pr": pr.get("number"), "head": head, "contexts": states, "bypass": not ok, "merged_by": (pr.get("merged_by") or {}).get("login")}
        self.store.record_event(rec.issue_id, "merge_gate_audit", payload)
        if not ok:
            self.store.record_event(rec.issue_id, "admin_bypass_detected", payload)
            log.warning("#%s: PR #%s was merged with required contexts not green: %s", rec.issue_id, pr.get("number"), states)
            self._milestone(rec.issue_id, f"⚠️ PR #{pr.get('number')} was merged outside the workflow with required gates not green "
                                          f"({', '.join(f'{k}={v}' for k, v in states.items())}) — recorded as an admin break-glass bypass.")
        return payload

    def check_branch_protection(self) -> list[str]:
        """Detect protection drift (required contexts / admin enforcement changed). Returns audit notes."""
        notes: list[str] = []
        try:
            prot = self.github.get_branch_protection(self.config.base_branch)
        except Exception as exc:  # noqa: BLE001
            return [f"protection check failed: {str(exc)[:120]}"]
        contexts = sorted((prot or {}).get("required_status_checks", {}).get("contexts", []) or []) if prot else []
        enforce = bool(((prot or {}).get("enforce_admins") or {}).get("enabled")) if prot else False
        fingerprint = json.dumps({"contexts": contexts, "enforce_admins": enforce, "protected": prot is not None}, sort_keys=True)
        previous = self.store.get_meta("protection_fingerprint")
        if previous != fingerprint:
            self.store.set_meta("protection_fingerprint", fingerprint)
            self.store.record_event(None, "protection_observed", json.loads(fingerprint))
            if previous is not None:
                self.store.record_event(None, "protection_drift", {"before": json.loads(previous), "after": json.loads(fingerprint)})
                notes.append(f"branch protection changed: {previous} -> {fingerprint}")
        missing = [c for c in self.config.protection_required_contexts if c not in contexts]
        if prot is None:
            notes.append(f"{self.config.base_branch} is NOT protected — autonomous merges still verify every gate, but nothing stops a manual bypass")
        elif missing:
            notes.append(f"branch protection is missing required contexts {missing}")
        if prot is not None and not enforce:
            notes.append("branch protection exempts admins (break-glass only — bypasses are audited)")
        return notes

    # -- domain lead (on demand) --------------------------------------------------------------
    def investigate(self, domain: str, question: str, *, cwd: Path | None = None) -> AgentRunResult:
        path = cwd or self.config.repo_root
        spec = AgentRunSpec(role=DOMAIN_LEAD, issue_id=0, attempt=1, model=self.config.models["domain_lead"], cwd=path,
                            prompt=prompts.domain_lead_prompt(domain=domain, question=question, worktree=str(path)),
                            timeout_seconds=self.config.domain_lead_timeout_seconds, system_prompt=prompts.ROLE_SYSTEM_PROMPTS[DOMAIN_LEAD],
                            json_schema=DOMAIN_LEAD_BRIEF_SCHEMA, tools=self.config.domain_lead_tools, restricted=True,
                            effort=self.config.claude_effort, session_name=f"agent-domain-lead-{domain}", persist_session=False)
        result = self.runner.run(spec)
        audit.write_run_record(self.config, spec, result, extra={"domain": domain, "question": question})
        return result


# --------------------------------------------------------------------------------------------
# module helpers
# --------------------------------------------------------------------------------------------

def _sh(cmd: str, cwd: Path, timeout: int, extra_env: dict[str, str] | None = None):
    import subprocess
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GH_TOKEN", "GITHUB_TOKEN"))}
    for k, v in (extra_env or {}).items():
        env.setdefault(k, v)
    return subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)


def _has_untracked(path: Path) -> bool:
    return bool(run_git(["status", "--porcelain", "--untracked-files=all"], path).stdout.strip())


def _contract_to_dict(c: IssueContract) -> dict:
    from agent_team.issue_contract import render_body
    return {"title": c.title, "body": render_body(c), "risk": c.risk, "resource_class": c.resource_class,
            "domains": list(c.domains), "dependencies": list(c.dependencies), "slug": c.slug}


def _body_from_dict(d: dict) -> str:
    return d["body"]


def _review_sha(rec: IssueRecord) -> str | None:
    if rec.review_verdict and "@" in rec.review_verdict:
        return rec.review_verdict.split("@", 1)[1]
    return None


def _already_rerun(store: StateStore, issue_id: int, head: str) -> bool:
    return any(e["kind"] == "ci_rerun" and e["payload"].get("head") == head for e in store.events(issue_id, limit=500))


def _last_worker_report(store: StateStore, issue_id: int) -> dict:
    for e in reversed(store.events(issue_id, limit=500)):
        if e["kind"] == "worker_report":
            return e["payload"].get("report", {})
    return {}


def _evidence_path(config: Config, issue_id: int) -> Path:
    return config.path(config.logs_dir) / "evidence" / f"{issue_id}.md"


def _save_evidence_note(config: Config, issue_id: int, text: str) -> None:
    p = _evidence_path(config, issue_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _load_evidence_note(config: Config, issue_id: int) -> str:
    p = _evidence_path(config, issue_id)
    return p.read_text(encoding="utf-8") if p.exists() else "(no evidence recorded)"


def _verdict_markdown(v: dict) -> str:
    lines = [f"### Independent review (Sonnet): **{v.get('verdict')}**", "", v.get("summary", ""), "", "| AC | Verdict | Note |", "|---|---|---|"]
    for a in v.get("ac_assessment", []):
        lines.append(f"| {a.get('ac')} | {a.get('verdict')} | {str(a.get('note', '')).replace('|', '/')[:200]} |")
    flags = [k for k in ("unrelated_changes", "hidden_behavior_changes", "tolerance_hacks", "silent_fallback") if v.get(k)]
    lines += ["", f"tests meaningful: {v.get('tests_meaningful')} · architecture appropriate: {v.get('architecture_appropriate')}"
              + (f" · flags: {', '.join(flags)}" if flags else "")]
    if v.get("findings"):
        lines += ["", "Findings:"]
        for f in v["findings"]:
            loc = f"{f.get('file')}" + (f":{f['line']}" if f.get("line") else "")
            lines.append(f"- **{f.get('severity')}** `{loc}` — {f.get('summary')}")
    lines += ["", "<sub>Advisory verdict recorded by the orchestrator; it can block but never overrides a deterministic gate.</sub>"]
    return "\n".join(lines)


def render_ready_report(r: dict) -> str:
    """The Issue-comment form of the READY FOR OWNER report (concise, decision-oriented)."""
    lines = [f"READY FOR OWNER — PR #{r['pr']} ({r['pr_url'] or ''})", "",
             f"- ROOT Issue: #{r.get('root') or r['issue']}" + (f" · Child Issue: #{r['issue']}" if r.get('root') and r.get('root') != r['issue'] else ""),
             f"- Issue: #{r['issue']} {r['title']}", f"- Branch: `{r['branch']}`", f"- Head SHA: `{r['head']}`", f"- Risk: {r['risk']}", "",
             f"**Summary**: {r['summary'] or '(see PR description)'}"]
    if r["what_changed"]:
        lines += ["", "**What changed**:", *[f"- {x}" for x in r["what_changed"]]]
    if r["acceptance"]:
        lines += ["", "**Acceptance Criteria**:", *[f"- {x}" for x in r["acceptance"]]]
    lines += ["", f"**CI**: {r['ci']} ({', '.join(f'{k}={v}' for k, v in r['gates'].items())})",
              f"**Tests**: {r['tests']}", f"**Regression**: {r['regression']}", f"**Independent review**: {r['review']} ({r['review_count']} run(s))",
              f"**Failures/retries**: {'; '.join(r['failures']) if r['failures'] else 'none'} (worker attempts: {r['attempts']})",
              f"**Known limitations**: {'; '.join(r['limitations']) if r['limitations'] else 'none'}", "",
              f"**Opus recommendation**: {r['recommendation']}", "",
              "The orchestrator does not merge. Merge via Telegram (Merge → CONFIRM MERGE) or the GitHub Merge button; "
              "a new commit on the PR invalidates this readiness and triggers re-validation."]
    return "\n".join(lines)


def render_ready_notification(r: dict) -> str:
    """The short Telegram form."""
    root = f" (ROOT #{r['root']})" if r.get("root") and r["root"] != r["issue"] else ""
    lines = [f"PR #{r['pr']} READY FOR OWNER — מוכן לאישורך", "", f"Issue #{r['issue']}{root}", r["title"][:120], "",
             f"סיכון: {r['risk']}", f"CI: {r['ci']}", f"רגרסיה: {r['regression'].split(' (')[0]}", f"ביקורת עצמאית: {r['review']}", "",
             f"Head SHA:\n{r['head']}", "", f"תקציר:\n{r['summary'] or '(ראה PR)'}"]
    if r["failures"]:
        lines += ["", "כשלונות/ניסיונות חוזרים: " + "; ".join(r["failures"])[:300]]
    if r["limitations"]:
        lines += ["", "מגבלות ידועות: " + "; ".join(r["limitations"])[:300]]
    lines += ["", f"המלצת Opus: {r['recommendation']}", "", r["pr_url"] or ""]
    return "\n".join(lines)
