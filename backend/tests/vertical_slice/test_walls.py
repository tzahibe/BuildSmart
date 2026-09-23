"""Wall semantic model (Issue #45) — AC-1: classes on the canonical fixture."""
from __future__ import annotations

from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.walls import WallClass, derive_walls


def test_classes_on_canonical_fixtures(tmp_path):
    result = run_demo(str(tmp_path / "canonical.svg"))
    design = result.design
    walls = derive_walls(design)

    # Exterior count equals the envelope sides. `wall_facts[side].boundary_context` IS the
    # geometric envelope fact each `RoomOut` side already carries (`geometry_adapter.envelope_
    # sides`, unchanged by this Issue) — an exterior zone-side is never split by a neighbour (no
    # other room's rect can lie outside the footprint), so it maps 1:1 onto exactly one `Wall`.
    envelope_sides = sum(
        1 for room in design.rooms for facts in room.wall_facts.values()
        if facts.boundary_context.value == "EXTERIOR"
    )
    exterior_walls = [w for w in walls if w.wall_class is WallClass.EXTERIOR]
    assert len(exterior_walls) == envelope_sides

    # Safe-room walls are PROTECTED, except the safe room's own envelope wall (EXTERIOR wins —
    # see the module docstring's precedence rationale).
    safe_room_walls = [w for w in walls if "SAFE_ROOM" in w.zones]
    assert safe_room_walls, "canonical fixture has no safe room — fixture drifted"
    for w in safe_room_walls:
        assert w.wall_class in (WallClass.PROTECTED, WallClass.EXTERIOR), (
            f"{w.id} touches SAFE_ROOM but is {w.wall_class.value}")
    assert any(w.wall_class is WallClass.PROTECTED for w in safe_room_walls)

    # Wet shared walls are WET_SERVICE: every interior wall bordering a BATHROOM/TOILET zone,
    # except one that also touches the safe room (PROTECTED wins over WET_SERVICE).
    wet_zone_ids = {r.zone_id for r in design.rooms if set(r.roles) & {"BATHROOM", "TOILET"}}
    assert wet_zone_ids, "canonical fixture has no wet room — fixture drifted"
    wet_walls = [w for w in walls if wet_zone_ids & set(w.zones)]
    assert any(w.wall_class is WallClass.WET_SERVICE for w in wet_walls)
    for w in wet_walls:
        assert w.wall_class in (WallClass.WET_SERVICE, WallClass.EXTERIOR, WallClass.PROTECTED), (
            f"{w.id} touches a wet room but is {w.wall_class.value}")
