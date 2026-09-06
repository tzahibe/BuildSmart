"""Tests for conversational project editing (app/chat/{intent,proposals,proposal_builder,
mutation_reply}.py + the new endpoints in app/chat/router.py). Uses a `FakeChatIntentExtractor` (see
tests/test_chat.py) to control exactly what "intent" a message produces — no real OpenAI calls, matching
this codebase's existing hermeticity convention. `MockArchitectModelGateway` (fast, deterministic) is
used wherever a proposal's confirmation triggers a design regeneration.
"""

import pytest
from fastapi.testclient import TestClient

from app.architect.gateway import MockArchitectModelGateway
from app.chat.intent import ChatIntentExtraction, FieldUpdateIntent, PreferenceIntent, ProposalActionType, RollbackIntent
from app.design.pipeline import generate_design_via_solver
from app.projects.models import TaggedBool, TaggedInt
from app.projects.routes import base_routes as project_base_routes

# Reuses test_chat.py's fixtures verbatim (client already wires the fake assistant/intent-extractor and
# all four repositories) — importing them here makes pytest pick them up as fixtures in this module too.
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


def _create_and_parse_project(client: TestClient) -> str:
    response = client.post("/projects", json=PROJECT_PAYLOAD)
    project_id = response.json()["project_id"]
    project_base_routes.repository.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=1, source="requested"),
        bedrooms=TaggedInt(value=3, source="requested"),
        safe_room=TaggedBool(value=False, source="requested"),
        parking_spaces=TaggedInt(value=None, source="unknown"),
        pool=None,
    )
    return project_id


def _send(client: TestClient, project_id: str, text: str) -> dict:
    response = client.post(f"/projects/{project_id}/chat/messages", json={"content": text})
    assert response.status_code == 200
    return response.json()


def _pending_proposal_id(conversation: dict) -> str:
    last = conversation["messages"][-1]
    assert last["proposal"] is not None
    return last["proposal"]["proposal_id"]


# --- A: bedrooms 3 -> 4 proposed, confirmed, applied ------------------------------------------------


def test_a_bedrooms_change_is_proposed_confirmed_and_applied(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields,
        field_update=FieldUpdateIntent(field="bedrooms", int_value=4),
    )

    conversation = _send(client, project_id, "בעצם אני רוצה 4 חדרי שינה")
    assert "4" in conversation["messages"][-1]["content"]
    proposal_id = _pending_proposal_id(conversation)

    response = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["bedrooms"]["value"] == 4
    assert body["project"]["change_log"][-1]["source"] == "CHAT"
    room_types = [r["type"] for r in body["project"]["rooms"]]
    assert room_types.count("bedroom") == 4
    assert body["conversation"]["messages"][-1]["content"].startswith("בוצע")


# --- B: safe_room false -> true --------------------------------------------------------------------


def test_b_safe_room_false_to_true(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields,
        field_update=FieldUpdateIntent(field="safe_room", bool_value=True),
    )

    conversation = _send(client, project_id, 'תוסיף ממ"ד')
    proposal_id = _pending_proposal_id(conversation)

    response = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["safe_room"]["value"] is True
    assert any(r["type"] == "safe_room" for r in body["project"]["rooms"])


# --- C: add ADJACENCY preference ---------------------------------------------------------------------


def test_c_add_adjacency_preference_is_no_regen(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.add_preference,
        preference=PreferenceIntent(kind="ADJACENCY", target="kitchen", related_target="living_room", original_text="מטבח גדול ליד הסלון"),
    )

    conversation = _send(client, project_id, "חשוב לי מטבח גדול ליד הסלון")
    proposal_id = _pending_proposal_id(conversation)

    response = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    assert response.status_code == 200
    body = response.json()
    assert len(body["project"]["preferences"]) == 1
    pref = body["project"]["preferences"][0]
    assert pref["kind"] == "ADJACENCY"
    assert pref["source"] == "CHAT"
    assert pref["original_text"] == "מטבח גדול ליד הסלון"
    assert body["project"]["active_design_version_id"] is None  # NO_REGEN — nothing generated


# --- D: user cancels proposal -> no mutation --------------------------------------------------------


def test_d_cancel_proposal_applies_no_mutation(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields,
        field_update=FieldUpdateIntent(field="bedrooms", int_value=4),
    )
    conversation = _send(client, project_id, "בעצם אני רוצה 4 חדרי שינה")
    proposal_id = _pending_proposal_id(conversation)

    response = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/cancel")

    assert response.status_code == 200
    assert response.json()["project"] is None
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["bedrooms"]["value"] == 3


# --- E: stale confirmation rejected ------------------------------------------------------------------


