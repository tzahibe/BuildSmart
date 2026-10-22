"""THE PREVIEW MAY NOT COST PRODUCTION ANYTHING (Issue #246, ROOT #211).

WHAT WAS MEASURED, AND WHY THIS MODULE EXISTS
---------------------------------------------
#226 ran the question alone on an idle ten-core machine, with a same-session control, against a
scratch server: **production's own latency, beside N concurrent brain preview requests.**

    concurrent brain requests   production median   production worst
    0                           1.65 s              1.71 s
    2                           5.89 s              11.51 s
    4                           9.29 s              16.87 s
    0 again                     1.63 s              -

x3.6 to x5.6 on the median, x9.9 at worst, and a complete recovery the moment the load stopped —
so contention, not a leak. The mechanism is the GIL: `scipy.optimize.milp` does not release it, so
every brain request serializes on one saturated core (the server process sat at 107.3 % CPU with
*one* brain request and 100.2 % with *four*) and Starlette's anyio threadpool buys nothing at all.
Memory was never the risk (241 -> 272 MB).

Two consequences are worse than that table reads, and both shaped this module:

* **The event loop stayed responsive.** `/docs` answered in 26 ms median over 315 samples while
  four brain requests ran. A liveness probe therefore stayed green while a real user waited 17 s —
  the probe suppressed the one alarm it exists to raise. `app/main.py`'s `/health` now reports this
  module's occupancy for that reason.
* **Contention changed the product's answer.** B08 alone shipped `PUBLIC_BAND+FOYER` at 131.45 m²;
  the same brief beside three others shipped `TWO_HALL` at 129.92 m². Two people comparing the
  preview at the same moment were not looking at the same engine.

TWO THINGS ARE DONE ABOUT IT, AND NEITHER TOUCHES THE ENGINE
------------------------------------------------------------
1. **Admission: one preview request at a time**, server-side, enforced here rather than advised in
   a runbook. The number is `preview_gate.max_concurrency()` — 1 by default and 1 at most.
2. **A separate process**, so a preview request cannot hold the interpreter lock production needs.
   The admission limit alone would not have been enough: #226 measured 107.3 % CPU with a *single*
   brain request, which is one whole core taken from production inside production's own process.

WHY A `threading` PRIMITIVE AND NOT `asyncio.Semaphore`
-------------------------------------------------------
This is the trap, and it is worth naming because the obvious answer silently does nothing here.

`app/demo/router.py`'s handlers are plain `def`, not `async def`, so Starlette runs them with
`anyio.to_thread.run_sync` — on a worker thread, with no running event loop. An
`asyncio.Semaphore` cannot be awaited from that thread at all, and `asyncio.run()`-ing one per
request would create a *fresh* semaphore each time, which bounds nothing. The streaming endpoint is
worse still: it starts its own bare `threading.Thread` and does the work there, two frames away
from any loop. And making the handler `async def` so a semaphore *could* be awaited would move a
30-second GIL-holding solver onto the event loop thread — turning the one good property #226 found
(the loop stayed responsive) into a total stall.

So the primitive is a `threading.Lock` around a counter, which works on a worker thread, on a bare
thread, and under `TestClient`. A `threading.BoundedSemaphore` would also work, but it is
constructed with a fixed value, and the limit here is read *per request* like every other piece of
this gate's configuration, so a lock and a counter is the honest shape.

WHY A SECOND REQUEST IS REFUSED AND NOT QUEUED
----------------------------------------------
Refused, with `PREVIEW_BUSY` and HTTP 503.

#226 measured a brain request at **31.6 s median and 48.9 s max**. A queued second request would
therefore wait up to ~49 s before its own work *started*, for a total approaching 100 s — a wait
that is itself a bad answer, and one no browser or `curl` default would still be listening for, so
the server would finish a 30-second solve for nobody. A refusal is immediate, honest, and
countable: it goes through `DemoGenerationError`, so `failure_log` records it with the brief that
was refused, and an operator can see that the preview is oversubscribed instead of inferring it
from a latency graph.

The refusal is reachable **only by an authorized request**: admission is checked after
`preview_gate.authorized`, at a seam only a resolved gated engine reaches, so the new code is not a
new oracle — an unauthorized prober still gets the one 422 that names no hidden engine.

WHY A SUBPROCESS PER REQUEST, AND NOT A SECOND SERVER OR A WARM POOL
--------------------------------------------------------------------
* **A second uvicorn** is the shape that looks right on a diagram and is the worst one to own. It
  needs a second port, a routing rule, a second supervisor entry and a *second copy of the gate's
  state* — the flag, the token and the kill file would have to be true in two places, and #231's
  whole finding was that an operator gets one off switch and it must work. It also bounds nothing
  by itself: N concurrent brain requests inside it serialize exactly as they do today.
* **A warm worker pool** (`ProcessPoolExecutor`) saves the interpreter start-up, and keeps a
  long-lived process that has already imported the engine. That is precisely what makes it wrong
  here: a wedged or leaking solver survives the request that caused it, the kill file cannot reach
  a child that is mid-solve, and a pool of size 1 is this module with a worse failure mode.
* **A subprocess per request** has its own GIL, its own memory, and dies with the request. A crash
  is an exit code instead of a dead worker thread, the OS scheduler — not the interpreter lock —
  decides who gets a core, and the child is `nice`d so that decision favours production. The cost
  is one interpreter start plus the engine's imports, paid by the preview alone and only once per
  request; against #226's 31.6 s median that is a few percent, and the proof is in
  `docs/reports/architectural-brain/PREVIEW-isolation-proof.md`.

WHAT THE CHILD IS AND IS NOT GIVEN
----------------------------------
It is given the project as JSON on stdin and the engine flags the parent already resolved. It is
**not** given `BRAIN_PREVIEW_TOKEN`: the authorization decision was taken in the parent's request
frame and is finished, so the secret has no business crossing the boundary. The child never
re-checks authorization — it could not, and must not, be a second gate.

Its stdout is this module's protocol. Its **stderr is inherited**, so `preview_log`'s one line per
request (#214) still lands in the server's own output beside uvicorn's access line — which is only
true because the child calls `log_output.configure()` itself (#233: the application had no logging
configuration, and a record with no handler is a record nobody receives; a child process starts out
in exactly that state).
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from . import preview_gate
from .contract import DemoPlanSet
from .service import DemoGenerationError, generate_demo_design

#: the module the child runs as, named once so the parent's command line and the `__main__` guard
#: at the bottom of this file cannot drift apart
CHILD_MODULE = "app.demo.preview_isolation"

#: `backend/`, from this module's own location rather than the working directory — the same
#: reasoning as `preview_gate.DEFAULT_KILL_FILE`: the child must find the application however the
#: parent happened to be started.
BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]

#: Set in the child's environment so a child can tell it is one. Nothing branches on it today; it
#: is there for an operator reading `ps` output and for the test that proves the token is gone.
CHILD_MARKER_ENV = "BRAIN_PREVIEW_IN_CHILD"

#: The child's scheduling penalty. Removing the GIL coupling is what makes production safe; this is
#: what decides the remaining, ordinary competition for a core, and it decides it in production's
#: favour. 10 is the conventional "background work" value and needs no privileges.
CHILD_NICE = 10

#: A WATCHDOG, and deliberately not a request budget. #247 owns the request budget — #226 measured
#: that the stated 30 s bounds only one stage and a request still costs 34.8 s. This number exists
#: for one narrower failure: a child that is wedged forever would otherwise hold the single
#: admission slot forever, which would be a new fault introduced by this change. It is set far
#: above any measured request so that it can never be mistaken for the budget.
CHILD_WATCHDOG_S = 600.0

#: the typed refusal an authorized request gets when the preview is already busy
BUSY_CODE = "PREVIEW_BUSY"
BUSY_MESSAGE = ("התצוגה המוקדמת של המוח האדריכלי תפוסה כרגע בבקשה אחרת. "
                "נסו שוב בעוד דקה.")
#: the `Retry-After` an operator (and a client) is told, in seconds — #226's median brain request
BUSY_RETRY_AFTER_S = 32


class PreviewBusy(DemoGenerationError):
    """The preview is already running a request, and this one is refused rather than queued.

    A `DemoGenerationError` on purpose, so it needs no new handling anywhere: the plain endpoint
    already turns one into a typed body and records it in `failure_log` with the brief, and the
    streaming endpoint already turns one into a typed `error` event. `http_status` is the one thing
    it adds — 503 and not 422, because "come back in a moment" is a statement about the server's
    capacity and not about the request, and because a 503 with `Retry-After` is the answer a client
    can act on without reading Hebrew.
    """

    #: read by `app/demo/router.py`; every other `DemoGenerationError` keeps 422
    http_status = 503
    retry_after = BUSY_RETRY_AFTER_S

    def __init__(self, *, limit: int, running: int, oldest_s: float) -> None:
        super().__init__(
            BUSY_CODE, BUSY_MESSAGE,
            f"preview concurrency limit {limit} reached: {running} in flight, "
            f"oldest running {oldest_s:.1f}s")
        self.limit = limit
        self.running = running
        self.oldest_s = oldest_s


class PreviewProcessError(RuntimeError):
    """The child process did not answer — it died, or its stream ended mid-protocol.

    Deliberately NOT a `DemoGenerationError`. A refusal means "we considered your brief and will not
    draw it"; this means the preview broke, and it must travel the crash path (#230) so
    `failure_log.crash` records it and the response is a 500 rather than a tidy 422 that reads like
    a verdict on the house. The child's own traceback is already in the server's output: its stderr
    is inherited, not captured.
    """


# ============================================================ 1. ADMISSION: one at a time

#: `token -> monotonic start`, guarded by `_lock`. A dict rather than a counter so `/health` can
#: report HOW LONG the oldest in-flight request has been running, which is the number that makes
#: an honest liveness signal possible at all.
_in_flight: dict[int, float] = {}
_lock = threading.Lock()
_tokens = itertools.count(1)


def occupancy() -> dict[str, object]:
    """What the preview is doing right now, for `/health` — a fact, never a judgement.

    `oldest_running_s` is the point of it. #226's defect was a probe that answered in 26 ms while a
    user waited 17 s; a signal that reports only "up" repeats that mistake, and a signal that
    reports only a count cannot tell one request that started a moment ago from one that has been
    running for five minutes.
    """
    now = time.monotonic()
    with _lock:
        started = sorted(_in_flight.values())
        limit = preview_gate.max_concurrency()
    return {
        "in_flight": len(started),
        "limit": limit,
        "slots_free": max(0, limit - len(started)),
        "oldest_running_s": round(now - started[0], 3) if started else 0.0,
    }


@contextmanager
def admitted() -> Iterator[None]:
    """Hold one of the preview's slots for the duration of the block, or refuse.

    The limit is read HERE, per request, so narrowing it takes effect on the next request like
    every other piece of this gate's configuration. Release is in a `finally`, in this one
    function, which is why admission is acquired at the seam that runs the work and not in
    `_resolve_engine`: a slot taken while resolving a *streaming* request would be released by a
    generator body that a disconnected client may never run, and a leaked slot of a pool of one is
    an outage.
    """
    limit = preview_gate.max_concurrency()
    now = time.monotonic()
    with _lock:
        if len(_in_flight) >= limit:
            oldest = min(_in_flight.values())
            raise PreviewBusy(limit=limit, running=len(_in_flight), oldest_s=now - oldest)
        token = next(_tokens)
        _in_flight[token] = now
    try:
        yield
    finally:
        with _lock:
            _in_flight.pop(token, None)


# ============================================================ 2. THE SEPARATE PROCESS

def _child_env() -> dict[str, str]:
    """The child's environment: the parent's, minus the secret, plus a marker.

    Everything else is inherited on purpose — `preview_gate.sizer()` and `families()` are read
    inside the child and must answer exactly what they would have answered in the parent, or the
    log line (#214) would describe a configuration the request did not run.
    """
    env = dict(os.environ)
    env.pop(preview_gate.TOKEN_ENV, None)
    env[CHILD_MARKER_ENV] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _child_command() -> list[str]:
    return [sys.executable, "-m", CHILD_MODULE]


def _lower_priority() -> None:
    """Run behind production in the OS scheduler. Called by the CHILD, in its own first moments.

    Not `Popen(preexec_fn=…)`, which runs between `fork` and `exec` in a process that has just
    inherited the parent's locks and is documented as unsafe in a threaded program — and this
    parent is threaded by construction (Starlette's threadpool, and the streaming endpoint's own
    thread). The child setting its own niceness needs no `fork`-time callback at all.

    Never fatal: a niceness that cannot be set costs the isolation nothing, because the isolation
    is the separate process. This only decides the ordinary competition that is left.
    """
    try:
        os.nice(CHILD_NICE)
    except Exception:                      # noqa: BLE001 - a niceness we cannot set is not a failure
        pass


def _in_this_process(project, *, brain: bool, rear_band: bool,
                     concept_engine_v2: bool | None,
                     on_stage: Callable[[str], None] | None) -> DemoPlanSet:
    """Run one request HERE, which is where production has always run and still does.

    Deliberately the same signature as `_in_child_process`, so the two are interchangeable: that is
    what lets the gate's own tests (which fake `run_brain` to make "reached the brain" observable in
    milliseconds) swap the child for this one without the production path acquiring a switch that
    could turn the isolation off.
    """
    result = generate_demo_design(project, on_stage=on_stage,
                                  concept_engine_v2=concept_engine_v2,
                                  brain=brain, rear_band_preview=rear_band)
    return DemoPlanSet(plan=result.design, alternatives=list(result.alternatives),
                       search=result.search, building=result.building)


def _in_child_process(project, *, brain: bool, rear_band: bool,
                      concept_engine_v2: bool | None,
                      on_stage: Callable[[str], None] | None) -> DemoPlanSet:
    """Run one preview request in a child process and return the payload it produced.

    The protocol is one JSON object per line on the child's stdout: any number of
    `{"stage": name}`, then exactly one of `{"ok": …}`, `{"error": …}` or `{"crash": …}`. Stages
    are forwarded as they arrive, which is what keeps the streaming endpoint's percentage honest
    across the process boundary — collecting them and replaying them at the end would be a faithful
    record and a useless indicator.
    """
    request = json.dumps({
        "project": json.loads(project.model_dump_json()),
        "brain": brain, "rear_band": rear_band, "concept_engine_v2": concept_engine_v2,
    }, ensure_ascii=False)

    proc = subprocess.Popen(                                       # noqa: S603 - fixed argv
        _child_command(), cwd=str(BACKEND_ROOT), env=_child_env(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
        text=True, encoding="utf-8", start_new_session=True)
    watchdog = threading.Timer(CHILD_WATCHDOG_S, proc.kill)
    watchdog.daemon = True
    watchdog.start()
    outcome: dict | None = None
    try:
        proc.stdin.write(request + "\n")                           # type: ignore[union-attr]
        proc.stdin.flush()                                         # type: ignore[union-attr]
        proc.stdin.close()                                         # type: ignore[union-attr]
        for line in proc.stdout:                                   # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                # Not ours. The child's own output is not this module's to swallow, but it is also
                # not a protocol message: ignore it here and let it stand in the server's log.
                continue
            if "stage" in message:
                if on_stage is not None:
                    on_stage(message["stage"])
                continue
            outcome = message
            break
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    if outcome is None:
        raise PreviewProcessError(
            f"the preview process produced no answer (exit {proc.returncode})")
    if "ok" in outcome:
        return DemoPlanSet.model_validate(outcome["ok"])
    if "error" in outcome:
        err = outcome["error"]
        raise DemoGenerationError(err["code"], err["message"], err.get("detail", ""))
    raise PreviewProcessError(
        f"the preview process crashed: {outcome.get('crash', 'unknown')} (exit {proc.returncode})")


# ============================================================ 3. THE ONE SEAM

def plan_set(project, choice, on_stage: Callable[[str], None] | None = None) -> DemoPlanSet:
    """Generate this request's plans — the ONE place either endpoint runs an engine.

    Production and Concept Engine v2 run exactly where they ran before, in this process, with no
    admission check and no child: they are the traffic being protected, and nothing about them
    changes. A **gated preview** engine — `?engine=brain` or `?engine=e1_rear_band`, both of which
    only an authorized request can reach — takes a slot and runs in a child.

    Both gated engines are covered, not only the measured one. #226 measured the brain; nothing
    measured `e1_rear_band`, and "not measured" is not "safe". One rule for the whole preview is
    also the rule an operator can hold in their head.
    """
    if not (choice.brain or choice.rear_band):
        return _in_this_process(project, brain=False, rear_band=False,
                                concept_engine_v2=choice.concept_engine_v2, on_stage=on_stage)
    with admitted():
        return _in_child_process(project, brain=choice.brain, rear_band=choice.rear_band,
                                 concept_engine_v2=choice.concept_engine_v2, on_stage=on_stage)


# ============================================================ 4. THE CHILD

def _child_main(stdin=None, stdout=None) -> int:
    """`python -m app.demo.preview_isolation`: one request in, one payload out, then exit.

    Nothing is imported here that the parent does not already import; the cost is the interpreter
    and the engine's own import graph, which is the price of the isolation and is paid by the
    preview alone.
    """
    from app.observability import log_output
    from app.projects.models import Project

    # #233's lesson, which a child process re-learns the hard way: a logger with no handler drops
    # its records. Without this the preview's one line per request (#214) would vanish the moment
    # the work moved out of the server's process — the exact regression this file must not cause.
    log_output.configure()
    _lower_priority()
    _in = stdin or sys.stdin
    _out = stdout or sys.stdout

    def emit(message: dict) -> None:
        _out.write(json.dumps(message, ensure_ascii=False) + "\n")
        _out.flush()

    request = json.loads(_in.readline())
    project = Project.model_validate(request["project"])
    try:
        result = generate_demo_design(
            project, on_stage=lambda name: emit({"stage": name}),
            concept_engine_v2=request.get("concept_engine_v2"),
            brain=bool(request.get("brain")), rear_band_preview=bool(request.get("rear_band")))
    except DemoGenerationError as error:
        # Carried across as a refusal and re-raised in the parent's request frame, so the parent —
        # which still has the brief, the parcel and the footprint — writes the failure-log entry.
        emit({"error": {"code": error.code, "message": error.message, "detail": error.detail}})
        return 0
    except BaseException as error:         # noqa: BLE001 - reported across the boundary, then re-raised
        emit({"crash": type(error).__name__})
        raise
    payload = DemoPlanSet(plan=result.design, alternatives=list(result.alternatives),
                          search=result.search, building=result.building)
    emit({"ok": json.loads(payload.model_dump_json())})
    return 0


if __name__ == "__main__":                 # pragma: no cover - exercised as a real child process
    sys.exit(_child_main())
