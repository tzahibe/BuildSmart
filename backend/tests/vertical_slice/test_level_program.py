"""`level_program.allocate_levels` — allocation A / C, the building-level wet-room rule, and the
level-local warning that replaces the strict per-level refusal the Phase 1 investigation measured.
"""
from __future__ import annotations

from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.level_program import (
    GroundLayout,
    allocate_levels,
    closed_fallback,
    with_upper_strip,
)
from app.vertical_slice.spec import ProgramSpec, PublicPrivateStrategy


def _program(**kw) -> ProgramSpec:
    base = dict(bedrooms=3, wet_rooms=2, safe_room=True, open_plan_living=True, parking_spaces=2)
    base.update(kw)
    return ProgramSpec(**base)


def test_two_strategies_are_offered_a_before_c():
    allocations = allocate_levels(_program())
    assert [a.strategy for a in allocations] == [
        PublicPrivateStrategy.PUBLIC_BELOW_PRIVATE_ABOVE,
        PublicPrivateStrategy.PUBLIC_PLUS_ONE_BEDROOM_BELOW,
    ]


def test_allocation_a_puts_every_bedroom_upstairs_and_the_ground_is_closed_kitchen():
    a = allocate_levels(_program())[0]
    upstairs_bedrooms = [r for r in a.upper.rooms if r.role in
                         (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)]
    assert len(upstairs_bedrooms) == 3   # master + 2 secondary
    assert not any(r.role in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM) for r in a.ground.rooms)
    assert a.ground.ground_layout is GroundLayout.CLOSED_KITCHEN
    assert any("kitchen is closed" in w for w in a.ground.warnings)


def test_allocation_c_moves_one_secondary_bedroom_down_and_tries_open():
    c = allocate_levels(_program())[1]
    ground_bedrooms = [r for r in c.ground.rooms if r.role is ProgramRole.BEDROOM]
    assert len(ground_bedrooms) == 1
    assert c.ground.ground_layout is GroundLayout.OPEN
    kitchen_in_strip = any(r.zone_id == "KITCHEN" for row in c.ground.strip_rows for r in row)
    assert kitchen_in_strip   # a genuinely open LDK: kitchen stayed with living/dining


def test_closed_fallback_reproduces_c_with_the_kitchen_moved_and_the_same_upper():
    c = allocate_levels(_program())[1]
    fallback = closed_fallback(c, _program())
    assert fallback is not None
    assert fallback.ground.ground_layout is GroundLayout.CLOSED_KITCHEN
    assert fallback.upper is c.upper
    # the same rooms, just regrouped between the two columns
    assert {r.zone_id for r in fallback.ground.rooms} == {r.zone_id for r in c.ground.rooms}


def test_closed_fallback_is_none_for_allocation_a_which_is_already_closed():
    a = allocate_levels(_program())[0]
    assert closed_fallback(a, _program()) is None


def test_building_level_wet_room_invariant_is_the_only_upfront_gate():
    # a programme the SINGLE-LEVEL invariant already rejects (an unstated wet room, no shared
    # bathroom for it to be) must not reach allocation at all.
    from app.vertical_slice.spec import WetRoomKind, WetRoomRequirement
    bad = _program(wet_rooms=2, wet_room_kinds=(
        WetRoomRequirement(WetRoomKind.ENSUITE),
        WetRoomRequirement(WetRoomKind.ENSUITE, host="BEDROOM_1"),
    ))
    assert allocate_levels(bad) == ()


def test_a_level_with_a_bedroom_and_no_bathroom_is_a_warning_never_a_refusal():
    # allocation C with only 1 wet room: the one bathroom goes upstairs (the master's need is
    # HARD-ish by construction — upper always gets one first); the ground's lone bedroom then has
    # none of its own. Phase 1's rule: warn, never fabricate, never refuse.
    c = allocate_levels(_program(wet_rooms=1))[1]
    assert c is not None   # NOT refused, unlike the investigation's strict harness (0/36 for C)
    assert any("no full bathroom" in w for w in c.ground.warnings)
    # nothing was added: still exactly 1 wet room in the whole building
    from app.vertical_slice.geometry_core.model import ProgramRole
    wet = sum(1 for level in (c.ground, c.upper) for r in level.rooms
             if r.role in (ProgramRole.BATHROOM, ProgramRole.TOILET))
    assert wet == 1


def test_with_upper_strip_places_k_secondary_bedrooms_ahead_of_the_master():
    a = allocate_levels(_program())[0]
    a1 = with_upper_strip(a, 1)
    strip_ids = [r.zone_id for row in a1.upper.strip_rows for r in row]
    assert strip_ids[-2] == "MASTER"          # master is always last but its ensuite
    assert strip_ids.count("BEDROOM_1") + strip_ids.count("BEDROOM_2") == 1
    a0 = with_upper_strip(a, 0)
    assert [r for row in a0.upper.strip_rows for r in row][0].zone_id == "MASTER"


def test_too_few_bedrooms_for_two_levels_refuses():
    assert allocate_levels(_program(bedrooms=1)) == ()
