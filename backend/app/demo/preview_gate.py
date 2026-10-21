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
                                 forgets it is closed rather than open. The value is never logged
                                 and never appears in a response.

Reading both per request is the whole point of the design. `general_pipeline`'s
`CONCEPT_ENGINE_V2_ENABLED` is a module constant and flipping it needs a new deployment, which
cannot satisfy "instantly disablable"; `app/architect/config.py`'s `*_from_env()` functions are the
repository's existing convention for configuration that must be changeable without one, so this
follows that convention rather than inventing a third. Unsetting `BRAIN_PREVIEW_ENABLED` closes the
preview on the very next request, with no redeploy and no restart.

The refusal is deliberately indistinguishable from an unknown engine (`app/demo/router.py`): same
status, same message, and the message never names an engine the caller is not entitled to, so a
probe cannot learn that a brain exists. `authorized()` therefore does the same work whatever the
answer is, and compares with `hmac.compare_digest`, so neither the message nor the timing is an
oracle.

Refusal codes a preview request can get:

    422 unknown engine '<value>'   flag OFF, token missing or token wrong — byte-identical to the
                                   refusal for a genuinely unknown engine name.
    422 BRAIN_NO_PLAN              authorized and reached the brain, which could not plan the
                                   brief (`app/demo/service.py`).
    422 E1_REAR_BAND_UNAVAILABLE / E1_REAR_BAND_NOT_PLANNABLE
                                   authorized and reached E1's rear-band preview, likewise.

See `docs/wiki/architecture/engine-preview-gate.md`.
"""

from __future__ import annotations

import hmac
import os

#: the environment variables, named once so the tests and the docs cannot drift from the code
FLAG_ENV = "BRAIN_PREVIEW_ENABLED"
TOKEN_ENV = "BRAIN_PREVIEW_TOKEN"
FAMILIES_ENV = "BRAIN_PREVIEW_FAMILIES"
SIZER_ENV = "BRAIN_PREVIEW_SIZER"

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


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def enabled() -> bool:
    """Whether the internal preview is open AT ALL, read from the environment on every call."""
    return _env(FLAG_ENV).lower() in _TRUE


def authorized(token: str | None) -> bool:
    """Whether this request may reach a preview engine: the flag is on AND `token` matches the
    configured secret.

    Both halves are read here, per request, so unsetting either closes the preview on the next
    request. The comparison is `hmac.compare_digest`, and the function does the same work whether
    it says yes or no — a caller must not be able to tell "wrong token" from "no such engine" by
    how long the answer took any more than by what it said.
    """
    expected = _env(TOKEN_ENV)
    presented = (token or "").strip()
    # No secret configured means nobody is authorized. The comparison still runs, against a value
    # that cannot match, so the unconfigured case costs what the configured one costs.
    matches = hmac.compare_digest((presented or "\0").encode("utf-8"),
                                  (expected or "\0\0").encode("utf-8"))
    return enabled() and bool(expected) and matches


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
