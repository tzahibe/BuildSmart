from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator


class ChatRole(str, Enum):
    user = "user"
    assistant = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime


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
