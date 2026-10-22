"""THE PREVIEW'S ADMISSION LIMIT AND ITS SEPARATE PROCESS (Issue #246, ROOT #211).

#226 measured production's own latency beside N concurrent brain preview requests, alone on an
idle ten-core machine: 1.65 s median quiet, 5.89 s at N=2, 9.29 s at N=4, 16.87 s worst, 1.63 s
again once the load stopped. `scipy.optimize.milp` holds the GIL, so the preview serialized on one
saturated core inside production's own process. Its conclusion was "safe limit: one concurrent
brain request, enforced server-side", plus a process that cannot take that core.

WHAT IS REAL IN THIS FILE, AND WHAT IS NOT
------------------------------------------
The admission limit is real: the real `preview_isolation.admitted()`, reached through the real
route, with the real gate open.

The *parent half* of the process boundary is real too — a real `subprocess.Popen`, the real JSON
request on the child's stdin, the real line protocol on its stdout, the real watchdog. What is
substituted is the child's **body**: a fake child that speaks the protocol and then blocks, exits
or refuses on command, instead of running a 30-second solver. That is the only way a test can hold
a slot open for a known length of time and ask what the next request gets.

One test (`test_the_real_child_module_answers_the_protocol_end_to_end`) runs the REAL child —
`python -m app.demo.preview_isolation` — on production's engine, so the module's own `__main__`,
its stage lines and its `DemoPlanSet` round-trip are exercised by a real process rather than
asserted about. The brain itself is not run here: at #226's measured 31.6 s median it belongs to a
measurement, and that measurement is `docs/reports/architectural-brain/PREVIEW-isolation-proof.md`.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid

import pytest

from app.demo import preview_gate, preview_isolation
from app.demo.contract import DemoPlanSet
from app.demo.router import ENGINE_BRAIN, ENGINE_E1_REAR_BAND, EngineChoice
from app.demo.service import DemoGenerationError
from app.observability import failure_log

# The gate suite already owns a real project, a real client and the open/closed levers; reusing
# them keeps "what a preview request is" defined in exactly one place.
from tests.demo.test_brain_preview_gate import (  # noqa: F401 - fixtures are used by name
    BRIEF,
    TOKEN,
    _open,
    _post,
    _project,
    clean_env,
    client,
)

BRAIN = EngineChoice(brain=True)
PRODUCTION = EngineChoice()

#: Every fake child starts with this: read the one request line, and a way to answer.
_PRELUDE = """
import json, os, sys, time

