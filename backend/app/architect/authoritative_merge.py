"""Merges BuildSmart's own authoritative HARD room requirements into an `ArchitecturalSpec` returned by
ANY `ArchitectModelGateway` — applied uniformly in `app/design/pipeline.py`, after `gateway.generate()`
and before `GeometrySolver`, regardless of which provider (mock/local/remote) produced the spec.

Why this exists: Architect Model V1 has no SAFE_ROOM/MAMAD concept at all (confirmed against the
accepted model's own real `RoomType` vocabulary — see `app/architect/model_schema.py`), so it silently
omits a safe room even when explicitly asked for one (verified empirically against real inference).
BuildSmart's own product requirement for a safe room must not depend on a model capability that doesn't
exist. Symmetrically, a model gateway must never be allowed to invent a bedroom count BuildSmart itself
doesn't actually know (`RequirementState.unknown`) — a model will always predict SOME plausible count,
because that's what it was trained to do, but BuildSmart's own anti-fabrication guarantee (see
`RequiredRoomConstraint`'s docstring) has to win regardless of what came back from the model.

Both directions are handled by the same generic logic (`_enforce_required_room`), driven only by
`ArchitectModelRequest.hard_constraints`' `RequiredRoomConstraint` entries — never by anything the model
returned. This is why the merge step needs the original `request`, not just the gateway's `spec`.

Traceability: anything this module adds or corrects is tagged `source="USER_REQUIREMENT"` (see
`app/architect/models.py`'s `ConstraintSource`) — today that's accurate because BuildSmart's only
source of a `RequiredRoomConstraint` is Feature 02's requirement parser, which only ever tags a field
`requested`/`inferred`/`unknown` (see `app/projects/models.py`'s `SourceTag`), both of which originate
from the user's own free-text description. Once a Regulation Engine exists (explicitly out of scope
here), `RequiredRoomConstraint` will need its own `source` field so this module can tag some merges
`"REGULATION"` instead — see the module docstring's TODO note below for the minimal change that would
require.

TODO (minimal contract change, once a Regulation Engine exists): add `source: ConstraintSource` to
`RequiredRoomConstraint` in `app/architect/models.py` (defaulting to `"USER_REQUIREMENT"` for backward
compatibility) so `_build_request` in `app/design/pipeline.py` can tag a regulation-driven requirement
`"REGULATION"`, and change this module to read `constraint.source` instead of hardcoding
`"USER_REQUIREMENT"` below. No other change is needed — `ArchitecturalSpec`'s own `ProgramItem`/
`RelationalConstraint.source` fields added this milestone already accept any `ConstraintSource` value.
"""

from app.architect.gateway import MIN_WIDTH_M, TARGET_AREA_M2
from app.architect.models import (
    ArchitecturalSpec,
    ArchitectModelRequest,
    ConstraintSeverity,
    DirectAccessConstraint,
    ProgramItem,
    RelationalConstraint,
    RequiredRoomConstraint,
    RequirementState,
    Zone,
)

# Where a room type not already present in a zone gets filed — same grouping
# `MockArchitectModelGateway` uses, kept here so a merged-in room lands somewhere sensible regardless
# of which zone names the real model happened to emit.
_DEFAULT_ZONE_FOR_ROOM_TYPE = {"bedroom": "private", "safe_room": "private"}
_AUTHORITATIVE_SOURCE = "USER_REQUIREMENT"  # see the module docstring's TODO


def _strip_room_type(
    room_type: str,
    program: list[ProgramItem],
    zones: list[Zone],
    relationships: list[RelationalConstraint],
) -> tuple[list[ProgramItem], list[Zone], list[RelationalConstraint]]:
    program = [item for item in program if item.room_type != room_type]
    zones = [
        zone if room_type not in zone.room_types
        else zone.model_copy(update={"room_types": [rt for rt in zone.room_types if rt != room_type]})
        for zone in zones
    ]
    relationships = [rel for rel in relationships if room_type not in (rel.room_type_a, rel.room_type_b)]
    return program, zones, relationships


