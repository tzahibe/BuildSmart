"""Feature 006 — the outline list and the cross-outline selection, tested on stand-ins.

`_select_plans` reads five things off a plan: `concept.used_area_m2`, `index`, `layout_signature`,
`ok`, `family_signature` (phase 4 on) and `massing_signature` (one wing or two). The stubs below
provide exactly those, so the selection rules are pinned without solving a single fixture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from app.demo import service as svc
from app.demo.requirements_view import review_of
from app.demo.site_geometry import PREFERRED_RATIOS, feasible_options, derive
from app.projects.models import (
    Project, SelectedFootprint, SourceTag, StreetSide, TaggedBool, TaggedInt,
)


# ------------------------------------------------------------------ stand-ins
@dataclass(frozen=True)
class _Concept:
    used_area_m2: float


@dataclass(frozen=True)
class _Plan:
    used_area_m2: float
    index: int = 0
    family: str = "V[H[B,B],H,H[P,P,M]]"
    layout: str = ""
    ok: bool = True
    #: one wing ("1W") or two ("2W", an L) — `RealizedPlan.massing_signature`
    massing: str = "1W"
    #: realized quality for the L tiebreak (bedroom-class aspect, wet share, two-sided share)
    quality: tuple = (1.5, 1.0, 0.5)

    @property
    def concept(self) -> _Concept:
        return _Concept(self.used_area_m2)

    @property
    def family_signature(self) -> str:
        return self.family

    @property
    def massing_signature(self) -> str:
        return self.massing

    @property
    def layout_signature(self) -> str:
        return self.layout or f"{self.family}@{self.used_area_m2}#{self.index}"


@dataclass(frozen=True)
class _OutlineResult:
    outline: svc.Outline
    plans: tuple = ()
    result: object = None
    latency_ms: float = 0.0
    #: an engine outline offered beside a person's outline that planned short (delivery policy)
    offered_for_area: bool = False


@dataclass(frozen=True)
class _Massing:
    """Stand-in for `site_geometry.LMassing`: only the arm end matters to the selection."""
    arm_end: str


def _outline(order: int, origin: str = "ENGINE", w: float = 12.0, d: float = 15.0,
             arm_end: str | None = None) -> svc.Outline:
    return svc.Outline(w, d, origin, order, _Massing(arm_end) if arm_end else None)


# ------------------------------------------------------------------ _select_plans (US1)
def test_primary_is_the_plan_nearest_the_requested_area_across_outlines():
    results = [
        _OutlineResult(_outline(0), (_Plan(170.0, 0), _Plan(160.0, 1))),
        _OutlineResult(_outline(1), (_Plan(178.0, 0),)),
        _OutlineResult(_outline(2), (_Plan(190.0, 0),)),
    ]
    selection = svc._select_plans(results, 180.0)
    assert selection.primary[0].outline.order == 1
    assert selection.primary[1].used_area_m2 == 178.0


def test_only_outline_primaries_compete_and_ties_fall_to_the_earlier_outline():
    """An outline's alternatives never displace its primary — the same invariant that holds
    within one outline today (`test_the_alternatives_never_change_which_plan_was_chosen`)."""
    results = [
        _OutlineResult(_outline(0), (_Plan(170.0, 3), _Plan(176.0, 5))),   # alternative nearer
        _OutlineResult(_outline(1), (_Plan(176.0, 0),)),
        _OutlineResult(_outline(2), (_Plan(176.0, 0),)),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[0].outline.order == 1
    assert selection.primary[1].index == 0


def test_an_unvalidated_plan_must_never_reach_the_pool():
    results = [_OutlineResult(_outline(0), (_Plan(176.0, 0, ok=False),))]
    with pytest.raises(AssertionError):
        svc._select_plans(results, 176.0)


def test_no_plans_anywhere_selects_nothing():
    results = [_OutlineResult(_outline(0)), _OutlineResult(_outline(1))]
    assert svc._select_plans(results, 176.0) is None


def test_at_most_three_plans_are_shown():
    plans = tuple(_Plan(176.0 - i, i) for i in range(8))
    selection = svc._select_plans([_OutlineResult(_outline(0), plans)], 176.0)
    assert 1 + len(selection.alternatives) <= 3


def test_the_persons_outline_stays_first_even_when_an_engine_outline_is_nearer_the_target():
    results = [
        _OutlineResult(_outline(0, "PERSON"), (_Plan(160.0, 0),)),
        _OutlineResult(_outline(1), (_Plan(176.0, 0),)),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[0].outline.origin == "PERSON"
    assert selection.primary[1].used_area_m2 == 160.0


def test_a_persons_outline_that_did_not_plan_does_not_block_an_engine_plan():
    results = [
        _OutlineResult(_outline(0, "PERSON")),
        _OutlineResult(_outline(1), (_Plan(176.0, 0),)),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[0].outline.origin == "ENGINE"


# ------------------------------------------------------------------ _outlines_for (US1)
def _project(*, footprint: tuple[float, float] | None, plot=(20.0, 24.0), area=132.0) -> Project:
    now = datetime.now(timezone.utc)
    selected = None
    if footprint is not None:
        w, d = footprint
        selected = SelectedFootprint(source="CUSTOM", shape_type="RECTANGLE", target_area_m2=area,
                                     width_m=w, depth_m=d, area_m2=round(w * d, 4))
    return Project(
        project_id="T", city="TLV", street="S", plot_area_m2=plot[0] * plot[1],
        plot_width_m=plot[0], plot_depth_m=plot[1], street_facing_side=StreetSide("NORTH"),
        built_area_m2=area, description="", status="active", created_at=now, updated_at=now,
        selected_footprint=selected,
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=2, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.unknown),
        parking_spaces=TaggedInt(value=0, source=SourceTag.requested),
        wet_rooms=TaggedInt(value=1, source=SourceTag.requested),
        open_plan=TaggedBool(value=True, source=SourceTag.requested),
        requirements_parsed_at=now,
    )


def test_without_a_footprint_the_outlines_are_the_engines_shapes_in_preferred_order():
    project = _project(footprint=None)
    outlines = svc._outlines_for(project)
    expected = feasible_options(derive(project), project.built_area_m2)
    # The rectangles first, in the preferred order; then the engine's L massings, when the site
    # and the area allow any (they are outlines too, with a massing on them).
    rectangles = [o for o in outlines if o.massing is None]
    assert [(o.width_m, o.depth_m) for o in rectangles] == list(dict.fromkeys(expected))
    assert all(o.origin == "ENGINE" for o in outlines)
    assert [o.order for o in outlines] == list(range(len(outlines)))
    assert len(rectangles) <= len(PREFERRED_RATIOS)
    assert all(o.massing is not None for o in outlines[len(rectangles):])


def test_the_persons_footprint_comes_first_and_an_equal_engine_shape_is_dropped():
    project = _project(footprint=None)
    first_w, first_d = feasible_options(derive(project), project.built_area_m2)[0]
    with_person = _project(footprint=(first_w, first_d))
    outlines = svc._outlines_for(with_person)
    assert outlines[0].origin == "PERSON" and outlines[0].order == 0
    assert (outlines[0].width_m, outlines[0].depth_m) == (first_w, first_d)
    assert sum(1 for o in outlines
               if (round(o.width_m, 2), round(o.depth_m, 2)) == (round(first_w, 2), round(first_d, 2))) == 1


def test_a_custom_footprint_precedes_the_engines_shapes_without_replacing_them():
    project = _project(footprint=(11.0, 12.0))
    outlines = svc._outlines_for(project)
    assert outlines[0].origin == "PERSON"
    assert [o.origin for o in outlines[1:]] == ["ENGINE"] * (len(outlines) - 1)
    assert all(abs(o.area_m2 - 132.0) < 1.0 for o in outlines)


# ------------------------------------------------------------------ shown alternatives (US2)
#
# Family is a DISPLAY de-duplication key: it decides which of the validated plans are worth
# showing beside the primary, and nothing else.

def test_three_families_available_means_three_families_shown():
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), _Plan(175.0, 1, "F1"), _Plan(174.0, 2, "F2"))),
        _OutlineResult(_outline(1), (_Plan(173.0, 0, "F3"),)),
    ]
    selection = svc._select_plans(results, 176.0)
    families = [selection.primary[1].family] + [p.family for _, p in selection.alternatives]
    assert sorted(families) == ["F1", "F2", "F3"]


def test_two_families_both_shown_and_the_third_slot_needs_a_different_outline():
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), _Plan(175.0, 1, "F2"), _Plan(174.0, 2, "F1"))),
    ]
    selection = svc._select_plans(results, 176.0)
    assert [p.family for _, p in selection.alternatives] == ["F2"], "no third slot: same outline only"

    with_other_outline = results + [_OutlineResult(_outline(1), (_Plan(172.0, 0, "F1"),))]
    selection = svc._select_plans(with_other_outline, 176.0)
    assert [(o.outline.order, p.family) for o, p in selection.alternatives] == [(0, "F2"), (1, "F1")]


def test_one_family_from_one_outline_shows_one_plan_and_is_not_padded():
    results = [_OutlineResult(_outline(0), tuple(_Plan(176.0 - i, i, "F1") for i in range(5)))]
    selection = svc._select_plans(results, 176.0)
    assert selection.alternatives == ()


def test_the_same_drawing_is_never_shown_twice():
    same = _Plan(175.0, 1, "F2", layout="same")
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), same, _Plan(175.0, 2, "F2", layout="same"))),
        _OutlineResult(_outline(1), (_Plan(174.0, 0, "F3"),)),
    ]
    selection = svc._select_plans(results, 176.0)
    drawings = [(o.outline.order, p.layout_signature) for o, p in [selection.primary, *selection.alternatives]]
    assert len(drawings) == len(set(drawings))


def test_no_two_shown_plans_share_family_and_outline():
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), _Plan(175.0, 1, "F1"), _Plan(174.0, 2, "F1"))),
        _OutlineResult(_outline(1), (_Plan(173.0, 0, "F1"),)),
        _OutlineResult(_outline(2), (_Plan(172.0, 0, "F1"),)),
    ]
    selection = svc._select_plans(results, 176.0)
    pairs = [(o.outline.order, p.family) for o, p in [selection.primary, *selection.alternatives]]
    assert len(pairs) == len(set(pairs))
    assert [o.outline.order for o, _ in selection.alternatives] == [1, 2]


def test_a_rarer_family_nearer_the_target_still_does_not_become_primary():
    """Family must never reach the primary choice: the primary is the area-nearest OUTLINE PRIMARY,
    even when a different-family alternative sits nearer the target."""
    results = [
        _OutlineResult(_outline(0), (_Plan(170.0, 0, "F1"), _Plan(176.0, 4, "F2"))),
        _OutlineResult(_outline(1), (_Plan(171.0, 0, "F1"),)),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[1].family == "F1" and selection.primary[1].used_area_m2 == 171.0
    assert [p.family for _, p in selection.alternatives][0] == "F2"


def test_the_persons_plan_stays_first_and_its_alternatives_follow_the_same_rules():
    results = [
        _OutlineResult(_outline(0, "PERSON"), (_Plan(160.0, 0, "F1"), _Plan(159.0, 1, "F1"), _Plan(158.0, 2, "F2"))),
        _OutlineResult(_outline(1), (_Plan(176.0, 0, "F1"),)),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[0].outline.origin == "PERSON"
    assert [(o.outline.order, p.family) for o, p in selection.alternatives] == [(0, "F2"), (1, "F1")]


# ------------------------------------------------------------------ massing representation
def test_a_plan_of_another_massing_is_shown_before_a_second_organisation_of_the_same():
    """An L (two wings) that lands farther from the request than every one-wing plan is still
    shown: a massing is the coarsest difference a person sees, so it takes a slot before a second
    one-wing organisation does. The primary is untouched — still the area-nearest plan."""
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), _Plan(175.0, 1, "F2"), _Plan(174.0, 2, "F3"),
                                     _Plan(150.0, 3, "V[...]+H[...]", massing="2W"))),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[1].family == "F1" and selection.primary[1].massing == "1W"
    shown = [(p.family, p.massing) for _, p in selection.alternatives]
    assert shown[0] == ("V[...]+H[...]", "2W"), "the other massing takes the first alternative slot"
    assert shown[1] == ("F2", "1W")
    assert len(shown) == 2


def test_the_massing_pass_changes_nothing_when_every_plan_is_one_wing():
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), _Plan(175.0, 1, "F1"), _Plan(174.0, 2, "F2"))),
        _OutlineResult(_outline(1), (_Plan(173.0, 0, "F3"),)),
    ]
    selection = svc._select_plans(results, 176.0)
    families = [selection.primary[1].family] + [p.family for _, p in selection.alternatives]
    assert sorted(families) == ["F1", "F2", "F3"]


def test_a_two_wing_primary_gets_a_one_wing_alternative_first():
    """The rule is symmetric: when the area-nearest plan is the L, a one-wing plan is guaranteed
    a slot — the person sees both massings whichever won on area."""
    results = [
        _OutlineResult(_outline(0), (_Plan(176.0, 0, "V[...]+H[...]", massing="2W"),
                                     _Plan(175.0, 1, "V[...]+H[...]", massing="2W"),
                                     _Plan(160.0, 2, "F1"))),
    ]
    selection = svc._select_plans(results, 176.0)
    assert selection.primary[1].massing == "2W"
    assert [p.massing for _, p in selection.alternatives][0] == "1W"



# ------------------------------------------------------------------ L massings on a rectangular plot
from app.demo import site_geometry as sg


def _site(w=24.0, d=28.0, front=5.5, side=3.0, rear=4.0) -> sg.SiteGeometry:
    return sg.SiteGeometry(plot_width_m=w, plot_depth_m=d, street_facing_side=StreetSide.north,
                           canonical_width_m=w, canonical_depth_m=d,
                           front_setback_m=front, side_setback_m=side, rear_setback_m=rear)


def test_l_massings_carve_two_wings_at_the_requested_area_when_the_site_allows():
    massings = sg.l_massings(_site(), 200.0)
    assert [m.arm_end for m in massings] == ["rear", "front"]
    for m in massings:
        assert m.area_m2 == pytest.approx(200.0, abs=0.5), "the area is the request, never less"
        assert m.arm_w_m == sg.L_ARM_WIDTH_M and m.arm_d_m == sg.L_ARM_DEPTH_M
        assert m.bbox_w_m <= _site().buildable_width_m + 1e-9 and m.bbox_d_m <= _site().buildable_depth_m + 1e-9
        assert m.primary_w_m >= sg.L_PRIMARY_MIN_WIDTH_M
        # The primary column outweighs the full-width strip along the arm, so the adapter's largest
        # rectangle IS the primary and the arm lies east of it, not north or south.
        assert m.primary_w_m * m.primary_d_m > (m.primary_w_m + m.arm_w_m) * m.arm_d_m


def test_l_massings_ring_is_the_l_itself():
    rear, front = sg.l_massings(_site(), 200.0)
    pts = rear.ring_points(3.0, 5.5)
    assert len(pts) == 6 and pts[0] == (3.0, 5.5)
    # Shoelace: the ring's area is the massing's, and it is counter-clockwise (positive).
    area = 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))
    assert area == pytest.approx(rear.area_m2, abs=0.01)
    assert front.ring_points(3.0, 5.5)[1] == (3.0 + front.bbox_w_m, 5.5), "front arm: full width at the street"


def test_no_l_massing_when_the_house_is_too_small_or_the_site_too_tight():
    assert sg.l_massings(_site(), 120.0) == []                        # primary would be a strip
    assert sg.l_massings(_site(w=16.0, d=22.0, front=5.0, side=3.0, rear=3.0), 150.0) == []  # 10 x 14 buildable
    assert sg.l_massings(_site(), 300.0) == []                        # too wide for the plot


def test_outlines_include_the_l_massings_after_the_rectangles_and_label_them():
    project = _project(footprint=None, plot=(24.0, 28.0), area=200.0)
    outlines = svc._outlines_for(project)
    shapes = [o.shape for o in outlines]
    assert shapes[: shapes.index("L")].count("L") == 0 and shapes.count("L") == 2
    l = next(o for o in outlines if o.massing is not None)
    assert l.origin == "ENGINE" and l.area_m2 == pytest.approx(200.0, abs=0.5)
    out = l.as_out()
    assert out.shape == "L" and len(out.wing_dims_m) == 2 and out.width_m == l.massing.bbox_w_m


def test_a_second_l_from_the_other_massing_outline_does_not_take_a_rectangles_slot():
    """The rear-arm and front-arm L massings produce same-area, same-family plans on different
    outlines. One is shown (massing pass); the other must not come through the 'another outline'
    pass in place of a rectangle alternative."""
    results = [
        _OutlineResult(_outline(0), (_Plan(192.0, 0, "F1"),)),
        _OutlineResult(_outline(1), (_Plan(190.0, 0, "F1"),)),                 # same family, other outline
        _OutlineResult(_outline(4), (_Plan(141.5, 0, "L1", massing="2W"),)),
        _OutlineResult(_outline(5), (_Plan(141.5, 0, "L1", massing="2W"),)),
    ]
    selection = svc._select_plans(results, 200.0)
    shown = [(p.massing, p.family, o.outline.order) for o, p in selection.alternatives]
    assert shown == [("2W", "L1", 4), ("1W", "F1", 1)]


def test_the_two_l_orientations_are_different_families_but_only_one_is_shown():
    """Arm at the rear and arm at the front give different trees (band above or below the seam),
    so family alone would admit both. One L per shown set; the rectangle alternative keeps its slot."""
    results = [
        _OutlineResult(_outline(0), (_Plan(192.0, 0, "F1"), _Plan(185.0, 1, "F2"))),
        _OutlineResult(_outline(4), (_Plan(166.0, 0, "L-rear", massing="2W"),)),
        _OutlineResult(_outline(5), (_Plan(166.0, 0, "L-front", massing="2W"),)),
    ]
    selection = svc._select_plans(results, 200.0)
    shown = [(p.massing, p.family) for _, p in selection.alternatives]
    assert shown == [("2W", "L-rear"), ("1W", "F2")]


# ------------------------------------------------------------------ the L orientation tiebreak
from app.vertical_slice.spec import HouseConcept, PublicOpenSide

GARDEN = HouseConcept(public_open_side=PublicOpenSide.GARDEN)
STREET = HouseConcept(public_open_side=PublicOpenSide.STREET)
ENGINE = HouseConcept()


@pytest.fixture(autouse=True)
def _stub_l_quality(monkeypatch):
    """The tiebreak reads realized measures off `plan.design`; the stubs carry them directly."""
    monkeypatch.setattr(svc, "_l_quality_of_plan", lambda plan: svc.LQuality(*plan.quality))


def _tied_ls(rear_quality=(1.5, 1.0, 0.5), front_quality=(1.5, 1.0, 0.5)):
    """A rectangle primary, two one-wing alternatives, and the two L orientations tied on area."""
    return [
        _OutlineResult(_outline(0), (_Plan(196.0, 0, "F1"), _Plan(185.0, 1, "F2"), _Plan(184.0, 2, "F3"))),
        _OutlineResult(_outline(4, arm_end="rear"), (_Plan(161.5, 0, "L-rear", massing="2W", quality=rear_quality),)),
        _OutlineResult(_outline(5, arm_end="front"), (_Plan(161.5, 0, "L-front", massing="2W", quality=front_quality),)),
    ]


def _shown_l(selection):
    ls = [(o.outline.massing.arm_end, p.family) for o, p in selection.alternatives if o.outline.massing]
    assert len(ls) == 1, "exactly one L in the shown set"
    return ls[0][0]


def test_garden_preference_selects_the_front_arm_l():
    assert _shown_l(svc._select_plans(_tied_ls(), 200.0, GARDEN)) == "front"


def test_street_preference_selects_the_rear_arm_l():
    assert _shown_l(svc._select_plans(_tied_ls(), 200.0, STREET)) == "rear"


def test_engine_selects_the_better_realized_l_when_quality_differs():
    # The front L has the better bedrooms and the same wet share and exposure: it dominates.
    assert _shown_l(svc._select_plans(_tied_ls(front_quality=(1.2, 1.0, 0.5)), 200.0, ENGINE)) == "front"
    # The rear L has better exposure: it dominates.
    assert _shown_l(svc._select_plans(_tied_ls(rear_quality=(1.5, 1.0, 0.8)), 200.0, ENGINE)) == "rear"
    # Better on one measure, worse on another: no dominance, order decides (rear is order 4).
    assert _shown_l(svc._select_plans(_tied_ls(rear_quality=(1.2, 1.0, 0.5), front_quality=(1.5, 1.0, 0.8)),
                                      200.0, ENGINE)) == "rear"


def test_an_exact_quality_tie_falls_back_to_outline_order_deterministically():
    for _ in range(3):
        assert _shown_l(svc._select_plans(_tied_ls(), 200.0, ENGINE)) == "rear"
    # ...and a plan's own concept default is ENGINE, so no concept given behaves the same.
    assert _shown_l(svc._select_plans(_tied_ls(), 200.0)) == "rear"


def test_a_preference_that_no_peer_matches_falls_through_to_quality():
    results = [
        _OutlineResult(_outline(0), (_Plan(196.0, 0, "F1"), _Plan(185.0, 1, "F2"))),
        _OutlineResult(_outline(4, arm_end="rear"), (_Plan(161.5, 0, "L-rear-a", massing="2W", quality=(1.5, 1.0, 0.5)),)),
        _OutlineResult(_outline(6, arm_end="rear"), (_Plan(161.5, 0, "L-rear-b", massing="2W", quality=(1.3, 1.0, 0.5)),)),
    ]
    selection = svc._select_plans(results, 200.0, GARDEN)   # no front-arm L exists
    assert [p.family for _, p in selection.alternatives if p.massing == "2W"] == ["L-rear-b"]


def test_the_tiebreak_leaves_rectangles_and_the_primary_alone():
    for concept in (GARDEN, STREET, ENGINE):
        selection = svc._select_plans(_tied_ls(), 200.0, concept)
        assert selection.primary[1].family == "F1" and selection.primary[1].massing == "1W"
        shown = [(p.massing, p.family) for _, p in selection.alternatives]
        assert shown[1] == ("1W", "F2"), "the rectangle alternative keeps its slot"
        assert sum(1 for m, _ in shown if m == "2W") == 1
    # A pool with no L at all: the same three families as always, whatever the concept says.
    plain = [_OutlineResult(_outline(0), (_Plan(176.0, 0, "F1"), _Plan(175.0, 1, "F2"), _Plan(174.0, 2, "F3")))]
    for concept in (GARDEN, STREET, ENGINE):
        selection = svc._select_plans(plain, 176.0, concept)
        assert [selection.primary[1].family] + [p.family for _, p in selection.alternatives] == ["F1", "F2", "F3"]


def test_the_tiebreak_applies_only_to_peers_tied_on_the_area_criterion():
    """A front-arm L nearer the request is chosen by the existing criterion, whatever the
    preference says — the tiebreak never overrides the pool's own ranking."""
    results = [
        _OutlineResult(_outline(0), (_Plan(196.0, 0, "F1"), _Plan(185.0, 1, "F2"))),
        _OutlineResult(_outline(4, arm_end="rear"), (_Plan(150.0, 0, "L-rear", massing="2W"),)),
        _OutlineResult(_outline(5, arm_end="front"), (_Plan(170.0, 0, "L-front", massing="2W"),)),
    ]
    assert _shown_l(svc._select_plans(results, 200.0, STREET)) == "front"



