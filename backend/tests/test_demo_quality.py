"""`DemoDesign.quality` — the room-size tiers the contract exposes (policy C, 2026-09-15).

Measured on the 431-context log with the two-level maxima: 440 rooms above their preferred
maximum in 395 plans, 306 of them under 1.10x (a 14.5 m2 bedroom), 86 at 1.10-1.20x, 48 above
1.20x — all bedrooms. Warning on every one would have marked 46 % of plans; the notice tier marks
8 %. So: every room's standing is data on its `RoomOut`, the middle tier is a signal, only the
top tier speaks — and never through `validation.warnings`, because it is not validation.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.demo import service as svc
from app.demo.contract import quality_of
from app.vertical_slice.concept_generator import (
    OVER_PREFERRED_NOTICE_RATIO,
    OVER_PREFERRED_SIGNAL_RATIO,
    ROOM_TEMPLATES,
)
from app.vertical_slice.geometry_core.model import ProgramRole
from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project
from tests.test_capacity_note import OVER_CAPACITY


def _room(zone_id: str, role: str, area: float):
    return SimpleNamespace(zone_id=zone_id, roles=(role,), net_area_m2=area)


def _design(*rooms, over_preferred=False):
    return SimpleNamespace(rooms=list(rooms), over_preferred=over_preferred)


BED = ROOM_TEMPLATES[ProgramRole.BEDROOM].max_area_m2       # 14
MASTER = ROOM_TEMPLATES[ProgramRole.MASTER_BEDROOM].max_area_m2   # 20


def test_thresholds_are_the_calibrated_ones():
    assert OVER_PREFERRED_SIGNAL_RATIO == 1.10 and OVER_PREFERRED_NOTICE_RATIO == 1.20


def test_a_room_just_above_preferred_is_metadata_only():
    q = quality_of(_design(_room("B1", "BEDROOM", BED * 1.05), _room("M", "MASTER_BEDROOM", MASTER * 1.09)))
    assert q.signal == [] and q.notices == []


def test_the_middle_tier_is_a_signal_and_not_a_notice():
    q = quality_of(_design(_room("B1", "BEDROOM", BED * 1.15)))
    assert [(s.room_id, s.ratio) for s in q.signal] == [("B1", 1.15)]
    assert q.notices == []


def test_the_top_tier_is_one_aggregated_notice_per_plan():
    q = quality_of(_design(_room("B1", "BEDROOM", 17.6), _room("B2", "BEDROOM", 17.2),
                           _room("B3", "BEDROOM", 14.8), _room("L", "LIVING", 47.0)))
    assert len(q.notices) == 1
    notice = q.notices[0]
    assert notice.startswith("2 חדרים גדולים מהמומלץ בצורה ניכרת")
    assert "חדר שינה 17.6, 17.2" in notice and "(מומלץ עד 14)" in notice
    assert "14.8" not in notice and "סלון" not in notice      # the 1.06x and 1.02x rooms stay quiet
    assert q.signal == []                                      # 14.8 is under the signal threshold too


def test_a_single_room_notice_reads_in_the_singular():
    q = quality_of(_design(_room("B1", "BEDROOM", 17.5)))
    assert q.notices[0].startswith("חדר אחד גדול מהמומלץ בצורה ניכרת: חדר שינה 17.5")


def test_circulation_and_flex_have_no_tier():
    q = quality_of(_design(_room("HALL", "HALL", 40.0), _room("FLEX", "FLEX", 90.0)))
    assert q.signal == [] and q.notices == []


def test_the_planners_flag_is_carried_but_is_not_a_notice():
    q = quality_of(_design(_room("B1", "BEDROOM", BED * 1.02), over_preferred=True))
    assert q.over_preferred and q.notices == [] and q.signal == []


# ------------------------------------------------------------------ Issue #17: metrics (M1–M6)
#
# `quality_of()` above runs on the raw solver output and never sees metrics (they need the
# flattened walls/open-interfaces/doors `to_demo_design` builds) — so these go through the real
# service entry point, like `test_capacity_note.py` and `test_hub_guard.py` already do.

_M_FIELDS = (
    "m1_habitable_aspect_median", "m1_habitable_aspect_max", "m2_habitable_on_envelope_ratio",
    "m3_circulation_share", "m4_hall_door_count", "m4_hall_aspect_median",
    "m5_wet_adjacency_ratio", "m6_public_zone_contiguous",
)


def test_a_planned_design_carries_all_six_metrics_and_no_dead_space():
    result = svc.generate_demo_design(_project(WIDE_SQUARE))
    metrics = result.design.quality.metrics
    assert metrics is not None
    for field in _M_FIELDS:
        assert hasattr(metrics, field)
    # WIDE_SQUARE has bedrooms, wet rooms, and an open-plan public zone: every metric that CAN be
    # non-None on some plan is non-None on this one.
    assert metrics.m1_habitable_aspect_median is not None
    assert metrics.m2_habitable_on_envelope_ratio is not None
    assert metrics.m5_wet_adjacency_ratio is not None
    assert metrics.m6_public_zone_contiguous is not None
    assert metrics.dead_space_m2 == 0.0                      # C2 already gates this to zero
    assert 0.0 <= metrics.wasted_circulation_share <= metrics.m3_circulation_share + 1e-9


def test_metrics_is_present_on_every_alternative_and_every_level_too():
    result = svc.generate_demo_design(_project(WIDE_SQUARE))
    assert result.design.quality.metrics is not None
    for alternative in result.alternatives:
        assert alternative.quality.metrics is not None
    if result.building is not None:
        for level in result.building.levels:
            assert level.design.quality.metrics is not None


def test_metrics_is_present_on_a_second_real_brief():
    """A different brief (over the programme's own capacity) — not just one fixture's shape."""
    result = svc.generate_demo_design(_project(OVER_CAPACITY))
    assert result.design.quality.metrics is not None
    assert result.design.quality.metrics.m3_circulation_share > 0.0


# ------------------------------------------------------------ Issue #34: dimension consistency
#
# Before this Issue, `RoomOut.width_m`/`depth_m` were the room's GROSS rectangle while `area_m2`
# was the NET area — so the displayed rectangle never multiplied out to the displayed area. C27
# (`app.vertical_slice.validation.check_realized_dimensions`) now gates every delivered `RoomOut`
# on this; `tests/vertical_slice/test_dimension_consistency.py` proves it fails closed on tampered
# metadata. This proves it holds — green — on real, unmodified plans.

def test_every_room_width_depth_matches_its_area():
    for fixture in (WIDE_SQUARE, OVER_CAPACITY):
        result = svc.generate_demo_design(_project(fixture))
        for design in (result.design, *result.alternatives):
            for room in design.rooms:
                assert abs(room.width_m * room.depth_m - room.area_m2) <= 0.05, \
                    (design.rooms, room.id, room.width_m, room.depth_m, room.area_m2)
                assert abs(room.gross_width_m * room.gross_depth_m - room.gross_area_m2) <= 0.05, \
                    (room.id, room.gross_width_m, room.gross_depth_m, room.gross_area_m2)
                # A wall inset only ever shrinks a room: the net rect never exceeds its own gross.
                assert room.width_m <= room.gross_width_m + 1e-6
                assert room.depth_m <= room.gross_depth_m + 1e-6


# ------------------------------------------------------------------ Issue #19: exposure report

def test_a_planned_design_carries_exposure_report_with_one_entry_per_room():
    result = svc.generate_demo_design(_project(WIDE_SQUARE))
    exposure = result.design.quality.exposure
    assert {e.room_id for e in exposure} == {r.id for r in result.design.rooms}
    for entry in exposure:
        # exactly one of "a window was placed" or "a reason is given" holds
        assert (entry.window_side is not None) != (entry.no_window_reason is not None)
        if entry.window_side is not None:
            assert entry.window_width_m and entry.window_width_m > 0
