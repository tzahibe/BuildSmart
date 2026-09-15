"""End-to-end tests for the first vertical slice: ArchitecturalSpec -> ... -> renderer.

Mirrors the acceptance list from the vertical-slice brief directly — each named validation
check is asserted individually (not just "overall pass"), so a future regression that breaks
one specific property (e.g. window exposure) fails with a precise, named test rather than a
generic pipeline failure.
"""
from __future__ import annotations

import os

import pytest

from app.vertical_slice.pipeline import run_demo, run_once
from app.vertical_slice.site import place_footprint
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec, demo_spec

ALL_CHECK_IDS = [f"C{i}" for i in range(1, 14)]


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("vslice") / "house.png"
    return run_demo(str(out))


def test_pipeline_runs_end_to_end_and_validation_passes_overall(result):
    # Except C21: the hand-authored slice's 5.7 m rooms column cannot hold a bedroom under the
    # template's 14 m2 — see FROZEN_SLICE_FAILS_C21 in test_baseline_and_decoupling.py.
    failed = [c.check_id for c in result.validation.failures()]
    assert failed == ["C21"], "; ".join(f"{c.check_id}: {c.detail}" for c in result.validation.failures())


@pytest.mark.parametrize("check_id", ALL_CHECK_IDS)
def test_each_named_validation_check_passes(result, check_id):
    check = next(c for c in result.validation.checks if c.check_id == check_id)
    assert check.passed, f"{check.check_id} {check.name}: {check.detail}"


def test_render_file_is_written_and_is_a_real_png(result):
    assert os.path.exists(result.render_path)
    assert os.path.getsize(result.render_path) > 10_000  # a blank/broken figure would be tiny
    with open(result.render_path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_gross_area_is_within_the_150_to_180_m2_target(result):
    assert 150.0 <= result.design.gross_area_m2 <= 180.0


def test_program_counts_match_the_brief(result):
    roles = [r for room in result.design.rooms for r in room.roles]
    assert roles.count("BEDROOM") + roles.count("MASTER_BEDROOM") == 3
    assert roles.count("SAFE_ROOM") == 1
    assert roles.count("BATHROOM") == 2
    assert len(result.design.parking_m) == 2
    assert any(room.roles == ("LIVING",) for room in result.design.rooms)


def test_open_plan_ldk_shares_a_wall_less_boundary(result):
    rooms = {r.zone_id: r for r in result.design.rooms}
    assert rooms["LIVING"].walls["S"] == "OPEN"
    assert rooms["DINING"].walls["N"] == "OPEN"
    assert rooms["DINING"].walls["S"] == "OPEN"
    assert rooms["KITCHEN"].walls["N"] == "OPEN"


def test_infeasible_plot_raises_with_a_clear_diagnostic_not_a_bad_house(tmp_path):
    tiny = ArchitecturalSpec(plot=PlotSpec(width_m=10.0, depth_m=10.0), program=ProgramSpec())
    with pytest.raises(ValueError, match="does not fit"):
        run_once(tiny, str(tmp_path / "out.png"))
    assert not (tmp_path / "out.png").exists()


def test_place_footprint_error_names_actual_and_required_sizes():
    tiny = ArchitecturalSpec(plot=PlotSpec(width_m=10.0, depth_m=10.0), program=ProgramSpec())
    with pytest.raises(ValueError) as exc:
        place_footprint(tiny, 12.0, 14.2)
    msg = str(exc.value)
    assert "12.0" in msg and "buildable envelope" in msg
