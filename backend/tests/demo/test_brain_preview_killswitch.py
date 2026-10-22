"""THE EMERGENCY DISABLE, which had to actually work (Issue #231, child of ROOT #211).

#212 read both halves of the gate from the environment on every request and PR #224's text
concluded that blanking either one closes the preview on the next request. #214 tested that against
a running server and it is false where it matters:

* blanking both lines in `.env` left the preview fully open on the same pid — a worker does not
  re-read `.env`, and a process's `os.environ` cannot be changed from outside the process;
* `touch app/main.py` is what closed it, and only because `--reload` respawns the worker;
* with the variables **exported in the starting shell**, removing them from `.env` *and* forcing a
  reload still left the preview open: `load_dotenv()` does not override, and a respawned worker
  inherits its parent's environment. Only stopping the process worked — an owner action, and the
  opposite of "immediately, without a deployment".

So every test in this file sets `BRAIN_PREVIEW_ENABLED` and `BRAIN_PREVIEW_TOKEN` in `os.environ`
and leaves them there. That is not a weaker version of the exported case, it IS the exported case:
an exported variable reaches a Python process as an entry in `os.environ` and nothing else, and
`monkeypatch.setenv` produces the identical entry. The kill file has to beat it with the flag still
truthy and still set, which is what each test asserts.

Everything goes through the real route, with `service.run_brain` spied exactly as in
`test_brain_preview_gate.py` (which this file imports its harness from, so the two cannot drift):
reaching the brain is observable as `BRAIN_NO_PLAN` in milliseconds, and the gate's refusal is a
different answer entirely.
"""
from __future__ import annotations

import logging
import os
import stat

import pytest

from app.demo import preview_gate
from app.demo.router import ENGINE_BRAIN, ENGINE_E1_REAR_BAND
from app.observability import failure_log

from tests.demo.test_brain_preview_gate import (  # noqa: F401 - fixtures are used by name
    TOKEN,
    _open,
    _post,
    _refusal_shape,
    brain_spy,
    clean_env,
    client,
    in_this_process,
)


@pytest.fixture()
def kill_file(tmp_path, monkeypatch):
    """The kill switch, pointed somewhere this test owns.

    The built-in path is `backend/DISABLE_BRAIN_PREVIEW`, in the checkout. A test must not create
    that: a crashed test run would leave the preview disabled for every later run and for the
    developer's own server. `BRAIN_PREVIEW_KILL_FILE` adds a location, so the tests use one under
    `tmp_path` and `test_configuration_can_add_a_kill_location_but_never_move_the_built_in_one`
    pins the part that cannot be moved.
    """
    path = tmp_path / "DISABLE_BRAIN_PREVIEW"
    monkeypatch.setenv(preview_gate.KILL_FILE_ENV, str(path))
    return path


def _reaches_the_brain(client, brain_spy) -> bool:
    """One authorized request, answered by whether it got through to the brain."""
    before = len(brain_spy)
    response = _post(client, ENGINE_BRAIN, token=TOKEN)
    got_through = len(brain_spy) > before
    if got_through:
        assert response.json()["detail"]["code"] == "BRAIN_NO_PLAN"
    else:
        assert response.status_code == 422
    return got_through


# ============================================ AC-1: the kill file beats an exported, truthy flag

def test_the_kill_file_closes_the_preview_on_the_next_request_in_the_same_process(
        client, brain_spy, monkeypatch, kill_file):
    """AC-1. Two requests, one process, one set of imported modules. Between them: a file is
    created. Nothing is restarted, nothing is reloaded, no variable is unset — `BRAIN_PREVIEW_
    ENABLED` is still `1` and still in `os.environ` when the second request is refused."""
    _open("1", TOKEN, monkeypatch)
    assert _reaches_the_brain(client, brain_spy)

    kill_file.write_text("")                                    # the emergency disable

    assert os.environ[preview_gate.FLAG_ENV] == "1", "the flag must still be on and exported"
    assert not _reaches_the_brain(client, brain_spy), "a request got through after the kill switch"


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "Yes", "on", " on "])
def test_no_truthy_value_of_the_flag_survives_the_kill_file(flag, clean_env, monkeypatch,
                                                            kill_file):
    """Every spelling #224 documents as ON is OFF with the kill file there. The gate's own
    `enabled()`, so the claim is about the decision and not about one route."""
    monkeypatch.setenv(preview_gate.FLAG_ENV, flag)
    assert preview_gate.enabled() is True
    kill_file.write_text("")
    assert preview_gate.enabled() is False
    assert preview_gate.authorized(TOKEN) is False


