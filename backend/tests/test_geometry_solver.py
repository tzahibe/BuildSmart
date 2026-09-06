import pytest

from app.architect.gateway import MockArchitectModelGateway
from app.architect.models import (
    AdjacencyConstraint,
    ArchitecturalSpec,
    ArchitectModelRequest,
    Circulation,
    ConstraintSeverity,
    DirectAccessConstraint,
    ProgramItem,
    RequiredRoomConstraint,
    SeparationConstraint,
    SiteSpec,
    Zone,
)
from app.geometry.instances import expand_program_to_instances
from app.geometry.models import BuildingFootprintSpec, Edge, RoomInstance, SolverStatus
from app.geometry.solver import (
    GeometrySolver,
    _DIRECT_ACCESS_PROXY_NOTE,
    _circulation_reach_score,
    _find_pre_solver_contradiction,
    _group_by_type,
    _rectangle_gap,
    _shared_edge_length,
    _touches_an_allowed_entry_edge,
    _touches_edge,
    _touches_perimeter,
    _zone_cohesion_score,
)

# --- Type-to-instance mapping --------------------------------------------------------------------


def test_count_one_gets_bare_type_name_no_suffix():
    program = [ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0)]

    instances = expand_program_to_instances(program)

    assert [instance_id for instance_id, _type, _item in instances] == ["KITCHEN"]


def test_count_three_gets_numbered_suffixes():
    program = [ProgramItem(room_type="bedroom", count=3, target_area_m2=12.0)]

    instances = expand_program_to_instances(program)

    assert [instance_id for instance_id, _type, _item in instances] == [
        "BEDROOM_1",
        "BEDROOM_2",
        "BEDROOM_3",
    ]
    assert all(room_type == "bedroom" for _id, room_type, _item in instances)


def test_instance_order_follows_program_order():
    program = [
        ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0),
        ProgramItem(room_type="bedroom", count=2, target_area_m2=12.0),
    ]

    ids = [instance_id for instance_id, _type, _item in expand_program_to_instances(program)]

    assert ids == ["KITCHEN", "BEDROOM_1", "BEDROOM_2"]


def test_expansion_is_deterministic_across_repeated_calls():
    program = [
        ProgramItem(room_type="bedroom", count=3, target_area_m2=12.0),
        ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0),
    ]

    first = expand_program_to_instances(program)
    second = expand_program_to_instances(program)

    assert first == second
    assert [instance_id for instance_id, _type, _item in first] == [
        "BEDROOM_1",
        "BEDROOM_2",
        "BEDROOM_3",
        "KITCHEN",
    ]


# --- Test fixtures: hand-built ArchitecturalSpec examples ----------------------------------------


def _simple_spec() -> ArchitecturalSpec:
    """Kitchen + living room, one hard adjacency requirement. Should comfortably fit a generous
    footprint."""
    return ArchitecturalSpec(
        program=[
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, min_width_m=1.6),
            ProgramItem(room_type="living_room", count=1, target_area_m2=20.0, min_width_m=3.0),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=12.0, min_width_m=2.6),
        ],
        zones=[
            Zone(name="public", room_types=["kitchen", "living_room"]),
            Zone(name="private", room_types=["bedroom", "bathroom"]),
        ],
        relationships=[
            AdjacencyConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard),
            AdjacencyConstraint(room_type_a="bedroom", room_type_b="bathroom", severity=ConstraintSeverity.soft),
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )


def _multi_bedroom_spec_with_hard_safe_room_access() -> ArchitecturalSpec:
    """3 bedrooms + a safe room that MUST have direct access from *a* bedroom (hard) — exercises
    hard-relationship resolution across multiple instances of the same type."""
    return ArchitecturalSpec(
        program=[
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, min_width_m=1.6),
            ProgramItem(room_type="living_room", count=1, target_area_m2=20.0, min_width_m=3.0),
            ProgramItem(room_type="bedroom", count=3, target_area_m2=12.0, min_width_m=2.6),
            ProgramItem(room_type="safe_room", count=1, target_area_m2=9.0, min_width_m=2.2),
        ],
        zones=[
            Zone(name="public", room_types=["kitchen", "living_room"]),
            Zone(name="private", room_types=["bedroom", "bathroom", "safe_room"]),
        ],
        relationships=[
            AdjacencyConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard),
            DirectAccessConstraint(room_type_a="safe_room", room_type_b="bedroom", severity=ConstraintSeverity.hard),
            AdjacencyConstraint(room_type_a="bedroom", room_type_b="bathroom", severity=ConstraintSeverity.soft),
        ],
        circulation=Circulation(entry_room_type="living_room", requires_hallway=True),
    )


