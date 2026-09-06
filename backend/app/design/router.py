from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from app.design.errors_http import (
    DESIGN_PIPELINE_ERRORS,
    raise_design_error_as_http,
    raise_spatial_edit_rejection_as_http,
)
from app.design.pipeline import generate_design_via_solver
from app.geometry.geometric_design import GeometricDesign
from app.geometry.spatial_edit import apply_spatial_edit
from app.geometry.spatial_edit_adapter import geometric_design_to_spatial_layout, spatial_layout_to_geometric_design
from app.geometry.spatial_edit_types import CommandType, Direction, MoveRoomByVectorCommand, MoveRoomCommand
from app.projects.models import Project, Room
from app.projects.routes import base_routes as project_routes

router = APIRouter(prefix="/projects", tags=["design"])


class SpatialEditRequest(BaseModel):
    """Request body for POST /{project_id}/design/spatial-edit. Field names follow this
    codebase's snake_case convention (see app/projects/models.py, app/chat/models.py) rather than
    the camelCase used in the original task illustration -- no other request model in this API
    uses camelCase, so matching the existing convention takes priority over that illustration.

    Two command shapes share this one model, discriminated by `type` (kept explicit so future edit
    commands can extend this same endpoint without a breaking request-shape change):
      - "MOVE_ROOM" (default, unchanged from the original committed spatial-edit flow):
        room_id + direction + optional distance_m.
      - "MOVE_ROOM_BY_VECTOR" (prepared for a future drag-to-move UI -- not yet wired to any
        frontend code): room_id + dx_m + dy_m, same coordinate convention as `direction_delta`
        (positive dx = EAST, positive dy = SOUTH), letting a caller who already knows the exact
        movement skip the direction+distance decomposition entirely.
    """

    type: CommandType = "MOVE_ROOM"
    room_id: str
    direction: Direction | None = None
    distance_m: float | None = None
    dx_m: float | None = None
    dy_m: float | None = None

    @model_validator(mode="after")
    def _validate_fields_for_type(self) -> "SpatialEditRequest":
        if self.type == "MOVE_ROOM" and self.direction is None:
            raise ValueError("direction is required when type is MOVE_ROOM")
        if self.type == "MOVE_ROOM_BY_VECTOR" and (self.dx_m is None or self.dy_m is None):
            raise ValueError("dx_m and dy_m are required when type is MOVE_ROOM_BY_VECTOR")
        return self


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
        geometric_design=design.geometric_design,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@router.post("/{project_id}/design/spatial-edit", response_model=GeometricDesign)
def apply_spatial_edit_to_project_design(project_id: str, body: SpatialEditRequest) -> GeometricDesign:
    """Applies one bounded spatial edit (currently MOVE_ROOM) to the project's CURRENT
    GeometricDesign. Does not call the Architect Model, does not run GeometrySolver, does not
    regenerate topology -- it translates one room and reuses app.geometry.spatial_edit's existing
    validation (overlap/bounds/required-access-edge integrity) against the design already on file.

    Resolution of "the current design": Project.geometric_design (a dict, the same field
    POST /{project_id}/design writes) is the ONLY store consulted here -- there is no separate
    "design_id" resource in this codebase (see app/projects/models.py's Project.geometric_design
    docstring); a project's current design is always addressed via its project_id.

    Atomicity: project_routes.repository.set_design_model(...) below is only ever reached on
    APPLIED. Every REJECTED path raises before it, so a rejected edit never touches the stored
    project at all -- the persisted design is provably unchanged, not merely "not intentionally
    changed".
    """
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.geometric_design is None:
        raise HTTPException(
            status_code=422,
            detail="Project has no design yet — call POST /projects/{project_id}/design first",
        )

    current_design = GeometricDesign.model_validate(project.geometric_design)
    layout = geometric_design_to_spatial_layout(current_design)

    if body.type == "MOVE_ROOM_BY_VECTOR":
        command = MoveRoomByVectorCommand(room_id=body.room_id, dx_m=body.dx_m, dy_m=body.dy_m)
    else:
        command = MoveRoomCommand(room_id=body.room_id, direction=body.direction, distance_m=body.distance_m)
    result = apply_spatial_edit(layout, command)

    if result.status == "REJECTED":
        raise_spatial_edit_rejection_as_http(result.reason)

    updated_design = spatial_layout_to_geometric_design(result.layout, current_design)

    source_by_room_id = {room.id: room.source for room in current_design.rooms}
    rooms = [
        Room(
            type=room.type, floor=room.floor, area_m2=room.area_m2, x=room.x, y=room.y,
            width_m=room.width_m, depth_m=room.depth_m, source=source_by_room_id.get(room.id),
        )
        for room in updated_design.rooms
    ]

    updated_project = project_routes.repository.set_design_model(
        project_id,
        site_width_m=updated_design.footprint.width_m,
        site_depth_m=updated_design.footprint.depth_m,
        rooms=rooms,
        design_notes=project.design_notes or [],
        geometric_design=updated_design.model_dump(mode="json"),
    )
    if updated_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated_design
