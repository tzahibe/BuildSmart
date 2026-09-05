from fastapi import APIRouter, HTTPException

from app.architect.area_budget import AuthoritativeAreaExceedsBudgetError
from app.architect.errors import (
    ArchitectModelError,
    ArchitectModelTimeoutError,
    ArchitectModelUnavailableError,
)
from app.design.pipeline import DesignUnsatisfiableError, MultiFloorNotSupportedError, generate_design_via_solver
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
    # Error handling below distinguishes every failure class the pipeline can raise into its own
    # `{"error": <code>, "message": ...}` body and an appropriate HTTP status — see
    # app/architect/errors.py for the full taxonomy. Order matters: the more specific
    # ArchitectModel*Error subclasses must be caught before the general ArchitectModelError base class.
    try:
        design = generate_design_via_solver(project)
    except AuthoritativeAreaExceedsBudgetError as error:
        raise HTTPException(
            status_code=422,
            detail={"error": error.code, "message": str(error)},
        ) from None
    except MultiFloorNotSupportedError as error:
        raise HTTPException(
            status_code=422,
            detail={"error": error.code, "message": str(error)},
        ) from None
    except ArchitectModelUnavailableError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": ArchitectModelUnavailableError.code,
                "message": "The Architect Model service is currently unavailable. Please try again shortly.",
            },
        ) from None
    except ArchitectModelTimeoutError:
        raise HTTPException(
            status_code=504,
            detail={
                "error": ArchitectModelTimeoutError.code,
                "message": "The Architect Model took too long to respond. Please try again.",
            },
        ) from None
    except ArchitectModelError:
        # Covers empty response / malformed JSON / schema-invalid JSON / unsupported room or
        # constraint types — all distinct exception types for backend diagnostics (see
        # app/architect/errors.py and the logging in app/design/pipeline.py), but a single
        # user-facing code: the model produced something BuildSmart could not use. The underlying
        # provider-specific detail is deliberately NOT included here — it stays server-side only.
        raise HTTPException(
            status_code=502,
            detail={
                "error": "ARCHITECT_MODEL_INVALID_OUTPUT",
                "message": "The Architect Model returned a design BuildSmart could not use. Please try again.",
            },
        ) from None
    except DesignUnsatisfiableError as error:
        raise HTTPException(
            status_code=422,
            detail={"error": error.code, "message": str(error)},
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
