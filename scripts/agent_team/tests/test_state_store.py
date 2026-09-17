from __future__ import annotations

import pytest

from agent_team import state_machine as sm
from agent_team.state_store import StateStore, TransitionConflict
from agent_team.tests.helpers import make_contract, track


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def store(tmp_path):
    s = StateStore(tmp_path / "state.sqlite3", clock=Clock())
    yield s
    s.close()


def test_track_then_transition_persists_across_reopen(tmp_path):
    clock = Clock()
    s = StateStore(tmp_path / "s.sqlite3", clock=clock)
    track(s, make_contract(10))
    s.transition(10, sm.CLAIMED, branch="agent/10-sample-task", worktree=".worktrees/10-sample-task")
    s.close()
    s2 = StateStore(tmp_path / "s.sqlite3", clock=clock)
    rec = s2.get(10)
    assert rec.state == sm.CLAIMED and rec.branch == "agent/10-sample-task"
    kinds = [e["kind"] for e in s2.events(10)]
    assert kinds == ["tracked", "transition"]


def test_illegal_transition_rejected(store):
    track(store, make_contract(1))
    with pytest.raises(sm.IllegalTransition):
        store.transition(1, sm.MERGED)  # QUEUED -> MERGED is not allowed
    assert store.get(1).state == sm.QUEUED


def test_compare_and_set_prevents_double_claim(store):
    track(store, make_contract(2))
    store.transition(2, sm.CLAIMED, allowed_from=(sm.QUEUED,))
    with pytest.raises(TransitionConflict):
        store.transition(2, sm.CLAIMED, allowed_from=(sm.QUEUED,))
    assert store.get(2).state == sm.CLAIMED


def test_track_is_idempotent_and_never_resets_state(store):
    c = make_contract(3)
    track(store, c)
    store.transition(3, sm.CLAIMED)
    track(store, c)  # re-polled: metadata refresh only
    assert store.get(3).state == sm.CLAIMED
    assert len(store.list((sm.CLAIMED,))) == 1


def test_full_happy_path_is_legal(store):
    track(store, make_contract(4))
    for st in (sm.CLAIMED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.REVIEW, sm.READY, sm.MERGED, sm.DONE):
        store.transition(4, st)
    assert store.get(4).state == sm.DONE
    with pytest.raises(sm.IllegalTransition):
        store.transition(4, sm.QUEUED)


def test_repair_loop_transitions(store):
    track(store, make_contract(5))
    for st in (sm.CLAIMED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.FIX_REQUIRED, sm.WORKING, sm.PR_OPEN, sm.CI, sm.BLOCKED, sm.QUEUED):
        store.transition(5, st)
    assert store.get(5).state == sm.QUEUED


def test_update_refuses_state(store):
    track(store, make_contract(6))
    with pytest.raises(ValueError):
        store.update(6, state=sm.DONE)
    store.update(6, pr_number=77, last_error="boom")
    rec = store.get(6)
    assert rec.pr_number == 77 and rec.last_error == "boom"


def test_locks_all_or_nothing(store):
    track(store, make_contract(7))
    track(store, make_contract(8))
    assert store.try_acquire_locks(7, [("planner-core", "exclusive"), ("docs", "shared")]) == []
    conflicts = store.try_acquire_locks(8, [("docs", "shared"), ("planner-core", "exclusive")])
    assert [c.name for c in conflicts] == ["planner-core"]
    # nothing partial was granted to #8
    assert {(l.name, l.issue_id) for l in store.locks_held()} == {("planner-core", 7), ("docs", 7)}
    assert store.try_acquire_locks(8, [("docs", "shared")]) == []       # shared + shared coexist
    assert store.release_locks(7) == 2
    assert store.try_acquire_locks(8, [("planner-core", "exclusive")]) == []


def test_heavy_job_pool_is_a_persisted_semaphore(store):
    j1 = store.try_start_heavy_job(1, "regression", limit=1, stale_after=100)
    assert j1 is not None
    assert store.try_start_heavy_job(2, "pytest", limit=1, stale_after=100) is None
    store.finish_heavy_job(j1.job_id)
    j2 = store.try_start_heavy_job(2, "pytest", limit=1, stale_after=100)
    assert j2 is not None and j2.job_id != j1.job_id


def test_stale_heavy_job_expires(store):
    clock = store.clock
    j = store.try_start_heavy_job(1, "regression", limit=1, stale_after=100)
    assert j is not None
    clock.t += 500  # the job's process died without finishing
    assert store.active_heavy_jobs(100) == []
    assert store.try_start_heavy_job(2, "pytest", limit=1, stale_after=100) is not None


def test_approvals_and_meta(store):
    track(store, make_contract(9))
    rec = store.add_approval(9, "lead_approval", "opus", "looks right")
    assert rec.approvals[0]["kind"] == "lead_approval"
    store.set_meta("last_poll", "123")
    assert store.get_meta("last_poll") == "123"
    assert store.get_meta("nope", "dflt") == "dflt"
