"""Strip rooms — the shape rule, at every layer it lives on.

The defect: a wet room alone in a wide column (or an ensuite beside a deep bedroom) realized as a
5-7 x 1.6 m bathroom or a 6 x 1.2 m WC, satisfied every area requirement, and passed every check.
The planner floored a row's depth by its SHORT SIDE alone, then wrote the room's `ZoneSpec` with
`max_aspect_ratio = max(template, planned aspect + 0.3)` — so the solver and validator C3 judged
the rectangle against a limit derived from the rectangle itself.

Three layers now hold the line, and each is tested on its own:

  1. the planner's shape band (`room_depth_band_m`) floors depths by width / aspect, widens a
     shared row's narrow member by depth / aspect, and refuses a row that cannot be shaped;
  2. every `ZoneSpec` the generator emits carries the TEMPLATE's aspect ratio, never a relaxed one;
  3. validation C20 measures the drawing against `ROOM_TEMPLATES` directly, so a candidate that
     relaxes its own ZoneSpec — now or in a future sizing path — still cannot pass a strip.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import concept_generator as cg
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import site as site_stage
from app.vertical_slice.concept_generator import (
    HUB_TEMPLATE,
    ROOM_TEMPLATES,
    RejectionReason,
    _row_depths,
    _row_widths,
    build_room_program,
    room_depth_band_m,
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
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt, build_buildable_region
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import validate

CIRCULATION = {ProgramRole.HALL, ProgramRole.CIRCULATION}

#: Programmes that produced strips before the fix (from the 110-programme sweep that diagnosed
#: it), plus the ensuite case. Every family that had a wet strip is represented.
STRIP_PROGRAMS = {
    "2BR_1wet_front_band": ProgramSpec(bedrooms=2, safe_room=False, wet_rooms=1),
    "3BR_2wet_ensuite_and_wc": ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2,
                                           target_built_area_m2=200),
    "4BR_3wet_toilet_strip": ProgramSpec(bedrooms=4, safe_room=False, wet_rooms=3,
                                         target_built_area_m2=200),
    "3BR_2wet_hub_flank": ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2,
                                      target_built_area_m2=170),
    "5BR_2wet_stood_on_end": ProgramSpec(bedrooms=5, safe_room=False, wet_rooms=2,
                                         target_built_area_m2=200),
}


def _spec(program: ProgramSpec) -> ArchitecturalSpec:
    return ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=program)


def _room(role: ProgramRole, zone_id: str | None = None, entered_from: str | None = None):
    return cg.ProgramRoom(zone_id or role.value, role, cg.ZoneGroup.SERVICE, ROOM_TEMPLATES[role],
                          entered_from)


# ------------------------------------------------------------------ 1. the shape band

def test_band_floors_a_wide_room_by_its_aspect_not_its_short_side():
    bath = ROOM_TEMPLATES[ProgramRole.BATHROOM]
    lo, hi = room_depth_band_m(bath, 5.0)
    assert lo == pytest.approx(5.0 / bath.max_aspect_ratio)  # 1.67, not the 1.6 short side
    assert lo > bath.min_short_side_m
    assert hi == pytest.approx(5.0 * bath.max_aspect_ratio)
    # Narrow enough and the short side is what binds, as before.
    lo, _ = room_depth_band_m(bath, 3.0)
    assert lo == bath.min_short_side_m


@pytest.mark.parametrize("role, width", [
    (ProgramRole.BATHROOM, 6.5),   # sqrt(12 * 3.0) = 6.0 m is the widest a bathroom can be
    (ProgramRole.TOILET, 4.65),    # sqrt(6 * 3.5) = 4.58 m for a WC — the sweep's 4.65 x 1.15 strip
    (ProgramRole.TOILET, 6.1),     # the sweep's worst: 6.1 x 1.2 m, 7.3 m2 against a 6 m2 maximum
])
def test_band_is_empty_where_the_aspect_floor_exceeds_the_area_cap(role, width):
    assert room_depth_band_m(ROOM_TEMPLATES[role], width) is None


@pytest.mark.parametrize("role, width", [
    (ProgramRole.MASTER_BEDROOM, 6.8),  # 3.0 m minimum x 6.8 = 20.4 m2 against 20; aspect 2.27
    (ProgramRole.BEDROOM, 6.1),         # 2.6 m minimum x 6.1 = 15.9 m2 against 14; aspect 2.35
])
def test_band_does_not_refuse_the_short_side_against_the_area_cap(role, width):
    """Out of scope on purpose. Where the SHORT SIDE binds, the room is not a strip — it is what
    the planner drew before this rule, possibly over its area cap. That is the planners not holding
    rooms to their area maxima, a separate defect; refusing it here cost programmes with no strip in
    them at all (measured: 5 for the master case, and 643 seam attempts for the bedroom one)."""
    template = ROOM_TEMPLATES[role]
    band = room_depth_band_m(template, width)
    assert band is not None
    assert band[0] == template.min_short_side_m
    assert width / band[0] <= template.max_aspect_ratio


# ------------------------------------------------------------------ 2. the planners

def test_a_bathroom_alone_in_a_wide_column_is_floored_by_its_aspect():
    """The classic strip: a 5.2 m column, a bathroom row. Its depth used to be the 1.6 m short
    side plus the wall allowance; it is now deep enough for the template's aspect ratio."""
    bath = _room(ProgramRole.BATHROOM, "BATH_1")
    depths, failure = _row_depths([[bath]], {"BATH_1": 6.5}, 5.2, 14.0)
    assert failure is None
    net_d = depths[0] - cg._EDGE_INSET_ALLOWANCE_M / 2
    assert 5.2 / net_d <= bath.template.max_aspect_ratio + 1e-9


