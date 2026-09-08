"""General Concept Generator: programmes, allocation, topology and bounded candidates."""
from __future__ import annotations

import pytest

from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.concept_generator import (
    ConceptStrategy,
    RejectionReason,
    ZoneGroup,
    build_room_program,
    generate_concepts,
    minimum_footprint_width_m,
    target_gross_area_m2,
)
from app.vertical_slice.general_pipeline import run_general, run_general_from_site
from app.vertical_slice.geometry_core.model import ConnectionKind, ProgramRole
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

PROGRAMS = {
    "2BR": ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=1),
    "3BR": ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2),
    "3BR_SAFE": ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2),
    "3BR_SAFE_3WET": ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=3),
    "2BR_SAFE": ProgramSpec(bedrooms=2, safe_room=True, wet_rooms=1),
}


def _spec(program: ProgramSpec) -> ArchitecturalSpec:
    return ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=program)


# ------------------------------------------------------------------ programme generation

@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_program_is_derived_from_the_spec_not_a_fixed_room_list(name):
    program = PROGRAMS[name]
    rooms = build_room_program(_spec(program))
    ids = [r.zone_id for r in rooms]
    bedrooms = [r for r in rooms if r.role in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)]
    baths = [r for r in rooms if r.role is ProgramRole.BATHROOM]
    assert len(bedrooms) == program.bedrooms
    assert len(baths) == program.wet_rooms
    assert ("SAFE_ROOM" in ids) is program.safe_room
    assert "HALL" in ids


def test_open_plan_flag_changes_the_public_zones():
    with_open = build_room_program(_spec(ProgramSpec(open_plan_living=True)))
    without = build_room_program(_spec(ProgramSpec(open_plan_living=False)))
    assert {r.zone_id for r in with_open if r.group is ZoneGroup.PUBLIC} == {
        "LIVING", "DINING", "KITCHEN"}
    assert {r.zone_id for r in without if r.group is ZoneGroup.PUBLIC} == {"LIVING", "KITCHEN"}


def test_first_wet_room_becomes_an_ensuite_only_when_there_are_two_or_more():
    one = build_room_program(_spec(ProgramSpec(wet_rooms=1)))
    two = build_room_program(_spec(ProgramSpec(wet_rooms=2)))
    assert all(r.entered_from is None for r in one)
    assert any(r.entered_from == "MASTER" for r in two)


def test_bigger_programmes_need_more_area_and_more_width():
    small = build_room_program(_spec(PROGRAMS["2BR"]))
    big = build_room_program(_spec(PROGRAMS["3BR_SAFE_3WET"]))
    assert target_gross_area_m2(big) > target_gross_area_m2(small)
    assert minimum_footprint_width_m(big) >= minimum_footprint_width_m(small)


# ------------------------------------------------------------------ candidate generation

def _candidates(program: ProgramSpec, site=None):
    site = site or F.exact_rectangle()
    adapter = adapt(build_buildable_region(site))
    return generate_concepts(_spec(program), list(adapter.candidates))


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_generator_produces_a_bounded_candidate_set(name):
    result = _candidates(PROGRAMS[name])
    assert result.any, [r.detail for r in result.rejections]
    assert 1 <= len(result.candidates) <= 6


def test_candidates_are_deterministic():
    a = _candidates(PROGRAMS["3BR_SAFE"])
    b = _candidates(PROGRAMS["3BR_SAFE"])
    assert [c.strategy for c in a.candidates] == [c.strategy for c in b.candidates]
    assert [c.used_area_m2 for c in a.candidates] == [c.used_area_m2 for c in b.candidates]


def test_rejections_carry_structured_reasons():
    """4BR used to be rejected by every strategy pre-solver. The front-band parti now passes the
    pre-check for it (the rear sizes itself and the public band absorbs the surplus depth), so
    candidates ARE produced — but the other strategies still decline, with structured reasons."""
    result = _candidates(ProgramSpec(bedrooms=4, safe_room=True, wet_rooms=3))
    assert result.rejections
    for rejection in result.rejections:
        assert isinstance(rejection.reason, RejectionReason)
        assert rejection.detail


def test_four_bedroom_programme_still_does_not_complete_end_to_end():
    """The remaining headline limit, pinned so it cannot regress silently in either direction.
    The front-band concept is generated and pre-checked, but Geometry Core cannot realize its
    forced cuts, so the run ends without a design."""
    result = run_general_from_site(
        F.exact_rectangle(), plot_size_m=(20.0, 24.0),
        program=ProgramSpec(bedrooms=4, safe_room=True, wet_rooms=3))
    assert result.design is None
    assert result.metrics.concept_candidates_generated >= 1
    assert result.metrics.solver_attempts >= 1


def test_front_band_parti_is_generated_and_can_win():
    """The new parti is a real strategy, not dead code: it wins the 2BR programme outright."""
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0),
                                   program=PROGRAMS["2BR"])
    assert result.design is not None
    assert result.concept.strategy is ConceptStrategy.FRONT_PUBLIC_BAND
    assert result.validation.ok


