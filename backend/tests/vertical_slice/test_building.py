"""`Building` — a list of levels, each today's pipeline output; and the between-level checks.

The invariant everything here protects: a one-storey house is a `Building` with one level, and
that level's design IS the design the demo produces today — same object, same numbers. The
frozen canonical slice is the witness. Two-level buildings are exercised on SYNTHETIC designs
because nothing can plan one yet (that is Phase 1); the checks must be right before the first
real one arrives, not after.
"""
from __future__ import annotations

import pytest

from app.vertical_slice.building import (
    FLOOR_TO_FLOOR_M,
    Building,
    Level,
    LevelEntry,
    LevelEntryKind,
    LevelKind,
    LevelPlan,
    Massing,
)
from app.vertical_slice.building_validation import validate_building
from app.vertical_slice.design_output import DoorOut, GeometricDesign
from app.vertical_slice.geometry_core.model import Rect, Side, m_to_u
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.validation import ValidationReport
from app.vertical_slice.vertical import StairArchetype, VerticalCore, VerticalCoreKind


@pytest.fixture(scope="module")
def slice_result(tmp_path_factory):
    return run_demo(str(tmp_path_factory.mktemp("building") / "house.png"))


# ------------------------------------------------------------------ the single-storey witness

def test_the_frozen_slice_is_a_one_level_building_carrying_its_own_design(slice_result):
    building = Building.single_level(slice_result.design, slice_result.validation)
    assert building.story_count == 1
    assert building.cores == ()
    assert building.levels[0].design is slice_result.design, "the design is carried, not copied"
    assert building.ground.level == Level("L0", 0, LevelKind.GROUND)
    assert building.ground.level.floor_to_floor_m == FLOOR_TO_FLOOR_M
    assert building.ground.entry == LevelEntry(LevelEntryKind.STREET_DOOR, zone_id="HALL_MAIN")
    assert building.ok


def test_totals_on_one_level_are_that_levels_own_gross_and_net(slice_result):
    """The frozen baseline's numbers, read back through the building — nothing summed twice."""
    building = Building.single_level(slice_result.design, slice_result.validation)
    assert building.total_gross_m2 == pytest.approx(170.4)
    assert building.total_net_m2 == pytest.approx(153.83)
    assert building.total_gross_m2 == slice_result.design.gross_area_m2
    assert building.total_net_m2 == slice_result.design.net_area_m2


def test_massing_of_one_level_is_the_plot_and_the_footprint(slice_result):
    building = Building.single_level(slice_result.design, slice_result.validation)
    massing = building.massing
    assert massing.plot_m == slice_result.design.plot_m
    # One region per wing — one wing — and the bounding-box view is that same rectangle.
    assert massing.level_regions_m == ((slice_result.design.footprint_m,),)
    assert massing.level_outlines_m == (slice_result.design.footprint_m,)
    assert slice_result.design.footprints_m == (slice_result.design.footprint_m,)
    assert massing.ground_coverage == pytest.approx(170.4 / (20.0 * 24.0), abs=1e-3)
    assert massing.retreat_m2 == 0.0


def test_the_building_checks_pass_on_the_frozen_slice_and_only_ran_checks_appear(slice_result):
    building = Building.single_level(slice_result.design, slice_result.validation)
    report = validate_building(building)
    assert report.ok
    # Phase 0 runs the two checks computable without a realized core. V1/V3–V6 are NOT listed as
    # passed: a check that did not run makes no claim.
    assert [c.check_id for c in report.checks] == ["V2", "V7"]
    assert "single level" in next(c for c in report.checks if c.check_id == "V2").detail


# ------------------------------------------------------------------ synthetic two-level buildings

def _design(plot, footprint, *, gross=None, net=None, entrance_zone="HALL",
            wings=None) -> GeometricDesign:
    """A `GeometricDesign` with only what the building layer reads: plot, footprint (bounding
    box), its wings, areas, entry. `wings` defaults to the one rectangle `footprint` names."""
    x, y, w, h = footprint
    wings = tuple(wings) if wings else (footprint,)
    area = round(sum(r[2] * r[3] for r in wings), 2)
    door = DoorOut("OUTSIDE", entrance_zone, "DOOR", 1.0, (x + w / 2, y), "horizontal", True, w)
    return GeometricDesign(
        plot_m=plot, footprint_m=footprint, rooms=(), interior_doors=(), entrance_door=door,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(x + w / 2 - 0.6, 0.0, 1.2, y),
        gross_area_m2=area if gross is None else gross,
        net_area_m2=round(area * 0.9, 2) if net is None else net,
        wall_iterations=1, footprints_m=wings,
    )