def test_a_wc_alone_in_a_column_it_cannot_be_shaped_in_is_refused_with_its_own_reason():
    wc = _room(ProgramRole.TOILET, "TOILET_1")
    depths, failure = _row_depths([[wc]], {"TOILET_1": 4.0}, 5.2, 14.0, "east column")
    assert depths is None
    assert failure.reason is RejectionReason.ROOM_SHAPE_INFEASIBLE
    assert "TOILET_1" in failure.detail and "east column" in failure.detail


def test_a_column_that_is_merely_too_shallow_keeps_its_own_reason():
    bed = _room(ProgramRole.BEDROOM, "BEDROOM_1")
    depths, failure = _row_depths([[bed], [bed]], {"BEDROOM_1": 10.5}, 4.0, 3.0)
    assert depths is None
    assert failure.reason is RejectionReason.COLUMN_DEPTH_EXCEEDED


def test_an_ensuite_beside_a_deep_bedroom_is_widened_by_the_depth():
    """The strip stood on end: at its 1.6 m minimum width beside a 5.6 m deep master, an ensuite
    is 1:3.5. With the depth known, its minimum width is the depth over its aspect ratio."""
    rooms = build_room_program(_spec(ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2)))
    master = next(r for r in rooms if r.zone_id == "MASTER")
    ensuite = next(r for r in rooms if r.entered_from == "MASTER")
    without = _row_widths([master, ensuite], 5.0)
    with_depth = _row_widths([master, ensuite], 5.0, net_depth=5.6)
    assert without[1] < 5.6 / ensuite.template.max_aspect_ratio  # 1.73 m: the old answer, a strip
    assert with_depth[1] >= 5.6 / ensuite.template.max_aspect_ratio
    assert with_depth[0] >= master.template.min_short_side_m
    assert sum(with_depth) == pytest.approx(5.0)


def test_a_shared_row_the_surplus_would_deepen_into_a_strip_is_refused_not_stretched():
    """A generous column hands its surplus to the bedroom row; if that leaves no width for the
    ensuite to keep its aspect beside the deepened bedroom, the row is refused."""
    rooms = build_room_program(_spec(ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2)))
    master = next(r for r in rooms if r.zone_id == "MASTER")
    ensuite = next(r for r in rooms if r.entered_from == "MASTER")
    # 4.7 m net: master 3.0 + ensuite 1.6 fit at their minimums, but a 14 m deep column pushes the
    # row to ~14 m deep, where the ensuite would need 4.7 m of width on its own.
    depths, failure = _row_depths([[master, ensuite]], {"MASTER": 14.0, ensuite.zone_id: 6.5},
                                  4.7, 14.0)
    assert depths is None
    assert failure.reason in (RejectionReason.ROOM_SHAPE_INFEASIBLE,
                              RejectionReason.ROW_WIDTH_EXCEEDED)


def _all_candidates(program: ProgramSpec):
    adapter = adapt(build_buildable_region(F.exact_rectangle()))
    return cg.generate_concepts(_spec(program), list(adapter.candidates)).candidates