def test_shared_row_members_each_clear_their_minimum_width():
    """Regression for the ensuite bug: splitting a shared row by area alone gave a bathroom
    30% of a 5 m column — 1.39 m, under its 1.6 m minimum. Minimums are allocated first now."""
    from app.vertical_slice.concept_generator import _row_widths, build_room_program

    rooms = build_room_program(_spec(PROGRAMS["3BR_SAFE"]))
    master = next(r for r in rooms if r.zone_id == "MASTER")
    ensuite = next(r for r in rooms if r.entered_from == "MASTER")
    widths = _row_widths([master, ensuite], 5.0)
    assert widths is not None
    assert widths[0] >= master.template.min_short_side_m
    assert widths[1] >= ensuite.template.min_short_side_m
    assert sum(widths) == pytest.approx(5.0)
    assert _row_widths([master, ensuite], 3.0) is None  # genuinely too narrow


# ------------------------------------------------------------------ topology

@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_every_private_room_is_entered_from_circulation_or_its_own_bedroom(name):
    result = _candidates(PROGRAMS[name])
    concept = result.candidates[0].concept
    rooms = {r.zone_id: r for r in result.program}
    for edge in concept.fixture.access.edges:
        if edge.kind is not ConnectionKind.DOOR:
            continue
        room = rooms.get(edge.b)
        if room is None or room.group not in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE):
            continue
        assert edge.a.startswith("HALL") or edge.a == room.entered_from


def test_safe_room_is_reached_directly_from_circulation():
    result = _candidates(PROGRAMS["3BR_SAFE"])
    concept = result.candidates[0].concept
    edges = [e for e in concept.fixture.access.edges if e.b == "SAFE_ROOM" or e.a == "SAFE_ROOM"]
    assert edges
    assert all(e.a.startswith("HALL") for e in edges)


def test_open_plan_zones_are_one_open_group_with_no_doors_between_them():
    result = _candidates(PROGRAMS["3BR_SAFE"])
    concept = result.candidates[0].concept
    groups = [set(g) for g in concept.fixture.open_groups]
    assert {"LIVING", "DINING", "KITCHEN"} in groups
    doors = {frozenset((e.a, e.b)) for e in concept.fixture.access.edges
             if e.kind is ConnectionKind.DOOR}
    assert frozenset(("LIVING", "DINING")) not in doors
    assert frozenset(("DINING", "KITCHEN")) not in doors


def test_topology_does_not_depend_on_the_wing_rectangle():
    """Topology before dimensions: the same programme on two different safe geometries must
    produce the same access graph, even though the rectangles differ."""
    a = _candidates(PROGRAMS["3BR_SAFE"], F.exact_rectangle())
    b = _candidates(PROGRAMS["3BR_SAFE"], F.rectangular_obstacle_site())
    def graph(result):
        return {(e.a, e.b, e.kind) for e in result.candidates[0].concept.fixture.access.edges}
    assert graph(a) == graph(b)


# ------------------------------------------------------------------ wings

def test_a_second_wing_is_considered_and_declined_with_a_reason_never_ignored():
    result = _candidates(PROGRAMS["3BR_SAFE"], F.l_shaped_site())
    multi = [r for r in result.rejections if r.strategy is ConceptStrategy.MULTI_WING_SPLIT]
    assert multi, "the L-shape's second wing must be evaluated"
    assert multi[0].reason in (RejectionReason.CIRCULATION_WOULD_CROSS_PRIVATE,
                               RejectionReason.NO_SEAM_ALIGNMENT)
    assert multi[0].wing_orders == (0, 1)
    assert "wing 1" in multi[0].detail


# ------------------------------------------------------------------ end to end

@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_each_programme_runs_end_to_end_on_a_rectangle(name):
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0),
                                   program=PROGRAMS[name])
    assert result.design is not None, result.metrics.rejection_reasons
    assert result.validation.ok, [c.detail for c in result.validation.failures()]
    assert result.safety.ok


GEOMETRIES = {
    "L_shape": lambda: run_general_from_site(F.l_shaped_site()),
    "curved_facade": lambda: run_general(F.concave_facade()),
    "obstacle": lambda: run_general_from_site(F.rectangular_obstacle_site()),
    "disconnected": lambda: run_general(F.disconnected_components()),
}


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_each_geometry_runs_end_to_end(name):
    result = GEOMETRIES[name]()
    assert result.design is not None, result.metrics.rejection_reasons
    assert result.validation.ok, [c.detail for c in result.validation.failures()]
    assert result.safety.rooms_inside_buildable
    assert result.safety.rooms_clear_of_exclusions


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_open_plan_ldk_is_physically_open_not_merely_declared(name):
    """Regression for the defect the realized-connectivity invariant caught: the declared
    open-plan group used to be three walled rooms with no doors between them, because the group
    was not a whole subtree. Geometry-derived open interfaces now realize it."""
    result = GEOMETRIES[name]()
    rooms = {r.zone_id: r for r in result.design.rooms}
    assert rooms["LIVING"].walls["S"] == "OPEN"
    assert rooms["DINING"].walls["N"] == "OPEN"
    assert rooms["DINING"].walls["S"] == "OPEN"
    assert rooms["KITCHEN"].walls["N"] == "OPEN"
    c13 = next(c for c in result.validation.checks if c.check_id == "C13")
    assert c13.passed, c13.detail


@pytest.mark.parametrize("name", sorted(GEOMETRIES))
def test_metrics_are_reported(name):
    metrics = GEOMETRIES[name]().metrics
    assert metrics.concept_candidates_generated >= 1
    assert metrics.solver_attempts >= 1
    assert metrics.first_valid_candidate_index is not None
    assert metrics.latency_ms > 0
    assert metrics.room_count > 0
    assert metrics.wing_count_offered >= 1
