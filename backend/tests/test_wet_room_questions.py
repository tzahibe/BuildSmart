"""Toilet as a fixture, WC as a room (Phases 1–3, 2026-09-15): the parser's `FixtureDemand` is
normalized into rooms by rule, a reading the rule will not settle is a stored QUESTION that blocks
generation and carries a proposed answer, every derived room says so (`origin`), and decision A's
I4 question now offers "add a shared bathroom" as its one-click answer."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# The chat fixtures (fake assistant + fake intent extractor + all repositories), verbatim. Imported
# FIRST: it loads `app.main`, which reads `.env` before the OpenAI-backed parser is constructed.
from tests.test_chat import (  # noqa: F401
    PROJECT_PAYLOAD,
    client,
    conversation_repo,
    design_version_repo,
    fake_assistant,
    fake_intent_extractor,
    project_repo,
    proposal_repo,
)
from app.demo import scope
from app.projects.models import PoolField, TaggedBool, TaggedFloat, TaggedInt, WetRoomKindRecord
from app.projects.routes import base_routes as project_base_routes
from app.projects.update import ProjectUpdateDiff, apply_project_update
from app.requirements import router as requirements_router
from app.requirements.parser import (
    BriefExtraction,
    FixtureDemand,
    RequirementParser,
    normalize_extraction,
)

REQ, INF, UNK = "requested", "inferred", "unknown"


def _brief(*, bedrooms=3, demand: FixtureDemand | None = None) -> BriefExtraction:
    return BriefExtraction(
        floors=TaggedInt(value=1, source=INF),
        bedrooms=TaggedInt(value=bedrooms, source=REQ),
        safe_room=TaggedBool(value=True, source=REQ),
        parking_spaces=TaggedInt(value=0, source=REQ),
        pool=PoolField(requested=TaggedBool(value=None, source=UNK),
                       length_m=TaggedFloat(value=None, source=UNK), width_m=TaggedFloat(value=None, source=UNK)),
        open_plan=TaggedBool(value=True, source=REQ),
        wet_room_demand=demand or FixtureDemand(),
    )


class _CannedParser(RequirementParser):
    """What the live parser does after the model answers: normalize. The model's part is canned."""

    def __init__(self, brief: BriefExtraction):
        self.brief = brief

    def parse(self, description: str):
        return normalize_extraction(self.brief)


def _project(client: TestClient, monkeypatch, brief: BriefExtraction) -> str:
    monkeypatch.setattr(requirements_router, "parser", _CannedParser(brief))
    project_id = client.post("/projects", json={
        **PROJECT_PAYLOAD, "plot_area_m2": 352.0, "plot_width_m": 16.0, "plot_depth_m": 22.0,
        "street_facing_side": "NORTH", "built_area_m2": 150.0,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE", "target_area_m2": 150.0,
                               "area_m2": 150.0, "width_m": 12.0, "depth_m": 12.5},
    }).json()["project_id"]
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    return project_id


MASTER_TOILET_ONLY = {"host": "MASTER_BEDROOM", "fixtures": "toilet_only", "source_text": "חדר הורים עם שירותים"}
MASTER_BATH = {"host": "MASTER_BEDROOM", "fixtures": "bath", "source_text": "חדר הורים עם מקלחת"}
GUEST = {"source_text": "שירותי אורחים"}


# ------------------------------------------------------------------ Phase 1: derived, not counted

def test_the_count_is_derived_from_the_rooms_and_the_model_has_no_count_field():
    assert "wet_rooms" not in BriefExtraction.model_fields
    assert "wet_room_kinds" not in BriefExtraction.model_fields
    extraction = normalize_extraction(_brief(demand=FixtureDemand(
        bathrooms=[{"source_text": "מקלחת"}], toilet_mentions=2, toilet_source_text="2 שירותים")))
    assert extraction.wet_rooms.value == len(extraction.wet_room_kinds) == 2
    assert [(k.kind, k.origin) for k in extraction.wet_room_kinds] == [
        ("guest_wc", "count_derived"), ("shared_bathroom", "explicit")]


def test_one_bathroom_plus_two_toilets_is_stored_as_a_bathroom_and_one_derived_wc_and_plans(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(demand=FixtureDemand(
        bathrooms=[{"source_text": "מקלחת"}], toilet_mentions=2, toilet_source_text="2 שירותים")))
    stored = project_base_routes.repository.get(project_id)
    assert stored.wet_rooms.value == 2 and stored.wet_room_questions == []
    assert [(r.kind, r.origin, r.source) for r in stored.wet_room_kinds] == [
        ("guest_wc", "count_derived", "requested"), ("shared_bathroom", "explicit", "requested")]
    review = client.get(f"/projects/{project_id}/review").json()
    assert review["wet_room_problem"] is None
    # The derived room is called derived on the screen, and the plan lists it.
    assert review["wet_room_kinds"][0]["origin"] == "count_derived"
    assert review["wet_room_kinds"][0]["label"].startswith("נגזר מהספירה")
    assert review["wet_room_kinds"][1]["origin"] == "explicit"
    assert "שירותים" in review["planned_rooms"]
    assert scope.check_supported(stored) is None


