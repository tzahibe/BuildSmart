"""Issue #133/#134 — Stage 2 AC-3/AC-5: the refusal contract, proven on synthetic objects (this
file's original scope, Issue #133) AND on the REAL Stage 2 pipeline (Issue #134's own addition
below): when `stage2.realizer.realize_layout` cannot honestly realize a layout, the caller gets a
`contract.RealizerRefusal` naming the failing constraint — never a `RealizedLayout`, never a result
from `geometry_core.engine`'s own guillotine solver (nothing in `stage2` ever calls it), and never
silently upgraded to a fallback success.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.stage2 import contract as c
from app.vertical_slice.stage2.realizer import RealizedLayout, realize_layout


def test_refusal_carries_a_stated_reason():
    result = c.Stage2Result.refuse("PINWHEEL_INFEASIBLE", "no thickness solution")
    assert result.ok is False
    assert result.refusal.reason == "PINWHEEL_INFEASIBLE"
    assert result.zones == ()


def test_refusal_reason_must_be_non_empty():
    with pytest.raises(ValueError, match="stated, non-empty reason"):
        c.Stage2Result.refuse("")
    with pytest.raises(ValueError):
        c.RealizerRefusal(reason="")


def test_success_carries_zones_and_no_refusal():
    zone = c.RealizedZone(zone_id="LIVING_0", repaired_cell_ids=("repaired__LIVING_0",),
                          donor_room_ids=("LIVING_0",))
    result = c.Stage2Result.success((zone,))
    assert result.ok is True
    assert result.refusal is None
    assert result.zones == (zone,)


def test_result_cannot_be_both_success_and_refusal():
    zone = c.RealizedZone(zone_id="LIVING_0", repaired_cell_ids=("repaired__LIVING_0",),
                          donor_room_ids=("LIVING_0",))
    with pytest.raises(ValueError, match="never both, never neither"):
        c.Stage2Result(zones=(zone,), refusal=c.RealizerRefusal(reason="X"))


def test_result_cannot_be_neither_success_nor_refusal():
    with pytest.raises(ValueError, match="never both, never neither"):
        c.Stage2Result(zones=(), refusal=None)


def test_ensure_stage2_result_accepts_a_genuine_result():
    refusal = c.Stage2Result.refuse("EMPTY_LAYOUT", "a layout needs at least one wing")
    assert c.ensure_stage2_result(refusal) is refusal


def test_ensure_stage2_result_rejects_a_plain_dict_shaped_like_a_result():
    fake = {"ok": False, "reason": "EMPTY_LAYOUT", "zones": []}
    with pytest.raises(TypeError, match="not a Stage2Result"):
        c.ensure_stage2_result(fake)


def test_ensure_stage2_result_rejects_a_guillotine_shaped_result_object():
    """Stands in for `geometry_core.engine`'s own solved output or Stage 1's own
    `rectilinear_realizer.RealizedLayout` — a DIFFERENT realization path's result, shaped similarly
    (an `ok` property, a `rects`/`zones`-like payload) but never accepted as a Stage 2 outcome."""

    @dataclass
    class GuillotineLikeResult:
        rects: dict
        report_ok: bool

        @property
        def ok(self) -> bool:
            return self.report_ok

    fallback = GuillotineLikeResult(rects={"LIVING": object()}, report_ok=True)
    assert fallback.ok is True  # looks like a success from ITS OWN path
    with pytest.raises(TypeError, match="not a Stage2Result"):
        c.ensure_stage2_result(fallback)


def test_ensure_stage2_result_rejects_none():
    with pytest.raises(TypeError, match="not a Stage2Result"):
        c.ensure_stage2_result(None)


def test_refusal_is_never_silently_upgraded_to_a_fallback_success():
    """The refusal itself, once produced, stays a refusal end to end — no code path in this
    contract module can turn a `RealizerRefusal` into a `Stage2Result.success` without an actual
    list of `RealizedZone`s to construct one from."""
    refusal_result = c.Stage2Result.refuse("NOTCH_INFEASIBLE", "no corner notch fits")
    checked = c.ensure_stage2_result(refusal_result)
    assert checked.ok is False
    assert checked.refusal.reason == "NOTCH_INFEASIBLE"
    assert checked.zones == ()


# ------------------------------------------------------- AC-5: the REAL pipeline, not a stand-in

def _two_zone_scenario(width_m: float, height_m: float) -> c.RealizerInput:
    """LIVING + KITCHEN, side by side — a genuine, minimal two-room scenario: sized generously it
    realizes cleanly; sized far too small the real realizer must refuse."""
    living = c.ZoneIntent(zone_id="LIVING_0", role=ProgramRole.LIVING, donor_room_id=None,
                          target_area_m2=16.0, min_area_m2=14.0, max_area_m2=20.0,
                          min_short_side_m=3.0, max_aspect_ratio=2.4)
    kitchen = c.ZoneIntent(zone_id="KITCHEN_0", role=ProgramRole.KITCHEN, donor_room_id=None,
                           target_area_m2=10.0, min_area_m2=9.0, max_area_m2=13.0,
                           min_short_side_m=2.4, max_aspect_ratio=2.8)
    row = c.RowWing(wing_id="row0", width_m=width_m, height_m=height_m,
                    slots=("LIVING_0", "KITCHEN_0"),
                    zones={"LIVING_0": living, "KITCHEN_0": kitchen}, groups={})
    return c.RealizerInput(name="ac5-scenario", wings=(row,), wet_rooms=())


def test_real_realizer_returns_a_contract_refusal_when_it_cannot_realize():
    """AC-5: a layout `stage2.realizer.realize_layout` cannot honestly realize returns a
    `contract.RealizerRefusal` carrying its reason — the SAME type this module's own synthetic
    tests above check, not a parallel shape a caller would need to translate."""
    result = realize_layout(_two_zone_scenario(width_m=1.0, height_m=1.0))
    assert isinstance(result, c.RealizerRefusal)
    assert result.reason
    assert not isinstance(result, RealizedLayout)


def test_real_realizer_refusal_is_never_a_guillotine_shaped_result():
    """The refusal the real realizer returns is never substitutable by ANY other realization
    path's result object — `ensure_stage2_result` rejects it exactly like the synthetic
    `GuillotineLikeResult` above, because a `RealizerRefusal` has no `ok`/`zones`/`rects` shape a
    caller could mistake for a success."""
    result = realize_layout(_two_zone_scenario(width_m=1.0, height_m=1.0))
    assert isinstance(result, c.RealizerRefusal)
    with pytest.raises(TypeError, match="not a Stage2Result"):
        c.ensure_stage2_result(result)
    wrapped = c.Stage2Result.refuse(result.reason, result.detail)
    assert c.ensure_stage2_result(wrapped) is wrapped
    assert wrapped.ok is False


def test_a_feasible_scenario_realizes_and_is_not_confused_with_a_refusal():
    """The positive control: the SAME realizer, given a scenario it CAN honestly build, returns a
    real `RealizedLayout` — proving the refusal above is about feasibility, not a broken realizer."""
    result = realize_layout(_two_zone_scenario(width_m=8.6, height_m=3.6))
    assert isinstance(result, RealizedLayout)
    assert not isinstance(result, c.RealizerRefusal)