def _ensure_room_type(room_type: str, count: int, program: list[ProgramItem], zones: list[Zone]) -> tuple[list[ProgramItem], list[Zone]]:
    existing = next((item for item in program if item.room_type == room_type), None)
    if existing is not None and existing.count == count:
        # Already present with the right count (the model happened to agree) — just stamp it
        # authoritative, since BuildSmart is now the one vouching for this fact, not the model.
        program = [
            item if item.room_type != room_type else item.model_copy(update={"source": _AUTHORITATIVE_SOURCE})
            for item in program
        ]
        return program, zones

    new_item = ProgramItem(
        room_type=room_type,
        count=count,
        target_area_m2=TARGET_AREA_M2.get(room_type),
        min_width_m=MIN_WIDTH_M.get(room_type),
        source=_AUTHORITATIVE_SOURCE,
    )
    program = [item for item in program if item.room_type != room_type] + [new_item]

    if not any(room_type in zone.room_types for zone in zones):
        zone_name = _DEFAULT_ZONE_FOR_ROOM_TYPE.get(room_type, "public")
        zone_index = next((i for i, zone in enumerate(zones) if zone.name == zone_name), None)
        if zone_index is not None:
            zones = list(zones)
            zones[zone_index] = zones[zone_index].model_copy(
                update={"room_types": zones[zone_index].room_types + [room_type]}
            )
        else:
            zones = zones + [Zone(name=zone_name, room_types=[room_type])]

    return program, zones


def _enforce_required_room(
    constraint: RequiredRoomConstraint,
    program: list[ProgramItem],
    zones: list[Zone],
    relationships: list[RelationalConstraint],
    incomplete_requirements: list[str],
) -> tuple[list[ProgramItem], list[Zone], list[RelationalConstraint], list[str]]:
    room_type = constraint.room_type

    if constraint.state == RequirementState.unknown:
        program, zones, relationships = _strip_room_type(room_type, program, zones, relationships)
        if room_type not in incomplete_requirements:
            incomplete_requirements = incomplete_requirements + [room_type]
        return program, zones, relationships, incomplete_requirements

    count = constraint.count or 0
    if count <= 0:
        program, zones, relationships = _strip_room_type(room_type, program, zones, relationships)
        return program, zones, relationships, incomplete_requirements

    program, zones = _ensure_room_type(room_type, count, program, zones)
    return program, zones, relationships, incomplete_requirements


def merge_authoritative_requirements(spec: ArchitecturalSpec, request: ArchitectModelRequest) -> ArchitecturalSpec:
    """Applied uniformly after every `ArchitectModelGateway.generate()` call, for every provider. For
    `MockArchitectModelGateway` this is a no-op in practice (the mock already honors its own request's
    hard constraints), but running the same authoritative pass regardless of provider means BuildSmart's
    HARD-requirement guarantee doesn't depend on which gateway happened to produce `spec`.
    """
    program = list(spec.program)
    zones = list(spec.zones)
    relationships = list(spec.relationships)
    incomplete_requirements = list(spec.incomplete_requirements)

    for constraint in request.hard_constraints:
        if not isinstance(constraint, RequiredRoomConstraint):
            continue
        program, zones, relationships, incomplete_requirements = _enforce_required_room(
            constraint, program, zones, relationships, incomplete_requirements
        )

    room_types_present = {item.room_type for item in program}
    if "safe_room" in room_types_present and "bedroom" in room_types_present:
        already_linked = any(
            isinstance(rel, DirectAccessConstraint) and {rel.room_type_a, rel.room_type_b} == {"safe_room", "bedroom"}
            for rel in relationships
        )
        if not already_linked:
            relationships = relationships + [
                DirectAccessConstraint(
                    room_type_a="safe_room",
                    room_type_b="bedroom",
                    severity=ConstraintSeverity.hard,
                    source=_AUTHORITATIVE_SOURCE,
                    description=(
                        "Safe room reachable directly from a bedroom — an authoritative BuildSmart "
                        "requirement enforced independently of the Architect Model, which has no "
                        "SAFE_ROOM concept at all"
                    ),
                )
            ]

    return ArchitecturalSpec(
        program=program,
        zones=zones,
        relationships=relationships,
        circulation=spec.circulation,
        incomplete_requirements=incomplete_requirements,
    )
