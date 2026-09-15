"""Hard room-area maxima (Phase 1 of the room-size work) — each layer that holds them.

The defect: room area was never a decision in the column partis. A column runs the footprint's
full depth, a row its column's full width, and `_row_depths` split the column's spare depth by
elasticity with no ceiling — so a bathroom alone in a rear column took the whole 11.6 m (62 m2
against 12) and a safe room (elasticity 0, kept in the pool by a 0.15 weight floor) reached 30 m2.
`_zone_spec` then centred the ZoneSpec on the rectangle it had just planned (0.6-1.6x), so C3
could not fail on area by construction. Measured over the demo's programmes and outlines: 56 % of
plans had a room past its maximum.

Three layers now hold the line, each tested on its own:

  1. `_distribute_column_surplus` caps every row at the depth where its first member reaches its
     maximum, redirects the residue to rows with headroom, gives a zero-elasticity row nothing,
     and refuses the seam when the column cannot absorb its depth;
  2. `_zone_spec` caps `net_area_max_m2` at the template's maximum and `_specs_within_maxima`
     refuses a candidate planned above it;
  3. validation C21 measures the realized room against `ROOM_TEMPLATES` directly, never the
     ZoneSpec, so a future sizing path that relaxes its own spec still cannot pass.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import concept_generator as cg
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import site as site_stage
from app.vertical_slice.concept_generator import (
    ROOM_TEMPLATES,
    RejectionReason,
    _distribute_column_surplus,
    _row_depth_ceiling_m,
    _row_depths,
    _specs_within_maxima,
    _zone_spec,
)
from app.vertical_slice.doors import build_entrance_door, generate_interior_doors
from app.vertical_slice.general_pipeline import run_general_from_site
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Rect,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.safe_adapter import AdapterOutcome
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import validate


def _room(role: ProgramRole, zone_id: str | None = None):
    group = cg.ZoneGroup.PUBLIC if role in (ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN) \
        else cg.ZoneGroup.SERVICE
    return cg.ProgramRoom(zone_id or role.value, role, group, ROOM_TEMPLATES[role], None)


def _net_area(room, net_width: float, depth: float) -> float:
    return net_width * (depth - cg._EDGE_INSET_ALLOWANCE_M / 2)


# ------------------------------------------------------------------ 1. the distribution

def test_surplus_stops_at_each_rows_maximum_and_moves_on():
    """A 5.2 m column, 12 m deep: bedroom + bathroom + safe room. The bathroom (12 m2) and the
    safe room (14 m2, elasticity 0) cannot take 12 m between them; what they cannot take goes to
    the bedroom up to ITS ceiling, and everything lands inside its maximum."""
    bed, bath, safe = _room(ProgramRole.BEDROOM), _room(ProgramRole.BATHROOM), _room(ProgramRole.SAFE_ROOM)
    rows = [[bed], [bath], [safe]]
    net_w = 4.0
    depths, failure = _row_depths(rows, {"BEDROOM": 10.5, "BATHROOM": 6.5, "SAFE_ROOM": 10.5},
                                  net_w, 9.0)
    assert failure is None, failure
    assert sum(depths) == pytest.approx(9.0)
    for row, d in zip(rows, depths):
        assert _net_area(row[0], net_w, d) <= row[0].template.max_area_m2 + 1e-6, (row[0].zone_id, d)
        assert d <= _row_depth_ceiling_m(row, net_w, d) + 1e-9


def test_a_zero_elasticity_row_receives_no_surplus():
    """The safe room used to grow through the 0.15 weight floor. It now sits at its own need."""
    bed, safe = _room(ProgramRole.BEDROOM), _room(ProgramRole.SAFE_ROOM)
    wanted = [3.0, 3.0]
    depths, failure = _distribute_column_surplus([[bed], [safe]], wanted, 3.5, 6.9, "column")
    assert failure is None, failure
    assert depths[1] == pytest.approx(3.0)
    assert depths[0] == pytest.approx(3.9)
    # One grid step more than the bedroom can take is a refusal, not a step onto the safe room.
    depths, failure = _distribute_column_surplus([[bed], [safe]], wanted, 3.5, 7.0, "column")
    assert depths is None and failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA


def test_a_column_that_cannot_absorb_its_depth_refuses_the_seam():
    """The 62 m2 bathroom: one wet room alone in a 5.35 m column, 11.6 m deep. Refused with the
    area reason and the row's ceiling in the text, never stretched."""
    bath = _room(ProgramRole.BATHROOM, "BATH_2")
    depths, failure = _row_depths([[bath]], {"BATH_2": 6.5}, 5.15, 11.6, "rear east column")
    assert depths is None
    assert failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA
    assert "BATH_2" in failure.detail and "12 m2" in failure.detail


