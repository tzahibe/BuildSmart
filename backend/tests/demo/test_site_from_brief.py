"""Issue #223 — the drawing shows the PERSON'S OWN PARCEL, or says there isn't one.

What this pins, and why each level is the level it is:

* The **payload** facts (AC-1/AC-2/AC-3) are read off `demo.contract.to_demo_design` — the one
  function that turns a realized plan into what the renderer draws. Nothing here re-derives a
  plot, a garden or a bay; every number is compared against the brief's own `ArchitecturalSpec`.
* **Production** is checked end to end through `demo.service.generate_demo_design`, because the
  measurement limit #213 declared (every corpus brief had `parking_spaces = 0`) can only be closed
  by a brief that actually asks for parking. It is also the control: production already carried
  the parcel, and this Issue must not move it.
* **The brain** is checked through `brain.runner.run_brain` with production's own sizer rather than
  through `?engine=brain`, which spends the whole 30 s request budget on the exact sizer. Same
  realizer, same validators, same `to_demo_design`; seconds instead of minutes.
* The **plan must not move** (the Issue's `primary_signature_changes: none`): the last test runs the
  brain twice, once with the parcel and once without, and compares every room, wall, door and
  window RELATIVE TO THE FOOTPRINT. A rigid translation into the parcel is the only difference
  allowed, and the test fails on anything else.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.demo.contract import to_demo_design
from app.demo.scope import ScopeCode, check_supported
from app.demo.service import generate_demo_design
from app.projects.models import (
    Project,
    SelectedFootprint,
    SourceTag,
    StreetSide,
    TaggedBool,
    TaggedInt,
)
from app.vertical_slice.brain.runner import run_brain
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.site import (
    NO_PARCEL_NOTICE,
    PARKING_BAY_DEPTH_M,
    classify_garden,
    site_frame_for,
)
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

#: One parcel, used everywhere below so a mismatch can only be the code's. Deliberately NOT the
#: footprint plus a margin: 23 x 20 m of land for a 15 x 12 m house is exactly the case the old
#: `_build_site` erased, and the numbers are far enough apart that no rounding could confuse them.
PLOT_W_M, PLOT_D_M = 23.0, 20.0
OUTLINE_W_M, OUTLINE_D_M = 15.0, 12.0
BUILT_AREA_M2 = 180.0


def _spec(parking: int = 2) -> ArchitecturalSpec:
    """The brief as the planner sees it. Setbacks 0 are the product's own committed defaults
    (`demo.site_geometry.FRONT_SETBACK_M` and friends), so the buildable region IS the parcel and
    the only street-side band is the one the bays need."""
    return ArchitecturalSpec(
        plot=PlotSpec(width_m=PLOT_W_M, depth_m=PLOT_D_M, front_setback_m=0.0,
                      side_setback_m=0.0, rear_setback_m=0.0),
        program=ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, parking_spaces=parking,
                            target_built_area_m2=BUILT_AREA_M2),
    )


def _project(parking: int = 2) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id="SITE223", city="TLV", street="S", plot_area_m2=PLOT_W_M * PLOT_D_M,
        plot_width_m=PLOT_W_M, plot_depth_m=PLOT_D_M, street_facing_side=StreetSide("NORTH"),
        built_area_m2=BUILT_AREA_M2, description="", status="active",
        created_at=now, updated_at=now,
        selected_footprint=SelectedFootprint(
            source="CUSTOM", shape_type="RECTANGLE", target_area_m2=BUILT_AREA_M2,
            width_m=OUTLINE_W_M, depth_m=OUTLINE_D_M,
            area_m2=round(OUTLINE_W_M * OUTLINE_D_M, 4)),
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=3, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.requested),
        parking_spaces=TaggedInt(value=parking, source=SourceTag.requested),
        wet_rooms=TaggedInt(value=2, source=SourceTag.requested),
        open_plan=TaggedBool(value=False, source=SourceTag.requested),
        requirements_parsed_at=now,
    )


@pytest.fixture(scope="module")
def brain_payloads() -> list:
    """Every plan the brain realizes for the parking brief, as the payload the renderer gets."""
    res = run_brain(_spec(parking=2), (OUTLINE_W_M, OUTLINE_D_M), brief="SITE223")
    assert res.distinct, "the brain planned nothing; the site facts below would be vacuous"
    return [to_demo_design(p.realized.design, p.realized.report) for p in res.distinct]


@pytest.fixture(scope="module")
def no_parcel_payloads() -> list:
    """The same brief realized with NO parcel — what a harness caller gets, and the only way to
    reach the disclosed-absence branch, since the product refuses such a project outright
    (see `test_the_product_refuses_a_brief_with_no_parcel_rather_than_reaching_that_branch`)."""
    from app.vertical_slice.brain import proposer

    real = proposer.site_frame_for
    proposer.site_frame_for = lambda spec: None
    try:
        res = run_brain(_spec(parking=2), (OUTLINE_W_M, OUTLINE_D_M), brief="SITE223")
    finally:
        proposer.site_frame_for = real
    assert res.distinct
    return [to_demo_design(p.realized.design, p.realized.report) for p in res.distinct]


# --------------------------------------------------------------- AC-1: the plot IS the parcel

def test_ac1_the_brain_payload_plot_is_the_brief_parcel(brain_payloads):
    for payload in brain_payloads:
        assert (payload.plot.x, payload.plot.y) == (0.0, 0.0)
        assert (payload.plot.width_m, payload.plot.depth_m) == (PLOT_W_M, PLOT_D_M), (
            "the plot drawn around the house must be the parcel the person entered, not a "
            "rectangle derived from the footprint")


def test_ac1_production_already_drew_the_parcel_and_still_does():
    """The control. #213 reported this defect as affecting production too; it does not — and this
    test is what stops #223 from changing production while fixing the brain."""
    design = generate_demo_design(_project(parking=2)).design
    assert (design.plot.width_m, design.plot.depth_m) == (PLOT_W_M, PLOT_D_M)