def test_the_kill_file_needs_no_cooperation_from_the_environment_that_enabled_the_preview(
        clean_env, monkeypatch, kill_file):
    """#231's point 1, stated as the gate sees it: the flag is set, the token is set, the families
    and sizer are set, and the preview is still closed. Nothing had to be unset, which is the whole
    reason this mechanism exists — the exported variables could not be."""
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    monkeypatch.setenv(preview_gate.TOKEN_ENV, TOKEN)
    monkeypatch.setenv(preview_gate.FAMILIES_ENV, "band")
    monkeypatch.setenv(preview_gate.SIZER_ENV, "exact")
    kill_file.write_text("")
    assert preview_gate.authorized(TOKEN) is False
    # and the configuration the environment DID set is still exactly what it set — the kill switch
    # closes the door, it does not quietly rewrite the room behind it.
    assert preview_gate.families() == ("band",)
    assert os.environ[preview_gate.TOKEN_ENV] == TOKEN


def test_an_empty_kill_file_is_enough_and_so_is_a_directory_and_a_dangling_symlink(
        clean_env, monkeypatch, tmp_path):
    """What an operator can create under pressure, with whatever tool is to hand. The NAME is the
    signal; nothing reads the contents, so there is nothing to get wrong inside it."""
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    for name, make in (("empty", lambda p: p.write_text("")),
                       ("text", lambda p: p.write_text("closed at 02:14, see #231\n")),
                       ("dir", lambda p: p.mkdir()),
                       ("dangling", lambda p: p.symlink_to(tmp_path / "nothing-here"))):
        path = tmp_path / f"kill-{name}"
        monkeypatch.setenv(preview_gate.KILL_FILE_ENV, str(path))
        assert preview_gate.enabled() is True, f"{name}: not created yet"
        make(path)
        assert preview_gate.enabled() is False, f"{name} did not close the preview"


def test_both_gated_engines_are_closed_by_the_one_kill_file(client, brain_spy, monkeypatch,
                                                            kill_file):
    """`e1_rear_band` is gated by the same `authorized()` call, so it is killed by the same file.
    One mechanism, one place, both previews."""
    _open("1", TOKEN, monkeypatch)
    kill_file.write_text("")
    for engine in (ENGINE_BRAIN, ENGINE_E1_REAR_BAND):
        assert _post(client, engine, token=TOKEN).status_code == 422
    assert not brain_spy


def test_the_streaming_endpoint_is_closed_by_the_kill_file_too(client, brain_spy, monkeypatch,
                                                               kill_file):
    """The second route resolves the engine through the same `_resolve_engine`; this pins that the
    kill switch did not get added to one call site only."""
    _open("1", TOKEN, monkeypatch)
    kill_file.write_text("")
    response = client.post(f"/projects/GATE/design/demo/stream?engine={ENGINE_BRAIN}",
                           headers={preview_gate.TOKEN_HEADER: TOKEN})
    assert response.status_code == 422
    assert not brain_spy


# ============================================================ AC-2: removing it re-enables, same process

def test_removing_the_kill_file_re_enables_the_preview_on_the_next_request(
        client, brain_spy, monkeypatch, kill_file):
    """AC-2. The switch is a switch, not a latch: nothing is remembered, so an operator who closed
    the preview can re-open it without a restart either. Three requests, one process."""
    _open("1", TOKEN, monkeypatch)
    assert _reaches_the_brain(client, brain_spy)

    kill_file.write_text("")
    assert not _reaches_the_brain(client, brain_spy)

    kill_file.unlink()
    assert _reaches_the_brain(client, brain_spy), "removing the kill file did not re-open it"


def test_nothing_caches_the_kill_decision(clean_env, monkeypatch, kill_file):
    """Resolved per call means per call. Ten flips, no import, no restart, and the answer tracks
    the filesystem every time."""
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    for _ in range(5):
        kill_file.write_text("")
        assert preview_gate.enabled() is False
        kill_file.unlink()
        assert preview_gate.enabled() is True


def test_removing_the_kill_file_cannot_re_open_a_preview_the_flag_also_closed(
        client, brain_spy, monkeypatch, kill_file):
    """The kill switch overrides the flag in the closing direction only. Deleting the file does not
    grant anything: a preview with no flag and no token stays shut."""
    _open(None, None, monkeypatch)
    kill_file.write_text("")
    assert not _reaches_the_brain(client, brain_spy)
    kill_file.unlink()
    assert not _reaches_the_brain(client, brain_spy)


# ======================================================================= AC-3: fail closed on ambiguity

