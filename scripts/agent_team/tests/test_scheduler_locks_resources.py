from __future__ import annotations

import pytest

from agent_team import state_machine as sm
from agent_team.locks import LockManager, effective_locks
from agent_team.resource_manager import FakeProbe, ResourceManager
from agent_team.scheduler import plan
from agent_team.state_store import StateStore
from agent_team.tests.helpers import make_contract, track


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(repo_config, tmp_path):
    store = StateStore(tmp_path / "s.sqlite3", clock=Clock())
    probe = FakeProbe(cpu=10.0, free_gb=20.0)
    rm = ResourceManager(repo_config, store, probe)
    lm = LockManager(store, repo_config)
    yield repo_config, store, rm, lm, probe
    store.close()


def _plan(env, contracts, external=None):
    config, store, rm, lm, _ = env
    queued = []
    for c in contracts:
        rec = store.get(c.number) or track(store, c)
        if rec.state == sm.QUEUED:
            queued.append((rec, c))
    snap = rm.snapshot(probe_machine=True)
    return plan(queued, config=config, store=store, locks=lm, resources=rm, snapshot=snap, external_satisfied=external)


def test_independent_issues_start_up_to_worker_cap(env):
    c1, c2, c3 = (make_contract(n, locks="none", domains="qa") for n in (1, 2, 3))
    decisions = _plan(env, [c1, c2, c3])
    assert [d.action for d in decisions] == ["start", "start", "wait"]
    assert "worker slots full" in decisions[2].reason


def test_weighted_capacity_blocks_a_heavy_next_to_a_medium(env):
    c1 = make_contract(1, resource="MEDIUM", locks="none", domains="qa")
    c2 = make_contract(2, resource="HEAVY", locks="none", domains="qa")
    decisions = _plan(env, [c1, c2])
    assert decisions[0].action == "start"
    assert decisions[1].action == "wait" and "weighted capacity" in decisions[1].reason


def test_running_workers_consume_capacity(env):
    config, store, rm, lm, _ = env
    running = make_contract(1, resource="HEAVY", locks="none", domains="qa")
    track(store, running)
    store.transition(1, sm.CLAIMED)
    store.transition(1, sm.WORKING)
    c2 = make_contract(2, resource="MEDIUM", locks="none", domains="qa")
    decisions = _plan(env, [c2])
    assert decisions[0].action == "wait" and "weighted capacity 3+2 > 4" in decisions[0].reason
    snap = rm.snapshot(probe_machine=False)
    assert snap.workers_running == 1 and snap.weighted_used == 3


def test_machine_pressure_blocks_spawning(env):
    config, store, rm, lm, probe = env
    probe.cpu = 95.0
    d = _plan(env, [make_contract(1, locks="none", domains="qa")])
    assert d[0].action == "wait" and "CPU 95%" in d[0].reason
    probe.cpu = 10.0
    probe.free_gb = 1.0
    d = _plan(env, [make_contract(1, locks="none", domains="qa")])
    assert d[0].action == "wait" and "free memory" in d[0].reason


def test_dependency_blocks_until_done(env):
    config, store, rm, lm, _ = env
    dep = make_contract(200, locks="none", domains="qa")
    child = make_contract(201, deps="#200", locks="none", domains="qa")
    d = _plan(env, [dep, child])
    assert d[0].action == "start" and d[1].action == "wait" and "waiting for #200 is QUEUED" in d[1].reason
    for st in (sm.CLAIMED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.REVIEW, sm.READY, sm.MERGED):
        store.transition(200, st)
    d = _plan(env, [child])
    assert d[0].action == "wait"  # MERGED is not DONE (smoke not yet green)
    store.transition(200, sm.DONE)
    d = _plan(env, [child])
    assert d[0].action == "start"


def test_blocked_dependency_reports_blocked(env):
    config, store, rm, lm, _ = env
    dep = make_contract(300, locks="none", domains="qa")
    track(store, dep)
    store.transition(300, sm.BLOCKED)
    child = make_contract(301, deps="#300", locks="none", domains="qa")
    d = _plan(env, [child])
    assert d[0].action == "wait" and d[0].reason == "blocked by #300"


def test_external_closed_dependency_is_satisfied(env):
    child = make_contract(401, deps="#5", locks="none", domains="qa")
    assert _plan(env, [child])[0].action == "wait"
    assert _plan(env, [child], external={5})[0].action == "start"


