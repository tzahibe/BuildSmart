"""THE APPLICATION'S LOG LINES REACH THE SERVER'S OUTPUT. Nothing else.

WHY THIS EXISTS (Issue #233, ROOT #211)
---------------------------------------
#214 added one line per brain preview request (`preview_log`) so an operator could tell a healthy
preview from one quietly serving production's geometry, and #211's risk register recorded that
detection as closed. #231, proving the kill switch against a real server, found that **no line
appeared at all**: there was no logging configuration anywhere in this application, so under
`uvicorn app.main:app` — the one way the README documents running it — the record reached the root
logger, found no handler, and was dropped. It was genuinely emitted (the unit tests capture it with
`caplog`, which installs its own root handler and is therefore exactly what missed this) and
genuinely invisible in a deployment.

Measured on a scratch server before this module existed
(`docs/reports/architectural-brain/PREVIEW-logging-proof.md`):

    a served brain request   INFO     -> nothing. No handler, and INFO is below `lastResort`.
    a no-plan request        WARNING  -> arrived, via `logging.lastResort`, as a bare line with no
                                        level, no logger name and nothing marking it a warning.

So the only preview line an operator could see was the one for a request that failed, unlabelled —
the inverse of the health signal #214 was asked for.

WHAT THIS CONFIGURES, AND WHAT IT DELIBERATELY DOES NOT
-------------------------------------------------------
One handler, on one logger: `buildsmart`, which is already this application's own logger namespace
and not a new convention — `buildsmart.preview`, `buildsmart.design_pipeline` and
`buildsmart.architect_local_gateway` are every logger the application names for itself.

- **Not the root logger**, because that would also raise every library's INFO chatter (`httpx`,
  `openai`, `urllib3`) to the operator's screen. Nobody asked for that, and a log an operator
  stops reading is not an improvement on no log.
- **Not per-module levels, not a config file, not a logging framework.** The whole configuration is
  "the application's own lines go to stderr at INFO", which is the smallest thing that makes #214's
  line arrive.
- **`propagate` is left alone** (so, on). `caplog` captures at the root, and #214's and #231's
  tests rely on that; turning propagation off here would silence them. One handler plus
  propagation means exactly one copy under `uvicorn`, where the root has no handler.
- **stderr**, which is where uvicorn's own `default` handler writes, so the preview's line appears
  in order among the access lines for the same requests rather than in a second interleaved stream.
- **No timestamp in the format**, matching uvicorn's own default line (`INFO:     127.0.0.1 - …`).
  The level is in the format because the runbook distinguishes INFO from the no-plan WARNING, and
  the logger name because three `buildsmart.*` loggers share this handler.

This changes **nothing about what is logged**: no field is added, renamed or enriched, and
`preview_log.FIELDS` is untouched. The record that #214 built and #231 could not see is the same
record; this module is only the handler it was missing.

WHERE IT IS CALLED
------------------
`app/main.py`, at import, next to `load_dotenv()` — the module `uvicorn app.main:app` imports, so
the configuration exists however the server was started, with or without `--reload`, and without an
operator having to pass `--log-config`. Importing `app.main` twice (a reload, a test) configures
once: `configure()` is idempotent by the marker it puts on its own handler.
"""
from __future__ import annotations

import logging
import sys
from typing import TextIO

#: The application's own logger namespace. Every logger this application names for itself is a
#: child of it, and nothing else is, so this handler reaches our lines and no library's.
LOGGER_NAME = "buildsmart"

#: Level, name, message. See the module docstring for why each of the three, and why no timestamp.
FORMAT = "%(levelname)-8s %(name)s %(message)s"

#: Set on the handler this module installs, so a second call finds it instead of adding a second
#: handler — which would print every line twice under `--reload`.
_MARKER = "_buildsmart_log_output"


def installed(logger: logging.Logger | None = None) -> logging.Handler | None:
    """This module's handler on `logger`, or None. The idempotence check, and what a test asks."""
    target = logger if logger is not None else logging.getLogger(LOGGER_NAME)
    for handler in target.handlers:
        if getattr(handler, _MARKER, False):
            return handler
    return None


def configure(stream: TextIO | None = None) -> logging.Logger:
    """Send `buildsmart.*` records to `stream` (stderr) at INFO. Idempotent; returns the logger.

    Never raises: a server must not fail to start because its logging could not be set up.
    """
    logger = logging.getLogger(LOGGER_NAME)
    try:
        if installed(logger) is None:
            handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
            handler.setFormatter(logging.Formatter(FORMAT))
            setattr(handler, _MARKER, True)
            logger.addHandler(handler)
        # NOTSET would inherit the root's WARNING and drop #214's INFO line — the defect this
        # module closes is as much the level as the handler.
        if logger.level == logging.NOTSET or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
    except Exception:  # noqa: BLE001 - observability must never become the failure it reports
        pass
    return logger
