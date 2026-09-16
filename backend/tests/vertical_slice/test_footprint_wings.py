"""The footprint as a list of wings (`footprint.py`), and every stage that used to read one
rectangle now reading the wings — with the one-wing case byte-identical.

Two witnesses. The FROZEN SLICE proves nothing moved for a one-wing house: its garden, windows,
entrance and exposure are what they were (the frozen baseline test holds the numbers; this file
holds the shapes). The SPIKE'S F2 L-HOUSE — two wings meeting at a seam, solved by the production
Geometry Core — proves the generalisation is real: a seam side is not exterior, the crook is
accounted for as garden, C2 measures the wings and not the bounding box, and the entrance sits on
the street wing's wall. Nothing here makes the generator produce an L; that is a later feature.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import doors as doors_stage
from app.vertical_slice import furniture as furniture_stage
from app.vertical_slice import site as site_stage
from app.vertical_slice import validation as validation_stage
from app.vertical_slice import windows as windows_stage
from app.vertical_slice.design_output import assemble
from app.vertical_slice.footprint import (
    area_u,
    bounding_box,
    covers,
    remainder_within_bbox,
    subtract,
    wing_of,
    wing_on_street_line,
)
from app.vertical_slice.general_pipeline import _family_signature, _site_plan_for
from app.vertical_slice.geometry_adapter import envelope_sides
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
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
    u_to_m,
)
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.geometry_domain.walls import BoundaryContext


# ------------------------------------------------------------------ the helpers

def test_bounding_box_area_and_wing_lookup():
    bar, arm = Rect(0, 0, 160, 240), Rect(160, 0, 90, 170)
    assert bounding_box((bar,)) == bar
    assert bounding_box((bar, arm)) == Rect(0, 0, 250, 240)
    assert area_u((bar, arm)) == 160 * 240 + 90 * 170 < 250 * 240
    assert wing_of((bar, arm), Rect(170, 10, 40, 40)) == arm
    with pytest.raises(ValueError, match="lies in no wing"):
        wing_of((bar, arm), Rect(200, 200, 10, 10))       # the crook
    assert wing_on_street_line((bar, arm), 200, 0) == arm
    assert wing_on_street_line((bar, arm), 200, 5) is None
    with pytest.raises(ValueError):
        bounding_box(())


def test_subtract_is_exact_and_deterministic():
    box = Rect(0, 0, 10, 10)
    assert subtract(box, (box,)) == ()
    assert subtract(box, ()) == (box,)
    # A hole in the middle: four pieces, rows top to bottom, merged along each row.
    pieces = subtract(box, (Rect(3, 3, 4, 4),))
    assert pieces == (Rect(0, 0, 10, 3), Rect(0, 3, 3, 4), Rect(7, 3, 3, 4), Rect(0, 7, 10, 3))
    assert sum(p.w * p.h for p in pieces) == 100 - 16
    # The crook of an L is one rectangle.
    assert remainder_within_bbox((Rect(0, 0, 160, 240), Rect(160, 0, 90, 170))) == (Rect(160, 170, 90, 70),)
    assert remainder_within_bbox((box,)) == ()
    assert covers((Rect(0, 0, 5, 10), Rect(5, 0, 5, 10)), box)
    assert not covers((Rect(0, 0, 5, 10),), box)


def test_envelope_sides_read_the_rooms_own_wing_and_skip_declared_seams():
    bar, arm = Rect(0, 0, 160, 240), Rect(160, 0, 90, 170)
    bbox = bounding_box((bar, arm))
    # A room at the arm's west edge, against the seam. Its west side lies on ITS WING's edge, so
    # the wing reading alone would call it exterior; the declared seam is what says it is not —
    # the two facts together give the truth. (The bounding-box reading happens to agree here,
    # for the wrong reason: x=160 is simply not the box's edge.)
    room = Rect(160, 0, 90, 60)
    assert envelope_sides(room, bbox) == [Side.E, Side.N]
    assert envelope_sides(room, bbox, wings=(bar, arm)) == [Side.W, Side.E, Side.N]
    assert envelope_sides(room, bbox, wings=(bar, arm), seam_sides=frozenset({Side.W})) == [Side.E, Side.N]
    # A room at the bar's south-east corner, BELOW the arm: its east side is on the bar's edge
    # and faces the crook — genuinely exterior — which the bounding-box reading misses.
    below_arm = Rect(100, 170, 60, 70)
    assert envelope_sides(below_arm, bbox) == [Side.S]
    assert envelope_sides(below_arm, bbox, wings=(bar, arm)) == [Side.E, Side.S]


# ------------------------------------------------------------------ one wing: nothing moved

@pytest.fixture(scope="module")
def slice_result(tmp_path_factory):
    return run_demo(str(tmp_path_factory.mktemp("wings") / "house.png"))


def test_a_one_wing_design_reports_its_footprint_once_as_its_only_wing(slice_result):
    design = slice_result.design
    assert design.footprints_m == (design.footprint_m,)
    # The garden is the three bands plus the front strip, exactly as before — no crook region.
    assert [g.classification for g in design.garden] == ["GARDEN"] * len(design.garden)
    assert len(design.garden) == 4
    assert [g.region_id for g in design.garden] == ["garden_0", "garden_1", "garden_2", "garden_3"]


def test_one_wing_site_plan_defaults_its_wings_to_the_footprint():
    plan = Rect(0, 0, 400, 480)
    footprint = Rect(60, 110, 240, 284)
    site = site_stage.SitePlan(plan, footprint, (60, 110), (), site_stage.build_entrance(footprint, 180), ())
    assert site.wings == (footprint,)


# ------------------------------------------------------------------ two wings: the L is real

def _z(zid, role, lo, t, hi, short, aspect=2.5):
    return ZoneSpec(zid, (role,) if role is not ProgramRole.HALL else (role, ProgramRole.CIRCULATION),
                    lo, t, hi, short, aspect)


def _l_house(origin_x_u: int, origin_y_u: int) -> Fixture:
    """The spike's F2 L-house on production types, placed at a plot offset: wing A (bar) 8 x 12 m
    with the hall against the seam over a forced 8.5 m cut and the dining below; wing B (arm)
    4.5 x 8.5 m with every west side a seam."""
    zones = (
        _z("LIVING", ProgramRole.LIVING, 28, 34, 44, 3.6), _z("KITCHEN", ProgramRole.KITCHEN, 10, 13, 20, 2.4, 3.0),
        _z("HALL", ProgramRole.HALL, 9, 12, 22, 1.2, 8.0), _z("DINING", ProgramRole.DINING, 12, 20, 28, 2.6, 3.0),
        _z("MASTER", ProgramRole.MASTER_BEDROOM, 11, 14, 19, 3.0), _z("BEDROOM_1", ProgramRole.BEDROOM, 9, 12, 16, 2.8),
        _z("BATH", ProgramRole.BATHROOM, 4.5, 6.0, 9.0, 1.7, 3.0))
    L, ox, oy = Leaf, origin_x_u, origin_y_u
    wing_a = Wing("A", ox, oy, m_to_u(8.0), m_to_u(12.0),
                  Split(Cut.H, Split(Cut.V, Split(Cut.H, L("LIVING"), L("KITCHEN")), L("HALL")), L("DINING"),
                        m_to_u(8.5)),
                  seam_leaf_sides=(("HALL", Side.E),))
    wing_b = Wing("B", ox + m_to_u(8.0), oy, m_to_u(4.5), m_to_u(8.5),
                  Split(Cut.H, L("MASTER"), Split(Cut.H, L("BEDROOM_1"), L("BATH"))),
                  seam_leaf_sides=(("MASTER", Side.W), ("BEDROOM_1", Side.W), ("BATH", Side.W)))
    D, CO = ConnectionKind.DOOR, ConnectionKind.CASED_OPENING
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "LIVING", D), DesiredAccessEdge("HALL", "KITCHEN", D),
        DesiredAccessEdge("HALL", "DINING", D), DesiredAccessEdge("LIVING", "KITCHEN", CO, 1.4),
        DesiredAccessEdge("HALL", "MASTER", D), DesiredAccessEdge("HALL", "BEDROOM_1", D),
        DesiredAccessEdge("HALL", "BATH", D)))
    return Fixture("F2_L_HOUSE", (wing_a, wing_b), zones, access)


@pytest.fixture(scope="module")
def l_house():
    """The L realized through the generalised stages, the way `general_pipeline._realize` does it."""
    spec = ArchitecturalSpec(PlotSpec(20.0, 24.0), ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=1,
                                                              parking_spaces=1))
    fixture = _l_house(m_to_u(3.0), m_to_u(5.5))
    solve = solve_fixture(fixture)
    wings = tuple(w.rect() for w in fixture.wings)
    footprint = bounding_box(wings)
    resolved = doors_stage.resolve_entrance(fixture, solve.rects, footprint, wings)
    site = _site_plan_for(spec, footprint, (resolved[1], resolved[2]), wings)
    interior = doors_stage.generate_interior_doors(fixture, solve.rects)
    entrance = doors_stage.build_entrance_door(site.entrance, footprint, resolved[0], wings)
    windows = windows_stage.generate_windows(fixture, solve.rects, footprint, wings)
    furniture = furniture_stage.check_furniture_feasibility(fixture, solve.rects, solve.walls)
    report = validation_stage.validate(fixture, solve.rects, solve.walls, interior, entrance, windows,
                                       furniture, site)
    design = assemble(fixture, solve.rects, solve.walls, solve.wall_iterations, interior, entrance,
                      windows, furniture, site)
    return dict(fixture=fixture, solve=solve, wings=wings, footprint=footprint, site=site,
                entrance=entrance, resolved=resolved, windows=windows, report=report, design=design)


def test_the_l_house_footprint_is_two_wings_and_a_bounding_box(l_house):
    design = l_house["design"]
    assert len(design.footprints_m) == 2
    assert design.footprint_m == (3.0, 5.5, 12.5, 12.0)                       # the box
    assert design.footprints_m == ((3.0, 5.5, 8.0, 12.0), (11.0, 5.5, 4.5, 8.5))  # the wings
    assert design.gross_area_m2 == pytest.approx(8.0 * 12.0 + 4.5 * 8.5)       # wings, not box


def test_c2_measures_the_wings_so_the_crook_is_not_unassigned_interior(l_house):
    c2 = next(c for c in l_house["report"].checks if c.check_id == "C2")
    assert c2.passed, c2.detail


def test_the_crook_is_accounted_for_as_garden(l_house):
    site = l_house["site"]
    crook = Rect(m_to_u(11.0), m_to_u(5.5 + 8.5), m_to_u(4.5), m_to_u(3.5))
    crook_regions = [g for g in site.garden if g.rects == (crook,)]
    assert len(crook_regions) == 1
    assert crook_regions[0].classification is OutdoorClassification.GARDEN
    # The bands and the front strip are still drawn around the bounding box (four regions, as for
    # a one-wing house on this site) and the crook is the fifth, so the plot is fully accounted for.
    assert len(site.garden) == 5
    assert crook_regions[0].region_id == "garden_4"
    c12 = next(c for c in l_house["report"].checks if c.check_id == "C12")
    assert c12.passed


def test_a_seam_side_is_interior_and_the_wall_facing_the_crook_is_exterior(l_house):
    rooms = {r.zone_id: r for r in l_house["design"].rooms}
    # The hall's east side is the seam to the arm: not exterior, whatever the bounding box says.
    assert rooms["HALL"].wall_facts["E"].boundary_context is BoundaryContext.INTERIOR
    assert rooms["MASTER"].wall_facts["W"].boundary_context is BoundaryContext.INTERIOR
    # The dining room sits under the arm; its east wall faces the crook and IS exterior.
    assert rooms["DINING"].wall_facts["E"].boundary_context is BoundaryContext.EXTERIOR
    # The arm's own east wall is on the envelope.
    assert rooms["MASTER"].wall_facts["E"].boundary_context is BoundaryContext.EXTERIOR


def test_no_window_is_placed_on_a_seam(l_house):
    seams = windows_stage.seam_sides_of(l_house["fixture"])
    assert seams == {"HALL": frozenset({Side.E}), "MASTER": frozenset({Side.W}),
                     "BEDROOM_1": frozenset({Side.W}), "BATH": frozenset({Side.W})}
    for window in l_house["windows"]:
        assert window.side not in seams.get(window.zone_id, frozenset()), window
    # The master has a real east wall and gets its window there, not on the seam.
    master = next(w for w in l_house["windows"] if w.zone_id == "MASTER")
    assert master.placeable and master.side is Side.E


def test_the_entrance_sits_on_a_street_wing_wall_and_reaches_every_room(l_house):
    zone, low, high = l_house["resolved"]
    assert zone == "HALL"                # the hall fronts the street in F2 and outranks the living room
    wing = wing_of(l_house["wings"], l_house["solve"].rects[zone])
    assert wing == l_house["wings"][0]   # the bar, not the arm
    # Corner clearance measured against the WING's street wall, not the bounding box.
    assert low >= wing.x + m_to_u(1.0) and high <= wing.x2 - m_to_u(1.0)
    assert l_house["entrance"].placeable
    assert l_house["entrance"].shared_length_m == wing.w
    c5 = next(c for c in l_house["report"].checks if c.check_id == "C5")
    assert c5.passed, c5.detail           # the arm's rooms are reached across the seam
    c13 = next(c for c in l_house["report"].checks if c.check_id == "C13")
    assert c13.passed, c13.detail


def test_family_signature_joins_one_tree_per_wing(l_house):
    signature = _family_signature(l_house["fixture"], "SPINE_PUBLIC_PRIVATE")
    assert signature.count("+") == 1
    # And a one-wing fixture's signature has no join — the string it always was.
    one_wing = Fixture("ONE", (l_house["fixture"].wings[0],), l_house["fixture"].zones,
                       DesiredAccessTopology(()))
    assert "+" not in _family_signature(one_wing, "SPINE_PUBLIC_PRIVATE")
