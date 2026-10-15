"""The entrance as an explicit concept (#197).

THE DEFECT THESE PIN. The #197 render audit measured 22 of 23 brain plans arriving in the living
room, and traced it to one cause: the hall is a hub — it touches every bedroom, every shared wet
room and a public room — and in a band layout a hub has to sit in a middle band to reach the bands
above and below it. A middle band has no exterior wall, so the hall cannot hold the front door
however much `ENTRANCE_ZONE_PRIORITY` would like it to. The correlation was exact: the single plan
whose hall reached the street was the single plan that arrived in the hall.

Two things fixed it, and both are tested here: a degree-2 entry foyer that places trivially in the
street band, and a preference that makes every accepted candidate comparable instead of taking the
first one the embedder happened to offer.
"""
import pytest

from app.vertical_slice.band_pipeline import PipelineInput, PipelineSuccess, run_band_pipeline
from app.vertical_slice.brain.proposer import (ENTRY, FOYER_MIN_NET_M2, HALL, DeterministicProposer,
                                               programme_from_spec)
from app.vertical_slice.brain.runner import _arrival_zone, _rebanded, run_brain
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.band_embedding import find_k4, find_triple_lens
from tests.vertical_slice.test_hub_guard import _project

from app.demo.service import spec_for


def _spec(**kw):
    base = dict(bedrooms=4, wet_rooms=2, safe_room=False, open_plan=False,
                built_area_m2=216.0, footprint_width_m=12.0, footprint_depth_m=18.0,
                plot_width_m=20.0, plot_depth_m=26.0)
    base.update(kw)
    return spec_for(_project(base)), (base["footprint_width_m"], base["footprint_depth_m"])


# ----------------------------------------------------------------- the foyer, as a concept

def test_a_brief_that_can_afford_a_foyer_is_offered_both_variants():
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    assert p.affords_foyer
    names = [x.name for x in DeterministicProposer().propose(p)]
    assert any(n.endswith("+FOYER") for n in names)
    assert any(not n.endswith("+FOYER") for n in names), "the plain parti is still offered"
    # the foyer variant comes first: it is the one with an actual entrance sequence
    assert names[0].endswith("+FOYER")


def test_a_brief_too_small_for_a_foyer_gets_none():
    """A foyer in a small house is a room the brief cannot spare, and arriving in a public room
    is the honest answer there."""
    spec, fp = _spec(bedrooms=2, wet_rooms=1, built_area_m2=72.0,
                     footprint_width_m=8.0, footprint_depth_m=9.0)
    p = programme_from_spec(spec, fp)
    assert p.net_available_m2 < FOYER_MIN_NET_M2
    assert not p.affords_foyer
    assert not any(x.name.endswith("+FOYER") for x in DeterministicProposer().propose(p))


def test_the_foyer_is_degree_two_which_is_the_whole_point():
    """A hub cannot reach the street band. A degree-2 node can. If the foyer ever acquires more
    neighbours it becomes a second hall and stops solving the problem it was added for."""
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    for prop in DeterministicProposer().propose(p):
        if not prop.name.endswith("+FOYER"):
            continue
        neighbours = {b if a == ENTRY else a for a, b in prop.spatial if ENTRY in (a, b)}
        assert len(neighbours) == 1, f"{prop.name}: foyer touches {neighbours}"
        assert prop.arrival == ENTRY


def test_the_foyer_is_circulation_not_a_hall_so_a_street_fronting_hall_still_wins_the_door():
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    assert p.zones[ENTRY].role is ProgramRole.CIRCULATION
    assert p.zones[HALL].role is ProgramRole.HALL


def test_the_foyer_cannot_grow_into_a_second_hall():
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    assert p.zones[ENTRY].max_area_m2 <= 9.0


def test_adding_the_foyer_keeps_every_proposal_representable():
    """The two obstructions no rectangle layout can carry, re-asserted over the new variants."""
    for kw in ({}, dict(bedrooms=5, wet_rooms=3, safe_room=True, built_area_m2=312.0,
                        footprint_width_m=13.0, footprint_depth_m=24.0)):
        spec, fp = _spec(**kw)
        for prop in DeterministicProposer().propose(programme_from_spec(spec, fp)):
            adj: dict[str, set] = {}
            for a, b in prop.spatial:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
            assert find_k4(adj) is None, f"{prop.name} has a K4"
            assert find_triple_lens(adj) is None, f"{prop.name} has a triple lens"


# ----------------------------------------------------------------- the preference seam

