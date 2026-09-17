"""Crash-safe orchestration state in SQLite (WAL). Local process memory is never the truth.

Three concerns share one file so a single transaction can move an issue AND its locks AND its
heavy-job slot together:

- `issues`     one row per tracked Issue (state, branch, worktree, attempt, PR, heartbeat, ...)
- `locks`      domain locks held per issue
- `heavy_jobs` the heavy validation pool (separate from agent slots)
- `events`     append-only audit trail

Compare-and-set transitions: `transition()` updates `WHERE state IN (<allowed sources>)` and treats
rowcount 0 as a conflict, so a stale in-memory view can never overwrite a newer state.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Iterator

from agent_team import state_machine as sm

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    issue_id         INTEGER PRIMARY KEY,
    title            TEXT NOT NULL DEFAULT '',
    state            TEXT NOT NULL,
    risk             TEXT NOT NULL DEFAULT 'MEDIUM',
    resource_class   TEXT NOT NULL DEFAULT 'MEDIUM',
    domains          TEXT NOT NULL DEFAULT '[]',
    assigned_agent   TEXT,
    agent_pid        INTEGER,
    session_id       TEXT,
    branch           TEXT,
    worktree         TEXT,
    domain_locks     TEXT NOT NULL DEFAULT '[]',
    attempt_number   INTEGER NOT NULL DEFAULT 0,
    pr_number        INTEGER,
    pr_url           TEXT,
    started_at       REAL,
    heartbeat_at     REAL,
    last_error       TEXT,
    failure_class    TEXT,
    dependencies     TEXT NOT NULL DEFAULT '[]',
    validated_commit TEXT,
    base_sha         TEXT,
    review_verdict   TEXT,
    approvals        TEXT NOT NULL DEFAULT '[]',
    contract         TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS locks (
    name         TEXT NOT NULL,
    mode         TEXT NOT NULL,
    issue_id     INTEGER NOT NULL,
    acquired_at  REAL NOT NULL,
    PRIMARY KEY (name, issue_id)
);
CREATE TABLE IF NOT EXISTS heavy_jobs (
    job_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id     INTEGER,
    kind         TEXT NOT NULL,
    pid          INTEGER,
    started_at   REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    finished_at  REAL,
    status       TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    issue_id  INTEGER,
    kind      TEXT NOT NULL,
    payload   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_issue ON events(issue_id, id);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Owner notifications (Telegram). dedup_key is e.g. "pr:57:READY_FOR_OWNER:<sha>": one row per
-- validated SHA, so scheduler ticks and restarts can never resend; a new SHA is a new row.
CREATE TABLE IF NOT EXISTS outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,
    dedup_key       TEXT NOT NULL UNIQUE,
    issue_id        INTEGER,
    text            TEXT NOT NULL,
    buttons         TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      REAL NOT NULL,
    sent_at         REAL,
    message_id      INTEGER
);
-- Remote control plane (Telegram): the single paired owner, one-time pairing codes, processed
-- update ids and executed command ids (replay protection), Issue drafts and per-chat context.
CREATE TABLE IF NOT EXISTS remote_owner (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    telegram_user_id INTEGER NOT NULL,
    chat_id          INTEGER NOT NULL,
    paired_at        REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_pairing (
    code        TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_updates (
    update_id   INTEGER PRIMARY KEY,
    received_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_commands (
    command_id  TEXT PRIMARY KEY,
    action      TEXT NOT NULL,
    entity      TEXT,
    source      TEXT NOT NULL,
    owner_id    INTEGER,
    ts          REAL NOT NULL,
    result      TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS remote_drafts (
    draft_id     TEXT PRIMARY KEY,
    chat_id      INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft',
    title        TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    problems     TEXT NOT NULL DEFAULT '[]',
    issue_number INTEGER,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_context (
    chat_id          INTEGER PRIMARY KEY,
    current_draft_id TEXT,
    current_pr       INTEGER,
    pending_merge    TEXT,
    updated_at       REAL NOT NULL
);
"""

