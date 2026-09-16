"""V1/V3/V4/V5/V8 — proved on a REAL two-level `Building` the coordinator assembled, not on
synthetic rects. `test_building.py` covers V2/V7 on synthetic designs (Phase 0); this file is
the Phase 1 sequel, exercising the checks that need a realized core.
"""
from __future__ import annotations

import pytest

from app.vertical_slice.building_coordinator import plan_buildings
from app.vertical_slice.spec import PlotSpec, ProgramSpec


@pytest.fixture(scope="module")
def building():
    """One real, complete two-level building — expensive to plan, so built once per module."""
    program = ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=True, open_plan_living=True,
                          parking_spaces=2)
    result = plan_buildings(program, PlotSpec(20.0, 24.0), 170.0, stop_at_first=True)
    assert result.candidates, "fixture precondition: a Phase 1 building must be findable"
    return result.candidates[0]


def test_every_v_check_that_should_run_does_and_passes(building):
    ids = {c.check_id for c in building.building_validation.checks}
    assert ids == {"V1", "V2", "V3", "V4", "V5", "V7", "V8"}
    assert building.building_validation.ok, [c.detail for c in building.building_validation.failures()]


def test_v1_core_rectangle_is_literally_the_same_object_on_both_levels(building):
    core = building.building.cores[0]
    assert core.lower_level_id == "L0" and core.upper_level_id == "L1"
    v1 = next(c for c in building.building_validation.checks if c.check_id == "V1")
    assert v1.passed and v1.detail == "identical"


def test_v4_reaches_every_zone_on_both_levels_from_outside(building):
    v4 = next(c for c in building.building_validation.checks if c.check_id == "V4")
    assert v4.passed
    # the core's zone is ONE physical rectangle, so it is ONE node in V4's graph even though it
    # is also a zone in each level's OWN fixture — counted once here, not twice.
    total_zones = sum(len(lp.concept.concept.fixture.zones) for lp in building.building.levels) - 1
    assert f"all {total_zones} zones across both levels reachable" in v4.detail


def test_v8_every_requested_room_present_exactly_once(building):
    v8 = next(c for c in building.building_validation.checks if c.check_id == "V8")
    assert v8.passed


def test_single_level_building_still_gets_only_v2_and_v7():
    # the compatibility invariant every Phase 0 test already pins, restated here so a Phase 1
    # regression cannot silently widen what a one-storey `Building` reports.
    from app.vertical_slice.building import Building
    from app.vertical_slice.building_validation import validate_building
    from app.vertical_slice.pipeline import run_demo
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        result = run_demo(os.path.join(d, "house.png"))
    b = Building.single_level(result.design, result.validation)
    report = validate_building(b)
    assert {c.check_id for c in report.checks} == {"V2", "V7"}
