"""Conservative arc linearization and the minimum boolean set.

The safety rule under test: an INNER approximation must be a SUBSET of the true region and an
OUTER approximation a SUPERSET — for convex arcs, concave arcs, and hole boundaries alike, where
the correct construction differs in each case.
"""
from __future__ import annotations

import math

import pytest

from app.geometry_domain.booleans import (
    BooleanOperationError,
    area_of,
    contains_region,
    difference,
    intersection,
    offset_inward,
    offset_outward,
    union,
)
from app.geometry_domain.linearize import (
    ApproxDirection,
    arc_polyline,
    linearize_multiregion,
    linearize_region,
)
from app.geometry_domain.primitives import GeometryValidationError, MultiRegion, Region, Ring


def _mr(region: Region) -> MultiRegion:
    return MultiRegion.of(region)


def _sample_inside(region: Region, other: Region, n: int = 40) -> bool:
    """Every sampled point of `other` must also be in `region` (exact, arc-aware)."""
    minx, miny, maxx, maxy = other.bounds()
    for i in range(n + 1):
        for j in range(n + 1):
            p = (minx + (maxx - minx) * i / n, miny + (maxy - miny) * j / n)
            if other.contains_point(p) and not region.contains_point(p):
                return False
    return True


# ------------------------------------------------------------------ direction correctness

def test_inner_approximation_of_a_convex_arc_is_a_subset():
    curved = Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, 0.4, 0, 0]))
    inner, report = linearize_region(curved, ApproxDirection.INNER, 0.02)
    assert inner.area() < curved.area()
    assert _sample_inside(curved, inner)
    assert report.area_delta_m2 < 0


def test_outer_approximation_of_a_convex_arc_is_a_superset():
    curved = Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, 0.4, 0, 0]))
    outer, report = linearize_region(curved, ApproxDirection.OUTER, 0.02)
    assert outer.area() > curved.area()
    assert _sample_inside(outer, curved)
    assert report.area_delta_m2 > 0


def test_inner_approximation_of_a_concave_arc_is_a_subset():
    """The case where a chord would be WRONG: the polyline must stay clear of the bite."""
    curved = Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, -0.4, 0, 0]))
    inner, _ = linearize_region(curved, ApproxDirection.INNER, 0.02)
    assert inner.area() < curved.area()
    assert _sample_inside(curved, inner)


def test_a_chord_across_a_concave_arc_would_not_be_a_subset():
    """Proves the rule is load-bearing: the naive single chord (tolerance so loose that one
    segment is used) genuinely covers area the true region does not have."""
    curved = Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, -0.4, 0, 0]))
    chordish, _ = linearize_region(curved, ApproxDirection.OUTER, 10.0)
    assert chordish.area() > curved.area()
    assert not _sample_inside(curved, chordish)


def test_inner_approximation_of_a_curved_hole_is_a_subset():
    """A hole's boundary is convex as a circle but CONCAVE with respect to the material — the
    trap the architecture report warned about. The inner approximation must GROW the hole."""
    holed = Region(Ring.rectangle(0, 0, 20, 20), (Ring.circle(10, 10, 3.0),))
    inner, _ = linearize_region(holed, ApproxDirection.INNER, 0.02)
    assert inner.area() < holed.area()
    assert _sample_inside(holed, inner)
    # the hole grew, so its centre is still excluded
    assert not inner.contains_point((10.0, 10.0))


def test_outer_approximation_of_a_curved_hole_shrinks_the_hole():
    holed = Region(Ring.rectangle(0, 0, 20, 20), (Ring.circle(10, 10, 3.0),))
    outer, _ = linearize_region(holed, ApproxDirection.OUTER, 0.02)
    assert outer.area() > holed.area()
    assert _sample_inside(outer, holed)


def test_mixed_line_and_arc_boundary_linearizes_conservatively():
    mixed = Region(Ring.from_points([(0, 0), (10, 1), (10, 8), (0, 8)], [0, -0.2, 0.3, 0]))
    inner, _ = linearize_region(mixed, ApproxDirection.INNER, 0.01)
    assert _sample_inside(mixed, inner)


# ------------------------------------------------------------------ tolerance reporting

def test_tighter_tolerance_produces_more_segments_and_less_loss():
    curved = Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, 0.5, 0, 0]))
    coarse, coarse_rep = linearize_region(curved, ApproxDirection.INNER, 0.20)
    fine, fine_rep = linearize_region(curved, ApproxDirection.INNER, 0.01)
    assert fine_rep.segments_generated > coarse_rep.segments_generated
    assert fine.area() > coarse.area()
    assert fine_rep.max_deviation_m < coarse_rep.max_deviation_m


