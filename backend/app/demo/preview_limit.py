"""THE CONCURRENCY LIMIT of the internal preview (Issue #246, ROOT #211).

#226 measured, alone on an idle machine, that a brain request holds one core for 30-49 s and that
the solver (scipy/HiGHS) holds the GIL, so requests do not run in parallel — they serialize, and
every other request in the same process queues behind them. Production's median went from 1.65 s
to 5.89 s beside two brain requests and to 9.29 s beside four (x3.6 to x5.6, x9.9 at worst), and
nothing bounded how many could be in flight.

So a gated preview request (`?engine=brain`, `?engine=e1_rear_band`) now has to take a slot before
it does any work, and the number of slots is ONE:

    BRAIN_PREVIEW_MAX_CONCURRENCY   optional. Default 1. Read per request. It can only be LOWERED
                                    in effect: `MEASURED_MAX_CONCURRENCY` is the highest value any
                                    measurement supports, a larger value is clamped to it (and the
                                    clamp is logged), and an empty, non-numeric or < 1 value means
                                    the default. Raising the ceiling is a code change that cites a
                                    new measurement — not an environment variable someone sets at
                                    2 a.m., the same rule `preview_gate.ALLOWED_FAMILIES` follows.

WHY REFUSE AND NOT WAIT. A brain request takes 31.6 s median and 48.9 s at worst (#226 B.1), so a
caller waiting behind another would wait 30-90 s — itself a bad answer — while holding a threadpool
thread and a connection, and a reverse proxy's own timeout would cut it with the work still running.
Refusing is instant, costs nothing, and tells the caller the truth: the preview is single-user. The
refusal is typed (`BRAIN_PREVIEW_BUSY`, HTTP 429, `Retry-After`) and reaches only an AUTHORIZED
caller: `_resolve_engine` runs first, so an unauthorized probe still gets the byte-identical unknown
engine 422 and cannot learn from this module that a preview exists.

The count is per PROCESS. That is the right unit: the contention being bounded is for one process's
GIL, which is also why the preview must be served by a process of its own
(`docs/runbooks/brain-preview.md`) — with `--workers N` there would be N independent counters.
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Iterator

LIMIT_ENV = "BRAIN_PREVIEW_MAX_CONCURRENCY"

#: the committed default: one gated preview request at a time per process
DEFAULT_MAX_CONCURRENCY = 1

#: The highest limit ANY measurement supports. #226 B.3/B.4: at 2 concurrent brain requests
#: production's median is x3.6 and its worst case x6.7; at 4 it is x5.6 and x9.9. Not even one
#: measured value above 1 is acceptable, so the ceiling is the default.
MEASURED_MAX_CONCURRENCY = 1

#: seconds a refused caller is told to wait. A brain request takes 31.6 s median (#226 B.1), so a
#: retry sooner than this is very likely to be refused again.
RETRY_AFTER_S = 30

BUSY_CODE = "BRAIN_PREVIEW_BUSY"
BUSY_MESSAGE = ("תצוגת המנוע הניסיוני מטפלת כרגע בבקשה אחרת. אפשר לנסות שוב בעוד חצי דקה.")

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_in_flight = 0


class PreviewBusy(Exception):
    """Every slot is taken. Carries the limit so the typed refusal can say what it is."""

    def __init__(self, limit: int, in_flight: int) -> None:
        super().__init__(f"{in_flight} of {limit} preview slot(s) in use")
        self.limit = limit
        self.in_flight = in_flight


def max_concurrency() -> int:
    """The limit in force right now: the environment's value, clamped to what is measured."""
    raw = (os.environ.get(LIMIT_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENCY
    try:
        asked = int(raw)
    except ValueError:
        _log.warning("%s=%r is not an integer; using the default %d",
                     LIMIT_ENV, raw, DEFAULT_MAX_CONCURRENCY)
        return DEFAULT_MAX_CONCURRENCY
    if asked < 1:
        _log.warning("%s=%d is below 1; using the default %d",
                     LIMIT_ENV, asked, DEFAULT_MAX_CONCURRENCY)
        return DEFAULT_MAX_CONCURRENCY
    if asked > MEASURED_MAX_CONCURRENCY:
        _log.warning("%s=%d is above the highest measured-safe limit %d (#226); using %d",
                     LIMIT_ENV, asked, MEASURED_MAX_CONCURRENCY, MEASURED_MAX_CONCURRENCY)
        return MEASURED_MAX_CONCURRENCY
    return asked


def in_flight() -> int:
    """How many gated preview requests hold a slot right now."""
    with _lock:
        return _in_flight


def acquire() -> None:
    """Take a slot or raise `PreviewBusy` — never blocks. Pair with `release()`.

    The streaming route cannot use `slot()`: its slot must outlive the request frame, because the
    worker thread keeps solving after a client disconnects, and the slot is released by that
    thread and not by whoever is listening.
    """
    global _in_flight
    limit = max_concurrency()
    with _lock:
        if _in_flight >= limit:
            busy = PreviewBusy(limit, _in_flight)
        else:
            _in_flight += 1
            return
    _log.warning("preview refused: %s (%s)", BUSY_CODE, busy)
    raise busy


def release() -> None:
    global _in_flight
    with _lock:
        _in_flight = max(0, _in_flight - 1)


@contextmanager
def slot() -> Iterator[None]:
    """A slot for the duration of the block."""
    acquire()
    try:
        yield
    finally:
        release()
