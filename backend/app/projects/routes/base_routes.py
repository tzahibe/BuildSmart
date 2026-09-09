from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.design.errors_http import raise_design_error_as_http
from app.design.version import DesignVersion, JsonFileDesignVersionRepository
from app.projects.models import StreetSide, Project, ProjectCreate
from app.projects.repository import JsonFileProjectRepository
from app.projects.update import ProjectNotFoundError, ProjectUpdateRequest, apply_project_update, rollback_to_design_version

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "projects.json"
_DESIGN_VERSIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "design_versions.json"

router = APIRouter(prefix="/projects", tags=["projects"])
repository = JsonFileProjectRepository(_DATA_FILE)
design_version_repository = JsonFileDesignVersionRepository(_DESIGN_VERSIONS_FILE)


@router.post("", response_model=Project, status_code=201)
def create_project(data: ProjectCreate) -> Project:
    # BACKEND ENFORCEMENT of the fit rule, at the moment the footprint is actually chosen.
    #
    # The options offered by the UI are already site-aware, but filtering in the client is not a
    # guarantee — a stale page, a direct API call or a hand-edited payload can all still submit an
    # outline that cannot go on the land. Rejecting it here means an impossible footprint can never
    # be stored, rather than being caught later at generation with a plan already half-expected.
    if data.selected_footprint is not None and data.plot_width_m and data.plot_depth_m:
        from app.demo import site_geometry  # local: app.demo depends on app.projects, not vice versa

        site = site_geometry.SiteGeometry(
            plot_width_m=data.plot_width_m, plot_depth_m=data.plot_depth_m,
            street_facing_side=data.street_facing_side or StreetSide.north,
            canonical_width_m=(data.plot_depth_m
                               if data.street_facing_side in (StreetSide.east, StreetSide.west)
                               else data.plot_width_m),
            canonical_depth_m=(data.plot_width_m
                               if data.street_facing_side in (StreetSide.east, StreetSide.west)
                               else data.plot_depth_m),
            front_setback_m=(data.setbacks.front_m if data.setbacks
                             else site_geometry.FRONT_SETBACK_M),
            side_setback_m=(data.setbacks.side_m if data.setbacks
                            else site_geometry.SIDE_SETBACK_M),
            rear_setback_m=(data.setbacks.rear_m if data.setbacks
                            else site_geometry.REAR_SETBACK_M),
        )
        fit = site_geometry.check_footprint_fits(
            site, data.selected_footprint.width_m, data.selected_footprint.depth_m)
        if not fit.fits:
            # A parcel with no buildable region at all is refused for its own reason: no outline
            # would have fitted, so pointing at the chosen one would be pointing at the wrong number.
            no_area = site_geometry.no_buildable_area_message(site)
            raise HTTPException(
                status_code=422,
                detail={
                    "code": (site_geometry.NO_BUILDABLE_AREA_CODE if no_area is not None
                             else "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION"),
                    "message": no_area if no_area is not None else (
                        f"המתאר שנבחר אינו נכנס בשטח שנותר לבנייה על המגרש הזה "
                        f"({site_geometry.buildable_dimensions_he(site)}). "
                        f"{site_geometry.SETBACK_DISCLAIMER}"),
                    "detail": fit.detail,
                })
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
