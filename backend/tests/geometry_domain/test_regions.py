"""Regions with holes, and multi-component regions — the two things a single vertex ring
cannot express (report §1)."""
from __future__ import annotations

import math

import pytest

from app.geometry_domain.primitives import (
    GeometryValidationError,
    MultiRegion,
    Region,
    Ring,
)


def test_region_with_one_hole_subtracts_the_hole_area():
    outer = Ring.rectangle(0, 0, 10, 10)
    hole = Ring.rectangle(4, 4, 2, 2)
    region = Region(outer, (hole,))
    assert region.area() == pytest.approx(100 - 4)


def test_region_with_a_circular_hole_models_a_clearance_disc():
    """A protected tree / column punches a hole; no special case is needed because arcs are in
    the edge model (report §4)."""
    region = Region(Ring.rectangle(0, 0, 20, 20), (Ring.circle(10, 10, 3.0),))
    assert region.area() == pytest.approx(400 - math.pi * 9)


def test_point_inside_a_hole_is_not_inside_the_region():
    region = Region(Ring.rectangle(0, 0, 10, 10), (Ring.rectangle(4, 4, 2, 2),))
    assert region.contains_point((1.0, 1.0))
    assert not region.contains_point((5.0, 5.0))


def test_hole_outside_the_outer_boundary_is_rejected():
    region = Region(Ring.rectangle(0, 0, 10, 10), (Ring.rectangle(20, 20, 2, 2),))
    with pytest.raises(GeometryValidationError, match="outside the outer boundary"):
        region.validate()


def test_normalization_orients_outer_ccw_and_holes_cw():
    region = Region(Ring.rectangle(0, 0, 10, 10).reversed(), (Ring.rectangle(4, 4, 2, 2),))
    norm = region.normalized()
    assert norm.outer.is_ccw()
    assert not norm.holes[0].is_ccw()
    assert norm.area() == pytest.approx(96)


def test_multiple_disconnected_components():
    """An inward setback offset routinely SPLITS a pinched parcel; the type must be able to say
    so rather than silently returning the larger piece (report §1, §7 cases 5 and 7)."""
    a = Region(Ring.rectangle(0, 0, 4, 4))
    b = Region(Ring.rectangle(10, 0, 3, 3))
    multi = MultiRegion.of(a, b)
    assert multi.component_count == 2
    assert not multi.is_connected
    assert multi.area() == pytest.approx(16 + 9)
    assert multi.contains_point((1.0, 1.0))
    assert multi.contains_point((11.0, 1.0))
    assert not multi.contains_point((7.0, 1.0))


def test_multiregion_bounds_span_all_components():
    multi = MultiRegion.of(Region(Ring.rectangle(0, 0, 4, 4)), Region(Ring.rectangle(10, 0, 3, 3)))
    assert multi.bounds() == pytest.approx((0.0, 0.0, 13.0, 4.0))


def test_empty_multiregion_is_representable_and_has_no_bounds():
    empty = MultiRegion()
    assert empty.is_empty
    assert empty.area() == 0.0
    with pytest.raises(GeometryValidationError, match="empty MultiRegion"):
        empty.bounds()


def test_a_region_can_carry_several_holes_at_once():
    """Multiple interior exclusions (report §7 case 3) must be representable even though the
    current rectangular solver cannot consume them."""
    region = Region(
        Ring.rectangle(0, 0, 20, 20),
        (Ring.rectangle(2, 2, 2, 2), Ring.rectangle(10, 10, 3, 3), Ring.circle(16, 4, 1.0)),
    )
    region.validate()
    assert region.area() == pytest.approx(400 - 4 - 9 - math.pi)
