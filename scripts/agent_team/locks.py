"""Domain locks: semantic mutual exclusion that branches alone cannot give.

An Issue declares the locks it needs (or inherits them from its domains, see
`config.locks.implied_by_domain`). Two issues needing the same *exclusive* lock never run
concurrently; *shared* holders coexist with each other but not with an exclusive holder.

Locks live in the state store (they survive restarts). Stale recovery: a lock whose owner is no
longer in a resource-holding state, or whose owner's heartbeat is older than the TTL while it is
supposed to be running, is released with an audit event.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent_team import state_machine as sm
from agent_team.config import Config
from agent_team.issue_contract import IssueContract, LockRequirement
from agent_team.state_store import LockRow, StateStore


@dataclass(frozen=True)
class LockDecision:
    ok: bool
    conflicts: tuple[LockRow, ...] = ()

    @property
    def reason(self) -> str:
        if self.ok:
            return ""
        return "lock conflict: " + ", ".join(f"{c.name}({c.mode}) held by #{c.issue_id}" for c in self.conflicts)


def effective_locks(contract: IssueContract, config: Config) -> tuple[LockRequirement, ...]:
    """Explicit locks win; otherwise the locks implied by the affected domains (exclusive)."""
    if contract.locks:
        return contract.locks
    implied: list[LockRequirement] = []
    for domain in contract.domains:
        for name in config.implied_locks_by_domain.get(domain, ()):
            if not any(l.name == name for l in implied):
                implied.append(LockRequirement(name, "exclusive"))
    return tuple(implied)


class LockManager:
    def __init__(self, store: StateStore, config: Config):
        self.store = store
        self.config = config

    def check(self, issue_id: int, requirements: tuple[LockRequirement, ...], *, extra_held: list[LockRow] | None = None) -> LockDecision:
        """Non-mutating conflict check. `extra_held` lets the scheduler simulate locks it is about to grant."""
        conflicts: list[LockRow] = []
        for req in requirements:
            conflicts.extend(self.store.lock_conflicts(req.name, req.mode, issue_id))
            for h in extra_held or ():
                if h.name == req.name and h.issue_id != issue_id and (req.mode == "exclusive" or h.mode == "exclusive"):
                    conflicts.append(h)
        return LockDecision(ok=not conflicts, conflicts=tuple(conflicts))

    def acquire(self, issue_id: int, requirements: tuple[LockRequirement, ...]) -> LockDecision:
        conflicts = self.store.try_acquire_locks(issue_id, [(r.name, r.mode) for r in requirements])
        return LockDecision(ok=not conflicts, conflicts=tuple(conflicts))

    def release(self, issue_id: int, reason: str = "released") -> int:
        return self.store.release_locks(issue_id, reason)

    def recover_stale(self, now: float) -> list[LockRow]:
        """Release locks whose owner cannot legitimately hold them any more. Returns what was released."""
        released: list[LockRow] = []
        by_issue: dict[int, list[LockRow]] = {}
        for row in self.store.locks_held():
            by_issue.setdefault(row.issue_id, []).append(row)
        for issue_id, rows in by_issue.items():
            rec = self.store.get(issue_id)
            stale = False
            if rec is None or rec.state not in sm.RESOURCE_HOLDING_STATES:
                stale = True
            elif rec.state in sm.AGENT_ACTIVE_STATES:
                hb = rec.heartbeat_at or rec.started_at or 0.0
                if now - hb > self.config.lock_stale_after_seconds:
                    stale = True
            else:
                oldest = min(r.acquired_at for r in rows)
                # A lock held far beyond the TTL while nothing is running is a leak from a crash.
                if rec.heartbeat_at is None and now - oldest > self.config.lock_stale_after_seconds * 4:
                    stale = True
            if stale:
                self.store.release_locks(issue_id, reason="stale-recovery")
                released.extend(rows)
        return released
