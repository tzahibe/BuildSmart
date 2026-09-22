"""Issue #35 — the SAFE_ROOM/MAMAD `TypedConstraint` survives requirement -> constraint -> concept
-> geometry -> validator -> contract, and any stage that drops it refuses rather than delivering a
plan without the room.

`test_constraint_source_user_and_none` (AC-1) checks derivation, both directly
(`derive_safe_room_constraint`, `ArchitecturalSpec.safe_room_constraint`) and through the real
parser-to-spec path (`spec_for`). `test_dropping_the_room_at_any_stage_refuses` (AC-2)
fault-injects at each of the three stages the Issue names: after concept generation, in the
validator (the geometry-realization check), and the pipeline's own escalation of that check into a
product refusal — proving none of them can silently deliver a plan without an authoritative safe
room.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.demo import service as svc
from app.demo.requirements_view import spec_for
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import site as site_stage
from app.vertical_slice.constraints import (
    NO_SAFE_ROOM_CONSTRAINT,
    SAFE_ROOM_MIN_AREA_M2,
    SAFE_ROOM_NOT_REALIZED_DETAIL,
    ConstraintKind,
    ConstraintSource,
    SafeRoomDropped,
    TypedConstraint,
    derive_safe_room_constraint,
)
from app.vertical_slice.doors import build_entrance_door, generate_interior_doors
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
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import ValidationReport, validate
from tests.vertical_slice.test_hub_guard import NARROW_DEEP, WIDE_SQUARE, _project


def _spec(program: ProgramSpec) -> ArchitecturalSpec:
    return ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=program)


# --------------------------------------------------------------------------- AC-1: derivation

def test_constraint_source_user_and_none():
    requested = derive_safe_room_constraint(True)
    assert requested == TypedConstraint(ConstraintKind.SAFE_ROOM, ConstraintSource.USER, True,
                                        SAFE_ROOM_MIN_AREA_M2)

    none = derive_safe_room_constraint(False)
    assert none == NO_SAFE_ROOM_CONSTRAINT
    assert none.source is ConstraintSource.NONE and not none.authoritative

    # `ArchitecturalSpec.safe_room_constraint` is derived, not stored: it tracks `program.safe_room`.
    assert _spec(ProgramSpec(safe_room=True)).safe_room_constraint.source is ConstraintSource.USER
    assert _spec(ProgramSpec(safe_room=False)).safe_room_constraint is NO_SAFE_ROOM_CONSTRAINT

    # The real parser-to-spec path (`spec_for`, `app/demo/requirements_view.py`): a user-requested
    # safe room in the project's own (possibly corrected) requirements resolves to USER, and a
    # brief that never requested one resolves to NONE — never invented.
    with_safe_room = spec_for(_project(WIDE_SQUARE)).safe_room_constraint
    assert with_safe_room.source is ConstraintSource.USER and with_safe_room.authoritative
    without_safe_room = spec_for(_project(NARROW_DEEP)).safe_room_constraint
    assert without_safe_room.source is ConstraintSource.NONE and not without_safe_room.authoritative


# --------------------------------------------------------------------------- AC-2: fault injection

def _row_fixture_without_safe_room() -> Fixture:
    """A HALL + MASTER row that never declares a SAFE_ROOM zone at all — the same thing, from
    C4's perspective, as a zone the concept declared but the solver never gave a rectangle to
    (see the comment on the check itself in `validation.py`)."""
    tree = Split(Cut.V, Leaf("HALL"), Leaf("MASTER"), None)
    wing = Wing("W", 0, 0, m_to_u(10.0), m_to_u(4.0), tree)
    access = DesiredAccessTopology((DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),))
    zones = (
        ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 10, 20, 1.2, 8.0),
        ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 25, 2.5),
    )
    return Fixture("NO_SAFE_ROOM", (wing,), zones, access)


def _validate_row(fixture: Fixture, constraint) -> ValidationReport:
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
    return validate(fixture, solve.rects, solve.walls, doors, entrance_door, [], [], site,
                    constraint=constraint)


def test_dropping_the_room_at_any_stage_refuses(monkeypatch):
    # --- Stage 1: after concept generation. `generate_concepts` asserts the programme it is about
    # to build candidates from still carries the room; a fault that strips it (a fallback ladder or
    # a rearrangement gone wrong, simulated here directly) raises `SafeRoomDropped`.
    real_build_room_program = generator.build_room_program

    def _stripped(spec: ArchitecturalSpec):
        return [r for r in real_build_room_program(spec) if r.role is not ProgramRole.SAFE_ROOM]

    monkeypatch.setattr(generator, "build_room_program", _stripped)
    program = ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2)
    adapter = adapt(build_buildable_region(F.exact_rectangle()))
    with pytest.raises(SafeRoomDropped):
        generator.generate_concepts(_spec(program), list(adapter.candidates))
    monkeypatch.setattr(generator, "build_room_program", real_build_room_program)

    # The same fault, observed through the real product entry point: `generate_demo_design`
    # catches `SafeRoomDropped` from the concept stage and turns it into a refusal, never a plan.
    monkeypatch.setattr(generator, "build_room_program", _stripped)
    with pytest.raises(svc.DemoGenerationError) as exc:
        svc.generate_demo_design(_project(WIDE_SQUARE))
    assert exc.value.code == "SAFE_ROOM_DROPPED"
    monkeypatch.setattr(generator, "build_room_program", real_build_room_program)

    # --- Stage 2: after geometry realization, in the validator. C4 is extended to fail when an
    # authoritative constraint has no realized safe-room zone — checked here directly on a fixture
    # that never carries one, which is exactly what a fallback ladder or candidate swap that drops
    # the room produces by the time geometry is realized.
    authoritative = derive_safe_room_constraint(True)
    report = _validate_row(_row_fixture_without_safe_room(), authoritative)
    assert not report.ok
    c4 = next(c for c in report.checks if c.check_id == "C4")
    assert not c4.passed and SAFE_ROOM_NOT_REALIZED_DETAIL in c4.detail

    # A non-authoritative (NONE) constraint never faults the same fixture — nothing was dropped
    # because nothing was ever required.
    report_none = _validate_row(_row_fixture_without_safe_room(), derive_safe_room_constraint(False))
    c4_none = next(c for c in report_none.checks if c.check_id == "C4")
    assert c4_none.passed

    # --- Stage 3: the pipeline's own escalation of that C4 failure into a product refusal — the
    # path a candidate swap or alternative selection takes when EVERY outline's best candidate
    # still fails to realize the room: `_finish` is the terminal refusal point once every outline
    # has been tried, and this is the first thing it checks.
    result = SimpleNamespace(validation=report)
    with pytest.raises(svc.DemoGenerationError) as exc:
        svc._finish(project=None, spec=_spec(program), result=result, preference_dropped=False)
    assert exc.value.code == "SAFE_ROOM_DROPPED"
