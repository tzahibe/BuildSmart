"""Interprets a chat message into a typed, structured intent — NEVER a mutation. This is the ONLY new
thing chat gets this milestone: everything downstream (validating the intent against current Project
state, building a human-readable proposal, and — only after explicit user confirmation — actually
calling `app.projects.update.apply_project_update`/`rollback_to_design_version`) reuses the existing
Project State foundation exactly as-is. See `app/chat/router.py` for how a `ChatIntentExtraction` here
becomes a `Proposal` (`app/chat/proposals.py`) and, later, a real mutation.

`ProposalActionType.no_action` covers both "this message isn't a design-change request at all" (a
question, small talk) and "the model couldn't confidently resolve a concrete intent" — either way,
nothing is proposed and the existing grounded Q&A `ChatAssistant.reply()` handles the reply, completely
unchanged.
"""

import os
from abc import ABC, abstractmethod
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from app.chat.models import ChatMessage, ChatRole
from app.chat.proposal_action import ProposalActionType
from app.design.version import DesignVersion
from app.projects.models import Project, SourceTag


# Deliberately the same 4 fields Settings itself exposes (see SettingsPage.tsx) — `pool`'s nested shape
# is out of scope for chat this milestone, same as it was for Settings.
_UPDATABLE_FIELDS = ("floors", "bedrooms", "safe_room", "parking_spaces")


class FieldUpdateIntent(BaseModel):
    field: Literal["floors", "bedrooms", "safe_room", "parking_spaces"] | None = None
    # Exactly one of these should be set, matching `field` (int fields vs. the bool safe_room field).
    int_value: int | None = None
    bool_value: bool | None = None
    # True when the user is explicitly saying they DON'T know / are unsure — never inferred by us,
    # only ever set here because the model judged the user's own words said so.
    mark_unknown: bool = False


class PreferenceIntent(BaseModel):
    kind: Literal["ROOM_AREA", "ADJACENCY", "PRIVACY", "OTHER"] | None = None
    target: str | None = None
    related_target: str | None = None
    original_text: str | None = None
    # For UPDATE_PREFERENCE/REMOVE_PREFERENCE only: which EXISTING preference (from the list given in
    # the prompt) this refers to — matched by its own original_text, never a preference_id (the model is
    # never told real ids). `app/chat/proposal_builder.py` resolves this back to a real preference_id by
    # exact/case-insensitive text match; an unresolvable or ambiguous match is rejected, never guessed.
    existing_preference_text: str | None = None


class RollbackIntent(BaseModel):
    # 1-indexed ordinal into the project's own design-version history, oldest first — the prompt below
    # enumerates them this way so the model can resolve "the previous version" / "version 2" itself
    # into a concrete number; app/chat/proposal_builder.py only ever looks up an ordinal it's given, it
    # never interprets "previous" itself.
    target_version_ordinal: int | None = None


class ChatIntentExtraction(BaseModel):
    action: ProposalActionType
    field_update: FieldUpdateIntent | None = None
    preference: PreferenceIntent | None = None
    rollback: RollbackIntent | None = None


def _describe_tagged(label: str, value, unit: str = "") -> str:
    if value is None or value.source == SourceTag.unknown:
        return f"{label}: unknown"
    return f"{label}: {value.value}{unit}"


def _build_context(project: Project, design_versions: list[DesignVersion]) -> str:
    lines = [
        "Current project requirements:",
        _describe_tagged("floors", project.floors),
        _describe_tagged("bedrooms", project.bedrooms),
        _describe_tagged("safe_room", project.safe_room),
        _describe_tagged("parking_spaces", project.parking_spaces),
    ]

    if project.preferences:
        lines.append("Existing preferences (refer to one of these EXACTLY by its text for "
                     "UPDATE_PREFERENCE/REMOVE_PREFERENCE — never invent one that isn't listed here):")
        for preference in project.preferences:
            lines.append(f'- [{preference.kind.value}] "{preference.original_text}"')
    else:
        lines.append("Existing preferences: none.")

    if design_versions:
        lines.append(f"Design version history ({len(design_versions)} total, oldest first):")
        for ordinal, version in enumerate(design_versions, start=1):
            marker = " (current)" if version.design_version_id == project.active_design_version_id else ""
            lines.append(f"- version {ordinal}, created {version.created_at.isoformat()}{marker}")
    else:
        lines.append("Design version history: none yet.")

    return "\n".join(lines)


_SYSTEM_PROMPT_TEMPLATE = """\
You interpret one chat message from a user planning a home-building project in BuildSmart, deciding
whether it requests a concrete, actionable change to their PROJECT STATE.

Output exactly one `action`:
- UPDATE_PROJECT_FIELDS: the user wants to change floors, bedrooms, safe_room, or parking_spaces to a
  specific new value, OR wants to explicitly say a field is now unknown/unsure. Fill `field_update`.
- ADD_PREFERENCE: the user expresses a new soft architectural wish not already in the existing
  preferences list below (e.g. "I want a big kitchen next to the living room"). Fill `preference` with
  `original_text` = a faithful, close paraphrase of what the user actually said (never invent details
  they didn't mention), and pick the best-fitting `kind`:
  - ROOM_AREA: about a room's size (e.g. "the kitchen should be big").
  - ADJACENCY: about two rooms being near/next to each other (or NOT near each other) — set `target`
    and `related_target` to the two room types mentioned.
  - PRIVACY: about a room being private/quiet/separated from common areas.
  - OTHER: anything else that doesn't fit the above.
- UPDATE_PREFERENCE / REMOVE_PREFERENCE: the user wants to change or remove one of the EXISTING
  preferences listed below. Set `preference.existing_preference_text` to that preference's text EXACTLY
  as listed. If no existing preference clearly matches what they mean, use NO_ACTION instead — do not
  guess which one they mean.
- ROLLBACK_DESIGN_VERSION: the user wants to go back to an earlier design (e.g. "take me back to the
  previous version", "go back to version 2"). Set `rollback.target_version_ordinal` to the concrete
  version number from the history below (resolve "previous"/"the one before this" yourself using that
  list) — if there's no such version (e.g. asking for "the previous version" when there's only one, or a
  version number that doesn't exist), use NO_ACTION instead.
- NO_ACTION: the message is a question, small talk, or anything else that isn't a concrete, resolvable
  request to change one of the above. This is also the correct choice whenever you are not confident you
  understood the specific value/field/preference/version the user means — NEVER guess a value the user
  didn't actually state.

Never invent a value, room type, or preference the user didn't actually say. `field_update.mark_unknown`
must only be true when the user is explicitly saying they don't know/aren't sure — not a default.

{context}
"""


class ChatIntentExtractor(ABC):
    @abstractmethod
    def extract(
        self, project: Project, design_versions: list[DesignVersion], history: list[ChatMessage], new_message: str
    ) -> ChatIntentExtraction: ...


class OpenAIChatIntentExtractor(ChatIntentExtractor):
    def __init__(self, model: str = "gpt-5-nano") -> None:
        self._model = model
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def extract(
        self, project: Project, design_versions: list[DesignVersion], history: list[ChatMessage], new_message: str
    ) -> ChatIntentExtraction:
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(context=_build_context(project, design_versions))

        messages = [{"role": "system", "content": system_prompt}]
        for message in history:
            role = "user" if message.role == ChatRole.user else "assistant"
            messages.append({"role": role, "content": message.content})
        messages.append({"role": "user", "content": new_message})

        response = self._client.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=ChatIntentExtraction,
        )
        parsed = response.choices[0].message.parsed
        assert parsed is not None
        return parsed