_JSON_FIELDS = ("domains", "domain_locks", "dependencies", "approvals")


class TransitionConflict(RuntimeError):
    """The row was not in one of the expected source states (someone else moved it)."""


@dataclass
class IssueRecord:
    issue_id: int
    state: str
    title: str = ""
    risk: str = "MEDIUM"
    resource_class: str = "MEDIUM"
    domains: list[str] = field(default_factory=list)
    assigned_agent: str | None = None
    agent_pid: int | None = None
    session_id: str | None = None
    branch: str | None = None
    worktree: str | None = None
    domain_locks: list[dict] = field(default_factory=list)
    attempt_number: int = 0
    pr_number: int | None = None
    pr_url: str | None = None
    started_at: float | None = None
    heartbeat_at: float | None = None
    last_error: str | None = None
    failure_class: str | None = None
    dependencies: list[int] = field(default_factory=list)
    validated_commit: str | None = None
    base_sha: str | None = None
    review_verdict: str | None = None
    approvals: list[dict] = field(default_factory=list)
    contract: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "IssueRecord":
        d = {k: row[k] for k in row.keys()}
        for k in _JSON_FIELDS:
            d[k] = json.loads(d[k] or "[]")
        return cls(**{f.name: d[f.name] for f in fields(cls)})

    def contract_dict(self) -> dict:
        return json.loads(self.contract) if self.contract else {}


@dataclass(frozen=True)
class LockRow:
    name: str
    mode: str
    issue_id: int
    acquired_at: float


@dataclass(frozen=True)
class HeavyJob:
    job_id: int
    issue_id: int | None
    kind: str
    pid: int | None
    started_at: float
    heartbeat_at: float
    finished_at: float | None
    status: str


