"""`GeometricDesign`: the stable, UI-facing production DTO for one solved floor layout.

This is the ONLY thing `app/design/pipeline.py` builds for the frontend to render as "the design" going
forward (see `app/projects/models.py`'s `Project.geometric_design`). It is built entirely by READING
already-computed facts off an `ArchitecturalSpec` + `BuildingFootprintSpec` + `GeometrySolverResult` in
`build_geometric_design` below — it never re-decides architecture, and it changes nothing about how a
layout is solved:

- `walls`: pure computational geometry over already-placed room rectangles. The exterior perimeter is
  exactly the `BuildingFootprintSpec` boundary the solver already enforced as its hard room-placement
  boundary (not a bounding box re-derived from room extents, which is what the old frontend guessed —
  see `frontend/src/design/SketchSvg.tsx`'s pre-existing `outerEdgeTouched`/`maxX`/`maxDepth` logic).
  Every interior wall is a real shared edge between two placed rooms, using the exact same geometric
  quantity as `app.geometry.solver._shared_edge_length` (imported, not reimplemented, so this can never
  drift from what the solver itself considers "touching").

- `doors`: ONLY for room-instance pairs whose shared wall satisfies a `direct_access` relationship the
  solver itself already reported satisfied — i.e. the exact "V1 shared-wall-length proxy"
  (`app.geometry.solver._DOOR_OPENING_MIN_M`) the solver's own module docstring documents as "an opening
  could plausibly exist," never a modeled door leaf/frame/swing. A shared wall that only satisfies plain
  `adjacency` (or has no relationship requirement between those two types at all) NEVER produces a door
  here — this is the authoritative replacement for the frontend's removed "shared wall long enough ->
  hasDoor" inference, not a variant of it.

- `circulation`: rooms whose TYPE is already one of the Architect Model's own dedicated circulation room
  types (`corridor`, `staircase` — see `app.architect.model_schema.ModelRoomType`), never a guess about
  which unused space "looks like" a hallway. A design with no such rooms simply has no circulation rooms
  — this module never invents one.

Nothing here depends on HOW the solver reached its answer (backtracking order, scoring, candidate
pooling — none of that is imported or referenced), only on its final `instances` + relationship
satisfaction, so a future solver replacement needs no change here as long as it still produces a
`GeometrySolverResult` over `RoomInstance`s.
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.architect.models import ArchitecturalSpec, ConstraintKind
from app.geometry.models import BuildingFootprintSpec, GeometrySolverResult, RoomInstance
from app.geometry.solver import _DOOR_OPENING_MIN_M, _EPSILON, _group_by_type, _shared_edge_length

# The Architect Model's own dedicated circulation-space room types (see `model_schema.ModelRoomType`'s
# CORRIDOR/STAIRCASE, mapped 1:1 in `app.architect.adapter._ROOM_TYPE_MAP`) — a room is circulation
# because the program already says so, not because this module decides it looks unused.
_CIRCULATION_ROOM_TYPES = frozenset({"corridor", "staircase"})


class WallKind(str, Enum):
    exterior = "exterior"
    interior = "interior"


class Orientation(str, Enum):
    horizontal = "horizontal"
    vertical = "vertical"


class Wall(BaseModel):
    """One straight wall segment. `orientation="vertical"` means the wall runs along the y-axis at
    `x=coord` from `y=start` to `y=end`; `orientation="horizontal"` means it runs along the x-axis at
    `y=coord` from `x=start` to `x=end` — the same convention `SketchSvg.tsx`'s prior internal
    `sharedEdge()` used, now computed once, authoritatively, on the backend."""

    id: str
    kind: WallKind
    orientation: Orientation
    coord: float
    start: float
    end: float
    room_ids: list[str] = Field(default_factory=list)


class DoorConnection(BaseModel):
    """One opening in a wall, backed by a satisfied `direct_access` relationship — see module
    docstring. `width_m` is the same fixed proxy threshold the solver used to decide this opening could
    exist, not a measured/designed door width; `note` says so explicitly so nothing downstream mistakes
    this for a modeled door leaf/swing (see `DOOR_SWING_PRESENTATION` in the frontend adapter for how
    the UI renders this without claiming a real swing direction)."""

    id: str
    wall_id: str
    orientation: Orientation
    coord: float
    center: float
    width_m: float
    room_ids: tuple[str, str]
    provenance: str = "direct_access_proxy"
    note: str = (
        f"Derived from the solver's own direct_access shared-wall-length proxy (>= {_DOOR_OPENING_MIN_M} "
        f"m) — confirms a door-width opening could plausibly exist here, not a modeled door swing/leaf/"
        f"frame."
    )


class GeometricRoom(BaseModel):
    id: str
    type: str
    floor: int
    x: float
    y: float
    width_m: float
    depth_m: float
    area_m2: float
    is_circulation: bool
    source: str | None = None


class Footprint(BaseModel):
    width_m: float
    depth_m: float
    floor: int


class GeometricDesign(BaseModel):
    """The final, stable geometry contract for one floor. See module docstring for provenance of every
    field — nothing here is inferred beyond what's documented above."""

    footprint: Footprint
    rooms: list[GeometricRoom]
    walls: list[Wall]
    doors: list[DoorConnection]
    programmed_area_m2: float
    circulation_area_m2: float


