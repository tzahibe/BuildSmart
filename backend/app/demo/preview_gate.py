"""THE INTERNAL-PREVIEW GATE for the development engines behind `?engine=` (Issue #212, ROOT #211).

Before this module, `?engine=brain` **was** the authorization: any caller who typed the parameter
reached the Architectural Brain, and nothing could be turned off without a new deployment. Two
things are now required of such a request, and both are read from the environment at REQUEST time:

    BRAIN_PREVIEW_ENABLED        1|true|yes|on to open the preview at all. Absent/anything else
                                 means OFF, which is the committed default — the preview is never
                                 on because a module was imported.
    BRAIN_PREVIEW_TOKEN          the shared secret an authorized request presents in the
                                 `X-Brain-Preview-Token` header. No default, no fallback: an unset
                                 or empty token means NOBODY is authorized, so a deployment that
                                 forgets it is closed rather than open. The value is never written
                                 down and never appears in a response.

And one that OVERRIDES both of them, because reading the environment per request turned out not to
be enough (#214 measured it, #231 fixes it):

    BRAIN_PREVIEW_KILL_FILE      an ADDITIONAL path whose existence closes the preview. The
                                 built-in path `DEFAULT_KILL_FILE` is checked whatever this says,
                                 so configuration can add a kill location but can never move or
                                 remove the one an operator is told about.

And one that bounds what the preview may COST, because #226 measured that an unbounded preview
degrades production traffic:

    BRAIN_PREVIEW_MAX_CONCURRENCY  how many preview requests may run at once. 1 by default and 1 at
                                 most — `max_concurrency()` clamps, so this may only ever make the
                                 preview smaller than the measurement supports. Enforced in
                                 `app/demo/preview_isolation.py`, at the one seam the gated engines
                                 run through.

**Why a file.** `BRAIN_PREVIEW_ENABLED` and `BRAIN_PREVIEW_TOKEN` are read per request, which was
meant to make the preview "disablable immediately, without a new deployment". #214 tested that
claim against a running server and it is false in the configuration that matters: a process's
`os.environ` cannot be changed from outside the process, a worker does not re-read `.env`, and when
the variables were EXPORTED in the starting shell, removing them from `.env` and forcing a reload
left the preview open — `load_dotenv()` does not override, and a respawned worker inherits its
parent's environment. The only disable left was stopping the process, which is an owner action and
the opposite of "no deployment". A file is the one signal an operator can change from outside the
process, that needs no cooperation from the environment that enabled the preview, and that the next
request sees.

**It fails closed.** A check that cannot decide refuses: an unreadable path, a permission error, a
path that is not usable as a path, any exception at all means DISABLED. The dangerous direction of a
broken kill switch is the one that keeps the preview serving.

Reading both per request is the whole point of the design. `general_pipeline`'s
`CONCEPT_ENGINE_V2_ENABLED` is a module constant and flipping it needs a new deployment, which
cannot satisfy "instantly disablable"; `app/architect/config.py`'s `*_from_env()` functions are the
repository's existing convention for configuration that must be changeable without one, so this
follows that convention rather than inventing a third. Unsetting `BRAIN_PREVIEW_ENABLED` closes the
preview on the very next request *when the variable came from `.env` and the worker re-read it* —
and the kill file closes it on the very next request in every other case too, including the one
where the variable is exported and cannot be unset at all.

The refusal is deliberately indistinguishable from an unknown engine (`app/demo/router.py`): same
status, same message, and the message never names an engine the caller is not entitled to, so a
probe cannot learn that a brain exists. `authorized()` therefore does the same work whatever the
answer is, and compares with `hmac.compare_digest`, so neither the message nor the timing is an
oracle.

Refusal codes a preview request can get:

    422 unknown engine '<value>'   flag OFF, kill file present, token missing or token wrong —
                                   byte-identical to the refusal for a genuinely unknown engine
                                   name. The kill switch adds no code and no new message of its
                                   own: a killed preview is a preview that does not exist.
    503 PREVIEW_BUSY              authorized, and another preview request is already running
                                   (`app/demo/preview_isolation.py`). Only an AUTHORIZED request
                                   can ever see this code, so it tells an unauthorized prober
                                   nothing it did not already know.
    422 BRAIN_NO_PLAN              authorized and reached the brain, which could not plan the
                                   brief (`app/demo/service.py`).
    422 E1_REAR_BAND_UNAVAILABLE / E1_REAR_BAND_NOT_PLANNABLE
                                   authorized and reached E1's rear-band preview, likewise.

See `docs/wiki/architecture/engine-preview-gate.md`.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path

#: the environment variables, named once so the tests and the docs cannot drift from the code
FLAG_ENV = "BRAIN_PREVIEW_ENABLED"
TOKEN_ENV = "BRAIN_PREVIEW_TOKEN"
FAMILIES_ENV = "BRAIN_PREVIEW_FAMILIES"
SIZER_ENV = "BRAIN_PREVIEW_SIZER"
KILL_FILE_ENV = "BRAIN_PREVIEW_KILL_FILE"
MAX_CONCURRENCY_ENV = "BRAIN_PREVIEW_MAX_CONCURRENCY"

#: THE KILL SWITCH's built-in location: `backend/DISABLE_BRAIN_PREVIEW`, derived from this module's
#: own path rather than from the working directory, so the path an operator is told in the runbook
#: is the path the running process checks however it was started. It is the directory the operator
#: already edits (`backend/.env` lives here), and the name says what creating it does.
DEFAULT_KILL_FILE: str = str(Path(__file__).resolve().parents[2] / "DISABLE_BRAIN_PREVIEW")

#: the request header carrying the shared secret
TOKEN_HEADER = "X-Brain-Preview-Token"

#: What counts as ON. Everything else — unset, empty, "0", "false", a typo — is OFF, because the
#: dangerous direction of a misread flag is the one that opens the preview.
_TRUE = frozenset({"1", "true", "yes", "on"})

#: THE BRAIN's sizer and layout families for the preview (#197 item 4, 2026-10-15): the exact MILP
#: placement with the target objective, and the cross-band layouts measured on the frozen six.
DEFAULT_SIZER = "exact"
DEFAULT_FAMILIES: tuple[str, ...] = ("band", "spine", "stack", "cells")

#: The families the preview may EVER use — measured, gate-passed work only. A family absent from
#: this set is unreachable from `?engine=brain` whatever the configuration asks for, which is what
#: keeps work in flight out of a preview an owner is looking at: #208's `generator` family took a
#: day-2 gate verdict of STOP, so it is not here and configuration cannot put it here. Widening
#: this set is a code change with a review, not an environment variable someone sets at 2 a.m.
ALLOWED_FAMILIES: frozenset[str] = frozenset(DEFAULT_FAMILIES)

#: Named so the test that pins the exclusion reads as the promise it is, rather than as the absence
#: of a string. Kept separate from `ALLOWED_FAMILIES` on purpose: "not allowed yet" and "refused by
#: a gate verdict" are different facts and the second one is worth saying out loud.
GATE_FAILED_FAMILIES: frozenset[str] = frozenset({"generator"})

#: HOW MANY PREVIEW REQUESTS MAY RUN AT ONCE (#246, from #226's measurement).
#:
#: #226 measured production's own latency beside N concurrent brain requests, alone on an idle
#: machine with a same-session control: 1.65 s median quiet, 5.89 s at N=2, 9.29 s at N=4, 16.87 s
#: worst case, and 1.63 s again once the load stopped. `scipy.optimize.milp` holds the GIL, so the
#: requests serialize on one saturated core (107.3 % CPU with one, 100.2 % with four) and Starlette's
#: threadpool buys nothing. #226's own conclusion was "safe limit: one concurrent brain request,
#: enforced server-side".
#:
#: So 1 is the default AND the ceiling. The asymmetry is the same one `ALLOWED_FAMILIES` has and it
#: is deliberate: configuration may make the preview *smaller* than the measurement supports and can
#: never make it bigger. #226 measured N=2 and N=4 as harmful and measured no N above 1 as safe, so
#: there is no number above 1 an environment variable could be *entitled* to ask for. Raising this
#: is a new measurement and a code change with a review, not a variable someone sets at 2 a.m.
DEFAULT_MAX_CONCURRENCY = 1
MAX_CONCURRENCY_CEILING = 1


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def kill_file_paths() -> tuple[str, ...]:
    """Every path whose existence closes the preview, in the order they are checked.

    `DEFAULT_KILL_FILE` is always first and is always checked. `BRAIN_PREVIEW_KILL_FILE` may ADD a
    second location — for a deployment whose `backend/` is read-only, say — but it cannot move the
    built-in one away, and blanking it takes nothing away. That asymmetry is deliberate: a kill
    switch whose location the enabling environment could choose would need that environment's
    cooperation, which is exactly the property #214 found missing.
    """
    configured = _env(KILL_FILE_ENV)
    if configured and configured != DEFAULT_KILL_FILE:
        return (DEFAULT_KILL_FILE, configured)
    return (DEFAULT_KILL_FILE,)


def killed() -> bool:
    """Whether a kill file closes the preview right now — resolved per call, never cached.

    `os.lstat` rather than a convenience existence check, for two reasons. It does not follow
    symlinks, so a dangling symlink with the kill file's name still counts as "somebody disabled
    this". And it RAISES, which is what lets this fail closed: `Path.exists()` swallows every
    `OSError` and answers False — "keep serving" — for a permission error or a broken mount, which
    is the one answer a kill switch must never give.

    Exactly one outcome means "not killed": `FileNotFoundError`, the file is plainly absent.
    Everything else means killed — the file is there, or the check could not decide (a permission
    error, a path with a NUL in it, a stale mount, a path whose parent is a file, a `TypeError` on
    something that is not a path at all). An operator who has mis-set `BRAIN_PREVIEW_KILL_FILE`
    gets a closed preview and a line in the runbook, not a preview that kept serving because its
    off switch was broken.
    """
    for path in kill_file_paths():
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except BaseException:                 # noqa: BLE001 - a check that cannot decide refuses
            return True
        return True
    return False


def enabled() -> bool:
    """Whether the internal preview is open AT ALL, resolved on every call.

    The kill file wins over everything. It is evaluated unconditionally, before the result is
    combined, so a request costs the same whichever way either half answers.
    """
    killed_now = killed()
    flag_on = _env(FLAG_ENV).lower() in _TRUE
    return flag_on and not killed_now


def authorized(token: str | None) -> bool:
    """Whether this request may reach a preview engine: the flag is on AND `token` matches the
    configured secret.

    Both halves are read here, per request, so a change to either one is seen by the next request
    — by the next request *in this process*, which is a weaker promise than it sounds and is why
    `enabled()` also consults the kill file. That closes the preview on the next request whatever
    the environment says, and it lives behind this one function, so this stays the ONE question the
    router asks and the kill switch is not a second gate somewhere else. The comparison is `hmac.compare_digest`, and the function does the
    same work whether it says yes or no — a caller must not be able to tell "wrong token" from "no such engine" by
    how long the answer took any more than by what it said.
    """
    expected = _env(TOKEN_ENV)
    presented = (token or "").strip()
    # No secret configured means nobody is authorized. The comparison still runs, against a value
    # that cannot match, so the unconfigured case costs what the configured one costs.
    matches = hmac.compare_digest((presented or "\0").encode("utf-8"),
                                  (expected or "\0\0").encode("utf-8"))
    return enabled() and bool(expected) and matches


def max_concurrency() -> int:
    """How many preview requests may run at once — configuration, clamped to what was measured.

    Read per call, like everything else here, so a narrowing takes effect on the next request.

    The clamp has a floor as well as a ceiling. 0 or a negative value would *close* the preview,
    and closing it is the kill switch's job (`DISABLE_BRAIN_PREVIEW`), not this variable's: two
    different ways to turn the preview off is one way too many, and an operator who meant to
    disable it must reach for the switch the runbook names. An unparseable value is the default,
    for the same reason an unparseable flag is OFF — the dangerous direction of a misread number is
    the one that lets more work in.
    """
    raw = _env(MAX_CONCURRENCY_ENV)
    try:
        asked = int(raw)
    except ValueError:
        return DEFAULT_MAX_CONCURRENCY
    return max(1, min(MAX_CONCURRENCY_CEILING, asked))


def sizer() -> str:
    """The brain's sizer for the preview — configuration, with the measured default."""
    return _env(SIZER_ENV) or DEFAULT_SIZER


def families() -> tuple[str, ...]:
    """The brain's layout families for the preview — configuration, filtered through
    `ALLOWED_FAMILIES`.

    `BRAIN_PREVIEW_FAMILIES` is a comma-separated list and may only NARROW the preview: a name
    outside `ALLOWED_FAMILIES` is dropped rather than honoured, so no environment variable can show
    an owner a family that has not passed its gate. An empty or entirely-unrecognised list means
    the default, because a preview that silently sized nothing would read as a brain that cannot
    plan.
    """
    raw = _env(FAMILIES_ENV)
    if not raw:
        return DEFAULT_FAMILIES
    asked = [part.strip().lower() for part in raw.split(",")]
    kept = tuple(dict.fromkeys(name for name in asked if name in ALLOWED_FAMILIES))
    return kept or DEFAULT_FAMILIES
