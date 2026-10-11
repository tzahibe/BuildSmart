"""Issue #151 review follow-up (2026-10-01): a merged `LIVING_KITCHEN` `RoomOut`
(`app.vertical_slice.room_merge`) must split back into role-tagged LIVING/KITCHEN room refs so the
critic can measure adjacency/access for it, instead of silently reading as "no evidence" (`None`)
for every brief the merge fires on."""
from __future__ import annotations

from types import SimpleNamespace

from app.ai_harness.topology_poc.generator_adapter import topology_from_demo_design
from app.ai_harness.topology_poc.schema import ENTRANCE_ID


def _room(id_, type_, x, y, w, h):
    return SimpleNamespace(id=id_, type=type_, x=x, y=y, gross_width_m=w, gross_depth_m=h)


def _door(a, b, *, is_entrance=False):
    return SimpleNamespace(a=a, b=b, is_entrance=is_entrance)


def _design(rooms, doors, open_interfaces=()):
    return SimpleNamespace(rooms=rooms, doors=doors, open_interfaces=open_interfaces, quality=None)


def test_merged_living_kitchen_splits_into_two_measurable_rooms():
    design = _design(
        rooms=[
            _room("LK1", "LIVING_KITCHEN", 0.0, 0.0, 6.0, 4.0),
            _room("HALL1", "HALL", 6.0, 0.0, 2.0, 2.0),
            _room("BED1", "BEDROOM", 0.0, 4.0, 4.0, 3.0),
        ],
        doors=[
            _door("OUTSIDE", "HALL1", is_entrance=True),
            _door("HALL1", "LK1"),
        ],
    )
    topology = topology_from_demo_design(design)

    roles = {r.id: r.role for r in topology.rooms}
    assert set(roles.values()) == {"LIVING", "KITCHEN", "HALL", "BEDROOM"}
    living_id = next(rid for rid, role in roles.items() if role == "LIVING")
    kitchen_id = next(rid for rid, role in roles.items() if role == "KITCHEN")
    assert living_id != kitchen_id
    assert "LIVING_KITCHEN" not in roles.values()

    # the two split halves are always mutually touching/accessible (one undivided polygon)
    assert frozenset((living_id, kitchen_id)) in topology.spatial_adjacency
    assert (living_id, kitchen_id) in topology.access_graph
    assert (kitchen_id, living_id) in topology.access_graph

    # a door into the merged room gives access to BOTH split halves
    assert ("HALL1", living_id) in topology.access_graph
    assert ("HALL1", kitchen_id) in topology.access_graph

    # zoning follows the real role now, not the unmapped "LIVING_KITCHEN" -> service fallback
    assert living_id in topology.zones["public"]
    assert kitchen_id in topology.zones["public"]


def test_entrance_into_merged_room_reaches_both_halves():
    design = _design(
        rooms=[_room("LK1", "LIVING_KITCHEN", 0.0, 0.0, 6.0, 4.0)],
        doors=[_door("OUTSIDE", "LK1", is_entrance=True)],
    )
    topology = topology_from_demo_design(design)
    targets = {b for a, b in topology.access_graph if a == ENTRANCE_ID}
    assert targets == {r.id for r in topology.rooms}


def test_unmerged_rooms_keep_their_original_id():
    design = _design(
        rooms=[_room("LIVING1", "LIVING", 0.0, 0.0, 4.0, 4.0)],
        doors=[],
    )
    topology = topology_from_demo_design(design)
    assert [r.id for r in topology.rooms] == ["LIVING1"]
    assert [r.role for r in topology.rooms] == ["LIVING"]
