from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator

from app.chat.proposals import ProposalSummary


class ChatRole(str, Enum):
    user = "user"
    assistant = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime
    # Set only on an assistant message that is proposing a change and awaiting confirmation — see
    # app/chat/router.py. `None` for every plain conversational message (the overwhelming majority,
    # unchanged from before this milestone) and for outcome messages after a confirm/cancel.
    proposal: ProposalSummary | None = None


class Conversation(BaseModel):
    project_id: str
    messages: list[ChatMessage]


class ChatMessageCreate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty")
        return stripped
