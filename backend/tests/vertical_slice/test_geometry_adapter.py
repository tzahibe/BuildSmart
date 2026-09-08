"""The Rect <-> Region seam, and the layering rules that keep it a seam."""
from __future__ import annotations

import pytest

from app.geometry_domain.primitives import Region, Ring
from app.geometry_domain.walls import BoundaryContext, Construction
from app.vertical_slice.geometry_adapter import (
    assert_units_agree,
    envelope_sides,
    rect_to_region,
    region_to_rect,
    wall_facts_for_side,
)
from app.vertical_slice.geometry_core.model import Rect, Side, WallType, m_to_u


def test_grid_unit_is_the_same_on_both_sides_of_the_seam():
    assert_units_agree()


def test_rect_converts_to_a_region_exactly():
    rect = Rect(0, 0, m_to_u(12.0), m_to_u(14.2))
    region = rect_to_region(rect)
    assert region.area() == pytest.approx(170.4)
    assert region.bounds() == pytest.approx((0.0, 0.0, 12.0, 14.2))


def test_rect_region_roundtrip_is_lossless():
    rect = Rect(m_to_u(4.0), m_to_u(5.5), m_to_u(12.0), m_to_u(14.2))
    assert region_to_rect(rect_to_region(rect)) == rect


def test_region_with_a_hole_is_refused_rather_than_approximated():
    """Silent approximation in this direction is exactly the bug the architecture exists to
    prevent: it would hand the solver space that does not exist."""
    region = Region(Ring.rectangle(0, 0, 10, 10), (Ring.rectangle(4, 4, 2, 2),))
    assert region_to_rect(region) is None


def test_curved_region_is_refused():
    region = Region(Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)], [0.0, 0.5, 0.0, 0.0]))
    assert region_to_rect(region) is None


def test_non_axis_aligned_region_is_refused():
    region = Region(Ring.from_points([(0, 0), (4, 1), (3, 5), (-1, 4)]))
    assert region_to_rect(region) is None


def test_off_grid_region_is_refused_rather_than_rounded():
    region = Region(Ring.rectangle(0.0, 0.0, 3.333, 2.0))
    assert region_to_rect(region) is None


def test_l_shaped_region_is_refused():
    region = Region(Ring.from_points([(0, 0), (10, 0), (10, 6), (4, 6), (4, 10), (0, 10)]))
    assert region_to_rect(region) is None


# ------------------------------------------------------------------ exposure & wall facts

def _footprint() -> Rect:
    return Rect(m_to_u(4.0), m_to_u(5.5), m_to_u(12.0), m_to_u(14.2))


def test_envelope_sides_detects_corner_room_exposure():
    fp = _footprint()
    corner = Rect(fp.x, fp.y, m_to_u(3.0), m_to_u(3.0))
    assert set(envelope_sides(corner, fp)) == {Side.W, Side.N}


def test_envelope_sides_returns_nothing_for_a_fully_interior_room():
    fp = _footprint()
    inner = Rect(fp.x + m_to_u(2.0), fp.y + m_to_u(2.0), m_to_u(3.0), m_to_u(3.0))
    assert envelope_sides(inner, fp) == []


def test_exterior_rc_safe_room_wall_keeps_both_facts_through_the_adapter():
    """The regression that motivated the whole wall-model change: the solver reports only
    RC_SAFE_ROOM for this side, and exposure has to come from geometry."""
    facts = wall_facts_for_side(WallType.RC_SAFE_ROOM, on_envelope=True)
    assert facts.boundary_context is BoundaryContext.EXTERIOR
    assert facts.construction is Construction.RC_SAFE_ROOM
    assert facts.can_take_a_window


def test_interior_rc_safe_room_wall_is_distinguishable_from_the_exterior_one():
    facts = wall_facts_for_side(WallType.RC_SAFE_ROOM, on_envelope=False)
    assert facts.boundary_context is BoundaryContext.INTERIOR
    assert facts.construction is Construction.RC_SAFE_ROOM
    assert not facts.can_take_a_window


def test_open_boundary_maps_to_no_construction():
    facts = wall_facts_for_side(WallType.OPEN, on_envelope=False)
    assert facts.construction is Construction.NONE


def test_solver_exterior_wall_type_implies_exposure_but_carries_no_construction_detail():
    facts = wall_facts_for_side(WallType.EXTERIOR, on_envelope=True)
    assert facts.boundary_context is BoundaryContext.EXTERIOR
    assert facts.construction is Construction.STANDARD_PARTITION
