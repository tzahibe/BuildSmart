"""The orchestrator: a deterministic loop over the issue state machine.

    tick():  reconcile -> poll (agent:queued) -> schedule (start workers) -> advance (every
             tracked issue one step: PR_OPEN -> CI -> REVIEW -> READY -> MERGED -> DONE, or
             FIX_REQUIRED -> WORKING, or -> BLOCKED)

Long-running agent runs (worker, repair, reviewer) execute in threads with their own SQLite
connection; the main loop never blocks on a model. Every state change is a compare-and-set in
the state store and is mirrored to the Issue's `agent:*` label; every milestone is a concise
Issue comment; every agent run is a redacted JSON record under `.agent/logs/runs/`.

DRY_RUN: polls and schedules against a separate state file, prints the proposed assignments,
and performs no GitHub write, no spawn, no push, no merge.
"""
from __future__ import annotations

import fcntl
import json
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
from agent_team.issue_contract import ContractError, IssueContract, parse_contract, verification_manifest
from agent_team.labels import STATE_LABEL_PREFIX
from agent_team.locks import LockManager, effective_locks
from agent_team.pr_body import render_pr_body
from agent_team.resource_manager import ResourceManager, ResourceProbe
from agent_team.schemas import DOMAIN_LEAD_BRIEF_SCHEMA, REVIEW_VERDICT_SCHEMA, WORKER_REPORT_SCHEMA
from agent_team.state_store import IssueRecord, StateStore, TransitionConflict
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
        self._lock_fh = None
        self._ci_started: dict[int, float] = {}
        self.blocking_decisions: list[str] = []

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
        for rec in self.store.list((sm.PR_OPEN, sm.CI, sm.REVIEW, sm.FIX_REQUIRED, sm.READY, sm.MERGED)):
            try:
                outcome = self.advance(rec)
                if outcome:
                    report.advanced[rec.issue_id] = outcome
            except TransitionConflict as exc:
                log.warning("#%s: %s", rec.issue_id, exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("advance #%s failed", rec.issue_id)
                report.errors[rec.issue_id] = str(exc)[:200]
        self.store.set_meta("last_tick", str(self.clock()))
        return report

    def run(self, *, once: bool = False) -> None:
        self.acquire_singleton()
        previous = {}
        try:
            if not once:
                for sig in (signal.SIGTERM, signal.SIGINT):
                    previous[sig] = signal.signal(sig, lambda *_: self._stop.set())
            while True:
                report = self.tick()
                log.info("tick: %s", report.summary())
                if once or self._stop.is_set():
                    break
                self._stop.wait(self.config.poll_interval_seconds)
                if self._stop.is_set():
                    break
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            self.shutdown()

    def shutdown(self) -> None:
        self._stop.set()
        term = getattr(self.runner, "terminate_all", None)
        if callable(term):
            term()
        self.wait_for_threads(timeout=10)
        self.release_singleton()

    # -- poll ---------------------------------------------------------------------------------
    def poll(self) -> list[int]:
        """Track every executable `agent:queued` Issue exactly once. Idempotent."""
        new: list[int] = []
        for issue in self.github.list_issues(labels=self.config.poll_labels, state="open"):
            number = issue["number"]
            existing = self.store.get(number)
            if existing is not None and existing.state != sm.QUEUED:
                continue  # already claimed or further along: the label is stale, reconciliation fixes it
            if issue.get("author_association", "NONE") not in self.config.executable_author_associations:
                log.warning("#%s ignored: author association %s is not executable", number, issue.get("author_association"))
                continue
            try:
                contract = parse_contract(number, issue.get("title", ""), issue.get("body") or "", known_locks=self.config.known_locks,
                                          behavior_domains=self.config.behavior_domains)
            except ContractError as exc:
                if existing is None:
                    self._reject_contract(number, exc.problems)
                continue
            manifest = verification_manifest(contract, regression_domains=self.config.regression_domains)
            self.store.track(number, title=contract.title, risk=contract.risk, resource_class=contract.resource_class,
                             domains=list(contract.domains), dependencies=list(contract.dependencies),
                             contract=_contract_to_dict(contract))
            audit.write_contract_snapshot(self.config, number, contract.to_dict(), manifest)
            if existing is None:
                new.append(number)
        return new

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
    def schedule(self) -> list[scheduler.Decision]:
        queued = []
        for rec in self.store.list((sm.QUEUED,)):
            try:
                queued.append((rec, self._contract(rec)))
            except ContractError as exc:
                log.error("#%s: stored contract no longer parses: %s", rec.issue_id, exc)
        if not queued:
            return []
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
        for d in decisions:
            if d.starts:
                rec, contract = by_id[d.issue_id]
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
                pr = self.github.create_pr(head=rec.branch, base=self.config.base_branch, title=f"{contract.title} (#{issue_id})", body=body)
                self._milestone(issue_id, f"PR opened: {pr.get('html_url', pr['number'])} (attempt {spec.attempt}, head `{head[:12]}`).")
            else:
                self.github.update_pr(pr["number"], body=body)
                self._milestone(issue_id, f"Repair attempt {spec.attempt - 1} pushed to PR #{pr['number']} (head `{head[:12]}`).")
            store.update(issue_id, agent_pid=None, assigned_agent=None)
            self._set_state(store, issue_id, sm.PR_OPEN, note="PR ready", pr_number=pr["number"], pr_url=pr.get("html_url"),
                            validated_commit=None)
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
        if rec.state == sm.READY:
            return self._step_ready(rec)
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
                return self.worktrees.changed_files(Path(rec.worktree), self.worktrees.base_ref())
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
        snap = self.resources.snapshot(probe_machine=True)
        adm = self.resources.can_start_worker(rec.resource_class, snap)
        if not adm.ok:
            return f"repair waiting: {adm.reason}"
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
            self._set_state(self.store, rec.issue_id, sm.READY, note=f"policy satisfied: {decision.describe()}")
            self._milestone(rec.issue_id, f"Ready to merge under the {rec.risk} policy ({decision.describe()}).")
            return "REVIEW -> READY"
        return f"awaiting {', '.join(decision.missing)}"

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
            files = "\n".join(self.worktrees.changed_files(path, self.worktrees.base_ref()))
            diff = self.worktrees.diff(path, self.worktrees.base_ref())
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
            log.warning("#%s: reviewer failed (%s); will retry next tick", issue_id, result.error[:200])
            return
        verdict = result.structured
        v = verdict.get("verdict", "BLOCK")
        # SEMANTIC_REVIEW criteria are evidence only when the reviewer marked them MET.
        semantic = contract.semantic_review_acs
        assessed = {a.get("ac"): a.get("verdict") for a in verdict.get("ac_assessment", []) if isinstance(a, dict)}
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
    def _step_ready(self, rec: IssueRecord) -> str:
        pr, head = self._pr_head(rec)
        if pr.get("merged"):
            self._set_state(self.store, rec.issue_id, sm.MERGED, note="merged externally", validated_commit=pr.get("merge_commit_sha"))
            return "READY -> MERGED (externally)"
        if head != rec.validated_commit:
            self._set_state(self.store, rec.issue_id, sm.CI, note="head changed after validation")
            self._ci_started[rec.issue_id] = self.clock()
            return "READY -> CI (head changed)"
        path = Path(rec.worktree)
        self.worktrees.fetch()
        try:
            behind = self.worktrees.behind_base(path)
        except GitError:
            behind = 0
        if behind > 0:
            if self.dry_run:
                return f"DRY-RUN would update branch ({behind} behind) and re-validate"
            try:
                self.worktrees.update_from_base(path)
                self.worktrees.push(path, rec.branch)
            except MergeConflict as exc:
                self.locks.release(rec.issue_id, "merge-conflict")
                self._set_state(self.store, rec.issue_id, sm.BLOCKED, note=MERGE_CONFLICT, failure_class=MERGE_CONFLICT, last_error=str(exc)[:1000])
                self._milestone(rec.issue_id, f"Blocked: base advanced and the branch conflicts — {str(exc)[:400]}")
                return "READY -> BLOCKED (merge conflict)"
            self._ci_started[rec.issue_id] = self.clock()
            self._set_state(self.store, rec.issue_id, sm.CI, note="base advanced: merged base, re-validating", validated_commit=None)
            self._milestone(rec.issue_id, f"Base `{self.config.base_branch}` advanced by {behind} commit(s); merged it into the branch and re-running the gates before merge.")
            return "READY -> CI (base advanced)"
        if self.dry_run:
            return "DRY-RUN would merge"
        contract = self.refresh_contract(self.store, rec)
        if contract is None:
            return "READY -> BLOCKED (live contract invalid)"
        rec = self.store.get(rec.issue_id)
        self._ensure_review_status(self.store, rec, head)
        ev = ci_evidence.collect(self.github, self.config, head, fetch_logs=False)
        decision = merge_policy.decide(rec, ev, self.config, review_sha=_review_sha(rec),
                                       lost_allowance=contract.lost_allowance, require_github_gates=True)
        if not decision.ok:
            if decision.missing == ("github_gates_green",):
                # policy holds locally but GitHub does not (yet) show every required context green:
                # never merge through the admin exemption — wait and re-check.
                self.store.record_event(rec.issue_id, "merge_deferred", {"reason": decision.describe()})
                return f"merge deferred: {decision.describe()}"
            self._set_state(self.store, rec.issue_id, sm.CI, note=f"policy no longer satisfied: {decision.describe()}")
            return "READY -> CI (policy re-check failed)"
        _, gate_states = ev.required_contexts_green(self.config.protection_required_contexts)
        try:
            res = self.github.merge_pr(rec.pr_number, method=self.config.merge_method, title=f"{rec.title} (#{rec.pr_number})", sha=head)
        except Exception as exc:  # noqa: BLE001
            self._set_state(self.store, rec.issue_id, sm.BLOCKED, note="merge failed", failure_class="MERGE_FAILED", last_error=str(exc)[:1000])
            self._milestone(rec.issue_id, f"Blocked: merge failed — {str(exc)[:400]}")
            return "READY -> BLOCKED (merge failed)"
        merge_sha = res.get("sha")
        self._set_state(self.store, rec.issue_id, sm.MERGED, note="merged", validated_commit=merge_sha)
        self.store.record_event(rec.issue_id, "merged", {"pr": rec.pr_number, "merge_sha": merge_sha, "method": self.config.merge_method})
        self.store.record_event(rec.issue_id, "merge_gate_audit", {"head": head, "contexts": gate_states, "bypass": False,
                                                                    "policy": decision.describe()})
        self._milestone(rec.issue_id, f"Merged PR #{rec.pr_number} into `{self.config.base_branch}` ({self.config.merge_method}, `{str(merge_sha)[:12]}`). Running post-merge smoke.")
        return "READY -> MERGED"

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
            path = self.worktrees.validation_worktree(self.worktrees.base_ref())
            if rec.validated_commit:
                anc = run_git(["merge-base", "--is-ancestor", rec.validated_commit, "HEAD"], path, check=False)
                if anc.returncode != 0:
                    raise RuntimeError(f"merge commit {rec.validated_commit[:12]} is not on {self.worktrees.base_ref()} yet")
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
