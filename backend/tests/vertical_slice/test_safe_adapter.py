"""Safe Geometry Adapter: the subset invariant across all thirteen required shapes.

THE INVARIANT UNDER TEST: the adapter may lose usable area; it may never create area that does
not exist. Every candidate is verified against the EXACT arc-aware authoritative geometry, not
against the linearization it was derived from — otherwise the check would only be re-confirming
its own approximation.
"""
from __future__ import annotations

import pytest

from app.geometry_domain.constraints import BuildableRegion, SiteConstraints
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.geometry_core.model import UNIT_M
from app.vertical_slice.safe_adapter import (
    AdapterOutcome,
    RectStrategy,
    ResidualSource,
    adapt,
    build_buildable_region,
    verify_candidate_within,
)

SURVEYED = Provenance(Source.SURVEY, Authority.AUTHORITATIVE)


def _buildable(fixture) -> BuildableRegion:
    return build_buildable_region(fixture) if isinstance(fixture, SiteConstraints) else fixture


#: The thirteen required shapes (§11). Name -> factory.
SHAPES = {
    "exact_rectangle": F.exact_rectangle,
    "diagonal_polygon": F.diagonal_polygon,
    "l_shaped": F.l_shaped_site,
    "convex_facade": F.convex_facade,
    "concave_facade": F.concave_facade,
    "strongly_concave": F.strongly_concave_facade,
    "curved_exclusion_hole": F.curved_exclusion_hole,
    "rectangular_obstacle": F.rectangular_obstacle_site,
    "multiple_holes": F.multiple_holes,
    "disconnected": F.disconnected_components,
    "mixed_lines_arcs": F.mixed_lines_and_arcs,
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_candidate_is_inside_the_authoritative_region(name):
    buildable = _buildable(SHAPES[name]())
    result = adapt(buildable)
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.candidates
    authoritative = buildable.require_known()
    for candidate in result.candidates:
        assert verify_candidate_within(candidate, authoritative), \
            f"{name}: candidate {candidate.order} escapes the authoritative region"


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_solver_area_never_exceeds_authoritative_area(name):
    result = adapt(_buildable(SHAPES[name]()))
    assert result.solver_area_m2 <= result.authoritative_area_m2 + 1e-6
    assert 0.0 < result.retention_ratio <= 1.0


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_area_accounting_closes(name):
    """Every square metre is either used by a candidate, listed as a residual, or explicitly
    charged to curve approximation / dropped slivers."""
    result = adapt(_buildable(SHAPES[name]()))
    assert result.accounted_area_m2 == pytest.approx(result.authoritative_area_m2, abs=0.02)


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_candidates_are_grid_aligned_by_construction(name):
    """Rectangles are built from whole grid cells, so there is no metres->units rounding step
    that could round outward (§9)."""
    result = adapt(_buildable(SHAPES[name]()))
    for candidate in result.candidates:
        r = candidate.rect
        assert all(isinstance(v, int) for v in (r.x, r.y, r.w, r.h))
        assert r.w > 0 and r.h > 0


# ------------------------------------------------------------------ per-shape expectations

def test_exact_rectangle_loses_nothing():
    """§12: for an exact rectangular authoritative region the adapter must be a no-op."""
    result = adapt(_buildable(F.exact_rectangle()))
    assert result.retention_ratio == 1.0
    assert result.residuals == ()
    assert result.curve_loss_area_m2 == 0.0
    assert len(result.candidates) == 1
    assert result.candidates[0].strategy is RectStrategy.MAX_INSCRIBED_RECT


def test_l_shape_keeps_both_wings_instead_of_collapsing_to_one_rectangle():
    """§7: the L must not be reduced to its single largest rectangle."""
    result = adapt(_buildable(F.l_shaped_site()))
    assert len(result.candidates) >= 2
    assert result.retention_ratio == pytest.approx(1.0, abs=1e-6)
    # the two wings share a boundary — the seam a future concept generator would need
    assert result.candidates[0].adjacent_orders
    assert 1 in result.candidates[0].adjacent_orders


def test_disconnected_components_are_never_merged():
    result = adapt(F.disconnected_components())
    components = {c.component_index for c in result.candidates}
    assert len(components) == 2


def test_concave_facade_costs_area_but_stays_safe():
    buildable = F.concave_facade()
    result = adapt(buildable)
    assert result.retention_ratio < 1.0
    assert all(verify_candidate_within(c, buildable.require_known()) for c in result.candidates)


def test_curve_loss_is_reported_separately_from_rectangularization_loss():
    result = adapt(F.strongly_concave_facade())
    assert result.curve_loss_area_m2 > 0
    assert result.approximation is not None
    assert result.approximation.arcs_linearized >= 1


def test_no_candidate_overlaps_a_curved_exclusion_hole():
    buildable = F.curved_exclusion_hole()
    result = adapt(buildable)
    authoritative = buildable.require_known()
    for candidate in result.candidates:
        assert verify_candidate_within(candidate, authoritative)
    # the hole's centre must not be inside any candidate
    for candidate in result.candidates:
        r = candidate.rect
        assert not (r.x * UNIT_M <= 18.0 <= r.x2 * UNIT_M and r.y * UNIT_M <= 13.5 <= r.y2 * UNIT_M)


def test_obstacle_is_excluded_from_every_candidate():
    site = F.rectangular_obstacle_site()
    result = adapt(build_buildable_region(site))
    for candidate in result.candidates:
        r = candidate.rect
        overlaps = not (r.x2 * UNIT_M <= 17.6 or r.x * UNIT_M >= 20.0
                        or r.y2 * UNIT_M <= 11.0 or r.y * UNIT_M >= 16.0)
        assert not overlaps, f"candidate {candidate.order} overlaps the shaft"


def test_multiple_holes_are_all_respected():
    buildable = F.multiple_holes()
    result = adapt(buildable)
    assert all(verify_candidate_within(c, buildable.require_known()) for c in result.candidates)


def test_diagonal_polygon_loses_area_to_orthogonal_fitting_but_stays_inside():
    buildable = F.diagonal_polygon()
    result = adapt(buildable)
    assert result.retention_ratio < 1.0  # a diagonal cannot be tiled exactly by axis-aligned rects
    assert all(verify_candidate_within(c, buildable.require_known()) for c in result.candidates)


# ------------------------------------------------------------------ residuals

def test_residuals_carry_geometric_facts_and_no_architectural_use():
    result = adapt(F.multiple_holes())
    assert result.residuals
    for residual in result.residuals:
        assert residual.area_m2 > 0
        assert residual.thickness_est_m >= 0
        assert residual.max_extent_m > 0
        assert isinstance(residual.source, ResidualSource)
        assert isinstance(residual.touches_solver_geometry, bool)
        assert isinstance(residual.has_exterior_exposure, bool)
        assert not hasattr(residual, "suggested_use")


def test_dropped_residual_area_is_counted_not_discarded():
    result = adapt(F.strongly_concave_facade())
    assert result.dropped_residual_area_m2 >= 0.0
    assert result.accounted_area_m2 == pytest.approx(result.authoritative_area_m2, abs=0.02)


# ------------------------------------------------------------------ structured outcomes

def test_unknown_buildable_region_refuses_to_produce_geometry():
    """§10: no fallback to the parcel boundary, no guessed envelope."""
    result = adapt(F.unknown_buildable())
    assert result.outcome is AdapterOutcome.BUILDABLE_REGION_UNKNOWN
    assert result.candidates == ()
    assert "must not be inferred from the parcel" in result.notes[0]


def test_insufficient_capacity_is_reported_when_a_required_size_does_not_fit():
    result = adapt(F.too_small_for_programme(), required_size_m=(12.0, 14.2))
    assert result.outcome is AdapterOutcome.INSUFFICIENT_RECTANGULAR_CAPACITY


def test_same_region_solves_when_no_size_is_required():
    result = adapt(F.too_small_for_programme())
    assert result.outcome is AdapterOutcome.SOLVED


def test_outcomes_are_product_level_not_library_level():
    for outcome in AdapterOutcome:
        assert "geos" not in outcome.value.lower()
        assert "shapely" not in outcome.value.lower()


# ------------------------------------------------------------------ quantization safety (§9)

def test_off_grid_boundaries_are_never_rounded_outward():
    """A region whose edges fall between grid lines must yield candidates strictly inside it."""
    odd = BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(0.02, 0.03, 5.11, 4.07))), SURVEYED)
    result = adapt(odd, min_candidate_area_m2=0.5)
    assert result.candidates
    for candidate in result.candidates:
        r = candidate.rect
        assert r.x * UNIT_M >= 0.02 - 1e-9
        assert r.y * UNIT_M >= 0.03 - 1e-9
        assert r.x2 * UNIT_M <= 0.02 + 5.11 + 1e-9
        assert r.y2 * UNIT_M <= 0.03 + 4.07 + 1e-9
        assert verify_candidate_within(candidate, odd.require_known())


def test_a_sub_cell_region_yields_no_candidate_rather_than_a_rounded_up_one():
    tiny = BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(0.0, 0.0, 0.03, 0.03))), SURVEYED)
    result = adapt(tiny, min_candidate_area_m2=0.0)
    assert result.outcome is AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY


# ------------------------------------------------------------------ buildable-region assembly

def test_build_buildable_region_subtracts_setback_and_obstacle():
    site = F.rectangular_obstacle_site()
    buildable = build_buildable_region(site)
    assert buildable.is_known
    geometry = buildable.require_known()
    assert not geometry.contains_point((18.8, 13.5))   # inside the shaft
    assert geometry.contains_point((6.0, 12.0))        # well inside the envelope
    assert not geometry.contains_point((1.0, 1.0))     # inside the setback frame


def test_build_buildable_region_records_what_it_was_derived_from():
    buildable = build_buildable_region(F.rectangular_obstacle_site())
    assert set(buildable.derived_from) == {"setback", "shaft"}


def test_constraints_that_remove_everything_yield_unknown_not_empty_geometry():
    site = F.exact_rectangle()
    from app.geometry_domain.constraints import ConstraintRole, GeometricConstraint

    swallow = GeometricConstraint(
        "everything", ConstraintRole.NO_BUILD_REGION,
        MultiRegion.of(Region(Ring.rectangle(-5, -5, 40, 40))), SURVEYED)
    site = SiteConstraints(site.parcel, site.constraints + (swallow,))
    buildable = build_buildable_region(site)
    assert not buildable.is_known
