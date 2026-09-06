"""Central coordinate-direction convention for Spatial V1 edit commands -- ported unmodified from
the validated experimental spatial-edit layer. This is the ONLY place NORTH/SOUTH/EAST/WEST are
mapped to signed (dx, dy) deltas; every edit command that needs a direction must import
`direction_delta` from here rather than redefine the mapping locally.

Global coordinate convention (matches `app.geometry.models.RoomInstance` / `BuildingFootprintSpec`:
x is the width axis, y is the depth axis, origin at the footprint's top-left corner):

    NORTH = negative Y
    SOUTH = positive Y
    WEST  = negative X
    EAST  = positive X
"""
from dataclasses import dataclass
from typing import Literal, Optional

Direction = Literal["NORTH", "SOUTH", "EAST", "WEST"]
CommandType = Literal["MOVE_ROOM"]
RejectReason = Literal["ROOM_NOT_FOUND", "OUT_OF_BOUNDS", "OVERLAP", "CONSTRAINT_VIOLATION"]

# Single centrally-defined default edit step. Callers (including an LLM issuing a command with no
# explicit distance) must never invent an arbitrary distance -- this is the only value ever used
# when distance_m is omitted.
DEFAULT_EDIT_STEP_M = 1.0

_DIRECTION_UNIT_DELTA: dict[str, tuple[float, float]] = {
    "WEST": (-1.0, 0.0),
    "EAST": (1.0, 0.0),
    "NORTH": (0.0, -1.0),
    "SOUTH": (0.0, 1.0),
}


def direction_delta(direction: Direction, distance_m: float) -> tuple[float, float]:
    """The one function that turns a Direction + distance into a signed (dx, dy) offset."""
    if direction not in _DIRECTION_UNIT_DELTA:
        raise ValueError(f"unknown direction: {direction}")
    unit_dx, unit_dy = _DIRECTION_UNIT_DELTA[direction]
    return unit_dx * distance_m, unit_dy * distance_m


@dataclass(frozen=True)
class MoveRoomCommand:
    room_id: str
    direction: Direction
    distance_m: Optional[float] = None
    type: CommandType = "MOVE_ROOM"

    def resolved_distance_m(self) -> float:
        return self.distance_m if self.distance_m is not None else DEFAULT_EDIT_STEP_M


@dataclass(frozen=True)
class SpatialLayout:
    """Minimal bundle the edit layer needs: the room list (Spatial V1's room-dict shape --
    id/type/x/y/width/height/area_m2), the footprint (width_m/depth_m, for bounds checking), and
    OPTIONALLY the AccessTopology this layout must satisfy. When topology is given, the edit layer
    reuses `spatial_v1_topology.derive_door_topology` to confirm every required-access edge still
    lands on a real shared wall after the move."""
    rooms: list
    footprint: dict
    topology: object = None


@dataclass(frozen=True)
class EditResult:
    status: Literal["APPLIED", "REJECTED"]
    layout: Optional[SpatialLayout] = None
    reason: Optional[RejectReason] = None
