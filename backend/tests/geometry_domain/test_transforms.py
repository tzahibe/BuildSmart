"""Transforms, and the property that motivated choosing bulge in the first place:
curvature is invariant under translation/rotation/uniform scale, so a transform touches only
the vertex table and cannot desynchronize the arc from its endpoints (report §2)."""
from __future__ import annotations

import math

import pytest

from app.geometry_domain.primitives import Region, Ring, arc_radius
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.geometry_domain.transforms import (
    mirror_x,
    mirror_y,
    rotate,
    scale_uniform,
    translate,
)

SURVEYED = Provenance(Source.SURVEY, Authority.AUTHORITATIVE, ref="plan-7")


def _curved_ring() -> Ring:
    return Ring.from_points([(0, 0), (4, 0), (4, 4), (0, 4)], [0.0, 0.5, 0.0, -0.3], provenance=SURVEYED)


# ------------------------------------------------------------------ bulge invariance

def test_bulge_is_invariant_under_translation():
    ring = _curved_ring()
    moved = translate(ring, 17.5, -3.25)
    assert [e.bulge for e in moved.edges] == [e.bulge for e in ring.edges]


def test_bulge_is_invariant_under_rotation():
    ring = _curved_ring()
    turned = rotate(ring, math.radians(37.0))
    assert [e.bulge for e in turned.edges] == [e.bulge for e in ring.edges]


def test_bulge_is_invariant_under_uniform_scale():
    ring = _curved_ring()
    bigger = scale_uniform(ring, 2.5)
    assert [e.bulge for e in bigger.edges] == [e.bulge for e in ring.edges]


def test_mirroring_negates_bulge():
    """The one transform that changes handedness — and the whole of the exception."""
    ring = _curved_ring()
    for flipped in (mirror_x(ring), mirror_y(ring)):
        assert [e.bulge for e in flipped.edges] == [-e.bulge for e in ring.edges]


# ------------------------------------------------------------------ geometric correctness

def test_translation_preserves_area_and_moves_bounds():
    ring = _curved_ring()
    moved = translate(ring, 10.0, 5.0)
    assert moved.area() == pytest.approx(ring.area())
    x0, y0, x1, y1 = ring.bounds()
    assert moved.bounds() == pytest.approx((x0 + 10, y0 + 5, x1 + 10, y1 + 5))


def test_rotation_preserves_area():
    ring = _curved_ring()
    assert rotate(ring, math.radians(90)).area() == pytest.approx(ring.area())


def test_uniform_scale_squares_the_area_and_scales_the_radius():
    ring = _curved_ring()
    factor = 3.0
    bigger = scale_uniform(ring, factor)
    assert bigger.area() == pytest.approx(ring.area() * factor * factor)

    def radius_of_second_edge(r: Ring) -> float:
        p0, p1, b = r.edge_geometry()[1]
        return arc_radius(p0, p1, b)

    assert radius_of_second_edge(bigger) == pytest.approx(radius_of_second_edge(ring) * factor)


def test_mirroring_preserves_area_magnitude():
    ring = _curved_ring()
    assert mirror_x(ring).area() == pytest.approx(ring.area())


def test_rotation_about_a_point_leaves_that_point_fixed():
    ring = Ring.rectangle(0, 0, 2, 2)
    turned = rotate(ring, math.radians(90), about=(0.0, 0.0))
    assert turned.vertices[0].x == pytest.approx(0.0)
    assert turned.vertices[0].y == pytest.approx(0.0)


# ------------------------------------------------------------------ provenance

def test_provenance_survives_every_transform():
    """Transforming geometry does not change where the fact came from (report §5)."""
    ring = _curved_ring()
    for transformed in (
        translate(ring, 1, 2),
        rotate(ring, 0.4),
        scale_uniform(ring, 2.0),
        mirror_x(ring),
    ):
        assert all(e.provenance == SURVEYED for e in transformed.edges)


def test_transforms_apply_through_regions_and_holes():
    region = Region(Ring.rectangle(0, 0, 10, 10), (Ring.circle(5, 5, 2.0),))
    moved = translate(region, 3.0, 4.0)
    assert moved.area() == pytest.approx(region.area())
    assert moved.contains_point((4.0, 5.0))
    assert not moved.contains_point((8.0, 9.0))  # the hole moved with it
