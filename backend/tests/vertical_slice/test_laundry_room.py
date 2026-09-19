"""Laundry room — phase 1 (2026-09-16, docs/LAUNDRY_ROOM_OPTION_REVIEW.md).

`ProgramSpec.laundry` carries an explicit request; `concept_generator.LAUNDRY_ROOM_ENABLED` gates
whether it is actually PLANNED, independently of the request, until the sweep this phase produced
is reviewed (see the phase report). Every test below that needs a planned room monkeypatches the
gate `True` for its own scope — the gate's default (`False`) is itself covered by
`test_gate_off_never_emits_a_room_even_when_requested`, proving normal generation is untouched.
"""
from __future__ import annotations

import pytest

from app.demo.requirements_view import _laundry_of, spec_for
from app.projects.models import Project, TaggedBool
from app.vertical_slice import concept_generator as cg
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import site as site_stage
from app.vertical_slice.concept_generator import (
    ROOM_TEMPLATES,
    ZoneGroup,
    _access_intact,
    _hub_allocation,
    _rows_for_width,
    _rows_of,
    build_room_program,
    room_depth_band_m,
    target_gross_area_m2,
)
from app.vertical_slice.doors import Door
from app.vertical_slice.general_pipeline import run_general_from_site
from app.vertical_slice.geometry_adapter import envelope_sides
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Rect,
    Side,
    Split,
    WallType,
    Wing,
    ZoneSpec,
    furniture_envelope_fits,
    m_to_u,
    min_furniture_envelope_m,
)
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt, build_buildable_region
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import (
    ArchitecturalSpec,
    LaundryDemand,
    LaundryRequirement,
    PlotSpec,
    ProgramSpec,
)
from app.vertical_slice.validation import validate
from app.vertical_slice.windows import (
    LAUNDRY_WINDOW_MIN_WIDTH_M,
    EXTERIOR_WINDOW,
    generate_windows,
)

CIRCULATION = {ProgramRole.HALL, ProgramRole.CIRCULATION}


def _spec(program: ProgramSpec) -> ArchitecturalSpec:
    return ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=program)


def _room(role: ProgramRole, zone_id: str | None = None, entered_from: str | None = None):
    return cg.ProgramRoom(zone_id or role.value, role, ZoneGroup.SERVICE, ROOM_TEMPLATES[role],
                          entered_from)


# ------------------------------------------------------------------ 1. domain / requirement


def test_laundry_defaults_to_none_and_carries_no_source_text():
    assert ProgramSpec().laundry == LaundryRequirement(demand=LaundryDemand.NONE, source_text="")


def test_laundry_of_reads_none_when_never_parsed():
    project = Project.model_construct(laundry_requested=None, laundry_source_text="")
    assert _laundry_of(project) == LaundryRequirement(demand=LaundryDemand.NONE, source_text="")


def test_laundry_of_reads_explicit_room_request_with_its_source_text():
    project = Project.model_construct(
        laundry_requested=TaggedBool(value=True, source="requested"),
        laundry_source_text="חדר כביסה נפרד")
    result = _laundry_of(project)
    assert result.demand is LaundryDemand.ROOM
    assert result.source_text == "חדר כביסה נפרד"


def test_laundry_of_reads_false_as_none_regardless_of_stray_source_text():
    """An appliance mention never leaves `source_text` behind on the honest "none" reading — but
    even if it did (a defensive case, not a producible one via the parser), a `False` demand must
    never leak stale text into the spec."""
    project = Project.model_construct(
        laundry_requested=TaggedBool(value=False, source="inferred"),
        laundry_source_text="")
    assert _laundry_of(project) == LaundryRequirement(demand=LaundryDemand.NONE, source_text="")


# ------------------------------------------------------------------ 2. room program / gate


def _program(**kw) -> ProgramSpec:
    return ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2,
                       laundry=LaundryRequirement(demand=LaundryDemand.ROOM, source_text="x"), **kw)


