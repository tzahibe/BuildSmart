"""apply_spatial_edit: the structured edit API layered ON TOP OF the existing Spatial V1
solver -- ported unmodified from the validated experimental spatial-edit layer. Deliberately does
NOT call CP-SAT and does NOT regenerate topology for a basic move -- it translates one room's
rectangle directly and reuses EXISTING validation to check the result:

  - overlap                        -> app.geometry.solver._overlaps (real production function,
                                       pure rectangle math, no ArchitecturalSpec needed)
  - required-access-edge integrity -> spatial_v1_topology.derive_door_topology (unchanged from the
                                       validated Spatial V1 prototype)
  - footprint bounds                -> a small dedicated check (CP-SAT enforces this via variable
                                       domains at solve time, not as a separately-callable
                                       post-hoc check, so no equivalent production function exists
                                       to reuse here)

Dispatch is by command.type so future commands (RESIZE_ROOM, MOVE_NEAR, ALIGN, ...) can be added
as additional `_apply_<TYPE>` handlers without touching this module's public entry point or the
existing MOVE_ROOM handler.
"""
from app.geometry.solver import _overlaps
from app.geometry.spatial_edit_types import (
    EditResult,
    MoveRoomByVectorCommand,
    MoveRoomCommand,
    SpatialLayout,
    direction_delta,
)
from app.geometry.spatial_v1_topology import derive_door_topology


def _room_out_of_bounds(room: dict, footprint: dict, eps: float = 1e-6) -> bool:
    width_m = footprint["width_m"]
    depth_m = footprint["depth_m"]
    return (
        room["x"] < -eps or room["y"] < -eps
        or room["x"] + room["width"] > width_m + eps
        or room["y"] + room["height"] > depth_m + eps
    )


def _overlaps_any_other(room: dict, all_rooms: list) -> bool:
    for other in all_rooms:
        if other["id"] == room["id"]:
            continue
        if _overlaps(
            room["x"], room["y"], room["width"], room["height"],
            other["x"], other["y"], other["width"], other["height"],
        ):
            return True
    return False


def _move_and_validate(layout: SpatialLayout, room_id: str, dx: float, dy: float) -> EditResult:
    """Shared core for every translate-one-room command: apply (dx, dy) to `room_id`, leave every
    other room untouched, and run the exact same validation regardless of how the caller arrived
    at (dx, dy) (a cardinal direction + distance, or a raw vector)."""
    target = next((r for r in layout.rooms if r["id"] == room_id), None)
    if target is None:
        return EditResult(status="REJECTED", reason="ROOM_NOT_FOUND")

    moved_room = dict(target)
    moved_room["x"] = target["x"] + dx
    moved_room["y"] = target["y"] + dy

    # only the target room's dict is replaced -- every other room dict is the SAME object,
    # unmodified, guaranteeing no unrelated room can change as a side effect of this edit
    new_rooms = [moved_room if r["id"] == room_id else r for r in layout.rooms]

    if _room_out_of_bounds(moved_room, layout.footprint):
        return EditResult(status="REJECTED", reason="OUT_OF_BOUNDS")

    if _overlaps_any_other(moved_room, new_rooms):
        return EditResult(status="REJECTED", reason="OVERLAP")

    if layout.topology is not None:
        _, mismatches = derive_door_topology(new_rooms, layout.topology)
        if mismatches:
            return EditResult(status="REJECTED", reason="CONSTRAINT_VIOLATION")

    new_layout = SpatialLayout(rooms=new_rooms, footprint=layout.footprint, topology=layout.topology)
    return EditResult(status="APPLIED", layout=new_layout)


def _apply_move_room(layout: SpatialLayout, command: MoveRoomCommand) -> EditResult:
    dx, dy = direction_delta(command.direction, command.resolved_distance_m())
    return _move_and_validate(layout, command.room_id, dx, dy)


def _apply_move_room_by_vector(layout: SpatialLayout, command: MoveRoomByVectorCommand) -> EditResult:
    return _move_and_validate(layout, command.room_id, command.dx_m, command.dy_m)


_HANDLERS = {
    "MOVE_ROOM": _apply_move_room,
    "MOVE_ROOM_BY_VECTOR": _apply_move_room_by_vector,
}


def apply_spatial_edit(layout: SpatialLayout, command: MoveRoomCommand | MoveRoomByVectorCommand) -> EditResult:
    """Applies one structured edit command to an existing SOLVED Spatial V1 layout and validates
    the result via existing Spatial V1 / production validation. Never silently repairs,
    regenerates, or moves any room other than the one named in the command -- an invalid edit is
    rejected outright, and this function does not mutate `layout` or its `rooms`/`footprint` in
    place, so the caller's original layout remains valid and usable after a REJECTED result."""
    handler = _HANDLERS.get(command.type)
    if handler is None:
        raise ValueError(f"unsupported command type: {command.type}")
    return handler(layout, command)
