"""Demo API: the review contract and the authoritative generation endpoint.

Deliberately a NEW route rather than a swap of `POST /projects/{id}/design`, so the existing
solver path keeps working untouched while the demo path is built. Switching the product over is
then a one-line change, not a migration.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.projects.routes import base_routes as project_routes

from app.projects.models import SourceTag, TaggedBool, TaggedInt

from .contract import DemoDesign
from .requirements_view import RequirementsReview, ReviewEdit, review_of
from .service import DemoGenerationError, generate_demo_design

router = APIRouter(prefix="/projects", tags=["demo"])


def _project_or_404(project_id: str):
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/review", response_model=RequirementsReview)
def get_requirements_review(project_id: str) -> RequirementsReview:
    """"This is what I understood" — the correctable requirements, and where each came from."""
    return review_of(_project_or_404(project_id))


@router.put("/{project_id}/review", response_model=RequirementsReview)
def update_requirements_review(project_id: str, body: ReviewEdit) -> RequirementsReview:
    """The user corrects what we understood. Whatever they set here becomes AUTHORITATIVE — it is
    what generation reads, and a corrected value is recorded as `requested` because the person
    asked for it explicitly. Fields left absent keep their parsed value."""
    project = _project_or_404(project_id)
    if project.requirements_parsed_at is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "REQUIREMENTS_NOT_PARSED",
                    "message": "עדיין לא הבנו את הדרישות.", "detail": ""})

    def _int(new, current):
        return TaggedInt(value=new, source=SourceTag.requested) if new is not None else current

    def _bool(new, current):
        return TaggedBool(value=new, source=SourceTag.requested) if new is not None else current

    updated = project_routes.repository.set_parsed_requirements(
        project_id,
        floors=_int(body.floors, project.floors),
        bedrooms=_int(body.bedrooms, project.bedrooms),
        safe_room=_bool(body.safe_room, project.safe_room),
        parking_spaces=_int(body.parking_spaces, project.parking_spaces),
        pool=project.pool,
        wet_rooms=_int(body.wet_rooms, project.wet_rooms),
        open_plan=_bool(body.open_plan, project.open_plan),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return review_of(updated)


@router.post("/{project_id}/design/demo", response_model=DemoDesign)
def generate_demo_plan(project_id: str) -> DemoDesign:
    project = _project_or_404(project_id)
    try:
        return generate_demo_design(project).design
    except DemoGenerationError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": error.message, "detail": error.detail},
        )
