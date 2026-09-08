"""Constraints, parcel/buildable separation, UNKNOWN, provenance, wall facts, quantization."""
from __future__ import annotations

from datetime import date

import pytest

from app.geometry_domain.constraints import (
    BuildableRegion,
    ConstraintRole,
    GeometricConstraint,
    Knowledge,
    Parcel,
    SiteConstraints,
    UnknownBuildableRegionError,
)
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source, weakest_of
from app.geometry_domain.units import (
    Rounding,
    clearance_units_no_understate,
    length_units_no_overstate,
    lower_bound_units,
    quantize_m,
    upper_bound_units,
)
from app.geometry_domain.walls import (
    BoundaryContext,
    Construction,
    OpeningPolicy,
    WallFacts,
)

SURVEY = Provenance(Source.SURVEY, Authority.AUTHORITATIVE, as_of=date(2026, 1, 1), ref="TAB-1")
GIS = Provenance(Source.GIS, Authority.INDICATIVE, ref="public layer")
GUESS = Provenance(Source.USER, Authority.ASSUMED)


def _plot() -> MultiRegion:
    return MultiRegion.of(Region(Ring.rectangle(0, 0, 20, 24)))


# ------------------------------------------------------------------ parcel vs buildable

def test_parcel_and_buildable_region_are_different_concepts():
    """A parcel is a legal identity; it is not a permission to build (report §5, task §6)."""
    parcel = Parcel("gush-1/helka-2", _plot(), SURVEY, legal_ref="1/2")
    site = SiteConstraints(parcel=parcel)
    assert parcel.geometry.area() == pytest.approx(480)
    assert not site.buildable.is_known


def test_unknown_buildable_region_refuses_to_be_read():
    """The failure this type exists to prevent: silently falling back to the parcel boundary."""
    buildable = BuildableRegion.unknown("no building lines available for this plan")
    assert buildable.knowledge is Knowledge.UNKNOWN
    with pytest.raises(UnknownBuildableRegionError, match="must not be inferred from the parcel"):
        buildable.require_known()


def test_unknown_reason_is_carried_into_the_error():
    buildable = BuildableRegion.unknown("plan 1234 not digitized")
    with pytest.raises(UnknownBuildableRegionError, match="plan 1234 not digitized"):
        buildable.require_known()


def test_known_buildable_region_returns_its_geometry():
    geom = MultiRegion.of(Region(Ring.rectangle(3, 5.5, 14, 14.5)))
    buildable = BuildableRegion.known(geom, SURVEY, derived_from=("setback-front",))
    assert buildable.is_known
    assert buildable.require_known().area() == pytest.approx(14 * 14.5)
    assert buildable.derived_from == ("setback-front",)


def test_known_without_geometry_is_impossible():
    with pytest.raises(ValueError, match="must carry geometry"):
        BuildableRegion(Knowledge.KNOWN, None)


def test_unknown_carrying_geometry_is_impossible():
    """Partial knowledge is modelled as KNOWN with weaker provenance, never as UNKNOWN plus a
    guess sitting in the geometry field."""
    with pytest.raises(ValueError, match="must not carry geometry"):
        BuildableRegion(Knowledge.UNKNOWN, _plot())


# ------------------------------------------------------------------ constraints

def test_constraint_roles_cover_the_required_vocabulary():
    assert {r.value for r in ConstraintRole} == {
        "PARCEL_BOUNDARY", "BUILDABLE_REGION", "NO_BUILD_REGION",
        "OBSTACLE", "SETBACK_REGION", "ACCESS_REQUIRED_REGION",
    }


def test_exclusion_region_is_expressible_as_a_constraint():
    disc = MultiRegion.of(Region(Ring.circle(8.0, 8.0, 2.5)))
    c = GeometricConstraint("tree-1", ConstraintRole.NO_BUILD_REGION, disc, GIS,
                            note="protected tree clearance")
    assert c.subtracts_from_envelope
    assert c.geometry.contains_point((8.0, 8.0))


def test_obstacle_does_not_shrink_the_envelope_but_no_build_does():
    """The distinction the report insists on keeping: NO_BUILD shrinks, OBSTACLE punches a hole
    inside — different because a hole is what the rectangular solver cannot represent."""
    geom = MultiRegion.of(Region(Ring.rectangle(1, 1, 1, 1)))
    assert GeometricConstraint("s", ConstraintRole.SETBACK_REGION, geom, SURVEY).subtracts_from_envelope
    assert not GeometricConstraint("o", ConstraintRole.OBSTACLE, geom, SURVEY).subtracts_from_envelope


