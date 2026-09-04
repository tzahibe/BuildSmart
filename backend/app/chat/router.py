from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.chat.assistant import ChatAssistant, OpenAIChatAssistant
from app.chat.models import ChatMessage, ChatMessageCreate, ChatRole, Conversation
from app.chat.repository import ConversationRepository, JsonFileConversationRepository
from app.projects.routes import base_routes as project_routes

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "conversations.json"

router = APIRouter(prefix="/projects", tags=["chat"])
repository: ConversationRepository = JsonFileConversationRepository(_DATA_FILE)
assistant: ChatAssistant = OpenAIChatAssistant()


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
        reply_text = assistant.reply(project, history, data.content)
    except Exception:
        # Nothing is persisted on failure — the user's message is never saved without a reply
        # (see contracts/chat-api.md's atomicity note), so the client can simply resend.
        raise HTTPException(
            status_code=502,
            detail="Assistant is unavailable, please try again",
        ) from None

    assistant_message = ChatMessage(
        role=ChatRole.assistant, content=reply_text, created_at=datetime.now(UTC)
    )

    return repository.append_messages(project_id, new_messages=[user_message, assistant_message])
