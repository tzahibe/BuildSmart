"""specs/007 Phase 5 — the wet-room kinds travel from the brief through storage, review and chat, and
Generate stays blocked while they leave a bedroom without a bathroom (decision A, B)."""
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
from app.chat.intent import ChatIntentExtraction, FieldUpdateIntent, ProposalActionType, WetRoomKindIntent
from app.projects.models import PoolField, TaggedBool, TaggedFloat, TaggedInt, WetRoomKindRecord
from app.projects.routes import base_routes as project_base_routes
from app.projects.update import ProjectUpdateDiff, apply_project_update
from app.requirements import router as requirements_router
from app.requirements.parser import RequirementExtraction, RequirementParser, WetRoomKindItem
from app.requirements.router import reconcile_wet_rooms


REQ, INF, UNK = "requested", "inferred", "unknown"


def _extraction(*, bedrooms=2, wet_rooms=2, wet_source=REQ, kinds=()) -> RequirementExtraction:
    return RequirementExtraction(
        floors=TaggedInt(value=1, source=INF),
        bedrooms=TaggedInt(value=bedrooms, source=REQ),
        safe_room=TaggedBool(value=True, source=REQ),
        parking_spaces=TaggedInt(value=0, source=REQ),
        pool=PoolField(requested=TaggedBool(value=None, source=UNK),
                       length_m=TaggedFloat(value=None, source=UNK), width_m=TaggedFloat(value=None, source=UNK)),
        wet_rooms=TaggedInt(value=wet_rooms, source=wet_source),
        open_plan=TaggedBool(value=True, source=REQ),
        wet_room_kinds=list(kinds),
    )


ENSUITE = WetRoomKindItem(kind="ensuite", host="MASTER_BEDROOM", source_text="חדר הורים עם שירותים")
GUEST_WC = WetRoomKindItem(kind="guest_wc", source_text="שירותי אורחים")
SHARED = WetRoomKindItem(kind="shared_bathroom", source_text="חדר רחצה")


# ------------------------------------------------------------------ parser -> records (FR-1, §5)

def test_fewer_kinds_than_the_count_are_stored_as_stated_and_the_rest_are_unstated():
    count, records, unresolved = reconcile_wet_rooms(_extraction(wet_rooms=3, kinds=[ENSUITE]))
    assert (count.value, count.source) == (3, REQ)
    assert [r.kind for r in records] == ["ensuite"] and unresolved == []


def test_named_kinds_make_the_count_when_none_was_stated():
    count, records, unresolved = reconcile_wet_rooms(
        _extraction(wet_rooms=1, wet_source=INF, kinds=[ENSUITE, GUEST_WC]))
    assert (count.value, count.source) == (2, REQ)
    assert [r.kind for r in records] == ["ensuite", "guest_wc"] and unresolved == []


def test_kinds_beyond_a_stated_count_are_a_contradiction_the_person_settles():
    count, records, unresolved = reconcile_wet_rooms(_extraction(wet_rooms=1, kinds=[ENSUITE, GUEST_WC]))
    assert count.value == 1 and [r.kind for r in records] == ["ensuite"]
    assert len(unresolved) == 1 and unresolved[0].severity.value == "ambiguous"
    assert "שירותי אורחים" in unresolved[0].text


# ------------------------------------------------------------ brief -> review -> generate (FR-3)

class _CannedParser(RequirementParser):
    def __init__(self, extraction):
        self.extraction = extraction

    def parse(self, description: str):
        return self.extraction


@pytest.fixture
def parsed(client: TestClient, monkeypatch):
    """A project whose brief parsed to ensuite + guest WC with two bedrooms — decision A's case."""
    monkeypatch.setattr(requirements_router, "parser",
                        _CannedParser(_extraction(bedrooms=2, wet_rooms=2, kinds=[ENSUITE, GUEST_WC])))
    project_id = client.post("/projects", json={
        **PROJECT_PAYLOAD, "plot_area_m2": 352.0, "plot_width_m": 16.0, "plot_depth_m": 22.0, "street_facing_side": "NORTH",
        "built_area_m2": 150.0,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE", "target_area_m2": 150.0,
                               "area_m2": 150.0, "width_m": 12.0, "depth_m": 12.5},
    }).json()["project_id"]
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    return project_id


