"""Furnishability / usability validation (`app/vertical_slice/furnishability.py`, Issue #40).

Fixtures here construct `RoomOut`/`DoorOut`/`GeometricDesign` BY HAND, exactly the pattern
`test_interior_layout.py` already uses (see that file's own module docstring for why a hand-built
design is exactly as authoritative an input as a solved one for a module that reasons purely about
realized geometry).
"""
from __future__ import annotations

from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut
from app.vertical_slice.furnishability import (
    ACCEPTABLE,
    GOOD,
    POOR,
    UNUSABLE,
    compute_usability,
    compute_usability_for_room,
)
from app.vertical_slice.interior_layout import layout_for_room
from app.vertical_slice.validation import check_furnishability

_NO_DOOR = DoorOut(a="OUTSIDE", b="NOWHERE", kind="ENTRANCE_DOOR", width_m=0.0,
                   center_m=(-100.0, -100.0), orientation="horizontal", placeable=False,
                   shared_length_m=0.0)


def _room(zone_id: str, roles: tuple[str, ...], w: float, h: float,
         x: float = 0.0, y: float = 0.0) -> RoomOut:
    return RoomOut(
        zone_id=zone_id, roles=roles, rect_m=(x, y, w, h), net_w_m=w, net_h_m=h,
        net_area_m2=round(w * h, 4),
        walls={s: "OPEN" for s in ("N", "S", "E", "W")},
        wall_facts={},
    )


def _design(rooms: tuple[RoomOut, ...], doors: tuple[DoorOut, ...] = ()) -> GeometricDesign:
    total_w = max(r.rect_m[0] + r.rect_m[2] for r in rooms)
    total_h = max(r.rect_m[1] + r.rect_m[3] for r in rooms)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 40.0, 40.0), footprint_m=(0.0, 0.0, total_w, total_h),
        rooms=rooms, interior_doors=doors, entrance_door=_NO_DOOR, windows=(),
        parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=total_w * total_h,
        net_area_m2=round(sum(r.net_area_m2 for r in rooms), 4), wall_iterations=0,
    )


# --------------------------------------------------------------------------- AC-1: UNUSABLE

def test_unusable_bedroom_fails_c30():
    """AC-1: a bedroom too small to place a bed + wardrobe AT ALL is UNUSABLE, and C30
    (`validation.check_furnishability`) fails it — never raises, always data first."""
    room = _room("BEDROOM", ("BEDROOM",), 1.0, 1.0)
    design = _design((room,))
    layout = layout_for_room(room, design)
    assert layout.placed == ()
    assert {u.kind for u in layout.unplaceable} == {"BED", "WARDROBE"}

    usability = compute_usability_for_room(room, design, layout)
    assert usability.tier == UNUSABLE
    assert usability.required_placed is False
    assert "BED" in usability.missing_required
    assert usability.reasons

    check = check_furnishability(design)
    assert check.check_id == "C30"
    assert check.passed is False
    assert "BEDROOM" in check.detail and "BED" in check.detail


# --------------------------------------------------------------------------- AC-2: POOR, not failed

def test_blocked_path_is_poor_not_failed():
    """AC-2: a bedroom with BOTH required objects placed, but whose only door has no straight,
    unobstructed line to the wardrobe (the bed's own footprint sits in the way), is POOR — a
    ranking/disclosure signal, never a C30 failure. Built through the REAL placer
    (`layout_for_room`), not a hand-built `RoomLayout`, so this proves the real placement +
    tiering + C30 code path end to end, not just the tiering function in isolation.

    Geometry: a 4.0 x 2.2 m room. The door sits on the EAST wall; with east excluded, the bed
    (1.4 x 2.0 m) takes the longest wall (north) and, at 2.2 m room depth, its own clearance zone
    (2.2 m deep, the room's full depth) spans the room's x in [1.3, 2.7]. The wardrobe is pushed to
    the west wall. A straight line from the door (x=4.0) to the wardrobe (x<=1.2) at the door's own
    y passes straight through the bed's x-span — the wardrobe has no unobstructed line to the door;
    the bed, entered first along the same corridor, still does.
    """
    room = _room("BEDROOM", ("BEDROOM",), 4.0, 2.2)
    door = DoorOut(a="HALL", b="BEDROOM", kind="ROOM_DOOR", width_m=0.9, center_m=(4.0, 1.1),
                  orientation="vertical", placeable=True, shared_length_m=0.9,
                  swings_into="BEDROOM", hinge_m=(4.0, 0.65), swing_deg=180.0)
    design = _design((room,), doors=(door,))

    layout = layout_for_room(room, design)
    assert {o.kind for o in layout.placed} == {"BED", "WARDROBE"}
    assert layout.unplaceable == ()

    usability = compute_usability_for_room(room, design, layout)
    assert usability.required_placed is True
    assert usability.access_path_clear is False
    assert usability.blocked_objects == ("WARDROBE",)
    assert usability.tier == POOR

    check = check_furnishability(design)
    assert check.check_id == "C30"
    assert check.passed is True, check.detail  # POOR never fails C30 — only UNUSABLE does


# --------------------------------------------------------------------------- coverage: every room, tiers

def test_compute_usability_covers_every_room_and_generous_rooms_are_not_unusable():
    """`compute_usability` returns one record per room in the design, in room order; a room
    generously sized (well above its role's `interior_layout.py` item specs, no doors/windows
    competing for a wall) is never UNUSABLE."""
    bedroom = _room("BEDROOM", ("BEDROOM",), 4.0, 4.0)
    living = _room("LIVING", ("LIVING",), 4.5, 4.5, x=0.0, y=4.0)
    study = _room("STUDY", ("STUDY",), 3.0, 3.0, x=0.0, y=8.5)  # out of REQUIRED_ITEMS' scope
    design = _design((bedroom, living, study))

    records = compute_usability(design)
    assert [u.room_id for u in records] == ["BEDROOM", "LIVING", "STUDY"]
    by_id = {u.room_id: u for u in records}
    assert by_id["BEDROOM"].tier in (GOOD, ACCEPTABLE)
    assert by_id["LIVING"].tier in (GOOD, ACCEPTABLE)
    # STUDY has no required items at all (out of `interior_layout.py`'s own placement scope) — it
    # is still reported, and can never be UNUSABLE on that account.
    assert by_id["STUDY"].required_placed is True
    assert by_id["STUDY"].tier != UNUSABLE
    for u in records:
        assert u.tier != UNUSABLE
        assert u.clearance_satisfied is True