def test_a_kill_path_that_cannot_be_read_closes_the_preview(clean_env, monkeypatch, tmp_path):
    """AC-3. A directory with no execute permission: `lstat` on a path inside it raises
    `PermissionError`, so the check cannot tell whether the kill file is there. It refuses.

    This is the case a convenience existence check gets wrong. `Path.exists()` swallows the
    `OSError` and answers False — "keep serving" — which is the one answer an off switch must never
    give, and the reason `killed()` uses `os.lstat` and catches rather than asks.
    """
    locked = tmp_path / "locked"
    locked.mkdir()
    target = locked / "DISABLE_BRAIN_PREVIEW"
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    monkeypatch.setenv(preview_gate.KILL_FILE_ENV, str(target))
    assert preview_gate.enabled() is True                        # readable: absent means absent
    locked.chmod(0o000)
    try:
        if os.geteuid() == 0:                                    # pragma: no cover - not CI
            pytest.skip("root reads everything; the permission case cannot be constructed")
        with pytest.raises(PermissionError):
            os.lstat(target)                                     # the ambiguity, demonstrated
        assert preview_gate.killed() is True
        assert preview_gate.enabled() is False
        assert preview_gate.authorized(TOKEN) is False
    finally:
        locked.chmod(stat.S_IRWXU)


@pytest.mark.parametrize("path, why", [
    ("/dev/null/DISABLE_BRAIN_PREVIEW", "a path whose parent is a device, not a directory"),
    ("/proc/self/nonexistent-brain-preview-kill", "a pseudo-filesystem that may answer oddly"),
])
def test_an_unusable_kill_path_closes_the_preview(path, why, clean_env, monkeypatch):
    """Anything that is not a plain `FileNotFoundError` is treated as "cannot decide" and refuses.
    An operator who mis-set the variable gets a closed preview and a runbook line, not a preview
    that kept serving because its off switch was broken."""
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    monkeypatch.setenv(preview_gate.KILL_FILE_ENV, path)
    if not preview_gate.killed():                                # pragma: no cover - platform
        pytest.skip(f"{why}: this platform reports plain FileNotFoundError")
    assert preview_gate.enabled() is False


def test_any_exception_at_all_inside_the_check_closes_the_preview(clean_env, monkeypatch):
    """The general claim, not the two constructible cases: whatever `lstat` raises — `OSError`,
    `ValueError` on a path with a NUL in it, a `TypeError` on something that is not a path, and
    even a `KeyboardInterrupt` arriving mid-check — the answer is "disabled"."""
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    for error in (OSError(5, "I/O error"), ValueError("embedded null byte"),
                  TypeError("not a path"), MemoryError(), KeyboardInterrupt(),
                  RuntimeError("something nobody predicted")):
        monkeypatch.setattr(preview_gate.os, "lstat",
                            lambda _path, _e=error: (_ for _ in ()).throw(_e))
        assert preview_gate.killed() is True, f"{type(error).__name__} did not close the preview"
        assert preview_gate.enabled() is False
        assert preview_gate.authorized(TOKEN) is False


def test_configuration_can_add_a_kill_location_but_never_move_the_built_in_one(clean_env,
                                                                               monkeypatch):
    """The asymmetry that makes this independent of the enabling environment.

    `BRAIN_PREVIEW_KILL_FILE` may point somewhere else — a deployment whose `backend/` is read-only
    needs that — but `DEFAULT_KILL_FILE` is checked whatever it says, and blanking or deleting the
    variable takes no kill location away. A switch whose location the environment that opened the
    preview could choose would need that environment's cooperation, which is exactly the property
    #214 found missing.
    """
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    assert preview_gate.kill_file_paths() == (preview_gate.DEFAULT_KILL_FILE,)
    for value in ("", "   ", preview_gate.DEFAULT_KILL_FILE):
        monkeypatch.setenv(preview_gate.KILL_FILE_ENV, value)
        assert preview_gate.kill_file_paths() == (preview_gate.DEFAULT_KILL_FILE,), value
    monkeypatch.setenv(preview_gate.KILL_FILE_ENV, "/tmp/elsewhere")
    assert preview_gate.kill_file_paths() == (preview_gate.DEFAULT_KILL_FILE, "/tmp/elsewhere")


def test_the_built_in_kill_path_is_the_one_the_runbook_names(clean_env):
    """It is derived from the module's own location, not from the working directory, so the path an
    operator is told is the path the process checks however it was started — `uvicorn` from
    `backend/`, a supervisor from `/`, a test runner from the repository root."""
    assert os.path.isabs(preview_gate.DEFAULT_KILL_FILE)
    assert os.path.basename(preview_gate.DEFAULT_KILL_FILE) == "DISABLE_BRAIN_PREVIEW"
    parent = os.path.dirname(preview_gate.DEFAULT_KILL_FILE)
    assert os.path.basename(parent) == "backend"
    assert os.path.isfile(os.path.join(parent, "app", "demo", "preview_gate.py"))
    assert not os.path.exists(preview_gate.DEFAULT_KILL_FILE), (
        "the checkout's own kill file exists — a crashed run left it behind; delete it")


