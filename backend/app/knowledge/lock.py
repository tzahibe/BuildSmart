"""Single-writer lock for index refresh — multiple agents may run concurrently against the same
shared SQLite-backed index; only one may write (index/clear) at a time. Readers (search/context/
stats) never need this lock — `sqlite_store.py` enables WAL mode specifically so a reader always
sees the last committed snapshot even while a writer is active, per SQLite's own concurrency model
for exactly this "one writer, many readers" case.

Uses `flock` (POSIX advisory file locking), not a PID file: `flock` is held against an open file
descriptor and is released automatically by the OS the moment the holding process exits or
crashes — there is no "stale lock" state to detect or recover from by construction, unlike a
PID-file scheme where a crashed writer can leave a lock nobody cleans up.
"""

from __future__ import annotations

import contextlib
import errno
import os
import time


class IndexLockTimeout(RuntimeError):
    """The lock could not be acquired within the bounded wait. Callers must treat this as "defer
    the write, read the last known-good index instead" (routine refresh) or "refuse the
    destructive operation" (clear) — never as license to force a rebuild while another writer
    might be mid-transaction."""


class IndexLock:
    def __init__(self, db_path: str):
        self.lock_path = db_path + ".lock"
        self._fd: int | None = None

    def _try_acquire_once(self) -> bool:
        import fcntl

        os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
        # Diagnostics only — who holds the lock, for a human reading the file. Never read back to
        # decide staleness; flock's own OS-level release on process exit is what makes this safe.
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        return True

    def acquire(self, *, timeout_s: float = 30.0, poll_interval_s: float = 0.2) -> bool:
        """Polls up to `timeout_s`. Returns True once acquired, False if the deadline passed."""
        deadline = time.monotonic() + timeout_s
        while True:
            if self._try_acquire_once():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval_s)

    def release(self) -> None:
        if self._fd is not None:
            import fcntl

            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


@contextlib.contextmanager
def acquire_index_lock(db_path: str, *, timeout_s: float = 30.0):
    """Yields True if the lock was acquired (caller proceeds with the write) or False if the
    bounded wait timed out (caller must defer/refuse, never force)."""
    lock = IndexLock(db_path)
    acquired = lock.acquire(timeout_s=timeout_s)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