def _infeasible_spec() -> ArchitecturalSpec:
    """Rooms whose combined minimum footprint cannot fit a tiny footprint — must fail cleanly."""
    return ArchitecturalSpec(
        program=[
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
            ProgramItem(room_type="living_room", count=1, target_area_m2=20.0, min_width_m=3.0),
            ProgramItem(room_type="bedroom", count=3, target_area_m2=12.0, min_width_m=2.6),
        ],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="living_room"),
    )


def _generous_footprint(floor: int = 1) -> BuildingFootprintSpec:
    return BuildingFootprintSpec(width_m=10, depth_m=10, floor=floor, available_area_m2=100)


# --- Invariant helpers ----------------------------------------------------------------------------


def _assert_within_bounds(instances: list[RoomInstance], footprint: BuildingFootprintSpec) -> None:
    for room in instances:
        assert room.x >= -1e-6
        assert room.y >= -1e-6
        assert room.x + room.width <= footprint.width_m + 1e-6
        assert room.y + room.height <= footprint.depth_m + 1e-6
        assert room.floor == footprint.floor


def _assert_no_overlaps(instances: list[RoomInstance]) -> None:
    for i, a in enumerate(instances):
        for b in instances[i + 1 :]:
            overlap_x = a.x < b.x + b.width - 1e-6 and b.x < a.x + a.width - 1e-6
            overlap_y = a.y < b.y + b.height - 1e-6 and b.y < a.y + a.height - 1e-6
            assert not (overlap_x and overlap_y), f"{a.id} overlaps {b.id}"


# --- Solver: valid examples -------------------------------------------------------------------


def test_simple_spec_produces_one_instance_per_room_and_satisfies_hard_adjacency():
    footprint = _generous_footprint()

    result = GeometrySolver().solve(_simple_spec(), footprint)

    assert result.status == SolverStatus.satisfied
    assert {room.id for room in result.instances} == {"KITCHEN", "BATHROOM", "LIVING_ROOM", "BEDROOM"}
    _assert_within_bounds(result.instances, footprint)
    _assert_no_overlaps(result.instances)
    assert all(check.satisfied for check in result.hard_constraints_checked)

    by_id = {room.id: room for room in result.instances}
    kitchen, living_room = by_id["KITCHEN"], by_id["LIVING_ROOM"]
    assert _shared_edge_length(kitchen, living_room) > 0


def test_multi_bedroom_spec_expands_instances_and_satisfies_hard_direct_access():
    footprint = BuildingFootprintSpec(width_m=14, depth_m=12, available_area_m2=14 * 12)
    spec = _multi_bedroom_spec_with_hard_safe_room_access()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    expected_ids = {"KITCHEN", "BATHROOM", "LIVING_ROOM", "BEDROOM_1", "BEDROOM_2", "BEDROOM_3", "SAFE_ROOM"}
    assert {room.id for room in result.instances} == expected_ids
    _assert_within_bounds(result.instances, footprint)
    _assert_no_overlaps(result.instances)

    by_id = {room.id: room for room in result.instances}
    safe_room = by_id["SAFE_ROOM"]
    bedrooms = [by_id["BEDROOM_1"], by_id["BEDROOM_2"], by_id["BEDROOM_3"]]
    assert any(
        _shared_edge_length(safe_room, bedroom) + 1e-6 >= 0.9 for bedroom in bedrooms
    ), "safe room must have a door-width-or-wider shared wall with at least one bedroom (HARD direct_access)"