def test_residue_from_grid_rounding_never_lands_on_a_row_at_its_ceiling():
    """Every depth is on the 5 cm grid and the column tiles exactly; the centimetres the rounding
    leaves go to a row with headroom, so no row ends a grid step past its ceiling."""
    bed1, bed2, bath = _room(ProgramRole.BEDROOM, "B1"), _room(ProgramRole.BEDROOM, "B2"), _room(ProgramRole.BATHROOM)
    rows = [[bed1], [bed2], [bath]]
    net_w = 4.3
    depths, failure = _row_depths(rows, {"B1": 10.5, "B2": 10.5, "BATHROOM": 6.5}, net_w, 9.15)
    assert failure is None, failure
    assert sum(depths) == pytest.approx(9.15)
    for d in depths:
        assert abs(d / 0.05 - round(d / 0.05)) < 1e-6
    for row, d in zip(rows, depths):
        assert d <= _row_depth_ceiling_m(row, net_w, d) + 1e-9


def test_the_ceiling_is_the_largest_net_the_room_can_come_back_with():
    """An open-plan public zone may realize its whole gross rectangle (no wall on its open sides);
    a closed room has at least half a partition on every side. The ceiling honours each."""
    dining, bed = _room(ProgramRole.DINING), _room(ProgramRole.BEDROOM)
    net_w = 6.8
    d_public = _row_depth_ceiling_m([dining], net_w, 4.0)
    d_closed = _row_depth_ceiling_m([bed], net_w, 2.5)
    gross_w = net_w + cg._EDGE_INSET_ALLOWANCE_M
    assert gross_w * d_public <= dining.template.max_area_m2 + 1e-9
    assert gross_w * (d_public + 0.05) > dining.template.max_area_m2
    inset = 2 * cg._MIN_SIDE_INSET_M
    assert (gross_w - inset) * (d_closed - inset) <= bed.template.max_area_m2 + 1e-9
    assert (gross_w - inset) * (d_closed + 0.05 - inset) > bed.template.max_area_m2


# ------------------------------------------------------------------ 2. the ZoneSpec

def test_zone_spec_max_is_capped_at_the_template():
    bed = _room(ProgramRole.BEDROOM)
    spec = _zone_spec(bed, 4.0, 3.0, 0.60, 1.60)     # planned 12.0 m2; 1.6x would be 19.2
    assert spec.net_area_target_m2 == pytest.approx(12.0)
    assert spec.net_area_max_m2 == bed.template.max_area_m2
    small = _zone_spec(bed, 3.0, 3.0, 0.60, 1.60)    # planned 9.0; 1.6x = 14.4, still over 14
    assert small.net_area_max_m2 == bed.template.max_area_m2


def test_a_candidate_planned_above_a_maximum_is_refused():
    bed = _room(ProgramRole.BEDROOM)
    specs = {"BEDROOM": _zone_spec(bed, 5.0, 3.2, 0.60, 1.60)}   # 16.0 m2 against 14
    failure = _specs_within_maxima([bed], specs, "columns")
    assert failure is not None
    assert failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA
    assert "BEDROOM" in failure.detail
    assert _specs_within_maxima([bed], {"BEDROOM": _zone_spec(bed, 4.0, 3.0, 0.60, 1.60)}, "columns") is None


# ------------------------------------------------------------------ 3. validation C21

