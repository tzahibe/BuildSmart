"""THE APPLICATION'S LOG LINES ARRIVE (Issue #233, ROOT #211).

#214 added one line per brain preview request and #211's risk register recorded the detection half
of risk 1 as closed. #231, proving the kill switch against a running server, found that the line
appeared nowhere: the application had no logging configuration at all, so under
`uvicorn app.main:app` the record reached the root logger, found no handler and was dropped.

**The tests here are necessary and are not what proves the fix.** A test that captures a record
proves emission, and emission was never the problem — `caplog` installs its own root handler, which
is precisely why #214's unit tests passed while a deployment showed nothing. The proof is a real
server's own captured output, in `docs/reports/architectural-brain/PREVIEW-logging-proof.md`. What
these tests pin is the configuration that proof depends on, so it cannot be removed silently:
one handler, on the namespace the application already uses, at INFO, idempotent, and installed by
the module uvicorn imports.
"""
from __future__ import annotations

import io
import logging

import pytest

from app.observability import log_output, preview_log


@pytest.fixture()
def captured():
    """`configure()` on the REAL `buildsmart` logger, writing to a buffer instead of stderr.

    The real logger name on purpose: the thing most worth pinning is that the namespace the
    handler is attached to is the one `preview_log` actually logs under. Whatever the surrounding
    test session had configured is put back afterwards.
    """
    logger = logging.getLogger(log_output.LOGGER_NAME)
    handlers, level = list(logger.handlers), logger.level
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    buffer = io.StringIO()
    log_output.configure(stream=buffer)
    yield buffer
    logger.handlers[:] = handlers
    logger.setLevel(level)


def test_the_namespace_is_the_one_the_application_already_logs_under():
    """Not a new convention: `buildsmart.*` is what every logger the application names for itself
    already is, so one handler reaches all of them and no library's."""
    assert log_output.LOGGER_NAME == "buildsmart"
    assert preview_log.LOGGER_NAME == "buildsmart.preview"
    assert preview_log.LOGGER_NAME.startswith(log_output.LOGGER_NAME + ".")


def test_configure_installs_exactly_one_stderr_handler_at_info():
    """stderr because that is where uvicorn's own `default` handler writes, so the preview's line
    lands in order among the access lines for the same requests. INFO because #214's line is INFO
    and the root's WARNING is what dropped it."""
    logger = logging.getLogger(log_output.LOGGER_NAME)
    handlers, level = list(logger.handlers), logger.level
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    try:
        import sys

        log_output.configure()
        handler = log_output.installed()
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stderr
        assert logger.level == logging.INFO
        assert logger.isEnabledFor(logging.INFO)
    finally:
        logger.handlers[:] = handlers
        logger.setLevel(level)


def test_configure_is_idempotent_because_reload_re_imports_the_module(captured):
    """`uvicorn --reload` re-imports `app.main` on every respawn. A second handler would print
    every line twice, which is how a log stops being read."""
    before = log_output.installed()
    log_output.configure(stream=io.StringIO())
    log_output.configure(stream=io.StringIO())
    logger = logging.getLogger(log_output.LOGGER_NAME)
    assert len([h for h in logger.handlers if h is log_output.installed()]) == 1
    assert log_output.installed() is before          # the first handler, still the only one
    preview_log.brain_request(engine="brain", sizer="exact", families=("band",), plan_sizer="exact")
    assert captured.getvalue().count("engine=brain") == 1


def test_a_served_request_line_arrives_whole_and_unchanged(captured):
    """The INFO case — the one that reached nothing before. The delivered text must contain the
    line `brain_request` returned, character for character: #233 changes whether a line arrives,
    never what it says."""
    line = preview_log.brain_request(
        engine="brain", sizer="exact", families=("band", "spine"), plan_sizer="exact",
        plan_family="spine", solves=14, plans=3, partis=8, seconds=24.1)
    out = captured.getvalue()
    assert line in out
    assert out.rstrip("\n").endswith(line)
    assert "INFO" in out and preview_log.LOGGER_NAME in out


def test_the_no_plan_warning_arrives_labelled_as_a_warning(captured):
    """Before #233 this line DID arrive — through `logging.lastResort`, which handles WARNING and
    above when no handler is found, and prints the bare message. So an operator saw an unlabelled
    line for a failed request and nothing at all for a healthy one. The level is in the format
    because the runbook distinguishes the two."""
    line = preview_log.brain_request(engine="brain", sizer="exact", families=("band",),
                                     code="BRAIN_NO_PLAN")
    out = captured.getvalue()
    assert line in out
    assert out.startswith("WARNING")
    assert "code=BRAIN_NO_PLAN" in out


def test_no_library_chatter_is_raised_with_it(captured):
    """The handler is on `buildsmart`, not the root, so this configuration cannot turn a third
    party's INFO logging into output an operator has to scroll past."""
    logging.getLogger("httpx").info("a library's own INFO line")
    logging.getLogger("openai").info("another one")
    assert captured.getvalue() == ""


def test_propagation_stays_on_so_caplog_still_captures(captured, caplog):
    """`caplog` captures at the root. #214's and #231's tests depend on that, so this module must
    not switch propagation off to avoid a duplicate it does not have under uvicorn."""
    logger = logging.getLogger(log_output.LOGGER_NAME)
    assert logger.propagate is True
    with caplog.at_level(logging.INFO, logger=preview_log.LOGGER_NAME):
        line = preview_log.brain_request(engine="brain", sizer="exact", families=("band",))
    assert line in captured.getvalue()                       # the handler
    assert any(line == r.message for r in caplog.records)    # and the root, still


def test_the_module_uvicorn_imports_is_what_configures_it():
    """`app/main.py`, at import — the one entry point the README documents
    (`uv run uvicorn app.main:app --reload --port 8000`), so an operator needs no `--log-config`
    and it works with or without `--reload`. If this ever stops being true, #231's finding is back.
    """
    import app.main  # noqa: F401 - imported for its side effect, which is the claim

    assert log_output.installed() is not None
    assert logging.getLogger(log_output.LOGGER_NAME).isEnabledFor(logging.INFO)


def test_configure_never_raises_even_on_an_unusable_stream():
    """A server must not fail to start because its logging could not be set up."""
    class Hostile:
        def write(self, _):
            raise OSError("no")

        def flush(self):
            raise OSError("no")

    logger = logging.getLogger(log_output.LOGGER_NAME)
    handlers, level = list(logger.handlers), logger.level
    logger.handlers.clear()
    try:
        assert log_output.configure(stream=Hostile()) is logger   # configuring is fine
        preview_log.brain_request(engine="brain", sizer="exact", families=())  # and emitting
    finally:
        logger.handlers[:] = handlers
        logger.setLevel(level)
