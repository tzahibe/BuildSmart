"""Wall-clock budgets in tests are calibrated on the developer machine (M1 Pro).

A shared CI runner with parallel pytest workers is not a performance reference, so CI sets
`WALLCLOCK_BUDGETS=off` and the timing assertions become no-ops there while every functional
assertion in the same tests keeps running. Locally the budgets stay enforced.
"""
from __future__ import annotations

import os


def enforced() -> bool:
    return os.environ.get("WALLCLOCK_BUDGETS", "on").strip().lower() not in ("off", "0", "false", "no")


def within(elapsed_s: float, budget_s: float) -> bool:
    """True when the budget is met OR budgets are switched off (CI)."""
    return (not enforced()) or elapsed_s < budget_s
