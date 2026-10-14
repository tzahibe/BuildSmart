"""E1 — orientation as an explicit concept dimension (`PublicOrientation`).

Four things these tests exist to hold:

1. PRODUCTION IS UNTOUCHED. `generate_concepts` with its default returns the same candidates in the
   same order it always did, and every orientation-dependent helper behaves exactly as before at
   its default. This is the acceptance criterion the owner stated as "byte-identical with the flag
   OFF", pinned at the two places the flag could leak.
2. THE MIRROR IS REAL. A `REAR_PUBLIC_BAND` candidate puts the public band on the GARDEN elevation
   and the arrival hall on the street — checked on the realized rectangles, not on the tree.
3. THE PARTI IS SHARED. The rear band is produced exactly when the front band is, because the two
   share every sizing rule; a brief where the front band refuses is a brief where the rear band
   refuses, for the same recorded reason.
4. IT REALIZES AND VALIDATES. On the one audited brief whose programme the band parti can host, the
   rear band passes every unchanged validator.
"""
from __future__ import annotations

import pytest

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice.concept_spec import PublicOrientation, concept_spec_of
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.safe_adapter import adapt

#: The one frozen audit brief whose programme the band parti can host at all (measured: the front
#: band produces candidates on 1 of the 8, and the rear band on exactly the same 1).
_BAND_BRIEF = "B19"
#: One where it cannot, so the "same refusal, both orientations" property has a witness.
_NO_BAND_BRIEF = "B06"


def _project(bid: str):
    from tests.vertical_slice.test_hub_guard import _project as make
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    return make(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                     open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                     footprint_width_m=b.footprint_width_m,
                     footprint_depth_m=b.footprint_depth_m,
                     plot_width_m=b.footprint_width_m + 8,
                     plot_depth_m=b.footprint_depth_m + 8))


def _generated(bid: str, orientation: PublicOrientation):
    project = _project(bid)
    spec = svc.spec_for(project)
    buildable = svc._buildable_from(spec, project, None)
    return spec, buildable, generator.generate_concepts(
        spec, list(adapt(buildable).candidates), public_orientation=orientation)


def _identity(candidate) -> tuple:
    """Everything about a candidate that a later stage can see — enough that two runs agreeing on
    it cannot be producing different plans."""
    return (candidate.strategy.value, candidate.circulation_class.value, candidate.rationale,
            candidate.used_area_m2, candidate.unused_wing_area_m2, candidate.repartitioned,
            candidate.shrunk, candidate.over_preferred, candidate.quality_repartitioned,
            tuple(sorted(z.zone_id for z in candidate.concept.fixture.zones)))


# --------------------------------------------------------------- 1. production is untouched

@pytest.mark.parametrize("bid", [_BAND_BRIEF, _NO_BAND_BRIEF])
def test_the_default_generates_no_rear_band_candidate(bid):
    _, _, generated = _generated(bid, PublicOrientation.STREET)
    assert not [c for c in generated.candidates
                if c.strategy is generator.ConceptStrategy.REAR_PUBLIC_BAND]
    assert all(c.public_orientation is PublicOrientation.STREET for c in generated.candidates)


@pytest.mark.parametrize("bid", [_BAND_BRIEF, _NO_BAND_BRIEF])
def test_asking_for_garden_leaves_every_existing_candidate_exactly_as_it_was(bid):
    """The rear band is ADDITIVE. Every candidate the default run produced is still there, in the
    same order, with the same rationale and the same area — so a brief that plans today plans
    identically whether or not the experiment is asked for."""
    _, _, default = _generated(bid, PublicOrientation.STREET)
    _, _, garden = _generated(bid, PublicOrientation.GARDEN)
    kept = [c for c in garden.candidates
            if c.strategy is not generator.ConceptStrategy.REAR_PUBLIC_BAND]
    assert [_identity(c) for c in kept] == [_identity(c) for c in default.candidates]


def test_daylight_order_is_unchanged_at_its_default():
    """`south_is_envelope` defaults to the assumption every parti on `main` relies on, so the
    rescue moves the same rows it always did."""
    rooms = generator.build_room_program(svc.spec_for(_project(_BAND_BRIEF)))
    rows = generator._rows_of([r for r in rooms if r.group is not generator.ZoneGroup.PUBLIC])
    for north in (True, False):
        assert (generator._daylight_order(rows, north_is_envelope=north)
                == generator._daylight_order(rows, north_is_envelope=north,
                                             south_is_envelope=True))


def test_without_a_south_envelope_an_at_risk_row_is_moved_to_the_north_end():
    """The one behaviour the new parameter adds: with only the north end exterior, a shared row
    that would otherwise be landlocked takes that end instead of the south one."""
    rooms = generator.build_room_program(svc.spec_for(_project(_BAND_BRIEF)))
    rows = generator._rows_of([r for r in rooms if r.group is not generator.ZoneGroup.PUBLIC])
    at_risk = [r for r in rows if generator._needs_column_end(r)]
    if not at_risk:
        pytest.skip("this programme has no shared row that needs a column end")
    ordered = generator._daylight_order(rows, north_is_envelope=True, south_is_envelope=False)
    assert ordered[0] is at_risk[0]
    assert sorted(map(id, ordered)) == sorted(map(id, rows))      # nothing is lost or duplicated


# --------------------------------------------------------------- 2./4. the mirror is real

def test_the_rear_band_realizes_with_the_public_band_on_the_garden():
    spec, buildable, generated = _generated(_BAND_BRIEF, PublicOrientation.GARDEN)
    rear = [(i, c) for i, c in enumerate(generated.candidates)
            if c.strategy is generator.ConceptStrategy.REAR_PUBLIC_BAND]
    assert rear, "the band parti plans on this brief, so its rear orientation must too"

    plan = None
    for index, candidate in rear:
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue        # a candidate the solver refuses is not a failure of the orientation
        realized = gp._realize(spec, buildable, None, candidate, index, solve, ())
        if realized.ok:
            plan = realized
            break
    assert plan is not None, "no rear-band candidate passed the unchanged validators"
    assert not [c.check_id for c in plan.validation.failures()]
    assert plan.safety.ok

    rooms = {r.zone_id: r for r in plan.design.rooms}
    fx, fy, fw, fh = plan.design.footprint_m
    public = [r for r in plan.design.rooms
              if {"LIVING", "DINING", "KITCHEN", "LIVING_KITCHEN"} & {str(x) for x in r.roles}]
    assert public
    # every public room's SOUTH edge is the building's south edge — the garden elevation
    assert all(abs((r.rect_m[1] + r.rect_m[3]) - (fy + fh)) < 0.06 for r in public), \
        "a REAR_PUBLIC_BAND must put the public band on the garden elevation"
    # and the hall reaches the street, which is what makes the arrival a hall rather than a room
    hall = rooms["HALL"]
    assert abs(hall.rect_m[1] - fy) < 0.06


def test_the_rear_band_carries_its_orientation_into_the_concept_spec():
    _, _, generated = _generated(_BAND_BRIEF, PublicOrientation.GARDEN)
    rear = next(c for c in generated.candidates
                if c.strategy is generator.ConceptStrategy.REAR_PUBLIC_BAND)
    front = next(c for c in generated.candidates
                 if c.strategy is generator.ConceptStrategy.FRONT_PUBLIC_BAND)
    assert concept_spec_of(rear).public_orientation is PublicOrientation.GARDEN
    assert concept_spec_of(front).public_orientation is PublicOrientation.STREET


# --------------------------------------------------------------- 3. the parti is shared

def test_a_brief_the_front_band_refuses_the_rear_band_refuses_for_the_same_reason():
    """E1's own ceiling, pinned: the two orientations share every sizing rule, so the rear band
    cannot plan where the parti itself cannot. This is why E1's reach is the band parti's reach."""
    _, _, generated = _generated(_NO_BAND_BRIEF, PublicOrientation.GARDEN)
    front = [c for c in generated.candidates
             if c.strategy is generator.ConceptStrategy.FRONT_PUBLIC_BAND]
    rear = [c for c in generated.candidates
            if c.strategy is generator.ConceptStrategy.REAR_PUBLIC_BAND]
    assert not front and not rear
    reasons = {r.strategy.value: (r.reason.value, r.detail) for r in generated.rejections}
    assert reasons["FRONT_PUBLIC_BAND"] == reasons["REAR_PUBLIC_BAND"]
