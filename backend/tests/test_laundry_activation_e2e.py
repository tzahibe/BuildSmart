"""End-to-end laundry activation smoke (2026-09-16, post-review verification for
docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md).

Every test here goes through the SAME routes a real user hits, exactly like `test_demo_p0.py`
(whose fixture/helper pattern this file mirrors, not shares — kept self-contained rather than
importing that file's private helpers):

    POST /projects                      (brief + built area + selected footprint)
    POST /projects/{id}/requirements    (the parser — faked, standing in for the OpenAI call)
    GET  /projects/{id}/review          ("what I understood" — Review must not be blocked)
    POST /projects/{id}/design/demo     (the validated pipeline — Generate must produce a plan)

Confirms, through this real flow and nothing constructed by hand: an explicit "חדר כביסה" request
is not routed to `unsupported_requests`; Review is not blocked by it; the delivered plan contains
exactly one LAUNDRY room; `laundry_notice` fires only when redistribution actually happens; and a
vague appliance mention ("מקום למכונת כביסה") does not silently create a room.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.demo.service import (
    DemoGenerationError,
    Outline,
    OutlineResult,
    _finish,
    _laundry_unplaceable_message,
)
from app.main import app
from app.projects.models import PoolField, SourceTag, TaggedBool, TaggedFloat, TaggedInt
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes
from app.requirements import router as requirements_router
from app.requirements.parser import LaundryRoomDemand, RequirementExtraction, RequirementParser
from app.vertical_slice.concept_generator import build_room_program
from app.vertical_slice.general_pipeline import GeneralSliceResult, RunMetrics
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.safe_adapter import AdapterOutcome as _AdapterOutcome
from app.vertical_slice.spec import PlotSpec as _PlotSpec
from app.vertical_slice.validation import Check, ValidationReport

REQ = SourceTag.requested
INF = SourceTag.inferred
UNK = SourceTag.unknown

_F, _S, _R = 5.5, 3.0, 4.0
_DEMO_SETBACKS = {"front_m": _F, "side_m": _S, "rear_m": _R}


def _extraction(*, bedrooms=3, safe_room=True, wet_rooms=2, open_plan=True, parking=2,
                laundry_requested=False, laundry_source_text="") -> RequirementExtraction:
    return RequirementExtraction(
        floors=TaggedInt(value=1, source=INF),
        bedrooms=TaggedInt(value=bedrooms, source=REQ),
        safe_room=TaggedBool(value=safe_room, source=REQ if safe_room else UNK),
        parking_spaces=TaggedInt(value=parking, source=REQ),
        pool=PoolField(requested=TaggedBool(value=None, source=UNK),
                      length_m=TaggedFloat(value=None, source=UNK),
                      width_m=TaggedFloat(value=None, source=UNK)),
        wet_rooms=TaggedInt(value=wet_rooms, source=REQ),
        open_plan=TaggedBool(value=open_plan, source=REQ),
        laundry=LaundryRoomDemand(
            requested=TaggedBool(value=laundry_requested, source=REQ if laundry_requested else INF),
            source_text=laundry_source_text),
    )


# Generous footprint (matches test_demo_p0.py's C_3BR_SAFE_OPEN sizing — known to plan comfortably)
# and a deliberately TIGHT one (the programme's own natural, no-surplus size), to exercise both
# "laundry_notice stays silent" and "laundry_notice actually fires".
BRIEF_LAUNDRY_GENEROUS = (
    'בית פרטי בקומה אחת עם שלושה חדרי שינה, ממ"ד, מטבח פתוח לסלון ולפינת אוכל, '
    'שני חדרי רחצה, שתי חניות, וחדר כביסה נפרד.'
)
BRIEF_LAUNDRY_TIGHT = (
    'בית עם שלושה חדרי שינה, שני חדרי רחצה, מטבח פתוח, וחדר כביסה נפרד.'
)
BRIEF_NO_LAUNDRY = (
    'בית פרטי בקומה אחת עם שלושה חדרי שינה, ממ"ד, מטבח פתוח לסלון ולפינת אוכל, '
    'שני חדרי רחצה ושתי חניות.'
)
BRIEF_APPLIANCE_ONLY = (
    'בית עם שלושה חדרי שינה, שני חדרי רחצה, מטבח פתוח, ומקום למכונת כביסה במטבח.'
)

CANNED = {
    BRIEF_LAUNDRY_GENEROUS: _extraction(laundry_requested=True, laundry_source_text="חדר כביסה נפרד"),
    BRIEF_LAUNDRY_TIGHT: _extraction(safe_room=False, laundry_requested=True,
                                     laundry_source_text="חדר כביסה נפרד"),
    BRIEF_NO_LAUNDRY: _extraction(laundry_requested=False),
    # The negative case (§2's "vague wording" check): an appliance mention, no room asked for —
    # the parser's own rule (requirements/parser.py's `laundry` extraction section) says this
    # must NOT become a room request; the canned extraction here is what the prompt instructs the
    # model to produce for exactly this phrasing, standing in for the real OpenAI call.
    BRIEF_APPLIANCE_ONLY: _extraction(safe_room=False, laundry_requested=False),
}


class FakeParser(RequirementParser):
    def parse(self, description: str) -> RequirementExtraction:
        try:
            return CANNED[description]
        except KeyError:
            raise AssertionError(f"no canned extraction for: {description!r}")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", repo)
    monkeypatch.setattr(requirements_router, "parser", FakeParser())
    return TestClient(app)


def _create(client: TestClient, description: str, *, width: float, depth: float) -> str:
    area = round(width * depth, 2)
    plot_w = round(width + 2 * _S + 1.0, 2)
    plot_d = round(depth + _F + _R + 1.0, 2)
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": round(plot_w * plot_d, 2), "built_area_m2": area,
        "plot_width_m": plot_w, "plot_depth_m": plot_d, "street_facing_side": "NORTH",
        "setbacks": _DEMO_SETBACKS, "description": description,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE",
                               "target_area_m2": area, "area_m2": area,
                               "width_m": width, "depth_m": depth},
    })
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def _run(client: TestClient, description: str, *, width: float, depth: float):
    project_id = _create(client, description, width=width, depth=depth)
    parsed = client.post(f"/projects/{project_id}/requirements")
    assert parsed.status_code == 200, parsed.text
    review = client.get(f"/projects/{project_id}/review")
    assert review.status_code == 200, review.text
    design = client.post(f"/projects/{project_id}/design/demo")
    return project_id, parsed.json(), review.json(), design


def _rooms_of_type(design_json: dict, room_type: str) -> list:
    return [r for r in design_json["plan"]["rooms"] if r["type"] == room_type]


def test_explicit_laundry_request_is_not_an_unsupported_requirement(client):
    """§2, point 1: not returned as an unsupported hard requirement."""
    _, parsed, _, _ = _run(client, BRIEF_LAUNDRY_GENEROUS, width=12.5, depth=14.5)
    assert parsed["laundry_requested"] == {"value": True, "source": "requested"}
    assert not any("כביסה" in r["text"] for r in parsed["unsupported_requests"])


def test_review_is_not_blocked_by_a_laundry_request(client):
    """§2, point 2: Review is not blocked merely because laundry was requested — the ONE thing
    that keeps Generate blocked at the review level (`wet_room_problem`) is driven purely by
    bedrooms/wet-room counts and stays None here, exactly as for the equivalent no-laundry brief."""
    _, _, review, design = _run(client, BRIEF_LAUNDRY_GENEROUS, width=12.5, depth=14.5)
    assert review["wet_room_problem"] is None
    assert design.status_code == 200, design.text


def test_program_spec_carries_exactly_one_laundry_room(client):
    """§2, point 3, at the ProgramSpec level (not just the delivered plan): `spec_for` resolves
    to a programme whose `build_room_program` emits exactly one LAUNDRY room."""
    from app.demo.requirements_view import spec_for
    from app.projects.routes import base_routes as project_routes

    project_id = _create(client, BRIEF_LAUNDRY_GENEROUS, width=12.5, depth=14.5)
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    project = project_routes.repository.get(project_id)
    spec = spec_for(project)
    rooms = build_room_program(spec)
    laundry_rooms = [r for r in rooms if r.role is ProgramRole.LAUNDRY]
    assert len(laundry_rooms) == 1


def test_generated_plan_contains_the_laundry_room_when_feasible(client):
    """§2, point 4: a generated valid plan contains the room when feasible."""
    _, _, _, design = _run(client, BRIEF_LAUNDRY_GENEROUS, width=12.5, depth=14.5)
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["plan"]["validation"]["passed"]
    laundry_rooms = _rooms_of_type(body, "LAUNDRY")
    assert len(laundry_rooms) == 1


def test_delivered_laundry_room_has_a_door_a_window_and_a_machine_bay(client):
    """Issue #21, AC-4: a laundry brief that plans delivers a LAUNDRY room with a door, a window
    (the API's `no_window_reason is None` + `window_side` set is exactly the condition
    `windows.py::generate_windows` sets `ventilation_status = EXTERIOR_WINDOW` under — see
    `windows.py`), a short side >= 1.7 m, and a placed washing-machine footprint (C9, in
    `plan.validation.checks`, passing by construction once the short side floor is 1.7 m — see
    `test_laundry_room.py::test_a_room_at_the_template_floor_always_inscribes_the_washing_machine_
    footprint`)."""
    _, _, _, design = _run(client, BRIEF_LAUNDRY_GENEROUS, width=12.5, depth=14.5)
    assert design.status_code == 200, design.text
    body = design.json()
    checks = body["plan"]["validation"]["checks"]
    for check_id in ("C19", "C8", "C3", "C9", "C24"):
        assert checks[check_id] is True, (check_id, body["plan"]["validation"])

    laundry_rooms = _rooms_of_type(body, "LAUNDRY")
    assert len(laundry_rooms) == 1
    room = laundry_rooms[0]
    assert min(room["width_m"], room["depth_m"]) >= 1.7 - 1e-6, room

    doors = [d for d in body["plan"]["doors"] if room["id"] in (d["a"], d["b"])]
    assert len(doors) == 1, doors
    assert doors[0]["width_m"] == 0.8, doors[0]  # SERVICE_DOOR (access_rules.DOOR_WIDTH_M)

    exposure = next(e for e in body["plan"]["quality"]["exposure"] if e["room_id"] == room["id"])
    assert exposure["no_window_reason"] is None, exposure
    assert exposure["window_side"] is not None
    assert exposure["window_width_m"] >= 0.6 - 1e-6


def test_laundry_notice_stays_silent_on_a_generous_brief(client):
    """§2, point 5 (silent half): plenty of area — no room genuinely squeezed, no notice."""
    _, _, _, design = _run(client, BRIEF_LAUNDRY_GENEROUS, width=12.5, depth=14.5)
    assert design.status_code == 200, design.text
    quality = design.json()["plan"]["quality"]
    assert quality["laundry_notice"] is None


def test_laundry_notice_fires_when_redistribution_actually_happens(client):
    """§2, point 5 (firing half): a deliberately tight brief — the same programme, sized to its
    own natural (no-surplus) area, so the laundry room's cost forces a real redistribution."""
    from app.vertical_slice.concept_generator import build_room_program, target_gross_area_m2
    from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

    rooms = build_room_program(ArchitecturalSpec(
        plot=PlotSpec(20.0, 24.0),
        program=ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, open_plan_living=True)))
    target = target_gross_area_m2(rooms)
    aspect = 0.82
    depth = (target / aspect) ** 0.5
    width = target / depth

    _, _, _, design = _run(client, BRIEF_LAUNDRY_TIGHT, width=round(width, 2), depth=round(depth, 2))
    assert design.status_code == 200, design.text
    body = design.json()
    assert len(_rooms_of_type(body, "LAUNDRY")) == 1
    notice = body["plan"]["quality"]["laundry_notice"]
    assert notice is not None
    assert "כביסה" in notice


