"""End-to-end (§13): general geometry through the EXISTING slice, unmodified.

For each case: no room outside the authoritative buildable geometry, no overlap with exclusion
zones, topology still valid, doors/windows still valid, residuals reported.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.general_pipeline import run_general, run_general_from_site
from app.vertical_slice.safe_adapter import AdapterOutcome

BASELINE_GROSS_M2 = 170.4
BASELINE_NET_M2 = 153.83
BASELINE_WALL_ITERATIONS = 2


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    out = tmp_path_factory.mktemp("general")
    return {
        "A_rectangle": run_general_from_site(
            F.exact_rectangle(), render_path=str(out / "a.png"), plot_size_m=(20.0, 24.0)),
        "B_l_shape": run_general_from_site(F.l_shaped_site(), render_path=str(out / "b.png")),
        "C_concave_facade": run_general(F.concave_facade(), render_path=str(out / "c.png")),
        "D_obstacle": run_general_from_site(
            F.rectangular_obstacle_site(), render_path=str(out / "d.png")),
    }


CASE_IDS = ["A_rectangle", "B_l_shape", "C_concave_facade", "D_obstacle"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_case_runs_end_to_end(cases, case_id):
    result = cases[case_id]
    assert result.outcome is AdapterOutcome.SOLVED, result.notes
    assert result.design is not None
    assert result.render_path is not None


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_no_room_lies_outside_the_authoritative_buildable_geometry(cases, case_id):
    safety = cases[case_id].safety
    assert safety.rooms_inside_buildable, f"rooms outside buildable: {safety.offending_rooms}"


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_no_room_overlaps_an_exclusion_zone(cases, case_id):
    safety = cases[case_id].safety
    assert safety.rooms_clear_of_exclusions, f"rooms in exclusions: {safety.offending_rooms}"


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_all_slice_checks_still_pass(cases, case_id):
    report = cases[case_id].validation
    # C14/C15 only run when a corridor width or a relationship was requested; C16, C17 (bathroom
    # access against the programme's requirements), C18, C19 (exterior exposure), C20 (template
    # aspect), C21 (template maximum area), C23 (entrance opens into an allowed arrival room),
    # C24 (access topology obeys the door rules), C25 (Issue #22, no dead-space pocket at the
    # entrance), C26 (no extreme dedicated circulation) and C29 (Issue #37, wet-room privacy)
    # always do.
    assert len(report.checks) == 24
    assert report.ok, "; ".join(f"{c.check_id}: {c.detail}" for c in report.failures())


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_declared_topology_is_physically_realized(cases, case_id):
    """C13: every declared access edge has a real physical connection behind it."""
    report = cases[case_id].validation
    c13 = next(c for c in report.checks if c.check_id == "C13")
    assert c13.passed, c13.detail


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_doors_and_windows_remain_geometrically_valid(cases, case_id):
    design = cases[case_id].design
    assert all(d.placeable for d in design.interior_doors)
    assert design.entrance_door.placeable
    assert all(w.placeable for w in design.windows if w.width_m > 0)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_residual_space_is_explicitly_reported(cases, case_id):
    """Reported means accounted for — including the cases where there is legitimately none."""
    adapter = cases[case_id].adapter
    assert adapter.accounted_area_m2 == pytest.approx(adapter.authoritative_area_m2, abs=0.02)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_design_is_generated_not_the_canonical_fixture(cases, case_id):
    """Superseded the earlier assertion that every geometry case reproduced the canonical
    170.4 m2 design. That was true only while the general path reused the hand-authored
    concept; the generator now sizes the house to the programme and the safe wing, so the
    geometry legitimately differs per site. What must hold is that the design is real, complete
    and generated — and `test_canonical_run_demo_is_untouched_by_all_of_this` still pins the
    frozen baseline."""
    result = cases[case_id]
    design = result.design
    assert result.concept is not None
    assert design.gross_area_m2 > 100.0
    assert 0.80 < design.net_area_m2 / design.gross_area_m2 < 0.95
    assert design.wall_iterations >= 1
    assert len(design.rooms) == 10  # 3BR + safe room + 2 wet + LDK + hall
    assert design.gross_area_m2 != pytest.approx(BASELINE_GROSS_M2)


def test_l_shape_used_a_wing_rather_than_the_whole_bounding_box(cases):
    """The chosen candidate must be a real safe rectangle, not the L's bounding box."""
    result = cases["B_l_shape"]
    chosen = result.chosen_candidate
    assert chosen is not None
    assert chosen.area_m2 < result.adapter.authoritative_area_m2


def test_obstacle_case_shifted_the_footprint_away_from_the_shaft(cases):
    footprint = cases["D_obstacle"].design.footprint_m
    x, _, w, _ = footprint
    assert x + w <= 17.6 + 1e-9, "footprint must stop short of the shaft at x=17.6"


# ------------------------------------------------------------------ failure modes

def test_unknown_buildable_region_produces_no_design(tmp_path):
    result = run_general(F.unknown_buildable(), render_path=str(tmp_path / "x.png"))
    assert result.outcome is AdapterOutcome.BUILDABLE_REGION_UNKNOWN
    assert result.design is None
    assert not (tmp_path / "x.png").exists()


def test_region_too_small_reports_insufficient_capacity(tmp_path):
    result = run_general(F.too_small_for_programme(), render_path=str(tmp_path / "y.png"))
    assert result.outcome is AdapterOutcome.INSUFFICIENT_RECTANGULAR_CAPACITY
    assert result.design is None


def test_canonical_run_demo_is_untouched_by_all_of_this(tmp_path):
    """§12: the frozen vertical slice still produces its exact baseline."""
    from app.vertical_slice.pipeline import run_demo

    result = run_demo(str(tmp_path / "demo.png"))
    assert result.design.gross_area_m2 == pytest.approx(BASELINE_GROSS_M2)
    assert result.design.net_area_m2 == pytest.approx(BASELINE_NET_M2)
    assert result.design.wall_iterations == BASELINE_WALL_ITERATIONS
    # See FROZEN_SLICE_FAILS_C21 in test_baseline_and_decoupling.py: under the two-level maxima
    # the slice's 15.4 m2 bedrooms are inside the hard gate, so every check holds.
    assert result.validation.ok, "; ".join(f"{c.check_id}: {c.detail}" for c in result.validation.failures())