# ========================================== AC-4: the refusal and the timing are the same refusal

def test_a_killed_preview_refuses_exactly_as_an_unknown_engine_does(client, brain_spy, monkeypatch,
                                                                    kill_file):
    """AC-4. The kill switch introduces no code, no message and no status of its own. A killed
    preview is a preview that does not exist, which is the same claim #212 made for a closed one:
    the refusal cannot tell a prober that there is something here to come back for."""
    _open("1", TOKEN, monkeypatch)
    kill_file.write_text("")
    unknown = _post(client, "banana")
    for engine in (ENGINE_BRAIN, ENGINE_E1_REAR_BAND):
        killed = _post(client, engine, token=TOKEN)
        assert _refusal_shape(killed, engine) == _refusal_shape(unknown, "banana")
        # the message quotes what the caller itself asked for (that is what `_refusal_shape`
        # blanks); what it must never do is LIST a gated engine as one that exists.
        after = killed.json()["detail"].split("expected", 1)[1]
        assert ENGINE_BRAIN not in after and ENGINE_E1_REAR_BAND not in after
    assert not brain_spy


def test_the_killed_refusal_is_identical_to_the_flag_off_refusal(client, monkeypatch, kill_file):
    """Byte-for-byte, including the engine name this time, because both requests ask for the same
    one: an operator who used the kill switch and an operator who unset the flag leave a prober
    looking at literally the same response. The kill switch is not detectable from outside."""
    _open("1", TOKEN, monkeypatch)
    kill_file.write_text("")
    killed = _post(client, ENGINE_BRAIN, token=TOKEN)
    kill_file.unlink()
    monkeypatch.delenv(preview_gate.FLAG_ENV)
    flag_off = _post(client, ENGINE_BRAIN, token=TOKEN)
    assert (killed.status_code, killed.text) == (flag_off.status_code, flag_off.text)


def test_the_kill_check_runs_for_every_engine_so_it_is_not_a_timing_oracle(clean_env, monkeypatch,
                                                                           kill_file):
    """No new oracle. `_resolve_engine` consults `authorized()` FIRST and unconditionally — #212's
    invariant — so the `lstat` happens for `?engine=banana` and for `?engine=production` exactly as
    it happens for `?engine=brain`. Counted, rather than timed: a wall-clock comparison on a
    loaded CI box measures the box, and the structural claim is the one that matters."""
    from app.demo import router

    calls: list[str] = []
    real = preview_gate.os.lstat
    monkeypatch.setattr(preview_gate.os, "lstat",
                        lambda path: (calls.append(str(path)), real(path))[1])
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    monkeypatch.setenv(preview_gate.TOKEN_ENV, TOKEN)
    for engine in (None, "production", "concept_engine_v2", "banana", ENGINE_BRAIN,
                   ENGINE_E1_REAR_BAND, ""):
        before = len(calls)
        try:
            router._resolve_engine(engine, TOKEN)
        except Exception:                     # noqa: BLE001 - the refusal is the expected answer
            pass
        assert len(calls) > before, f"?engine={engine!r} skipped the kill check"
    assert set(calls) == {preview_gate.DEFAULT_KILL_FILE, str(kill_file)}


# ============================================================= AC-7: the kill switch writes nothing

def test_the_kill_switch_writes_no_log_line_and_leaks_no_secret(client, brain_spy, monkeypatch,
                                                                kill_file, caplog):
    """AC-7, for the path this issue added. The gate holds the secret and must stay write-free, so
    a killed request must not produce a line of its own — and the refusal it does produce must not
    carry the token, the kill path, or the fact that a kill switch exists."""
    _open("1", TOKEN, monkeypatch)
    kill_file.write_text("")
    with caplog.at_level(logging.DEBUG):
        response = _post(client, ENGINE_BRAIN, token=TOKEN)
    assert response.status_code == 422
    text = caplog.text + "\n" + str(failure_log.read_all()) + "\n" + response.text
    assert TOKEN not in text
    for secret in (str(kill_file), preview_gate.DEFAULT_KILL_FILE, "DISABLE_BRAIN_PREVIEW",
                   preview_gate.KILL_FILE_ENV, "kill"):
        assert secret not in response.text, f"the refusal mentions {secret!r}"