def test_gate_off_never_emits_a_room_even_when_requested(monkeypatch):
    """The gate mechanism itself: with `LAUNDRY_ROOM_ENABLED` off, generation stays inert whatever
    `ProgramSpec.laundry` says — this was the shipped default through phase 1
    (docs/LAUNDRY_ROOM_PHASE1_REPORT.md); activation (docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md)
    flipped the module default to `True`, but the gate itself still works either way."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", False)
    rooms = build_room_program(_spec(_program()))
    assert not any(r.role is ProgramRole.LAUNDRY for r in rooms)


def test_gate_is_on_by_default_after_activation():
    """docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md: the flag flip is the shipped state now."""
    assert cg.LAUNDRY_ROOM_ENABLED is True


def test_gate_on_without_a_request_still_emits_nothing(monkeypatch):
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = build_room_program(_spec(ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2)))
    assert not any(r.role is ProgramRole.LAUNDRY for r in rooms)


def test_gate_on_with_a_request_emits_exactly_one_laundry_room(monkeypatch):
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = build_room_program(_spec(_program()))
    laundry = [r for r in rooms if r.role is ProgramRole.LAUNDRY]
    assert len(laundry) == 1
    room = laundry[0]
    assert room.group is ZoneGroup.SERVICE
    assert room.template == ROOM_TEMPLATES[ProgramRole.LAUNDRY]
    # Never a dependent: circulation-accessible, never only through a bedroom (§5).
    assert room.entered_from is None


# ------------------------------------------------------------------ 3. row-sharing generalisation


def _wet_and_laundry_program(**kw) -> list:
    return build_room_program(_spec(_program(**kw)))


def test_a_laundry_room_that_cannot_be_shaped_across_its_column_joins_the_ensuite_row(monkeypatch):
    """The exact WC fix (`test_strip_rooms.test_a_wc_that_cannot_be_shaped_across_its_column_
    joins_the_ensuite_row`), now reached by a requested laundry room through the SAME code path —
    `_ROW_RESCUE_ROLES` names `(TOILET, LAUNDRY)` explicitly (narrowed from the wider
    `ZoneGroup.SERVICE` after measurement found it also touched BATHROOM; see
    docs/LAUNDRY_ROOM_PHASE1_REPORT.md §3)."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = _wet_and_laundry_program()
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    laundry = next(r for r in private if r.role is ProgramRole.LAUNDRY)
    ensuite = next(r for r in private if r.entered_from)
    rows = [cg._orient_row(r, corridor_on_east=True) for r in _rows_of(private)]
    assert [laundry] in rows
    shared = _rows_for_width(rows, 5.2)
    paired = next(row for row in shared if laundry in row)
    assert paired == [ensuite, laundry]
    bedroom_row = next(i for i, row in enumerate(shared)
                       if len(row) == 1 and row[0].zone_id == ensuite.entered_from)
    assert shared.index(paired) == bedroom_row + 1
    assert [laundry] not in shared
    assert sum(len(r) for r in shared) == len(private)
    assert _access_intact(
        shared, cg.Repartition(open_chain=(), hall_public=None, north_is_envelope=True), True)


def test_a_column_narrow_enough_for_the_laundry_room_keeps_its_rows(monkeypatch):
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = _wet_and_laundry_program()
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    rows = _rows_of(private)
    # sqrt(8 x 3.0) = 4.9 m: the laundry template's own shape floor (min=2.5, max=8.0, aspect=3.0).
    assert _rows_for_width(rows, 3.5) is rows


def test_a_column_with_no_ensuite_keeps_the_laundry_row_and_is_refused_downstream():
    laundry = _room(ProgramRole.LAUNDRY, "LAUNDRY")
    bed = _room(ProgramRole.BEDROOM, "BEDROOM_1")
    rows = [[bed], [laundry]]
    assert _rows_for_width(rows, 5.2) is rows
    depths, failure = cg._row_depths(
        rows, {"BEDROOM_1": 10.5, "LAUNDRY": 6.5}, 5.2, 14.0)
    assert depths is None and failure.reason is cg.RejectionReason.ROOM_SHAPE_INFEASIBLE


def test_a_lone_bathroom_is_deliberately_not_rescued_at_tier_one():
    """The point of narrowing `_ROW_RESCUE_ROLES` to (TOILET, LAUNDRY): a lone BATHROOM hitting
    the same strip condition stays alone and is refused downstream, exactly as it was before this
    phase — measurement (docs/LAUNDRY_ROOM_PHASE1_REPORT.md §3) found the wider `ZoneGroup.SERVICE`
    condition rescued a real brief's BATHROOM this way, which the phase's own bar did not want."""
    bath = _room(ProgramRole.BATHROOM, "BATH_1")
    ensuite = _room(ProgramRole.BATHROOM, "ENSUITE", entered_from="MASTER")
    master = cg.ProgramRoom("MASTER", ProgramRole.MASTER_BEDROOM, ZoneGroup.PRIVATE,
                            ROOM_TEMPLATES[ProgramRole.MASTER_BEDROOM])
    rows = [[master, ensuite], [bath]]
    # 6.1 m: `test_strip_rooms.test_band_is_empty_where_the_aspect_floor_exceeds_the_area_cap`'s
    # own BATHROOM-analogue width — chosen so `room_depth_band_m` is None for the lone BATHROOM.
    assert room_depth_band_m(bath.template, 6.5) is None
    assert _rows_for_width(rows, 6.5) is rows