def test_a_vague_appliance_mention_does_not_silently_create_a_room(client):
    """§2, point 6: "מקום למכונת כביסה" (a washing-machine spot, no room asked for) must not
    become a LAUNDRY room — the parser's own explicit negative rule."""
    _, parsed, _, design = _run(client, BRIEF_APPLIANCE_ONLY, width=12.0, depth=13.5)
    assert parsed["laundry_requested"] == {"value": False, "source": "inferred"}
    assert design.status_code == 200, design.text
    assert len(_rooms_of_type(design.json(), "LAUNDRY")) == 0


def test_no_laundry_request_plans_with_no_laundry_room(client):
    """Control: the exact same class of brief with no laundry mention at all — no room, no
    notice, same as before this activation existed."""
    _, parsed, _, design = _run(client, BRIEF_NO_LAUNDRY, width=12.5, depth=14.5)
    assert parsed["laundry_requested"] == {"value": False, "source": "inferred"}
    assert design.status_code == 200, design.text
    body = design.json()
    assert len(_rooms_of_type(body, "LAUNDRY")) == 0
    assert body["plan"]["quality"]["laundry_notice"] is None


# ------------------------------------------------------------------ LAUNDRY_UNPLACEABLE (Issue #21, AC-3)
#
# The real search (`app.vertical_slice.general_pipeline.run_general`) already places LAUNDRY on an
# exterior wall on every footprint this suite could construct — the exterior-preference ordering
# `_daylight_order` gained for free once LAUNDRY joined `DAYLIGHT_ROLES` (Issue #21, requirement 1)
# is resilient across the partis this codebase's search tries. So the tests below prove the
# REFUSAL's own logic directly, against the real production types
# (`ValidationReport`/`GeneralSliceResult`/`OutlineResult`) the pipeline actually produces, the same
# way `test_exposure_policy.py`'s fixture-based C19/C8 proofs stand in for a full corpus repro.