def test_e_stale_confirmation_is_rejected(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)

    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields, field_update=FieldUpdateIntent(field="bedrooms", int_value=4)
    )
    first = _send(client, project_id, "אני רוצה 4 חדרי שינה")
    stale_proposal_id = _pending_proposal_id(first)

    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields, field_update=FieldUpdateIntent(field="bedrooms", int_value=5)
    )
    _send(client, project_id, "בעצם תעשה 5")

    response = client.post(f"/projects/{project_id}/chat/proposals/{stale_proposal_id}/confirm")

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "PROPOSAL_STALE"
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["bedrooms"]["value"] == 3  # neither proposal was ever confirmed


# --- F: invalid field update rejected -----------------------------------------------------------------


def test_f_unresolvable_field_update_is_rejected_with_no_pending_proposal(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    # The model recognized an UPDATE_PROJECT_FIELDS intent but couldn't extract a concrete value or an
    # explicit "unknown" marker — must be rejected, never guessed.
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields,
        field_update=FieldUpdateIntent(field="bedrooms", int_value=None, mark_unknown=False),
    )

    conversation = _send(client, project_id, "אני רוצה לשנות את מספר חדרי השינה")

    assert conversation["messages"][-1]["proposal"] is None
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["bedrooms"]["value"] == 3


# --- G: rollback previous design version --------------------------------------------------------------


def test_g_rollback_to_previous_version_via_chat(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    project = project_base_routes.repository.get(project_id)

    first_design = generate_design_via_solver(project, gateway=MockArchitectModelGateway())
    from app.design.version import DesignVersion
    import uuid
    from datetime import UTC, datetime

    first_version = DesignVersion(
        design_version_id=str(uuid.uuid4()),
        project_id=project_id,
        created_at=datetime.now(UTC),
        supersedes_id=None,
        request_snapshot=first_design.request_snapshot or {},
        adapter_diagnostics=[],
        spec_snapshot=first_design.spec_snapshot or {},
        solver_summary=first_design.solver_summary or {},
        rooms=first_design.rooms,
        design_notes=first_design.design_notes,
    )
    project_base_routes.design_version_repository.append(first_version)
    project_base_routes.repository.replace(
        project_id,
        project.model_copy(
            update={
                "active_design_version_id": first_version.design_version_id,
                "rooms": first_design.rooms,
                "site_width_m": first_design.site_width_m,
                "site_depth_m": first_design.site_depth_m,
                "design_notes": first_design.design_notes,
            }
        ),
    )

    # A second, distinct version (4 bedrooms instead of 3).
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields, field_update=FieldUpdateIntent(field="bedrooms", int_value=4)
    )
    conversation = _send(client, project_id, "אני רוצה 4 חדרי שינה")
    proposal_id = _pending_proposal_id(conversation)
    client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    assert len(project_base_routes.design_version_repository.list_for_project(project_id)) == 2

    # rollback_to_design_version (called by the confirm endpoint below for a ROLLBACK_DESIGN_VERSION
    # proposal) takes no gateway parameter at all — proof by construction that it cannot invoke the
    # Architect Model, independent of what this test asserts afterward.
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.rollback_design_version, rollback=RollbackIntent(target_version_ordinal=1)
    )
    conversation = _send(client, project_id, "תחזיר אותי לגרסה הקודמת")
    proposal_id = _pending_proposal_id(conversation)

    response = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["active_design_version_id"] == first_version.design_version_id
    room_types = [r["type"] for r in body["project"]["rooms"]]
    assert room_types.count("bedroom") == 3


# --- H: chat update creates a new DesignVersion only when impact=REGENERATE_DESIGN --------------------


def test_h_preference_change_via_chat_does_not_create_a_design_version(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.add_preference,
        preference=PreferenceIntent(kind="OTHER", original_text="בית מואר"),
    )
    conversation = _send(client, project_id, "אני רוצה בית מואר")
    proposal_id = _pending_proposal_id(conversation)

    client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    assert project_base_routes.design_version_repository.list_for_project(project_id) == []


# --- I: no competing frontend/chat state after refresh (backend contract half) -------------------------


def test_i_confirm_response_project_matches_a_fresh_get(client: TestClient, fake_intent_extractor):
    project_id = _create_and_parse_project(client)
    fake_intent_extractor.next_extraction = ChatIntentExtraction(
        action=ProposalActionType.update_project_fields, field_update=FieldUpdateIntent(field="bedrooms", int_value=4)
    )
    conversation = _send(client, project_id, "4 חדרי שינה בבקשה")
    proposal_id = _pending_proposal_id(conversation)

    response = client.post(f"/projects/{project_id}/chat/proposals/{proposal_id}/confirm")

    from_confirm = response.json()["project"]
    from_get = client.get(f"/projects/{project_id}").json()
    assert from_confirm == from_get

