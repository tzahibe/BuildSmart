"""Runtime-root migration and rollback (GitHub #188 directive 4).

The property that matters most is the last one: a rollback must never overwrite a database that
has moved on. Everything else is "did the copy carry the orchestrator's memory"; that one is "can
this procedure destroy work".
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from agent_team import migrate_root as mr


def _make_root(tmp_path, name, *, events=3, offset="12345"):
    root = tmp_path / name
    (root / ".agent/state").mkdir(parents=True)
    (root / ".agent/logs").mkdir(parents=True)
    db = root / mr.STATE
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE issues (issue_id INTEGER PRIMARY KEY, state TEXT);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, issue_id INTEGER,
                             kind TEXT, payload TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE locks (name TEXT); CREATE TABLE heavy_jobs (id TEXT);
        CREATE TABLE outbox (id TEXT); CREATE TABLE remote_owner (chat_id TEXT);
        CREATE TABLE remote_pairing (code TEXT); CREATE TABLE remote_updates (uid TEXT);
        CREATE TABLE remote_commands (cid TEXT);
    """)
    con.execute("INSERT INTO issues VALUES (1,'DONE')")
    con.execute("INSERT INTO meta VALUES ('telegram_offset',?)", (offset,))
    con.execute("INSERT INTO meta VALUES ('scheduler_paused','0')")
    con.execute("INSERT INTO meta VALUES ('last_tick','1.0')")
    con.execute("INSERT INTO remote_owner VALUES ('chat-1')")
    for i in range(events):
        con.execute("INSERT INTO events (ts,issue_id,kind,payload) VALUES (?,1,'x','{}')",
                    (1000.0 + i,))
    con.commit(); con.close()
    (root / ".agent/logs/run.json").write_text("{}")
    return root


def test_snapshot_carries_the_orchestrator_memory(tmp_path):
    src = _make_root(tmp_path, "old")
    dst = tmp_path / "new"
    mr.snapshot(src, dst)
    assert mr.verify(src, dst)
    assert (dst / ".agent/logs/run.json").exists()        # evidence travels too


def test_snapshot_leaves_no_stale_wal_sidecars(tmp_path):
    """A WAL sidecar copied beside an already-checkpointed database is how a torn copy looks
    healthy and then loses committed transactions."""
    src = _make_root(tmp_path, "old")
    dst = tmp_path / "new"
    mr.snapshot(src, dst)
    assert not (dst / ".agent/state/orchestrator.sqlite3-wal").exists()
    assert not (dst / ".agent/state/orchestrator.sqlite3-shm").exists()


def test_the_telegram_offset_and_pairing_survive(tmp_path):
    """Losing either is silently user-visible: the bot re-processes or skips updates, and the
    owner has to pair again."""
    src = _make_root(tmp_path, "old", offset="28915689")
    dst = tmp_path / "new"
    mr.snapshot(src, dst)
    assert mr.meta_fingerprint(mr._db(dst))["telegram_offset"] == "28915689"
    con = sqlite3.connect(mr._db(dst))
    assert con.execute("SELECT COUNT(*) FROM remote_owner").fetchone()[0] == 1


def test_verify_fails_when_a_critical_table_was_not_carried(tmp_path):
    src = _make_root(tmp_path, "old")
    dst = tmp_path / "new"
    mr.snapshot(src, dst)
    sqlite3.connect(mr._db(dst)).execute("DELETE FROM remote_owner").connection.commit()
    assert not mr.verify(src, dst)


# ----------------------------------------------------------------- the one that prevents data loss

def test_guard_allows_the_copy_while_the_destination_is_not_ahead(tmp_path):
    src = _make_root(tmp_path, "old")
    dst = tmp_path / "new"
    mr.snapshot(src, dst)
    assert mr.guard(src, dst) is True


def test_guard_REFUSES_to_overwrite_newer_state(tmp_path):
    """Migrate, let the new root work, then attempt a naive rollback. The stale database must not
    be copied over the one that moved on."""
    old = _make_root(tmp_path, "old")
    new = tmp_path / "new"
    mr.snapshot(old, new)
    con = sqlite3.connect(mr._db(new))                     # the new root does an hour of work
    con.execute("INSERT INTO events (ts,issue_id,kind,payload) VALUES (?,9,'after','{}')",
                (time.time(),))
    con.commit(); con.close()

    assert mr.guard(old, new) is False                     # old -> new is REFUSED
    assert mr.guard(new, old) is True                      # new -> old is still fine


def test_guard_treats_a_missing_destination_as_safe(tmp_path):
    src = _make_root(tmp_path, "old")
    assert mr.guard(src, tmp_path / "nonexistent") is True


def test_worktree_hazard_is_stated_not_silently_handled(tmp_path):
    notes = mr.worktree_notes(_make_root(tmp_path, "old"))
    assert any("absolute" in n for n in notes)
    assert any("worktree_root" in n for n in notes)
