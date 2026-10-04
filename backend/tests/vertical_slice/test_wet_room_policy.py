"""Issue #142I — ONE canonical wet-room entry policy (`wet_room_policy`), and every consumer derives
from it: the access-rules table (C24), C17, the realizer's door filter and the band pipeline's
selection legality. The rule: an ENSUITE only from its host; a shared wet room from HALL/CIRCULATION
or, as the specs/009 decision-C public fallback, LIVING; never a non-host bedroom, KITCHEN or DINING;
exactly one door."""
from __future__ import annotations

import pytest

from app.vertical_slice import access_rules, wet_room_policy
from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.wet_rooms import ResolvedWetRoom

SHARED = ResolvedWetRoom("BATH", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, True)
WC = ResolvedWetRoom("WC", WetRoomKind.GUEST_WC, None, WetRoomStrength.REQUIRED, True)
ENSUITE = ResolvedWetRoom("BATH", WetRoomKind.ENSUITE, "MASTER", WetRoomStrength.REQUIRED, True)
ROLES = {"HALL": (ProgramRole.HALL,), "CORR": (ProgramRole.CIRCULATION,), "LIVING": (ProgramRole.LIVING,),
         "KITCHEN": (ProgramRole.KITCHEN,), "DINING": (ProgramRole.DINING,), "MASTER": (ProgramRole.MASTER_BEDROOM,),
         "BEDROOM_1": (ProgramRole.BEDROOM,), "BATH": (ProgramRole.BATHROOM,), "WC": (ProgramRole.TOILET,)}


@pytest.mark.parametrize("wet,entrant,allowed,rank", [
    (SHARED, "HALL", True, 0), (SHARED, "CORR", True, 0), (SHARED, "LIVING", True, 1),
    (SHARED, "KITCHEN", False, 99), (SHARED, "DINING", False, 99), (SHARED, "MASTER", False, 99), (SHARED, "BEDROOM_1", False, 99),
    (WC, "HALL", True, 0), (WC, "LIVING", True, 1), (WC, "KITCHEN", False, 99),
    (ENSUITE, "MASTER", True, 0), (ENSUITE, "HALL", False, 99), (ENSUITE, "BEDROOM_1", False, 99), (ENSUITE, "LIVING", False, 99),
])
def test_canonical_rule(wet, entrant, allowed, rank):
    assert wet_room_policy.wet_room_entry_allowed(wet, entrant, ROLES[entrant]) is allowed
    assert wet_room_policy.entry_rank(wet, entrant, ROLES[entrant]) == rank


def test_access_rules_table_is_derived_from_the_policy():
    for role in access_rules.WET_ROLES:
        allowed = access_rules.ALLOWED_ENTERED_FROM[role]
        assert wet_room_policy.SHARED_WET_ROOM_ENTRY_ROLES <= allowed
        assert access_rules.BEDROOM_HOST_ROLES <= allowed
        assert not (wet_room_policy.FORBIDDEN_ENTRY_ROLES & allowed)
        assert allowed == access_rules.BEDROOM_HOST_ROLES | wet_room_policy.SHARED_WET_ROOM_ENTRY_ROLES


def test_realizer_filter_agrees_with_the_policy_and_keeps_one_door_class():
    pairs = [("HALL", "BATH"), ("LIVING", "BATH"), ("KITCHEN", "BATH"), ("MASTER", "BATH"), ("HALL", "MASTER")]
    kept = rr._filter_wet_room_access(pairs, ROLES, (SHARED,))
    assert kept == [("HALL", "BATH"), ("HALL", "MASTER")]                 # the living door is outranked, kitchen/master illegal
    kept = rr._filter_wet_room_access([("LIVING", "BATH"), ("KITCHEN", "BATH"), ("HALL", "MASTER")], ROLES, (SHARED,))
    assert kept == [("LIVING", "BATH"), ("HALL", "MASTER")]               # no hall: LIVING is the legal fallback
    kept = rr._filter_wet_room_access([("HALL", "BATH"), ("MASTER", "BATH")], ROLES, (ENSUITE,))
    assert kept == [("MASTER", "BATH")]
    for a, b in [("HALL", "BATH"), ("LIVING", "BATH")]:
        assert rr._wet_room_edge_allowed(SHARED, a, ROLES) is wet_room_policy.wet_room_entry_allowed(SHARED, a, ROLES[a])


def test_c17_holds_a_shared_bathroom_to_the_same_policy():
    """C17 on real geometry: a shared bathroom's single door from LIVING passes (specs/009 fallback);
    the same door against an ENSUITE requirement fails; a KITCHEN door fails."""
    from app.vertical_slice.geometry_core.model import (ConnectionKind, Cut, DesiredAccessEdge, DesiredAccessTopology,
                                                        Fixture, Leaf, Split, Wing, ZoneSpec, m_to_u)
    from tests.vertical_slice.test_c17_bathroom_access import _c17

    def fixture(entrant_role: ProgramRole):
        tree = Split(Cut.V, Leaf("HALL"), Split(Cut.V, Leaf("MASTER"), Split(Cut.V, Leaf("PUBLIC"), Leaf("BATH_1"), None), None), None)
        wing = Wing("W", 0, 0, m_to_u(16.0), m_to_u(4.0), tree)
        access = DesiredAccessTopology((DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
                                        DesiredAccessEdge("MASTER", "PUBLIC", ConnectionKind.DOOR),
                                        DesiredAccessEdge("PUBLIC", "BATH_1", ConnectionKind.DOOR)))
        zones = (ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 10, 20, 1.2, 8.0),
                 ZoneSpec("MASTER", (ProgramRole.MASTER_BEDROOM,), 10, 14, 25, 2.5),
                 ZoneSpec("PUBLIC", (entrant_role,), 10, 14, 25, 2.5),
                 ZoneSpec("BATH_1", (ProgramRole.BATHROOM,), 5, 8, 12, 1.6, 3.0))
        return Fixture("C17", (wing,), zones, access)

    shared = (ResolvedWetRoom("BATH_1", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, True),)
    ensuite = (ResolvedWetRoom("BATH_1", WetRoomKind.ENSUITE, "MASTER", WetRoomStrength.REQUIRED, True),)
    assert _c17(fixture(ProgramRole.LIVING), shared).passed
    assert not _c17(fixture(ProgramRole.LIVING), ensuite).passed
    assert not _c17(fixture(ProgramRole.KITCHEN), shared).passed
