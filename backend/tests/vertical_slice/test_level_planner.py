"""`level_planner.plan_level` — the pinned core-band planner: SHRUNK on the ground, FULL on the
upper (pinned to the ground's realized seam), ABSORBED only where eligible. Solved through
Geometry Core (unchanged) to prove the tree is real, not just accepted by the pre-checks.
"""
from __future__ import annotations

import pytest

from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.geometry_core.model import m_to_u, u_to_m
from app.vertical_slice.level_planner import (
    DEFAULT_SEAT,
    CoreLobbyForm,
    eligible_for_absorbed,
    plan_level,
)
from app.vertical_slice.level_program import allocate_levels, with_upper_strip
from app.vertical_slice.spec import ProgramSpec


def _program(**kw) -> ProgramSpec:
    base = dict(bedrooms=3, wet_rooms=2, safe_room=True, open_plan_living=True, parking_spaces=2)
    base.update(kw)
    return ProgramSpec(**base)


def _solved_candidate(candidates):
    """The first candidate that actually solves through Geometry Core, or None."""
    for c in candidates:
        try:
            return c, solve_fixture(c.concept.fixture)
        except GeometryInfeasible:
            continue
    return None, None


def test_ground_shrunk_plans_and_solves_with_a_smaller_lobby_than_full():
    a = allocate_levels(_program())[0]   # allocation A, closed-kitchen ground
    fw, fh = 10.25, 8.9
    shrunk, fail = plan_level(a.ground, fw, fh, 0, 0, DEFAULT_SEAT, CoreLobbyForm.SHRUNK, kind="ground")
    full, _ = plan_level(a.ground, fw, fh, 0, 0, DEFAULT_SEAT, CoreLobbyForm.FULL, kind="ground")
    assert shrunk and full, fail
    _, shrunk_solve = _solved_candidate(shrunk)
    _, full_solve = _solved_candidate(full)
    assert shrunk_solve is not None and full_solve is not None
    assert shrunk_solve.rects["HALL_2"].area_m2() < full_solve.rects["HALL_2"].area_m2()
    # the STAIR rectangle itself is unaffected by the lobby form
    assert shrunk_solve.rects["STAIR"].w == full_solve.rects["STAIR"].w
    assert shrunk_solve.rects["STAIR"].h == full_solve.rects["STAIR"].h


def test_shrunk_strip_room_reuses_an_eligible_guest_wc_rather_than_fabricating_storage():
    # 3 wet rooms: ensuite + guest WC + shared bath -> the corridor side has >= 2 wet rooms, so
    # the guest WC is eligible to become the strip room.
    a = allocate_levels(_program(wet_rooms=3))[0]
    fw, fh = 10.65, 9.25
    candidates, fail = plan_level(a.ground, fw, fh, 0, 0, DEFAULT_SEAT, CoreLobbyForm.SHRUNK, kind="ground")
    assert candidates, fail
    zone_ids = {z.zone_id for z in candidates[0].concept.fixture.zones}
    assert "SROOM" not in zone_ids   # no engine room fabricated
    assert "TOILET_1" in zone_ids    # the guest WC moved into the strip instead


def test_upper_full_pins_to_the_grounds_realized_seam():
    alloc = allocate_levels(_program())[0]
    fw, fh = 10.25, 8.9
    ground, _ = plan_level(alloc.ground, fw, fh, 0, 0, DEFAULT_SEAT, CoreLobbyForm.SHRUNK, kind="ground")
    g_cand, g_solve = _solved_candidate(ground)
    assert g_solve is not None
    seam_m = u_to_m(g_solve.rects["STAIR"].x)

    # k (how many secondary bedrooms sit ahead of the master) is the coordinator's own bounded
    # search, not this module's — try the small range directly, as the coordinator would.
    u_solve = None
    for k in range(0, 3):
        a = with_upper_strip(alloc, k)
        upper, fail = plan_level(a.upper, fw, fh, 0, 0, DEFAULT_SEAT, CoreLobbyForm.FULL, kind="upper",
                                 fixed_seam_m=seam_m, allow_deficit=True, allow_hard=True)
        if upper:
            _, u_solve = _solved_candidate(upper)
            if u_solve is not None:
                break
    assert u_solve is not None, "no k in [0,2] pinned to the ground's seam planned and solved"
    assert u_solve.rects["STAIR"].x == g_solve.rects["STAIR"].x
    assert u_solve.rects["STAIR"].w == g_solve.rects["STAIR"].w
    assert u_solve.rects["STAIR"].h == g_solve.rects["STAIR"].h