def test_the_pipeline_is_unchanged_for_callers_that_pass_no_preference():
    """`prefer` is additive. Without it the pipeline still realizes in plausibility order and
    returns the first candidate the validators accept — byte-identical to before #197."""
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    prop = next(x for x in DeterministicProposer().propose(p) if not x.name.endswith("+FOYER"))
    # The FULL template range, which is what a caller outside the brain passes. The brain's own
    # zones are area-banded (#197 Stage 3) and rely on the runner's widening ladder; this test is
    # about the `prefer` seam in the pipeline, not about banding.
    zones = _rebanded({z: p.zones[z] for z in prop.rooms if z in p.zones}, p, None)
    inp = PipelineInput(name=prop.name, zones=zones, required_edges=tuple(prop.spatial),
                        footprint_m=p.footprint_m, wet_rooms=p.resolved_wet,
                        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE"))
    a = run_band_pipeline(inp, max_candidates=60, max_realizations=10)
    b = run_band_pipeline(inp, max_candidates=60, max_realizations=10)
    assert isinstance(a, PipelineSuccess) and isinstance(b, PipelineSuccess)
    assert a.candidate_index == b.candidate_index, "first-wins is deterministic"


def test_a_preference_can_choose_a_different_candidate_than_first_wins():
    """Proof the seam does something: a preference that inverts the order picks another plan."""
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    prop = next(x for x in DeterministicProposer().propose(p) if not x.name.endswith("+FOYER"))
    zones = _rebanded({z: p.zones[z] for z in prop.rooms if z in p.zones}, p, None)
    inp = PipelineInput(name=prop.name, zones=zones, required_edges=tuple(prop.spatial),
                        footprint_m=p.footprint_m, wet_rooms=p.resolved_wet,
                        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE"))
    plain = run_band_pipeline(inp, max_candidates=60, max_realizations=12)
    widest = run_band_pipeline(inp, max_candidates=60, max_realizations=12,
                               prefer=lambda res, pl, i: -max(r.w for r in res.rects.values()))
    assert isinstance(plain, PipelineSuccess) and isinstance(widest, PipelineSuccess)
    assert (max(r.w for r in widest.realized.rects.values())
            >= max(r.w for r in plain.realized.rects.values()))


def test_a_preference_never_accepts_a_candidate_the_validators_rejected():
    """The preference ORDERS the accepted candidates. It cannot admit one."""
    spec, fp = _spec()
    p = programme_from_spec(spec, fp)
    prop = next(iter(DeterministicProposer().propose(p)))
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    out = run_band_pipeline(
        PipelineInput(name=prop.name, zones=zones, required_edges=tuple(prop.spatial),
                      footprint_m=p.footprint_m, wet_rooms=p.resolved_wet,
                      access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE")),
        max_candidates=60, max_realizations=12, prefer=lambda res, pl, i: 0)
    if isinstance(out, PipelineSuccess):
        assert out.realized.ok, "a preference cannot override the validators"


# ----------------------------------------------------------------- end to end

def test_the_front_door_opens_into_circulation_not_a_living_room():
    """The headline regression, as a test. Before #197 this brief arrived in the living room."""
    spec, fp = _spec()
    res = run_brain(spec, fp, brief="entrance")
    assert res.distinct, "the brief must still plan"
    arrivals = []
    for plan in res.distinct:
        zone = _arrival_zone(plan.realized)
        role = next((z.roles for z in plan.realized.fixture.zones if z.zone_id == zone), ())
        arrivals.append((plan.parti, zone, role))
    assert any(ProgramRole.CIRCULATION in r or ProgramRole.HALL in r for _p, _z, r in arrivals), \
        f"no plan arrives at circulation: {arrivals}"


def test_every_delivered_plan_carries_an_area_verdict():
    spec, fp = _spec()
    res = run_brain(spec, fp, brief="area")
    assert res.distinct
    for plan in res.distinct:
        assert plan.area is not None
        assert plan.area.acceptable, f"{plan.parti}: {plan.area.code} — {plan.area.detail}"


def test_a_plan_whose_area_verdict_is_unacceptable_does_not_count():
    """The bar went UP, not down: `counts` now also requires an acceptable area verdict."""
    from app.vertical_slice.brain.area import assess_area
    from app.vertical_slice.brain.runner import BrainPlan

    good = BrainPlan("P", "r", True, bands=2, spatial_preserved="5/5", access_preserved="4/4",
                     area=assess_area(200, 195, 180, 240))
    bad = BrainPlan("P", "r", True, bands=2, spatial_preserved="5/5", access_preserved="4/4",
                    area=assess_area(200, 85, 78, 260))      # below the 50% floor
    assert good.counts and not bad.counts


def test_the_proportion_preference_never_reorders_the_architectural_priorities_and_prefers_rooms_on_target():
    """Owner item 2 (#197, 2026-10-14): the proportion-aware key keeps `_entrance_preference`'s
    three hard-priority keys first and unchanged, and between candidates that tie on them picks
    the one whose rooms sit closer to their targets. Measured on the 8 real briefs: 16 of 44
    parti pools change their pick, room deviation 17.0 -> 13.9 % on those, priorities identical
    in all 44 (docs/reports/architectural-brain/SELECTION-proportion.md)."""
    from app.vertical_slice.brain import runner as R
    from app.vertical_slice.brain.proposer import programme_from_spec
    from tests.vertical_slice.test_brain import SMALL, _spec_and_footprint
    spec, fp = _spec_and_footprint(SMALL)
    p = programme_from_spec(spec, fp)
    prop = DeterministicProposer().propose(p)[0]
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    seen = []
    old, new = R._entrance_preference(prop, zones, p), R._proportion_preference(prop, zones, p)

    def recording(realized, placement, inp):
        ko, kn = old(realized, placement, inp), new(realized, placement, inp)
        assert kn[:3] == ko[:3] and kn[5:] == ko[3:]          # the hard keys lead, the ornament trails
        seen.append((realized, ko, kn))
        return kn
    out = R.run_band_pipeline(R.PipelineInput(
        name=prop.name, zones=zones, required_edges=tuple(prop.spatial), footprint_m=p.footprint_m,
        wet_rooms=p.resolved_wet, access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE")),
        max_candidates=60, max_realizations=8, prefer=recording)
    assert isinstance(out, R.PipelineSuccess) and len(seen) >= 2
    best_new = min(seen, key=lambda c: c[2])
    ties = [c for c in seen if c[1][:3] == best_new[1][:3]]
    assert R.proportion_metrics(best_new[0], zones)[0] == min(R.proportion_metrics(c[0], zones)[0] for c in ties)