def _core(rect_m=(6.6, 5.7, 1.9, 4.8)) -> VerticalCore:
    x, y, w, h = rect_m
    return VerticalCore("STAIR_1", "L0", "L1", Rect(m_to_u(x), m_to_u(y), m_to_u(w), m_to_u(h)),
                        entry_edge=Side.N, arrival_edge=Side.N, direction=Side.S)


def _two_levels(ground_fp, upper_fp, *, plot=(0.0, 0.0, 20.0, 24.0), upper_gross=None,
                ground_wings=None, upper_wings=None):
    """Two levels; each footprint is a bounding box, optionally made of several wings."""
    core = _core()
    ground_wings = tuple(ground_wings) if ground_wings else (ground_fp,)
    upper_wings = tuple(upper_wings) if upper_wings else (upper_fp,)
    ground = LevelPlan(Level("L0", 0, LevelKind.GROUND),
                       LevelEntry(LevelEntryKind.STREET_DOOR, "HALL"),
                       _design(plot, ground_fp, wings=ground_wings), ValidationReport())
    upper = LevelPlan(Level("L1", 1, LevelKind.UPPER, elevation_m=FLOOR_TO_FLOOR_M),
                      LevelEntry(LevelEntryKind.STAIR_ARRIVAL, "STAIR_1", core_id="STAIR_1"),
                      _design(plot, upper_fp, gross=upper_gross, wings=upper_wings),
                      ValidationReport())
    return Building(levels=(ground, upper), massing=Massing(plot, (ground_wings, upper_wings)),
                    cores=(core,))


def test_a_two_level_building_sums_its_levels_and_reports_the_retreat():
    building = _two_levels((4.0, 5.5, 12.0, 10.5), (4.0, 5.5, 11.0, 10.5))
    assert building.story_count == 2
    assert building.total_gross_m2 == pytest.approx(126.0 + 115.5)
    assert building.massing.retreat_m2 == pytest.approx(10.5)   # the 1 m east strip
    assert building.massing.ground_coverage == pytest.approx(126.0 / 480.0, abs=1e-4)
    assert building.level("L1").entry.core_id == "STAIR_1"


def test_v2_holds_when_the_upper_outline_is_inside_the_ground_outline():
    report = validate_building(_two_levels((4.0, 5.5, 12.0, 10.5), (4.0, 5.5, 11.0, 10.5)))
    assert report.ok, [c.detail for c in report.failures()]
    assert next(c for c in report.checks if c.check_id == "V2").detail == "1 upper level(s) contained"


def test_v2_fails_on_a_cantilever():
    """An upper outline that leaves the outline below is deferred, not drawn."""
    report = validate_building(_two_levels((4.0, 5.5, 12.0, 10.5), (3.0, 5.5, 12.0, 10.5)))
    failed = report.failures()
    assert [c.check_id for c in failed] == ["V2"]
    assert "L1 region" in failed[0].detail and "leaves L0" in failed[0].detail


def test_v2_judges_an_upper_region_against_the_union_of_the_wings_below():
    """An L ground floor (bar + arm) with an upper level over the bar only: contained. The same
    upper level pushed over the crook — inside the bounding box, outside every wing — is not."""
    bar, arm = (4.0, 5.5, 8.0, 12.0), (12.0, 5.5, 4.5, 8.5)          # the F2 L, in metres
    ground_bbox = (4.0, 5.5, 12.5, 12.0)
    over_bar = _two_levels(ground_bbox, bar, ground_wings=(bar, arm), upper_wings=(bar,))
    assert validate_building(over_bar).ok, [c.detail for c in validate_building(over_bar).failures()]
    assert over_bar.massing.retreat_m2 == pytest.approx(4.5 * 8.5)   # the arm's roof
    assert over_bar.massing.level_outlines_m[0] == ground_bbox

    into_crook = (12.0, 14.0, 4.5, 3.5)                              # the crook: bbox minus wings
    over_crook = _two_levels(ground_bbox, into_crook, ground_wings=(bar, arm),
                             upper_wings=(into_crook,))
    failed = validate_building(over_crook).failures()
    assert [c.check_id for c in failed] == ["V2"]
    assert "2 region(s)" in failed[0].detail


