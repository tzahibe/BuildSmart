from fastapi import APIRouter, HTTPException

from app.design.generator import FootprintTooSmallError, generate_design
from app.projects.models import Project
from app.projects.routes import base_routes as project_routes

router = APIRouter(prefix="/projects", tags=["design"])


@router.post("/{project_id}/design", response_model=Project)
def generate_project_design(project_id: str) -> Project:
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.requirements_parsed_at is None:
        raise HTTPException(
            status_code=422,
            detail="Project has not been parsed yet — call POST /projects/{project_id}/requirements first",
        )

    try:
        design = generate_design(project)
    except FootprintTooSmallError:
        raise HTTPException(
            status_code=422,
            detail="Built area per floor is too small to fit the required rooms",
        ) from None

    updated = project_routes.repository.set_design_model(
        project_id,
        site_width_m=design.site_width_m,
        site_depth_m=design.site_depth_m,
        rooms=design.rooms,
        design_notes=design.design_notes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated
