"""THE PREVIEW'S CONCURRENCY LIMIT (Issue #246, ROOT #211): one gated request at a time, typed.

#226 measured production's median going x3.6 to x5.6 (x9.9 at worst) beside two to four brain
requests, because HiGHS holds the GIL and nothing bounded how many ran. These tests prove the bound
on the wire, through the real app and the real router, exactly as `test_brain_preview_gate.py` does:

- AC-1: with one preview request in flight a second is refused, on both endpoints, the default is 1,
  and the slot comes back on every way a request can end.
- AC-2: no configuration raises the limit above `MEASURED_MAX_CONCURRENCY`, and the refusal is a
  typed 429 with a code and a `Retry-After`, reaching only an authorized caller.

What is faked, and only this: `service.run_brain`, as in the gate tests. Here the fake BLOCKS until
the test lets it go, which is what makes "a request is in flight" a state the test can hold still.
What a fake cannot prove — that production stays fast beside a real brain request — is measured, in
`docs/reports/architectural-brain/PREVIEW-isolation-proof.md`, not asserted here.
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from app.demo import preview_gate, preview_limit, service as svc
from app.main import app
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes
from app.vertical_slice.brain.runner import BrainResult
from tests.demo.test_brain_preview_gate import BRIEF, TOKEN, _project

DEMO = "/projects/GATE/design/demo"
STREAM = "/projects/GATE/design/demo/stream"
HEADERS = {preview_gate.TOKEN_HEADER: TOKEN}


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for name in (preview_gate.FLAG_ENV, preview_gate.TOKEN_ENV, preview_gate.FAMILIES_ENV,
                 preview_gate.SIZER_ENV, preview_limit.LIMIT_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    monkeypatch.setenv(preview_gate.TOKEN_ENV, TOKEN)
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    repo.replace("GATE", _project(BRIEF))
    monkeypatch.setattr(project_base_routes, "repository", repo)
    # no slot may leak out of one test into the next
    assert preview_limit.in_flight() == 0
    yield
    assert preview_limit.in_flight() == 0, "a test left a preview slot held"


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


class HeldBrain:
    """A `run_brain` that signals it was entered and then blocks until released."""

    def __init__(self, monkeypatch, *, raises: BaseException | None = None) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.raises = raises

        def fake_run_brain(spec, footprint_m, **kwargs):
            self.calls += 1
            self.entered.set()
            assert self.release.wait(timeout=60), "the test never released the held brain request"
            if self.raises is not None:
                raise self.raises
            return BrainResult(brief=kwargs.get("brief", "brief"))

        monkeypatch.setattr(svc, "run_brain", fake_run_brain)

    def hold(self, client, path, *, headers=HEADERS) -> tuple[threading.Thread, dict]:
        """Start one authorized brain request on its own thread; return once it is IN the brain."""
        box: dict = {}

        def go():
            box["response"] = client.post(f"{path}?engine=brain", headers=headers)

        thread = threading.Thread(target=go, daemon=True)
        thread.start()
        assert self.entered.wait(timeout=120), "the first request never reached the brain"
        return thread, box

    def finish(self, thread: threading.Thread) -> None:
        self.release.set()
        thread.join(timeout=120)
        assert not thread.is_alive()


# ------------------------------------------------------------------------------- the limit itself

def test_the_default_limit_is_one_and_it_is_what_is_measured():
    assert preview_limit.DEFAULT_MAX_CONCURRENCY == 1
    assert preview_limit.MEASURED_MAX_CONCURRENCY == 1
    assert preview_limit.max_concurrency() == 1


@pytest.mark.parametrize("asked", ["2", "4", "8", "1000", " 3 "])
def test_no_configuration_raises_the_limit_above_what_is_measured(monkeypatch, asked):
    monkeypatch.setenv(preview_limit.LIMIT_ENV, asked)
    assert preview_limit.max_concurrency() == preview_limit.MEASURED_MAX_CONCURRENCY == 1


@pytest.mark.parametrize("asked", ["", "0", "-1", "-5", "two", "1.5", "NaN"])
def test_an_unusable_value_means_the_default_never_zero_and_never_open(monkeypatch, asked):
    monkeypatch.setenv(preview_limit.LIMIT_ENV, asked)
    assert preview_limit.max_concurrency() == preview_limit.DEFAULT_MAX_CONCURRENCY == 1


def test_a_second_acquire_is_refused_without_blocking_and_a_release_reopens_it():
    preview_limit.acquire()
    try:
        with pytest.raises(preview_limit.PreviewBusy) as busy:
            preview_limit.acquire()
        assert (busy.value.limit, busy.value.in_flight) == (1, 1)
        assert preview_limit.in_flight() == 1, "a refused acquire must not take a slot"
    finally:
        preview_limit.release()
    with preview_limit.slot():
        assert preview_limit.in_flight() == 1
    assert preview_limit.in_flight() == 0


def test_the_ceiling_holds_under_a_race_of_many_simultaneous_acquirers(monkeypatch):
    monkeypatch.setenv(preview_limit.LIMIT_ENV, "50")
    start = threading.Barrier(16)
    won: list[bool] = []

    def contend():
        start.wait()
        try:
            preview_limit.acquire()
            won.append(True)
        except preview_limit.PreviewBusy:
            won.append(False)

    threads = [threading.Thread(target=contend) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    try:
        assert sum(won) == 1, f"{sum(won)} of 16 simultaneous acquirers got a slot"
    finally:
        for _ in range(sum(won)):
            preview_limit.release()


# ---------------------------------------------------------------------------- on the wire (AC-1/2)

def test_a_second_simultaneous_brain_request_is_a_typed_429(client, monkeypatch):
    held = HeldBrain(monkeypatch)
    first, box = held.hold(client, DEMO)

    second = client.post(f"{DEMO}?engine=brain", headers=HEADERS)

    assert second.status_code == 429
    detail = second.json()["detail"]
    assert detail["code"] == preview_limit.BUSY_CODE == "BRAIN_PREVIEW_BUSY"
    assert detail["message"] and "1 of 1" in detail["detail"]
    assert second.headers["Retry-After"] == str(preview_limit.RETRY_AFTER_S)
    assert held.calls == 1, "the refused request must not have reached the brain"

    held.finish(first)
    # the first request is unaffected by the refusal: it ends as the brain says it ends
    assert box["response"].status_code == 422
    assert box["response"].json()["detail"]["code"] == "BRAIN_NO_PLAN"


def test_the_slot_comes_back_so_the_next_request_is_served(client, monkeypatch):
    held = HeldBrain(monkeypatch)
    first, _ = held.hold(client, DEMO)
    assert client.post(f"{DEMO}?engine=brain", headers=HEADERS).status_code == 429
    held.finish(first)
    assert preview_limit.in_flight() == 0

    third = client.post(f"{DEMO}?engine=brain", headers=HEADERS)
    assert third.status_code == 422 and third.json()["detail"]["code"] == "BRAIN_NO_PLAN"
    assert held.calls == 2


def test_the_slot_comes_back_when_the_brain_crashes(client, monkeypatch):
    held = HeldBrain(monkeypatch, raises=RuntimeError("solver blew up"))
    first, box = held.hold(client, DEMO)
    assert client.post(f"{DEMO}?engine=brain", headers=HEADERS).status_code == 429
    held.finish(first)
    assert box["response"].status_code == 500
    assert preview_limit.in_flight() == 0, "a crashed request must give its slot back"


def test_the_streaming_endpoint_shares_the_one_slot(client, monkeypatch):
    held = HeldBrain(monkeypatch)
    first, box = held.hold(client, STREAM)

    # beside a streaming request, BOTH endpoints refuse a second one
    for path in (STREAM, DEMO):
        refused = client.post(f"{path}?engine=brain", headers=HEADERS)
        assert refused.status_code == 429, path
        assert refused.json()["detail"]["code"] == "BRAIN_PREVIEW_BUSY"
        assert refused.headers["Retry-After"] == str(preview_limit.RETRY_AFTER_S)
    assert held.calls == 1

    held.finish(first)
    assert box["response"].status_code == 200
    assert "event: error" in box["response"].text and "BRAIN_NO_PLAN" in box["response"].text
    assert preview_limit.in_flight() == 0

    after = client.post(f"{STREAM}?engine=brain", headers=HEADERS)
    assert after.status_code == 200 and held.calls == 2


def test_the_streaming_slot_is_held_by_the_work_not_by_the_listener(client, monkeypatch):
    """The solver keeps running after a client leaves, so the slot must too: if the slot followed
    the connection, a reconnecting client could start a second solve beside the first."""
    held = HeldBrain(monkeypatch)
    first, _ = held.hold(client, STREAM)
    # the worker is mid-solve; whoever was listening is irrelevant to the count
    assert preview_limit.in_flight() == 1
    assert client.post(f"{STREAM}?engine=brain", headers=HEADERS).status_code == 429
    held.finish(first)
    assert preview_limit.in_flight() == 0


def test_the_other_gated_preview_shares_the_same_limit(client, monkeypatch):
    held = HeldBrain(monkeypatch)
    first, _ = held.hold(client, DEMO)
    refused = client.post(f"{DEMO}?engine=e1_rear_band", headers=HEADERS)
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "BRAIN_PREVIEW_BUSY"
    held.finish(first)


def test_a_configured_limit_above_the_ceiling_still_refuses_the_second_on_the_wire(client, monkeypatch):
    monkeypatch.setenv(preview_limit.LIMIT_ENV, "4")
    held = HeldBrain(monkeypatch)
    first, _ = held.hold(client, DEMO)
    assert client.post(f"{DEMO}?engine=brain", headers=HEADERS).status_code == 429
    held.finish(first)


# ----------------------------------------------------------- the limit protects, and does not leak

def test_production_and_the_open_engine_never_queue_behind_a_preview(client, monkeypatch):
    held = HeldBrain(monkeypatch)
    first, _ = held.hold(client, DEMO)

    production = client.post(DEMO)
    open_engine = client.post(f"{DEMO}?engine=concept_engine_v2")

    assert production.status_code != 429 and open_engine.status_code != 429
    assert preview_limit.in_flight() == 1, "production must neither take nor give a preview slot"
    held.finish(first)


@pytest.mark.parametrize("headers", [{}, {preview_gate.TOKEN_HEADER: "wrong"}])
def test_an_unauthorized_caller_cannot_see_that_a_preview_is_busy(client, monkeypatch, headers):
    """The 429 is behind the gate: a prober must get the byte-identical unknown-engine 422 whether
    or not a preview is running, or the busy refusal becomes the oracle #212 closed."""
    quiet = client.post(f"{DEMO}?engine=brain", headers=headers)
    held = HeldBrain(monkeypatch)
    first, _ = held.hold(client, DEMO)
    busy = client.post(f"{DEMO}?engine=brain", headers=headers)
    held.finish(first)

    assert quiet.status_code == busy.status_code == 422
    assert quiet.json() == busy.json()
    assert "Retry-After" not in busy.headers


def test_a_refusal_before_any_work_leaves_no_slot_behind(client):
    """An unknown project, an unknown engine and an unauthorized caller are all refused before a
    slot is taken — none of them may count against the preview."""
    assert client.post("/projects/NOPE/design/demo?engine=brain", headers=HEADERS).status_code == 404
    assert client.post(f"{DEMO}?engine=banana", headers=HEADERS).status_code == 422
    assert client.post(f"{DEMO}?engine=brain").status_code == 422
    assert preview_limit.in_flight() == 0