def test_v7_fails_when_a_levels_gross_is_not_its_own_outline():
    """The accounting defect this exists to catch: an upper level reporting the ground's area."""
    report = validate_building(_two_levels((4.0, 5.5, 12.0, 10.5), (4.0, 5.5, 11.0, 10.5),
                                           upper_gross=126.0))
    failed = report.failures()
    assert [c.check_id for c in failed] == ["V7"]
    assert "L1 gross 126.0 m2 is not its outline's 115.5 m2" in failed[0].detail


def test_v7_measures_a_levels_gross_against_its_wings_not_its_bounding_box():
    bar, arm = (4.0, 5.5, 8.0, 12.0), (12.0, 5.5, 4.5, 8.5)
    building = _two_levels((4.0, 5.5, 12.5, 12.0), bar, ground_wings=(bar, arm), upper_wings=(bar,))
    assert building.ground.design.gross_area_m2 == pytest.approx(96.0 + 38.25)   # wings, not 150
    assert validate_building(building).ok
    assert building.massing.ground_coverage == pytest.approx(134.25 / 480.0, abs=1e-4)


def test_v7_fails_when_the_ground_outline_leaves_the_plot():
    report = validate_building(_two_levels((15.0, 5.5, 12.0, 10.5), (15.0, 5.5, 11.0, 10.5)))
    assert [c.check_id for c in report.failures()] == ["V7"]
    assert "leaves the plot" in report.failures()[0].detail


# ------------------------------------------------------------------ construction invariants

def test_levels_are_ordered_unique_and_entered_the_right_way():
    plot = (0.0, 0.0, 20.0, 24.0)
    fp = (4.0, 5.5, 12.0, 10.5)
    ground = LevelPlan(Level("L0", 0, LevelKind.GROUND), LevelEntry(LevelEntryKind.STREET_DOOR, "HALL"),
                       _design(plot, fp), ValidationReport())
    with pytest.raises(ValueError, match="at least one level"):
        Building(levels=(), massing=Massing(plot, ((fp,),)))
    with pytest.raises(ValueError, match="one region list per level"):
        Building(levels=(ground,), massing=Massing(plot, ((fp,), (fp,))))
    with pytest.raises(ValueError, match="no regions"):
        Massing(plot, ((fp,), ()))
    # A second level with no stair to reach it is not a building anyone can use.
    upper = LevelPlan(Level("L1", 1, LevelKind.UPPER),
                      LevelEntry(LevelEntryKind.STAIR_ARRIVAL, "STAIR_1", core_id="STAIR_1"),
                      _design(plot, fp), ValidationReport())
    with pytest.raises(ValueError, match="does not reach it"):
        Building(levels=(ground, upper), massing=Massing(plot, ((fp,), (fp,))))
    # Level 0 is the ground; an upper level is not entered from the street.
    with pytest.raises(ValueError, match="GROUND level"):
        Level("L1", 1, LevelKind.GROUND)
    with pytest.raises(ValueError, match="STAIR_ARRIVAL"):
        Building(levels=(ground, LevelPlan(Level("L1", 1, LevelKind.UPPER),
                                           LevelEntry(LevelEntryKind.STREET_DOOR, "HALL"),
                                           _design(plot, fp), ValidationReport())),
                 massing=Massing(plot, ((fp,), (fp,))), cores=(_core(),))


def test_a_level_entry_names_its_core_exactly_when_it_arrives_by_stair():
    with pytest.raises(ValueError, match="must name the core"):
        LevelEntry(LevelEntryKind.STAIR_ARRIVAL, "STAIR_1")
    with pytest.raises(ValueError, match="has no core"):
        LevelEntry(LevelEntryKind.STREET_DOOR, "HALL", core_id="STAIR_1")


def test_a_vertical_core_connects_two_levels_with_a_real_footprint():
    core = _core()
    assert core.kind is VerticalCoreKind.STAIR
    assert core.archetype is StairArchetype.STRAIGHT
    assert core.zone_id == "STAIR_1", "the stair zone defaults to the core id"
    assert core.level_ids == ("L0", "L1") and core.touches("L1") and not core.touches("L2")
    with pytest.raises(ValueError, match="DIFFERENT levels"):
        VerticalCore("S", "L0", "L0", Rect(0, 0, 10, 10), Side.N, Side.N, Side.S)
    with pytest.raises(ValueError, match="real footprint"):
        VerticalCore("S", "L0", "L1", Rect(0, 0, 0, 10), Side.N, Side.N, Side.S)
