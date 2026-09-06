"""Structured soft-preference model — see specs/audit for "conversational design editing": a
`Preference` is a non-binding architectural wish (e.g. "I'd like the kitchen open to the living room")
distinct from `Project`'s authoritative requirement fields (floors/bedrooms/safe_room/parking_spaces/
pool), which are hard facts the solver must satisfy. Preferences are advisory only — nothing in this
milestone wires them into `ArchitectModelRequest.soft_constraints` yet (that's future work, once the
Architect Model's own input format is extended to carry them); today they are recorded, editable, and
traceable, and that's the whole scope of this foundation.

Deliberately small and extensible: four kinds cover the cases the product-editing audit called out
without inventing a wider taxonomy up front. `original_text` is always kept (even for a SETTINGS-sourced
preference, where it's just a restatement of the structured fields) so a preference can always be shown
back to the user in their own words, not just as reconstructed structured data.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class PreferenceKind(str, Enum):
    room_area = "ROOM_AREA"
    adjacency = "ADJACENCY"
    privacy = "PRIVACY"
    other = "OTHER"


class PreferenceSource(str, Enum):
    chat = "CHAT"
    settings = "SETTINGS"


class PreferencePriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


def _non_empty_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("original_text must not be empty")
    return stripped


class Preference(BaseModel):
    """A stored preference. `target`/`related_target` are free-text room-type-ish strings (not
    constrained to a fixed enum — the Architect Model's own room-type vocabulary already lives
    elsewhere, see app/architect/model_schema.py, and a preference should be able to reference a target
    that vocabulary doesn't even cover yet, e.g. "the office"). `value` is intentionally a loose
    float|str|bool union — what it means depends on `kind` (e.g. a target m² for ROOM_AREA, a boolean
    "must not be adjacent" for ADJACENCY, free text for OTHER)."""

    preference_id: str
    kind: PreferenceKind
    target: str | None = None
    related_target: str | None = None
    value: float | str | bool | None = None
    priority: PreferencePriority = PreferencePriority.medium
    original_text: str
    source: PreferenceSource
    created_at: datetime

    @field_validator("original_text")
    @classmethod
    def original_text_non_empty(cls, value: str) -> str:
        return _non_empty_text(value)


class PreferenceCreate(BaseModel):
    kind: PreferenceKind
    target: str | None = None
    related_target: str | None = None
    value: float | str | bool | None = None
    priority: PreferencePriority = PreferencePriority.medium
    original_text: str

    @field_validator("original_text")
    @classmethod
    def original_text_non_empty(cls, value: str) -> str:
        return _non_empty_text(value)


class PreferenceUpdate(BaseModel):
    """Identifies the preference to change by `preference_id`; every other field is "leave unchanged"
    when omitted, same convention as `ProjectUpdateDiff`."""

    preference_id: str
    kind: PreferenceKind | None = None
    target: str | None = None
    related_target: str | None = None
    value: float | str | bool | None = None
    priority: PreferencePriority | None = None
    original_text: str | None = None

    @field_validator("original_text")
    @classmethod
    def original_text_non_empty_if_given(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty_text(value)
