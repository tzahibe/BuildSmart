"""Tests for the new geometric layout-quality metrics (app/geometry/quality.py) and their integration
into GeometrySolverResult (candidate ranking, explainable score breakdown) — this milestone's Step 2/3.
Hard-constraint correctness itself is unaffected and still covered exhaustively by
tests/test_geometry_solver.py; these tests are specifically about the NEW quality/ranking behavior.
"""

from app.architect.models import ArchitectModelRequest, ArchitecturalSpec, SiteSpec
from app.geometry.models import BuildingFootprintSpec, RoomInstance, SolverStatus
from app.geometry.quality import compute_quality_metrics
from app.geometry.solver import GeometrySolver, _shared_edge_length


def _room(type_, x, y, w, h) -> RoomInstance:
    return RoomInstance(id=type_, type=type_, floor=1, x=x, y=y, width=w, height=h, area_m2=round(w * h, 3))


def _empty_spec() -> ArchitecturalSpec:
    return ArchitecturalSpec(program=[], zones=[], relationships=[], circulation=None)


# --- Geometric unused-region metrics: exact tiling, one big gap, fragmented gaps ---------------------


def test_exact_tiling_has_zero_unused_area_and_full_utilization():
    footprint = BuildingFootprintSpec(width_m=4, depth_m=2, available_area_m2=8)
    placed = [_room("a", 0, 0, 2, 2), _room("b", 2, 0, 2, 2)]

    metrics = compute_quality_metrics(_empty_spec(), footprint, placed, {"a": placed[:1], "b": placed[1:]}, _shared_edge_length)

    assert metrics.programmed_area_m2 == 8.0
    assert metrics.footprint_area_m2 == 8.0
    assert metrics.utilization_ratio == 1.0
    assert metrics.unused_area_m2 == 0.0
    assert metrics.largest_contiguous_unused_region_m2 == 0.0
    assert metrics.compactness == 1.0


def test_one_contiguous_gap_has_fragmentation_ratio_near_one():
    # 4x4 footprint, one 2x2 room in a corner — the remaining 12 m2 is a single L-shaped, but fully
    # connected, contiguous region.
    footprint = BuildingFootprintSpec(width_m=4, depth_m=4, available_area_m2=16)
    placed = [_room("a", 0, 0, 2, 2)]

    metrics = compute_quality_metrics(_empty_spec(), footprint, placed, {"a": placed}, _shared_edge_length)

    assert metrics.unused_area_m2 == 12.0
    assert metrics.largest_contiguous_unused_region_m2 == 12.0
    assert metrics.unused_region_fragmentation_ratio == 1.0


def test_two_disconnected_gaps_have_a_lower_fragmentation_ratio_than_one_contiguous_gap():
    # 6x2 footprint, one room in the middle splitting the remaining space into two disconnected 2x2
    # pockets on either side — same total unused area as a single 8 m2 region would be, but fragmented.
    footprint = BuildingFootprintSpec(width_m=6, depth_m=2, available_area_m2=12)
    placed = [_room("a", 2, 0, 2, 2)]

    metrics = compute_quality_metrics(_empty_spec(), footprint, placed, {"a": placed}, _shared_edge_length)

    assert metrics.unused_area_m2 == 8.0
    assert metrics.largest_contiguous_unused_region_m2 == 4.0  # each pocket alone, not both combined
    assert metrics.unused_region_fragmentation_ratio == 0.5


# --- Compactness: tight cluster vs. spread out ------------------------------------------------------


def test_compactness_is_lower_when_rooms_are_spread_apart_than_when_clustered():
    footprint = BuildingFootprintSpec(width_m=10, depth_m=10, available_area_m2=100)
    clustered = [_room("a", 0, 0, 2, 2), _room("b", 2, 0, 2, 2)]
    spread = [_room("a", 0, 0, 2, 2), _room("b", 8, 8, 2, 2)]

    clustered_metrics = compute_quality_metrics(_empty_spec(), footprint, clustered, {}, _shared_edge_length)
    spread_metrics = compute_quality_metrics(_empty_spec(), footprint, spread, {}, _shared_edge_length)

    assert clustered_metrics.compactness == 1.0  # rooms exactly tile their own 4x2 bounding box
    assert spread_metrics.compactness < clustered_metrics.compactness
    # Both placements use identical total room area — utilization_ratio must be identical; only
    # compactness (a different, independent metric) should differ.
    assert clustered_metrics.utilization_ratio == spread_metrics.utilization_ratio


# --- Solver integration: quality/objective_breakdown/candidate_summaries are populated ---------------


def _mock_program_spec():
    from app.architect.gateway import MockArchitectModelGateway

    request = ArchitectModelRequest(brief="test", site=SiteSpec(width_m=12, depth_m=10))
    return MockArchitectModelGateway().generate(request)


def test_satisfied_result_carries_quality_and_explainable_breakdown():
    spec = _mock_program_spec()
    footprint = BuildingFootprintSpec(width_m=14, depth_m=12, available_area_m2=14 * 12)

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.satisfied
    assert result.quality is not None
    assert 0.0 <= result.quality.utilization_ratio <= 1.0
    assert 0.0 <= result.quality.compactness <= 1.0
    assert result.objective_breakdown is not None
    assert result.objective_score == result.objective_breakdown.total
    assert result.candidate_count >= 1
    assert len(result.candidate_summaries) >= 1
    assert len(result.candidate_summaries) <= 5


def test_candidate_summaries_are_sorted_best_first():
    spec = _mock_program_spec()
    footprint = BuildingFootprintSpec(width_m=14, depth_m=12, available_area_m2=14 * 12)

    result = GeometrySolver().solve(spec, footprint)

    totals = [c.total for c in result.candidate_summaries]
    assert totals == sorted(totals, reverse=True)
    assert result.objective_breakdown.total == totals[0]


def test_unsatisfiable_result_has_no_quality_report():
    spec = _mock_program_spec()
    # Absurdly tiny footprint — guaranteed unsatisfiable regardless of ranking changes.
    footprint = BuildingFootprintSpec(width_m=1, depth_m=1, available_area_m2=1)

    result = GeometrySolver().solve(spec, footprint)

    assert result.status == SolverStatus.unsatisfiable
    assert result.quality is None
    assert result.objective_breakdown is None
    assert result.candidate_count == 0