def test_review_shows_each_wet_room_by_kind_with_its_source_and_names_the_problem(client, parsed):
    review = client.get(f"/projects/{parsed}/review").json()
    rows = review["wet_room_kinds"]
    assert [(r["kind"], r["host"], r["specified"]) for r in rows] == [
        ("ensuite", "MASTER_BEDROOM", True), ("guest_wc", None, True)]
    assert rows[0]["source_text"] == "חדר הורים עם שירותים"
    assert rows[0]["can_be_flexible"] is False
    # Decision A: the second bedroom has no bathroom it can reach — said before Generate.
    assert review["wet_room_problem"] and "חדר שינה 1" in review["wet_room_problem"]
    assert review["planned_rooms"] == []


def test_generate_is_refused_with_needs_clarification_while_the_problem_stands(client, parsed):
    response = client.post(f"/projects/{parsed}/design/demo")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "NEEDS_CLARIFICATION"


def test_a_review_edit_that_answers_the_question_clears_it_and_is_authoritative(client, parsed):
    body = {"wet_rooms": 3, "wet_room_kinds": [
        {"kind": "ensuite", "host": "MASTER_BEDROOM"}, {"kind": "guest_wc"}, {"kind": "shared_bathroom"}]}
    review = client.put(f"/projects/{parsed}/review", json=body).json()
    assert review["wet_room_problem"] is None
    assert [r["kind"] for r in review["wet_room_kinds"]] == ["ensuite", "guest_wc", "shared_bathroom"]
    assert review["wet_room_kinds"][2]["can_be_flexible"] is True
    assert "שירותים" in review["planned_rooms"]
    stored = project_base_routes.repository.get(parsed)
    assert [r.source for r in stored.wet_room_kinds] == ["requested"] * 3
    # Rows the person left as the brief said keep the brief's words; the new row has none.
    assert [r.source_text for r in stored.wet_room_kinds] == ["חדר הורים עם שירותים", "שירותי אורחים", ""]


def test_editing_another_field_keeps_what_the_brief_said_about_the_wet_rooms(client, parsed):
    client.put(f"/projects/{parsed}/review", json={"bedrooms": 1})
    stored = project_base_routes.repository.get(parsed)
    assert [r.kind for r in stored.wet_room_kinds] == ["ensuite", "guest_wc"]
    # ...and with one bedroom the same rooms are no longer a question.
    assert client.get(f"/projects/{parsed}/review").json()["wet_room_problem"] is None


def test_lowering_the_count_drops_rows_from_the_end_raising_it_adds_unstated_ones(client, parsed):
    review = client.put(f"/projects/{parsed}/review", json={"wet_rooms": 1}).json()
    assert [r["kind"] for r in review["wet_room_kinds"]] == ["ensuite"]
    review = client.put(f"/projects/{parsed}/review", json={"wet_rooms": 3}).json()
    assert [(r["kind"], r["specified"]) for r in review["wet_room_kinds"]] == [
        ("ensuite", True), ("shared_bathroom", False), ("shared_bathroom", False)]
    assert review["wet_room_kinds"][1]["label"].startswith("לא צוין")


def test_more_rows_than_the_count_is_refused_not_trimmed(client, parsed):
    response = client.put(f"/projects/{parsed}/review", json={
        "wet_rooms": 1, "wet_room_kinds": [{"kind": "ensuite"}, {"kind": "guest_wc"}]})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "WET_ROOM_KINDS_EXCEED_COUNT"


def test_a_legacy_project_reviews_as_defaults_not_as_statements(client, monkeypatch):
    monkeypatch.setattr(requirements_router, "parser", _CannedParser(_extraction(bedrooms=3, wet_rooms=2)))
    project_id = client.post("/projects", json=PROJECT_PAYLOAD).json()["project_id"]
    client.post(f"/projects/{project_id}/requirements")
    rows = client.get(f"/projects/{project_id}/review").json()["wet_room_kinds"]
    assert [(r["kind"], r["specified"]) for r in rows] == [("ensuite", False), ("shared_bathroom", False)]
    assert all(r["label"].startswith("לא צוין — ברירת מחדל") for r in rows)