def test_toilet_rescue_is_unaffected_by_the_generalisation():
    """§3's explicit proof requirement: TOILET's behaviour through the (now generalised) fast path
    is unchanged — same assertions as `test_strip_rooms.test_a_wc_that_cannot_be_shaped_across_
    its_column_joins_the_ensuite_row`, re-run here beside the laundry equivalent."""
    rooms = build_room_program(_spec(ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=3)))
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    rows = [cg._orient_row(r, corridor_on_east=True) for r in _rows_of(private)]
    wc = next(r for r in private if r.role is ProgramRole.TOILET)
    ensuite = next(r for r in private if r.entered_from)
    assert [wc] in rows
    shared = _rows_for_width(rows, 5.2)
    paired = next(row for row in shared if wc in row)
    assert paired == [ensuite, wc]


# ------------------------------------------------------------------ 4. hub allocation


def test_hub_allocation_accepts_a_programme_with_a_laundry_room():
    """§4: hub topology needs no redesign — `_hub_allocation`'s `rank()` already classifies
    anything that is not a bedroom/safe room as "wet/service" generically, so a laundry room fills
    exactly the seat a spare wet room would. This proves the claim rather than asserting it."""
    master = cg.ProgramRoom("MASTER", ProgramRole.MASTER_BEDROOM, ZoneGroup.PRIVATE,
                            ROOM_TEMPLATES[ProgramRole.MASTER_BEDROOM])
    ensuite = cg.ProgramRoom("ENSUITE", ProgramRole.BATHROOM, ZoneGroup.SERVICE,
                             ROOM_TEMPLATES[ProgramRole.BATHROOM], entered_from="MASTER")
    bed1 = cg.ProgramRoom("BEDROOM_1", ProgramRole.BEDROOM, ZoneGroup.PRIVATE,
                          ROOM_TEMPLATES[ProgramRole.BEDROOM])
    bed2 = cg.ProgramRoom("BEDROOM_2", ProgramRole.BEDROOM, ZoneGroup.PRIVATE,
                          ROOM_TEMPLATES[ProgramRole.BEDROOM])
    laundry = cg.ProgramRoom("LAUNDRY", ProgramRole.LAUNDRY, ZoneGroup.SERVICE,
                             ROOM_TEMPLATES[ProgramRole.LAUNDRY])
    living = cg.ProgramRoom("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC,
                            ROOM_TEMPLATES[ProgramRole.LIVING])
    hall = cg.ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION,
                          ROOM_TEMPLATES[ProgramRole.HALL])
    rooms = [living, hall, master, ensuite, bed1, bed2, laundry]

    alloc, rejection = _hub_allocation(rooms, hub_w_m=3.0)

    assert rejection is None, rejection
    all_seated = {r.zone_id for r in alloc.flank_west + alloc.flank_east + alloc.foot}
    assert all_seated == {"MASTER", "ENSUITE", "BEDROOM_1", "BEDROOM_2", "LAUNDRY"}
    assert laundry in alloc.foot or laundry in alloc.flank_west or laundry in alloc.flank_east


# ------------------------------------------------------------------ 5. end to end: access, shape, validation


def test_a_planned_laundry_room_is_circulation_accessible_and_within_its_template(monkeypatch):
    """§5/§6 end to end: HALL-only access (never through a bedroom, never an ensuite-style
    dependent), and no strip — the realized rectangle stays inside the template's aspect/area,
    exactly the C20 guarantee every other room already has."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    result = run_general_from_site(
        F.exact_rectangle(), plot_size_m=(20.0, 24.0),
        program=ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, target_built_area_m2=180,
                            laundry=LaundryRequirement(demand=LaundryDemand.ROOM,
                                                       source_text="חדר כביסה")))
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    zones = {z.zone_id: z for z in result.concept.concept.fixture.zones}
    laundry_rooms = [r for r in result.design.rooms if "LAUNDRY" in zones[r.zone_id].roles]
    assert len(laundry_rooms) == 1
    room = laundry_rooms[0]
    template = ROOM_TEMPLATES[ProgramRole.LAUNDRY]
    aspect = max(room.net_w_m, room.net_h_m) / min(room.net_w_m, room.net_h_m)
    assert aspect <= template.max_aspect_ratio + 1e-6, (room.net_w_m, room.net_h_m)
    assert room.net_w_m * room.net_h_m <= template.hard_max + 1e-6
    entered = sorted({d.a if d.b == room.zone_id else d.b
                      for d in result.design.interior_doors if room.zone_id in (d.a, d.b)})
    assert entered == ["HALL"], entered


def test_laundry_none_leaves_the_same_brief_byte_identical(monkeypatch):
    """§7A in miniature: the same programme, laundry NONE vs ROOM with the gate OFF, must realize
    the identical drawing — proof at the single-scenario level that the request alone changes
    nothing while the gate stays closed."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", False)
    program_without = ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, target_built_area_m2=180)
    program_with = ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, target_built_area_m2=180,
                               laundry=LaundryRequirement(demand=LaundryDemand.ROOM, source_text="x"))
    a = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program_without)
    b = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program_with)
    assert a.outcome is b.outcome is AdapterOutcome.SOLVED
    sig_a = sorted((r.zone_id, r.net_w_m, r.net_h_m, r.rect_m) for r in a.design.rooms)
    sig_b = sorted((r.zone_id, r.net_w_m, r.net_h_m, r.rect_m) for r in b.design.rooms)
    assert sig_a == sig_b


