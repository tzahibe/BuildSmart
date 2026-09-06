from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.chat.assistant import ChatAssistant, OpenAIChatAssistant
from app.chat.intent import ChatIntentExtractor, OpenAIChatIntentExtractor, ProposalActionType
from app.chat.models import ChatMessage, ChatMessageCreate, ChatRole, Conversation
from app.chat.mutation_reply import describe_rollback_result, describe_update_result
from app.chat.proposal_builder import build_proposal
from app.chat.proposals import (
    JsonFileProposalRepository,
    Proposal,
    ProposalRepository,
    ProposalSummary,
)
from app.chat.repository import ConversationRepository, JsonFileConversationRepository
from app.projects.models import Project
from app.projects.routes import base_routes as project_routes
from app.projects.update import ProjectNotFoundError, apply_project_update, rollback_to_design_version

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "conversations.json"
_PROPOSALS_FILE = Path(__file__).resolve().parent.parent / "data" / "chat_proposals.json"

router = APIRouter(prefix="/projects", tags=["chat"])
repository: ConversationRepository = JsonFileConversationRepository(_DATA_FILE)
proposal_repository: ProposalRepository = JsonFileProposalRepository(_PROPOSALS_FILE)
assistant: ChatAssistant = OpenAIChatAssistant()
intent_extractor: ChatIntentExtractor = OpenAIChatIntentExtractor()


class ChatMutationResponse(BaseModel):
    conversation: Conversation
    # Only set when a mutation actually happened (confirm) — `None` for cancel, or when confirm hits a
    # design-affecting update whose regeneration failed (the field/preference change itself still
    # persisted — see app/chat/mutation_reply.py — but the caller should still re-render from the
    # returned `conversation`'s explanation; `project` being present always means "here is the latest
    # state, replace what you have," same contract as SettingsPage's `updateProject`).
    project: Project | None = None


def _append(project_id: str, *messages: ChatMessage) -> Conversation:
    return repository.append_messages(project_id, new_messages=list(messages))


@router.get("/{project_id}/chat", response_model=Conversation)
def get_conversation(project_id: str) -> Conversation:
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return repository.get(project_id)


@router.post("/{project_id}/chat/messages", response_model=Conversation)
def send_chat_message(project_id: str, data: ChatMessageCreate) -> Conversation:
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    history = repository.get(project_id).messages
    user_message = ChatMessage(role=ChatRole.user, content=data.content, created_at=datetime.now(UTC))

    try:
        design_versions = project_routes.design_version_repository.list_for_project(project_id)
        extraction = intent_extractor.extract(project, design_versions, history, data.content)
    except Exception:
        raise HTTPException(status_code=502, detail="Assistant is unavailable, please try again") from None

    if extraction.action == ProposalActionType.no_action:
        # Completely unchanged path: the existing grounded Q&A assistant, no proposal involved at all.
        try:
            reply_text = assistant.reply(project, history, data.content)
        except Exception:
            raise HTTPException(status_code=502, detail="Assistant is unavailable, please try again") from None
        assistant_message = ChatMessage(role=ChatRole.assistant, content=reply_text, created_at=datetime.now(UTC))
        return _append(project_id, user_message, assistant_message)

    result = build_proposal(project, design_versions, extraction)
    if result.proposal is None:
        assistant_message = ChatMessage(role=ChatRole.assistant, content=result.message, created_at=datetime.now(UTC))
        return _append(project_id, user_message, assistant_message)

    proposal_repository.save(result.proposal)
    reply_text = f"{result.proposal.summary}\n\nלאשר את השינוי?"
    assistant_message = ChatMessage(
        role=ChatRole.assistant,
        content=reply_text,
        created_at=datetime.now(UTC),
        proposal=ProposalSummary(
            proposal_id=result.proposal.proposal_id, action=result.proposal.action, summary=result.proposal.summary
        ),
    )
    return _append(project_id, user_message, assistant_message)


def _load_pending_or_409(project_id: str, proposal_id: str) -> Proposal:
    proposal = proposal_repository.get_pending_for_project(project_id, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "PROPOSAL_STALE", "message": "ההצעה הזו כבר אינה בתוקף — יתכן שהיא בוטלה או הוחלפה בהצעה חדשה יותר."},
        )
    return proposal


@router.post("/{project_id}/chat/proposals/{proposal_id}/confirm", response_model=ChatMutationResponse)
def confirm_proposal(project_id: str, proposal_id: str) -> ChatMutationResponse:
    if project_routes.repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    proposal = _load_pending_or_409(project_id, proposal_id)
    # Consumed BEFORE executing — a duplicate/concurrent confirm click on the same proposal can't apply
    # it twice, since the second call's lookup above would already find it consumed.
    proposal_repository.mark_consumed(project_id, proposal_id)

    if proposal.action == ProposalActionType.rollback_design_version:
        try:
            updated = rollback_to_design_version(
                project_routes.repository, project_routes.design_version_repository, project_id, proposal.rollback_design_version_id
            )
        except (ProjectNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        reply_text = describe_rollback_result(proposal, updated)
        assistant_message = ChatMessage(role=ChatRole.assistant, content=reply_text, created_at=datetime.now(UTC))
        conversation = _append(project_id, assistant_message)
        return ChatMutationResponse(conversation=conversation, project=updated)

    # UPDATE_PROJECT_FIELDS / ADD_PREFERENCE / UPDATE_PREFERENCE / REMOVE_PREFERENCE all go through the
    # exact same `apply_project_update` Settings uses — no chat-specific mutation logic. Note
    # `result.design_error` (set when impact=REGENERATE_DESIGN but generation failed) is deliberately
    # NOT raised as an HTTP error here — the field/preference update itself already succeeded and was
    # persisted (see apply_project_update's own docstring), so `describe_update_result` reports both the
    # applied change and the regeneration failure in one reply, rather than the request looking like it
    # failed outright.
    result = apply_project_update(
        project_routes.repository,
        project_routes.design_version_repository,
        project_id,
        source="CHAT",
        diff=proposal.diff,
    )
    reply_text = describe_update_result(proposal, result)
    assistant_message = ChatMessage(role=ChatRole.assistant, content=reply_text, created_at=datetime.now(UTC))
    conversation = _append(project_id, assistant_message)
    return ChatMutationResponse(conversation=conversation, project=result.project)


@router.post("/{project_id}/chat/proposals/{proposal_id}/cancel", response_model=ChatMutationResponse)
def cancel_proposal(project_id: str, proposal_id: str) -> ChatMutationResponse:
    if project_routes.repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    _load_pending_or_409(project_id, proposal_id)
    proposal_repository.mark_consumed(project_id, proposal_id)

    assistant_message = ChatMessage(role=ChatRole.assistant, content="בסדר, לא ביצעתי את השינוי.", created_at=datetime.now(UTC))
    conversation = _append(project_id, assistant_message)
    return ChatMutationResponse(conversation=conversation, project=None)