class StateStore:
    def __init__(self, path: Path | str, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        if str(self.path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- transactions -------------------------------------------------------------------------
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """BEGIN IMMEDIATE so compare-and-set sequences are serialized against other writers."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # -- issues -------------------------------------------------------------------------------
    def get(self, issue_id: int) -> IssueRecord | None:
        row = self._conn.execute("SELECT * FROM issues WHERE issue_id=?", (issue_id,)).fetchone()
        return IssueRecord.from_row(row) if row else None

    def list(self, states: tuple[str, ...] | None = None) -> list[IssueRecord]:
        if states:
            q = f"SELECT * FROM issues WHERE state IN ({','.join('?' * len(states))}) ORDER BY issue_id"
            rows = self._conn.execute(q, states).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM issues ORDER BY issue_id").fetchall()
        return [IssueRecord.from_row(r) for r in rows]

    def track(self, issue_id: int, *, title: str, risk: str, resource_class: str, domains: list[str],
              dependencies: list[int], contract: dict | None, state: str = sm.QUEUED) -> IssueRecord:
        """Insert if unknown; if known, refresh the contract-derived metadata but never the state."""
        now = self.clock()
        with self.tx() as c:
            existing = c.execute("SELECT issue_id FROM issues WHERE issue_id=?", (issue_id,)).fetchone()
            if existing:
                c.execute(
                    "UPDATE issues SET title=?, risk=?, resource_class=?, domains=?, dependencies=?, contract=?, updated_at=? WHERE issue_id=?",
                    (title, risk, resource_class, json.dumps(domains), json.dumps(dependencies),
                     json.dumps(contract) if contract else None, now, issue_id))
            else:
                c.execute(
                    "INSERT INTO issues (issue_id, title, state, risk, resource_class, domains, dependencies, contract, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (issue_id, title, state, risk, resource_class, json.dumps(domains), json.dumps(dependencies),
                     json.dumps(contract) if contract else None, now, now))
                self._event(c, issue_id, "tracked", {"state": state, "risk": risk, "resource_class": resource_class})
        rec = self.get(issue_id)
        assert rec is not None
        return rec

    def transition(self, issue_id: int, to_state: str, *, allowed_from: tuple[str, ...] | None = None,
                   note: str | None = None, **fields_to_set: Any) -> IssueRecord:
        """Atomic compare-and-set state change. `allowed_from` defaults to every legal source."""
        now = self.clock()
        sets, params = ["state=?", "updated_at=?"], [to_state, now]
        for k, v in fields_to_set.items():
            if k in _JSON_FIELDS:
                v = json.dumps(v)
            sets.append(f"{k}=?")
            params.append(v)
        with self.tx() as c:
            row = c.execute("SELECT state FROM issues WHERE issue_id=?", (issue_id,)).fetchone()
            if row is None:
                raise KeyError(f"issue #{issue_id} is not tracked")
            if allowed_from is None:
                # No expectation given: the transition must be legal from the state on disk.
                sm.check_transition(row["state"], to_state)
                allowed_from = (row["state"],)
            else:
                for src in allowed_from:
                    sm.check_transition(src, to_state)
            cur = c.execute(
                f"UPDATE issues SET {', '.join(sets)} WHERE issue_id=? AND state IN ({','.join('?' * len(allowed_from))})",
                (*params, issue_id, *allowed_from))
            if cur.rowcount != 1:
                row = c.execute("SELECT state FROM issues WHERE issue_id=?", (issue_id,)).fetchone()
                current = row["state"] if row else None
                raise TransitionConflict(
                    f"issue #{issue_id}: cannot move to {to_state} from {current!r} (expected one of {allowed_from})")
            payload = {"to": to_state, "from_any_of": list(allowed_from)}
            if note:
                payload["note"] = note
            self._event(c, issue_id, "transition", payload)
        rec = self.get(issue_id)
        assert rec is not None
        return rec

    def update(self, issue_id: int, **fields_to_set: Any) -> IssueRecord:
        """Set non-state fields (heartbeat, pr number, error, ...)."""
        if "state" in fields_to_set:
            raise ValueError("use transition() to change state")
        sets, params = ["updated_at=?"], [self.clock()]
        for k, v in fields_to_set.items():
            if k in _JSON_FIELDS:
                v = json.dumps(v)
            sets.append(f"{k}=?")
            params.append(v)
        with self.tx() as c:
            c.execute(f"UPDATE issues SET {', '.join(sets)} WHERE issue_id=?", (*params, issue_id))
        rec = self.get(issue_id)
        assert rec is not None
        return rec

    def heartbeat(self, issue_id: int) -> None:
        with self.tx() as c:
            c.execute("UPDATE issues SET heartbeat_at=? WHERE issue_id=?", (self.clock(), issue_id))

    def add_approval(self, issue_id: int, kind: str, by: str, note: str = "") -> IssueRecord:
        rec = self.get(issue_id)
        if rec is None:
            raise KeyError(issue_id)
        approvals = list(rec.approvals) + [{"kind": kind, "by": by, "note": note, "ts": self.clock()}]
        with self.tx() as c:
            c.execute("UPDATE issues SET approvals=?, updated_at=? WHERE issue_id=?",
                      (json.dumps(approvals), self.clock(), issue_id))
            self._event(c, issue_id, "approval", {"kind": kind, "by": by, "note": note})
        return self.get(issue_id)  # type: ignore[return-value]

    # -- locks --------------------------------------------------------------------------------
    def locks_held(self) -> list[LockRow]:
        rows = self._conn.execute("SELECT * FROM locks ORDER BY name, issue_id").fetchall()
        return [LockRow(r["name"], r["mode"], r["issue_id"], r["acquired_at"]) for r in rows]

    def lock_conflicts(self, name: str, mode: str, issue_id: int, conn: sqlite3.Connection | None = None) -> list[LockRow]:
        c = conn or self._conn
        rows = c.execute("SELECT * FROM locks WHERE name=? AND issue_id<>?", (name, issue_id)).fetchall()
        held = [LockRow(r["name"], r["mode"], r["issue_id"], r["acquired_at"]) for r in rows]
        if mode == "exclusive":
            return held
        return [h for h in held if h.mode == "exclusive"]

    def try_acquire_locks(self, issue_id: int, requirements: list[tuple[str, str]]) -> list[LockRow]:
        """All-or-nothing. Returns the conflicting rows (empty list == acquired)."""
        now = self.clock()
        with self.tx() as c:
            conflicts: list[LockRow] = []
            for name, mode in requirements:
                conflicts.extend(self.lock_conflicts(name, mode, issue_id, c))
            if conflicts:
                return conflicts
            for name, mode in requirements:
                c.execute("INSERT OR REPLACE INTO locks (name, mode, issue_id, acquired_at) VALUES (?,?,?,?)",
                          (name, mode, issue_id, now))
            c.execute("UPDATE issues SET domain_locks=?, updated_at=? WHERE issue_id=?",
                      (json.dumps([{"name": n, "mode": m} for n, m in requirements]), now, issue_id))
            self._event(c, issue_id, "locks_acquired", {"locks": requirements})
        return []

    def release_locks(self, issue_id: int, reason: str = "released") -> int:
        with self.tx() as c:
            cur = c.execute("DELETE FROM locks WHERE issue_id=?", (issue_id,))
            if cur.rowcount:
                self._event(c, issue_id, "locks_released", {"count": cur.rowcount, "reason": reason})
            c.execute("UPDATE issues SET domain_locks='[]' WHERE issue_id=?", (issue_id,))
        return cur.rowcount

    # -- heavy jobs ---------------------------------------------------------------------------
    def active_heavy_jobs(self, stale_after: float) -> list[HeavyJob]:
        cutoff = self.clock() - stale_after
        rows = self._conn.execute(
            "SELECT * FROM heavy_jobs WHERE status='running' AND heartbeat_at>=? ORDER BY job_id", (cutoff,)).fetchall()
        return [HeavyJob(**{k: r[k] for k in r.keys()}) for r in rows]

    def try_start_heavy_job(self, issue_id: int | None, kind: str, limit: int, stale_after: float, pid: int | None = None) -> HeavyJob | None:
        now = self.clock()
        with self.tx() as c:
            # Expire stale rows first so a crashed job never pins the pool forever.
            c.execute("UPDATE heavy_jobs SET status='stale', finished_at=? WHERE status='running' AND heartbeat_at<?",
                      (now, now - stale_after))
            n = c.execute("SELECT COUNT(*) FROM heavy_jobs WHERE status='running'").fetchone()[0]
            if n >= limit:
                return None
            cur = c.execute("INSERT INTO heavy_jobs (issue_id, kind, pid, started_at, heartbeat_at) VALUES (?,?,?,?,?)",
                            (issue_id, kind, pid, now, now))
            self._event(c, issue_id, "heavy_job_started", {"kind": kind, "job_id": cur.lastrowid})
            row = c.execute("SELECT * FROM heavy_jobs WHERE job_id=?", (cur.lastrowid,)).fetchone()
        return HeavyJob(**{k: row[k] for k in row.keys()})

    def heartbeat_heavy_job(self, job_id: int) -> None:
        with self.tx() as c:
            c.execute("UPDATE heavy_jobs SET heartbeat_at=? WHERE job_id=?", (self.clock(), job_id))

    def finish_heavy_job(self, job_id: int, status: str = "done") -> None:
        with self.tx() as c:
            c.execute("UPDATE heavy_jobs SET status=?, finished_at=? WHERE job_id=?", (status, self.clock(), job_id))
            row = c.execute("SELECT issue_id, kind FROM heavy_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row:
                self._event(c, row["issue_id"], "heavy_job_finished", {"kind": row["kind"], "job_id": job_id, "status": status})

    # -- outbox (owner notifications) ---------------------------------------------------------
    def enqueue_notification(self, kind: str, dedup_key: str, issue_id: int | None, text: str, buttons: list | None = None) -> bool:
        """Returns True when a new row was created; False when the dedup key already exists."""
        with self.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO outbox (kind, dedup_key, issue_id, text, buttons, created_at) VALUES (?,?,?,?,?,?)",
                (kind, dedup_key, issue_id, text, json.dumps(buttons or []), self.clock()))
            created = cur.rowcount == 1
            if created:
                self._event(c, issue_id, "notification_queued", {"kind": kind, "dedup_key": dedup_key})
        return created

    def due_notifications(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM outbox WHERE status='pending' AND next_attempt_at<=? ORDER BY id LIMIT ?", (self.clock(), limit)).fetchall()
        return [self._outbox_row(r) for r in rows]

    def notification(self, dedup_key: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM outbox WHERE dedup_key=?", (dedup_key,)).fetchone()
        return self._outbox_row(row) if row else None

    def notifications_for_issue(self, issue_id: int) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM outbox WHERE issue_id=? ORDER BY id", (issue_id,)).fetchall()
        return [self._outbox_row(r) for r in rows]

    def mark_notification(self, row_id: int, *, sent: bool, error: str = "", message_id: int | None = None,
                          max_attempts: int = 3, backoff_seconds: float = 120.0) -> str:
        """Returns the resulting status: sent | pending (will retry) | failed (attempts exhausted)."""
        now = self.clock()
        with self.tx() as c:
            row = c.execute("SELECT attempts, issue_id, dedup_key FROM outbox WHERE id=?", (row_id,)).fetchone()
            if row is None:
                return "missing"
            attempts = row["attempts"] + 1
            if sent:
                c.execute("UPDATE outbox SET status='sent', attempts=?, sent_at=?, message_id=?, last_error=NULL WHERE id=?",
                          (attempts, now, message_id, row_id))
                self._event(c, row["issue_id"], "notification_sent", {"dedup_key": row["dedup_key"], "attempts": attempts})
                return "sent"
            status = "failed" if attempts >= max_attempts else "pending"
            c.execute("UPDATE outbox SET status=?, attempts=?, next_attempt_at=?, last_error=? WHERE id=?",
                      (status, attempts, now + backoff_seconds * attempts, error[:500], row_id))
            self._event(c, row["issue_id"], "notification_failure", {"dedup_key": row["dedup_key"], "attempts": attempts,
                                                                       "status": status, "error": error[:200]})
            return status

    @staticmethod
    def _outbox_row(r: sqlite3.Row) -> dict:
        d = {k: r[k] for k in r.keys()}
        d["buttons"] = json.loads(d.get("buttons") or "[]")
        return d

    # -- remote control: owner / pairing / replay protection ----------------------------------
    def owner(self) -> dict | None:
        row = self._conn.execute("SELECT * FROM remote_owner WHERE id=1").fetchone()
        return {k: row[k] for k in row.keys()} if row else None

    def set_owner(self, telegram_user_id: int, chat_id: int) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO remote_owner (id, telegram_user_id, chat_id, paired_at) VALUES (1,?,?,?)",
                      (telegram_user_id, chat_id, self.clock()))
            self._event(c, None, "owner_paired", {"telegram_user_id": telegram_user_id, "chat_id": chat_id})

    def clear_owner(self) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM remote_owner")
            self._event(c, None, "owner_unpaired", {})

    def create_pairing_code(self, code: str, ttl_seconds: float) -> None:
        now = self.clock()
        with self.tx() as c:
            c.execute("DELETE FROM remote_pairing")   # one active code at a time
            c.execute("INSERT INTO remote_pairing (code, created_at, expires_at) VALUES (?,?,?)", (code, now, now + ttl_seconds))
            self._event(c, None, "pairing_code_created", {"expires_in": ttl_seconds})

    def consume_pairing_code(self, code: str) -> bool:
        """One-time use: returns True and deletes the code when it matches and has not expired."""
        with self.tx() as c:
            row = c.execute("SELECT expires_at FROM remote_pairing WHERE code=?", (code,)).fetchone()
            if row is None:
                return False
            c.execute("DELETE FROM remote_pairing WHERE code=?", (code,))
            if row["expires_at"] < self.clock():
                self._event(c, None, "pairing_expired", {})
                return False
        return True

    def mark_update(self, update_id: int) -> bool:
        """Returns True if the Telegram update is new (first delivery)."""
        with self.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO remote_updates (update_id, received_at) VALUES (?,?)", (update_id, self.clock()))
            return cur.rowcount == 1

    def command_executed(self, command_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM remote_commands WHERE command_id=?", (command_id,)).fetchone()
        return {k: row[k] for k in row.keys()} if row else None

    def record_command(self, command_id: str, action: str, entity: str | None, source: str, owner_id: int | None,
                       result: str, payload: dict | None = None) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO remote_commands (command_id, action, entity, source, owner_id, ts, result, payload) VALUES (?,?,?,?,?,?,?,?)",
                      (command_id, action, entity, source, owner_id, self.clock(), result, json.dumps(payload or {}, default=str)))
            issue_id = None
            if entity and entity.startswith("issue:"):
                issue_id = int(entity.split(":", 1)[1])
            self._event(c, issue_id, "OWNER_COMMAND", {"source": source, "action": action, "entity": entity, "owner_id": owner_id,
                                                        "command_id": command_id, "result": result, **(payload or {})})

    # -- remote control: drafts and per-chat context ------------------------------------------
    def save_draft(self, draft_id: str, chat_id: int, title: str, body: str, problems: list[str], status: str = "draft") -> None:
        now = self.clock()
        with self.tx() as c:
            c.execute("INSERT INTO remote_drafts (draft_id, chat_id, status, title, body, problems, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)"
                      " ON CONFLICT(draft_id) DO UPDATE SET status=excluded.status, title=excluded.title, body=excluded.body,"
                      " problems=excluded.problems, updated_at=excluded.updated_at",
                      (draft_id, chat_id, status, title, body, json.dumps(problems), now, now))

    def draft(self, draft_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM remote_drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if not row:
            return None
        d = {k: row[k] for k in row.keys()}
        d["problems"] = json.loads(d["problems"] or "[]")
        return d

    def finish_draft(self, draft_id: str, status: str, issue_number: int | None = None) -> None:
        with self.tx() as c:
            c.execute("UPDATE remote_drafts SET status=?, issue_number=?, updated_at=? WHERE draft_id=?",
                      (status, issue_number, self.clock(), draft_id))

    def context(self, chat_id: int) -> dict:
        row = self._conn.execute("SELECT * FROM remote_context WHERE chat_id=?", (chat_id,)).fetchone()
        if not row:
            return {"chat_id": chat_id, "current_draft_id": None, "current_pr": None, "pending_merge": None}
        d = {k: row[k] for k in row.keys()}
        d["pending_merge"] = json.loads(d["pending_merge"]) if d.get("pending_merge") else None
        return d

    def set_context(self, chat_id: int, **fields_to_set: Any) -> dict:
        cur = self.context(chat_id)
        cur.update(fields_to_set)
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO remote_context (chat_id, current_draft_id, current_pr, pending_merge, updated_at) VALUES (?,?,?,?,?)",
                      (chat_id, cur.get("current_draft_id"), cur.get("current_pr"),
                       json.dumps(cur["pending_merge"]) if cur.get("pending_merge") else None, self.clock()))
        return self.context(chat_id)

    # -- events / meta ------------------------------------------------------------------------
    def _event(self, c: sqlite3.Connection, issue_id: int | None, kind: str, payload: dict) -> None:
        c.execute("INSERT INTO events (ts, issue_id, kind, payload) VALUES (?,?,?,?)",
                  (self.clock(), issue_id, kind, json.dumps(payload, default=str)))

    def record_event(self, issue_id: int | None, kind: str, payload: dict | None = None) -> None:
        with self.tx() as c:
            self._event(c, issue_id, kind, payload or {})

    def events(self, issue_id: int | None = None, limit: int = 200) -> list[dict]:
        if issue_id is None:
            rows = self._conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM events WHERE issue_id=? ORDER BY id DESC LIMIT ?", (issue_id, limit)).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "issue_id": r["issue_id"], "kind": r["kind"], "payload": json.loads(r["payload"])}
                for r in reversed(rows)]

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