def test_report_exposes_tolerance_deviation_and_area():
    curved = Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, 0.5, 0, 0]))
    _, rep = linearize_region(curved, ApproxDirection.INNER, 0.05)
    assert rep.tolerance_m == 0.05
    assert rep.arcs_linearized == 1
    assert rep.max_deviation_m <= 0.05 + 1e-9
    assert rep.area_before_m2 > rep.area_after_m2


def test_deviation_stays_within_tolerance_for_both_constructions():
    p0, p1 = (0.0, 0.0), (6.0, 0.0)
    for bulge in (0.3, -0.3, 0.9, 1.6):
        for inscribe in (True, False):
            _, dev = arc_polyline(p0, p1, bulge, inscribe=inscribe, tolerance_m=0.02)
            assert dev <= 0.02 + 1e-9, (bulge, inscribe, dev)


def test_major_arcs_need_no_special_case():
    """The research report suggested splitting at |bulge| = 1; parameterizing by angle removes
    the need, so a 300-degree arc linearizes like any other."""
    pts, dev = arc_polyline((0.0, 0.0), (2.0, 0.0), 3.0, inscribe=True, tolerance_m=0.02)
    assert len(pts) > 3
    assert dev <= 0.02 + 1e-9


def test_linear_region_is_unchanged_by_linearization():
    rect = Region(Ring.rectangle(0, 0, 10, 5))
    out, rep = linearize_region(rect, ApproxDirection.INNER, 0.01)
    assert rep.arcs_linearized == 0
    assert out.area() == pytest.approx(rect.area())


# ------------------------------------------------------------------ booleans

def test_difference_removes_a_setback_frame():
    parcel = _mr(Region(Ring.rectangle(0, 0, 20, 24)))
    keep = _mr(Region(Ring.rectangle(3, 5.5, 14, 14.5)))
    frame = difference(parcel, keep)
    result = difference(parcel, frame)
    assert area_of(result) == pytest.approx(14 * 14.5, abs=1e-6)


def test_difference_of_an_interior_obstacle_creates_a_hole():
    envelope = _mr(Region(Ring.rectangle(0, 0, 20, 20)))
    obstacle = _mr(Region(Ring.rectangle(8, 8, 2, 2)))
    result = difference(envelope, obstacle)
    assert result.component_count == 1
    assert result.regions[0].holes
    assert area_of(result) == pytest.approx(400 - 4)


def test_union_and_intersection_round_trip():
    a = _mr(Region(Ring.rectangle(0, 0, 10, 10)))
    b = _mr(Region(Ring.rectangle(5, 0, 10, 10)))
    assert area_of(union(a, b)) == pytest.approx(150)
    assert area_of(intersection(a, b)) == pytest.approx(50)


def test_inward_offset_shrinks_and_can_disconnect_a_narrow_neck():
    """The reason every boolean returns a MultiRegion."""
    from app.vertical_slice.geometry_fixtures import narrow_neck

    hourglass = narrow_neck()
    assert hourglass.component_count == 1
    split = offset_inward(hourglass, 1.0)
    assert split.component_count == 2
    assert split.area() < hourglass.area()


def test_inward_offset_can_empty_a_region_entirely():
    small = _mr(Region(Ring.rectangle(0, 0, 1.0, 1.0)))
    assert offset_inward(small, 2.0).is_empty


def test_outward_offset_grows_a_point_feature_into_a_clearance_region():
    """Correct usage: a clearance region will be SUBTRACTED, so it is linearized OUTER first —
    the buffer then grows something that already covers the true trunk."""
    tree = _mr(Region(Ring.circle(5, 5, 0.2)))
    tree_linear, _ = linearize_multiregion(tree, ApproxDirection.OUTER, 0.01)
    clearance = offset_outward(tree_linear, 3.0)
    assert clearance.area() > tree.area()
    assert clearance.contains_point((7.5, 5.0))
    assert not clearance.contains_point((9.0, 5.0))


def test_offset_rejects_a_negative_distance():
    region = _mr(Region(Ring.rectangle(0, 0, 5, 5)))
    with pytest.raises(ValueError, match="must be >= 0"):
        offset_inward(region, -1.0)


def test_booleans_refuse_curved_input_rather_than_dropping_the_curvature():
    curved = _mr(Region(Ring.from_points([(0, 0), (10, 0), (10, 8), (0, 8)], [0, 0.4, 0, 0])))
    other = _mr(Region(Ring.rectangle(0, 0, 1, 1)))
    with pytest.raises(GeometryValidationError, match="linearize the region first"):
        difference(curved, other)


def test_containment_helper_answers_the_subset_question():
    big = _mr(Region(Ring.rectangle(0, 0, 10, 10)))
    small = _mr(Region(Ring.rectangle(2, 2, 3, 3)))
    outside = _mr(Region(Ring.rectangle(9, 9, 5, 5)))
    assert contains_region(big, small)
    assert not contains_region(big, outside)


def test_boolean_errors_do_not_leak_library_internals():
    assert issubclass(BooleanOperationError, RuntimeError)
