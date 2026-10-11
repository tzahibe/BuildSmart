"""Issue #142J — the proposer prompt no longer licenses access without contact, teaches the one-door
wet-room rule, and carries the brief's wet-room kinds and hosts instead of a flat list of BATHROOMs."""
from __future__ import annotations

from app.ai_harness.topology_poc import briefs, prompt
from app.vertical_slice.spec import WetRoomKind


def _brief(bedrooms, wet_rooms, open_plan=False):
    return briefs.Brief("T", "k", "p", bedrooms, wet_rooms, False, open_plan, 200.0, 14.0, 14.0, "medium", "square", {})


def test_system_prompt_requires_a_wall_for_every_door_and_one_door_per_wet_room():
    s = prompt.SYSTEM_PROMPT
    assert "accessed but not touching" not in s
    assert "REQUIRES that A and B share a wall" in s
    assert "A corridor between A and B is A->corridor and corridor->B, never A->B" in s
    assert "EXACTLY ONE door" in s
    assert "ENSUITE is entered only from its one host bedroom" in s
    assert "SHARED_BATHROOM or GUEST_WC is entered from the public side" in s
    assert "never from the kitchen or dining room" in s
    assert "Preferences such as 'near', 'clustered' or 'wet core' are NOT wall contacts" in s
    assert "spatial_adjacency is a HARD requirement" in s


def test_private_rooms_are_entered_only_from_circulation_142l():
    """#142L: the one sentence that removed the last remaining validity failure mode. It states an
    EXISTING rule — `access_rules.ALLOWED_ENTERED_FROM` already maps every PRIVATE_ROLES role to
    CIRCULATION_ROLES only, and C24 fails closed on it — so the prompt and the policy cannot drift."""
    from app.vertical_slice.access_rules import ALLOWED_ENTERED_FROM, CIRCULATION_ROLES, PRIVATE_ROLES
    s = prompt.SYSTEM_PROMPT
    assert "PRIVATE ROOMS" in s
    assert "entered ONLY from a hall or circulation space" in s
    assert "never from the living room, the kitchen, the dining room, or another bedroom" in s
    for role in PRIVATE_ROLES:                       # the prompt may not promise more than the policy
        assert ALLOWED_ENTERED_FROM[role] == CIRCULATION_ROLES, role


def test_programme_text_carries_wet_room_kinds_and_hosts_from_the_brief():
    rooms, text = prompt.build_brief_program_text(_brief(3, 3))
    ids = [r for r, _ in rooms]
    assert ids.count("BATHROOM_1") == 1 and "TOILET_1" in ids and "BATHROOM_2" in ids
    assert "BATHROOM_1(BATHROOM, ENSUITE of MASTER: exactly one door, from MASTER only)" in text
    assert "TOILET_1(TOILET, GUEST_WC: exactly one door, from HALL/circulation or LIVING)" in text
    assert "BATHROOM_2(BATHROOM, SHARED_BATHROOM: exactly one door, from HALL/circulation or LIVING)" in text
    kinds = [r.kind for r in briefs.brief_wet_room_kinds(_brief(3, 3))]
    assert kinds == [WetRoomKind.ENSUITE, WetRoomKind.GUEST_WC, WetRoomKind.SHARED_BATHROOM]


def test_stated_kinds_in_the_context_win_over_count_defaults():
    b = briefs.Brief("T", "k", "p", 2, 2, False, False, 150.0, 12.0, 12.0, "medium", "square",
                     {"wet_room_kinds": [{"kind": "shared_bathroom"}, {"kind": "guest_wc"}]})
    kinds = briefs.brief_wet_room_kinds(b)
    assert [k.kind for k in kinds] == [WetRoomKind.SHARED_BATHROOM, WetRoomKind.GUEST_WC]
    assert all(k.origin.value == "explicit" for k in kinds)
    _rooms, text = prompt.build_brief_program_text(b)
    assert "ENSUITE" not in text and "TOILET_1(TOILET, GUEST_WC" in text


def test_user_prompt_states_the_door_rules_in_the_schema_lines():
    from app.ai_harness.topology_poc.context import PromptContext
    ctx = PromptContext((), (), (), (), {}, (), 0, 0)          # an empty corpus context: only the schema lines matter here
    _sys, user = prompt.build_prompt(ctx, _brief(2, 2))
    assert "include every access pair here too" in user and "every wet room has exactly one door" in user
    assert "Wet-room kinds and hosts above are the brief's requirements" in user