# --- the preference travels from the stored project into the spec the selection reads -----------


def test_a_project_without_the_living_side_reads_as_the_engine_deciding():
    """Every project stored before the field existed, and every brief that says nothing: the
    review shows "the engine decides" as an assumption, and the spec's concept is the default
    one — so the plans are exactly what they were."""
    from app.vertical_slice.spec import HouseConcept
    from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project
    project = _project(WIDE_SQUARE)
    assert project.public_open_side is None
    review = review_of(project)
    assert (review.public_open_side.value, review.public_open_side.source) == ("engine", "inferred")
    assert svc.spec_for(project).concept == HouseConcept()


def test_the_stored_living_side_becomes_the_concept_the_selection_reads():
    from app.projects.models import TaggedStr
    from app.vertical_slice.spec import PublicOpenSide
    from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project
    project = _project(WIDE_SQUARE).model_copy(
        update={"public_open_side": TaggedStr(value="garden", source=SourceTag.requested)})
    review = review_of(project)
    assert (review.public_open_side.value, review.public_open_side.source) == ("garden", "requested")
    concept = svc.spec_for(project).concept
    assert concept.public_open_side is PublicOpenSide.GARDEN
    assert not concept.hard_fields, "a preference, never a binding requirement"


def test_a_living_side_this_build_does_not_know_falls_back_to_the_engine():
    """A project stored by a later build with a value this one has no parti for still plans."""
    from app.projects.models import TaggedStr
    from app.vertical_slice.spec import PublicOpenSide
    from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project
    project = _project(WIDE_SQUARE).model_copy(
        update={"public_open_side": TaggedStr(value="courtyard", source=SourceTag.requested)})
    assert svc.spec_for(project).concept.public_open_side is PublicOpenSide.ENGINE