def test_ac1_the_house_stands_inside_the_parcel_behind_the_street_band(brain_payloads):
    """Placed, not merely drawn: `site.place_footprint`'s own convention — centred across the
    buildable width, flush to the band the bays need. The same place production stands it."""
    for payload in brain_payloads:
        fp = payload.footprint
        assert fp.y == pytest.approx(PARKING_BAY_DEPTH_M), "the bays' band must be left free"
        assert fp.x >= 0 and fp.x + fp.width_m <= PLOT_W_M + 1e-9
        assert fp.y + fp.depth_m <= PLOT_D_M + 1e-9
        # centred: the land left to its left and to its right differ by at most one grid unit
        left, right = fp.x, PLOT_W_M - (fp.x + fp.width_m)
        assert abs(left - right) <= 0.05 + 1e-9


# --------------------------------------------------------- AC-2: the garden is the real remainder

def _u(rect) -> Rect:
    return Rect(m_to_u(rect.x), m_to_u(rect.y), m_to_u(rect.width_m), m_to_u(rect.depth_m))


def _garden_classified_from_the_payloads_own_parcel(payload):
    """`site.classify_garden` — PRODUCTION's own remainder classification — re-run from the plot,
    the house and the bays this payload actually carries. A garden that equals this is the real
    remainder of the real parcel; a synthesised rectangle cannot be."""
    return classify_garden(None, _u(payload.plot), _u(payload.footprint),
                           tuple(_u(p) for p in payload.parking),
                           tuple(_u(f) for f in payload.footprints))


def _garden_facts(payload):
    house = sum(f.width_m * f.depth_m for f in payload.footprints)
    bays = sum(p.width_m * p.depth_m for p in payload.parking)
    garden = sum(g.width_m * g.depth_m for g in payload.garden)
    return house, bays, garden


def _assert_garden_is_the_real_remainder(payload):
    assert payload.garden, "a 460 m² parcel holding a ~180 m² house has a garden"
    expected = _garden_classified_from_the_payloads_own_parcel(payload)
    assert ([_u(g) for g in payload.garden]
            == [r for region in expected for r in region.rects])
    house, bays, garden = _garden_facts(payload)
    plot_area = payload.plot.width_m * payload.plot.depth_m
    # never claims land the parcel does not have, and never over the house or the bays
    assert garden + house + bays <= plot_area + 1e-6
    for g in payload.garden:
        assert g.x >= -1e-9 and g.y >= -1e-9
        assert g.x + g.width_m <= payload.plot.width_m + 1e-9
        assert g.y + g.depth_m <= payload.plot.depth_m + 1e-9
        for other in [*payload.footprints, *payload.parking]:
            over_w = min(g.x + g.width_m, other.x + other.width_m) - max(g.x, other.x)
            over_h = min(g.y + g.depth_m, other.y + other.depth_m) - max(g.y, other.y)
            assert over_w <= 1e-9 or over_h <= 1e-9, "garden drawn over the house or a bay"
    # EVERY square metre behind the building line is accounted for as house or garden. The only
    # land `classify_garden` leaves unclassified is inside the street band, beside the bays —
    # production's own long-standing behaviour, identical in both engines and untouched here.
    band_area = payload.plot.width_m * payload.footprint.y
    assert garden >= plot_area - band_area - house - 1e-6