# ------------------------------------------------------------------ 6. allocation policy B (activation)


def _alloc_rooms():
    """MASTER/BEDROOM/HALL/LIVING/KITCHEN plus BATHROOM+TOILET (service) and LAUNDRY — a small,
    hand-computable programme for testing `scale_program`'s deficit branches directly."""
    return [
        cg.ProgramRoom("MASTER", ProgramRole.MASTER_BEDROOM, ZoneGroup.PRIVATE,
                       ROOM_TEMPLATES[ProgramRole.MASTER_BEDROOM]),
        cg.ProgramRoom("BEDROOM_1", ProgramRole.BEDROOM, ZoneGroup.PRIVATE,
                       ROOM_TEMPLATES[ProgramRole.BEDROOM]),
        cg.ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION, ROOM_TEMPLATES[ProgramRole.HALL]),
        cg.ProgramRoom("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC, ROOM_TEMPLATES[ProgramRole.LIVING]),
        cg.ProgramRoom("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC, ROOM_TEMPLATES[ProgramRole.KITCHEN]),
        cg.ProgramRoom("BATHROOM", ProgramRole.BATHROOM, ZoneGroup.SERVICE, ROOM_TEMPLATES[ProgramRole.BATHROOM]),
        cg.ProgramRoom("TOILET", ProgramRole.TOILET, ZoneGroup.SERVICE, ROOM_TEMPLATES[ProgramRole.TOILET]),
        cg.ProgramRoom("LAUNDRY", ProgramRole.LAUNDRY, ZoneGroup.SERVICE, ROOM_TEMPLATES[ProgramRole.LAUNDRY]),
    ]


def _targets_of(rooms, net_available_m2):
    return {zid: spec.net_area_target_m2 for zid, spec in cg.scale_program(rooms, net_available_m2).items()}


def test_a_deficit_without_laundry_is_the_unchanged_uniform_proportional_shrink():
    """Byte-for-byte proof that a programme with NO laundry room takes the ORIGINAL formula —
    the new branch in `scale_program` is unreachable without a `ProgramRole.LAUNDRY` room present."""
    rooms = [r for r in _alloc_rooms() if r.role is not ProgramRole.LAUNDRY]
    base = sum(r.template.target_area_m2 for r in rooms)
    net_available = base - 5.0   # a 5 m2 deficit
    targets = _targets_of(rooms, net_available)
    for r in rooms:
        start = r.template.target_area_m2
        expected = max(start - 5.0 * (start / base), r.template.min_area_m2)
        assert targets[r.zone_id] == pytest.approx(expected, abs=1e-6), r.zone_id


def test_a_small_laundry_deficit_is_absorbed_by_service_headroom_alone(monkeypatch):
    """Deficit fully covered by BATHROOM/TOILET headroom: every OTHER room — bedrooms, hall,
    public rooms, and the laundry room itself — keeps its own exact target, zero collateral."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = _alloc_rooms()
    base = sum(r.template.target_area_m2 for r in rooms)
    bath, wc = ROOM_TEMPLATES[ProgramRole.BATHROOM], ROOM_TEMPLATES[ProgramRole.TOILET]
    service_capacity = (bath.target_area_m2 - bath.min_area_m2) + (wc.target_area_m2 - wc.min_area_m2)
    deficit = service_capacity - 1.0   # inside the service headroom, with margin
    targets = _targets_of(rooms, base - deficit)
    for r in rooms:
        if r.role in (ProgramRole.BATHROOM, ProgramRole.TOILET):
            assert targets[r.zone_id] < r.template.target_area_m2 - 1e-6, r.zone_id
            assert targets[r.zone_id] >= r.template.min_area_m2 - 1e-6, r.zone_id
        else:
            assert targets[r.zone_id] == pytest.approx(r.template.target_area_m2, abs=1e-6), r.zone_id
    bath_share = (bath.target_area_m2 - bath.min_area_m2) / service_capacity
    wc_share = (wc.target_area_m2 - wc.min_area_m2) / service_capacity
    assert targets["BATHROOM"] == pytest.approx(bath.target_area_m2 - deficit * bath_share, abs=1e-6)
    assert targets["TOILET"] == pytest.approx(wc.target_area_m2 - deficit * wc_share, abs=1e-6)


def test_a_large_laundry_deficit_floors_service_then_cascades_to_everyone_else(monkeypatch):
    """Deficit exceeds service headroom: BATHROOM/TOILET land exactly at their floors (never
    below), and the remainder is shared proportionally among every other room — bedrooms,
    circulation and public rooms alike, none singled out or protected."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = _alloc_rooms()
    base = sum(r.template.target_area_m2 for r in rooms)
    bath, wc = ROOM_TEMPLATES[ProgramRole.BATHROOM], ROOM_TEMPLATES[ProgramRole.TOILET]
    service_capacity = (bath.target_area_m2 - bath.min_area_m2) + (wc.target_area_m2 - wc.min_area_m2)
    deficit = service_capacity + 3.0   # exceeds service headroom
    targets = _targets_of(rooms, base - deficit)
    assert targets["BATHROOM"] == pytest.approx(bath.min_area_m2, abs=1e-6)
    assert targets["TOILET"] == pytest.approx(wc.min_area_m2, abs=1e-6)
    others = [r for r in rooms if r.role not in (ProgramRole.BATHROOM, ProgramRole.TOILET)]
    other_base = sum(r.template.target_area_m2 for r in others)
    remaining = deficit - service_capacity
    for r in others:
        expected = max(r.template.target_area_m2 - remaining * (r.template.target_area_m2 / other_base),
                       r.template.min_area_m2)
        assert targets[r.zone_id] == pytest.approx(expected, abs=1e-6), r.zone_id


def test_laundry_deficit_never_shrinks_any_room_below_its_floor(monkeypatch):
    """Stress case: a deficit far larger than the whole programme's headroom. Every room still
    lands at or above its own `min_area_m2` — the floor holds through both tiers."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    rooms = _alloc_rooms()
    base = sum(r.template.target_area_m2 for r in rooms)
    targets = _targets_of(rooms, base * 0.2)   # an extreme, unrealizable shortfall
    for r in rooms:
        assert targets[r.zone_id] >= r.template.min_area_m2 - 1e-6, r.zone_id


def _tight_project(bedrooms: int, wet: int, laundry_requested: bool):
    """A `Project` whose plot/footprint are sized to the programme's OWN natural (no-surplus)
    gross area — deficit-inducing once a laundry room's target joins the base, exactly the
    `docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md` "tight" tier methodology. Self-contained here
    (not imported from spikes/) so this regression proof does not depend on spike-script code."""
    from datetime import UTC, datetime

    from app.projects.models import Project, SelectedFootprint, StreetSide, TaggedBool, TaggedInt

    base_program = ProgramSpec(bedrooms=bedrooms, safe_room=False, wet_rooms=wet, open_plan_living=True)
    rooms = build_room_program(_spec(base_program))
    target = target_gross_area_m2(rooms)
    aspect = 0.82
    fd = (target / aspect) ** 0.5
    fw = target / fd
    now = datetime.now(UTC)
    footprint = SelectedFootprint(source="CUSTOM", shape_type="RECTANGLE", target_area_m2=target,
                                  width_m=fw, depth_m=fd, area_m2=round(fw * fd, 4))
    return Project(
        project_id="TEST", city="TLV", street="S", plot_area_m2=(fw + 4) * (fd + 4),
        plot_width_m=fw + 4, plot_depth_m=fd + 4, street_facing_side=StreetSide.north,
        built_area_m2=round(target, 2), description="", status="active",
        created_at=now, updated_at=now, selected_footprint=footprint,
        floors=TaggedInt(value=1, source="inferred"),
        bedrooms=TaggedInt(value=bedrooms, source="requested"),
        safe_room=TaggedBool(value=False, source="unknown"),
        parking_spaces=TaggedInt(value=0, source="requested"),
        wet_rooms=TaggedInt(value=wet, source="requested"),
        open_plan=TaggedBool(value=True, source="requested"),
        laundry_requested=TaggedBool(value=laundry_requested,
                                     source="requested" if laundry_requested else "inferred"),
        laundry_source_text="חדר כביסה" if laundry_requested else "",
        requirements_parsed_at=now,
    )


def test_end_to_end_bathroom_absorbs_the_deficit_first(monkeypatch):
    """The activation decision's own case (3BR/2wet, tight target —
    docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md): with the laundry room planned, BATHROOM's realized
    total lands below its own combined template TARGET (never below its FLOOR) — the fixed,
    unconfounded reference this test (and the disclosure notice, §7) both use, since a second
    "without laundry" solve can land on a genuinely different footprint candidate and confound a
    before/after comparison (documented in the investigation report)."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    from app.demo.service import generate_demo_design

    result = generate_demo_design(_tight_project(3, 2, laundry_requested=True))
    by_role: dict[str, float] = {}
    for r in result.design.rooms:
        by_role[r.type] = by_role.get(r.type, 0.0) + r.area_m2
    assert "LAUNDRY" in by_role
    bath = ROOM_TEMPLATES[ProgramRole.BATHROOM]
    bathroom_count = sum(1 for r in result.design.rooms if r.type == "BATHROOM")
    assert bathroom_count >= 1
    assert by_role["BATHROOM"] < bath.target_area_m2 * bathroom_count - 1e-6
    assert by_role["BATHROOM"] >= bath.min_area_m2 * bathroom_count - 1e-6


