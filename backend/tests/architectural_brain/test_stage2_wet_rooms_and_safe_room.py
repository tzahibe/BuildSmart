"""Issue #134 — Stage 2 (B/2) AC-2: wet rooms and SAFE_ROOM both reach the validator chain.

Two scenarios, not one, and this is itself a finding `repair.py`'s own module docstring documents:
the row realizer supports at most ONE gated-PRIVATE-room arm per connected row, so a bedroom (with
its own ensuite, sharing that SAME arm) and a SAFE_ROOM cannot both sit in ONE realized row here —
`test_stage2_end_to_end.py` proves the milestone-1 brief's own wet room (an ensuite) reaches C17/C29
passing; this file adds the SAFE_ROOM half on its own minimal scenario (no competing bedroom),
proving `stage2.realizer`'s C4/RC_SAFE_ROOM wiring independently of that limit.
"""
from __future__ import annotations

from app.vertical_slice.constraints import derive_safe_room_constraint
from app.vertical_slice.geometry_core.model import ProgramRole, Side, WallType
from app.vertical_slice.stage2 import pipeline
from app.vertical_slice.stage2.contract import RealizerInput, RealizerRefusal, RowWing, ZoneIntent
from app.vertical_slice.stage2.realizer import realize_layout


def test_milestone_1_wet_room_reaches_c17_and_c29_passing():
    """The milestone-1 brief's own ensuite (BATH_1, host MASTER) is a REAL wet room threaded
    through `RealizerInput.wet_rooms` (Required Behaviour 5's own fix for #117's gap: its own
    realizer never passed `wet_rooms` to `validate()` at all, so C17/C29 could not run)."""
    run = pipeline.run_milestone_1()
    assert run.ok, run.refusal
    assert len(run.repair.wet_rooms) == 1
    checks = {c.check_id: c for c in run.realized.report.checks}
    assert checks["C17"].passed, checks["C17"].detail
    assert checks["C29"].passed, checks["C29"].detail
    assert "BATH_1" in run.realized.rects


def _safe_room_only_scenario() -> RealizerInput:
    living = ZoneIntent("LIVING_0", ProgramRole.LIVING, None, 24.0, 16.0, 40.0, 3.0, 2.4)
    hall = ZoneIntent("HALL_1", ProgramRole.HALL, None, 6.5, 5.0, 30.0, 1.2, 8.0)
    safe = ZoneIntent("SAFE_ROOM", ProgramRole.SAFE_ROOM, None, 12.0, 9.0, 14.0, 2.2, 2.5)
    height_m = 3.9
    width_m = round((24.0 + 6.5 + 12.0) / height_m, 2)
    row = RowWing(wing_id="row0", width_m=width_m, height_m=height_m,
                  slots=("LIVING_0", "HALL_1", "SAFE_ROOM"),
                  zones={"LIVING_0": living, "HALL_1": hall, "SAFE_ROOM": safe}, groups={})
    return RealizerInput(name="safe-room-only-scenario", wings=(row,), wet_rooms=())


def test_safe_room_reaches_c4_passing_with_rc_walls():
    """A minimal scenario (no competing bedroom — see module docstring) proving SAFE_ROOM's own
    C4 gate (RC_SAFE_ROOM walls on every side, regulated net-area minimum, an authoritative
    constraint realized) passes through `stage2.realizer`, independently of the milestone-1
    brief's own one-arm limit."""
    layout = _safe_room_only_scenario()
    result = realize_layout(layout, safe_room_constraint=derive_safe_room_constraint(True))
    assert result.ok, getattr(result, "detail", result)
    checks = {c.check_id: c for c in result.report.checks}
    assert checks["C4"].passed, checks["C4"].detail
    for side in Side:
        assert result.walls[("SAFE_ROOM", side)] is WallType.RC_SAFE_ROOM


def test_safe_room_dropped_zone_fails_c4_when_authoritative():
    """The negative case: an authoritative SAFE_ROOM constraint with NO realized safe room at all
    must fail C4 (`constraints.SAFE_ROOM_NOT_REALIZED_DETAIL`) — never a silent pass."""
    living = ZoneIntent("LIVING_0", ProgramRole.LIVING, None, 24.0, 16.0, 40.0, 3.0, 2.4)
    hall = ZoneIntent("HALL_1", ProgramRole.HALL, None, 8.0, 5.0, 30.0, 1.2, 8.0)
    height_m = 3.9
    row = RowWing(wing_id="row0", width_m=round((24.0 + 8.0) / height_m, 2), height_m=height_m,
                  slots=("LIVING_0", "HALL_1"), zones={"LIVING_0": living, "HALL_1": hall},
                  groups={})
    layout = RealizerInput(name="no-safe-room-scenario", wings=(row,), wet_rooms=())
    result = realize_layout(layout, safe_room_constraint=derive_safe_room_constraint(True))
    assert isinstance(result, RealizerRefusal)
    assert "C4" in result.detail or "SAFE_ROOM" in result.detail
