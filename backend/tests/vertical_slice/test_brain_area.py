"""The area verdict (#197): did the plan miss, or does the brief not add up?

The first brain report quoted "area fidelity 53–110%" as one number and presented a plan covering
53% of its brief as meeting it. These tests pin the distinction that replaced that number.
"""
from app.vertical_slice.brain.area import AREA_TOLERANCE, assess_area


def test_a_plan_inside_the_stated_tolerance_meets_the_brief():
    v = assess_area(requested_m2=200, gross_m2=195, net_m2=180, capacity_m2=240)
    assert v.code == "WITHIN_TOLERANCE"
    assert v.acceptable
    assert v.gross_pct == 97.5


def test_the_tolerance_is_the_published_one_and_is_exact_at_the_boundary():
    low = 200 * (1 - AREA_TOLERANCE)
    assert assess_area(200, low, low, 240).code == "WITHIN_TOLERANCE"
    assert assess_area(200, low - 0.01, low, 240).code != "WITHIN_TOLERANCE"


def test_a_brief_whose_rooms_cannot_fill_the_footprint_is_named_as_such_and_still_counts():
    """B09: 440 m² asked of a programme that tops out at 250 m² (production's own
    `program_capacity_gross_m2`). No layout reaches 440 — production delivers 51.6% of it and the
    brain 40%. Saying so is the product behaviour; drawing a 177 m² house under a 440 m² label
    is not."""
    v = assess_area(requested_m2=440, gross_m2=177, net_m2=163, capacity_m2=250)
    assert v.code == "PROGRAMME_UNDERFILLS_FOOTPRINT"
    assert v.acceptable, "an honest answer to an inconsistent brief is not a failed plan"
    assert "more rooms or larger room types" in v.detail
    assert "250" in v.detail and "440" in v.detail, "the customer is told the actual numbers"


def test_a_layout_that_misses_what_its_own_programme_could_have_reached_is_a_defect():
    """Same shortfall, but here the rooms COULD have filled the footprint. That is the layout's
    fault, and past the 50% floor the plan must not be drawn at all."""
    v = assess_area(requested_m2=200, gross_m2=85, net_m2=78, capacity_m2=260)
    assert v.code == "AREA_TOLERANCE_EXCEEDED"
    assert not v.acceptable
    assert "the layout, not the brief, fell short" in v.detail


def test_over_delivering_is_also_outside_tolerance():
    v = assess_area(requested_m2=180, gross_m2=212, net_m2=195, capacity_m2=300)
    assert v.code == "AREA_OVER_TOLERANCE"
    assert not v.acceptable


def test_gross_and_net_are_reported_separately_and_never_conflated():
    """The published report quoted one and labelled it the other."""
    v = assess_area(requested_m2=200, gross_m2=196, net_m2=180, capacity_m2=240)
    assert v.gross_m2 != v.net_m2
    assert v.gross_pct == 98.0 and v.net_pct == 90.0


def test_the_two_failing_codes_differ_only_in_capacity():
    """The ONLY thing separating 'your brief does not add up' from 'we failed' is whether the
    programme could have reached the area. Pinned, because collapsing them is the original bug."""
    under = assess_area(400, 150, 140, capacity_m2=200)      # 37.5%, programme tops out at 200
    missed = assess_area(400, 150, 140, capacity_m2=420)     # same plan, programme could reach it
    assert under.code == "PROGRAMME_UNDERFILLS_FOOTPRINT" and under.acceptable
    assert missed.code == "AREA_TOLERANCE_EXCEEDED" and not missed.acceptable


def test_no_target_is_not_treated_as_a_failure():
    assert assess_area(0, 150, 140, 200).code == "NO_TARGET"


def test_a_shortfall_between_the_two_thresholds_is_delivered_with_the_shortfall_stated():
    """A single 10% bar rejects PRODUCTION on four of the eight audit briefs (77.4%, 62.6%,
    56.9%, 51.6%). A bar the shipping product cannot clear is not a quality bar. So between 10%
    and 20% the plan ships and the customer is told the number."""
    v = assess_area(requested_m2=216, gross_m2=185, net_m2=171, capacity_m2=233)
    assert v.code == "BELOW_TARGET_DISCLOSED"
    assert v.acceptable, "it ships"
    assert not v.meets_brief, "but it is never presented as meeting the brief"
    assert "31 m² short" in v.detail


def test_meets_brief_is_strictly_narrower_than_acceptable():
    inside = assess_area(216, 210, 195, 233)
    disclosed = assess_area(216, 185, 171, 233)
    underfilled = assess_area(440, 177, 163, 250)
    assert inside.meets_brief and inside.acceptable
    assert not disclosed.meets_brief and disclosed.acceptable
    assert not underfilled.meets_brief and underfilled.acceptable


def test_beyond_the_disclosure_threshold_nothing_is_delivered():
    """Below half the area asked for, the drawing is not an answer to that brief whatever its
    proportions — and here the programme could have reached it, so there is nothing to explain."""
    v = assess_area(requested_m2=216, gross_m2=100, net_m2=92, capacity_m2=233)
    assert v.code == "AREA_TOLERANCE_EXCEEDED"
    assert not v.acceptable
