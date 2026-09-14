from fastapi import APIRouter, HTTPException

from app.projects.models import (
    CorridorWidthField,
    Project,
    RoomRelationshipRecord,
    TaggedInt,
    UnsupportedRequestRecord,
    WetRoomKindRecord,
)
from app.projects.routes import base_routes as project_routes
from app.requirements.parser import (
    OpenAIRequirementParser,
    RequirementExtraction,
    RequirementParser,
    RequestSeverity,
    UnsupportedRequest,
)

router = APIRouter(prefix="/projects", tags=["requirements"])
parser: RequirementParser = OpenAIRequirementParser()


@router.post("/{project_id}/requirements", response_model=Project)
def parse_requirements(project_id: str) -> Project:
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    extraction = parser.parse(project.description)
    wet_rooms, wet_room_kinds, unresolved = reconcile_wet_rooms(extraction)

    updated = project_routes.repository.set_parsed_requirements(
        project_id,
        floors=extraction.floors,
        bedrooms=extraction.bedrooms,
        safe_room=extraction.safe_room,
        parking_spaces=extraction.parking_spaces,
        pool=extraction.pool,
        wet_rooms=wet_rooms,
        open_plan=extraction.open_plan,
        unsupported_requests=[UnsupportedRequestRecord(text=r.text, topic=r.topic, severity=r.severity.value)
                              for r in [*extraction.other_requests, *unresolved]],
        corridor_width=CorridorWidthField(
            value_m=extraction.corridor_width.value_m,
            mode=extraction.corridor_width.mode.value,
            source=extraction.corridor_width.source),
        room_relationships=[
            RoomRelationshipRecord(
                source_role=r.source_role, target_role=r.target_role,
                relation=r.relation.value, strength=r.strength.value,
                source_text=r.source_text, ambiguous=r.ambiguous)
            for r in extraction.room_relationships],
        wet_room_kinds=wet_room_kinds,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


def reconcile_wet_rooms(extraction: RequirementExtraction,
                        ) -> tuple[TaggedInt, list[WetRoomKindRecord], list[UnsupportedRequest]]:
    """The count and the kinds, made consistent WITHOUT guessing (specs/007 FR-1, §5).

    The count is the authority on how many. Fewer kinds than the count is the normal case — the
    rest are unstated, and the engine pads them as `unspecified`. Kinds named where no count was stated
    (or only inferred) make the count: the person named the rooms. Kinds beyond a STATED count are
    a contradiction the parser could not settle; the stored kinds keep the count's length and an
    `ambiguous` request quoting the extra rooms stops generation until the person says which.
    """
    kinds = list(extraction.wet_room_kinds)
    count = extraction.wet_rooms
    unresolved: list[UnsupportedRequest] = []
    if kinds and (count.value is None or (count.source != "requested" and len(kinds) > count.value)):
        count = TaggedInt(value=len(kinds), source="requested")
    if count.value is not None and len(kinds) > count.value:
        extra = "; ".join(k.source_text or k.kind for k in kinds[count.value:])
        unresolved.append(UnsupportedRequest(
            text=f"{count.value} חדרי רחצה נספרו, אבל תוארו יותר: {extra}",
            topic="wet_rooms", severity=RequestSeverity.AMBIGUOUS))
        kinds = kinds[:count.value]
    records = [WetRoomKindRecord(kind=k.kind, host=k.host, strength=k.strength,
                                 source_text=k.source_text,
                                 source="requested" if k.kind != "unspecified" else "unknown")
               for k in kinds]
    return count, records, unresolved