# ------------------------------------------------------------------ 7. disclosure notice


def test_no_laundry_room_never_carries_a_laundry_notice():
    """§3: the notice is contained to plans with a laundry room — every existing, non-laundry
    plan (the whole regression corpus) must see `laundry_notice` stay `None`."""
    from app.demo.service import generate_demo_design

    result = generate_demo_design(_tight_project(3, 2, laundry_requested=False))
    assert result.design.quality is not None
    assert result.design.quality.laundry_notice is None


def test_a_laundry_deficit_room_carries_a_notice_naming_the_absorbing_room(monkeypatch):
    """§3: when BATHROOM is realized below its own target because of the laundry room, the notice
    names it, is not empty, is not presented as a validation issue, and is not a refusal."""
    monkeypatch.setattr(cg, "LAUNDRY_ROOM_ENABLED", True)
    from app.demo.service import generate_demo_design

    result = generate_demo_design(_tight_project(3, 2, laundry_requested=True))
    assert result.design.validation.passed
    quality = result.design.quality
    assert quality is not None
    assert quality.laundry_notice is not None
    assert "כביסה" in quality.laundry_notice
    assert "חדר רחצה" in quality.laundry_notice or "רחצה" in quality.laundry_notice


def test_laundry_notice_uses_the_fixed_template_target_not_a_second_solve():
    """Direct unit proof of `_laundry_redistribution_notice`'s own logic, independent of the
    solver: a synthetic design with a LAUNDRY room and a BATHROOM realized below its template
    target produces a notice naming BATHROOM; the same design without a LAUNDRY room produces
    none, even though BATHROOM is realized identically low."""
    from app.demo.contract import _laundry_redistribution_notice
    from app.vertical_slice.design_output import RoomOut

    def room(zone_id, roles, area):
        return RoomOut(zone_id=zone_id, roles=roles, rect_m=(0.0, 0.0, 2.0, area / 2.0),
                       net_w_m=2.0, net_h_m=area / 2.0, net_area_m2=area, walls={}, wall_facts={})

    bath_template = ROOM_TEMPLATES[ProgramRole.BATHROOM]
    low_bath_area = bath_template.target_area_m2 * 0.5   # well under the notice threshold

    class _Design:
        def __init__(self, rooms):
            self.rooms = rooms

    with_laundry = _Design([
        room("BATH_1", ("BATHROOM",), low_bath_area),
        room("LAUNDRY", ("LAUNDRY",), ROOM_TEMPLATES[ProgramRole.LAUNDRY].target_area_m2),
    ])
    without_laundry = _Design([room("BATH_1", ("BATHROOM",), low_bath_area)])

    notice = _laundry_redistribution_notice(with_laundry)
    assert notice is not None
    assert "רחצה" in notice
    assert _laundry_redistribution_notice(without_laundry) is None