def test_generous_footprint_achieves_the_soft_adjacency_too():
    footprint = _generous_footprint()

    result = GeometrySolver().solve(_simple_spec(), footprint)

    assert result.status == SolverStatus.satisfied
    assert any("bedroom" in check.description and "bathroom" in check.description for check in result.soft_constraints_satisfied)
    # objective_score is the documented, explainable sum of its breakdown's own components (relationship/
    # zone/circulation terms plus the geometric quality terms added this milestone — see
    # app/geometry/solver.py's `_score_candidate`) — not a magic number and not just the old
    # relationship-only formula.
    breakdown = result.objective_breakdown
    assert breakdown is not None
    assert result.objective_score == breakdown.total
    assert breakdown.soft_relationships_satisfied == len(result.soft_constraints_satisfied)
    assert breakdown.zone_cohesion_score == result.zone_cohesion_score
    assert breakdown.circulation_reach_score == result.circulation_reach_score
    assert result.objective_score == round(
        breakdown.soft_relationships_satisfied
        + breakdown.zone_cohesion_score
        + breakdown.circulation_reach_score
        + breakdown.utilization_term
        + breakdown.compactness_term
        + breakdown.fragmentation_term,
        4,
    )


def test_mock_gateway_output_is_solvable_end_to_end():
    # Integration: ArchitectModelGateway -> GeometrySolver, exactly the intended pipeline.
    footprint = BuildingFootprintSpec(width_m=16, depth_m=14, available_area_m2=16 * 14)
    request = ArchitectModelRequest(
        brief="בית עם 3 חדרי שינה וממ\"ד",
        site=SiteSpec(width_m=500, depth_m=500),  # deliberately huge/unrelated — see the site-vs-
        # footprint test below for why this must not matter to the solver.
        hard_constraints=[
            RequiredRoomConstraint(room_type="bedroom", count=3, severity=ConstraintSeverity.hard),
            RequiredRoomConstraint(room_type="safe_room", count=1, severity=ConstraintSeverity.hard),
        ],
    )
    spec = MockArchitectModelGateway().generate(request)

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    _assert_within_bounds(result.instances, footprint)
    _assert_no_overlaps(result.instances)
    # kitchen, bathroom, living_room, 3x bedroom, safe_room
    assert len(result.instances) == 7


# --- Site vs. footprint separation (the actual point of this milestone) ------------------------


def test_solver_signature_takes_a_footprint_not_a_site():
    import inspect

    params = list(inspect.signature(GeometrySolver.solve).parameters)
    assert "site" not in params
    assert "footprint" in params


def test_huge_site_does_not_rescue_a_footprint_too_small_to_fit_the_program():
    # The spec needs ~49 m² (12+5+20+12); the SITE is enormous (would fit it 100x over), but the
    # FOOTPRINT is tiny. If site geometry leaked into the boundary check, this would incorrectly
    # succeed. `ArchitectModelRequest.site` isn't even passed to the solver — this test also directly
    # confirms the tiny footprint is what actually fails it.
    tiny_footprint = BuildingFootprintSpec(width_m=4, depth_m=4, available_area_m2=16)

    result = GeometrySolver().solve(_simple_spec(), tiny_footprint)

    assert result.status == SolverStatus.unsatisfiable
    assert result.instances == []
    assert result.unsatisfiable_reason is not None
    assert "4.0x4.0" in result.unsatisfiable_reason


def test_footprint_available_area_is_enforced_even_when_the_rectangle_would_fit_more():
    # 10x10 = 100 m² of bounding rectangle, but available_area_m2 is capped well below what the
    # simple spec needs (~49 m²) — the rectangle alone would allow it, but the explicit area budget
    # must still be enforced as a separate hard check.
    footprint = BuildingFootprintSpec(width_m=10, depth_m=10, available_area_m2=20)

    result = GeometrySolver().solve(_simple_spec(), footprint)

    assert result.status == SolverStatus.unsatisfiable


def test_all_placed_instances_stay_within_the_footprint_rectangle():
    footprint = BuildingFootprintSpec(width_m=9, depth_m=7, available_area_m2=9 * 7)

    result = GeometrySolver().solve(_simple_spec(), footprint)

    assert result.status == SolverStatus.satisfied
    _assert_within_bounds(result.instances, footprint)


# --- Adjacency vs. direct access must not be collapsed -----------------------------------------