def _oversized_fixture(bath_max: float) -> Fixture:
    """A hall, a master and a bathroom side by side in a 14 x 3.4 m wing: the bathroom's forced
    7.0 m width at 3.4 m nets to ~6.8 x 3.1 = 21 m2 — past its 12 m2 maximum at a legal 2.2
    aspect. Its ZoneSpec says `bath_max`, which is the layer under test."""
    tree = Split(Cut.V, Leaf("HALL"),
                 Split(Cut.V, Leaf("MASTER"), Leaf("BATH_1"), m_to_u(5.6)), m_to_u(1.4))
    wing = Wing("W", 0, 0, m_to_u(14.0), m_to_u(3.4), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (
        ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 1, 3, 8, 1.2, 8.0),
        ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 11, 14, 20, 3.0, 2.5),
        ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 4, 8, bath_max, 1.6, 3.0),
    )
    return Fixture("C21", (wing,), zones, access)


def _checks(fixture: Fixture) -> dict[str, tuple[bool, str]]:
    solve = solve_fixture(fixture)
    wing = fixture.wings[0]
    footprint = Rect(wing.origin_x_u, wing.origin_y_u, wing.w_u, wing.h_u)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    parking = site_stage.build_parking(spec)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance,
                    site_stage.classify_garden(spec, plot, footprint, parking))
    doors = generate_interior_doors(fixture, solve.rects)
    entrance_door = build_entrance_door(entrance, footprint, "HALL")
    report = validate(fixture, solve.rects, solve.walls, doors, entrance_door, [], [], site)
    return {c.check_id: (c.passed, c.detail) for c in report.checks}


def test_c21_fails_an_oversized_room_whose_own_zone_spec_was_relaxed_to_allow_it():
    """THE regression. A sizing path that writes a ZoneSpec around the rectangle it drew gets
    past the solver and past C3 — and is still refused, on the template's number."""
    checks = _checks(_oversized_fixture(bath_max=40.0))
    assert checks["C3"][0], checks["C3"][1]          # the relaxed spec is satisfied: C3 is blind
    assert checks["C20"][0], checks["C20"][1]        # and the shape is legal: C20 has no case
    assert not checks["C21"][0]
    assert "BATH_1" in checks["C21"][1]
    assert f"{ROOM_TEMPLATES[ProgramRole.BATHROOM].hard_max:.0f} m2 hard" in checks["C21"][1]


def test_c21_gates_on_the_hard_maximum_not_the_preferred_one():
    """A bathroom between the preferred (12) and hard (14) maxima passes C21: the preferred
    figure is a quality target the contract reports on, the hard one is the gate."""
    # 12 x 3.4 wing, BATH_1 forced 4.35 m wide: ~4.15 x 3.1 = 12.9 m2 net.
    tree = Split(Cut.V, Leaf("HALL"),
                 Split(Cut.V, Leaf("MASTER"), Leaf("BATH_1"), m_to_u(6.25)), m_to_u(1.4))
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(3.4), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (
        ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 1, 3, 8, 1.2, 8.0),
        ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 11, 14, 23, 3.0, 2.5),
        ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 4, 8, 14, 1.6, 3.0),
    )
    checks = _checks(Fixture("C21-hard", (wing,), zones, access))
    assert checks["C21"][0], checks["C21"][1]


def test_c21_never_reads_the_zone_spec():
    for bath_max in (40.0, 400.0):
        assert not _checks(_oversized_fixture(bath_max=bath_max))["C21"][0]


def test_the_engine_refuses_the_same_room_when_the_zone_spec_is_honest():
    """Layer 2's contract with the engine: with the template's maximum in the ZoneSpec, the
    forced tree that produced the oversized room cannot be solved at all."""
    from app.vertical_slice.geometry_core.engine import GeometryInfeasible
    with pytest.raises(GeometryInfeasible):
        solve_fixture(_oversized_fixture(bath_max=ROOM_TEMPLATES[ProgramRole.BATHROOM].max_area_m2))


