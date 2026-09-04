from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.localities.data import CITY_STREETS
from app.projects.models import Project, ProjectCreate, ProjectUpdate
from app.projects.repository import JsonFileProjectRepository

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "projects.json"

router = APIRouter(prefix="/projects", tags=["projects"])
repository = JsonFileProjectRepository(_DATA_FILE)


@router.post("", response_model=Project, status_code=201)
def create_project(data: ProjectCreate) -> Project:
    return repository.create(data)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    project = repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=Project)
def update_project(project_id: str, data: ProjectUpdate) -> Project:
    existing = repository.get(project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # ProjectUpdate only cross-checks city/street when both are provided in the same
    # request (see specs/001-project-creation/research.md) — re-check the merged final
    # pair here, against whichever of the two the existing project already has.
    merged_city = data.city if data.city is not None else existing.city
    merged_street = data.street if data.street is not None else existing.street
    if merged_street not in CITY_STREETS.get(merged_city, []):
        raise HTTPException(
            status_code=422,
            detail="street must be selected from the list of streets for the chosen city",
        )

    # Same merged-pair re-check as above, for plot_area_m2/built_area_m2 (see
    # ProjectUpdate.built_area_fits_plot_when_both_given in models.py for the schema-level half).
    merged_plot_area = data.plot_area_m2 if data.plot_area_m2 is not None else existing.plot_area_m2
    merged_built_area = data.built_area_m2 if data.built_area_m2 is not None else existing.built_area_m2
    if merged_built_area >= merged_plot_area:
        raise HTTPException(
            status_code=422,
            detail="built_area_m2 must be smaller than plot_area_m2",
        )

    updated = repository.update(project_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated
