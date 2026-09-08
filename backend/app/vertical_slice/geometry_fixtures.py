"""Deterministic authoritative-geometry fixtures for the Safe Geometry Adapter.

These are DOMAIN fixtures, not test helpers: they describe authoritative sites (parcel +
constraints, or a directly-authored buildable region) in the general geometry language, and are
shared by the adapter tests and the end-to-end experiments.

Note on where arcs survive: Shapely has no arcs, so anything produced by a boolean is linear.
Curved fixtures therefore author the buildable region DIRECTLY with arcs — which is also the
realistic case (a curved building line comes from a plan, it is not derived by subtraction).
"""
from __future__ import annotations

from app.geometry_domain.constraints import (
    BuildableRegion,
    ConstraintRole,
    GeometricConstraint,
    Parcel,
    SiteConstraints,
)
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source

SURVEYED = Provenance(Source.SURVEY, Authority.AUTHORITATIVE, ref="fixture survey")
PLANNED = Provenance(Source.REGULATION, Authority.AUTHORITATIVE, ref="fixture plan")

#: The canonical footprint the existing concept is authored for.
CANONICAL_FOOTPRINT_M = (12.0, 14.2)


def _known(region: Region | MultiRegion, provenance: Provenance = SURVEYED) -> BuildableRegion:
    multi = region if isinstance(region, MultiRegion) else MultiRegion.of(region)
    return BuildableRegion.known(multi, provenance)


def _frame_setback(parcel_ring: Ring, keep: Ring, cid: str = "setback") -> GeometricConstraint:
    """A setback expressed as the frame between the parcel and the building line.

    Deliberately NOT an offset: many real building lines are absolute geometry taken from a plan
    rather than a uniform distance from the boundary (see the architecture report §4). Uniform
    offsets are still supported — `booleans.offset_inward` — and tested separately.
    """
    from app.geometry_domain.booleans import difference

    frame = difference(MultiRegion.of(Region(parcel_ring)), MultiRegion.of(Region(keep)))
    return GeometricConstraint(cid, ConstraintRole.SETBACK_REGION, frame, PLANNED,
                               note="building line from plan")


# --------------------------------------------------------------------------- 1-3: linear shapes

def exact_rectangle() -> SiteConstraints:
    """Case A. Parcel 20x24, building line leaving exactly the canonical 14.0 x 14.5 envelope."""
    parcel = Ring.rectangle(0, 0, 20.0, 24.0, prefix="p")
    keep = Ring.rectangle(3.0, 5.5, 14.0, 14.5, prefix="k")
    return SiteConstraints(
        parcel=Parcel("fixture-rect", MultiRegion.of(Region(parcel)), SURVEYED),
        constraints=(_frame_setback(parcel, keep),),
    )


def diagonal_polygon() -> BuildableRegion:
    """A rotated/diagonal boundary — no edge is axis-aligned."""
    return _known(Region(Ring.from_points([(4.0, 4.0), (20.0, 8.0), (16.0, 24.0), (0.0, 20.0)])))


def l_shaped_site() -> SiteConstraints:
    """Case B. Base envelope 18 x 16 with a notch removed from the north-east corner."""
    parcel = Ring.rectangle(0, 0, 24.0, 28.0, prefix="p")
    keep = Ring.rectangle(3.0, 5.5, 18.0, 16.0, prefix="k")
    notch = GeometricConstraint(
        "notch", ConstraintRole.NO_BUILD_REGION,
        MultiRegion.of(Region(Ring.rectangle(16.0, 5.5, 5.0, 6.5, prefix="n"))),
        PLANNED, note="unbuildable corner",
    )
    return SiteConstraints(
        parcel=Parcel("fixture-L", MultiRegion.of(Region(parcel)), SURVEYED),
        constraints=(_frame_setback(parcel, keep), notch),
    )


# --------------------------------------------------------------------------- 4-6: curved facades

def convex_facade() -> BuildableRegion:
    """Case C(i). East facade bulges OUTWARD — the chord is safe here."""
    return _known(Region(Ring.from_points(
        [(3.0, 5.5), (21.0, 5.5), (21.0, 21.5), (3.0, 21.5)], [0.0, 0.28, 0.0, 0.0])))


def concave_facade() -> BuildableRegion:
    """Case C(ii). East facade bites INWARD — a chord here would design into nothing."""
    return _known(Region(Ring.from_points(
        [(3.0, 5.5), (21.0, 5.5), (21.0, 21.5), (3.0, 21.5)], [0.0, -0.12, 0.0, 0.0])))


def strongly_concave_facade() -> BuildableRegion:
    """A deep bite, where a single chord would be wrong by metres, not centimetres."""
    return _known(Region(Ring.from_points(
        [(3.0, 5.5), (21.0, 5.5), (21.0, 21.5), (3.0, 21.5)], [0.0, -0.45, 0.0, 0.0])))


def mixed_lines_and_arcs() -> BuildableRegion:
    """Straight, diagonal, convex and concave edges in one boundary."""
    return _known(Region(Ring.from_points(
        [(3.0, 5.5), (21.0, 7.0), (21.0, 21.5), (3.0, 21.5)], [0.0, -0.15, 0.18, 0.0])))


# --------------------------------------------------------------------------- 7-9: holes

def curved_exclusion_hole() -> BuildableRegion:
    """A circular clearance (protected tree / column) fully inside the envelope."""
    outer = Ring.rectangle(3.0, 5.5, 18.0, 16.0)
    hole = Ring.circle(18.0, 13.5, 1.6)
    return _known(Region(outer, (hole,)))


def rectangular_obstacle_site() -> SiteConstraints:
    """Case D. An obstacle removed from an otherwise rectangular envelope."""
    parcel = Ring.rectangle(0, 0, 24.0, 28.0, prefix="p")
    keep = Ring.rectangle(3.0, 5.5, 18.0, 16.0, prefix="k")
    obstacle = GeometricConstraint(
        "shaft", ConstraintRole.OBSTACLE,
        MultiRegion.of(Region(Ring.rectangle(17.6, 11.0, 2.4, 5.0, prefix="o"))),
        SURVEYED, note="utility shaft with clearance",
    )
    return SiteConstraints(
        parcel=Parcel("fixture-obstacle", MultiRegion.of(Region(parcel)), SURVEYED),
        constraints=(_frame_setback(parcel, keep), obstacle),
    )


def multiple_holes() -> BuildableRegion:
    outer = Ring.rectangle(3.0, 5.5, 18.0, 16.0)
    return _known(Region(outer, (
        Ring.circle(18.5, 8.5, 0.9),
        Ring.rectangle(18.0, 17.0, 2.0, 3.0),
        Ring.circle(6.0, 19.5, 0.7),
    )))


# --------------------------------------------------------------------------- 10-11: components

def disconnected_components() -> BuildableRegion:
    """Two separate buildable pieces. They must never be merged to simplify solving."""
    return _known(MultiRegion.of(
        Region(Ring.rectangle(3.0, 5.5, 14.0, 15.0)),
        Region(Ring.rectangle(20.0, 5.5, 6.0, 8.0)),
    ))


def narrow_neck() -> MultiRegion:
    """An hourglass whose waist is 1.2 m wide. A 1.0 m inward offset SPLITS it — the case the
    MultiRegion return type exists for."""
    return MultiRegion.of(Region(Ring.from_points([
        (0.0, 0.0), (10.0, 0.0), (10.0, 8.0),
        (5.6, 8.0), (5.6, 9.2), (10.0, 9.2), (10.0, 17.0), (0.0, 17.0),
        (0.0, 9.2), (4.4, 9.2), (4.4, 8.0), (0.0, 8.0),
    ])))


# --------------------------------------------------------------------------- 12-13: edge cases

def unknown_buildable() -> BuildableRegion:
    return BuildableRegion.unknown("no building line available for this plan")


def too_small_for_programme() -> BuildableRegion:
    """Geometrically valid, architecturally hopeless — must not be reported as SOLVED when a
    required programme size is supplied."""
    return _known(Region(Ring.rectangle(0.0, 0.0, 5.0, 4.0)))
