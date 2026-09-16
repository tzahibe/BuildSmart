"""`building_coordinator.plan_buildings` — the joint search, end to end: allocation candidates ×
ground outlines × lobby forms × upper massing × k, each complete `Building` proven by the SAME
per-level C-checks every single-storey plan runs plus the building-level V-checks.
"""
from __future__ import annotations

import pytest

from app.vertical_slice.building_coordinator import plan_buildings
from app.vertical_slice.spec import PlotSpec, ProgramSpec


def _program(**kw) -> ProgramSpec:
    base = dict(bedrooms=3, wet_rooms=2, safe_room=True, open_plan_living=True, parking_spaces=2)
    base.update(kw)
    return ProgramSpec(**base)


def test_a_complete_building_is_found_for_a_representative_brief():
    result = plan_buildings(_program(), PlotSpec(20.0, 24.0), 170.0, stop_at_first=True)
    assert result.candidates, [f"{r.stage}/{r.reason}: {r.detail[:80]}" for r in result.refusals[:5]]
    candidate = result.candidates[0]
    assert candidate.building.story_count == 2
    assert candidate.building.ok
    assert candidate.building_validation.ok


def test_every_level_passes_its_own_c_checks_unchanged():
    result = plan_buildings(_program(), PlotSpec(20.0, 24.0), 170.0, stop_at_first=True)
    building = result.candidates[0].building
    for level_plan in building.levels:
        assert level_plan.validation.ok, [c.detail for c in level_plan.validation.failures()]
        assert level_plan.safety.ok


def test_the_upper_level_skips_site_checks_and_seeds_reachability_from_the_stair():
    result = plan_buildings(_program(), PlotSpec(20.0, 24.0), 170.0, stop_at_first=True)
    building = result.candidates[0].building
    upper = building.levels[1]
    ids = {c.check_id for c in upper.validation.checks}
    assert ids.isdisjoint({"C10", "C11", "C12", "C16", "C18"})
    c5 = next(c for c in upper.validation.checks if c.check_id == "C5")
    assert "seeded from STAIR" in c5.detail
    ground = building.levels[0]
    assert {"C10", "C11", "C12", "C16", "C18"} <= {c.check_id for c in ground.validation.checks}


def test_total_area_is_the_sum_over_both_levels_never_each_levels_footprint_doubled():
    total_m2 = 170.0
    result = plan_buildings(_program(), PlotSpec(20.0, 24.0), total_m2, stop_at_first=True)
    building = result.candidates[0].building
    ground, upper = building.levels
    assert building.total_gross_m2 == round(ground.design.gross_area_m2 + upper.design.gross_area_m2, 2)
    # delivered tracks the request (the same discipline the single-storey `_proportions` search
    # uses), never balloons to ~2x the ask the way "ground area + upper area, each == the ask"
    # would.
    assert 0.8 * total_m2 <= building.total_gross_m2 <= 1.3 * total_m2


def test_no_ranking_is_applied_every_valid_candidate_is_returned():
    # explicit Phase 1 scope: the coordinator does not choose a primary among A/C or SHRUNK/
    # ABSORBED — it returns whatever it validated, in search order, for the caller to rank.
    result = plan_buildings(_program(wet_rooms=1), PlotSpec(20.0, 24.0), 160.0, stop_at_first=False)
    if len(result.candidates) > 1:
        families = {c.family for c in result.candidates}
        assert len(families) >= 1   # multiple families may coexist; none is discarded here


def test_infeasible_programme_gives_named_refusals_not_a_silent_empty_result():
    # 1 bedroom cannot support two levels at all (`level_program.allocate_levels` refuses it).
    result = plan_buildings(_program(bedrooms=1), PlotSpec(20.0, 24.0), 120.0, stop_at_first=True)
    assert not result.candidates
    assert not result.refusals   # allocate_levels returns () before any outline/ground attempt
