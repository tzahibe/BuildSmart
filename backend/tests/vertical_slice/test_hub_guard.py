"""008 guard: a demoted hub is replaced only by a plan that is actually better (`hub_guard`)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.demo import service as svc
from app.projects.models import Project, SelectedFootprint, SourceTag, StreetSide, TaggedBool, TaggedInt
from app.vertical_slice.hub_guard import AREA_KEEP_RATIO, PlanProportions, hub_keeps_primary

HUB = PlanProportions(area_m2=156.6, bedroom_max=1.64, master=1.48, safe_room=1.22, wet_adjacent=2, wet_total=2)


def test_a_replacement_better_on_one_proportion_and_of_the_same_size_wins():
    """The intended 008 effect: same area, the strip bedroom gone."""
    spine = PlanProportions(196.0, bedroom_max=1.23, master=1.83, safe_room=1.09, wet_adjacent=1, wet_total=2)
    hub = PlanProportions(196.0, bedroom_max=2.29, master=1.77, safe_room=1.66, wet_adjacent=2, wet_total=2)
    assert hub_keeps_primary(hub, spine) is None


def test_a_replacement_worse_on_every_proportion_never_takes_the_primary():
    """Measured: 11 x 12 m, 4BR/1wet — the band plan was worse on every bedroom and the master."""
    hub = PlanProportions(130.8, bedroom_max=1.77, master=1.64, safe_room=None, wet_adjacent=0, wet_total=1)
    band = PlanProportions(129.6, bedroom_max=2.27, master=1.98, safe_room=None, wet_adjacent=0, wet_total=1)
    reason = hub_keeps_primary(hub, band)
    assert reason is not None and "no proportion" in reason


def test_equal_proportions_do_not_count_as_better():
    same = PlanProportions(HUB.area_m2 - 1.0, HUB.bedroom_max + 0.01, HUB.master, HUB.safe_room, 2, 2)
    assert hub_keeps_primary(HUB, same) is not None


def test_a_much_smaller_house_is_not_an_improvement():
    """Measured: 10 x 20 m — 156.6 m² (78 % of the ask) replaced by 116.3 m² (58 %)."""
    spine = PlanProportions(116.3, bedroom_max=1.06, master=1.32, safe_room=1.06, wet_adjacent=1, wet_total=2)
    reason = hub_keeps_primary(HUB, spine)
    assert reason is not None and f"{AREA_KEEP_RATIO:.0%}" in reason


def test_the_area_rule_is_a_threshold_not_a_preference_for_size():
    at_threshold = PlanProportions(AREA_KEEP_RATIO * HUB.area_m2 + 0.1, 1.06, 1.32, 1.06, 2, 2)
    assert hub_keeps_primary(HUB, at_threshold) is None
    below = PlanProportions(AREA_KEEP_RATIO * HUB.area_m2 - 0.1, 1.06, 1.32, 1.06, 2, 2)
    assert hub_keeps_primary(HUB, below) is not None


def test_a_missing_metric_is_not_compared():
    no_safe = PlanProportions(HUB.area_m2, bedroom_max=1.10, master=1.20, safe_room=None, wet_adjacent=2, wet_total=2)
    assert hub_keeps_primary(HUB, no_safe) is None


# ------------------------------------------------------------------ through the real service

def _project(ctx: dict) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id="GUARD", city="TLV", street="S", plot_area_m2=ctx["plot_width_m"] * ctx["plot_depth_m"],
        plot_width_m=ctx["plot_width_m"], plot_depth_m=ctx["plot_depth_m"], street_facing_side=StreetSide("NORTH"),
        built_area_m2=ctx["built_area_m2"], description="", status="active", created_at=now, updated_at=now,
        selected_footprint=SelectedFootprint(source="CUSTOM", shape_type="RECTANGLE", target_area_m2=ctx["built_area_m2"],
                                             width_m=ctx["footprint_width_m"], depth_m=ctx["footprint_depth_m"],
                                             area_m2=round(ctx["footprint_width_m"] * ctx["footprint_depth_m"], 4)),
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=ctx["bedrooms"], source=SourceTag.requested),
        safe_room=TaggedBool(value=ctx["safe_room"], source=SourceTag.requested),
        parking_spaces=TaggedInt(value=0, source=SourceTag.requested),
        wet_rooms=TaggedInt(value=ctx["wet_rooms"], source=SourceTag.requested),
        open_plan=TaggedBool(value=ctx["open_plan"], source=SourceTag.requested),
        requirements_parsed_at=now,
    )


#: The measured cases from the 008 review on current main (specs/008, 2026-09-14).
WIDE_SQUARE = dict(bedrooms=3, wet_rooms=2, safe_room=True, open_plan=True, built_area_m2=199.94,
                   footprint_width_m=14.14, footprint_depth_m=14.14, plot_width_m=21.14, plot_depth_m=24.64)
NARROW_DEEP = dict(bedrooms=3, wet_rooms=3, safe_room=False, open_plan=False, built_area_m2=200.0,
                   footprint_width_m=10.0, footprint_depth_m=20.0, plot_width_m=17.0, plot_depth_m=30.5)
SMALL_4BR = dict(bedrooms=4, wet_rooms=1, safe_room=False, open_plan=False, built_area_m2=132.0,
                 footprint_width_m=11.0, footprint_depth_m=12.0, plot_width_m=18.0, plot_depth_m=22.5)
#: Main delivers a band plan here (bedrooms 2.93, master 2.52) and the hub, at the same area, loses
#: the tie on strategy name — so it was never the primary, and demotion displaced nothing.
NEVER_PRIMARY = dict(bedrooms=3, wet_rooms=3, safe_room=False, open_plan=True, built_area_m2=200.0,
                     footprint_width_m=10.0, footprint_depth_m=20.0, plot_width_m=17.0, plot_depth_m=30.5)


def _hall_is_a_lobby(design) -> bool:
    hall = next(r for r in design.rooms if r.type.upper() in ("HALL", "CIRCULATION") or "HALL" in r.id)
    return max(hall.width_m, hall.depth_m) / min(hall.width_m, hall.depth_m) <= 1.5


@pytest.mark.parametrize("ctx, hub_stays, why", [
    (WIDE_SQUARE, False, "same area, bedroom 2.29 -> 1.23: the replacement is better"),
    (NARROW_DEEP, True, "154 m² -> 109 m²: a quarter smaller is not better"),
    (SMALL_4BR, True, "band plan worse on every bedroom and the master"),
    (NEVER_PRIMARY, False, "the hub would have trailed the winner without demotion: not the guard's call"),
])
def test_demoted_hubs_are_replaced_only_by_better_plans(ctx, hub_stays, why):
    result = svc.generate_demo_design(_project(ctx))
    assert result.design.validation.passed
    assert _hall_is_a_lobby(result.design) is hub_stays, why