def test_c21_leaves_circulation_alone():
    checks = _checks(_oversized_fixture(bath_max=40.0))
    assert "HALL" not in checks["C21"][1]


# ------------------------------------------------------------------ 4. end to end

@pytest.mark.parametrize("bedrooms, wet, target", [(4, 2, 200), (3, 2, 170), (2, 3, 230)])
def test_delivered_plans_have_no_room_above_its_template_maximum(bedrooms, wet, target):
    """The programmes that produced the worst rooms in the investigation sweep — a 62 m2
    bathroom, a 30 m2 safe room, a 23 m2 bedroom — now deliver with every room inside its HARD
    maximum, and inside its PREFERRED one unless the candidate had to exceed it
    (`ConceptCandidate.over_preferred`), or not at all."""
    program = ProgramSpec(bedrooms=bedrooms, safe_room=True, open_plan_living=True, wet_rooms=wet,
                          parking_spaces=2, target_built_area_m2=float(target))
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program)
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    for room in result.design.rooms:
        role = ProgramRole(room.roles[0])
        if role in (ProgramRole.HALL, ProgramRole.CIRCULATION, ProgramRole.FLEX):
            continue
        assert room.net_area_m2 <= ROOM_TEMPLATES[role].hard_max + 0.01, (room.zone_id, room.net_area_m2)
        if not result.concept.over_preferred:
            assert room.net_area_m2 <= ROOM_TEMPLATES[role].max_area_m2 + 0.01, (room.zone_id, room.net_area_m2)


# ------------------------------------------------------------------ 5. deficit distribution

def test_wants_over_the_column_shrink_toward_floors_instead_of_refusing():
    """The regression: a column whose rows' FLOORS fit with metres to spare was refused for
    4 cm of area-want. Rows above their floor now give up the same share of their want, the
    column tiles exactly, and no row goes under its floor."""
    from app.vertical_slice.concept_generator import _row_depth_floor_m, _row_wall_allowances_m
    master, bed1, bed2 = _room(ProgramRole.MASTER_BEDROOM), _room(ProgramRole.BEDROOM, "B1"), _room(ProgramRole.BEDROOM, "B2")
    safe, bath = _room(ProgramRole.SAFE_ROOM), _room(ProgramRole.BATHROOM)
    rows = [[master], [bed1], [bed2], [safe], [bath]]
    net_w = 4.9
    areas = {"MASTER_BEDROOM": 19.0, "B1": 13.0, "B2": 13.0, "SAFE_ROOM": 10.5, "BATHROOM": 8.0}
    floors = [_row_depth_floor_m(r, net_w, "column", a)[0]
              for r, a in zip(rows, _row_wall_allowances_m(rows, (True, True)))]
    wanted = [max(areas[r[0].zone_id] / net_w, f) for r, f in zip(rows, floors)]
    column = 14.0                      # floors sum to ~13.4, wants to ~15.6
    assert sum(wanted) > column > sum(floors)
    depths, failure = _row_depths(rows, areas, net_w, column, allow_deficit=True)  # the second pass
    assert failure is None, failure
    assert sum(depths) == pytest.approx(column)
    for d, f in zip(depths, floors):
        assert d >= f - 0.03   # 5 cm grid rounding, never a real step under the floor
    # The safe room (elasticity 0) sits at its floor; the deficit came out of the elastic rows.
    assert depths[3] == pytest.approx(round(floors[3] / 0.05) * 0.05, abs=0.051)


def test_a_column_whose_floors_do_not_fit_is_still_refused():
    from app.vertical_slice.concept_generator import _row_depth_floor_m, _row_wall_allowances_m
    rows = [[_room(ProgramRole.BEDROOM, "B1")], [_room(ProgramRole.BEDROOM, "B2")], [_room(ProgramRole.SAFE_ROOM)]]
    floors = [_row_depth_floor_m(r, 4.0, "column", a)[0]
              for r, a in zip(rows, _row_wall_allowances_m(rows, (True, True)))]
    depths, failure = _row_depths(rows, {"B1": 10.5, "B2": 10.5, "SAFE_ROOM": 10.5}, 4.0, sum(floors) - 0.2)
    assert depths is None
    assert failure.reason is RejectionReason.COLUMN_DEPTH_EXCEEDED
    assert "floors" in failure.detail