def test_nothing_said_about_wet_rooms_keeps_the_legacy_inferred_bathroom(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief())
    stored = project_base_routes.repository.get(project_id)
    assert (stored.wet_rooms.value, stored.wet_rooms.source.value) == (1, "inferred")
    assert stored.wet_room_kinds == [] and stored.wet_room_questions == []


# ------------------------------------------------------------------ a reading left open

def test_a_bedroom_with_only_a_toilet_named_blocks_generation_with_the_question_and_its_proposal(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=3, demand=FixtureDemand(
        attached=[MASTER_TOILET_ONLY], separate_wcs=[GUEST])))
    stored = project_base_routes.repository.get(project_id)
    # No shower was invented: the only stored room is the one named as a room.
    assert [r.kind for r in stored.wet_room_kinds] == ["guest_wc"] and stored.wet_rooms.value == 1
    assert [q.code for q in stored.wet_room_questions] == ["ATTACHED_TOILET_ONLY"]

    rejection = scope.check_supported(stored)
    assert rejection.code is scope.ScopeCode.NEEDS_CLARIFICATION
    assert "חדר הורים עם שירותים" in rejection.message
    # The proposal is complete: the ensuite the words may have meant PLUS the shared bathroom the
    # two other bedrooms need (I4) — one click, one plannable programme.
    assert [(r.kind, r.host, r.origin) for r in rejection.proposal.wet_room_kinds] == [
        ("ensuite", "MASTER_BEDROOM", "explicit"), ("guest_wc", None, "explicit"),
        ("shared_bathroom", None, "count_derived")]
    assert rejection.proposal.wet_rooms == 3

    review = client.get(f"/projects/{project_id}/review").json()
    assert review["wet_room_problem"] == rejection.message
    assert review["wet_room_proposal"]["wet_rooms"] == 3
    assert [k["kind"] for k in review["wet_room_proposal"]["wet_room_kinds"]] == ["ensuite", "guest_wc", "shared_bathroom"]
    assert review["planned_rooms"] == []
    assert client.post(f"/projects/{project_id}/design/demo").json()["detail"]["code"] == "NEEDS_CLARIFICATION"


def test_the_question_is_asked_before_the_count_envelope_is_judged(client, monkeypatch):
    """"חדר הורים עם שירותים" alone stores zero rooms; that is a question, not "0 is unsupported"."""
    project_id = _project(client, monkeypatch, _brief(bedrooms=1, demand=FixtureDemand(attached=[MASTER_TOILET_ONLY])))
    stored = project_base_routes.repository.get(project_id)
    assert stored.wet_rooms.value == 0
    rejection = scope.check_supported(stored)
    assert rejection.code is scope.ScopeCode.NEEDS_CLARIFICATION
    assert [r.kind for r in rejection.proposal.wet_room_kinds] == ["ensuite"]


def test_accepting_the_proposal_on_the_review_screen_answers_the_question_and_plans(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=3, demand=FixtureDemand(
        attached=[MASTER_TOILET_ONLY], separate_wcs=[GUEST])))
    proposal = client.get(f"/projects/{project_id}/review").json()["wet_room_proposal"]
    review = client.put(f"/projects/{project_id}/review", json={
        "wet_rooms": proposal["wet_rooms"], "wet_room_kinds": proposal["wet_room_kinds"]}).json()
    assert review["wet_room_problem"] is None and review["wet_room_proposal"] is None
    stored = project_base_routes.repository.get(project_id)
    assert stored.wet_room_questions == []
    # Rows the person confirmed are the person's word now, whatever proposed them.
    assert [(r.kind, r.origin) for r in stored.wet_room_kinds] == [
        ("ensuite", "explicit"), ("guest_wc", "explicit"), ("shared_bathroom", "explicit")]
    assert scope.check_supported(stored) is None


def test_editing_the_rows_any_other_way_also_answers_the_question(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=2, demand=FixtureDemand(
        attached=[MASTER_TOILET_ONLY], separate_wcs=[GUEST])))
    client.put(f"/projects/{project_id}/review", json={
        "wet_rooms": 2, "wet_room_kinds": [{"kind": "shared_bathroom"}, {"kind": "guest_wc"}]})
    stored = project_base_routes.repository.get(project_id)
    assert stored.wet_room_questions == [] and [r.kind for r in stored.wet_room_kinds] == ["shared_bathroom", "guest_wc"]


def test_editing_another_field_leaves_the_question_standing(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=2, demand=FixtureDemand(
        attached=[MASTER_TOILET_ONLY], separate_wcs=[GUEST])))
    client.put(f"/projects/{project_id}/review", json={"bedrooms": 1})
    assert [q.code for q in project_base_routes.repository.get(project_id).wet_room_questions] == ["ATTACHED_TOILET_ONLY"]


