"""Fidelity checks for the Geometry Core port (backend/spikes/geometry_core -> app/vertical_slice
/geometry_core). Not a re-run of the spike's own 34 regression tests — those stay authoritative
for the algorithm and are not duplicated here. These checks guard the specific invariants the
vertical slice's later stages (windows, validation) depend on, using the PRODUCTION import path.
"""
from __future__ import annotations

import pytest

from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Side,
    Split,
    WallType,
    Wing,
    ZoneSpec,
    half_thickness_units,
    m_to_u,
)


def _tiny_safe_room_fixture() -> Fixture:
    zones = (
        ZoneSpec("LIVING", (ProgramRole.LIVING,), 18, 22, 28, 3.0, max_aspect_ratio=3.0),
        ZoneSpec("SAFE_ROOM", (ProgramRole.SAFE_ROOM,), 9.0, 10.0, 13.0, 2.4, max_aspect_ratio=3.0),
    )
    tree = Split(Cut.V, Leaf("LIVING"), Leaf("SAFE_ROOM"), None)
    wing = Wing("W", 0, 0, m_to_u(7.5), m_to_u(5.5), tree)
    access = DesiredAccessTopology((DesiredAccessEdge("LIVING", "SAFE_ROOM", ConnectionKind.DOOR),))
    return Fixture("TINY", (wing,), zones, access)


def test_ported_engine_raises_the_renamed_exception_not_the_spike_one():
    with pytest.raises(GeometryInfeasible):
        solve_fixture(_infeasible_fixture())


def _infeasible_fixture() -> Fixture:
    zones = (ZoneSpec("A", (ProgramRole.BEDROOM,), 50, 55, 60, 8.0),)
    wing = Wing("W", 0, 0, m_to_u(2.0), m_to_u(2.0), Leaf("A"))
    return Fixture("TOO_SMALL", (wing,), zones, DesiredAccessTopology(()))


def test_safe_room_is_rc_on_every_side_in_the_ported_engine():
    res = solve_fixture(_tiny_safe_room_fixture())
    for side in Side:
        assert res.walls[("SAFE_ROOM", side)] is WallType.RC_SAFE_ROOM


def test_grid_alignment_guard_still_rejects_non_grid_thickness_in_the_port():
    with pytest.raises(ValueError, match="not grid-aligned"):
        half_thickness_units(0.25, label="PORTED_TEST")


def test_safe_room_in_open_group_still_rejected_eagerly_in_the_port():
    zones = (
        ZoneSpec("LIVING", (ProgramRole.LIVING,), 18, 22, 28, 3.0),
        ZoneSpec("SAFE_ROOM", (ProgramRole.SAFE_ROOM,), 9.0, 10.0, 13.0, 2.4),
    )
    wing = Wing("W", 0, 0, m_to_u(9.0), m_to_u(6.0), Split(Cut.V, Leaf("LIVING"), Leaf("SAFE_ROOM"), None))
    with pytest.raises(ValueError, match="SAFE_ROOM"):
        Fixture("BAD", (wing,), zones, DesiredAccessTopology(()), open_groups=(("LIVING", "SAFE_ROOM"),))


# ------------------------------------------------------------------ forced-leaf precheck

def _corridor_fixture(hall_w_m: float, depth_m: float, forced: bool) -> Fixture:
    """A 1.4 m corridor beside a room, the full depth of the wing: under aspect 12 a corridor that
    narrow can run about 16 m, not 22."""
    zones = (
        ZoneSpec("HALL", (ProgramRole.HALL,), 8.0, 25.0, 60.0, 1.2, max_aspect_ratio=12.0),
        ZoneSpec("ROOM", (ProgramRole.LIVING,), 30.0, 60.0, 500.0, 3.0, max_aspect_ratio=12.0),
    )
    tree = Split(Cut.V, Leaf("HALL"), Leaf("ROOM"), m_to_u(hall_w_m) if forced else None)
    wing = Wing("W", 0, 0, m_to_u(hall_w_m + 5.0), m_to_u(depth_m), tree)
    return Fixture("CORRIDOR", (wing,), zones, DesiredAccessTopology(()))


def test_a_leaf_its_forced_cuts_fix_outside_its_shape_curve_is_refused_before_any_composition():
    from app.vertical_slice.geometry_core.engine import forced_leaf_refusal
    refusal = forced_leaf_refusal(_corridor_fixture(1.4, 22.0, forced=True))
    assert refusal is not None and "HALL" in refusal and "1.4x22.0" in refusal
    with pytest.raises(GeometryInfeasible, match="forced cuts fix"):
        solve_fixture(_corridor_fixture(1.4, 22.0, forced=True))


def test_the_precheck_refuses_only_what_the_solver_refuses():
    """Same corridor at a depth its aspect allows: nothing to refuse, and the solve goes through
    at the forced width. Unforced, the solver may widen the corridor itself, so the precheck says
    nothing about it."""
    from app.vertical_slice.geometry_core.engine import forced_leaf_refusal
    assert forced_leaf_refusal(_corridor_fixture(1.4, 13.0, forced=True)) is None
    assert solve_fixture(_corridor_fixture(1.4, 13.0, forced=True)).rects["HALL"].w == m_to_u(1.4)
    assert forced_leaf_refusal(_corridor_fixture(1.4, 22.0, forced=False)) is None
    assert solve_fixture(_corridor_fixture(1.4, 22.0, forced=False)).rects["HALL"].w > m_to_u(1.4)
