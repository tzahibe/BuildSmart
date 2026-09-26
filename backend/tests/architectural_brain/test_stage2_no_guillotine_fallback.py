"""Issue #133 — Stage 2 (A/2) AC-3: the refusal contract.

A refusal names its reason and is NEVER substituted by a result from another realization path —
not the existing guillotine engine's own solved output, not Stage 1's own `rectilinear_realizer.
RealizedLayout`, not a bare dict shaped like either. `Stage2Result`/`ensure_stage2_result` are the
one place this is enforced structurally.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.vertical_slice.stage2 import contract as c


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
