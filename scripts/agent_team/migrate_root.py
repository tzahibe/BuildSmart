"""Runtime-root migration and rollback for the orchestrator (GitHub #188 directive 4).

The orchestrator's identity is not its code — it is `.agent/state/orchestrator.sqlite3`. Moving the
LaunchAgents to a different checkout moves `AGENT_TEAM_REPO_ROOT`, and every runtime directory is
gitignored, so a fresh root starts with NO memory: no issue records, no locks, no Telegram offset,
no owner pairing, no outbox, no evidence. This module makes that move verifiable and reversible.

    snapshot <src_root> <dst_root>   consistent copy of the runtime state (services must be stopped)
    verify   <src_root> <dst_root>   prove the copy is faithful, table by table
    guard    <src_root> <dst_root>   REFUSE to overwrite a destination that holds NEWER state

WAL CONSISTENCY. The state DB runs in WAL mode, so `orchestrator.sqlite3` on its own is NOT the
database — `-wal` holds committed transactions that have not been checkpointed. Copying the three
files with `cp` while anything writes is a torn copy. This uses SQLite's own online backup API,
which produces a single consistent file with the WAL already applied, and then verifies it with
`PRAGMA integrity_check` before anything is trusted.

THE ROLLBACK HAZARD this exists to prevent. Migrate, run for an hour on the new root, then roll
back: the OLD root's database is now stale by an hour. Copying it back would silently destroy
everything that happened in between. `guard` compares the newest event in each database and
refuses the copy when the destination is ahead — rollback must repoint the LaunchAgents at a root
whose state is already correct, never overwrite a newer database with an older one.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

STATE = Path(".agent/state/orchestrator.sqlite3")
#: Everything gitignored that a new root would otherwise not have. `.worktrees` is handled
#: separately (see `worktree_notes`) because git registrations hold ABSOLUTE paths.
RUNTIME_DIRS = (".agent/state", ".agent/logs", ".agent/contracts", ".agent/backups")
#: Tables whose row counts must match exactly after a migration. `remote_owner`/`remote_pairing`
#: are the owner's Telegram pairing; `meta` carries `telegram_offset`; `outbox` carries
#: notifications not yet delivered. Losing any of them is a silent, user-visible regression.
CRITICAL_TABLES = ("issues", "events", "meta", "locks", "heavy_jobs", "outbox",
                   "remote_owner", "remote_pairing", "remote_updates", "remote_commands")


def _db(root: Path) -> Path:
    return root / STATE


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def newest_event(db: Path) -> tuple[int, float]:
    """(max event id, max ts) — the comparable "how far has this database got" measure."""
    if not db.exists():
        return (-1, -1.0)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT COALESCE(MAX(id),-1), COALESCE(MAX(ts),-1) FROM events").fetchone()
        return (int(row[0]), float(row[1]))
    finally:
        con.close()


def table_counts(db: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in CRITICAL_TABLES if t in names}
    finally:
        con.close()


def meta_fingerprint(db: Path) -> dict:
    """The few meta keys whose loss is immediately visible to the owner."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        got = dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()
    return {k: got.get(k) for k in ("telegram_offset", "scheduler_paused", "last_tick")}


def snapshot(src_root: Path, dst_root: Path) -> None:
    """Consistent copy of every runtime directory. Services must be stopped."""
    src_db = _db(src_root)
    if not src_db.exists():
        sys.exit(f"ABORT: no state database at {src_db}")
    (dst_root / ".agent/state").mkdir(parents=True, exist_ok=True)

    # The ONLY safe way to copy a live WAL database: SQLite's own backup API.
    con_src = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    con_dst = sqlite3.connect(_db(dst_root))
    with con_dst:
        con_src.backup(con_dst)
    con_dst.close(); con_src.close()
    # A snapshot must not carry stale sidecars: the backup already applied the WAL.
    for suffix in ("-wal", "-shm"):
        stale = Path(str(_db(dst_root)) + suffix)
        if stale.exists():
            stale.unlink()
    chk = sqlite3.connect(_db(dst_root)).execute("PRAGMA integrity_check").fetchone()[0]
    if chk != "ok":
        sys.exit(f"ABORT: copied database failed integrity_check: {chk}")
    print(f"state      : copied + integrity ok ({_db(dst_root).stat().st_size:,} bytes)")

    for rel in RUNTIME_DIRS:
        if rel == ".agent/state":
            continue
        s, d = src_root / rel, dst_root / rel
        if not s.exists():
            continue
        d.mkdir(parents=True, exist_ok=True)
        shutil.copytree(s, d, dirs_exist_ok=True)
        print(f"{rel:<18}: copied")


def verify(src_root: Path, dst_root: Path) -> bool:
    """Prove the destination is a faithful copy — table by table, plus the meta that matters."""
    a, b = _db(src_root), _db(dst_root)
    ok = True
    ca, cb = table_counts(a), table_counts(b)
    for t in CRITICAL_TABLES:
        if t not in ca:
            continue
        same = ca.get(t) == cb.get(t)
        ok &= same
        print(f"  {t:<18} {ca.get(t):>6} -> {cb.get(t):>6}  {'ok' if same else 'MISMATCH'}")
    ma, mb = meta_fingerprint(a), meta_fingerprint(b)
    for k in ma:
        same = ma[k] == mb[k]
        ok &= same
        print(f"  meta:{k:<13} {str(ma[k])[:18]:>18} -> {str(mb[k])[:18]:<18} {'ok' if same else 'MISMATCH'}")
    chk = sqlite3.connect(f"file:{b}?mode=ro", uri=True).execute("PRAGMA integrity_check").fetchone()[0]
    print(f"  integrity_check    {chk}")
    ok &= chk == "ok"
    return ok


def guard(src_root: Path, dst_root: Path) -> bool:
    """True when copying src -> dst is SAFE. False when dst holds newer state."""
    sid, sts = newest_event(_db(src_root))
    did, dts = newest_event(_db(dst_root))
    print(f"  source      newest event id={sid} ts={sts:.0f}")
    print(f"  destination newest event id={did} ts={dts:.0f}")
    if did > sid or dts > sts:
        print("  REFUSED: the destination holds NEWER state than the source. Copying would "
              "destroy it. Repoint the services at the root that already has the correct state "
              "instead of overwriting a newer database with an older one.")
        return False
    print("  SAFE: the destination is not ahead of the source")
    return True


def worktree_notes(src_root: Path) -> list[str]:
    """Agent worktrees are registered in the SHARED .git with ABSOLUTE paths under the old root."""
    return [
        "git worktree registrations are absolute and live in the shared .git, so they survive a "
        "root change — but they keep pointing at the OLD root's .worktrees/.",
        "config.worktree_root resolves against the NEW root, which would be empty: reconciliation "
        "would see every agent worktree as missing while git still has it registered.",
        "Therefore either move each worktree (`git worktree move`) or leave the agent worktrees "
        "where they are and keep the old root on disk until they drain.",
    ]


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    cmd, src, dst = argv[1], Path(argv[2]), Path(argv[3])
    if cmd == "snapshot":
        snapshot(src, dst); return 0
    if cmd == "verify":
        return 0 if verify(src, dst) else 1
    if cmd == "guard":
        return 0 if guard(src, dst) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
