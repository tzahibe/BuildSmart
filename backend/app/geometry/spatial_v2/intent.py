"""Architectural intent model (SPATIAL_V2 Phase 2): a reusable, UI-independent representation of
GENERIC architectural preferences -- distinct from `ArchitecturalSpec.relationships`/`.zones`,
which encode what a SPECIFIC program explicitly required. This module encodes what a competent
human architect would prefer by default for ANY program, purely from room TYPE, so Spatial V2's
scoring has soft signal even for the (common) case where the Architect Model's own output didn't
happen to spell out every adjacency/zoning preference explicitly.

Zoning itself is NOT reinvented here: `ArchitecturalSpec.zones` (populated by
`app.architect.adapter._adapt_zone` from the Architect Model's own PUBLIC/PRIVATE/SERVICE/
CIRCULATION/OUTDOOR tags -- see `app.architect.model_schema.ModelZoneType`) is the authoritative
source when present. `zone_by_room_type` below only fills in a generic fallback for a room type
`spec.zones` doesn't happen to cover, so scoring never silently ignores an untagged room.

Designed so a future LLM can emit these same concepts (a `Zone`, a list of `AdjacencyPreference`)
directly as its planning output, instead of raw x/y coordinates -- nothing here is tied to FastAPI,
pydantic response models, or any UI type.
"""
from dataclasses import dataclass
from enum import Enum


class Zone(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SERVICE = "service"
    CIRCULATION = "circulation"
    OUTDOOR = "outdoor"


# Generic fallback room-type -> Zone mapping, over BuildSmart's real room-type vocabulary (see
# app.architect.adapter._ROOM_TYPE_MAP / app.geometry.instances). Used only when spec.zones does
# not already classify a given room type.
_DEFAULT_ZONE_BY_ROOM_TYPE: dict[str, Zone] = {
    "living_room": Zone.PUBLIC,
    "dining": Zone.PUBLIC,
    "kitchen": Zone.PUBLIC,
    "entrance": Zone.PUBLIC,
    "balcony": Zone.OUTDOOR,
    "parking": Zone.OUTDOOR,
    "bedroom": Zone.PRIVATE,
    "master_bedroom": Zone.PRIVATE,
    "safe_room": Zone.PRIVATE,
    "bathroom": Zone.SERVICE,
    "wc": Zone.SERVICE,
    "storage": Zone.SERVICE,
    "utility": Zone.SERVICE,
    "corridor": Zone.CIRCULATION,
    "staircase": Zone.CIRCULATION,
}


@dataclass(frozen=True)
class AdjacencyPreference:
    room_type_a: str
    room_type_b: str
    weight: float  # positive = preferred adjacency, negative = discouraged adjacency


# Generic architectural preferences, true across virtually any residential program -- not fitted to
# any one benchmark scenario. Each is a (type, type, weight) pair; weight magnitude reflects how
# strongly conventional residential design favors/avoids it, not a tuned hyperparameter per scenario.
GENERIC_ADJACENCY_PREFERENCES: list[AdjacencyPreference] = [
    AdjacencyPreference("kitchen", "living_room", 1.0),
    AdjacencyPreference("kitchen", "dining", 1.0),
    AdjacencyPreference("dining", "living_room", 0.6),
    AdjacencyPreference("bedroom", "bedroom", 0.4),
    AdjacencyPreference("bedroom", "bathroom", 0.5),
    AdjacencyPreference("master_bedroom", "bathroom", 0.6),
    AdjacencyPreference("bathroom", "corridor", 0.5),
    AdjacencyPreference("bedroom", "corridor", 0.4),
    # Discouraged: a bathroom opening directly into the main living/entertaining space is a common
    # residential design smell (privacy/odor/acoustic reasons), even though nothing about it is
    # geometrically or functionally invalid -- exactly the kind of soft, non-hard preference this
    # module exists to represent.
    AdjacencyPreference("bathroom", "living_room", -0.8),
    AdjacencyPreference("wc", "living_room", -0.5),
    AdjacencyPreference("bedroom", "kitchen", -0.3),
]

# Room types that architecturally benefit from an exterior wall (natural light/ventilation) --
# generic, not scenario-specific. Service/circulation rooms are deliberately excluded: a windowless
# bathroom/corridor is normal, not a defect.
EXTERIOR_PREFERRED_ROOM_TYPES: frozenset[str] = frozenset({
    "living_room", "bedroom", "master_bedroom", "dining", "kitchen",
})


def zone_by_room_type(spec_zones: list, room_types: set[str]) -> dict[str, Zone]:
    """Builds a room_type -> Zone map, preferring `spec_zones` (ArchitecturalSpec.zones, the
    authoritative per-program zoning already produced by the Architect Model) and falling back to
    `_DEFAULT_ZONE_BY_ROOM_TYPE` only for a room type no spec zone covers."""
    result: dict[str, Zone] = {}
    for zone in spec_zones:
        try:
            zone_enum = Zone(zone.name.lower())
        except ValueError:
            continue
        for room_type in zone.room_types:
            result[room_type] = zone_enum
    for room_type in room_types:
        if room_type not in result:
            result[room_type] = _DEFAULT_ZONE_BY_ROOM_TYPE.get(room_type, Zone.PRIVATE)
    return result