def test_floors_carry_the_template_minimum_area():
    """A row shrunk to its floor may not fall under its template's minimum area: a 2.75 m wide
    bedroom at its 2.6 m short side would be 7.3 m2 against 9."""
    from app.vertical_slice.concept_generator import room_depth_band_m
    bed = ROOM_TEMPLATES[ProgramRole.BEDROOM]
    lo, _ = room_depth_band_m(bed, 2.75)
    assert lo == pytest.approx(bed.min_area_m2 / 2.75)
    assert 2.75 * lo >= bed.min_area_m2 - 1e-9
    spec = _zone_spec(_room(ProgramRole.BEDROOM), 2.75, lo, 0.60, 1.60)
    assert spec.net_area_min_m2 >= bed.min_area_m2 - 1e-9


def test_floor_allowance_follows_the_rows_real_walls():
    """A row's floor carries the walls it actually has: exterior at a column end, RC beside the
    safe room, a partition otherwise — never less than the flat allowance."""
    from app.vertical_slice.concept_generator import _row_wall_allowances_m
    rows = [[_room(ProgramRole.MASTER_BEDROOM)], [_room(ProgramRole.BEDROOM, "B1")],
            [_room(ProgramRole.BEDROOM, "B2")], [_room(ProgramRole.SAFE_ROOM)], [_room(ProgramRole.BATHROOM)]]
    spine = _row_wall_allowances_m(rows, (True, True))
    assert spine == pytest.approx([0.20, 0.20, 0.20, 0.30, 0.30])   # B1: 0.10 real, floored at 0.20
    rear = _row_wall_allowances_m(rows, (False, True))                 # the band above, not the envelope
    assert rear == pytest.approx([0.20, 0.20, 0.20, 0.30, 0.30])


def test_shared_row_widths_pay_for_the_partition_between_them():
    from app.vertical_slice.concept_generator import _row_widths
    master, bath = _room(ProgramRole.MASTER_BEDROOM), _room(ProgramRole.BATHROOM)
    widths = _row_widths([master, bath], 5.0)
    assert sum(widths) == pytest.approx(5.0 - 0.10)
    assert widths[0] >= master.template.min_short_side_m and widths[1] >= bath.template.min_short_side_m
    assert _row_widths([master, bath], 4.65) is None          # 3.0 + 1.6 + 0.10 > 4.65


@pytest.mark.parametrize("w, d, bedrooms, wet, target, expect", [
    (13.3, 14.0, 3, 1, 216.0, 186.2),   # the two regressions: closed plan, FLEX, all rooms within max
    (11.9, 8.8, 1, 2, 181.25, 102.0),
])
def test_the_identified_regressions_plan_again(w, d, bedrooms, wet, target, expect):
    from app.geometry_domain.primitives import Region, Ring
    from app.vertical_slice.general_pipeline import run_general
    program = ProgramSpec(bedrooms=bedrooms, safe_room=True, wet_rooms=wet, open_plan_living=False,
                          parking_spaces=0, target_built_area_m2=target)
    result = run_general(F._known(Region(Ring.rectangle(3.0, 0.0, w, d))), plot_size_m=(w + 6, d + 8),
                         program=program, fast_path=True)
    assert result.design is not None, result.metrics.rejection_reasons
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    assert result.design.gross_area_m2 >= expect - 0.5
    for room in result.design.rooms:
        role = ProgramRole(room.roles[0])
        if role in (ProgramRole.HALL, ProgramRole.CIRCULATION, ProgramRole.FLEX):
            continue
        assert room.net_area_m2 <= ROOM_TEMPLATES[role].max_area_m2 + 0.01
        assert room.net_area_m2 >= ROOM_TEMPLATES[role].min_area_m2 - 0.01