def _laundry_spec():
    from app.vertical_slice.spec import ArchitecturalSpec, LaundryDemand, LaundryRequirement, ProgramSpec

    return ArchitecturalSpec(
        plot=_PlotSpec(10.0, 12.0),
        program=ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, open_plan_living=True,
                            laundry=LaundryRequirement(demand=LaundryDemand.ROOM,
                                                       source_text="חדר כביסה")))


def _outline_result(validation: ValidationReport | None, *,
                    outcome=_AdapterOutcome.SOLVED, rejection_reasons: tuple[str, ...] = (),
                    design=object()) -> OutlineResult:
    result = GeneralSliceResult(
        outcome=outcome, adapter=None, design=design if validation is not None else None,
        validation=validation, safety=None,
        metrics=RunMetrics(rejection_reasons=rejection_reasons))
    return OutlineResult(outline=Outline(10.0, 12.0, "PERSON", 0), result=result, plans=(),
                         latency_ms=0.0)


def test_laundry_unplaceable_message_names_the_exterior_wall_requirement():
    outlines = [_outline_result(ValidationReport(checks=[
        Check("C19", "required rooms touch an exterior wall", False,
             "LAUNDRY has no exterior wall (interior room)"),
    ]))]
    message = _laundry_unplaceable_message(_laundry_spec(), outlines)
    assert message is not None
    assert "קיר חיצוני" in message