@pytest.mark.parametrize("name", sorted(STRIP_PROGRAMS))
def test_every_emitted_zone_spec_carries_the_template_aspect_unrelaxed(name):
    """Layer 2. No ZoneSpec leaves the generator with an aspect ratio wider than its template's,
    whatever rectangle the planner drew for it — that relaxation was the root of the defect."""
    candidates = _all_candidates(STRIP_PROGRAMS[name])
    assert candidates, "the programme must still plan"
    for candidate in candidates:
        for zone in candidate.concept.fixture.zones:
            if CIRCULATION & set(zone.roles):
                expected = HUB_TEMPLATE.max_aspect_ratio if zone.zone_id.startswith("HUB") else None
                if expected is not None:
                    assert zone.max_aspect_ratio == expected, (candidate.strategy, zone.zone_id)
                continue
            template = ROOM_TEMPLATES[zone.primary_role]
            assert zone.max_aspect_ratio == template.max_aspect_ratio, (
                candidate.strategy, zone.zone_id, zone.max_aspect_ratio)


@pytest.mark.parametrize("name", sorted(STRIP_PROGRAMS))
def test_no_realized_room_exceeds_its_template_aspect(name):
    """End to end, on the programmes that produced strips: the drawing has none."""
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0),
                                   program=STRIP_PROGRAMS[name])
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    zones = {z.zone_id: z for z in result.concept.concept.fixture.zones}
    for room in result.design.rooms:
        zone = zones[room.zone_id]
        if CIRCULATION & set(zone.roles):
            continue
        template = ROOM_TEMPLATES[zone.primary_role]
        aspect = max(room.net_w_m, room.net_h_m) / min(room.net_w_m, room.net_h_m)
        assert aspect <= template.max_aspect_ratio + 1e-6, (
            room.zone_id, room.net_w_m, room.net_h_m, template.max_aspect_ratio)


# ------------------------------------------------------------------ 3. validation C20

def _strip_fixture(bath_aspect: float) -> Fixture:
    """A hall, a master and a bathroom side by side in a 12 x 2.0 m wing: the bathroom's forced
    8.0 m width at the wing's 2.0 m depth nets to roughly 7.9 x 1.7 m — a 1:4.6 strip. Its
    ZoneSpec says `bath_aspect`, which is the layer under test."""
    tree = Split(Cut.V, Leaf("HALL"),
                 Split(Cut.V, Leaf("MASTER"), Leaf("BATH_1"), m_to_u(2.6)), m_to_u(1.4))
    wing = Wing("W", 0, 0, m_to_u(12.0), m_to_u(2.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH_1", ConnectionKind.DOOR),
    ))
    zones = (
        ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 1, 2, 6, 1.2, 8.0),
        ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 2, 4, 8, 1.5, 10.0),
        ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 4, 8, 20, 1.6, bath_aspect),
    )
    return Fixture("C20", (wing,), zones, access)


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


def test_c19_fails_a_strip_whose_own_zone_spec_was_relaxed_to_allow_it():
    """THE regression. A future candidate that relaxes its ZoneSpec to fit the rectangle it drew
    gets past the solver and past C3 — exactly as every strip did — and is still refused."""
    checks = _checks(_strip_fixture(bath_aspect=10.0))
    assert checks["C3"][0], checks["C3"][1]          # the relaxed spec is satisfied: C3 is blind
    assert not checks["C20"][0]
    assert "BATH_1" in checks["C20"][1]
    assert f"{ROOM_TEMPLATES[ProgramRole.BATHROOM].max_aspect_ratio}" in checks["C20"][1]


def test_c19_never_reads_the_zone_spec():
    """Widening the ZoneSpec further changes nothing: the ceiling is the template's."""
    for aspect in (10.0, 100.0):
        checks = _checks(_strip_fixture(bath_aspect=aspect))
        assert not checks["C20"][0]


def test_the_engine_refuses_the_same_strip_when_the_zone_spec_is_honest():
    """Layer 1's contract with the engine: with the template's aspect in the ZoneSpec, the forced
    tree that produced the strip cannot be solved at all."""
    from app.vertical_slice.geometry_core.engine import GeometryInfeasible
    with pytest.raises(GeometryInfeasible):
        solve_fixture(_strip_fixture(bath_aspect=ROOM_TEMPLATES[ProgramRole.BATHROOM].max_aspect_ratio))


def test_c19_leaves_circulation_alone():
    """A corridor is a strip by definition; C14 measures its width. C20 must not refuse it."""
    checks = _checks(_strip_fixture(bath_aspect=10.0))
    assert "HALL" not in checks["C20"][1]


# ------------------------------------------------------------------ 4. the WC shares a row