def test_shrinking_is_the_second_pass_never_the_first_answer():
    """A seam search stops at the first seam that plans, so shrinking must be refused on the
    first pass or the area-share seam "plans" with its rooms shrunk and the seam where nothing
    shrinks is never reached (measured: 255 of 261 primaries changed, living rooms 37.5 -> 29 m2).
    With the wants fitting, both passes give the same depths; with the wants over the column the
    first pass refuses and only the second shrinks."""
    master, bed, bath = _room(ProgramRole.MASTER_BEDROOM), _room(ProgramRole.BEDROOM), _room(ProgramRole.BATHROOM)
    rows = [[master], [bed], [bath]]
    fits = {"MASTER_BEDROOM": 14.0, "BEDROOM": 10.5, "BATHROOM": 6.5}
    a, _ = _row_depths(rows, fits, 4.0, 10.0, allow_deficit=False)
    b, _ = _row_depths(rows, fits, 4.0, 10.0, allow_deficit=True)
    assert a == b
    wants_over = {"MASTER_BEDROOM": 19.0, "BEDROOM": 13.5, "BATHROOM": 10.0}
    refused, failure = _row_depths(rows, wants_over, 4.0, 9.0, allow_deficit=False)
    assert refused is None and failure.reason is RejectionReason.COLUMN_DEPTH_EXCEEDED
    shrunk, failure = _row_depths(rows, wants_over, 4.0, 9.0, allow_deficit=True)
    assert shrunk is not None, failure
    assert sum(shrunk) == pytest.approx(9.0)


# ------------------------------------------------------------------ 6. two-level maxima

def test_templates_carry_a_preferred_and_a_hard_maximum():
    bed = ROOM_TEMPLATES[ProgramRole.BEDROOM]
    assert bed.preferred_max_area_m2 == 14.0 and bed.hard_max == 18.0
    assert bed.ceiling_m2(False) == 14.0 and bed.ceiling_m2(True) == 18.0
    safe = ROOM_TEMPLATES[ProgramRole.SAFE_ROOM]
    assert safe.hard_max_area_m2 is None and safe.hard_max == safe.max_area_m2 == 14.0
    for role, hard in ((ProgramRole.MASTER_BEDROOM, 23.0), (ProgramRole.BATHROOM, 14.0),
                       (ProgramRole.TOILET, 7.0), (ProgramRole.LIVING, 50.0),
                       (ProgramRole.DINING, 33.0), (ProgramRole.KITCHEN, 28.0)):
        assert ROOM_TEMPLATES[role].hard_max == hard, role


def test_the_band_exists_under_the_hard_maximum_where_the_preferred_one_refuses():
    """A 6.1 m wide bedroom at its 2.6 m short side is 15.9 m2: no band under 14, a band under 18."""
    from app.vertical_slice.concept_generator import room_depth_band_m
    bed = ROOM_TEMPLATES[ProgramRole.BEDROOM]
    assert room_depth_band_m(bed, 6.1) is None
    lo, hi = room_depth_band_m(bed, 6.1, hard=True)
    assert lo == 2.6 and hi == pytest.approx(18.0 / 6.1)


def test_surplus_fills_to_preferred_first_and_hard_only_for_the_residue():
    """Two bedrooms and a bathroom in a 4.0 m column: at 9.4 m the preferred ceilings hold
    everything; at 10.4 m they cannot, and only then do the elastic rows grow past preferred."""
    b1, b2, bath = _room(ProgramRole.BEDROOM, "B1"), _room(ProgramRole.BEDROOM, "B2"), _room(ProgramRole.BATHROOM)
    rows = [[b1], [b2], [bath]]
    areas = {"B1": 10.5, "B2": 10.5, "BATHROOM": 6.5}
    fits, failure = _row_depths(rows, areas, 4.0, 9.4, allow_hard=True)
    assert failure is None, failure
    for row, d in zip(rows, fits):
        assert _net_area(row[0], 4.0, d) <= row[0].template.max_area_m2 + 0.3   # inside preferred (+ grid)
    refused, failure = _row_depths(rows, areas, 4.0, 10.4, allow_hard=False)
    assert refused is None and failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA
    grown, failure = _row_depths(rows, areas, 4.0, 10.4, allow_hard=True)
    assert failure is None, failure
    assert sum(grown) == pytest.approx(10.4)
    for row, d in zip(rows, grown):
        assert _net_area(row[0], 4.0, d) <= row[0].template.hard_max + 1e-6
    assert any(_net_area(row[0], 4.0, d) > row[0].template.max_area_m2 for row, d in zip(rows, grown))