def test_laundry_notice_says_nothing_when_every_room_meets_its_target():
    """A LAUNDRY room present, but every OTHER room realized at or above its own target — no
    notice, since nothing was actually redistributed away from anyone."""
    from app.demo.contract import _laundry_redistribution_notice
    from app.vertical_slice.design_output import RoomOut

    def room(zone_id, roles, area):
        return RoomOut(zone_id=zone_id, roles=roles, rect_m=(0.0, 0.0, 2.0, area / 2.0),
                       net_w_m=2.0, net_h_m=area / 2.0, net_area_m2=area, walls={}, wall_facts={})

    class _Design:
        def __init__(self, rooms):
            self.rooms = rooms

    design = _Design([
        room("BATH_1", ("BATHROOM",), ROOM_TEMPLATES[ProgramRole.BATHROOM].target_area_m2),
        room("LAUNDRY", ("LAUNDRY",), ROOM_TEMPLATES[ProgramRole.LAUNDRY].target_area_m2),
    ])
    assert _laundry_redistribution_notice(design) is None


def test_a_low_safe_room_is_never_named_in_the_notice_with_or_without_laundry():
    """2026-09-17, post-activation fix: SAFE_ROOM realizes a little under its own template target
    from ordinary row-depth geometry alone (elasticity 0 — it never moves through `scale_program`'s
    surplus/deficit math either way, in either direction), independent of any laundry room. Naming
    it in `laundry_notice` would be a false positive — found by the end-to-end smoke test on a
    brief that also requested a safe room. `_LAUNDRY_NOTICE_EXCLUDED_ROLES` excludes it explicitly.

    Two cases, both required: a low SAFE_ROOM with NO laundry room at all must not produce a
    notice (there is nothing to disclose — the notice only exists for laundry-containing plans in
    the first place); and a low SAFE_ROOM alongside an actual laundry-caused deficit (a low
    BATHROOM too) must still omit SAFE_ROOM specifically, while still naming the room that IS a
    real redistribution casualty."""
    from app.demo.contract import _laundry_redistribution_notice
    from app.vertical_slice.design_output import RoomOut

    def room(zone_id, roles, area):
        return RoomOut(zone_id=zone_id, roles=roles, rect_m=(0.0, 0.0, 2.0, area / 2.0),
                       net_w_m=2.0, net_h_m=area / 2.0, net_area_m2=area, walls={}, wall_facts={})

    safe_room_template = ROOM_TEMPLATES[ProgramRole.SAFE_ROOM]
    low_safe_room_area = safe_room_template.target_area_m2 * 0.5   # well under the notice threshold

    class _Design:
        def __init__(self, rooms):
            self.rooms = rooms

    # No laundry room at all — a low SAFE_ROOM here is the pre-existing, laundry-independent
    # geometry property the fix's commit message measured directly (9.3 m2 vs a 10.5 m2 target).
    no_laundry = _Design([room("SAFE_1", ("SAFE_ROOM",), low_safe_room_area)])
    assert _laundry_redistribution_notice(no_laundry) is None

    # A laundry room present AND a real redistribution casualty (BATHROOM) alongside the same low
    # SAFE_ROOM: the notice must fire (BATHROOM is a genuine casualty) but never name SAFE_ROOM.
    with_laundry_and_low_bathroom = _Design([
        room("SAFE_1", ("SAFE_ROOM",), low_safe_room_area),
        room("BATH_1", ("BATHROOM",), ROOM_TEMPLATES[ProgramRole.BATHROOM].target_area_m2 * 0.5),
        room("LAUNDRY", ("LAUNDRY",), ROOM_TEMPLATES[ProgramRole.LAUNDRY].target_area_m2),
    ])
    notice = _laundry_redistribution_notice(with_laundry_and_low_bathroom)
    assert notice is not None
    assert "רחצה" in notice
    assert 'ממ"ד' not in notice


