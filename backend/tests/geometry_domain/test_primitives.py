"""Authoritative geometry primitives: shapes, arcs, area, bounds, containment, validation."""
from __future__ import annotations

import math

import pytest

from app.geometry_domain.primitives import (
    BoundaryEdge,
    GeometryValidationError,
    Region,
    Ring,
    Vertex,
    arc_apex,
    arc_center,
    arc_radius,
    arc_sagitta,
    arc_segment_area,
    bulge_from_three_points,
    included_angle,
)


# ----------------------------------------------------------------- straight-edged shapes

def test_rectangle_is_representable_as_general_geometry():
    """Task §11: a rectangle must be one special case of the general model, not a separate
    language."""
    ring = Ring.rectangle(0, 0, 12.0, 14.2)
    assert len(ring.edges) == 4
    assert all(e.is_line for e in ring.edges)
    assert ring.area() == pytest.approx(170.4)
    assert ring.bounds() == pytest.approx((0.0, 0.0, 12.0, 14.2))


def test_arbitrary_straight_polygon():
    ring = Ring.from_points([(0, 0), (10, 0), (10, 6), (4, 6), (4, 10), (0, 10)])  # L-shape
    assert ring.area() == pytest.approx(10 * 6 + 4 * 4)


def test_diagonal_edge():
    ring = Ring.from_points([(0, 0), (10, 0), (0, 10)])  # right triangle with a diagonal
    assert ring.area() == pytest.approx(50.0)


def test_orientation_is_meaningful_and_reversible():
    ring = Ring.rectangle(0, 0, 4, 3)
    assert ring.is_ccw()
    assert not ring.reversed().is_ccw()
    assert ring.reversed().area() == pytest.approx(ring.area())


# ----------------------------------------------------------------- arcs

def test_convex_arc_adds_area_on_a_ccw_ring():
    """A square whose top edge bulges outward encloses MORE than the square."""
    straight = Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)])
    bulged = Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)], [0.0, 0.0, 0.5, 0.0])
    assert bulged.area() > straight.area()


def test_concave_arc_removes_area_on_a_ccw_ring():
    """The same edge bulging inward takes a bite out of the square — the case where a chord
    substitution would be unsafe (report §3)."""
    straight = Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)])
    bitten = Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)], [0.0, 0.0, -0.5, 0.0])
    assert bitten.area() < straight.area()


def test_mixed_lines_and_arcs_in_one_boundary():
    ring = Ring.from_points(
        [(0, 0), (6, 0), (6, 4), (0, 4)],
        [0.0, 0.3, 0.0, -0.2],  # line, convex arc, line, concave arc
    )
    ring.validate()
    assert ring.area() > 0
    kinds = [e.is_line for e in ring.edges]
    assert kinds == [True, False, True, False]


def test_circle_from_two_semicircular_arcs_has_exact_area():
    """A clearance disc needs no new primitive — it is a Ring of two bulge=1 edges (report §4).
    This also pins the sign convention: positive bulge on a CCW ring adds area."""
    r = 2.5
    ring = Ring.circle(0.0, 0.0, r)
    assert len(ring.edges) == 2
    assert ring.area() == pytest.approx(math.pi * r * r)


def test_sagitta_matches_the_closed_form_and_needs_no_centre():
    p0, p1, b = (0.0, 0.0), (4.0, 0.0), 0.5
    assert arc_sagitta(p0, p1, b) == pytest.approx(abs(b) * 4.0 / 2.0)


def test_arc_radius_and_centre_are_consistent_with_the_endpoints():
    p0, p1, b = (0.0, 0.0), (2.0, 0.0), 0.5
    c = arc_center(p0, p1, b)
    r = arc_radius(p0, p1, b)
    assert math.dist(c, p0) == pytest.approx(r)
    assert math.dist(c, p1) == pytest.approx(r)
    assert math.dist(c, arc_apex(p0, p1, b)) == pytest.approx(r)


def test_semicircle_has_bulge_one_and_a_half_disc_of_area():
    p0, p1, b = (0.0, 0.0), (2.0, 0.0), 1.0
    assert included_angle(b) == pytest.approx(math.pi)
    assert arc_radius(p0, p1, b) == pytest.approx(1.0)
    assert arc_segment_area(p0, p1, b) == pytest.approx(math.pi / 2)


def test_major_arc_is_flagged_for_splitting():
    """Report §2 requires |bulge| > 1 arcs to be split before simplification; the model must
    make them findable."""
    assert BoundaryEdge("a", "b", 2.0).is_major_arc
    assert not BoundaryEdge("a", "b", 0.9).is_major_arc
    assert not BoundaryEdge("a", "b", 0.0).is_major_arc


