"""THE INTERNAL-PREVIEW GATE (Issue #212, ROOT #211): `?engine=brain` is no longer authorization.

Every test here goes through the real route a real caller hits, `POST /projects/{id}/design/demo`
(and its streaming twin), with the real `app` and the real router, because the defect being closed
was reachable from the wire: typing the parameter was the whole access check.

What is faked, and only this: `service.run_brain`. The brain costs a 30 s request budget, and what
these tests are about is which requests REACH it. A spy that records the call and returns a result
with no plans makes "reached the brain" observable as its own typed refusal (`BRAIN_NO_PLAN`) —
a different code from the gate's — in milliseconds. The one thing a spy cannot prove, that the
brain itself still plans, is the existing brain suite's job and is untouched by this work.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.demo import preview_gate, service as svc
from app.demo.router import (
    ENGINE_BRAIN,
    ENGINE_CONCEPT_V2,
    ENGINE_E1_REAR_BAND,
    ENGINE_PRODUCTION,
    _resolve_engine,
)
from app.main import app
from app.projects.models import (
    Project,
    SelectedFootprint,
    SourceTag,
    StreetSide,
    TaggedBool,
    TaggedInt,
)
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes
from app.vertical_slice.brain.runner import BrainResult

TOKEN = "preview-token-for-tests-only"
BRIEF = dict(bedrooms=3, wet_rooms=1, safe_room=False, open_plan=True, built_area_m2=132.0,
             footprint_width_m=11.0, footprint_depth_m=12.0, plot_width_m=19.0, plot_depth_m=20.0)


def _project(ctx: dict) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id="GATE", city="TLV", street="S",
        plot_area_m2=ctx["plot_width_m"] * ctx["plot_depth_m"],
        plot_width_m=ctx["plot_width_m"], plot_depth_m=ctx["plot_depth_m"],
        street_facing_side=StreetSide("NORTH"), built_area_m2=ctx["built_area_m2"],
        description="", status="active", created_at=now, updated_at=now,
        selected_footprint=SelectedFootprint(
            source="CUSTOM", shape_type="RECTANGLE", target_area_m2=ctx["built_area_m2"],
            width_m=ctx["footprint_width_m"], depth_m=ctx["footprint_depth_m"],
            area_m2=round(ctx["footprint_width_m"] * ctx["footprint_depth_m"], 4)),
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=ctx["bedrooms"], source=SourceTag.requested),
        safe_room=TaggedBool(value=ctx["safe_room"], source=SourceTag.requested),
        parking_spaces=TaggedInt(value=0, source=SourceTag.requested),
        wet_rooms=TaggedInt(value=ctx["wet_rooms"], source=SourceTag.requested),
        open_plan=TaggedBool(value=ctx["open_plan"], source=SourceTag.requested),
        requirements_parsed_at=now,
    )


@pytest.fixture()
def clean_env(monkeypatch):
    """Nothing about the preview may be inherited from the machine running the tests."""
    for name in (preview_gate.FLAG_ENV, preview_gate.TOKEN_ENV,
                 preview_gate.FAMILIES_ENV, preview_gate.SIZER_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def client(tmp_path, monkeypatch, clean_env):
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    repo.replace("GATE", _project(BRIEF))
    monkeypatch.setattr(project_base_routes, "repository", repo)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def brain_spy(monkeypatch):
    """Records every call that reaches the brain, and returns a result with no plans so the
    service answers with its own `BRAIN_NO_PLAN` — proof of arrival that costs no solver time."""
    calls: list[dict] = []

    def fake_run_brain(spec, footprint_m, **kwargs):
        calls.append(kwargs)
        return BrainResult(brief=kwargs.get("brief", "brief"))

    monkeypatch.setattr(svc, "run_brain", fake_run_brain)
    return calls


def _open(flag: str | None, token: str | None, monkeypatch) -> None:
    if flag is None:
        monkeypatch.delenv(preview_gate.FLAG_ENV, raising=False)
    else:
        monkeypatch.setenv(preview_gate.FLAG_ENV, flag)
    if token is None:
        monkeypatch.delenv(preview_gate.TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(preview_gate.TOKEN_ENV, token)


def _refusal_shape(response, engine: str) -> tuple[int, object]:
    """A refusal with the caller's OWN engine name blanked out.

    The message necessarily quotes what was asked for, so two refusals for two different names can
    never be literally equal. Everything else about them must be — that is the whole claim: with
    the name removed there is nothing left to tell `?engine=brain` apart from `?engine=banana`.
    """
    detail = response.json().get("detail")
    if isinstance(detail, str):
        detail = detail.replace(repr(engine), "<asked>")
    return response.status_code, detail


def _post(client: TestClient, engine: str | None = None, token: str | None = None):
    url = "/projects/GATE/design/demo"
    if engine is not None:
        url += f"?engine={engine}"
    headers = {preview_gate.TOKEN_HEADER: token} if token is not None else {}
    return client.post(url, headers=headers)


# ================================================================== AC-1: OFF by default

def test_the_preview_is_off_with_no_configuration_at_all(clean_env):
    """The committed default. Nothing is enabled because a module was imported."""
    assert preview_gate.enabled() is False
    assert preview_gate.authorized(None) is False
    assert preview_gate.authorized(TOKEN) is False


def test_asking_for_the_brain_with_no_flag_is_refused(client, brain_spy):
    """AC-1 on the wire: the parameter alone reaches nothing."""
    response = _post(client, ENGINE_BRAIN)
    assert response.status_code == 422
    assert brain_spy == [], "the brain was reached with the preview off"


def test_the_flag_alone_is_not_enough_without_a_secret(client, brain_spy, monkeypatch):
    """A deployment that turns the flag on and forgets the token must be CLOSED, not open to
    everybody — the failure mode of a missing secret has to be refusal."""
    _open("1", None, monkeypatch)
    assert preview_gate.enabled() is True
    assert _post(client, ENGINE_BRAIN, token="").status_code == 422
    assert _post(client, ENGINE_BRAIN).status_code == 422
    assert brain_spy == []


@pytest.mark.parametrize("flag", ["0", "false", "no", "off", "", "  ", "yes_please", "TRUEISH"])
def test_only_an_explicit_true_opens_the_preview(flag, clean_env, monkeypatch):
    """A misread flag must fail CLOSED. Anything outside 1/true/yes/on is off."""
    _open(flag, TOKEN, monkeypatch)
    assert preview_gate.enabled() is False
    assert preview_gate.authorized(TOKEN) is False


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "Yes", "on", " on "])
def test_the_documented_true_values_all_work(flag, clean_env, monkeypatch):
    _open(flag, TOKEN, monkeypatch)
    assert preview_gate.enabled() is True


# ================================================================== AC-2: authorization required

def test_the_brain_refusal_is_byte_identical_to_an_unknown_engine(client, brain_spy):
    """The heart of it: an unauthorized caller must not be able to tell that a brain exists.

    Same status, same body, and the message names no engine they are not entitled to — so neither
    the response nor the error text is an oracle.
    """
    brain = _post(client, ENGINE_BRAIN)
    unknown = _post(client, "banana")
    assert brain.status_code == 422
    assert _refusal_shape(brain, ENGINE_BRAIN) == _refusal_shape(unknown, "banana")
    assert brain_spy == []


@pytest.mark.parametrize("engine", [ENGINE_BRAIN, ENGINE_E1_REAR_BAND])
def test_no_refusal_ever_names_a_gated_engine_to_an_unauthorized_caller(client, engine):
    """`e1_rear_band` is gated by the same check as the brain, and for this reason: an ungated
    second preview listed in the refusal would announce that a hidden one exists."""
    for probe in (engine, "banana", "BRAIN", "brain "):
        body = _post(client, probe).text.replace(repr(probe), "<asked>")
        assert ENGINE_BRAIN not in body, body
        assert ENGINE_E1_REAR_BAND not in body, body


@pytest.mark.parametrize("presented", [None, "", "wrong", "preview-token-for-tests-onl",
                                       "preview-token-for-tests-only ", "PREVIEW-TOKEN-FOR-TESTS-ONLY"])
def test_a_wrong_token_is_refused_exactly_like_an_unknown_engine(presented, client, brain_spy,
                                                                 monkeypatch):
    _open("1", TOKEN, monkeypatch)
    response = _post(client, ENGINE_BRAIN, token=presented)
    if presented == f"{TOKEN} ":
        # whitespace is stripped from both sides of the comparison, so this one IS the real token
        assert response.json()["detail"]["code"] == "BRAIN_NO_PLAN"
        return
    assert _refusal_shape(response, ENGINE_BRAIN) == _refusal_shape(_post(client, "banana"),
                                                                    "banana")
    assert brain_spy == []


def test_the_correct_token_with_the_flag_on_reaches_the_brain(client, brain_spy, monkeypatch):
    """AC-2's positive half: authorization actually opens the door, and what comes back is the
    BRAIN's own typed refusal, not the gate's — a different code, so arrival is observable."""
    _open("1", TOKEN, monkeypatch)
    response = _post(client, ENGINE_BRAIN, token=TOKEN)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BRAIN_NO_PLAN"
    assert len(brain_spy) == 1


def test_the_streaming_endpoint_is_gated_by_the_same_check(client, brain_spy, monkeypatch):
    """The second door into the same room. A gate on one endpoint is not a gate."""
    assert client.post(f"/projects/GATE/design/demo/stream?engine={ENGINE_BRAIN}").status_code == 422
    assert brain_spy == []
    _open("1", TOKEN, monkeypatch)
    opened = client.post(f"/projects/GATE/design/demo/stream?engine={ENGINE_BRAIN}",
                         headers={preview_gate.TOKEN_HEADER: TOKEN})
    assert opened.status_code == 200          # the stream starts, then carries the brain's refusal
    assert "BRAIN_NO_PLAN" in opened.text
    assert len(brain_spy) == 1


def test_no_request_shaped_input_can_stand_in_for_the_token(client, brain_spy, monkeypatch):
    """AC-7, as a test: the secret is read from the configured header and nowhere else. A query
    parameter, a body field or a differently-named header is not authorization."""
    _open("1", TOKEN, monkeypatch)
    probes = [
        client.post(f"/projects/GATE/design/demo?engine={ENGINE_BRAIN}&token={TOKEN}"),
        client.post(f"/projects/GATE/design/demo?engine={ENGINE_BRAIN}",
                    headers={"Authorization": f"Bearer {TOKEN}"}),
        client.post(f"/projects/GATE/design/demo?engine={ENGINE_BRAIN}",
                    headers={"X-Brain-Preview": TOKEN}),
        client.post(f"/projects/GATE/design/demo?engine={ENGINE_BRAIN}", json={"token": TOKEN}),
    ]
    for response in probes:
        assert response.status_code == 422, response.text
        assert response.json()["detail"] != {"code": "BRAIN_NO_PLAN"}
    assert brain_spy == [], "something other than the header authorized a brain request"


def test_the_token_is_never_echoed_back_to_the_caller(client, monkeypatch):
    """A refusal that quotes the secret back is a disclosure. Neither half may appear."""
    _open("1", TOKEN, monkeypatch)
    for response in (_post(client, ENGINE_BRAIN, token="wrong"), _post(client, "banana")):
        assert TOKEN not in response.text


# ================================================================== AC-3: instant disable

def test_flipping_the_flag_at_runtime_disables_the_preview_with_no_restart(client, brain_spy,
                                                                          monkeypatch):
    """AC-3. Two requests in the SAME process, the same imported modules, the same client: the
    first reaches the brain, the flag is unset, and the second one refuses. Nothing is reloaded,
    so nothing needs a redeploy."""
    _open("1", TOKEN, monkeypatch)
    first = _post(client, ENGINE_BRAIN, token=TOKEN)
    assert first.json()["detail"]["code"] == "BRAIN_NO_PLAN"
    assert len(brain_spy) == 1

    monkeypatch.delenv(preview_gate.FLAG_ENV)                      # the emergency disable

    second = _post(client, ENGINE_BRAIN, token=TOKEN)
    assert _refusal_shape(second, ENGINE_BRAIN) == _refusal_shape(_post(client, "banana"), "banana")
    assert len(brain_spy) == 1, "a request got through after the flag was turned off"


def test_clearing_the_token_disables_the_preview_just_as_fast(client, brain_spy, monkeypatch):
    """The second lever, in case the flag is the one an operator cannot reach: revoking the secret
    closes the preview on the next request too."""
    _open("1", TOKEN, monkeypatch)
    assert _post(client, ENGINE_BRAIN, token=TOKEN).json()["detail"]["code"] == "BRAIN_NO_PLAN"
    monkeypatch.setenv(preview_gate.TOKEN_ENV, "")
    assert _post(client, ENGINE_BRAIN, token=TOKEN).status_code == 422
    assert len(brain_spy) == 1


def test_nothing_caches_the_decision_across_requests(client, brain_spy, monkeypatch):
    """Read at request time means every request, not the first one."""
    _open("1", TOKEN, monkeypatch)
    for _ in range(3):
        assert _post(client, ENGINE_BRAIN, token=TOKEN).json()["detail"]["code"] == "BRAIN_NO_PLAN"
    monkeypatch.delenv(preview_gate.FLAG_ENV)
    for _ in range(3):
        assert _post(client, ENGINE_BRAIN, token=TOKEN).json()["detail"] != {"code": "BRAIN_NO_PLAN"}
    assert len(brain_spy) == 3


# ================================================================== AC-4: production untouched

def test_production_needs_no_token_and_is_unchanged_by_the_gate(client, clean_env):
    """The default engine is production, and the gate costs it nothing: no header, no flag, a plan."""
    for engine in (None, ENGINE_PRODUCTION):
        response = _post(client, engine)
        assert response.status_code == 200, response.text
        assert response.json()["plan"]["rooms"]


def test_concept_engine_v2_stays_open_because_it_was_never_the_defect(client, clean_env):
    """`?engine=concept_engine_v2` is a per-request override of a flag that is globally OFF; it was
    not the unauthorized path to unfinished geometry, and widening the gate over it would change
    behaviour this Issue was not asked to change."""
    assert _post(client, ENGINE_CONCEPT_V2).status_code == 200


def test_the_resolved_choice_is_what_it_always_was_for_the_open_engines(clean_env):
    assert _resolve_engine(None).concept_engine_v2 is None
    assert _resolve_engine(ENGINE_PRODUCTION).concept_engine_v2 is None
    assert _resolve_engine(ENGINE_CONCEPT_V2).concept_engine_v2 is True
    for choice in (_resolve_engine(None), _resolve_engine(ENGINE_PRODUCTION),
                   _resolve_engine(ENGINE_CONCEPT_V2)):
        assert (choice.brain, choice.rear_band) == (False, False)


def test_an_authorized_request_for_an_unknown_engine_is_still_refused(clean_env, monkeypatch):
    """Authorization is not a bypass of validation."""
    _open("1", TOKEN, monkeypatch)
    with pytest.raises(Exception) as caught:
        _resolve_engine("banana", TOKEN)
    assert getattr(caught.value, "status_code", None) == 422


# ================================================================== AC-5: the family list is config

def test_the_default_families_are_the_measured_four(clean_env):
    assert preview_gate.families() == ("band", "spine", "stack", "cells")
    assert preview_gate.sizer() == "exact"


def test_the_preview_can_never_use_the_generator_family(clean_env, monkeypatch):
    """AC-5, and the promise behind it: #208's `generator` family took a day-2 gate verdict of
    STOP, so an owner judging the preview must never be shown a plan it made. Configuration can
    only NARROW the list — asking for the family does not add it."""
    assert "generator" in preview_gate.GATE_FAILED_FAMILIES
    assert "generator" not in preview_gate.ALLOWED_FAMILIES
    assert "generator" not in preview_gate.DEFAULT_FAMILIES
    for asked in ("generator", "band,generator", "generator,spine,generator", "GENERATOR, band"):
        monkeypatch.setenv(preview_gate.FAMILIES_ENV, asked)
        assert "generator" not in preview_gate.families()


def test_configuration_may_narrow_the_families_but_not_widen_them(clean_env, monkeypatch):
    monkeypatch.setenv(preview_gate.FAMILIES_ENV, "band, spine")
    assert preview_gate.families() == ("band", "spine")
    monkeypatch.setenv(preview_gate.FAMILIES_ENV, "band,nonsense,band")
    assert preview_gate.families() == ("band",)
    monkeypatch.setenv(preview_gate.FAMILIES_ENV, "nonsense")
    assert preview_gate.families() == preview_gate.DEFAULT_FAMILIES, (
        "an unrecognised list must fall back to the default, not to sizing nothing")


def test_the_families_the_brain_is_actually_given_are_the_configured_ones(client, brain_spy,
                                                                         monkeypatch):
    """The pin that matters: the list is not just computed, it is what `run_brain` receives."""
    _open("1", TOKEN, monkeypatch)
    monkeypatch.setenv(preview_gate.FAMILIES_ENV, "band,generator")
    _post(client, ENGINE_BRAIN, token=TOKEN)
    assert brain_spy[0]["families"] == ("band",)
    assert brain_spy[0]["sizer"] == "exact"


def test_no_module_level_constant_enables_the_preview_at_import_time(clean_env):
    """AC-7's other half: nothing in the preview's own source is a committed `True`."""
    import inspect

    source = inspect.getsource(preview_gate)
    assert "= True" not in source, "a literal True in the gate module is a flag nobody can turn off"
    for name in ("BRAIN_SIZER", "BRAIN_FAMILIES"):
        assert not hasattr(svc, name), (
            f"service.{name} is back as a module constant — the family list must stay configuration")