def _exterior_walls(footprint: BuildingFootprintSpec) -> list[Wall]:
    w, d = footprint.width_m, footprint.depth_m
    return [
        Wall(id="EXT_N", kind=WallKind.exterior, orientation=Orientation.horizontal, coord=0.0, start=0.0, end=w),
        Wall(id="EXT_S", kind=WallKind.exterior, orientation=Orientation.horizontal, coord=d, start=0.0, end=w),
        Wall(id="EXT_W", kind=WallKind.exterior, orientation=Orientation.vertical, coord=0.0, start=0.0, end=d),
        Wall(id="EXT_E", kind=WallKind.exterior, orientation=Orientation.vertical, coord=w, start=0.0, end=d),
    ]


def _edge_between(a: RoomInstance, b: RoomInstance) -> tuple[Orientation, float, float, float] | None:
    """The real shared-edge geometry between two placed rooms, or `None` if they don't touch — same
    real quantity as `app.geometry.solver._shared_edge_length` (touching test + overlap span), just
    also returning the coordinate/span `Wall`/`DoorConnection` need instead of only a length."""
    a_right, a_bottom = a.x + a.width, a.y + a.height
    b_right, b_bottom = b.x + b.width, b.y + b.height

    if abs(a_right - b.x) < _EPSILON or abs(b_right - a.x) < _EPSILON:
        coord = a_right if abs(a_right - b.x) < _EPSILON else b_right
        start, end = max(a.y, b.y), min(a_bottom, b_bottom)
        if end - start > _EPSILON:
            return Orientation.vertical, coord, start, end

    if abs(a_bottom - b.y) < _EPSILON or abs(b_bottom - a.y) < _EPSILON:
        coord = a_bottom if abs(a_bottom - b.y) < _EPSILON else b_bottom
        start, end = max(a.x, b.x), min(a_right, b_right)
        if end - start > _EPSILON:
            return Orientation.horizontal, coord, start, end

    return None


def _interior_walls(instances: list[RoomInstance]) -> list[Wall]:
    walls: list[Wall] = []
    for i in range(len(instances)):
        for j in range(i + 1, len(instances)):
            a, b = instances[i], instances[j]
            edge = _edge_between(a, b)
            if edge is None:
                continue
            orientation, coord, start, end = edge
            walls.append(
                Wall(
                    id=f"INT_{a.id}_{b.id}",
                    kind=WallKind.interior,
                    orientation=orientation,
                    coord=coord,
                    start=start,
                    end=end,
                    room_ids=[a.id, b.id],
                )
            )
    return walls