def test_the_safe_room_never_grows_past_its_want_even_when_hard_is_allowed():
    bed, safe = _room(ProgramRole.BEDROOM), _room(ProgramRole.SAFE_ROOM)
    depths, failure = _distribute_column_surplus([[bed], [safe]], [3.0, 3.0], 3.5, 7.4, "column",
                                                 allow_hard=True)
    assert failure is None, failure
    assert depths[1] == pytest.approx(3.0)          # the safe room stays at its want
    assert depths[0] == pytest.approx(4.4)          # the bedroom took it all, past preferred (14/3.4=4.1)
    # and a column even the hard ceilings cannot absorb is still refused
    depths, failure = _distribute_column_surplus([[bed], [safe]], [3.0, 3.0], 3.5, 8.6, "column",
                                                 allow_hard=True)
    assert depths is None and failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA
    assert "hard" in failure.detail


def test_zone_spec_caps_at_preferred_unless_the_candidate_may_exceed_it():
    bed = _room(ProgramRole.BEDROOM)
    assert _zone_spec(bed, 4.0, 3.5, 0.60, 1.60).net_area_max_m2 == 14.0
    assert _zone_spec(bed, 4.0, 3.5, 0.60, 1.60, hard=True).net_area_max_m2 == 18.0
    specs = {"BEDROOM": _zone_spec(bed, 5.0, 3.2, 0.60, 1.60, hard=True)}   # 16 m2
    assert _specs_within_maxima([bed], specs, "columns") is not None
    assert _specs_within_maxima([bed], specs, "columns", hard=True) is None


def test_a_candidate_past_preferred_is_marked_and_the_contract_warns():
    """The 2BR/3wet 230 m2 brief cannot be planned inside the preferred maxima on the canonical
    rectangle; it plans past them, is flagged, every room stays inside its hard maximum, and the
    contract names the rooms above preferred."""
    from app.demo.contract import quality_of, to_demo_design
    program = ProgramSpec(bedrooms=2, safe_room=True, open_plan_living=True, wet_rooms=3,
                          parking_spaces=2, target_built_area_m2=230.0)
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program)
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.concept.over_preferred
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    over = [r for r in result.design.rooms if r.roles[0] not in ("HALL", "FLEX")
            and r.net_area_m2 > ROOM_TEMPLATES[ProgramRole(r.roles[0])].max_area_m2 + 0.01]
    assert over, "the flag means at least one room is past its preferred maximum"
    for r in over:
        assert r.net_area_m2 <= ROOM_TEMPLATES[ProgramRole(r.roles[0])].hard_max + 0.01
    quality = quality_of(result.design)
    assert quality.over_preferred
    # Every room above preferred is on its RoomOut as a ratio; nothing here is a validation warning.
    demo = to_demo_design(result.design, result.validation)
    rooms = {r.id: r for r in demo.rooms}
    assert {r.zone_id for r in over} == {i for i, r in rooms.items() if r.over_preferred_ratio}
    assert all(rooms[r.zone_id].hard_max_m2 == ROOM_TEMPLATES[ProgramRole(r.roles[0])].hard_max for r in over)
    assert not [w for w in demo.validation.warnings if "מהמומלץ" in w]


def test_a_brief_that_fits_inside_preferred_is_not_flagged():
    program = ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=True, wet_rooms=2,
                          parking_spaces=2, target_built_area_m2=170.0)
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program)
    assert result.outcome is AdapterOutcome.SOLVED
    assert not result.concept.over_preferred
    from app.demo.contract import quality_of
    quality = quality_of(result.design)
    assert not quality.over_preferred and quality.signal == [] and quality.notices == []
