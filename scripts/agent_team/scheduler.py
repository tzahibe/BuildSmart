"""Deterministic scheduling: which QUEUED issues may start this tick, and why the others wait.

Pure planning over a snapshot — no side effects — so it is trivially testable and its decisions
can be printed in dry-run exactly as they would be executed. Order is by ROOT Issue, then FIFO by number.
Each start decided in a tick is accounted for (weight, worker slot, locks) before the next
candidate is considered, so two MEDIUM issues never both start into one free slot.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent_team import state_machine as sm
from agent_team.config import Config
from agent_team.issue_contract import IssueContract, LockRequirement
from agent_team.locks import LockManager, effective_locks
from agent_team.resource_manager import ResourceManager, ResourceSnapshot
from agent_team.state_store import IssueRecord, LockRow, StateStore


@dataclass(frozen=True)
class Decision:
    issue_id: int
    action: str            # start | wait
    reason: str = ""
    locks: tuple[LockRequirement, ...] = ()

    @property
    def starts(self) -> bool:
        return self.action == "start"


def dependency_status(dep: int, store: StateStore, external_satisfied: set[int]) -> tuple[bool, str]:
    rec = store.get(dep)
    if rec is None:
        if dep in external_satisfied:
            return True, "closed on GitHub"
        return False, f"#{dep} not tracked/closed"
    if rec.state in sm.SATISFIES_DEPENDENCY:
        return True, rec.state
    return False, f"#{dep} is {rec.state}"


def plan(
    queued: list[tuple[IssueRecord, IssueContract]],
    *,
    config: Config,
    store: StateStore,
    locks: LockManager,
    resources: ResourceManager,
    snapshot: ResourceSnapshot,
    external_satisfied: set[int] | None = None,
) -> list[Decision]:
    external_satisfied = external_satisfied or set()
    decisions: list[Decision] = []
    pending_weight = 0
    pending_workers = 0
    granted: list[LockRow] = []

    # Priority: children of the earliest ROOT first (finish what is in flight), then FIFO by number.
    for rec, contract in sorted(queued, key=lambda rc: (rc[0].root, rc[0].issue_id)):
        waits: list[str] = []
        for dep in contract.dependencies:
            ok, why = dependency_status(dep, store, external_satisfied)
            if not ok:
                dep_rec = store.get(dep)
                if dep_rec is not None and dep_rec.state == sm.BLOCKED:
                    waits.append(f"blocked by #{dep}")
                else:
                    waits.append(f"waiting for {why}")
        if waits:
            decisions.append(Decision(rec.issue_id, "wait", "; ".join(waits)))
            continue

        reqs = effective_locks(contract, config)
        lock_decision = locks.check(rec.issue_id, reqs, extra_held=granted)
        if not lock_decision.ok:
            decisions.append(Decision(rec.issue_id, "wait", lock_decision.reason, reqs))
            continue

        admission = resources.can_start_worker(contract.resource_class, snapshot,
                                               pending_weight=pending_weight, pending_workers=pending_workers)
        if not admission.ok:
            decisions.append(Decision(rec.issue_id, "wait", admission.reason, reqs))
            continue

        decisions.append(Decision(rec.issue_id, "start", "dependencies satisfied, locks free, resources available", reqs))
        pending_weight += resources.weight(contract.resource_class)
        pending_workers += 1
        granted.extend(LockRow(r.name, r.mode, rec.issue_id, 0.0) for r in reqs)

    return decisions
