"""ArchitectModelAdapter: the ONLY deterministic translation from Architect Model V1's real output
schema (`ModelArchitecturalSpec`) to BuildSmart's own `ArchitecturalSpec`.

Every transformation here is one of: field renaming, enum/case mapping, an area-field rename, or a
documented severity-assignment policy (grounded in the fine-tuning project's own DATA_CONTRACT.md —
"ADJACENCY / DIRECT_ACCESS: priority=SOFT, source_type=OBSERVED_GEOMETRY" — not invented here). Nothing
here fabricates data the model didn't provide:

- `Circulation.entry_room_type` is never populated from the model's `circulation` field (a list of
  room TYPES that serve circulation space, a different concept — see `model_schema.py`). The returned
  spec's `circulation` is always `None`; see `app/geometry/solver.py` for how that's handled, and
  `app/architect/authoritative_merge.py` for the only place an entry-room requirement may be added
  (from an explicit BuildSmart-side requirement, never invented here).
- Relationship types with no honest BuildSmart equivalent (DOOR_CONNECTION, WINDOW_CONNECTION, NEAR)
  are dropped, not force-mapped onto adjacency/direct_access/separation — each drop is reported in the
  returned `diagnostics` list.
- A same-type self-relationship (e.g. two bathrooms marked ADJACENT to each other) has no BuildSmart
  representation either (`AdjacencyConstraint` etc. require two distinct room TYPES, since BuildSmart's
  contract is type-to-type, not instance-to-instance) and is dropped the same way.
- SAFE_ROOM/MAMAD is out of scope here entirely — the model has no such room type at all (see
  `model_schema.py`'s `ModelRoomType`); see `app/architect/authoritative_merge.py`.
"""

from dataclasses import dataclass, field

from app.architect.model_schema import ModelArchitecturalSpec, ModelRelationshipType, ModelRoomType, ModelZone
from app.architect.models import (
    AdjacencyConstraint,
    ArchitecturalSpec,
    ConstraintSeverity,
    DirectAccessConstraint,
    ProgramItem,
    RelationalConstraint,
    SeparationConstraint,
    Zone,
)

# Full, injective pass-through of the model's real RoomType vocabulary into BuildSmart's snake_case
# convention. LIVING -> "living_room" specifically (not "living") because the frontend hardcodes that
# exact string to find the ground-floor entry-door anchor room (see frontend/src/design/SketchSvg.tsx).
_ROOM_TYPE_MAP: dict[ModelRoomType, str] = {
    ModelRoomType.BEDROOM: "bedroom",
    ModelRoomType.MASTER_BEDROOM: "master_bedroom",
    ModelRoomType.BATHROOM: "bathroom",
    ModelRoomType.WC: "wc",
    ModelRoomType.LIVING: "living_room",
    ModelRoomType.KITCHEN: "kitchen",
    ModelRoomType.DINING: "dining",
    ModelRoomType.BALCONY: "balcony",
    ModelRoomType.CORRIDOR: "corridor",
    ModelRoomType.ENTRANCE: "entrance",
    ModelRoomType.STORAGE: "storage",
    ModelRoomType.UTILITY: "utility",
    ModelRoomType.STAIRCASE: "staircase",
    ModelRoomType.PARKING: "parking",
}

# Only these three have an honest BuildSmart equivalent — see the module docstring.
_RELATIONSHIP_KIND_MAP = {
    ModelRelationshipType.ADJACENT: AdjacencyConstraint,
    ModelRelationshipType.DIRECT_ACCESS: DirectAccessConstraint,
    ModelRelationshipType.SEPARATED: SeparationConstraint,
}


_REVERSE_ROOM_TYPE_MAP: dict[str, ModelRoomType] = {value: key for key, value in _ROOM_TYPE_MAP.items()}


def _map_room_type(model_type: ModelRoomType) -> str:
    return _ROOM_TYPE_MAP[model_type]


def model_room_type_for(buildsmart_room_type: str) -> ModelRoomType | None:
    """Reverse of `_ROOM_TYPE_MAP` — used by the input side (`app/architect/local_gateway.py`'s
    `_build_model_input`) to check whether a BuildSmart room type has any representation in the real
    model's vocabulary at all. Returns `None` for e.g. `"safe_room"`, which has none — see
    `model_schema.py`'s `ModelRoomType`."""
    return _REVERSE_ROOM_TYPE_MAP.get(buildsmart_room_type)


def _adapt_zone(zone: ModelZone) -> Zone:
    return Zone(name=zone.type.value.lower(), room_types=[_map_room_type(rt) for rt in zone.room_types])


@dataclass
class AdapterResult:
    spec: ArchitecturalSpec
    # Human-readable record of every model-provided fact that was intentionally NOT carried into
    # `spec` — dropped relationships, an ignored circulation list — so a caller can log/inspect exactly
    # what was excluded and why, without any of it being silently mistranslated. Never raised as an
    # error: a real, valid model response producing some of these is expected, not exceptional.
    diagnostics: list[str] = field(default_factory=list)


def adapt_model_spec(model_spec: ModelArchitecturalSpec) -> AdapterResult:
    diagnostics: list[str] = []

    program = [
        ProgramItem(
            room_type=_map_room_type(item.type),
            count=item.count,
            target_area_m2=item.area_per_room_m2,
            source="MODEL_INFERENCE",
        )
        for item in model_spec.program
    ]

    zones = [_adapt_zone(zone) for zone in model_spec.zones]

    relationships: list[RelationalConstraint] = []
    for rel in model_spec.relationships:
        if rel.a_type == rel.b_type:
            diagnostics.append(
                f"dropped self-relationship {rel.a_type.value} <-> {rel.a_type.value} "
                f"({rel.relationship.value}): BuildSmart relationships require two distinct room types"
            )
            continue

        constraint_cls = _RELATIONSHIP_KIND_MAP.get(rel.relationship)
        if constraint_cls is None:
            diagnostics.append(
                f"dropped unsupported relationship type {rel.relationship.value} between "
                f"{rel.a_type.value} and {rel.b_type.value}: no honest BuildSmart equivalent — "
                f"never force-mapped onto adjacency/direct_access/separation"
            )
            continue

        relationships.append(
            constraint_cls(
                room_type_a=_map_room_type(rel.a_type),
                room_type_b=_map_room_type(rel.b_type),
                # Every relationship Architect Model V1 emits is an observed fact about one solved
                # plan, not a universal hard rule — see the fine-tuning project's DATA_CONTRACT.md
                # ("ADJACENCY / DIRECT_ACCESS: priority=SOFT, source_type=OBSERVED_GEOMETRY"). This is
                # a documented policy, not a guess.
                severity=ConstraintSeverity.soft,
                source="MODEL_INFERENCE",
            )
        )

    if model_spec.circulation:
        diagnostics.append(
            f"model circulation list {[t.value for t in model_spec.circulation]} was present but not "
            f"used — it names circulation-serving room types, not an entry room, and BuildSmart's "
            f"Circulation.entry_room_type is never derived from it"
        )

    spec = ArchitecturalSpec(
        program=program,
        zones=zones,
        relationships=relationships,
        circulation=None,
        incomplete_requirements=[],
    )
    return AdapterResult(spec=spec, diagnostics=diagnostics)
