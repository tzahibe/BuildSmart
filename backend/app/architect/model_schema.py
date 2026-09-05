"""The REAL Architect Model V1 wire schema — verified against the accepted fine-tuning project's
`src/datasets/schema.py`, `src/evaluation/prompts.py`, and 500 real holdout-evaluation generations
(100% JSON-validity, 100% schema-validity). This is a description of what the model actually emits,
not an invention: room/zone/relationship type values and field names below are copied verbatim from
that verified contract.

This is deliberately a SEPARATE set of types from `app/architect/models.py`'s `ArchitecturalSpec` —
the two schemas differ in field names, room-type vocabulary/casing, relationship taxonomy, and the
`circulation` field's meaning. `app/architect/adapter.py` is the only place a `ModelArchitecturalSpec`
is turned into an `ArchitecturalSpec`; nothing else in this codebase should parse raw model JSON
directly into `ArchitecturalSpec`.
"""

from enum import Enum

from pydantic import BaseModel, Field


class ModelRoomType(str, Enum):
    """Verbatim `RoomType` enum from the fine-tuning project's `src/datasets/schema.py`. Notably has
    no SAFE_ROOM/MAMAD value — see `app/architect/authoritative_merge.py` for why that's handled
    outside the model rather than by extending this enum to include a value the model was never
    trained to emit."""

    BEDROOM = "BEDROOM"
    MASTER_BEDROOM = "MASTER_BEDROOM"
    BATHROOM = "BATHROOM"
    WC = "WC"
    LIVING = "LIVING"
    KITCHEN = "KITCHEN"
    DINING = "DINING"
    BALCONY = "BALCONY"
    CORRIDOR = "CORRIDOR"
    ENTRANCE = "ENTRANCE"
    STORAGE = "STORAGE"
    UTILITY = "UTILITY"
    STAIRCASE = "STAIRCASE"
    PARKING = "PARKING"


class ModelRelationshipType(str, Enum):
    """Verbatim `RelationshipType` enum. Only ADJACENT/DIRECT_ACCESS/SEPARATED have an honest
    BuildSmart equivalent (see `app/architect/adapter.py`'s `_RELATIONSHIP_KIND_MAP`) — DOOR_CONNECTION,
    WINDOW_CONNECTION, and NEAR are accepted here (so parsing a real response never fails on them) but
    are dropped, with a diagnostic, by the adapter rather than force-mapped onto a kind that would
    misrepresent them."""

    ADJACENT = "ADJACENT"
    DIRECT_ACCESS = "DIRECT_ACCESS"
    DOOR_CONNECTION = "DOOR_CONNECTION"
    WINDOW_CONNECTION = "WINDOW_CONNECTION"
    SEPARATED = "SEPARATED"
    NEAR = "NEAR"


class ModelZoneType(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SERVICE = "SERVICE"
    CIRCULATION = "CIRCULATION"
    OUTDOOR = "OUTDOOR"


class ModelProgramItem(BaseModel):
    type: ModelRoomType
    count: int = Field(gt=0)
    # Area of ONE room of this type — the model's own naming, not a total (see the fine-tuning
    # project's DATA_CONTRACT.md). Renamed to `target_area_m2` by the adapter.
    area_per_room_m2: float = Field(gt=0)
    zone: ModelZoneType


class ModelZone(BaseModel):
    type: ModelZoneType
    room_types: list[ModelRoomType]


class ModelRelationship(BaseModel):
    a_type: ModelRoomType
    b_type: ModelRoomType
    relationship: ModelRelationshipType
    source_type: str | None = None


class ModelArchitecturalSpec(BaseModel):
    """Exact shape of the JSON object Architect Model V1 generates — see `prompts.py`'s
    `SYSTEM_PROMPT`: top-level keys are exactly `program`, `zones`, `relationships`, `circulation`.

    `circulation` is a flat list of room TYPES that serve circulation (e.g. a staircase) — non-empty in
    only ~1.6% of 500 real holdout examples, and semantically unrelated to "which room is the entry."
    `app/architect/adapter.py` deliberately does not use this field to populate BuildSmart's
    `Circulation.entry_room_type`.
    """

    program: list[ModelProgramItem]
    zones: list[ModelZone]
    relationships: list[ModelRelationship]
    circulation: list[ModelRoomType] = Field(default_factory=list)
