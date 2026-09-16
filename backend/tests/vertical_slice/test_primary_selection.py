"""`primary_selection.select_primary` — the lexicographic candidate ranking, and the concept/
warning provenance `building_coordinator.py` now carries for it.
"""
from __future__ import annotations

import pytest

from app.vertical_slice.building_coordinator import plan_buildings
from app.vertical_slice.primary_selection import (
    OPEN_PLAN_ASPECT_ABSOLUTE_THRESHOLD,
    OPEN_PLAN_ASPECT_RELATIVE_THRESHOLD,
    preference_violations,
    quality_metrics_of,
    quality_warning_count,
    select_primary,
)
from app.vertical_slice.spec import HouseConcept, PlotSpec, ProgramSpec, PublicPrivateStrategy


def _program(**kw) -> ProgramSpec:
    base = dict(bedrooms=3, wet_rooms=2, safe_room=True, open_plan_living=True, parking_spaces=2)
    base.update(kw)
    return ProgramSpec(**base)


# ------------------------------------------------------------------ BuildingCandidate provenance

def test_building_candidate_carries_real_warnings_not_reconstructed():
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    assert res.candidates
    closed = [c for c in res.candidates if c.ground_layout == "closed_kitchen"]
    assert closed
    assert any("kitchen is closed" in w for w in closed[0].ground_warnings)
    assert closed[0].warnings == closed[0].ground_warnings + closed[0].upper_warnings


def test_single_level_behaviour_unchanged_when_no_concept_given():
    program = _program()
    with_default = plan_buildings(program, PlotSpec(20.0, 24.0), 170.0, stop_at_first=False)
    explicit_none = plan_buildings(program, PlotSpec(20.0, 24.0), 170.0, concept=None, stop_at_first=False)
    assert len(with_default.candidates) == len(explicit_none.candidates)
    fam_a = {c.family for c in with_default.candidates}
    fam_b = {c.family for c in explicit_none.candidates}
    assert fam_a == fam_b


# ------------------------------------------------------------------ HouseConcept threading

def test_hard_bound_strategy_excludes_the_other_allocation_entirely():
    program = _program(bedrooms=4, wet_rooms=1)
    concept = HouseConcept(stories=2, public_private_strategy=PublicPrivateStrategy.PUBLIC_PLUS_ONE_BEDROOM_BELOW,
                           hard_fields=frozenset({"public_private_strategy"}))
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, concept=concept, stop_at_first=False)
    assert res.candidates
    assert {c.strategy for c in res.candidates} == {"public_plus_one_bedroom_below"}
    assert any(r.reason == "HARD_PREFERENCE_EXCLUDED" for r in res.refusals)


def test_preference_strength_strategy_still_generates_both():
    program = _program(bedrooms=4, wet_rooms=1)
    concept = HouseConcept(stories=2, public_private_strategy=PublicPrivateStrategy.PUBLIC_PLUS_ONE_BEDROOM_BELOW)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, concept=concept, stop_at_first=False)
    strategies = {c.strategy for c in res.candidates}
    assert "public_below_private_above" in strategies
    assert "public_plus_one_bedroom_below" in strategies


# ------------------------------------------------------------------ select_primary — mechanics

def test_no_candidates_yields_no_primary():
    result = select_primary((), _program(), 170.0)
    assert not result.any
    assert result.primary is None and result.notice is None


def test_only_valid_candidates_participate_by_construction():
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    result = select_primary(res.candidates, program, 190.0)
    assert result.primary.building_validation.ok
    assert result.primary.building.ok
    for rc in result.ranked:
        assert rc.candidate.building_validation.ok


def test_preference_open_plan_kept_authoritative_over_quality():
    """The known 4BR/1wet case: the open ground has a much worse bedroom (2.13) than the
    closed-kitchen alternative (1.70), and still wins because it honours open_plan_living."""
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    result = select_primary(res.candidates, program, 190.0)
    assert result.primary.ground_layout == "open"
    assert preference_violations(result.primary, program, None) == 0


def test_no_bonus_for_generation_order_strategy_or_lobby_form():
    """Reversing the candidate order must not change the winner — order is the LAST tiebreak."""
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    forward = select_primary(res.candidates, program, 190.0)
    backward = select_primary(tuple(reversed(res.candidates)), program, 190.0)
    assert forward.primary.family == backward.primary.family
    assert forward.primary_metrics == backward.primary_metrics


def test_when_every_candidate_agrees_no_trade_off_notice():
    program = _program()  # 3BR/2wet: only allocation A ever plans (investigation report §6)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 170.0, stop_at_first=False)
    result = select_primary(res.candidates, program, 170.0)
    assert result.notice is None  # nothing to trade: no open ground exists to compare against


# ------------------------------------------------------------------ trade-off notice

def test_trade_off_notice_fires_with_structured_metadata():
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    result = select_primary(res.candidates, program, 190.0)
    assert result.notice is not None
    assert result.notice.kind == "OPEN_PLAN_BEDROOM_TRADEOFF"
    assert "חלל ציבורי פתוח" in result.notice.message_he
    assert result.notice.selected_worst_bed_aspect > result.notice.alternative_worst_bed_aspect
    # the thresholds actually justify the notice on this known case (2.13, +0.43 over 1.70)
    assert (result.notice.selected_worst_bed_aspect > OPEN_PLAN_ASPECT_ABSOLUTE_THRESHOLD or
           result.notice.selected_worst_bed_aspect - result.notice.alternative_worst_bed_aspect
           >= OPEN_PLAN_ASPECT_RELATIVE_THRESHOLD)


def test_trade_off_notice_never_overrides_the_preference():
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    result = select_primary(res.candidates, program, 190.0)
    # the notice exists, but the OPEN candidate (the preference-honouring one) is still primary
    assert result.notice is not None
    assert result.primary.ground_layout == "open"


def test_quality_warning_count_deduplicates_the_shared_warning_list():
    """`level_program._split` hands the SAME warnings list to both levels — a candidate with one
    real gap must not be double-penalised because both `LevelProgram`s repeat it."""
    program = _program(bedrooms=4, wet_rooms=1)
    res = plan_buildings(program, PlotSpec(20.0, 24.0), 190.0, stop_at_first=False)
    for c in res.candidates:
        raw_unique_facts = len(set(c.ground_warnings) | set(c.upper_warnings))
        assert quality_warning_count(c, program) <= raw_unique_facts
