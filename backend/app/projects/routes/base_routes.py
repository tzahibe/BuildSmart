from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.projects.models import Project, ProjectCreate
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