def test_shared_edge_length_below_door_width_is_adjacent_but_not_direct_access():
    a = RoomInstance(id="A", type="a", floor=1, x=0, y=0, width=2.0, height=2.0, area_m2=4.0)
    # b sits to the right of a, but shifted down so only the last 0.3 m of a's right edge overlaps b's
    # left edge.
    b = RoomInstance(id="B", type="b", floor=1, x=2.0, y=1.7, width=2.0, height=2.0, area_m2=4.0)

    shared = _shared_edge_length(a, b)

    assert 0 < shared < 0.9
    from app.architect.models import ConstraintKind

    adjacency_satisfied = shared > 1e-6
    direct_access_satisfied = shared + 1e-6 >= 0.9
    assert adjacency_satisfied is True
    assert direct_access_satisfied is False
    assert ConstraintKind.adjacency != ConstraintKind.direct_access  # distinct kinds in the data model


def test_shared_edge_length_at_least_door_width_satisfies_both():
    a = RoomInstance(id="A", type="a", floor=1, x=0, y=0, width=2.0, height=2.0, area_m2=4.0)
    b = RoomInstance(id="B", type="b", floor=1, x=2.0, y=0.0, width=2.0, height=2.0, area_m2=4.0)

    shared = _shared_edge_length(a, b)

    assert shared >= 0.9


# --- min/max area semantics --------------------------------------------------------------------


def test_solved_area_respects_min_and_max_area_bounds():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="office", count=1, min_area_m2=8.0, max_area_m2=10.0, min_width_m=2.0),
        ],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="office"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    office = result.instances[0]
    assert 8.0 - 1e-6 <= office.area_m2 <= 10.0 + 1e-6


def test_target_area_is_preferred_when_it_fits_within_bounds():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(
                room_type="office", count=1, target_area_m2=9.0, min_area_m2=8.0, max_area_m2=10.0, min_width_m=2.0
            ),
        ],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="office"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    assert result.instances[0].area_m2 == 9.0


# --- Infeasible spec must fail cleanly, with diagnostics ----------------------------------------


def test_infeasible_spec_returns_unsatisfiable_status_not_a_partial_layout():
    tiny_footprint = BuildingFootprintSpec(width_m=3, depth_m=3, available_area_m2=9)

    result = GeometrySolver().solve(_infeasible_spec(), tiny_footprint)

    assert result.status == SolverStatus.unsatisfiable
    assert result.instances == []
    assert result.hard_constraints_checked == []
    assert result.unsatisfiable_reason


def _room(id_: str, room_type: str, x: float, y: float, width: float, height: float, floor: int = 1) -> RoomInstance:
    return RoomInstance(
        id=id_, type=room_type, floor=floor, x=x, y=y, width=width, height=height, area_m2=round(width * height, 2)
    )


# --- Zones influence placement --------------------------------------------------------------------


def test_zone_cohesion_score_prefers_grouped_over_scattered_same_zone_rooms():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="bedroom", count=1, target_area_m2=9.0),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=6.0),
        ],
        zones=[Zone(name="private", room_types=["bedroom", "bathroom"])],
        relationships=[],
        circulation=Circulation(entry_room_type="bedroom"),
    )
    grouped = [_room("BEDROOM", "bedroom", 0, 0, 3, 3), _room("BATHROOM", "bathroom", 3, 0, 2, 3)]
    scattered = [_room("BEDROOM", "bedroom", 0, 0, 3, 3), _room("BATHROOM", "bathroom", 10, 10, 2, 3)]

    grouped_score = _zone_cohesion_score(spec, _group_by_type(grouped))
    scattered_score = _zone_cohesion_score(spec, _group_by_type(scattered))

    assert grouped_score > scattered_score
    assert scattered_score == 0


def test_solver_favors_same_zone_grouping_when_multiple_layouts_are_valid():
    # No hard relationship ties bedroom/bathroom together — only the zone's soft cohesion objective
    # should pull them toward each other.
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=9.0, min_width_m=2.6),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, min_width_m=1.8),
        ],
        zones=[Zone(name="private", room_types=["bedroom", "bathroom"])],
        relationships=[],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    assert result.zone_cohesion_score > 0
    by_id = {r.id: r for r in result.instances}
    assert _shared_edge_length(by_id["BEDROOM"], by_id["BATHROOM"]) > 0


def test_hard_zone_cohesion_rejects_a_split_zone():
    # A hard "private" zone spanning bedroom+bathroom requires them adjacent (only 2 rooms, so
    # "connected" means directly touching) — but a hard separation between the very same two types
    # forbids that. Together these are only satisfiable if hard zone-cohesion is actually enforced
    # (without it, the separation alone would trivially succeed by placing them apart).
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=9.0, min_width_m=2.6),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, min_width_m=1.8),
        ],
        zones=[Zone(name="private", room_types=["bedroom", "bathroom"], cohesion_severity=ConstraintSeverity.hard)],
        relationships=[
            SeparationConstraint(room_type_a="bedroom", room_type_b="bathroom", severity=ConstraintSeverity.hard)
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.unsatisfiable


# --- Circulation: entry room perimeter access ------------------------------------------------------


def test_touches_perimeter_true_for_room_flush_with_footprint_edge():
    footprint = BuildingFootprintSpec(width_m=10, depth_m=10, available_area_m2=100)
    room = _room("LIVING_ROOM", "living_room", 0, 0, 4, 4)

    assert _touches_perimeter(room, footprint) is True


def test_touches_perimeter_false_for_a_fully_interior_room():
    footprint = BuildingFootprintSpec(width_m=10, depth_m=10, available_area_m2=100)
    room = _room("CLOSET", "closet", 3, 3, 2, 2)

    assert _touches_perimeter(room, footprint) is False


def test_solved_entry_room_always_touches_the_footprint_perimeter():
    footprint = _generous_footprint()

    result = GeometrySolver().solve(_simple_spec(), footprint)

    assert result.status == SolverStatus.satisfied
    entry_room = next(r for r in result.instances if r.type == "living_room")
    assert _touches_perimeter(entry_room, footprint)
    assert any(
        check.kind == "entry_perimeter_access" and check.satisfied for check in result.hard_constraints_checked
    )


# --- Circulation: reach objective -------------------------------------------------------------------


def test_circulation_reach_score_is_zero_when_hallway_not_required():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=9.0),
        ],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="living_room", requires_hallway=False),
    )
    touching = [_room("LIVING_ROOM", "living_room", 0, 0, 4, 4), _room("BEDROOM", "bedroom", 4, 0, 3, 3)]

    assert _circulation_reach_score(spec, _group_by_type(touching)) == 0.0


def test_circulation_reach_score_rewards_direct_adjacency_to_entry_room():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0),
            ProgramItem(room_type="bedroom", count=2, target_area_m2=9.0),
        ],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="living_room", requires_hallway=True),
    )
    # BEDROOM_1 touches the living room directly; BEDROOM_2 only touches BEDROOM_1 — exactly the
    # "obviously depends on passing through an unrelated room" case this objective discourages.
    nested = [
        _room("LIVING_ROOM", "living_room", 0, 0, 4, 4),
        _room("BEDROOM_1", "bedroom", 4, 0, 3, 3),
        _room("BEDROOM_2", "bedroom", 7, 0, 3, 3),
    ]
    both_direct = [
        _room("LIVING_ROOM", "living_room", 0, 0, 6, 6),
        _room("BEDROOM_1", "bedroom", 6, 0, 3, 3),
        _room("BEDROOM_2", "bedroom", 0, 6, 3, 3),
    ]

    nested_score = _circulation_reach_score(spec, _group_by_type(nested))
    both_direct_score = _circulation_reach_score(spec, _group_by_type(both_direct))

    assert nested_score == 1.0
    assert both_direct_score == 2.0
    assert both_direct_score > nested_score


def test_circulation_reach_objective_influences_the_solvers_chosen_layout():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="bedroom", count=2, target_area_m2=9.0, min_width_m=2.4),
        ],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="living_room", requires_hallway=True),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    # At least one bedroom must directly reach the entry room; the objective existing at all (and
    # being reported) is what's under test — see the unit-level scoring tests above for proof it can
    # actually distinguish better from worse layouts.
    assert result.circulation_reach_score >= 1.0


# --- Separation constraint end-to-end ---------------------------------------------------------------


def test_hard_separation_default_enforces_non_adjacency():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="safe_room", count=1, target_area_m2=9.0, min_width_m=2.2),
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
        ],
        zones=[],
        relationships=[
            SeparationConstraint(room_type_a="safe_room", room_type_b="kitchen", severity=ConstraintSeverity.hard),
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    by_id = {r.id: r for r in result.instances}
    assert _shared_edge_length(by_id["SAFE_ROOM"], by_id["KITCHEN"]) == 0.0
    assert any(check.kind == "separation" and check.satisfied for check in result.hard_constraints_checked)


def test_hard_separation_with_min_distance_enforces_a_real_gap():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="safe_room", count=1, target_area_m2=9.0, min_width_m=2.2),
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
        ],
        zones=[],
        relationships=[
            SeparationConstraint(
                room_type_a="safe_room", room_type_b="kitchen", severity=ConstraintSeverity.hard, min_distance_m=1.5
            ),
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = BuildingFootprintSpec(width_m=20, depth_m=20, available_area_m2=400)

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    by_id = {r.id: r for r in result.instances}
    assert _rectangle_gap(by_id["SAFE_ROOM"], by_id["KITCHEN"]) >= 1.5 - 1e-6


def test_mock_gateway_includes_a_bedroom_kitchen_separation_and_it_is_reported():
    request = ArchitectModelRequest(
        brief="test",
        site=SiteSpec(width_m=100, depth_m=100),
        hard_constraints=[RequiredRoomConstraint(room_type="bedroom", count=1, severity=ConstraintSeverity.hard)],
    )
    spec = MockArchitectModelGateway().generate(request)
    assert any(
        isinstance(rel, SeparationConstraint) and rel.room_type_a == "bedroom" and rel.room_type_b == "kitchen"
        for rel in spec.relationships
    )

    footprint = BuildingFootprintSpec(width_m=14, depth_m=12, available_area_m2=14 * 12)
    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    reported_kinds = {c.kind for c in result.soft_constraints_satisfied + result.soft_constraints_not_satisfied}
    assert "separation" in reported_kinds


# --- Direct access proxy diagnostics -----------------------------------------------------------------


def test_direct_access_satisfied_result_carries_the_proxy_note():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, min_width_m=1.8),
        ],
        zones=[],
        relationships=[
            DirectAccessConstraint(
                room_type_a="bathroom", room_type_b="living_room", severity=ConstraintSeverity.hard
            )
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    direct_access_check = next(c for c in result.hard_constraints_checked if c.kind == "direct_access")
    assert direct_access_check.satisfied is True
    assert direct_access_check.note == _DIRECT_ACCESS_PROXY_NOTE


def test_adjacency_check_result_never_carries_the_direct_access_note():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0, min_width_m=3.0),
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
        ],
        zones=[],
        relationships=[
            AdjacencyConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard)
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    result = GeometrySolver().solve(spec, footprint)

    adjacency_check = next(c for c in result.hard_constraints_checked if c.kind == "adjacency")
    assert adjacency_check.note is None


# --- Entry edge semantics ------------------------------------------------------------------------


def test_allowed_entry_edges_unset_means_any_edge_counts():
    footprint = BuildingFootprintSpec(width_m=10, depth_m=10, available_area_m2=100)
    room = _room("LIVING_ROOM", "living_room", 0, 0, 4, 4)  # touches north + west only

    assert _touches_an_allowed_entry_edge(room, footprint) is True


def test_touching_a_non_allowed_edge_does_not_satisfy_entry_access():
    # The entry room (placed at the origin by the solver's ordering heuristic) touches north/west —
    # restricting allowed edges to south/east means it can NEVER satisfy entry access.
    footprint = BuildingFootprintSpec(
        width_m=10, depth_m=10, available_area_m2=100, allowed_entry_edges=[Edge.south, Edge.east]
    )
    room = _room("LIVING_ROOM", "living_room", 0, 0, 4, 4)

    assert _touches_an_allowed_entry_edge(room, footprint) is False


