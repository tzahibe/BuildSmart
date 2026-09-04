from fastapi import APIRouter, HTTPException

from app.projects.models import Project
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
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated
