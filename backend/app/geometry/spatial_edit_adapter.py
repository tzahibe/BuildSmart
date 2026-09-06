"""Integration glue between the production `GeometricDesign` contract and Spatial V1's edit-layer
`SpatialLayout` -- NEW code for this integration task, distinct from the ported Spatial V1 modules
(`spatial_edit.py`, `spatial_edit_types.py`, `spatial_v1_topology.py`), which are unmodified.

ARCHITECTURAL NOTE (must be read before changing this file): production's `GeometrySolver` has no
Spatial V1 AccessTopology concept at all -- a persisted `Project.geometric_design` was never
produced by Spatial V1's CP-SAT/topology-first pipeline, so there is no stored AccessTopology to
hand to `SpatialLayout`. `geometric_design_to_spatial_layout` below reconstructs one instead: every
`DoorConnection` in a persisted `GeometricDesign` exists ONLY because
`app.geometry.geometric_design._find_direct_access_doors` found a satisfied `direct_access`
relationship between those two rooms (see that module's docstring) -- so treating each existing
door as a `REQUIRED_ACCESS` edge is a faithful reconstruction of "this adjacency was required,"
not a guess. This is what makes `CONSTRAINT_VIOLATION` detection possible for real, persisted
production designs without ever running Spatial V1's own generation pipeline or touching the real
solver.
"""
from app.geometry.geometric_design import (
    DoorConnection as ProductionDoorConnection,
    Footprint,
    GeometricDesign,
    GeometricRoom,
    Wall,
    _exterior_walls,
    _interior_walls,
    _wall_lookup,
)
from app.geometry.models import BuildingFootprintSpec, RoomInstance
from app.geometry.spatial_edit_types import SpatialLayout
from app.geometry.spatial_v1_topology import AccessEdge, AccessTopology, derive_door_topology


def geometric_design_to_spatial_layout(design: GeometricDesign) -> SpatialLayout:
    rooms = [
        {
            "id": room.id, "type": room.type,
            "x": room.x, "y": room.y,
            "width": room.width_m, "height": room.depth_m,
            "area_m2": room.area_m2,
        }
        for room in design.rooms
    ]
    footprint = {"width_m": design.footprint.width_m, "depth_m": design.footprint.depth_m}

    node_types = {room.id: room.type for room in design.rooms}
    edges = [AccessEdge(door.room_ids[0], door.room_ids[1], "REQUIRED_ACCESS") for door in design.doors]
    topology = AccessTopology(name="reconstructed_from_persisted_doors", edges=edges, node_types=node_types)

    return SpatialLayout(rooms=rooms, footprint=footprint, topology=topology)


def spatial_layout_to_geometric_design(layout: SpatialLayout, original: GeometricDesign) -> GeometricDesign:
    """Rebuilds a `GeometricDesign` from an edited `SpatialLayout`, reusing production's own wall
    functions (`_exterior_walls`/`_interior_walls`, unmodified, imported not duplicated) and
    Spatial V1's own `derive_door_topology` (unmodified) against the topology reconstructed by
    `geometric_design_to_spatial_layout`. Room metadata that a pure move never changes (type,
    floor, area_m2, is_circulation, source) is carried over from `original` by room id, not
    re-derived."""
    original_by_id = {room.id: room for room in original.rooms}
    floor = original.footprint.floor

    instances = [
        RoomInstance(
            id=r["id"], type=r["type"], floor=floor,
            x=r["x"], y=r["y"], width=r["width"], height=r["height"], area_m2=r["area_m2"],
        )
        for r in layout.rooms
    ]

    footprint_spec = BuildingFootprintSpec(
        width_m=layout.footprint["width_m"], depth_m=layout.footprint["depth_m"], floor=floor,
        # _exterior_walls/_interior_walls never read available_area_m2 -- the full-rectangle value
        # here only satisfies BuildingFootprintSpec's own validation, it drives no wall/door logic.
        available_area_m2=layout.footprint["width_m"] * layout.footprint["depth_m"],
    )

    walls: list[Wall] = _exterior_walls(footprint_spec) + _interior_walls(instances)
    wall_by_pair = _wall_lookup(walls)

    sv1_doors, mismatches = derive_door_topology(layout.rooms, layout.topology)
    if mismatches:
        # Should be unreachable: apply_spatial_edit() already rejects any edit that produces a
        # mismatch (CONSTRAINT_VIOLATION) before this function is ever called on an APPLIED result.
        raise ValueError(f"cannot build GeometricDesign from a layout with unresolved mismatches: {mismatches}")

    doors: list[ProductionDoorConnection] = []
    for d in sv1_doors:
        wall = wall_by_pair.get(frozenset((d.from_room, d.to_room)))
        if wall is None:
            continue  # defensive -- a derived door implies a wall was already built
        center = (wall.start + wall.end) / 2
        doors.append(
            ProductionDoorConnection(
                id=f"DOOR_{d.from_room}_{d.to_room}",
                wall_id=wall.id, orientation=wall.orientation, coord=wall.coord, center=center,
                width_m=d.width_m, room_ids=(d.from_room, d.to_room), provenance=d.provenance,
            )
        )

    rooms: list[GeometricRoom] = []
    for r in layout.rooms:
        source_room = original_by_id.get(r["id"])
        rooms.append(
            GeometricRoom(
                id=r["id"], type=r["type"], floor=floor, x=r["x"], y=r["y"],
                width_m=r["width"], depth_m=r["height"], area_m2=r["area_m2"],
                is_circulation=source_room.is_circulation if source_room else False,
                source=source_room.source if source_room else None,
            )
        )

    programmed_area_m2 = round(sum(room.area_m2 for room in rooms), 2)
    circulation_area_m2 = round(sum(room.area_m2 for room in rooms if room.is_circulation), 2)

    return GeometricDesign(
        footprint=Footprint(width_m=footprint_spec.width_m, depth_m=footprint_spec.depth_m, floor=floor),
        rooms=rooms, walls=walls, doors=doors,
        programmed_area_m2=programmed_area_m2, circulation_area_m2=circulation_area_m2,
    )
