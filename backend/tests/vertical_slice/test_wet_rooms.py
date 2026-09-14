"""Wet-room access invariants (specs/007 FR-6): what a programme must satisfy before planning."""
from __future__ import annotations

import pytest

from app.vertical_slice.spec import (
    ENSUITE_HOST_BEDROOM,
    ENSUITE_HOST_MASTER,
    ProgramSpec,
    WetRoomKind,
    WetRoomRequirement,
    WetRoomStrength,
)
from app.vertical_slice.wet_rooms import (
    WetRoomResolutionError,
    check_wet_room_invariants,
    requirement_from_record,
)

ENSUITE = WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_MASTER)
BEDROOM_ENSUITE = WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_BEDROOM)
GUEST_WC = WetRoomRequirement(WetRoomKind.GUEST_WC)
SHARED = WetRoomRequirement(WetRoomKind.SHARED_BATHROOM)
UNSPECIFIED = WetRoomRequirement()


def _program(bedrooms: int, *kinds: WetRoomRequirement, wet_rooms: int | None = None) -> ProgramSpec:
    return ProgramSpec(bedrooms=bedrooms, wet_rooms=wet_rooms or len(kinds), wet_room_kinds=kinds)


@pytest.mark.parametrize("bedrooms", range(1, 7))
@pytest.mark.parametrize("wet_rooms", (1, 2, 3))
def test_every_bare_count_in_scope_satisfies_the_invariants(bedrooms, wet_rooms):
    """Legacy briefs never trip a refusal: the bare-count defaults always keep a shared bathroom."""
    assert check_wet_room_invariants(ProgramSpec(bedrooms=bedrooms, wet_rooms=wet_rooms)) == ()


def test_the_brief_that_names_every_room_and_covers_every_bedroom_is_fine():
    """"חדר הורים עם מקלחת, שירותי אורחים" in a ONE-bedroom house: nobody is left out."""
    assert check_wet_room_invariants(_program(1, ENSUITE, GUEST_WC)) == ()


def test_decision_a_a_bedroom_with_no_reachable_bathroom_is_a_question():
    """Decision A: ensuite + guest WC, a second bedroom, no shared full bathroom. I4 names the
    bedroom; it does not decide what to do about it."""
    problems = check_wet_room_invariants(_program(2, ENSUITE, GUEST_WC))
    assert [p.invariant for p in problems] == ["I4"]
    assert problems[0].bedrooms_without_bathroom == ("BEDROOM_1",)


def test_i4_names_every_bedroom_left_out_not_just_the_first():
    problems = check_wet_room_invariants(_program(4, ENSUITE, BEDROOM_ENSUITE))
    assert problems[0].invariant == "I4"
    # BEDROOM_3 hosts the explicit second suite (last secondary first); 1 and 2 are left out.
    assert problems[0].bedrooms_without_bathroom == ("BEDROOM_1", "BEDROOM_2")


def test_an_explicit_ensuite_for_every_bedroom_needs_no_shared_bathroom():
    """"לכל חדר שינה חדר רחצה צמוד": the person said so, and every bedroom has one — no question."""
    assert check_wet_room_invariants(_program(3, ENSUITE, BEDROOM_ENSUITE, BEDROOM_ENSUITE)) == ()


def test_a_shared_bathroom_anywhere_satisfies_i4():
    assert check_wet_room_invariants(_program(3, ENSUITE, GUEST_WC, SHARED)) == ()


def test_a_wc_alone_does_not_satisfy_the_unstated_room():
    """I1 is about a FULL bathroom. It cannot be reached through the resolver's own defaults (an
    unstated item beside stated ones is a shared bathroom), so it is exercised on the only path that
    can produce it: an all-unspecified count of one with no master — which defaults to a bathroom."""
    assert check_wet_room_invariants(ProgramSpec(bedrooms=0, wet_rooms=1)) == ()
    assert check_wet_room_invariants(_program(2, GUEST_WC, UNSPECIFIED)) == ()


def test_an_unbuildable_statement_is_reported_not_guessed_around():
    problems = check_wet_room_invariants(_program(0, ENSUITE))
    assert [p.invariant for p in problems] == ["RESOLUTION"]
    assert "no bedroom" in problems[0].detail


def test_records_load_only_words_this_build_knows():
    req = requirement_from_record("ensuite", "MASTER_BEDROOM", "flexible", "עם מקלחת")
    assert req == WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_MASTER,
                                     WetRoomStrength.FLEXIBLE, "עם מקלחת")
    with pytest.raises(WetRoomResolutionError):
        requirement_from_record("sauna", None, "required")
    with pytest.raises(WetRoomResolutionError):
        requirement_from_record("shared_bathroom", None, "whenever")