def test_ac2_the_garden_is_what_is_genuinely_left_of_the_parcel(brain_payloads):
    """Not a synthesised rectangle and not just the crook of an L (which is all the old
    `_build_site` ever produced — 0 regions on a one-wing house)."""
    for payload in brain_payloads:
        _assert_garden_is_the_real_remainder(payload)


def test_ac2_production_garden_is_the_same_remainder_of_the_same_parcel():
    _assert_garden_is_the_real_remainder(generate_demo_design(_project(parking=2)).design)


# ------------------------------------------------- AC-4 (the measurement limit): parking, measured

def test_parking_is_drawn_where_the_brief_asks_for_it(brain_payloads):
    """#213's unmeasured half. Every brief in its corpus had `parking_spaces = 0`, so "no parking"
    could not be told apart from "parking not asked for". It can be now."""
    for payload in brain_payloads:
        assert len(payload.parking) == 2
        for bay in payload.parking:
            assert bay.y == 0.0, "a bay fronts the street edge (C10)"
            assert bay.depth_m == pytest.approx(PARKING_BAY_DEPTH_M)


def test_no_parking_asked_for_means_no_bays_invented():
    res = run_brain(_spec(parking=0), (OUTLINE_W_M, OUTLINE_D_M), brief="SITE223-noparking")
    assert res.distinct
    for plan in res.distinct:
        payload = to_demo_design(plan.realized.design, plan.realized.report)
        assert payload.parking == []
        assert payload.footprint.y == 0.0, "with no bays the house is on the building line"


@pytest.mark.parametrize("parking", [0, 2])
def test_production_draws_exactly_the_bays_the_brief_asks_for(parking):
    design = generate_demo_design(_project(parking=parking)).design
    assert len(design.parking) == parking


# ------------------------------------------- AC-3: no parcel is a stated absence, never a rectangle

def test_the_product_refuses_a_brief_with_no_parcel_rather_than_reaching_that_branch():
    """The first line of the answer to AC-3: in the product a missing parcel is a refusal, so no
    plan with an invented plot can be produced at all."""
    project = _project(parking=2).model_copy(update={"plot_width_m": None, "plot_depth_m": None})
    rejection = check_supported(project)
    assert rejection is not None and rejection.code is ScopeCode.SITE_GEOMETRY_REQUIRED


def test_ac3_a_realized_plan_with_no_parcel_discloses_the_absence(no_parcel_payloads):
    """The second line: a caller that realizes geometry without a parcel (a harness, a frozen
    case) gets the absence IN THE PAYLOAD, in the person's own language, through the channel
    #180's capacity notice already uses — not a plausible rectangle presented as a boundary."""
    for payload in no_parcel_payloads:
        assert NO_PARCEL_NOTICE in payload.validation.warnings


def test_ac3_the_disclosed_margin_is_not_passed_off_as_the_parcel(no_parcel_payloads):
    """And it is visibly not the parcel: no bays, no garden bands, and a plot that is the
    footprint plus the 2 m drawing margin rather than 23 x 20 m."""
    for payload in no_parcel_payloads:
        assert payload.parking == []
        assert (payload.plot.width_m, payload.plot.depth_m) != (PLOT_W_M, PLOT_D_M)
        assert payload.plot.width_m == pytest.approx(payload.footprint.x
                                                     + payload.footprint.width_m + 2.0)


def test_a_plan_built_from_the_brief_has_nothing_to_disclose(brain_payloads):
    for payload in brain_payloads:
        assert NO_PARCEL_NOTICE not in payload.validation.warnings


# -------------------------------------------------------------- the frame itself, in isolation

