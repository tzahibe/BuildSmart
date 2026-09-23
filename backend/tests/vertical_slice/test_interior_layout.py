"""Engine-owned semantic layout objects (`app/vertical_slice/interior_layout.py`, Issue #39).

Fixtures here construct `RoomOut`/`DoorOut`/`WindowOut`/`GeometricDesign` BY HAND, exactly the
pattern `test_circulation_metrics.py::_hub_design` and `test_door_clearance.py` already use —
`interior_layout` reasons purely about realized geometry (rects, wall sides, door swings, windows),
never a zone_id lookup or a solver-internal type, so a hand-built design is exactly as authoritative
an input as a solved one and gives full control over each scenario's geometry. Every room here uses
`WallType.OPEN` walls (net == gross), the same convention `test_door_clearance.py` documents, since
this module's own checks are about furniture geometry, not wall-inset arithmetic.
"""
from __future__ import annotations

from shapely.geometry import box

from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts
from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut, WindowOut
from app.vertical_slice.interior_layout import (
    _swing_envelope,
    compute_layout,
    layout_for_room,
)

_OPEN = WallFacts(BoundaryContext.INTERIOR, Construction.NONE)
_NO_DOOR = DoorOut(a="OUTSIDE", b="NOWHERE", kind="ENTRANCE_DOOR", width_m=0.0,
                   center_m=(-100.0, -100.0), orientation="horizontal", placeable=False,
                   shared_length_m=0.0)


def _room(zone_id: str, roles: tuple[str, ...], w: float, h: float,
         x: float = 0.0, y: float = 0.0) -> RoomOut:
    return RoomOut(
        zone_id=zone_id, roles=roles, rect_m=(x, y, w, h), net_w_m=w, net_h_m=h,
        net_area_m2=round(w * h, 4),
        walls={s: "OPEN" for s in ("N", "S", "E", "W")},
        wall_facts={s: _OPEN for s in ("N", "S", "E", "W")},
    )


def _design(room: RoomOut, doors: tuple[DoorOut, ...] = (),
           windows: tuple[WindowOut, ...] = ()) -> GeometricDesign:
    return GeometricDesign(
        plot_m=(0.0, 0.0, 40.0, 40.0), footprint_m=(0.0, 0.0, room.rect_m[2], room.rect_m[3]),
        rooms=(room,), interior_doors=doors, entrance_door=_NO_DOOR, windows=windows,
        parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=room.rect_m[2] * room.rect_m[3], net_area_m2=room.net_area_m2,
        wall_iterations=0,
    )


def _box(rect) -> box:
    x, y, w, h = rect
    return box(x, y, x + w, y + h)


# --------------------------------------------------------------------------- AC-1

#: (role, roles tuple, generous net w/h, too-small net w/h, expected kinds placed on the generous
#: room). Generous dims are picked comfortably above each role's own item requirements (see
#: `interior_layout.py`'s item specs); too-small is 1.0x1.0 (or smaller for a WC), well under any
#: item's own footprint.
_ROLE_CASES = (
    ("BEDROOM", ("BEDROOM",), (4.0, 4.0), (1.0, 1.0), {"BED", "WARDROBE"}),
    ("MASTER_BEDROOM", ("MASTER_BEDROOM",), (4.5, 4.5), (1.0, 1.0), {"BED", "WARDROBE"}),
    ("LIVING", ("LIVING",), (4.5, 4.5), (1.0, 1.0), {"SOFA", "COFFEE_TABLE", "FOCAL_WALL"}),
    ("DINING", ("DINING",), (3.0, 3.0), (1.0, 1.0), {"DINING_TABLE"}),
    ("KITCHEN", ("KITCHEN",), (4.0, 2.5), (1.0, 1.0),
     {"REFRIGERATOR", "COUNTER_RUN", "SINK", "COOKTOP"}),
    ("BATHROOM", ("BATHROOM",), (3.0, 3.0), (0.3, 0.3), {"TOILET", "SINK", "SHOWER"}),
    ("TOILET", ("TOILET",), (2.2, 2.2), (0.3, 0.3), {"TOILET", "SINK"}),
)


def test_role_placers_on_canonical_and_too_small_fixtures():
    """AC-1: every role placer in scope produces objects with clearances on a generously-sized
    ("canonical") fixture for that role, and reports every one of its items `unplaceable` — never
    raising — on a deliberately too-small fixture."""
    for role, roles, generous, tiny, expected_kinds in _ROLE_CASES:
        generous_room = _room(role, roles, *generous)
        layout = layout_for_room(generous_room, _design(generous_room))
        placed_kinds = {o.kind for o in layout.placed}
        assert placed_kinds == expected_kinds, (role, placed_kinds, layout.unplaceable)
        assert layout.unplaceable == ()
        for obj in layout.placed:
            assert obj.room_id == role
            # Every clearance rect contains its own object's rect — a footprint plus its own
            # required use clearance, never a disjoint zone (`LayoutObject`'s own invariant).
            assert _box(obj.clearance_rect_m).contains(_box(obj.rect_m).buffer(-1e-6))

        tiny_room = _room(role, roles, *tiny)
        tiny_layout = layout_for_room(tiny_room, _design(tiny_room))
        assert tiny_layout.placed == ()
        unplaceable_kinds = {u.kind for u in tiny_layout.unplaceable}
        assert unplaceable_kinds == expected_kinds, (role, unplaceable_kinds)
        for u in tiny_layout.unplaceable:
            assert u.room_id == role and u.reason