def test_touching_an_allowed_edge_satisfies_entry_access():
    footprint = BuildingFootprintSpec(
        width_m=10, depth_m=10, available_area_m2=100, allowed_entry_edges=[Edge.north]
    )
    room = _room("LIVING_ROOM", "living_room", 0, 0, 4, 4)

    assert _touches_an_allowed_entry_edge(room, footprint) is True


@pytest.mark.parametrize("edge", [Edge.north, Edge.south, Edge.east, Edge.west])
def test_solver_can_satisfy_any_single_allowed_entry_edge(edge: Edge):
    # Candidate placement generation must offer all four footprint corners for the entry room (not
    # just the north-west one) — otherwise restricting to south or east alone could never be
    # satisfied no matter the room sizes. Each of the four edges must work on its own.
    footprint = BuildingFootprintSpec(width_m=10, depth_m=10, available_area_m2=100, allowed_entry_edges=[edge])

    result = GeometrySolver().solve(_simple_spec(), footprint)

    assert result.status == SolverStatus.satisfied, f"edge={edge.value} should be solvable but was not"
    entry_room = next(r for r in result.instances if r.type == "living_room")
    assert _touches_edge(entry_room, footprint, edge)
    assert _touches_an_allowed_entry_edge(entry_room, footprint)


# --- Pre-solver contradiction validation -----------------------------------------------------------


def test_contradiction_hard_adjacency_and_hard_separation_same_pair():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0),
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0),
        ],
        zones=[],
        relationships=[
            AdjacencyConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard),
            SeparationConstraint(room_type_a="living_room", room_type_b="kitchen", severity=ConstraintSeverity.hard),
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    reason = _find_pre_solver_contradiction(spec, footprint)
    assert reason is not None and "kitchen" in reason and "living_room" in reason

    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.unsatisfiable
    assert result.unsatisfiable_reason == reason


def test_contradiction_hard_direct_access_and_hard_separation_same_pair():
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0),
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0),
        ],
        zones=[],
        relationships=[
            DirectAccessConstraint(
                room_type_a="bathroom", room_type_b="living_room", severity=ConstraintSeverity.hard
            ),
            SeparationConstraint(room_type_a="bathroom", room_type_b="living_room", severity=ConstraintSeverity.hard),
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    footprint = _generous_footprint()

    reason = _find_pre_solver_contradiction(spec, footprint)
    assert reason is not None and "bathroom" in reason and "living_room" in reason and "mutually exclusive" in reason

    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.unsatisfiable
    assert result.unsatisfiable_reason == reason


def test_contradiction_min_width_exceeds_both_footprint_dimensions():
    spec = ArchitecturalSpec(
        program=[ProgramItem(room_type="hall", count=1, target_area_m2=9.0, min_width_m=20.0)],
        zones=[],
        relationships=[],
        circulation=Circulation(entry_room_type="hall"),
    )
    tiny_footprint = BuildingFootprintSpec(width_m=5, depth_m=5, available_area_m2=25)

    reason = _find_pre_solver_contradiction(spec, tiny_footprint)

    assert reason is not None and "min_width_m" in reason

    result = GeometrySolver().solve(spec, tiny_footprint)
    assert result.status == SolverStatus.unsatisfiable
    assert result.unsatisfiable_reason == reason


def test_no_contradiction_found_for_a_perfectly_reasonable_spec():
    assert _find_pre_solver_contradiction(_simple_spec(), _generous_footprint()) is None


def test_pre_solver_contradiction_short_circuits_before_search_runs():
    # A spec that is BOTH pre-solver-contradictory AND would also fail the full search (tiny
    # footprint) — the important thing is that solve() returns unsatisfiable immediately via the
    # pre-check's specific reason, not a generic "search budget exhausted" message.
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0),
            ProgramItem(room_type="living_room", count=1, target_area_m2=16.0),
        ],
        zones=[],
        relationships=[
            AdjacencyConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard),
            SeparationConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard),
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    tiny_footprint = BuildingFootprintSpec(width_m=1, depth_m=1, available_area_m2=1)

    result = GeometrySolver().solve(spec, tiny_footprint)

    assert result.status == SolverStatus.unsatisfiable
    assert "mutually exclusive" in result.unsatisfiable_reason