def test_straight_edge_is_bulge_zero_with_no_special_case():
    e = BoundaryEdge("a", "b", 0.0)
    assert e.is_line
    assert arc_segment_area((0.0, 0.0), (5.0, 0.0), 0.0) == 0.0


def test_three_point_input_converts_to_bulge():
    """Three-point is an accepted INPUT form and never a storage form (report §2)."""
    p0, p1, b = (0.0, 0.0), (4.0, 0.0), 0.4
    apex = arc_apex(p0, p1, b)
    assert bulge_from_three_points(p0, apex, p1) == pytest.approx(b)


def test_three_collinear_points_give_a_straight_edge():
    assert bulge_from_three_points((0.0, 0.0), (2.0, 0.0), (4.0, 0.0)) == pytest.approx(0.0)


def test_bounds_include_the_arc_bulge_not_just_the_vertices():
    """A bounding box over vertices alone would report a circle as a degenerate line."""
    ring = Ring.circle(0.0, 0.0, 3.0)
    assert ring.bounds() == pytest.approx((-3.0, -3.0, 3.0, 3.0))


# ----------------------------------------------------------------- containment

def test_contains_point_for_a_rectangle():
    ring = Ring.rectangle(0, 0, 10, 5)
    assert ring.contains_point((5.0, 2.5))
    assert not ring.contains_point((11.0, 2.5))


def test_contains_point_respects_a_convex_bulge():
    """A point in the bulge lies outside the chord polygon but inside the true region."""
    ring = Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)], [0.0, 0.0, 0.8, 0.0])
    assert ring.contains_point((2.0, 4.5))


def test_contains_point_respects_a_concave_bulge():
    """The mirror case: inside the chord polygon, outside the true region — exactly the area a
    chord substitution would wrongly hand to the solver."""
    ring = Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)], [0.0, 0.0, -0.8, 0.0])
    assert not ring.contains_point((2.0, 3.7))
    assert ring.contains_point((2.0, 1.0))


def test_contains_point_inside_a_circle():
    ring = Ring.circle(1.0, 1.0, 2.0)
    assert ring.contains_point((1.0, 1.0))
    assert ring.contains_point((2.5, 1.0))
    assert not ring.contains_point((4.0, 1.0))


# ----------------------------------------------------------------- validation

def test_unclosed_ring_is_rejected_with_a_named_diagnostic():
    verts = (Vertex("a", 0, 0), Vertex("b", 1, 0), Vertex("c", 1, 1))
    edges = (BoundaryEdge("a", "b"), BoundaryEdge("b", "c"))  # never returns to 'a'
    with pytest.raises(GeometryValidationError, match="not closed"):
        Ring(verts, edges)


def test_edge_referencing_an_unknown_vertex_is_rejected():
    verts = (Vertex("a", 0, 0), Vertex("b", 1, 0))
    edges = (BoundaryEdge("a", "b", 1.0), BoundaryEdge("b", "ghost", 1.0))
    with pytest.raises(GeometryValidationError, match="unknown vertex"):
        Ring(verts, edges)


def test_degenerate_zero_length_edge_is_rejected():
    verts = (Vertex("a", 0, 0), Vertex("b", 0, 0), Vertex("c", 1, 1))
    edges = (BoundaryEdge("a", "b"), BoundaryEdge("b", "c"), BoundaryEdge("c", "a"))
    with pytest.raises(GeometryValidationError, match="degenerate"):
        Ring(verts, edges)


def test_two_straight_edges_cannot_enclose_area():
    verts = (Vertex("a", 0, 0), Vertex("b", 2, 0))
    edges = (BoundaryEdge("a", "b", 0.0), BoundaryEdge("b", "a", 0.0))
    with pytest.raises(GeometryValidationError, match="at least one edge must be an arc"):
        Ring(verts, edges)


def test_duplicate_vertex_ids_are_rejected():
    verts = (Vertex("a", 0, 0), Vertex("a", 1, 0), Vertex("c", 1, 1))
    edges = (BoundaryEdge("a", "a"), BoundaryEdge("a", "c"), BoundaryEdge("c", "a"))
    with pytest.raises(GeometryValidationError, match="duplicate vertex ids"):
        Ring(verts, edges)


def test_mismatched_bulge_count_is_rejected():
    with pytest.raises(GeometryValidationError, match="one bulge per edge"):
        Ring.from_points([(0, 0), (1, 0), (1, 1)], [0.0, 0.0])
