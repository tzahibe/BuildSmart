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
from app.vertical_slice.concept_generator import (
    ROOM_TEMPLATES,
    ZoneGroup,
    _access_intact,
    _hub_allocation,
    _rows_for_width,
    _rows_of,
    build_room_program,
    room_depth_band_m,
)
from app.vertical_slice.general_pipeline import run_general_from_site
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt, build_buildable_region
from app.vertical_slice.spec import (
    ArchitecturalSpec,
    LaundryDemand,
    LaundryRequirement,
    PlotSpec,
    ProgramSpec,
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


def test_gate_off_never_emits_a_room_even_when_requested():
    """The default state (`LAUNDRY_ROOM_ENABLED` as shipped) must be inert: normal generation for
    every existing brief is byte-identical to before this phase, whatever `ProgramSpec.laundry`
    says."""
    assert cg.LAUNDRY_ROOM_ENABLED is False
    rooms = build_room_program(_spec(_program()))
    assert not any(r.role is ProgramRole.LAUNDRY for r in rooms)


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
    nothing until the gate opens."""
    program_without = ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, target_built_area_m2=180)
    program_with = ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, target_built_area_m2=180,
                               laundry=LaundryRequirement(demand=LaundryDemand.ROOM, source_text="x"))
    assert cg.LAUNDRY_ROOM_ENABLED is False
    a = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program_without)
    b = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0), program=program_with)
    assert a.outcome is b.outcome is AdapterOutcome.SOLVED
    sig_a = sorted((r.zone_id, r.net_w_m, r.net_h_m, r.rect_m) for r in a.design.rooms)
    sig_b = sorted((r.zone_id, r.net_w_m, r.net_h_m, r.rect_m) for r in b.design.rooms)
    assert sig_a == sig_b
