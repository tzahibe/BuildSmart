"""Resource-aware admission control.

Two independent pools:

- **agent slots** — weighted by resource class (LIGHT/MEDIUM/HEAVY -> 1/2/3 by default) against
  `weighted_capacity`, plus hard caps on worker/reviewer/domain-lead counts, plus a look at the
  real machine (CPU utilisation, free memory) before anything new is spawned.
- **heavy jobs** — full pytest, corpus regression, sweeps. `heavy_job_concurrency` (1 in V1) is a
  persisted semaphore in the state store, so a restart never double-books it and a crashed job
  cannot pin the pool (stale rows expire).

Agents being free never implies a heavy job may start, and vice versa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_team import state_machine as sm
from agent_team.config import Config
from agent_team.state_store import HeavyJob, IssueRecord, StateStore


class ResourceProbe(Protocol):
    def cpu_percent(self, window_seconds: float) -> float: ...
    def free_memory_gb(self) -> float: ...


class PsutilProbe:
    def cpu_percent(self, window_seconds: float) -> float:
        import psutil
        return float(psutil.cpu_percent(interval=window_seconds))

    def free_memory_gb(self) -> float:
        import psutil
        return psutil.virtual_memory().available / (1024 ** 3)


@dataclass
class FakeProbe:
    cpu: float = 10.0
    free_gb: float = 20.0

    def cpu_percent(self, window_seconds: float) -> float:
        return self.cpu

    def free_memory_gb(self) -> float:
        return self.free_gb


@dataclass(frozen=True)
class ResourceSnapshot:
    workers_running: int
    reviewers_running: int
    weighted_used: int
    heavy_running: int
    cpu_percent: float
    free_memory_gb: float
    running_issues: tuple[int, ...]

    def describe(self, config: Config) -> str:
        machine = ("not probed" if self.free_memory_gb == float("inf") else
                   f"CPU {self.cpu_percent:.0f}% (limit {config.cpu_threshold_percent:.0f}%)  "
                   f"free RAM {self.free_memory_gb:.1f} GiB (min {config.min_free_memory_gb:.1f})")
        return (f"workers {self.workers_running}/{config.max_worker_agents}  "
                f"reviewers {self.reviewers_running}/{config.max_reviewer_agents}  "
                f"weighted capacity {self.weighted_used}/{config.weighted_capacity}  "
                f"heavy jobs {self.heavy_running}/{config.heavy_job_concurrency}  {machine}")


@dataclass(frozen=True)
class Admission:
    ok: bool
    reason: str = ""


class ResourceManager:
    def __init__(self, config: Config, store: StateStore, probe: ResourceProbe | None = None):
        self.config = config
        self.store = store
        self.probe = probe or PsutilProbe()

    # -- observation --------------------------------------------------------------------------
    def snapshot(self, *, probe_machine: bool = True) -> ResourceSnapshot:
        active = self.store.list(sm.AGENT_ACTIVE_STATES)
        workers = [r for r in active if r.state == sm.WORKING]
        reviewers = [r for r in active if r.state == sm.REVIEW and r.assigned_agent]
        weighted = sum(self.weight(r.resource_class) for r in workers) + len(reviewers) * self.config.weights["LIGHT"]
        heavy = self.store.active_heavy_jobs(self.config.heavy_job_stale_after_seconds)
        cpu = self.probe.cpu_percent(self.config.probe_window_seconds) if probe_machine else 0.0
        mem = self.probe.free_memory_gb() if probe_machine else float("inf")
        return ResourceSnapshot(
            workers_running=len(workers), reviewers_running=len(reviewers), weighted_used=weighted,
            heavy_running=len(heavy), cpu_percent=cpu, free_memory_gb=mem,
            running_issues=tuple(r.issue_id for r in workers),
        )

    def weight(self, resource_class: str) -> int:
        return self.config.weights.get(resource_class.upper(), self.config.weights["MEDIUM"])

    # -- admission ----------------------------------------------------------------------------
    def can_start_worker(self, resource_class: str, snap: ResourceSnapshot, *, pending_weight: int = 0, pending_workers: int = 0) -> Admission:
        """`pending_*` let the scheduler account for starts it decided on in the same tick."""
        c = self.config
        if snap.workers_running + pending_workers >= c.max_worker_agents:
            return Admission(False, f"worker slots full ({snap.workers_running + pending_workers}/{c.max_worker_agents})")
        w = self.weight(resource_class)
        if snap.weighted_used + pending_weight + w > c.weighted_capacity:
            return Admission(False, f"weighted capacity {snap.weighted_used + pending_weight}+{w} > {c.weighted_capacity}")
        if snap.cpu_percent > c.cpu_threshold_percent:
            return Admission(False, f"CPU {snap.cpu_percent:.0f}% above threshold {c.cpu_threshold_percent:.0f}%")
        if snap.free_memory_gb < c.min_free_memory_gb:
            return Admission(False, f"free memory {snap.free_memory_gb:.1f} GiB below minimum {c.min_free_memory_gb:.1f}")
        return Admission(True)

    def can_start_reviewer(self, snap: ResourceSnapshot) -> Admission:
        c = self.config
        if snap.reviewers_running >= c.max_reviewer_agents:
            return Admission(False, f"reviewer slots full ({snap.reviewers_running}/{c.max_reviewer_agents})")
        if snap.cpu_percent > c.cpu_threshold_percent:
            return Admission(False, f"CPU {snap.cpu_percent:.0f}% above threshold")
        if snap.free_memory_gb < c.min_free_memory_gb:
            return Admission(False, "free memory below minimum")
        return Admission(True)

    # -- heavy pool ---------------------------------------------------------------------------
    def try_acquire_heavy(self, issue_id: int | None, kind: str, pid: int | None = None) -> HeavyJob | None:
        return self.store.try_start_heavy_job(issue_id, kind, self.config.heavy_job_concurrency,
                                              self.config.heavy_job_stale_after_seconds, pid)

    def heartbeat_heavy(self, job: HeavyJob) -> None:
        self.store.heartbeat_heavy_job(job.job_id)

    def release_heavy(self, job: HeavyJob, status: str = "done") -> None:
        self.store.finish_heavy_job(job.job_id, status)

    def heavy_jobs(self) -> list[HeavyJob]:
        return self.store.active_heavy_jobs(self.config.heavy_job_stale_after_seconds)
