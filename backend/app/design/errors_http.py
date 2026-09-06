"""Shared design-pipeline-error -> HTTPException mapping — used by both `POST /projects/{id}/design`
(app/design/router.py) and the project-update operation's design-regeneration step
(app/projects/update.py), so the two paths a design generation can be triggered from (an explicit
regenerate call, or a settings/chat update whose impact is REGENERATE_DESIGN) report failures
identically rather than drifting apart.
"""

from typing import NoReturn

from fastapi import HTTPException

from app.architect.area_budget import AuthoritativeAreaExceedsBudgetError
from app.architect.errors import (
    ArchitectModelError,
    ArchitectModelTimeoutError,
    ArchitectModelUnavailableError,
)
from app.design.pipeline import DesignUnsatisfiableError, MultiFloorNotSupportedError

# Errors `generate_design_via_solver` can raise that this module knows how to map — anything else
# propagates as a real 500, which is correct (an unmapped exception is a bug, not a domain failure).
DESIGN_PIPELINE_ERRORS = (
    AuthoritativeAreaExceedsBudgetError,
    MultiFloorNotSupportedError,
    ArchitectModelUnavailableError,
    ArchitectModelTimeoutError,
    ArchitectModelError,
    DesignUnsatisfiableError,
)


def raise_design_error_as_http(error: Exception) -> NoReturn:
    if isinstance(error, (AuthoritativeAreaExceedsBudgetError, MultiFloorNotSupportedError, DesignUnsatisfiableError)):
        raise HTTPException(status_code=422, detail={"error": error.code, "message": str(error)}) from None

    if isinstance(error, ArchitectModelUnavailableError):
        raise HTTPException(
            status_code=503,
            detail={
                "error": ArchitectModelUnavailableError.code,
                "message": "The Architect Model service is currently unavailable. Please try again shortly.",
            },
        ) from None

    if isinstance(error, ArchitectModelTimeoutError):
        raise HTTPException(
            status_code=504,
            detail={
                "error": ArchitectModelTimeoutError.code,
                "message": "The Architect Model took too long to respond. Please try again.",
            },
        ) from None

    if isinstance(error, ArchitectModelError):
        # Covers empty response / malformed JSON / schema-invalid JSON / unsupported room or constraint
        # types — a single user-facing code; the provider-specific detail stays server-side only.
        raise HTTPException(
            status_code=502,
            detail={
                "error": "ARCHITECT_MODEL_INVALID_OUTPUT",
                "message": "The Architect Model returned a design BuildSmart could not use. Please try again.",
            },
        ) from None

    raise error


# Reject reasons app.geometry.spatial_edit.apply_spatial_edit() can return (see
# app.geometry.spatial_edit_types.RejectReason) -> HTTPException, same {"error", "message"}
# convention as the design-pipeline mapping above. Kept in this shared module so a spatial edit
# and a design-generation failure report through the identical shape.
_SPATIAL_EDIT_REJECTION_STATUS = {
    "ROOM_NOT_FOUND": 404,
    "OUT_OF_BOUNDS": 422,
    "OVERLAP": 422,
    "CONSTRAINT_VIOLATION": 422,
}

_SPATIAL_EDIT_REJECTION_MESSAGE = {
    "ROOM_NOT_FOUND": "No room with that id exists in the current design.",
    "OUT_OF_BOUNDS": "That move would place the room outside the building footprint.",
    "OVERLAP": "That move would overlap another room.",
    "CONSTRAINT_VIOLATION": "That move would break a required adjacency between two rooms.",
}


def raise_spatial_edit_rejection_as_http(reason: str) -> NoReturn:
    status_code = _SPATIAL_EDIT_REJECTION_STATUS.get(reason, 422)
    message = _SPATIAL_EDIT_REJECTION_MESSAGE.get(reason, "The requested edit could not be applied.")
    raise HTTPException(status_code=status_code, detail={"error": reason, "message": message}) from None