def test_seam_pinned_outside_window_is_refused_before_any_solve():
    a = with_upper_strip(allocate_levels(_program())[0], 0)
    candidates, fail = plan_level(a.upper, 10.25, 8.9, 0, 0, DEFAULT_SEAT, CoreLobbyForm.FULL,
                                  kind="upper", fixed_seam_m=0.5)
    assert not candidates
    assert fail.reason == "SEAM_PINNED_OUTSIDE_WINDOW"


def test_absorbed_requires_eligibility_and_is_refused_cleanly_when_not_eligible():
    # allocation A's upper (private, no open-plan group at all) is never eligible.
    a = with_upper_strip(allocate_levels(_program())[0], 1)
    assert not eligible_for_absorbed(a.upper)
    candidates, fail = plan_level(a.upper, 10.25, 8.9, 0, 0, DEFAULT_SEAT, CoreLobbyForm.ABSORBED,
                                  kind="upper")
    assert not candidates
    assert fail.reason == "ABSORBED_NOT_ELIGIBLE"


def test_absorbed_plans_and_solves_on_an_eligible_closed_kitchen_ground():
    # The follow-up report's own measurement (§1.4): ABSORBED's rear block must fit inside one
    # flight's length (~4.6 m) — a single trailing row (DINING, once the kitchen is closed and
    # moved to the corridor side) fits; DINING+KITCHEN together usually do not. Both allocations'
    # CLOSED_KITCHEN layout still has LIVING+DINING as one open-plan group, so it is eligible too.
    # No safe room here on purpose — an unrelated, pre-existing generator limitation
    # (`_column_min_width` under-budgets a safe room's RC wall allowance) can independently
    # refuse the SAME outline, which is not what this test is about.
    from app.vertical_slice.level_program import closed_fallback
    program = _program(safe_room=False)
    alloc = closed_fallback(allocate_levels(program)[1], program)
    assert eligible_for_absorbed(alloc.ground)
    found = False
    for fw, fh in ((9.65, 10.2), (10.65, 9.25), (11.95, 8.25), (12.5, 8.65)):
        for allow_deficit, allow_hard in ((False, False), (True, False), (False, True), (True, True)):
            candidates, fail = plan_level(alloc.ground, fw, fh, 0, 0, DEFAULT_SEAT, CoreLobbyForm.ABSORBED,
                                          kind="ground", allow_deficit=allow_deficit, allow_hard=allow_hard)
            if not candidates:
                continue
            cand, solve = _solved_candidate(candidates)
            if solve is not None:
                assert "HALL_2" not in solve.rects   # ABSORBED has no lobby room at all
                found = True
                break
        if found:
            break
    assert found, "no (outline, tier) in the tried set both planned and solved ABSORBED"


def test_absorbed_requires_at_least_two_open_plan_rooms():
    from dataclasses import replace
    a = allocate_levels(_program())[0]
    single_public = replace(a.ground, strip_rows=(a.ground.strip_rows[0],))
    assert not eligible_for_absorbed(single_public)


def test_outline_too_shallow_for_the_stair_is_refused_before_any_row_math():
    a = allocate_levels(_program())[0]
    candidates, fail = plan_level(a.ground, 10.0, 5.0, 0, 0, DEFAULT_SEAT, CoreLobbyForm.SHRUNK,
                                  kind="ground")
    assert not candidates
    assert fail.reason == "OUTLINE_TOO_SHALLOW_FOR_STAIR"