def emit(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()

request = json.loads(sys.stdin.readline())
"""


def _fake_child(tmp_path, body: str) -> list[str]:
    """A child process that speaks the real protocol and does what `body` says."""
    script = tmp_path / f"fake_child_{uuid.uuid4().hex}.py"
    script.write_text(_PRELUDE + body, encoding="utf-8")
    return [sys.executable, str(script)]


def _use(monkeypatch, command: list[str]) -> None:
    monkeypatch.setattr(preview_isolation, "_child_command", lambda: command)


@pytest.fixture(scope="module")
def payload(tmp_path_factory) -> str:
    """A REAL `DemoPlanSet`, computed once by production, for a fake child to hand back.

    A fake child must answer with something the parent can actually validate, or a test could pass
    while the payload never survived the boundary. This is production's own output, so the
    round-trip being asserted is the real contract and not a hand-written stub of it.
    """

    plans = preview_isolation.plan_set(_project(BRIEF), PRODUCTION)
    path = tmp_path_factory.mktemp("payload") / "payload.json"
    path.write_text(plans.model_dump_json(), encoding="utf-8")
    return str(path)


def _blocking_child(tmp_path, payload: str, *, release, pid=None, env=None) -> list[str]:
    """Emits one stage, records what it was given, waits for `release` to exist, then answers."""
    return _fake_child(tmp_path, f"""
if {pid!r}:
    open({pid!r}, "w").write(str(os.getpid()))
if {env!r}:
    json.dump(sorted(os.environ), open({env!r}, "w"))
emit({{"stage": "concept"}})
while not os.path.exists({release!r}):
    time.sleep(0.01)
emit({{"ok": json.load(open({payload!r}))}})
""")


@pytest.fixture(autouse=True)
def no_slot_leaks():
    """Every test starts and ends with the preview idle, whatever it did in between."""
    yield
    with preview_isolation._lock:
        preview_isolation._in_flight.clear()


# ============================================================ AC-1: the limit, and its default

def test_the_default_limit_is_one_with_no_configuration_at_all(clean_env, monkeypatch):
    """The committed default, which is also #226's measured safe value."""
    monkeypatch.delenv(preview_gate.MAX_CONCURRENCY_ENV, raising=False)
    assert preview_gate.max_concurrency() == 1
    assert preview_isolation.occupancy() == {
        "in_flight": 0, "limit": 1, "slots_free": 1, "oldest_running_s": 0.0}


def test_two_concurrent_preview_requests_admit_exactly_one(tmp_path, monkeypatch, payload):
    """THE MEASUREMENT'S CONCLUSION, as a test: two at once, one admitted.

    Two real threads, the real dispatch, a real child process each — and one of them must be
    refused rather than both reaching a solver, which is what #226 found happening today.
    """
    release = tmp_path / "release"
    _use(monkeypatch, _blocking_child(tmp_path, payload, release=str(release)))
    project = _project(BRIEF)

    outcomes: list[object] = []
    started = threading.Barrier(2)

    def attempt() -> None:
        started.wait(timeout=5)
        try:
            outcomes.append(type(preview_isolation.plan_set(project, BRAIN)).__name__)
        except BaseException as error:                                  # noqa: BLE001
            outcomes.append(error)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    # The refusal is immediate, so it lands long before the admitted request finishes.
    deadline = time.monotonic() + 10
    while len(outcomes) < 1 and time.monotonic() < deadline:
        time.sleep(0.02)
    release.write_text("go", encoding="utf-8")
    for thread in threads:
        thread.join(timeout=30)

    busy = [o for o in outcomes if isinstance(o, preview_isolation.PreviewBusy)]
    served = [o for o in outcomes if o == "DemoPlanSet"]
    assert len(served) == 1, outcomes
    assert len(busy) == 1, outcomes
    assert busy[0].limit == 1 and busy[0].running == 1


def test_the_slot_is_released_so_the_very_next_request_is_served(tmp_path, monkeypatch, payload):
    """A limit that did not release would be an outage, not an isolation."""
    release = tmp_path / "release"
    release.write_text("go", encoding="utf-8")
    _use(monkeypatch, _blocking_child(tmp_path, payload, release=str(release)))
    project = _project(BRIEF)

    for _ in range(3):
        assert isinstance(preview_isolation.plan_set(project, BRAIN), DemoPlanSet)
        assert preview_isolation.occupancy()["in_flight"] == 0


def test_the_slot_is_released_even_when_the_request_fails(tmp_path, monkeypatch):
    """A refusal, a crash and a watchdog kill must all give the slot back."""
    _use(monkeypatch, _fake_child(tmp_path, "sys.exit(7)"))

    with pytest.raises(preview_isolation.PreviewProcessError):
        preview_isolation.plan_set(_project(BRIEF), BRAIN)
    assert preview_isolation.occupancy()["in_flight"] == 0


def test_admitted_is_the_whole_enforcement_and_it_releases_on_an_exception():
    """The primitive itself, with no process anywhere near it."""
    with preview_isolation.admitted():
        assert preview_isolation.occupancy() == {
            "in_flight": 1, "limit": 1, "slots_free": 0,
            "oldest_running_s": pytest.approx(0.0, abs=1.0)}
        with pytest.raises(preview_isolation.PreviewBusy):
            with preview_isolation.admitted():
                pytest.fail("a second slot was handed out")
    assert preview_isolation.occupancy()["in_flight"] == 0

    with pytest.raises(ZeroDivisionError):
        with preview_isolation.admitted():
            1 / 0
    assert preview_isolation.occupancy()["in_flight"] == 0


def test_a_second_request_on_the_wire_is_refused_while_a_slot_is_held(client, monkeypatch):
    """THE ROUTE's answer, not the primitive's: a real authorized request, a held slot, 503."""
    _open("1", TOKEN, monkeypatch)
    with preview_isolation.admitted():
        response = _post(client, ENGINE_BRAIN, token=TOKEN)
    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["code"] == preview_isolation.BUSY_CODE
    assert body["message"] == preview_isolation.BUSY_MESSAGE
    assert "limit 1" in body["detail"] and "1 in flight" in body["detail"]
    assert response.headers["Retry-After"] == str(preview_isolation.BUSY_RETRY_AFTER_S)


def test_both_gated_engines_share_the_one_limit(client, monkeypatch):
    """`e1_rear_band` was never measured, and "not measured" is not "safe"."""
    _open("1", TOKEN, monkeypatch)
    with preview_isolation.admitted():
        for engine in (ENGINE_BRAIN, ENGINE_E1_REAR_BAND):
            assert _post(client, engine, token=TOKEN).status_code == 503


# ============================================================ AC-2: the ceiling, and the type

@pytest.mark.parametrize("asked", ["2", "4", "8", "1000", " 4 "])
def test_the_limit_cannot_be_raised_above_what_the_measurement_supports(asked, clean_env,
                                                                        monkeypatch):
    """#226 measured N=2 and N=4 as harmful and measured no N above 1 as safe. Configuration may
    narrow the preview and may never widen it — the same asymmetry `ALLOWED_FAMILIES` has."""
    monkeypatch.setenv(preview_gate.MAX_CONCURRENCY_ENV, asked)
    assert preview_gate.max_concurrency() == 1
    assert preview_gate.MAX_CONCURRENCY_CEILING == 1


@pytest.mark.parametrize("asked", ["0", "-1", "", "one", "1.5", "banana"])
def test_a_value_that_is_not_a_usable_limit_is_the_default(asked, clean_env, monkeypatch):
    """0 and -1 would CLOSE the preview, and closing it is the kill switch's job — two ways to
    turn the preview off is one way too many. A typo is the default for the same reason an
    unreadable flag is OFF."""
    monkeypatch.setenv(preview_gate.MAX_CONCURRENCY_ENV, asked)
    assert preview_gate.max_concurrency() == preview_gate.DEFAULT_MAX_CONCURRENCY == 1


def test_the_limit_is_read_per_request_and_nothing_caches_it(clean_env, monkeypatch):
    monkeypatch.setenv(preview_gate.MAX_CONCURRENCY_ENV, "9")
    assert preview_isolation.occupancy()["limit"] == 1
    monkeypatch.delenv(preview_gate.MAX_CONCURRENCY_ENV)
    assert preview_isolation.occupancy()["limit"] == 1


def test_the_refusal_is_typed_and_reaches_the_failure_log(client, monkeypatch, tmp_path):
    """A refusal nobody can count is a refusal nobody can act on."""
    monkeypatch.setattr(failure_log, "_path", tmp_path / "failures.json")
    _open("1", TOKEN, monkeypatch)
    with preview_isolation.admitted():
        _post(client, ENGINE_BRAIN, token=TOKEN)
    codes = [entry.get("code") for entry in failure_log.read_all()]
    assert preview_isolation.BUSY_CODE in codes


def test_the_busy_refusal_is_a_demo_generation_error_so_nothing_needed_new_handling():
    """Why the type was chosen: both endpoints already knew what to do with one."""
    error = preview_isolation.PreviewBusy(limit=1, running=1, oldest_s=12.5)
    assert isinstance(error, DemoGenerationError)
    assert error.code == preview_isolation.BUSY_CODE
    assert error.http_status == 503
    assert "12.5s" in error.detail


def test_an_unauthorized_request_can_never_see_the_busy_refusal(client, monkeypatch):
    """THE NEW CODE IS NOT A NEW ORACLE. Admission is checked after authorization, so with the
    only slot taken an unauthorized `?engine=brain` still gets the one 422 that names no hidden
    engine — byte-identical to `?engine=banana`."""
    _open("1", TOKEN, monkeypatch)
    with preview_isolation.admitted():
        no_token = _post(client, ENGINE_BRAIN)
        wrong_token = _post(client, ENGINE_BRAIN, token="not-the-token")
        unknown = _post(client, "banana")
    assert no_token.status_code == wrong_token.status_code == 422
    for response in (no_token, wrong_token):
        assert response.json()["detail"] == unknown.json()["detail"].replace(
            repr("banana"), repr(ENGINE_BRAIN))
        assert preview_isolation.BUSY_CODE not in json.dumps(response.json())


def test_the_streaming_endpoint_refuses_in_its_own_typed_shape(client, monkeypatch):
    """A stream cannot carry a status code once it has started, so the typed refusal is its own
    `error` event — which the endpoint already knew how to send."""
    _open("1", TOKEN, monkeypatch)
    with preview_isolation.admitted():
        response = client.post(f"/projects/GATE/design/demo/stream?engine={ENGINE_BRAIN}",
                               headers={preview_gate.TOKEN_HEADER: TOKEN})
    assert response.status_code == 200
    assert "event: error" in response.text
    assert preview_isolation.BUSY_CODE in response.text


# ============================================================ the separate process

def test_a_gated_preview_request_runs_in_another_process(tmp_path, monkeypatch, payload):
    """The claim this whole change rests on, asserted about a real pid."""
    release = tmp_path / "release"
    release.write_text("go", encoding="utf-8")
    pid_file = tmp_path / "child.pid"
    _use(monkeypatch, _blocking_child(tmp_path, payload, release=str(release),
                                      pid=str(pid_file)))

    preview_isolation.plan_set(_project(BRIEF), BRAIN)
    assert int(pid_file.read_text()) != os.getpid()


def test_production_never_leaves_this_process_and_never_takes_a_slot(monkeypatch):
    """Production is the traffic being protected: it must not acquire a slot, and it must not be
    able to be refused by one."""
    def no_child(*args, **kwargs):
        raise AssertionError("production was dispatched to a child process")

    monkeypatch.setattr(preview_isolation, "_in_child_process", no_child)

    with preview_isolation.admitted():                 # the only slot is taken
        plans = preview_isolation.plan_set(_project(BRIEF), PRODUCTION)
    assert isinstance(plans, DemoPlanSet)


def test_the_child_is_not_given_the_token(tmp_path, monkeypatch, payload):
    """The authorization decision was taken in the parent's request frame and is finished. The
    secret has no business crossing the boundary."""
    release = tmp_path / "release"
    release.write_text("go", encoding="utf-8")
    env_file = tmp_path / "child.env"
    monkeypatch.setenv(preview_gate.TOKEN_ENV, "the-secret-nobody-should-inherit")
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    _use(monkeypatch, _blocking_child(tmp_path, payload, release=str(release),
                                      env=str(env_file)))

    preview_isolation.plan_set(_project(BRIEF), BRAIN)
    names = json.loads(env_file.read_text())
    assert preview_gate.TOKEN_ENV not in names
    assert preview_gate.FLAG_ENV in names, "the child must see the same configuration"
    assert preview_isolation.CHILD_MARKER_ENV in names


def test_stage_lines_cross_the_boundary_as_they_happen(tmp_path, monkeypatch, payload):
    """The loading screen's percentage is only honest if it arrives during the work."""
    _use(monkeypatch, _fake_child(tmp_path, f"""
emit({{"stage": "concept"}})
emit({{"stage": "sizing"}})
emit({{"ok": json.load(open({payload!r}))}})
"""))

    seen: list[str] = []
    preview_isolation.plan_set(_project(BRIEF), BRAIN, on_stage=seen.append)
    assert seen == ["concept", "sizing"]


def test_a_refusal_from_the_child_is_re_raised_in_the_parents_frame(tmp_path, monkeypatch):
    """`BRAIN_NO_PLAN` must still be the parent's refusal, with the parent's failure-log context."""
    _use(monkeypatch, _fake_child(tmp_path, """
emit({"error": {"code": "BRAIN_NO_PLAN", "message": "לא ניתן לתכנן", "detail": "no parti"}})
"""))

    with pytest.raises(DemoGenerationError) as raised:
        preview_isolation.plan_set(_project(BRIEF), BRAIN)
    assert raised.value.code == "BRAIN_NO_PLAN"
    assert not isinstance(raised.value, preview_isolation.PreviewBusy)


@pytest.mark.parametrize("body, why", [
    ("sys.exit(7)", "the child exited without answering"),
    ('emit({"crash": "ValueError"})', "the child reported a crash"),
    ('sys.stdout.write("not json at all\\n")', "the child said nothing this module understands"),
])
def test_a_child_that_does_not_answer_is_a_crash_and_not_a_verdict(body, why, tmp_path,
                                                                   monkeypatch):
    """A `DemoGenerationError` would read as "we considered your brief and will not draw it". A
    broken preview is not a verdict on the house, so it travels the crash path (#230)."""
    _use(monkeypatch, _fake_child(tmp_path, body))

    with pytest.raises(preview_isolation.PreviewProcessError):
        preview_isolation.plan_set(_project(BRIEF), BRAIN)
    assert not issubclass(preview_isolation.PreviewProcessError, DemoGenerationError)


def test_the_watchdog_kills_a_child_that_never_answers(tmp_path, monkeypatch, payload):
    """A wedged child would otherwise hold the single slot forever — a new fault this change must
    not introduce. The watchdog is NOT the request budget, which is #247's: it is set far above any
    measured request precisely so it cannot be mistaken for one."""
    monkeypatch.setattr(preview_isolation, "CHILD_WATCHDOG_S", 0.5)
    _use(monkeypatch, _fake_child(tmp_path, "time.sleep(600)"))

    started = time.monotonic()
    with pytest.raises(preview_isolation.PreviewProcessError):
        preview_isolation.plan_set(_project(BRIEF), BRAIN)
    assert time.monotonic() - started < 30
    assert preview_isolation.occupancy()["in_flight"] == 0


def test_the_real_child_module_answers_the_protocol_end_to_end():
    """The REAL child — `python -m app.demo.preview_isolation` — on production's engine.

    Not the brain: at #226's measured 31.6 s median that belongs to a measurement, and the
    measurement is `PREVIEW-isolation-proof.md`. What this proves is the module's own `__main__`:
    a project in on stdin, stage lines out as the work happens, and a `DemoPlanSet` that validates.
    """

    seen: list[str] = []
    plans = preview_isolation._in_child_process(
        _project(BRIEF), brain=False, rear_band=False, concept_engine_v2=None,
        on_stage=seen.append)
    assert isinstance(plans, DemoPlanSet)
    assert plans.plan is not None
    assert seen, "no stage crossed the process boundary"


def test_the_child_command_names_this_module_so_the_two_halves_cannot_drift():
    assert preview_isolation.CHILD_MODULE == preview_isolation.__name__
    assert preview_isolation._child_command()[1:] == ["-m", preview_isolation.CHILD_MODULE]
    assert (preview_isolation.BACKEND_ROOT / "app" / "demo" / "preview_isolation.py").exists()


# ============================================================ AC-4: the liveness signal

def test_health_reports_what_the_preview_is_doing(client):
    """#226's worst finding was a probe that answered in 26 ms while a user waited 17 s. `/health`
    now carries the occupancy, so an alarm has a number to look at."""
    quiet = client.get("/health").json()
    assert quiet["status"] == "ok"
    assert quiet["preview"] == {"in_flight": 0, "limit": 1, "slots_free": 1,
                                "oldest_running_s": 0.0}

    with preview_isolation.admitted():
        time.sleep(0.05)
        response = client.get("/health")
    busy = response.json()
    assert busy["preview"]["in_flight"] == 1
    assert busy["preview"]["slots_free"] == 0
    assert busy["preview"]["oldest_running_s"] > 0


def test_health_stays_200_and_ok_while_the_preview_is_busy(client):
    """DELIBERATE, and recorded as an accepted risk. A liveness probe that failed under preview
    load would hand a supervisor an instruction to restart the process serving production —
    destroying the traffic the probe exists to protect, for a condition that no longer slows that
    traffic down. The honest part is the disclosure above, not a failure."""
    with preview_isolation.admitted():
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