def test_site_constraints_can_be_filtered_by_role():
    geom = MultiRegion.of(Region(Ring.rectangle(1, 1, 1, 1)))
    site = SiteConstraints(
        parcel=Parcel("p", _plot(), SURVEY),
        constraints=(
            GeometricConstraint("a", ConstraintRole.OBSTACLE, geom, SURVEY),
            GeometricConstraint("b", ConstraintRole.NO_BUILD_REGION, geom, GIS),
        ),
    )
    assert len(site.by_role(ConstraintRole.OBSTACLE)) == 1
    assert site.by_role(ConstraintRole.SETBACK_REGION) == ()


# ------------------------------------------------------------------ provenance

def test_provenance_separates_source_from_authority():
    """Public GIS geometry is real data and is not legally relyable — two independent axes."""
    assert GIS.source is Source.GIS
    assert not GIS.is_authoritative
    assert SURVEY.is_authoritative


def test_authority_propagates_pessimistically():
    assert weakest_of(SURVEY, SURVEY) is Authority.AUTHORITATIVE
    assert weakest_of(SURVEY, GIS) is Authority.INDICATIVE
    assert weakest_of(SURVEY, GIS, GUESS) is Authority.ASSUMED


def test_unrecorded_provenance_counts_as_assumed():
    assert weakest_of(SURVEY, None) is Authority.ASSUMED


def test_site_authority_is_the_weakest_input():
    site = SiteConstraints(
        parcel=Parcel("p", _plot(), SURVEY),
        constraints=(GeometricConstraint("c", ConstraintRole.NO_BUILD_REGION, _plot(), GIS),),
    )
    assert site.effective_authority() is Authority.INDICATIVE


# ------------------------------------------------------------------ wall facts (task §7)

def test_exterior_rc_safe_room_wall_preserves_both_facts():
    """The exact defect the vertical slice hit: an enum that keeps only the precedence winner
    destroys the EXTERIOR fact for a ממ"ד wall on the envelope."""
    facts = WallFacts(BoundaryContext.EXTERIOR, Construction.RC_SAFE_ROOM)
    assert facts.boundary_context is BoundaryContext.EXTERIOR
    assert facts.construction is Construction.RC_SAFE_ROOM
    assert facts.is_on_envelope
    assert facts.can_take_a_window


def test_interior_safe_room_wall_permits_no_opening():
    facts = WallFacts(BoundaryContext.INTERIOR, Construction.RC_SAFE_ROOM)
    assert facts.opening_policy is OpeningPolicy.NONE_PERMITTED
    assert not facts.can_take_a_window


def test_exterior_safe_room_opening_is_restricted_not_free():
    assert WallFacts(BoundaryContext.EXTERIOR, Construction.RC_SAFE_ROOM).opening_policy \
        is OpeningPolicy.RESTRICTED


def test_ordinary_exterior_wall_takes_a_window_freely():
    facts = WallFacts(BoundaryContext.EXTERIOR, Construction.STANDARD_PARTITION)
    assert facts.opening_policy is OpeningPolicy.FREE
    assert facts.can_take_a_window


def test_open_plan_boundary_is_not_a_wall_to_cut_into():
    facts = WallFacts(BoundaryContext.INTERIOR, Construction.NONE)
    assert facts.opening_policy is OpeningPolicy.NONE_PERMITTED


# ------------------------------------------------------------------ quantization (task §8)

def test_rounding_mode_cannot_be_omitted():
    """Keyword-only and no default: quantizing by accident is a TypeError, not a silent
    nearest-rounding."""
    with pytest.raises(TypeError):
        quantize_m(1.23)  # type: ignore[call-arg]


def test_inward_never_gains_area_and_outward_never_loses_it():
    value = 1.23  # 24.6 grid units
    assert quantize_m(value, rounding=Rounding.INWARD) == 24
    assert quantize_m(value, rounding=Rounding.OUTWARD) == 25
    assert quantize_m(value, rounding=Rounding.NEAREST_UNSAFE) == 25


def test_nearest_can_gain_nonexistent_space_which_is_why_it_is_named_unsafe():
    value = 1.24  # 24.8 units — nearest rounds UP, claiming space that is not there
    assert quantize_m(value, rounding=Rounding.NEAREST_UNSAFE) == 25
    assert quantize_m(value, rounding=Rounding.INWARD) == 24


def test_exact_grid_values_are_not_bumped_by_float_error():
    """0.30 / 0.05 evaluates to 5.999999999999999 in IEEE-754; naive floor would return 5."""
    assert length_units_no_overstate(0.30) == 6
    assert clearance_units_no_understate(0.30) == 6
    assert lower_bound_units(0.30) == 6
    assert upper_bound_units(0.30) == 6


def test_bounds_helpers_shrink_the_region_from_both_sides():
    assert lower_bound_units(1.21) == 25   # ceil — moves the low edge inward
    assert upper_bound_units(1.29) == 25   # floor — moves the high edge inward


def test_clearance_is_never_understated_and_length_never_overstated():
    assert clearance_units_no_understate(0.26) == 6   # 5.2 -> 6
    assert length_units_no_overstate(0.29) == 5       # 5.8 -> 5
