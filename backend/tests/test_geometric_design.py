"""Unit tests for `app.geometry.geometric_design.build_geometric_design` — the stable UI DTO builder.

Constructs `RoomInstance`/`ArchitecturalSpec`/`BuildingFootprintSpec`/`GeometrySolverResult` directly
(same convention as test_geometry_solver.py) rather than running the full solver, so each test isolates
exactly one derivation this module makes.
"""

from app.architect.models import (
    AdjacencyConstraint,
    ArchitecturalSpec,
    ConstraintSeverity,
    DirectAccessConstraint,
    ProgramItem,
)
from app.geometry.geometric_design import build_geometric_design
from app.geometry.models import BuildingFootprintSpec, GeometrySolverResult, RoomInstance, SolverStatus


def _spec(relationships=()) -> ArchitecturalSpec:
    return ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=12.0),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=12.0),
        ],
        zones=[],
        relationships=list(relationships),
        circulation=None,
        incomplete_requirements=[],
    )


def _footprint() -> BuildingFootprintSpec:
    return BuildingFootprintSpec(width_m=6.0, depth_m=4.0, floor=1, available_area_m2=24.0)


def _two_adjacent_rooms() -> list[RoomInstance]:
    # living_room [0,0]-[3,4], bedroom [3,0]-[6,4] — share the full x=3 vertical edge (length 4 >=
    # the solver's own 0.9 m direct_access threshold).
    return [
        RoomInstance(id="LIVING_ROOM", type="living_room", floor=1, x=0.0, y=0.0, width=3.0, height=4.0, area_m2=12.0),
        RoomInstance(id="BEDROOM", type="bedroom", floor=1, x=3.0, y=0.0, width=3.0, height=4.0, area_m2=12.0),
    ]


def _result(instances: list[RoomInstance]) -> GeometrySolverResult:
    return GeometrySolverResult(status=SolverStatus.satisfied, instances=instances)


def test_exterior_walls_match_footprint_not_room_extents():
    footprint = BuildingFootprintSpec(width_m=10.0, depth_m=5.0, floor=1, available_area_m2=50.0)
    # Rooms only occupy a small corner — the exterior boundary must still be the FOOTPRINT, not a
    # bounding box around the rooms (the bug the old frontend had).
    instances = [RoomInstance(id="KITCHEN", type="kitchen", floor=1, x=0.0, y=0.0, width=2.0, height=2.0, area_m2=4.0)]

    design = build_geometric_design(_spec(), footprint, _result(instances))

    exterior = [w for w in design.walls if w.kind == "exterior"]
    assert len(exterior) == 4
    assert {(w.orientation, w.coord) for w in exterior} == {
        ("horizontal", 0.0),
        ("horizontal", 5.0),
        ("vertical", 0.0),
        ("vertical", 10.0),
    }
    assert design.footprint.width_m == 10.0
    assert design.footprint.depth_m == 5.0


def test_plain_adjacency_produces_a_wall_but_no_door():
    spec = _spec([
        AdjacencyConstraint(
            room_type_a="living_room", room_type_b="bedroom", severity=ConstraintSeverity.soft
        )
    ])
    design = build_geometric_design(spec, _footprint(), _result(_two_adjacent_rooms()))

    interior = [w for w in design.walls if w.kind == "interior"]
    assert len(interior) == 1
    assert interior[0].room_ids == ["LIVING_ROOM", "BEDROOM"]
    assert design.doors == []


def test_satisfied_direct_access_produces_exactly_one_door_on_the_shared_wall():
    spec = _spec([
        DirectAccessConstraint(
            room_type_a="living_room", room_type_b="bedroom", severity=ConstraintSeverity.hard
        )
    ])
    design = build_geometric_design(spec, _footprint(), _result(_two_adjacent_rooms()))

    assert len(design.doors) == 1
    door = design.doors[0]
    assert set(door.room_ids) == {"LIVING_ROOM", "BEDROOM"}
    interior_wall = next(w for w in design.walls if w.kind == "interior")
    assert door.wall_id == interior_wall.id
    assert door.orientation == interior_wall.orientation == "vertical"
    assert door.coord == interior_wall.coord == 3.0
    assert 0.0 <= door.center - door.width_m / 2 and door.center + door.width_m / 2 <= 4.0


def test_direct_access_relationship_with_no_real_shared_wall_produces_no_door():
    # Two rooms far apart — a direct_access relationship exists between their TYPES, but these specific
    # instances don't even touch, so nothing should be fabricated.
    instances = [
        RoomInstance(id="LIVING_ROOM", type="living_room", floor=1, x=0.0, y=0.0, width=3.0, height=4.0, area_m2=12.0),
        RoomInstance(id="BEDROOM", type="bedroom", floor=1, x=10.0, y=10.0, width=3.0, height=4.0, area_m2=12.0),
    ]
    spec = _spec([
        DirectAccessConstraint(
            room_type_a="living_room", room_type_b="bedroom", severity=ConstraintSeverity.hard
        )
    ])
    design = build_geometric_design(spec, _footprint(), _result(instances))

    assert design.doors == []
    assert [w for w in design.walls if w.kind == "interior"] == []


def test_circulation_rooms_are_flagged_and_summed_separately_from_programmed_area():
    instances = [
        RoomInstance(id="LIVING_ROOM", type="living_room", floor=1, x=0.0, y=0.0, width=3.0, height=4.0, area_m2=12.0),
        RoomInstance(id="CORRIDOR", type="corridor", floor=1, x=3.0, y=0.0, width=3.0, height=4.0, area_m2=12.0),
    ]
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=12.0),
            ProgramItem(room_type="corridor", count=1, target_area_m2=12.0),
        ],
        zones=[],
        relationships=[],
        circulation=None,
        incomplete_requirements=[],
    )
    design = build_geometric_design(spec, _footprint(), _result(instances))

    by_id = {room.id: room for room in design.rooms}
    assert by_id["CORRIDOR"].is_circulation is True
    assert by_id["LIVING_ROOM"].is_circulation is False
    assert design.circulation_area_m2 == 12.0
    assert design.programmed_area_m2 == 24.0


def test_no_circulation_rooms_gives_zero_circulation_area_not_a_guess():
    design = build_geometric_design(_spec(), _footprint(), _result(_two_adjacent_rooms()))

    assert design.circulation_area_m2 == 0.0
    assert all(not room.is_circulation for room in design.rooms)