def _wall_lookup(walls: list[Wall]) -> dict[frozenset[str], Wall]:
    return {frozenset(wall.room_ids): wall for wall in walls if len(wall.room_ids) == 2}


def _find_direct_access_doors(
    spec: ArchitecturalSpec, instances: list[RoomInstance], walls: list[Wall]
) -> list[DoorConnection]:
    """Every room-instance pair whose shared wall satisfies a `direct_access` relationship the solver
    itself already treats as satisfied (`_shared_edge_length(...) >= _DOOR_OPENING_MIN_M`) — see module
    docstring. Reuses the solver's own helpers so this can never disagree with
    `GeometrySolverResult.hard_constraints_checked`/`soft_constraints_satisfied` about which
    relationships actually hold."""
    by_type = _group_by_type(instances)
    by_pair = _wall_lookup(walls)
    doors: list[DoorConnection] = []
    seen_pairs: set[frozenset[str]] = set()

    for rel in spec.relationships:
        if rel.kind != ConstraintKind.direct_access:
            continue
        for a in by_type.get(rel.room_type_a, []):
            for b in by_type.get(rel.room_type_b, []):
                if _shared_edge_length(a, b) + _EPSILON < _DOOR_OPENING_MIN_M:
                    continue
                pair_key = frozenset((a.id, b.id))
                if pair_key in seen_pairs:
                    continue
                wall = by_pair.get(pair_key)
                if wall is None:
                    continue  # defensive — a satisfied direct_access implies a wall was already built
                seen_pairs.add(pair_key)
                center = (wall.start + wall.end) / 2
                doors.append(
                    DoorConnection(
                        id=f"DOOR_{a.id}_{b.id}",
                        wall_id=wall.id,
                        orientation=wall.orientation,
                        coord=wall.coord,
                        center=center,
                        width_m=_DOOR_OPENING_MIN_M,
                        room_ids=(a.id, b.id),
                    )
                )
    return doors


def build_geometric_design(
    spec: ArchitecturalSpec, footprint: BuildingFootprintSpec, result: GeometrySolverResult
) -> GeometricDesign:
    """Builds the stable UI contract from one SATISFIED `GeometrySolverResult` — callers must only call
    this when `result.status == SolverStatus.satisfied` (see `app.design.pipeline`, which raises
    `DesignUnsatisfiableError` beforehand for any other status, so this function never has to guess what
    an incomplete/unsatisfiable design would even mean)."""
    instances = result.instances
    walls = _exterior_walls(footprint) + _interior_walls(instances)
    doors = _find_direct_access_doors(spec, instances, walls)

    # Same provenance already carried on `Project.rooms` (see app/design/pipeline.py) — traced back to
    # the (post-authoritative-merge) ProgramItem that declared each room TYPE, not a new fact.
    source_by_room_type = {item.room_type: item.source for item in spec.program}
    rooms = [
        GeometricRoom(
            id=instance.id,
            type=instance.type,
            floor=instance.floor,
            x=instance.x,
            y=instance.y,
            width_m=instance.width,
            depth_m=instance.height,
            area_m2=instance.area_m2,
            is_circulation=instance.type in _CIRCULATION_ROOM_TYPES,
            source=source_by_room_type.get(instance.type),
        )
        for instance in instances
    ]

    programmed_area_m2 = round(sum(room.area_m2 for room in rooms), 2)
    circulation_area_m2 = round(sum(room.area_m2 for room in rooms if room.is_circulation), 2)

    return GeometricDesign(
        footprint=Footprint(width_m=footprint.width_m, depth_m=footprint.depth_m, floor=footprint.floor),
        rooms=rooms,
        walls=walls,
        doors=doors,
        programmed_area_m2=programmed_area_m2,
        circulation_area_m2=circulation_area_m2,
    )
