"""ONE LINE PER ARCHITECTURAL-BRAIN PREVIEW REQUEST, so an operator can answer "is it healthy?".

WHY THIS EXISTS (Issue #214, ROOT #211 §4)
------------------------------------------
Before this module, a brain preview request that SUCCEEDED emitted nothing at all. `failure_log`
records failures by design — a refusal or a crash — so the one thing it cannot tell anybody is that
the preview served 200s all day while quietly being something other than the brain.

That is not a hypothetical. #214 proved, in a scratch environment with `scipy` uninstalled, that
every parti falls back to the production sizer, the request returns **200**, and the only trace of
the degradation is a sentence in the plan's own notes — which goes to the caller's screen, never to
a log. From the server's side a wholly degraded preview and a healthy one looked identical.

WHAT A LINE CARRIES, AND WHY EACH FIELD
---------------------------------------
    engine          which engine served the request, so a log is readable without guessing
    sizer/families  what the preview was CONFIGURED to use (`preview_gate`, per request)
    plan_sizer      which sizer actually made the plan that was SHOWN, and `plan_family` its layout
                    — the pair that tells a healthy preview from a silently degraded one
    exact_refusal   the typed code the exact sizer returned, when it refused
                    (`EXACT_SIZER_UNAVAILABLE` / `EXACT_SIZER_UNKNOWN` / `NO_EXACT_PLAN` / a band
                    embedding refusal), so the reason is in the log and not only in a response
    budget_expired  whether the wall-clock request budget ran out before every candidate was sized
    solves          how many exact solves the request ran — 0 on a request that never reached one
    plans           how many distinct plans were offered, `partis` how many were proposed
    seconds         the brain's own measured duration (reported, never used as a budget)
    code            the typed refusal, on a request that produced no plan

A LOGGER AND NOT A FILE, unlike `failure_log`
---------------------------------------------
`failure_log` keeps a JSON file because a failure is a question to ask later ("which code fires
most?"). This is the opposite shape: a per-request health signal an operator reads live, which is
what the process's own stdout already is. Writing successes into `failures.json` would also corrupt
`failure_log.summary()`, whose counts mean "people who did not get a drawing".

NO SECRET EVER REACHES A LINE
-----------------------------
`BRAIN_PREVIEW_TOKEN` is not an argument of any function here and is not read by this module. The
token exists only in `app/demo/router.py`'s request frame and in `preview_gate.authorized`, neither
of which logs; `app/demo/service.py` — this module's only caller — never receives it.
`_fields` builds the line from a fixed, named list, so a future field cannot arrive by accident.
`backend/tests/vertical_slice/test_brain_fallbacks.py` pins it on every path.
"""
from __future__ import annotations

import logging

#: Named so a deployment can raise or silence the preview's own lines without touching the rest of
#: the application's logging.
LOGGER_NAME = "buildsmart.preview"

_log = logging.getLogger(LOGGER_NAME)

#: The fields a line may carry, in order. A fixed list, so the line's shape is reviewable here and
#: no caller can widen it — which is also what keeps a secret out of it.
FIELDS = ("engine", "sizer", "families", "plan_sizer", "plan_family", "exact_refusal",
          "budget_expired", "solves", "plans", "partis", "seconds", "code")


def _fields(values: dict) -> str:
    return " ".join(f"{name}={values[name]}" for name in FIELDS if values.get(name) is not None)


def brain_request(*, engine: str, sizer: str, families: tuple[str, ...], plan_sizer: str | None = None,
                  plan_family: str | None = None, exact_refusal: str | None = None,
                  budget_expired: bool = False, solves: int = 0, plans: int = 0, partis: int = 0,
                  seconds: float = 0.0, code: str | None = None) -> str:
    """Record one preview request. Returns the line, so a caller (and a test) can see exactly what
    was written. Never raises: observability must not become the failure it was recording."""
    values = {
        "engine": engine, "sizer": sizer, "families": ",".join(families) or "-",
        "plan_sizer": plan_sizer, "plan_family": plan_family, "exact_refusal": exact_refusal,
        "budget_expired": str(bool(budget_expired)).lower(), "solves": solves,
        "plans": plans, "partis": partis, "seconds": seconds, "code": code,
    }
    line = _fields(values)
    try:
        # A request that produced no plan is the one an operator must not scroll past.
        _log.warning(line) if code else _log.info(line)
    except Exception:  # noqa: BLE001 - a failing log must stay silent, never mask the real work
        pass
    return line