# ------------------------------------------------------------------ 6. exterior wall + window (Issue #21, AC-1)


_GRID_LEG_M = 3.0
_LOOSE = dict(net_area_min_m2=1.0, net_area_target_m2=9.0, net_area_max_m2=99.0,
             min_short_side_m=0.1, max_aspect_ratio=99.0)


def _grid_fixture(center_roles: tuple[ProgramRole, ...]) -> tuple[Fixture, dict[str, Rect], Rect]:
    """A|TOP/CENTER/BOTTOM|C, each leg `_GRID_LEG_M`. CENTER touches none of the four wing edges —
    the one genuinely INTERIOR room C19 exists to catch. Mirrors `test_exposure_policy.py`'s own
    `_grid_fixture` (kept self-contained here rather than cross-imported, same reasoning as that
    file's own module docstring)."""
    leg_u = m_to_u(_GRID_LEG_M)
    rects = {
        "A": Rect(0, 0, leg_u, 3 * leg_u),
        "TOP": Rect(leg_u, 0, leg_u, leg_u),
        "CENTER": Rect(leg_u, leg_u, leg_u, leg_u),
        "BOTTOM": Rect(leg_u, 2 * leg_u, leg_u, leg_u),
        "C": Rect(2 * leg_u, 0, leg_u, 3 * leg_u),
    }
    footprint = Rect(0, 0, 3 * leg_u, 3 * leg_u)
    tree = Split(Cut.V, Leaf("A"),
                Split(Cut.V,
                      Split(Cut.H, Leaf("TOP"), Split(Cut.H, Leaf("CENTER"), Leaf("BOTTOM"), None), None),
                      Leaf("C"), None),
                None)
    wing = Wing("W", 0, 0, footprint.w, footprint.h, tree)
    specs = (
        ZoneSpec("A", (ProgramRole.STORAGE,), **_LOOSE),
        ZoneSpec("TOP", (ProgramRole.STORAGE,), **_LOOSE),
        ZoneSpec("CENTER", center_roles, **_LOOSE),
        ZoneSpec("BOTTOM", (ProgramRole.STORAGE,), **_LOOSE),
        ZoneSpec("C", (ProgramRole.STORAGE,), **_LOOSE),
    )
    fixture = Fixture("GRID", (wing,), specs, DesiredAccessTopology(()))
    return fixture, rects, footprint


