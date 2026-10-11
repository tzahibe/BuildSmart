"""Scoped wakefulness: keep the Mac awake ONLY while approved agent work is running.

The problem this solves (GitHub #188 §3.3): both LaunchAgents stop while the machine sleeps, and
sleep is prevented only while the display is on. That costs throughput whenever the owner is away
— which is exactly when the orchestrator is supposed to be earning its keep.

What this is NOT: a global power setting. `pmset` is never invoked, no system preference is
written, and nothing here outlives the orchestrator process. The assertion is held by a child
`caffeinate` process and is released the moment the last agent thread finishes.

    with manager.assertion():      # refcounted; the first holder spawns, the last releases
        ...run an agent...

Three properties the tests pin:

  REFCOUNTED   N overlapping agent runs hold ONE `caffeinate`, released when the last one exits.
  SCOPED       no agents running -> no process -> the machine sleeps normally when the owner
               closes the lid, exactly as it does today.
  ORPHAN-SAFE  `caffeinate -w <our pid>` makes the kernel's own watcher exit when the orchestrator
               dies, so a crash cannot leave the machine awake forever. `release()` is still
               called on the normal path; `-w` is the backstop, not the mechanism.
"""
from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import threading

log = logging.getLogger("agent_team.power")

#: `-i` prevents idle SYSTEM sleep. Deliberately not `-d` (display) — the orchestrator has no
#: reason to keep a screen lit — and deliberately not `-s`, which only applies on AC power and
#: would silently do nothing on battery.
_CAFFEINATE_FLAGS = ("-i",)


class PowerAssertion:
    """Refcounted `caffeinate` lifetime. Thread-safe; every method is a no-op when disabled."""

    def __init__(self, enabled: bool = True, *, binary: str | None = None,
                 owner_pid: int | None = None) -> None:
        self.enabled = enabled
        self._binary = binary or shutil.which("caffeinate") or "/usr/bin/caffeinate"
        self._owner_pid = owner_pid if owner_pid is not None else os.getpid()
        self._lock = threading.Lock()
        self._holders = 0
        self._proc: subprocess.Popen | None = None

    # -- state, for status output and tests ----------------------------------------------
    @property
    def holders(self) -> int:
        with self._lock:
            return self._holders

    @property
    def active(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def describe(self) -> str:
        if not self.enabled:
            return "caffeinate: disabled"
        return (f"caffeinate: {'holding' if self.active else 'idle'} "
                f"({self.holders} agent run(s))")

    # -- lifecycle -----------------------------------------------------------------------
    def acquire(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._holders += 1
            if self._holders > 1 or (self._proc is not None and self._proc.poll() is None):
                return
            self._proc = self._spawn()

    def release(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._holders == 0:
                return                       # unbalanced release: never go negative
            self._holders -= 1
            if self._holders > 0:
                return
            self._terminate_locked()

    @contextlib.contextmanager
    def assertion(self):
        self.acquire()
        try:
            yield self
        finally:
            self.release()

    def shutdown(self) -> None:
        """Drop the assertion whatever the refcount says — for the drain path and tests."""
        with self._lock:
            self._holders = 0
            self._terminate_locked()

    # -- internals -----------------------------------------------------------------------
    def _spawn(self) -> subprocess.Popen | None:
        # `-w <pid>` ties the child's life to ours: if this process is killed -9 and never runs
        # `release()`, caffeinate still exits when the kernel reaps us. Without it a crash would
        # leave the machine awake until the next reboot.
        cmd = [self._binary, *_CAFFEINATE_FLAGS, "-w", str(self._owner_pid)]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
        except (OSError, ValueError) as exc:
            # Never fatal: a machine without caffeinate still runs agents, it just sleeps.
            log.warning("caffeinate unavailable (%s); agent work will not prevent sleep", exc)
            self.enabled = False
            return None
        log.info("power: holding idle-sleep assertion (pid %s) while agent work runs", proc.pid)
        return proc

    def _terminate_locked(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:       # pragma: no cover - caffeinate ignores SIGTERM?
            proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        log.info("power: released idle-sleep assertion")