def test_laundry_unplaceable_message_names_the_bay_requirement():
    outlines = [_outline_result(ValidationReport(checks=[
        Check("C3", "room areas and dimensions valid", False,
             "LAUNDRY short side 1.40 < 1.7"),
    ]))]
    message = _laundry_unplaceable_message(_laundry_spec(), outlines)
    assert message is not None
    assert "מכונת הכביסה" in message


def test_laundry_unplaceable_message_none_when_the_pre_solve_rejection_names_laundry():
    """C19/C8/C3 need a solved candidate; a footprint too narrow for the LAUNDRY room's own shape
    band never reaches the solver at all (`room_depth_band_m` returns None pre-solve) — the
    generator's own rejection reason for that failure names the zone the same way."""
    outlines = [_outline_result(
        None, outcome=_AdapterOutcome.INSUFFICIENT_RECTANGULAR_CAPACITY,
        rejection_reasons=("SPINE_PUBLIC_PRIVATE/ROOM_SHAPE_INFEASIBLE: LAUNDRY at 1.40 m wide "
                           "has no depth that keeps its 3.0 aspect ratio and 1.7 m short side "
                           "under its 8 m2 preferred maximum",))]
    message = _laundry_unplaceable_message(_laundry_spec(), outlines)
    assert message is not None
    assert "מכונת הכביסה" in message


