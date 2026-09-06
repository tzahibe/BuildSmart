from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.design.errors_http import raise_design_error_as_http
from app.design.version import DesignVersion, JsonFileDesignVersionRepository
from app.projects.models import Project, ProjectCreate
from app.projects.repository import JsonFileProjectRepository
from app.projects.update import ProjectNotFoundError, ProjectUpdateRequest, apply_project_update, rollback_to_design_version

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "projects.json"
_DESIGN_VERSIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "design_versions.json"

router = APIRouter(prefix="/projects", tags=["projects"])
repository = JsonFileProjectRepository(_DATA_FILE)
design_version_repository = JsonFileDesignVersionRepository(_DESIGN_VERSIONS_FILE)


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
def update_project(project_id: str, request: ProjectUpdateRequest) -> Project:
    """The single project-mutation endpoint — see app/projects/update.py's module docstring. Settings
    calls this with `source="SETTINGS"`; a future Chat Agent will call it with `source="CHAT"` after an
    explicit user confirmation, submitting the exact same `diff` shape. There is no other way to change
    a project's authoritative requirement fields or preferences.
    """
    try:
        result = apply_project_update(
            repository, design_version_repository, project_id, source=request.source, diff=request.diff
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None

    if result.design_error is not None:
        raise_design_error_as_http(result.design_error)

    return result.project


@router.get("/{project_id}/design-versions", response_model=list[DesignVersion])
def list_design_versions(project_id: str) -> list[DesignVersion]:
    if repository.get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return design_version_repository.list_for_project(project_id)


@router.post("/{project_id}/design-versions/{design_version_id}/activate", response_model=Project)
def activate_design_version(project_id: str, design_version_id: str) -> Project:
    """Rollback: repoints `Project.active_design_version_id` to an existing, immutable DesignVersion.
    Never calls the Architect Model or GeometrySolver — see app/projects/update.py's
    `rollback_to_design_version`."""
    try:
        return rollback_to_design_version(repository, design_version_repository, project_id, design_version_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
