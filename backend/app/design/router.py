from fastapi import APIRouter, HTTPException

from app.design.errors_http import DESIGN_PIPELINE_ERRORS, raise_design_error_as_http
from app.design.pipeline import generate_design_via_solver
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

    # `app.design.generator`'s old row-layout algorithm is deliberately NOT used here (or anywhere in
    # the normal runtime path) — see app/design/pipeline.py's module docstring. It remains in the
    # repository, untouched and still tested, for reference/tests only.
    #
    # Error mapping lives in app/design/errors_http.py — shared with app/projects/update.py's
    # design-regeneration step, so both entry points into `generate_design_via_solver` report failures
    # identically.
    try:
        design = generate_design_via_solver(project)
    except DESIGN_PIPELINE_ERRORS as error:
        raise_design_error_as_http(error)

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