def test_the_frame_is_the_spec_and_nothing_derived_from_the_building():
    frame = site_frame_for(_spec(parking=2))
    assert frame.plot == Rect(0, 0, m_to_u(PLOT_W_M), m_to_u(PLOT_D_M))
    assert frame.front_band_u == m_to_u(PARKING_BAY_DEPTH_M)   # 0 setback, so the bay decides
    assert len(frame.parking) == 2
    assert frame.buildable_u() == (m_to_u(PLOT_W_M), m_to_u(PLOT_D_M) - m_to_u(PARKING_BAY_DEPTH_M))
    # no setbacks and no parking: the buildable region is the whole parcel
    assert site_frame_for(_spec(parking=0)).buildable_u() == (m_to_u(PLOT_W_M), m_to_u(PLOT_D_M))


def test_a_footprint_past_the_buildable_envelope_is_disclosed_not_clamped_away():
    """The one case where the parcel and the realized house disagree. The geometry is drawn as
    planned; the plan says so."""
    frame = site_frame_for(_spec(parking=2))
    assert frame.overflow_m(m_to_u(10.0), m_to_u(10.0)) == (0.0, 0.0)
    assert frame.overflow_m(m_to_u(25.0), m_to_u(18.0)) == (2.0, 3.0)


# --------------------------------------------- AC-5: the SITE moved, the PLAN did not

def _plan_relative_to_its_footprint(payload) -> dict:
    """Everything about the plan itself, with the footprint's own corner as the origin — the only
    thing a rigid translation into the parcel can change."""
    ox, oy = payload.footprint.x, payload.footprint.y
    r = lambda v: round(v, 4)

    def along(w, v):
        return r(v - (ox if w.orientation == "horizontal" else oy))

    return {
        "footprint_size": (r(payload.footprint.width_m), r(payload.footprint.depth_m)),
        "gross": payload.gross_area_m2, "net": payload.net_area_m2,
        "rooms": sorted((m.id, m.type, r(m.x - ox), r(m.y - oy), r(m.width_m), r(m.depth_m))
                        for m in payload.rooms),
        "walls": sorted((w.orientation, w.construction, w.boundary_context,
                         r(w.coord - (oy if w.orientation == "horizontal" else ox)),
                         along(w, w.start), along(w, w.end), tuple(sorted(w.room_ids)))
                        for w in payload.walls),
        "doors": sorted((d.a or "", d.b or "", d.kind, r(d.x - ox), r(d.y - oy))
                        for d in payload.doors),
        "windows": sorted((w.room_id, w.side, r(w.x - ox), r(w.y - oy), r(w.width_m))
                          for w in payload.windows),
        "checks": tuple(sorted(payload.validation.checks.items())),
        "passed": payload.validation.passed,
    }


def test_ac5_carrying_the_parcel_moves_the_site_and_not_the_plan(brain_payloads,
                                                                 no_parcel_payloads):
    assert len(brain_payloads) == len(no_parcel_payloads), (
        "the parcel must not change WHICH plans the brain realizes")
    for with_parcel, without in zip(brain_payloads, no_parcel_payloads):
        assert (_plan_relative_to_its_footprint(with_parcel)
                == _plan_relative_to_its_footprint(without)), (
            "every room, wall, door, window and validator verdict must be identical relative to "
            "the footprint; only where the footprint stands in the parcel may differ")
        assert (with_parcel.footprint.x, with_parcel.footprint.y) != (without.footprint.x,
                                                                      without.footprint.y)


def test_bays_that_do_not_fit_the_parcel_width_are_disclosed_not_hidden():
    """The other half of `_parcel_notice`. `site.build_parking` lays the bays out from the side
    setback without consulting the plot's width — production's own behaviour, unchanged — so a
    narrow parcel can end up with a bay past its edge. The plan says so rather than drawing it as
    though the land were there."""
    from app.vertical_slice.rectilinear_realizer import _parcel_notice

    narrow = PlotSpec(width_m=6.0, depth_m=18.0, front_setback_m=0.0, side_setback_m=0.0,
                      rear_setback_m=0.0)
    house = Rect(0, m_to_u(5.0), m_to_u(6.0), m_to_u(10.0))   # fits the parcel; only bays overflow
    three = site_frame_for(ArchitecturalSpec(plot=narrow,
                                             program=ProgramSpec(parking_spaces=3)))
    notice = _parcel_notice(three, house)
    assert notice is not None and "3" in notice
    one = site_frame_for(ArchitecturalSpec(plot=narrow, program=ProgramSpec(parking_spaces=1)))
    assert _parcel_notice(one, house) is None