def test_exclusive_lock_conflict_within_one_tick(env):
    a = make_contract(1, locks="planner-core (exclusive)")
    b = make_contract(2, locks="planner-core (exclusive)")
    d = _plan(env, [a, b])
    assert d[0].action == "start" and d[0].locks[0].name == "planner-core"
    assert d[1].action == "wait" and "planner-core(exclusive) held by #1" in d[1].reason


def test_shared_locks_coexist_but_not_with_exclusive(env):
    a = make_contract(1, locks="knowledge-index (shared)")
    b = make_contract(2, locks="knowledge-index (shared)")
    c = make_contract(3, locks="knowledge-index (exclusive)")
    d = _plan(env, [a, b, c])
    assert [x.action for x in d] == ["start", "start", "wait"]


def test_persisted_lock_blocks_across_ticks(env):
    config, store, rm, lm, _ = env
    a = make_contract(1, locks="geometry-core (exclusive)")
    track(store, a)
    assert lm.acquire(1, a.locks).ok
    store.transition(1, sm.CLAIMED)
    b = make_contract(2, locks="geometry-core (shared)")
    d = _plan(env, [b])
    assert d[0].action == "wait" and "geometry-core(exclusive) held by #1" in d[0].reason
    lm.release(1)
    assert _plan(env, [b])[0].action == "start"


def test_implied_locks_from_domains(env):
    config, *_ = env
    c = make_contract(1, locks="none", domains="geometry, knowledge")
    names = [l.name for l in effective_locks(c, config)]
    assert names == ["geometry-core", "knowledge-index"]
    explicit = make_contract(2, locks="docs (shared)", domains="geometry")
    assert [l.name for l in effective_locks(explicit, config)] == ["docs"]


def test_stale_lock_recovery(env):
    config, store, rm, lm, _ = env
    clock = store.clock
    a = make_contract(1, locks="planner-core (exclusive)")
    track(store, a)
    store.transition(1, sm.CLAIMED)
    store.transition(1, sm.WORKING, started_at=clock(), heartbeat_at=clock())
    assert lm.acquire(1, a.locks).ok
    # heartbeat fresh: nothing released
    assert lm.recover_stale(clock()) == []
    # heartbeat ancient: the owner is dead -> lock released, audit event recorded
    clock.t += config.lock_stale_after_seconds + 1
    released = lm.recover_stale(clock())
    assert [r.name for r in released] == ["planner-core"]
    assert store.locks_held() == []
    assert any(e["kind"] == "locks_released" and e["payload"]["reason"] == "stale-recovery" for e in store.events(1))


def test_lock_of_done_issue_is_stale(env):
    config, store, rm, lm, _ = env
    a = make_contract(1, locks="docs (exclusive)")
    track(store, a)
    assert lm.acquire(1, a.locks).ok
    for st in (sm.CLAIMED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.REVIEW, sm.READY, sm.MERGED, sm.DONE):
        store.transition(1, st)
    assert [r.name for r in lm.recover_stale(store.clock())] == ["docs"]


def test_heavy_pool_independent_of_agent_slots(env):
    config, store, rm, lm, _ = env
    job = rm.try_acquire_heavy(1, "regression")
    assert job is not None
    assert rm.try_acquire_heavy(2, "pytest") is None          # pool full (concurrency 1)
    snap = rm.snapshot(probe_machine=False)
    assert snap.heavy_running == 1 and snap.workers_running == 0
    assert rm.can_start_worker("LIGHT", snap).ok                # agents unaffected by the heavy pool
    rm.release_heavy(job)
    assert rm.try_acquire_heavy(2, "pytest") is not None


def test_reviewer_admission(env):
    config, store, rm, lm, probe = env
    snap = rm.snapshot(probe_machine=False)
    assert rm.can_start_reviewer(snap).ok
    c = make_contract(1, locks="none", domains="qa")
    track(store, c)
    for st in (sm.CLAIMED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.REVIEW):
        store.transition(1, st)
    store.update(1, assigned_agent="reviewer:sonnet")
    snap = rm.snapshot(probe_machine=False)
    assert snap.reviewers_running == 1
    assert not rm.can_start_reviewer(snap).ok


def test_plan_is_deterministic_fifo(env):
    cs = [make_contract(n, locks="none", domains="qa") for n in (9, 3, 7)]
    d = _plan(env, cs)
    assert [x.issue_id for x in d] == [3, 7, 9]
    assert [x.action for x in d] == ["start", "start", "wait"]
