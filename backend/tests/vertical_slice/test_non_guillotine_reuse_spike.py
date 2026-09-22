"""Issue #108 — Architecture B reuse spike (Issue #102's report §4.B).

Does the EXISTING rectangle-typed pipeline (validators, M1-M6, hub/L-massing/wet-core guards, both
renderers) accept a `dict[str, Rect]` that is NOT a slicing-tree output, with ZERO code changes,
as the investigation report's reuse table claims? `spikes/non_guillotine_reuse/hand_encoded_
fixture.py` hand-authors one such layout (never solver-generated) for the `l-3br-corner` reference
archetype. See docs/reports/non-rectangular-geometry-architecture-b-spike.md for the write-up this
file is evidence for.

AC-1 is `test_fixture_layout_is_genuinely_non_guillotine`. Every other test is AC-2 evidence: each
is named for the pipeline entry point it feeds the hand-encoded layout into, UNCHANGED — no test
here modifies any module under `app/`.
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from app.demo.contract import to_demo_design
from app.vertical_slice.validation import check_realized_dimensions
from app.vertical_slice import doors as doors_stage
from app.vertical_slice import furniture as furniture_stage
from app.vertical_slice import windows as windows_stage
from app.vertical_slice import validation as validation_stage
from app.vertical_slice.design_output import assemble
from app.vertical_slice.geometry_core.model import u_to_m
from app.vertical_slice.renderer import render

from spikes.geometry_shapes.measure_real_plan_shapes import is_guillotine_separable
from spikes.non_guillotine_reuse.hand_encoded_fixture import (
    build_fixture,
    build_rects,
    build_site_plan,
    build_walls,
    build_wet_rooms,
    build_wing_rects,
)


@pytest.fixture(scope="module")
def rects():
    return build_rects()


@pytest.fixture(scope="module")
def fixture():
    return build_fixture()


@pytest.fixture(scope="module")
def wing_rects():
    return build_wing_rects()


@pytest.fixture(scope="module")
def site(wing_rects):
    return build_site_plan(wing_rects)


@pytest.fixture(scope="module")
def walls(rects):
    return build_walls(rects)


def _room_polygons_m(rects) -> list[Polygon]:
    polys = []
    for r in rects.values():
        x, y, w, h = u_to_m(r.x), u_to_m(r.y), u_to_m(r.w), u_to_m(r.h)
        polys.append(Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    return polys


# --------------------------------------------------------------------------- AC-1

def test_fixture_layout_is_genuinely_non_guillotine(rects):
    """AC-1. Proven with the SAME recognition function `measure_real_plan_shapes.py` uses (not a
    reimplementation) against every room's real polygon: no straight full-length cut exists that
    avoids crossing a room's interior and splits the 9 rooms into two non-empty groups."""
    assert is_guillotine_separable(_room_polygons_m(rects)) is False


def test_fixture_layout_would_be_guillotine_if_the_pinwheel_core_were_removed(rects):
    """Control: the 4-room bedroom arm ALONE (no pinwheel) is an ordinary 2x2 grid — trivially
    guillotine-separable. This is what proves the non-guillotine result above comes from the
    pinwheel core, not from an always-False test (the same discipline the investigation's own
    script validates itself against its synthetic-spine control, §3.2)."""
    arm_only = {k: v for k, v in rects.items() if k in ("BED2", "BED3", "BATH1", "BATH2")}
    assert is_guillotine_separable(_room_polygons_m(arm_only)) is True


# --------------------------------------------------------------------------- AC-2: validators

@pytest.fixture(scope="module")
def realized(fixture, rects, walls, site):
    interior_doors = doors_stage.generate_interior_doors(fixture, rects)
    resolved = doors_stage.resolve_entrance(fixture, rects, site.footprint, site.wings)
    assert resolved is not None, "resolve_entrance (doors.py) returned None on the hand-encoded layout"
    entrance_zone_id = resolved[0]
    entrance_door = doors_stage.build_entrance_door(site.entrance, site.footprint, entrance_zone_id,
                                                     site.wings)
    windows = windows_stage.generate_windows(fixture, rects, site.footprint, site.wings)
    furniture = furniture_stage.check_furniture_feasibility(fixture, rects, walls)
    return interior_doors, entrance_door, windows, furniture


def test_doors_and_windows_generation_accept_the_layout_unchanged(realized):
    """`doors.generate_interior_doors`/`resolve_entrance`/`build_entrance_door` and
    `windows.generate_windows` — every declared interior door is placeable, and the entrance
    resolves against the hand-encoded layout's own street frontage, with none of these four
    functions changed."""
    interior_doors, entrance_door, windows, _furniture = realized
    assert len(interior_doors) == 8
    unplaceable = [f"{d.a}-{d.b}" for d in interior_doors if not d.placeable]
    assert not unplaceable, f"doors not placeable: {unplaceable}"
    assert entrance_door.placeable


@pytest.fixture(scope="module")
def report(fixture, rects, walls, site, realized):
    interior_doors, entrance_door, windows, furniture = realized
    return validation_stage.validate(
        fixture, rects, walls, interior_doors, entrance_door, windows, furniture, site,
        wet_rooms=build_wet_rooms(),
    )


