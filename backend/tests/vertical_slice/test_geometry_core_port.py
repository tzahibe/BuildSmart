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
