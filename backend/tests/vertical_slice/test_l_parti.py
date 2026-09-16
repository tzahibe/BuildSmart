"""The L parti — two connected rectangular wings with one declared seam — and C22, the spike's
seam proof P9 in production.

What is held here: the parti fires only for two ADJACENT adapter candidates and never for one
wing; the seam geometry is classified honestly (arm east/west, flush front/rear, floating trimmed;
north/south, overhanging and rectangle-forming pairs refused with their reasons); the plans it
produces are two wings joined by REALIZED doors across the seam, with no exterior or window
semantics on it, every room inside its wing, and every existing check passing; C22 catches each
way a seam can be a lie; and without a target the L never displaces the plan a brief already had.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import concept_generator as cg
from app.vertical_slice import doors as doors_stage
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import l_parti
from app.vertical_slice import validation as validation_stage
from app.vertical_slice import windows as windows_stage
from app.vertical_slice.footprint import wing_of
from app.vertical_slice.general_pipeline import _family_signature, _realize, run_general_from_site
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    leaves_of,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    OutdoorClassification,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.l_parti import ArmEnd, ArmSide, seam_geometry
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.windows import Window

L = cg.ConceptStrategy.MULTI_WING_SPLIT


# ------------------------------------------------------------------ seam geometry

def test_seam_geometry_classifies_the_arm_and_trims_a_floating_one():
    primary = Rect(60, 110, 260, 320)                      # 13 x 16 m at (3, 5.5)
    rear = seam_geometry(primary, Rect(320, 240, 100, 190))   # arm east, flush with the rear
    assert (rear.side, rear.end) == (ArmSide.EAST, ArmEnd.REAR)
    assert rear.primary == primary and rear.hall_side is Side.E and rear.arm_seam_side is Side.W
    front = seam_geometry(primary, Rect(320, 110, 100, 200))  # arm east, flush with the street
    assert (front.side, front.end) == (ArmSide.EAST, ArmEnd.FRONT)
    west = seam_geometry(primary, Rect(-40, 240, 100, 190))   # arm west
    assert (west.side, west.end) == (ArmSide.WEST, ArmEnd.REAR)
    assert west.hall_side is Side.W and west.arm_seam_side is Side.E
    # Floating: the primary's rear is trimmed to the arm's rear, so the arm becomes rear-flush.
    floating = seam_geometry(primary, Rect(320, 200, 100, 150))
    assert floating.end is ArmEnd.REAR
    assert floating.primary == Rect(60, 110, 260, 240)


def test_seam_geometry_refuses_what_this_parti_does_not_author():
    primary = Rect(60, 110, 260, 320)
    north = seam_geometry(primary, Rect(60, 10, 100, 100))      # arm north of the primary
    assert north.reason is cg.RejectionReason.NO_SEAM_ALIGNMENT and "north or south" in north.detail
    apart = seam_geometry(primary, Rect(400, 110, 100, 100))
    assert "share no boundary" in apart.detail
    over = seam_geometry(primary, Rect(320, 300, 100, 200))     # arm past the primary's rear
    assert "extends past" in over.detail
    same = seam_geometry(primary, Rect(320, 110, 100, 320))     # same depth: a rectangle
    assert "not an L" in same.detail


def test_only_two_adjacent_candidates_reach_the_parti():
    one = adapt(build_buildable_region(F.rectangular_site())) if hasattr(F, "rectangular_site") else None
    if one is not None:
        assert cg._two_wing_pair(list(one.candidates)) is None
    two = adapt(build_buildable_region(F.l_shaped_site()))
    pair = cg._two_wing_pair(list(two.candidates))
    assert isinstance(pair, tuple) and pair[0].order == 0 and pair[1].order == 1
    # Two rectangles that do not touch are declined, with the reason, not planned across.
    from dataclasses import replace
    apart = [replace(two.candidates[0], adjacent_orders=()),
             replace(two.candidates[1], rect=Rect(500, 500, 60, 60), adjacent_orders=())]
    rejection = cg._two_wing_pair(apart)
    assert rejection.reason is cg.RejectionReason.NO_SEAM_ALIGNMENT


# ------------------------------------------------------------------ real L plans

def _l_plans(site, plot, program):
    """Every L candidate the generator offers for this site and programme, realized."""
    buildable = build_buildable_region(site)
    adapted = adapt(buildable)
    spec = ArchitecturalSpec(PlotSpec(*plot), program)
    generated = cg.generate_concepts(spec, list(adapted.candidates))
    out = []
    for index, candidate in enumerate(generated.candidates):
        if candidate.strategy is not L:
            continue
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        out.append((candidate, _realize(spec, buildable, site, candidate, index, solve, ())))
    return generated, out


OPEN_3BR = ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=True, wet_rooms=2,
                       parking_spaces=2, target_built_area_m2=200)
CLOSED_3BR = ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=False, wet_rooms=2,
                         parking_spaces=2, target_built_area_m2=200)


@pytest.fixture(scope="module")
def deep_open():
    return _l_plans(F.l_shaped_site_deep_primary(), (24.0, 32.0), OPEN_3BR)


@pytest.fixture(scope="module")
def e1_closed():
    return _l_plans(F.l_shaped_site(), (24.0, 28.0), CLOSED_3BR)


def test_the_l_is_offered_as_two_wings_with_one_declared_seam(deep_open):
    generated, plans = deep_open
    assert plans, "the deep-primary L site with a 3BR open-plan programme must produce an L"
    for candidate, _ in plans:
        fixture = candidate.concept.fixture
        assert candidate.strategy is L and candidate.wing_orders == (0, 1)
        assert len(fixture.wings) == 2
        primary, arm = fixture.wings
        assert primary.seam_leaf_sides == (("HALL", Side.E),)
        assert arm.seam_leaf_sides and all(side is Side.W for _, side in arm.seam_leaf_sides)
        # Every arm row's seam-facing member is declared; nothing else in the arm is.
        assert len(arm.seam_leaf_sides) == len(set(arm.seam_leaf_sides))
        assert "+" in _family_signature(fixture, candidate.strategy)


def test_every_solved_l_validates_including_c22(deep_open, e1_closed):
    for generated, plans in (deep_open, e1_closed):
        assert plans
        for candidate, plan in plans:
            assert plan.ok, [c.detail for c in plan.validation.failures()]
            checks = {c.check_id: c for c in plan.validation.checks}
            assert checks["C22"].passed, checks["C22"].detail
            assert checks["C17"].passed and checks["C20"].passed and checks["C21"].passed


def test_the_wings_are_one_house_joined_through_the_seam(deep_open):
    _, plans = deep_open
    candidate, plan = plans[0]
    fixture = candidate.concept.fixture
    design = plan.design
    arm_zones = set(leaves_of(fixture.wings[1].tree))
    # Every arm room has a REALIZED door from the hall, across the seam — not a touch.
    seam_doors = [d for d in design.interior_doors if d.placeable and "HALL" in (d.a, d.b)
                  and ({d.a, d.b} - {"HALL"}) <= arm_zones]
    arm_entered = {(d.a if d.b == "HALL" else d.b) for d in seam_doors}
    ensuites = {z for z in arm_zones if fixture.zone(z).primary_role is ProgramRole.BATHROOM
                and any(e.a != "HALL" and e.b == z for e in fixture.access.edges)}
    assert arm_entered == arm_zones - ensuites
    # The seam carries no exterior or window semantics on either wing.
    rooms = {r.zone_id: r for r in design.rooms}
    assert rooms["HALL"].wall_facts["E"].boundary_context.value == "INTERIOR"
    assert rooms["HALL"].walls["E"] != "EXTERIOR"
    for zone_id, side in fixture.wings[1].seam_leaf_sides:
        assert rooms[zone_id].wall_facts[side.value].boundary_context.value == "INTERIOR"
        assert not any(w.zone_id == zone_id and w.side == side.value and w.width_m > 0
                       for w in design.windows)
    # The footprint is two wings and the crook is accounted for as garden.
    assert len(design.footprints_m) == 2
    assert design.gross_area_m2 == pytest.approx(sum(w * h for _, _, w, h in design.footprints_m))
    assert design.gross_area_m2 < design.footprint_m[2] * design.footprint_m[3]
    assert all(g.classification == OutdoorClassification.GARDEN.value for g in design.garden)


def test_the_arm_is_the_private_wing_and_the_band_holds_the_public_rooms(deep_open):
    _, plans = deep_open
    for candidate, plan in plans:
        fixture = candidate.concept.fixture
        arm_roles = {fixture.zone(z).primary_role for z in leaves_of(fixture.wings[1].tree)}
        assert not arm_roles & {ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN, ProgramRole.HALL}
        assert arm_roles & {ProgramRole.MASTER_BEDROOM, ProgramRole.BEDROOM}
        # Open plan: the whole LDK group stays together in the primary, structurally open.
        assert fixture.open_groups and set(fixture.open_groups[0]) == {"LIVING", "DINING", "KITCHEN"}
        assert plan.validation.checks and next(c for c in plan.validation.checks if c.check_id == "C13").passed


def test_a_closed_plan_may_put_the_kitchen_beside_the_hall(e1_closed):
    generated, plans = e1_closed
    rationales = [c.rationale for c, _ in plans]
    assert any("kitchen beside the hall" in r for r in rationales)
    # ...and that kitchen is entered from the hall by its own door, realized.
    candidate, plan = next((c, p) for c, p in plans if "kitchen beside the hall" in c.rationale)
    kitchen_doors = [d for d in plan.design.interior_doors
                     if {d.a, d.b} == {"HALL", "KITCHEN"} and d.placeable]
    assert kitchen_doors and kitchen_doors[0].kind == "DOOR"


def test_the_short_arm_overflows_into_the_column_and_says_so(e1_closed):
    """The E1 arm is 9.5 m; a 3-bedroom private wing needs 11.2. Some rooms sit beside the hall
    instead, and the rationale names them — never a silent drop."""
    generated, plans = e1_closed
    assert any("beside the hall — the arm holds" in c.rationale for c, _ in plans)
    for candidate, plan in plans:
        placed = {r.zone_id for r in plan.design.rooms}
        assert {"MASTER", "BEDROOM_1", "BEDROOM_2", "SAFE_ROOM", "BATH_1", "BATH_2", "LIVING",
                "KITCHEN", "HALL"} <= placed


def test_refusals_name_the_binding_wing():
    """A programme the arm cannot hold and the column cannot fill is refused with the wing named,
    not planned badly: 4 bedrooms with a target above capacity carries FLEX, which the band does
    not combine with."""
    generated, plans = _l_plans(F.l_shaped_site(), (24.0, 28.0),
                                ProgramSpec(bedrooms=4, safe_room=True, open_plan_living=False,
                                            wet_rooms=3, parking_spaces=2, target_built_area_m2=240))
    assert not plans
    rejection = next(r for r in generated.rejections if r.strategy is L)
    assert "FLEX" in rejection.detail


# ------------------------------------------------------------------ the one-wing world is untouched

def test_a_single_candidate_never_reaches_the_l_parti():
    """The demo path plans one rectangle: no pair, no L candidate, no L rejection — nothing new."""
    buildable = build_buildable_region(F.l_shaped_site())
    adapted = adapt(buildable)
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0), OPEN_3BR)
    generated = cg.generate_concepts(spec, [adapted.candidates[0]])
    assert not any(c.strategy is L for c in generated.candidates)
    assert not any(r.strategy is L for r in generated.rejections)


def test_without_a_target_the_l_comes_after_every_one_wing_forced_tree():
    """Insertion order IS the ranking without a target (the site-driven baselines). The L is
    moved to the very end, so the plan such a brief already had is still first."""
    adapted = adapt(build_buildable_region(F.l_shaped_site()))
    spec = ArchitecturalSpec(PlotSpec(24.0, 28.0), ProgramSpec(bedrooms=3, safe_room=True,
                                                               open_plan_living=False, wet_rooms=2))
    generated = cg.generate_concepts(spec, list(adapted.candidates))
    l_indices = [i for i, c in enumerate(generated.candidates) if c.strategy is L]
    other_indices = [i for i, c in enumerate(generated.candidates) if c.strategy is not L]
    assert l_indices and other_indices
    # After EVERY one-wing candidate — forced trees, twins, tier 2 and last-resort hubs alike.
    assert min(l_indices) > max(other_indices)


def test_the_l_site_baseline_primary_is_unchanged():
    """`test_general_pipeline`'s B_l_shape case (no target): the same one-wing plan as before the
    parti existed — 10 rooms, a single wing, the double-loaded spine."""
    result = run_general_from_site(F.l_shaped_site())
    assert result.ok
    assert result.concept.strategy is cg.ConceptStrategy.SPINE_DOUBLE_LOADED
    assert len(result.design.footprints_m) == 1
    assert result.design.gross_area_m2 == pytest.approx(161.245)
    assert result.metrics.wings_used == 1


# ------------------------------------------------------------------ C22: every way a seam can lie

def _z(zid, role, lo, t, hi, short, aspect=2.5):
    roles = (role, ProgramRole.CIRCULATION) if role is ProgramRole.HALL else (role,)
    return ZoneSpec(zid, roles, lo, t, hi, short, aspect)


ZONES = (
    _z("LIVING", ProgramRole.LIVING, 28, 34, 44, 3.6), _z("KITCHEN", ProgramRole.KITCHEN, 10, 13, 20, 2.4, 3.0),
    _z("HALL", ProgramRole.HALL, 9, 12, 22, 1.2, 8.0), _z("DINING", ProgramRole.DINING, 12, 20, 28, 2.6, 3.0),
    _z("MASTER", ProgramRole.MASTER_BEDROOM, 11, 14, 19, 3.0), _z("BEDROOM_1", ProgramRole.BEDROOM, 9, 12, 16, 2.8),
    _z("BATH", ProgramRole.BATHROOM, 4.5, 6.0, 9.0, 1.7, 3.0))
D, CO = ConnectionKind.DOOR, ConnectionKind.CASED_OPENING
ACCESS = DesiredAccessTopology((
    DesiredAccessEdge("HALL", "LIVING", D), DesiredAccessEdge("HALL", "KITCHEN", D),
    DesiredAccessEdge("HALL", "DINING", D), DesiredAccessEdge("LIVING", "KITCHEN", CO, 1.4),
    DesiredAccessEdge("HALL", "MASTER", D), DesiredAccessEdge("HALL", "BEDROOM_1", D),
    DesiredAccessEdge("HALL", "BATH", D)))


def _f2(*, primary_seams=(("HALL", Side.E),),
        arm_seams=(("MASTER", Side.W), ("BEDROOM_1", Side.W), ("BATH", Side.W)),
        hall_len_m=8.5, access=ACCESS) -> Fixture:
    """The spike's F2 L-house at a plot offset, with the seam declarations under test. The arm
    is always 8.5 m; `hall_len_m` is where the primary's forced cut puts the hall's end."""
    ox, oy = m_to_u(3.0), m_to_u(5.5)
    wing_a = Wing("A", ox, oy, m_to_u(8.0), m_to_u(12.0),
                  Split(Cut.H, Split(Cut.V, Split(Cut.H, Leaf("LIVING"), Leaf("KITCHEN")), Leaf("HALL")),
                        Leaf("DINING"), m_to_u(hall_len_m)), seam_leaf_sides=primary_seams)
    wing_b = Wing("B", ox + m_to_u(8.0), oy, m_to_u(4.5), m_to_u(8.5),
                  Split(Cut.H, Leaf("MASTER"), Split(Cut.H, Leaf("BEDROOM_1"), Leaf("BATH"))),
                  seam_leaf_sides=arm_seams)
    return Fixture("F2", (wing_a, wing_b), ZONES, access)


def _c22(fixture: Fixture, *, windows=None, doors=None):
    from app.vertical_slice import furniture as furniture_stage
    from app.vertical_slice.footprint import bounding_box
    from app.vertical_slice.general_pipeline import _site_plan_for
    solve = solve_fixture(fixture)
    wings = tuple(w.rect() for w in fixture.wings)
    footprint = bounding_box(wings)
    spec = ArchitecturalSpec(PlotSpec(20.0, 24.0), ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=1,
                                                              parking_spaces=1))
    resolved = doors_stage.resolve_entrance(fixture, solve.rects, footprint, wings)
    site = _site_plan_for(spec, footprint, (resolved[1], resolved[2]), wings)
    interior = doors if doors is not None else doors_stage.generate_interior_doors(fixture, solve.rects)
    entrance = doors_stage.build_entrance_door(site.entrance, footprint, resolved[0], wings)
    wins = windows if windows is not None else windows_stage.generate_windows(fixture, solve.rects, footprint, wings)
    report = validation_stage.validate(fixture, solve.rects, solve.walls, interior, entrance, wins,
                                       furniture_stage.check_furniture_feasibility(fixture, solve.rects, solve.walls),
                                       site)
    return next(c for c in report.checks if c.check_id == "C22"), solve


def test_c22_holds_on_the_spikes_f2_house():
    check, _ = _c22(_f2())
    assert check.passed, check.detail
    assert "4 declared seam sides" in check.detail


def test_c22_catches_an_undeclared_abutment():
    """An arm room touching the hall without a declared seam would be typed EXTERIOR against a
    room — the L2 defect. C22 names the side."""
    check, _ = _c22(_f2(arm_seams=(("MASTER", Side.W), ("BEDROOM_1", Side.W))))   # BATH undeclared
    assert not check.passed
    assert "BATH.W abuts the other wing" in check.detail and "not declared" in check.detail


def test_c22_catches_a_partial_seam():
    """A hall longer than the arm: the hall's declared seam side is only partly abutted, so its
    wall type is ambiguous — exactly what the forced cut at the seam's length exists to prevent."""
    check, _ = _c22(_f2(hall_len_m=9.0))
    assert not check.passed
    assert "HALL.E" in check.detail and "PARTIAL seam" in check.detail


def test_c22_catches_a_window_on_the_seam():
    fixture = _f2()
    _, solve = _c22(fixture)
    rect = solve.rects["MASTER"]
    fake = [Window("MASTER", Side.W, 1.2, (rect.x, rect.y + rect.h // 2), True)]
    check, _ = _c22(fixture, windows=fake)
    assert not check.passed and "MASTER.W is a seam carrying a window" in check.detail


def test_c22_catches_two_buildings_that_only_touch():
    """Remove every door across the seam: the wings touch but nothing joins them."""
    access = DesiredAccessTopology(tuple(e for e in ACCESS.edges
                                         if {e.a, e.b} & {"MASTER", "BEDROOM_1", "BATH"} == set()))
    check, _ = _c22(_f2(access=access))
    assert not check.passed and "two buildings, not one house" in check.detail


def test_c22_is_not_emitted_for_a_one_wing_fixture():
    from app.vertical_slice.pipeline import run_demo
    import tempfile, os
    result = run_demo(os.path.join(tempfile.mkdtemp(), "h.png"))
    assert "C22" not in {c.check_id for c in result.validation.checks}
