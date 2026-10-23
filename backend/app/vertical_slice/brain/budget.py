"""One wall-clock budget for a WHOLE brain request, and the record of what it refused to start.

THE DEFECT THIS EXISTS TO FIX (#226, #247). `REQUEST_BUDGET_S` was handed to `_improve_exactly`
and to nothing else, so it bounded the exact sizer's search and left every other stage of the
request open-ended. Measured: with `budget_s=0.2` a request still cost 23.0 s on B11 and 34.8 s on
B16, and on B16 the exact pipeline was never entered at all — 26.4 s went to the production sizer
inside `run_brain`'s own first stage, which read no deadline. A stated 30 s was therefore a time
limit on one stage, not a request timeout.

A budget bounds a request only if every stage reads the SAME instant, so this object carries the
instant rather than a duration: `started` is taken once, at the beginning of the request, and
`deadline` is derived. `run_brain`'s production stage, the band pipeline's candidate loop, the
widening ladder and the exact sizer all consult the one object.

Two properties are deliberate and are the whole honesty of it:

* **Nothing is cancelled in flight.** `expired()` is asked BEFORE a unit of work is started and
  never during one. Killing a solve mid-flight would trade a slow plan for no plan, so a request
  may overrun its budget by the duration of the last unit it had already begun. That overshoot is
  bounded by the slowest single unit, measured and stated in the report, not hidden.
* **What was not started is recorded, not silently dropped.** `gave_up()` accumulates one sentence
  per distinct thing skipped, and those sentences travel to the response as plan notes. A request
  that ran out of time says so and still returns its plans; only a genuine no-plan is an error.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RequestBudget:
    """`budget_s` seconds from `started`, shared by every stage of one request.

    `started` is a `time.monotonic()` instant. It is the REQUEST's start — not the brain's — so
    the production work a brain request does before the brain is entered is inside the budget too,
    which is the only way the stated number can describe what a caller waits.
    """

    budget_s: float
    started: float
    _given_up: list[str] = field(default_factory=list)

    @classmethod
    def starting_now(cls, budget_s: float) -> RequestBudget:
        return cls(budget_s=budget_s, started=time.monotonic())

    @property
    def deadline(self) -> float:
        """The `time.monotonic()` instant after which no new unit of work is started."""
        return self.started + self.budget_s

    def spent(self) -> float:
        return time.monotonic() - self.started

    def left(self) -> float:
        return self.deadline - time.monotonic()

    def expired(self) -> bool:
        return self.left() <= 0.0

    def gave_up(self, what: str) -> None:
        """Record one thing the budget refused to start. Repeats of the same sentence collapse."""
        if what and what not in self._given_up:
            self._given_up.append(what)

    @property
    def given_up(self) -> tuple[str, ...]:
        return tuple(self._given_up)

    def notes(self) -> tuple[str, ...]:
        """The sentences a plan carries when the budget ran out — what did not run, and when.

        Empty when nothing was skipped, so a request that finished inside its budget says nothing
        and a plan's notes do not change.
        """
        if not self._given_up:
            return ()
        return (f"the request budget of {self.budget_s:g} s ran out after {self.spent():.1f} s; "
                + "; ".join(self._given_up),)


#: A budget that bounds nothing, for the callers and tests that had no deadline before this
#: existed. Every consulting site treats `None` as "no budget" and behaves exactly as it did.
NO_BUDGET: RequestBudget | None = None
