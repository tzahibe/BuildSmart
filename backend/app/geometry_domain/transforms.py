"""Rigid and similarity transforms.

The point of this module is what it does NOT have to do: bulge is invariant under translation,
rotation and uniform scale, so every transform below touches only the vertex table. There is no
second store of curvature that a transform could forget to update — which is the decisive
argument for bulge over center+radius+angles and over three-point (report §2).

Mirroring is the one exception: it reverses traversal handedness, so bulge negates.

Non-uniform scaling is deliberately NOT provided: it turns a circular arc into an elliptical one,
which this model cannot represent. That is a property of circular arcs, not of bulge.
"""
from __future__ import annotations

import math
from typing import Callable, TypeVar

from .primitives import BoundaryEdge, MultiRegion, Region, Ring, Vertex

Geometry = TypeVar("Geometry", Ring, Region, MultiRegion)

PointFn = Callable[[float, float], tuple[float, float]]
BulgeFn = Callable[[float], float]


def _map_ring(ring: Ring, point_fn: PointFn, bulge_fn: BulgeFn) -> Ring:
    vertices = tuple(Vertex(v.id, *point_fn(v.x, v.y)) for v in ring.vertices)
    edges = tuple(
        # provenance is carried through unchanged: transforming geometry does not change where
        # the fact came from.
        BoundaryEdge(e.start, e.end, bulge_fn(e.bulge), e.provenance)
        for e in ring.edges
    )
    return Ring(vertices, edges)


def _map_any(geometry, point_fn: PointFn, bulge_fn: BulgeFn):
    if isinstance(geometry, Ring):
        return _map_ring(geometry, point_fn, bulge_fn)
    if isinstance(geometry, Region):
        return Region(
            _map_ring(geometry.outer, point_fn, bulge_fn),
            tuple(_map_ring(h, point_fn, bulge_fn) for h in geometry.holes),
        )
    if isinstance(geometry, MultiRegion):
        return MultiRegion(tuple(_map_any(r, point_fn, bulge_fn) for r in geometry.regions))
    raise TypeError(f"cannot transform {type(geometry).__name__}")


def translate(geometry: Geometry, dx: float, dy: float) -> Geometry:
    """Bulge unchanged."""
    return _map_any(geometry, lambda x, y: (x + dx, y + dy), lambda b: b)


def rotate(geometry: Geometry, angle_rad: float, about: tuple[float, float] = (0.0, 0.0)) -> Geometry:
    """Bulge unchanged."""
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    ox, oy = about

    def point_fn(x: float, y: float) -> tuple[float, float]:
        px, py = x - ox, y - oy
        return (ox + px * ca - py * sa, oy + px * sa + py * ca)

    return _map_any(geometry, point_fn, lambda b: b)


def scale_uniform(geometry: Geometry, factor: float,
                  about: tuple[float, float] = (0.0, 0.0)) -> Geometry:
    """Bulge unchanged — an arc scaled uniformly is still an arc of the same included angle."""
    if factor == 0:
        raise ValueError("uniform scale factor must be non-zero")
    ox, oy = about
    return _map_any(
        geometry,
        lambda x, y: (ox + (x - ox) * factor, oy + (y - oy) * factor),
        lambda b: b,
    )


def mirror_x(geometry: Geometry, at_y: float = 0.0) -> Geometry:
    """Reflect across a horizontal line. Handedness flips, so bulge negates."""
    return _map_any(geometry, lambda x, y: (x, 2 * at_y - y), lambda b: -b)


def mirror_y(geometry: Geometry, at_x: float = 0.0) -> Geometry:
    """Reflect across a vertical line. Handedness flips, so bulge negates."""
    return _map_any(geometry, lambda x, y: (2 * at_x - x, y), lambda b: -b)
