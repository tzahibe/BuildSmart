from fastapi import APIRouter, HTTPException

from app.projects.models import (
    CorridorWidthField,
    Project,
    RoomRelationshipRecord,
    UnsupportedRequestRecord,
)
from app.projects.routes import base_routes as project_routes
from app.requirements.parser import OpenAIRequirementParser, RequirementParser

router = APIRouter(prefix="/projects", tags=["requirements"])
parser: RequirementParser = OpenAIRequirementParser()


@router.post("/{project_id}/requirements", response_model=Project)
def parse_requirements(project_id: str) -> Project:
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    extraction = parser.parse(project.description)

    updated = project_routes.repository.set_parsed_requirements(
        project_id,
        floors=extraction.floors,
        bedrooms=extraction.bedrooms,
        safe_room=extraction.safe_room,
        parking_spaces=extraction.parking_spaces,
        pool=extraction.pool,
        wet_rooms=extraction.wet_rooms,
        open_plan=extraction.open_plan,
        unsupported_requests=[UnsupportedRequestRecord(text=r.text, topic=r.topic, severity=r.severity.value)
                              for r in extraction.other_requests],
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
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated
