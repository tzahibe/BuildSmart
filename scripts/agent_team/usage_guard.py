"""Subscription usage guard: never let agents (or the Team Lead) run the session into the wall.

`claude -p /usage` answers in headless mode at zero cost with the real plan usage:

    Current session: 18% used · resets Sep 17 at 11:50pm (Asia/Jerusalem)
    Current week (all models): 71% used · resets Sep 20 at 12:59am (Asia/Jerusalem)

The orchestrator probes it every tick. At `pause_at_percent` (session OR week) it pauses itself
(reason `usage_limit`), tells the owner, lets running agents finish their current run, and
requeues any run that dies on a rate limit without consuming a repair attempt. When the window
resets or usage drops below `resume_below_percent`, an automatic pause is lifted automatically —
an owner's manual pause is never lifted by this guard.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

_LINE = re.compile(r"Current (session|week \(all models\)|week \([^)]+\)): (\d+)% used(?: · resets (.+?)(?: \((.+?)\))?)?$", re.M)
_RATE_LIMIT_PATTERNS = (
    r"(?i)usage limit", r"(?i)rate[ _-]?limit", r"\b429\b", r"(?i)hit your .*limit", r"(?i)limit reached",
    r"(?i)resets? (at|in) ", r"(?i)overloaded", r"(?i)too many requests",
)


@dataclass
class UsageSnapshot:
    session_percent: float | None = None
    week_percent: float | None = None
    session_resets: str = ""
    week_resets: str = ""
    raw: str = ""
    probed_at: float = 0.0
    ok: bool = False

    @property
    def worst_percent(self) -> float:
        return max(self.session_percent or 0.0, self.week_percent or 0.0)

    def describe(self) -> str:
        if not self.ok:
            return "usage unknown (probe failed)"
        return (f"session {self.session_percent:.0f}% (resets {self.session_resets or '?'}), "
                f"week {self.week_percent:.0f}% (resets {self.week_resets or '?'})")

    def to_dict(self) -> dict:
        return {"session_percent": self.session_percent, "week_percent": self.week_percent, "session_resets": self.session_resets,
                "week_resets": self.week_resets, "probed_at": self.probed_at, "ok": self.ok}


def parse_usage(text: str, now: float | None = None) -> UsageSnapshot:
    snap = UsageSnapshot(raw=text[:2000], probed_at=now or time.time())
    for m in _LINE.finditer(text or ""):
        kind, pct, resets = m.group(1), float(m.group(2)), (m.group(3) or "").strip()
        if kind == "session":
            snap.session_percent, snap.session_resets = pct, resets
        elif kind.startswith("week (all"):
            snap.week_percent, snap.week_resets = pct, resets
    snap.ok = snap.session_percent is not None or snap.week_percent is not None
    return snap


def probe_usage(binary: str, *, timeout: int = 60) -> UsageSnapshot:
    try:
        proc = subprocess.run([binary, "-p", "/usage", "--output-format", "json", "--tools", "", "--no-session-persistence",
                               "--model", "sonnet", "--permission-prompts", "none"], capture_output=True, text=True, timeout=timeout)
        data = json.loads(proc.stdout.strip() or "{}")
        return parse_usage(str(data.get("result", "")))
    except Exception:  # noqa: BLE001 — a failed probe is "unknown", never a crash
        return UsageSnapshot(ok=False, probed_at=time.time())


def looks_rate_limited(error_text: str) -> bool:
    t = error_text or ""
    return any(re.search(p, t) for p in _RATE_LIMIT_PATTERNS)


@dataclass
class UsageGuard:
    """Decides pause/resume from snapshots; the orchestrator applies the decisions."""
    pause_at: float
    resume_below: float
    enabled: bool = True
    last: UsageSnapshot = field(default_factory=UsageSnapshot)

    def evaluate(self, snap: UsageSnapshot, *, auto_paused: bool) -> str:
        """Returns 'pause', 'resume' or 'hold'."""
        self.last = snap
        if not self.enabled or not snap.ok:
            return "hold"
        if not auto_paused and snap.worst_percent >= self.pause_at:
            return "pause"
        if auto_paused and snap.worst_percent < self.resume_below:
            return "resume"
        return "hold"