#: Four of the five checks Issue #108 names explicitly, found inside `validate()`'s own
#: `ValidationReport` (see `test_named_validation_check_accepts_the_layout_unchanged`). C22 (wing
#: seams) is a sixth, non-negotiable one for a MULTI-WING fixture, added because the hand-encoded
#: layout is two wings. C27 is NOT one of `validate()`'s checks at all — see
#: `test_c27_dimension_consistency_accepts_the_design_unchanged` for why and how it is tested.
NAMED_CHECK_IDS = ("C1", "C3", "C9", "C20", "C22")


@pytest.mark.parametrize("check_id", NAMED_CHECK_IDS)
def test_named_validation_check_accepts_the_layout_unchanged(report, check_id):
    check = next(c for c in report.checks if c.check_id == check_id)
    assert check.passed, f"{check.check_id} {check.name}: {check.detail}"


def test_every_validation_check_that_ran_is_recorded(report):
    """Not itself an AC, but the evidence AC-2's report text is drawn from: every check id/name/
    pass-fail/detail the real `validate()` produced against this layout, unmodified."""
    ran = {c.check_id: (c.passed, c.detail) for c in report.checks}
    assert "C2" in ran, "C2 (no residual interior area) did not run at all"
    # Recorded, not asserted individually here (docs/reports/... quotes the ones that mattered):
    assert len(ran) >= 20


# --------------------------------------------------------------------------- AC-2: design_output
# / M1-M6 / the demo contract / both renderers

@pytest.fixture(scope="module")
def design(fixture, rects, walls, site, realized):
    interior_doors, entrance_door, windows, furniture = realized
    return assemble(fixture, rects, walls, 1, interior_doors, entrance_door, windows, furniture,
                    site, wet_rooms=build_wet_rooms())


def test_design_output_assemble_accepts_the_layout_unchanged(design):
    assert len(design.rooms) == 9
    assert design.gross_area_m2 > 0
    assert abs(design.net_area_m2) > 0


def test_demo_contract_and_m1_to_m6_quality_metrics_accept_the_design_unchanged(design, report):
    """`app.demo.contract.to_demo_design` — the exact function the product path calls — builds
    `_wall_segments` (the derivation §2.7 of the investigation flags as the highest-risk part of
    the contract) AND runs the REAL M1-M6 (`quality_metrics.measure_design`, called internally,
    `contract.py:1005`) in one call. Neither is reimplemented or mocked here."""
    demo = to_demo_design(design, report)
    assert len(demo.rooms) == 9
    assert len(demo.walls) > 0
    assert demo.quality.metrics is not None
    # M1: every habitable room's aspect was computed (not skipped/erroring) for at least the
    # bedroom-class rooms this fixture has.
    assert demo.quality.metrics.m1_habitable_aspect_median is not None


def test_c27_dimension_consistency_accepts_the_design_unchanged(design, report):
    """C27 is not one of `validate()`'s checks — `app.demo.contract.check_realized_dimensions`
    runs it separately, at the CONTRACT layer, against the displayed `RoomOut` list, raising
    `InconsistentGeometryError` on failure (`contract.py:971`). `to_demo_design` above already
    proves this indirectly (it would have raised); this calls the exact same function directly,
    on the exact same displayed rooms, for an explicit, named C27 result."""
    demo = to_demo_design(design, report)
    check = check_realized_dimensions(demo.rooms, demo.gross_area_m2)
    assert check.passed, f"{check.check_id}: {check.detail}"


def test_backend_renderer_accepts_the_design_unchanged(design, tmp_path):
    out = tmp_path / "l_3br_corner_hand_encoded.svg"
    render(design, str(out))
    assert out.exists() and out.stat().st_size > 500
    with open(out, "rb") as f:
        head = f.read(256)
    assert b"<svg" in head or b"<?xml" in head, "renderer did not produce a real SVG file"


def test_frontend_plan_canvas_payload_shape_is_unchanged(design, report):
    """The frontend (`frontend/src/design/DemoPlan.tsx`) draws every room as an independent SVG
    `<rect x=... y=... width={room.gross_width_m} height={room.gross_depth_m}>` and every wall as
    an independent `<line>` from `design.walls[]` — never reading room adjacency itself (confirmed
    by inspection of that file, out of scope for this backend test to execute directly: no browser
    runs here). What this test CAN verify mechanically is what actually crosses the wire: the
    `DemoDesign` JSON payload — the same JSON the real API endpoint returns to that component —
    round-trips with every field the component reads present, for a design assembled from a
    non-guillotine `dict[str, Rect]`."""
    demo = to_demo_design(design, report)
    payload = demo.model_dump(mode="json")
    for room in payload["rooms"]:
        for key in ("x", "y", "gross_width_m", "gross_depth_m", "width_m", "depth_m", "type"):
            assert key in room and room[key] is not None
    for wall in payload["walls"]:
        for key in ("orientation", "coord", "start", "end", "construction", "boundary_context"):
            assert key in wall
    # Round-trips through the pydantic model unchanged (the literal contract the API serves).
    from app.demo.contract import DemoDesign
    DemoDesign.model_validate(payload)