def test_a_chat_edit_of_the_rows_answers_the_question_too(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=2, demand=FixtureDemand(
        attached=[MASTER_TOILET_ONLY], separate_wcs=[GUEST])))
    result = apply_project_update(
        project_base_routes.repository, project_base_routes.design_version_repository, project_id,
        source="CHAT",
        diff=ProjectUpdateDiff(wet_rooms=TaggedInt(value=2, source=REQ), wet_room_kinds=[
            WetRoomKindRecord(kind="ensuite", host="MASTER_BEDROOM"), WetRoomKindRecord(kind="shared_bathroom")]))
    assert result.project.wet_room_questions == []
    assert any(e.field == "wet_room_questions" for e in result.project.change_log)


def test_toilets_with_no_bathroom_named_two_or_more_is_a_question_with_the_absorbing_reading_stored(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=3, demand=FixtureDemand(
        toilet_mentions=3, toilet_source_text="3 שירותים")))
    stored = project_base_routes.repository.get(project_id)
    assert [(r.kind, r.origin) for r in stored.wet_room_kinds] == [
        ("guest_wc", "count_derived"), ("guest_wc", "count_derived"), ("shared_bathroom", "count_derived")]
    rejection = scope.check_supported(stored)
    assert rejection.code is scope.ScopeCode.NEEDS_CLARIFICATION and "3 שירותים" in rejection.message
    assert [r.kind for r in rejection.proposal.wet_room_kinds] == ["guest_wc", "guest_wc", "shared_bathroom"]
    # One bare toilet is simply the house's bathroom — no question.
    one = _project(client, monkeypatch, _brief(bedrooms=3, demand=FixtureDemand(toilet_mentions=1, toilet_source_text="שירותים")))
    assert project_base_routes.repository.get(one).wet_room_questions == []
    assert client.get(f"/projects/{one}/review").json()["wet_room_problem"] is None


# ------------------------------------------------------------------ Phase 3: I4 offers its answer

def test_ensuite_plus_guest_wc_with_more_bedrooms_proposes_adding_a_shared_bathroom(client, monkeypatch):
    project_id = _project(client, monkeypatch, _brief(bedrooms=3, demand=FixtureDemand(
        attached=[MASTER_BATH], separate_wcs=[GUEST])))
    stored = project_base_routes.repository.get(project_id)
    assert stored.wet_room_questions == []          # nothing was left open by the parser
    rejection = scope.check_supported(stored)
    assert rejection.code is scope.ScopeCode.NEEDS_CLARIFICATION and "חדר שינה 1" in rejection.message
    assert rejection.proposal.summary.startswith("להוסיף חדר רחצה משותף")
    assert [(r.kind, r.origin) for r in rejection.proposal.wet_room_kinds] == [
        ("ensuite", "explicit"), ("guest_wc", "explicit"), ("shared_bathroom", "count_derived")]
    review = client.get(f"/projects/{project_id}/review").json()
    assert review["wet_room_proposal"]["summary"] == rejection.proposal.summary
    # Accepting it is the same edit as typing it.
    accepted = client.put(f"/projects/{project_id}/review", json={
        "wet_rooms": 3, "wet_room_kinds": review["wet_room_proposal"]["wet_room_kinds"]}).json()
    assert accepted["wet_room_problem"] is None
    assert [r["kind"] for r in accepted["wet_room_kinds"]] == ["ensuite", "guest_wc", "shared_bathroom"]


def test_the_i4_proposal_is_not_offered_when_it_would_leave_the_envelope():
    """Three stated rooms plus one more is four — outside SUPPORTED_WET_ROOMS, so the question is
    asked without a one-click answer rather than with one generation would refuse."""
    from app.projects.models import Project
    project = Project.model_validate({
        **PROJECT_PAYLOAD, "project_id": "p", "status": "created",
        "created_at": "2026-09-15T00:00:00Z", "updated_at": "2026-09-15T00:00:00Z",
        "bedrooms": {"value": 4, "source": REQ}, "wet_rooms": {"value": 3, "source": REQ},
        "wet_room_kinds": [{"kind": "ensuite", "host": "MASTER_BEDROOM"}, {"kind": "ensuite", "host": "BEDROOM"},
                           {"kind": "guest_wc"}],
    })
    rejection = scope.wet_room_rejection(project, 4, 3)
    assert rejection is not None and rejection.proposal is None


def test_a_legacy_record_without_origin_loads_as_explicit_and_plans_unchanged():
    from app.projects.models import Project
    project = Project.model_validate({
        **PROJECT_PAYLOAD, "project_id": "p", "status": "created",
        "created_at": "2026-09-15T00:00:00Z", "updated_at": "2026-09-15T00:00:00Z",
        "bedrooms": {"value": 3, "source": REQ}, "wet_rooms": {"value": 2, "source": REQ},
        "wet_room_kinds": [{"kind": "ensuite", "host": "MASTER_BEDROOM"}, {"kind": "shared_bathroom"}],
    })
    assert [r.origin for r in project.wet_room_kinds] == ["explicit", "explicit"]
    assert project.wet_room_questions == []
    assert scope.wet_room_rejection(project, 3, 2) is None
