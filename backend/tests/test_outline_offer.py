"""Delivery policy: a person's outline that plans SHORT keeps the primary and gains a better
engine outline as the first alternative (`service._better_engine_outline`, `service.outline_note`).

Measured on the failure log (431 briefs, 2026-09-14): every within-capacity plan delivered under
80 % of the request was a person's extreme outline (10 x 20, 20 x 10, 12 x 18, 18 x 12) planning at
56-80 %, while the engine's own outline delivered 87-100 % — and was never tried, because the
person's outline had planned. Their choice stays the primary; the alternative and the note are new.
"""
from __future__ import annotations

from dataclasses import replace

from app.demo import service as svc
from app.vertical_slice.concept_generator import build_room_program, program_capacity_gross_m2
from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project

#: Logged: 3 bedrooms, 1 wet room, open plan, 200 m² asked, a 10 x 20 outline on a 17 x 30.5 plot.
#: The outline plans — at 112.7 m². The engine's 13.8 x 14.49 delivers 199.4 m².
NARROW_PERSON = dict(bedrooms=3, wet_rooms=1, safe_room=False, open_plan=True, built_area_m2=200.0,
                     footprint_width_m=10.0, footprint_depth_m=20.0, plot_width_m=17.0, plot_depth_m=30.5)


def test_a_short_person_outline_keeps_the_primary_and_gains_the_engine_outline_first():
    result = svc.generate_demo_design(_project(NARROW_PERSON))
    primary = result.design
    assert primary.outline.origin == "PERSON"
    assert (primary.outline.width_m, primary.outline.depth_m) == (10.0, 20.0)
    assert primary.gross_area_m2 < svc.OUTLINE_SHORTFALL_RATIO * 200.0     # planned short
    assert primary.validation.passed                                       # and still the primary
    assert result.alternatives, "the better outline must be offered"
    first = result.alternatives[0]
    assert first.outline.origin == "ENGINE"
    assert first.validation.passed
    assert first.gross_area_m2 >= primary.gross_area_m2 * (1 + svc.OUTLINE_ALTERNATIVE_MIN_GAIN)
    note = (f"המתאר שבחרת (10.00×20.00) מאפשר {primary.gross_area_m2:.0f} מ\"ר; במתאר "
            f"{first.outline.width_m:.2f}×{first.outline.depth_m:.2f} באותו מגרש ניתן להגיע "
            f"ל-{first.gross_area_m2:.0f} מ\"ר.")
    assert note in primary.validation.warnings
    assert not any("המתאר שבחרת" in w for w in first.validation.warnings)   # the note is the primary's
    tried = [(o.origin, o.planned) for o in result.search.outlines]
    assert tried[0] == ("PERSON", True) and ("ENGINE", True) in tried


def test_a_person_outline_that_plans_near_the_request_is_left_alone():
    result = svc.generate_demo_design(_project(WIDE_SQUARE))
    assert result.design.outline.origin == "PERSON"
    assert result.design.gross_area_m2 >= svc.OUTLINE_SHORTFALL_RATIO * WIDE_SQUARE["built_area_m2"]
    assert all(o.origin == "PERSON" for o in result.search.outlines)      # no engine outline surveyed
    assert not any("המתאר שבחרת" in w for w in result.design.validation.warnings)
    assert all(a.outline.origin == "PERSON" for a in result.alternatives)


def test_the_offer_needs_a_target_a_material_gain_and_a_way_out_of_the_shortfall():
    project = _project(NARROW_PERSON)
    spec = svc.spec_for(project)
    outlines = svc._outlines_for(project)
    person = [o for o in outlines if o.origin == "PERSON"]
    engine = [o for o in outlines if o.origin == "ENGINE"]
    planned = svc._plan_outlines(spec, project, person)[0]
    assert planned.plans
    no_target = replace(spec, program=replace(spec.program, target_built_area_m2=None))
    assert svc._better_engine_outline(no_target, project, engine, planned, None) is None
    offer = svc._better_engine_outline(spec, project, engine, planned, 200.0)
    assert offer is not None and offer.offered_for_area
    assert offer.plans[0].design.gross_area_m2 >= svc.OUTLINE_SHORTFALL_RATIO * svc.effective_target_m2(spec)
    # the same plan judged against a request it already meets: no survey, no offer
    met = replace(spec, program=replace(spec.program,
                                        target_built_area_m2=planned.plans[0].design.gross_area_m2))
    assert svc._better_engine_outline(met, project, engine, planned, met.program.target_built_area_m2) is None
    # ...and an engine outline no larger than the person's is not offered
    same_size = replace(planned, plans=planned.plans, outline=replace(planned.outline, origin="ENGINE"))
    assert svc._better_engine_outline(spec, project, [same_size.outline], planned, 200.0) is None


def test_the_bar_is_the_effective_target_not_the_request():
    """A request above the programme's capacity is measured against the capacity: what the rooms
    can fill is the bar, and an alternative that stays under 80 % of it is not a way out."""
    project = _project(NARROW_PERSON)
    spec = svc.spec_for(project)
    capacity = program_capacity_gross_m2(build_room_program(spec))
    over = replace(spec, program=replace(spec.program, target_built_area_m2=capacity * 3))
    assert svc.effective_target_m2(over) == capacity
    assert svc.effective_target_m2(spec) == 200.0          # within capacity: the request itself
    outlines = svc._outlines_for(project)
    person = [o for o in outlines if o.origin == "PERSON"]
    planned = svc._plan_outlines(spec, project, person)[0]
    # a fake engine result that is 10 % larger than the person's but still short of 80 % of the bar
    short = planned.plans[0].design.gross_area_m2 * 1.2
    assert short < svc.OUTLINE_SHORTFALL_RATIO * 200.0
    fake = replace(planned, outline=replace(planned.outline, origin="ENGINE", order=1))
    real_plan = svc._plan_outlines
    svc._plan_outlines = lambda *a, **k: [replace(fake, plans=(replace(fake.plans[0], design=replace(fake.plans[0].design, gross_area_m2=short)),))]
    try:
        assert svc._better_engine_outline(spec, project, [fake.outline], planned, 200.0) is None
    finally:
        svc._plan_outlines = real_plan