def _validate_grid(center_roles: tuple[ProgramRole, ...]):
    fixture, rects, footprint = _grid_fixture(center_roles)
    walls = {
        (zone_id, side): (WallType.EXTERIOR if side in envelope_sides(rect, footprint)
                          else WallType.PARTITION)
        for zone_id, rect in rects.items() for side in Side
    }
    windows = generate_windows(fixture, rects, footprint)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), (), entrance,
                    site_stage.classify_garden(spec, plot, footprint, ()))
    dummy_entrance_door = Door("OUTSIDE", "A", ConnectionKind.DOOR, 1.0, (0, 0), "horizontal",
                               False, 0.0)
    return validate(fixture, rects, walls, [], dummy_entrance_door, windows, [], site,
                    skip_site_checks=True)


def _check(report, check_id: str):
    return next(c for c in report.checks if c.check_id == check_id)


def test_c19_fails_on_an_interior_laundry_room():
    """AC-1: LAUNDRY is REQUIRED/REQUIRED in `exposure_policy.EXPOSURE_POLICY` — an interior
    LAUNDRY room (no exterior wall at all) fails C19, exactly like the habitable roles Issue #19
    already covers. Same grid fixture as `test_exposure_policy.py`'s C19 proof."""
    report = _validate_grid((ProgramRole.LAUNDRY,))
    c19 = _check(report, "C19")
    assert not c19.passed
    assert "CENTER" in c19.detail


def test_c8_passes_with_a_service_sized_window_on_an_exterior_laundry_room():
    """AC-1: a LAUNDRY room ON an exterior wall gets a real window — sized at the SERVICE-window
    minimum (0.6 m, `LAUNDRY_WINDOW_MIN_WIDTH_M`), narrower than a habitable room's 0.9 m — and
    `ventilation_status` reports `EXTERIOR_WINDOW`, the same status AC-1 requires a delivered
    laundry room to always carry."""
    fixture, rects, footprint = _grid_fixture((ProgramRole.STORAGE,))
    # LAUNDRY on an exterior leg (`A`, full west envelope); CENTER stays STORAGE (no exposure
    # requirement), so this fixture's only exterior-required room is the one under test.
    exterior_fixture = Fixture("GRID_EXT", fixture.wings,
                               tuple(ZoneSpec(z.zone_id, (ProgramRole.LAUNDRY,) if z.zone_id == "A"
                                             else z.roles, **_LOOSE) for z in fixture.zones),
                               DesiredAccessTopology(()))
    windows = generate_windows(exterior_fixture, rects, footprint)
    window = next(w for w in windows if w.zone_id == "A")
    assert window.placeable, window
    assert window.width_m >= LAUNDRY_WINDOW_MIN_WIDTH_M - 1e-9
    assert window.ventilation_status == EXTERIOR_WINDOW

    walls = {
        (zone_id, side): (WallType.EXTERIOR if side in envelope_sides(rect, footprint)
                          else WallType.PARTITION)
        for zone_id, rect in rects.items() for side in Side
    }
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), (), entrance,
                    site_stage.classify_garden(spec, plot, footprint, ()))
    dummy_entrance_door = Door("OUTSIDE", "A", ConnectionKind.DOOR, 1.0, (0, 0), "horizontal",
                               False, 0.0)
    report = validate(exterior_fixture, rects, walls, [], dummy_entrance_door, windows, [], site,
                      skip_site_checks=True)
    assert _check(report, "C19").passed
    assert _check(report, "C8").passed


# ------------------------------------------------------------------ 7. machine bay (Issue #21, AC-2)


def test_template_short_side_is_the_machine_bay():
    """AC-2: the LAUNDRY template's minimum short side is 1.7 m (0.6 m machine + 0.6 m optional
    dryer + 0.5 m circulation)."""
    assert ROOM_TEMPLATES[ProgramRole.LAUNDRY].min_short_side_m == 1.7


def test_a_room_at_the_template_floor_always_inscribes_the_washing_machine_footprint():
    """AC-2: any LAUNDRY room realized at (or above) its template's short-side floor always fits
    the WASHING_MACHINE furniture envelope (0.6 m wide, 0.9 m clearance in front — C9's screen) —
    guaranteed by construction now that the floor (1.7 m on both sides) exceeds the envelope's own
    longer side (1.5 m), not left to chance at the solver."""
    zone = ZoneSpec("LAUNDRY", (ProgramRole.LAUNDRY,), net_area_min_m2=2.5, net_area_target_m2=4.0,
                    net_area_max_m2=8.0, min_short_side_m=1.7, max_aspect_ratio=3.0)
    envelope = min_furniture_envelope_m(zone)
    assert envelope == (0.6, 1.5)
    # The floor shape (short side exactly at the template minimum, on both axes) always fits —
    # 1.7 m exceeds the envelope's own longer side (1.5 m) in either orientation.
    assert furniture_envelope_fits(zone, 1.7, 1.7) is True
    # A room narrower than the envelope's longer side genuinely cannot inscribe it — the screen is
    # a real check, not vacuously true regardless of the room's shape.
    assert furniture_envelope_fits(zone, 1.4, 1.4) is False
