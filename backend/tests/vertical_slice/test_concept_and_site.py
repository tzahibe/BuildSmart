from __future__ import annotations

import pytest

from app.vertical_slice import site as site_stage
from app.vertical_slice.concept import build_concept
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec, demo_spec


def test_concept_solves_without_infeasibility():
    concept = build_concept(demo_spec())
    res = solve_fixture(concept.fixture)
    assert set(res.rects) == {z.zone_id for z in concept.fixture.zones}


def test_concept_gross_area_within_target_band():
    concept = build_concept(demo_spec())
    gross = concept.fixture.footprint_area_m2()
    assert 150.0 <= gross <= 180.0


def test_concept_rejects_an_unsupported_program():
    spec = ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=ProgramSpec(bedrooms=4))
    with pytest.raises(NotImplementedError):
        build_concept(spec)


def test_hall_main_touches_only_master_not_bedroom_1():
    """Regression for a real authoring bug found while building this slice: hall_col's split
    must exactly match rooms_col's split, or HALL_MAIN gets an undeclared sliver of contact
    with BEDROOM_1 instead of a clean 1:1 border with MASTER."""
    concept = build_concept(demo_spec())
    res = solve_fixture(concept.fixture)
    assert res.rects["HALL_MAIN"].shared_edge_len_u(res.rects["BEDROOM_1"]) == 0
    assert res.rects["HALL_MAIN"].shared_edge_len_u(res.rects["MASTER"]) > 0


def test_hall_spur_touches_all_four_back_rooms():
    concept = build_concept(demo_spec())
    res = solve_fixture(concept.fixture)
    for zid in ("BEDROOM_1", "SAFE_ROOM", "BEDROOM_2", "BATH_2"):
        assert res.rects["HALL_SPUR"].shared_edge_len_u(res.rects[zid]) > 0, zid


def test_site_places_footprint_inside_the_buildable_envelope():
    spec = demo_spec()
    concept = build_concept(spec)
    res = solve_fixture(concept.fixture)
    entrance_x = res.rects[concept.entrance_zone_id].x + res.rects[concept.entrance_zone_id].w // 2
    plan = site_stage.build_site_plan(spec, concept.footprint_width_m, concept.footprint_depth_m, entrance_x)
    assert plan.plot.x <= plan.footprint.x and plan.footprint.x2 <= plan.plot.x2
    assert plan.plot.y <= plan.footprint.y and plan.footprint.y2 <= plan.plot.y2


def test_site_rejects_a_footprint_too_big_for_a_small_plot():
    tiny_plot = PlotSpec(width_m=10.0, depth_m=10.0)
    spec = ArchitecturalSpec(plot=tiny_plot, program=ProgramSpec())
    with pytest.raises(ValueError, match="does not fit"):
        site_stage.place_footprint(spec, 12.0, 14.2)


def test_parking_bays_do_not_overlap_each_other_or_the_footprint():
    spec = demo_spec()
    concept = build_concept(spec)
    res = solve_fixture(concept.fixture)
    entrance_x = res.rects[concept.entrance_zone_id].x + res.rects[concept.entrance_zone_id].w // 2
    plan = site_stage.build_site_plan(spec, concept.footprint_width_m, concept.footprint_depth_m, entrance_x)
    bays = plan.parking
    for i in range(len(bays)):
        for j in range(i + 1, len(bays)):
            assert bays[i].overlap_area_u(bays[j]) == 0
        assert bays[i].overlap_area_u(plan.footprint) == 0
