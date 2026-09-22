"""C27 — displayed dimensions consistent with realized geometry (Issue #34).

`app.demo.contract.RoomOut` used to carry `width_m`/`depth_m` from the room's GROSS rectangle
while `area_m2` was the NET area — so the displayed width x depth never equalled the displayed
area. C27 (`app.vertical_slice.validation.check_realized_dimensions`) is the check that would have
caught this, run on the assembled `RoomOut` list inside `app.demo.contract.to_demo_design`, and
`app.demo.service` turns a failure into `DemoGenerationError("INCONSISTENT_GEOMETRY", ...)`.

On a real solved design C27 always passes — `net_rect_m` computes net width/height/area together,
so they cannot disagree unless something between the solver and the contract corrupts one of them.
These tests prove both halves: the check itself flags a tampered `RoomOut`-shaped object, and the
real demo path refuses (rather than silently showing a self-contradictory plan) when the
underlying geometry is tampered with.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.vertical_slice.design_output as design_output
from app.demo import service as svc
from app.vertical_slice.validation import check_realized_dimensions
from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project


def _room(id_="R1", width_m=3.0, depth_m=3.0, area_m2=9.0,
         gross_width_m=3.2, gross_depth_m=3.2, gross_area_m2=10.24):
    return SimpleNamespace(id=id_, width_m=width_m, depth_m=depth_m, area_m2=area_m2,
                           gross_width_m=gross_width_m, gross_depth_m=gross_depth_m,
                           gross_area_m2=gross_area_m2)


def test_c27_passes_a_self_consistent_room():
    check = check_realized_dimensions([_room()], gross_area_m2=10.24)
    assert check.check_id == "C27"
    assert check.passed, check.detail


def test_c27_fails_when_net_width_times_depth_disagrees_with_the_declared_net_area():
    # Exactly the historical bug: a GROSS rectangle's dims paired with the NET area.
    tampered = _room(width_m=3.2, depth_m=3.2, area_m2=9.0)
    check = check_realized_dimensions([tampered], gross_area_m2=10.24)
    assert not check.passed
    assert "R1" in check.detail and "!= declared net area" in check.detail


def test_c27_fails_when_the_net_rect_exceeds_its_own_gross_rect():
    tampered = _room(width_m=3.5, depth_m=3.5, area_m2=12.25,
                     gross_width_m=3.2, gross_depth_m=3.2, gross_area_m2=10.24)
    check = check_realized_dimensions([tampered], gross_area_m2=10.24)
    assert not check.passed
    assert "exceeds its own gross rect" in check.detail


def test_c27_fails_when_the_building_total_disagrees_with_the_sum_of_its_rooms():
    check = check_realized_dimensions([_room()], gross_area_m2=999.0)
    assert not check.passed
    assert "building gross area" in check.detail


def test_c27_fails_tampered_metadata_and_demo_refuses(monkeypatch):
    """The full demo path, with the solver's own `net_rect_m` tampered to corrupt every room's
    net area — simulating a future bug between the solver and the contract, not a hand-built
    fixture. The plan must refuse with INCONSISTENT_GEOMETRY rather than show a plan whose own
    numbers disagree with each other."""
    real_net_rect_m = design_output.net_rect_m

    def tampered_net_rect_m(zone_id, rect, walls):
        nw, nh, na = real_net_rect_m(zone_id, rect, walls)
        return nw, nh, round(na + 5.0, 4)   # corrupt the area only — dims stay real

    monkeypatch.setattr(design_output, "net_rect_m", tampered_net_rect_m)

    with pytest.raises(svc.DemoGenerationError) as exc_info:
        svc.generate_demo_design(_project(WIDE_SQUARE))
    assert exc_info.value.code == "INCONSISTENT_GEOMETRY"
    assert "C27" not in exc_info.value.message   # the person-facing message names no check id