def test_laundry_unplaceable_message_is_none_when_another_room_is_also_the_problem():
    """Never fires when the failure is not laundry-specific — an unrelated room's own defect
    alongside LAUNDRY's must not be attributed to the laundry room."""
    outlines = [_outline_result(ValidationReport(checks=[
        Check("C19", "required rooms touch an exterior wall", False,
             "LAUNDRY has no exterior wall (interior room)"),
        Check("C8", "daylight/window exposure present where required", False, "BEDROOM_1"),
    ]))]
    assert _laundry_unplaceable_message(_laundry_spec(), outlines) is None


def test_laundry_unplaceable_message_is_none_when_only_some_outlines_blame_laundry():
    """Never fires unless EVERY outline this brief tried failed for a laundry-specific reason —
    one outline that failed for an unrelated cause means the refusal is not really about laundry."""
    laundry_only = _outline_result(ValidationReport(checks=[
        Check("C19", "required rooms touch an exterior wall", False,
             "LAUNDRY has no exterior wall (interior room)"),
    ]))
    other_reason = _outline_result(ValidationReport(checks=[
        Check("C14", "corridor width", False, "corridor too narrow"),
    ]))
    assert _laundry_unplaceable_message(_laundry_spec(), [laundry_only, other_reason]) is None


def test_laundry_unplaceable_message_is_none_without_a_laundry_request():
    from app.vertical_slice.spec import ArchitecturalSpec, ProgramSpec

    program = ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, open_plan_living=True)
    spec = ArchitecturalSpec(plot=_PlotSpec(10.0, 12.0), program=program)
    outlines = [_outline_result(ValidationReport(checks=[
        Check("C19", "required rooms touch an exterior wall", False,
             "LAUNDRY has no exterior wall (interior room)"),
    ]))]
    assert _laundry_unplaceable_message(spec, outlines) is None


def test_finish_raises_laundry_unplaceable_for_a_laundry_only_c19_failure():
    """AC-3, the wiring: `_finish` — the real refusal path `generate_demo_design` calls — raises
    `LAUNDRY_UNPLACEABLE` (not the generic `PLAN_FAILED_VALIDATION`) when the plan's only failing
    check is the LAUNDRY room's own exterior-wall requirement."""
    spec = _laundry_spec()
    outline = _outline_result(ValidationReport(checks=[
        Check("C19", "required rooms touch an exterior wall", False,
             "LAUNDRY has no exterior wall (interior room)"),
    ]))
    with pytest.raises(DemoGenerationError) as excinfo:
        _finish(None, spec, outline.result, False, outlines=[outline])
    assert excinfo.value.code == "LAUNDRY_UNPLACEABLE"
    assert "קיר חיצוני" in excinfo.value.message