def _wet_program(**kw) -> list:
    return build_room_program(_spec(ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=3, **kw)))


def test_a_wc_that_cannot_be_shaped_across_its_column_joins_the_ensuite_row():
    """The topology catch-up. In a 5.2 m column a WC alone in a row is a strip or oversized
    (`room_depth_band_m` is None), so it takes the bedroom's slot in the ensuite's row and the
    bedroom gets a full-width row beside it — same orientation, same corridor side."""
    from app.vertical_slice.concept_generator import _orient_row, _rows_for_width, _rows_of
    rooms = _wet_program()
    private = [r for r in rooms if r.group in (cg.ZoneGroup.PRIVATE, cg.ZoneGroup.SERVICE)]
    rows = [_orient_row(r, corridor_on_east=True) for r in _rows_of(private)]
    wc = next(r for r in private if r.role is ProgramRole.TOILET)
    ensuite = next(r for r in private if r.entered_from)
    assert [wc] in rows                      # its own row to begin with
    shared = _rows_for_width(rows, 5.2)
    paired = next(row for row in shared if wc in row)
    assert paired == [ensuite, wc]           # ensuite kept its slot; the WC took the bedroom's
    bedroom_row = next(i for i, row in enumerate(shared)
                       if len(row) == 1 and row[0].zone_id == ensuite.entered_from)
    assert shared.index(paired) == bedroom_row + 1   # directly beside its bedroom
    assert [wc] not in shared
    assert sum(len(r) for r in shared) == len(private)


def test_a_column_narrow_enough_for_the_wc_keeps_its_rows():
    from app.vertical_slice.concept_generator import _rows_for_width, _rows_of
    rooms = _wet_program()
    private = [r for r in rooms if r.group in (cg.ZoneGroup.PRIVATE, cg.ZoneGroup.SERVICE)]
    rows = _rows_of(private)
    assert _rows_for_width(rows, 4.0) is rows    # sqrt(6 x 3.5) = 4.58 m: the WC is fine alone


def test_a_column_with_no_ensuite_keeps_its_rows_and_is_refused_downstream():
    from app.vertical_slice.concept_generator import _rows_for_width
    wc = _room(ProgramRole.TOILET, "TOILET_1")
    bed = _room(ProgramRole.BEDROOM, "BEDROOM_1")
    rows = [[bed], [wc]]
    assert _rows_for_width(rows, 5.2) is rows
    depths, failure = _row_depths(rows, {"BEDROOM_1": 10.5, "TOILET_1": 4.0}, 5.2, 14.0)
    assert depths is None and failure.reason is RejectionReason.ROOM_SHAPE_INFEASIBLE


def test_the_paired_wc_plan_keeps_its_access_semantics():
    """End to end on a programme that lost 30% of its area to the strip rule: it plans near the
    request again, the WC sits beside the ensuite, and C17 reads the same access — the WC from the
    hall only, the ensuite from its bedroom only, across the row boundary."""
    result = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0),
                                   program=ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=3,
                                                       target_built_area_m2=224))
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    assert result.design.gross_area_m2 >= 0.85 * 224
    rooms = {r.zone_id: r for r in result.design.rooms}
    wc = next(r for r in result.design.rooms if "TOILET" in r.roles)
    ensuite = next(r for r in result.design.rooms if "BATHROOM" in r.roles
                   and any(d.a == "MASTER" or d.b == "MASTER"
                           for d in result.design.interior_doors if r.zone_id in (d.a, d.b)))
    # a shared wall between the two wet rooms
    wx, wy, ww, wh = wc.rect_m; ex, ey, ew, eh = ensuite.rect_m
    assert abs(wy - ey) < 1e-6 and abs(wh - eh) < 1e-6 and (abs(wx + ww - ex) < 1e-6 or abs(ex + ew - wx) < 1e-6)
    entered = {z: sorted({d.a if d.b == z else d.b for d in result.design.interior_doors if z in (d.a, d.b)})
               for z in (wc.zone_id, ensuite.zone_id)}
    assert entered[wc.zone_id] == ["HALL"]
    assert entered[ensuite.zone_id] == ["MASTER"]
    for r in result.design.rooms:
        t = ROOM_TEMPLATES.get(ProgramRole(r.roles[0]))
        if t and not CIRCULATION & {ProgramRole(x) for x in r.roles}:
            assert max(r.net_w_m, r.net_h_m) / min(r.net_w_m, r.net_h_m) <= t.max_aspect_ratio + 1e-6, r.zone_id