# --------------------------------------------------------------------------- chat (FR-4)

def _chat_project(client: TestClient) -> str:
    project_id = client.post("/projects", json=PROJECT_PAYLOAD).json()["project_id"]
    project_base_routes.repository.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=1, source=REQ), bedrooms=TaggedInt(value=3, source=REQ),
        safe_room=TaggedBool(value=False, source=REQ), parking_spaces=TaggedInt(value=None, source=UNK),
        pool=None, wet_rooms=TaggedInt(value=2, source=REQ),
        wet_room_kinds=[WetRoomKindRecord(kind="ensuite", host="MASTER_BEDROOM", source="requested"),
                        WetRoomKindRecord(kind="shared_bathroom", source="requested")],
    )
    return project_id


def _send(client, project_id, text):
    response = client.post(f"/projects/{project_id}/chat/messages", json={"content": text})
    assert response.status_code == 200
    return response.json()


def test_chat_marks_a_shared_bathroom_flexible_through_a_confirmed_proposal(client, fake_intent_extractor):
    project_id = _chat_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_wet_room_kind,
        wet_room_kind=WetRoomKindIntent(index=2, strength="flexible"))
    conversation = _send(client, project_id, "חדר הרחצה השני — לא משנה איפה, אפשר גם צמוד לחדר")
    last = conversation["messages"][-1]
    assert last["proposal"] is not None and "גמיש" in last["content"]
    response = client.post(f"/projects/{project_id}/chat/proposals/{last['proposal']['proposal_id']}/confirm")
    assert response.status_code == 200
    stored = project_base_routes.repository.get(project_id)
    assert [(r.kind, r.strength) for r in stored.wet_room_kinds] == [("ensuite", "required"), ("shared_bathroom", "flexible")]
    assert stored.change_log[-1].field == "wet_room_kinds" and stored.change_log[-1].source == "CHAT"


def test_chat_refuses_to_make_an_ensuite_flexible(client, fake_intent_extractor):
    project_id = _chat_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_wet_room_kind,
        wet_room_kind=WetRoomKindIntent(index=1, strength="flexible"))
    conversation = _send(client, project_id, "חדר הרחצה של ההורים גמיש")
    assert conversation["messages"][-1]["proposal"] is None
    assert "גמיש" in conversation["messages"][-1]["content"]


def test_chat_will_not_pick_a_wet_room_the_message_did_not_name(client, fake_intent_extractor):
    project_id = _chat_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_wet_room_kind, wet_room_kind=WetRoomKindIntent(index=None, kind="guest_wc"))
    conversation = _send(client, project_id, "שיהיו שירותי אורחים")
    assert conversation["messages"][-1]["proposal"] is None


def test_chat_changes_the_wet_room_count_like_any_other_field(client, fake_intent_extractor):
    project_id = _chat_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields, field_update=FieldUpdateIntent(field="wet_rooms", int_value=3))
    conversation = _send(client, project_id, "שלושה חדרי רחצה")
    proposal_id = conversation["messages"][-1]["proposal"]["proposal_id"]
    body = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm").json()
    assert body["project"]["wet_rooms"]["value"] == 3
    # The stated rows survive; the third room is simply unstated.
    assert [r["kind"] for r in body["project"]["wet_room_kinds"]] == ["ensuite", "shared_bathroom"]


def test_apply_project_update_refuses_rows_this_build_cannot_read_or_beyond_the_count(client):
    project_id = _chat_project(client)
    with pytest.raises(ValueError):
        apply_project_update(project_base_routes.repository, project_base_routes.design_version_repository,
                             project_id, source="SETTINGS",
                             diff=ProjectUpdateDiff(wet_room_kinds=[WetRoomKindRecord(kind="sauna")]))
    with pytest.raises(ValueError):
        apply_project_update(project_base_routes.repository, project_base_routes.design_version_repository,
                             project_id, source="SETTINGS",
                             diff=ProjectUpdateDiff(wet_room_kinds=[WetRoomKindRecord()] * 3))
