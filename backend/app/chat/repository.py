import json
from abc import ABC, abstractmethod
from pathlib import Path

from app.chat.models import ChatMessage, Conversation


class ConversationRepository(ABC):
    @abstractmethod
    def get(self, project_id: str) -> Conversation:
        """Returns an empty Conversation (not None/404) when nothing has been stored yet — a project
        simply has no messages until the first one is sent (data-model.md)."""

    @abstractmethod
    def append_messages(self, project_id: str, *, new_messages: list[ChatMessage]) -> Conversation:
        """Appends all of `new_messages` in one call — a single request either persists the full
        user+assistant exchange or none of it (see contracts/chat-api.md's atomicity note)."""


class JsonFileConversationRepository(ConversationRepository):
    """Stores conversations in a single JSON file, keyed by project_id — same deliberately minimal,
    temporary storage mechanism as JsonFileProjectRepository (see
    specs/001-project-creation/research.md), in a separate file from projects.json (see
    specs/004-design-viewer-chat/research.md §7 for why not merged into Project)."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def _load(self) -> dict[str, list[dict]]:
        if not self._file_path.exists():
            return {}
        with self._file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, list[dict]]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def get(self, project_id: str) -> Conversation:
        data = self._load()
        raw_messages = data.get(project_id, [])
        messages = [ChatMessage.model_validate(entry) for entry in raw_messages]
        return Conversation(project_id=project_id, messages=messages)

    def append_messages(self, project_id: str, *, new_messages: list[ChatMessage]) -> Conversation:
        data = self._load()
        raw_messages = data.get(project_id, [])
        raw_messages.extend(json.loads(message.model_dump_json()) for message in new_messages)
        data[project_id] = raw_messages
        self._save(data)

        messages = [ChatMessage.model_validate(entry) for entry in raw_messages]
        return Conversation(project_id=project_id, messages=messages)