def test_compute_layout_covers_every_room_in_order_and_skips_out_of_scope_roles():
    living = _room("LIVING", ("LIVING",), 4.5, 4.5)
    study = _room("STUDY", ("STUDY",), 4.0, 4.0)  # out of scope for this Issue — no items requested
    design = GeometricDesign(
        plot_m=(0.0, 0.0, 40.0, 40.0), footprint_m=(0.0, 0.0, 10.0, 10.0),
        rooms=(living, study), interior_doors=(), entrance_door=_NO_DOOR, windows=(),
        parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=100.0, net_area_m2=40.25, wall_iterations=0,
    )
    layouts = compute_layout(design)
    assert [rl.room_id for rl in layouts] == ["LIVING", "STUDY"]
    assert layouts[1].placed == () and layouts[1].unplaceable == ()
    assert {o.kind for o in layouts[0].placed} == {"SOFA", "COFFEE_TABLE", "FOCAL_WALL"}


# --------------------------------------------------------------------------- AC-2

def test_objects_avoid_walls_doors_and_each_other():
    """AC-2: on a room with a real door (nonzero swing envelope) and a window, every PLACED
    object's rect AND clearance rect stay inside the room's own net rectangle (walls), clear of the
    door's swing envelope, and clear of every other object's clearance rect — checked directly on
    the geometry, not by construction alone."""
    room = _room("KITCHEN", ("KITCHEN",), 4.0, 2.5)
    # A door on the west wall, swinging INTO the kitchen — width/hinge/swing chosen so the swept
    # quarter-circle is a real obstacle in the room's near corner.
    door = DoorOut(a="HALL", b="KITCHEN", kind="ROOM_DOOR", width_m=0.9, center_m=(0.0, 0.7),
                  orientation="vertical", placeable=True, shared_length_m=0.9,
                  swings_into="KITCHEN", hinge_m=(0.0, 0.25), swing_deg=0.0)
    window = WindowOut(zone_id="KITCHEN", side="N", width_m=1.2, center_m=(2.0, 0.0), placeable=True,
                       ventilation_status="EXTERIOR_WINDOW")
    design = _design(room, doors=(door,), windows=(window,))

    layout = layout_for_room(room, design)
    assert layout.placed, "expected at least one placed kitchen object to check"

    room_poly = _box(room.rect_m)
    swing_poly = _swing_envelope(door)
    assert swing_poly.area > 0.05  # a real, nonzero swept obstacle

    for obj in layout.placed:
        rect_poly = _box(obj.rect_m)
        clearance_poly = _box(obj.clearance_rect_m)
        # never overlaps a wall: even the clearance rect stays inside the room's net rectangle
        assert room_poly.buffer(1e-6).contains(clearance_poly), (obj.kind, obj.clearance_rect_m)
        # never overlaps the door's swing envelope
        assert clearance_poly.intersection(swing_poly).area < 1e-4, (obj.kind, "door swing")
        assert rect_poly.intersection(swing_poly).area < 1e-4, (obj.kind, "door swing (rect)")

    # never overlaps each other: every pair of placed objects' clearance rects is disjoint
    for i, a in enumerate(layout.placed):
        for b in layout.placed[i + 1:]:
            overlap = _box(a.clearance_rect_m).intersection(_box(b.clearance_rect_m)).area
            assert overlap < 1e-4, (a.kind, b.kind, overlap)


def test_living_footprints_never_overlap_and_coffee_table_sits_in_the_sofa_clearance():
    """LIVING's `COFFEE_TABLE` is placed INSIDE the `SOFA`'s own clearance rectangle by design — a
    coffee table belongs in the seating/conversation zone that clearance represents, the one
    documented exception to "clearance rects never overlap" (`interior_layout._place_coffee_table`).
    The physical FOOTPRINTS (`rect_m`) still never overlap — two solid objects cannot occupy the
    same floor space regardless of how their clearance zones relate."""
    room = _room("LIVING", ("LIVING",), 4.5, 4.5)
    layout = layout_for_room(room, _design(room))
    by_kind = {o.kind: o for o in layout.placed}
    assert {"SOFA", "COFFEE_TABLE", "FOCAL_WALL"} <= set(by_kind)

    for i, a in enumerate(layout.placed):
        for b in layout.placed[i + 1:]:
            assert _box(a.rect_m).intersection(_box(b.rect_m)).area < 1e-4, (a.kind, b.kind)

    assert _box(by_kind["SOFA"].clearance_rect_m).contains(_box(by_kind["COFFEE_TABLE"].rect_m))


def test_objects_avoid_each_other_on_a_multi_object_bathroom():
    """The same AC-2 pairwise-disjoint proof on a role that places several DIFFERENT-kind objects
    on potentially different walls (toilet/sink/shower), not just the kitchen's one adjacent run."""
    room = _room("BATH_1", ("BATHROOM",), 3.0, 3.0)
    layout = layout_for_room(room, _design(room))
    kinds = {o.kind for o in layout.placed}
    assert kinds == {"TOILET", "SINK", "SHOWER"}
    for i, a in enumerate(layout.placed):
        for b in layout.placed[i + 1:]:
            overlap = _box(a.clearance_rect_m).intersection(_box(b.clearance_rect_m)).area
            assert overlap < 1e-4, (a.kind, b.kind, overlap)
