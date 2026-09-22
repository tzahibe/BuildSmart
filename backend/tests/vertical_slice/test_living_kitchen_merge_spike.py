"""Architecture A spike (Issue #107, Issue #102 §4.A) — LIVING+KITCHEN CLOSED_ADJACENT merge.

Direct unit proof of `room_merge.py`'s own logic and `contract._apply_room_merge`'s own payload
transform, independent of the solver — same style as `test_laundry_room.py`'s
`test_laundry_notice_uses_the_fixed_template_target_not_a_second_solve`: a hand-built
`design_output.RoomOut`/fake-design fixture, not a full pipeline solve, because what is under
test is the MERGE MODULE's own logic (candidate detection, geometry, the redesigned checks, the
contract-layer payload transform) — the real pipeline's own end-to-end behaviour (does a merge
actually fire on real corpus contexts, LOST=0) is measured separately by
`spikes/failure_log_sweep/living_kitchen_merge_ab.py` and reported in
`docs/reports/non-rectangular-geometry-architecture-a-spike.md`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.demo import contract
from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts
from app.vertical_slice import room_merge
from app.vertical_slice.design_output import RoomOut as SolvedRoomOut
from app.vertical_slice.validation import Check, ValidationReport

_EXT_PARTITION = WallFacts(BoundaryContext.EXTERIOR, Construction.STANDARD_PARTITION)
_INT_PARTITION = WallFacts(BoundaryContext.INTERIOR, Construction.STANDARD_PARTITION)


def _room(zone_id, roles, rect_m, net_w_m, net_h_m, wall_facts) -> SolvedRoomOut:
    net_area = round(net_w_m * net_h_m, 4)
    return SolvedRoomOut(zone_id=zone_id, roles=roles, rect_m=rect_m, net_w_m=net_w_m,
                         net_h_m=net_h_m, net_area_m2=net_area,
                         walls={s: "PARTITION" for s in wall_facts}, wall_facts=wall_facts)


def _living(rect_m=(0.0, 0.0, 5.0, 5.0), net_w_m=4.8, net_h_m=4.8, east=_INT_PARTITION):
    return _room("LIVING_1", ("LIVING",), rect_m, net_w_m, net_h_m,
                {"N": _EXT_PARTITION, "S": _EXT_PARTITION, "W": _EXT_PARTITION, "E": east})


def _kitchen(rect_m=(5.0, 1.0, 4.0, 3.0), net_w_m=3.8, net_h_m=2.8, west=_INT_PARTITION):
    return _room("KITCHEN_1", ("KITCHEN",), rect_m, net_w_m, net_h_m,
                {"N": _EXT_PARTITION, "S": _EXT_PARTITION, "E": _EXT_PARTITION, "W": west})


def _bedroom_far_away():
    return _room("BEDROOM_1", ("BEDROOM",), (20.0, 20.0, 3.0, 3.0), 2.8, 2.8,
                {"N": _EXT_PARTITION, "S": _EXT_PARTITION, "E": _EXT_PARTITION, "W": _EXT_PARTITION})


def _fake_design(rooms, open_groups=(), entrance_target="HALL_1", interior_doors=()):
    return SimpleNamespace(
        rooms=tuple(rooms), open_groups=tuple(open_groups),
        entrance_door=SimpleNamespace(b=entrance_target), interior_doors=tuple(interior_doors),
    )


def _passing_report(*check_ids: str) -> ValidationReport:
    report = ValidationReport()
    for check_id in check_ids:
        report.add(check_id, check_id, True, "ok")
    return report


# --------------------------------------------------------------------------- candidate detection


def test_flag_off_never_finds_or_applies_a_merge():
    assert room_merge.LIVING_KITCHEN_MERGE_ENABLED is False
    design = _fake_design([_living(), _kitchen()])
    report = _passing_report("C7", "C8", "C9", "C19")
    assert room_merge.plan_merge(design, report) is None


def test_open_plan_pair_is_not_a_closed_adjacent_candidate(monkeypatch):
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    design = _fake_design([_living(), _kitchen()], open_groups=[("LIVING_1", "KITCHEN_1")])
    assert room_merge.find_merge_candidate(design) is None
    assert room_merge.plan_merge(design, _passing_report()) is None


def test_non_adjacent_pair_is_not_a_candidate(monkeypatch):
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    far_kitchen = _kitchen(rect_m=(50.0, 50.0, 4.0, 3.0))
    design = _fake_design([_living(), far_kitchen])
    assert room_merge.find_merge_candidate(design) is None


def test_a_wall_other_than_a_standard_partition_is_not_a_candidate(monkeypatch):
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    rc_wall = WallFacts(BoundaryContext.INTERIOR, Construction.RC_SAFE_ROOM)
    design = _fake_design([_living(east=rc_wall), _kitchen()])
    assert room_merge.find_merge_candidate(design) is None


# --------------------------------------------------------------------------- the AC-1 case


def test_merged_room_passes_validation_and_renders_as_polygon(monkeypatch):
    """AC-1: a fixture with an adjacent LIVING/KITCHEN CLOSED_ADJACENT pair, flag ON, produces
    one merged L-shaped room that passes C1/C3/C6/C7/C8/C9/C14/C16/C19/C20/C26/C27 (redesigned/
    variant forms) and renders as a polygon."""
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    living, kitchen, bedroom = _living(), _kitchen(), _bedroom_far_away()
    design = _fake_design([living, kitchen, bedroom], entrance_target="HALL_1")
    # C7/C8/C9/C16/C19 are INHERITED from the plan's own already-passed whole-plan report — a
    # real solved plan that reached `to_demo_design` already required all of these to hold.
    report = _passing_report("C7", "C8", "C9", "C16", "C19")

    candidate = room_merge.find_merge_candidate(design)
    assert candidate is not None
    assert candidate.side == "E"

    result = room_merge.plan_merge(design, report)
    assert result is not None
    checks_by_id = {c.check_id: c for c in result.checks}
    for check_id in ("C1", "C2", "C3", "C6", "C7", "C8", "C9", "C14", "C16", "C19", "C20", "C26", "C27"):
        assert check_id in checks_by_id, f"{check_id} missing from the merge's own report"
        assert checks_by_id[check_id].passed, f"{check_id} failed: {checks_by_id[check_id].detail}"
    assert result.passed

    geometry = result.geometry
    # The union's own area is exactly the sum of the two source GROSS rectangles (25 + 12 m2) —
    # they only ever touch, never overlap.
    assert geometry.gross_area_m2 == pytest.approx(37.0, abs=0.01)
    assert geometry.net_area_m2 == pytest.approx(living.net_area_m2 + kitchen.net_area_m2, abs=0.01)
    # A genuine notch (kitchen's own W side, y in [1,4], is a strict subset of living's E side,
    # y in [0,5]) — the union is not itself a rectangle, i.e. this really is an L, not a flush
    # rectangle merge.
    assert len(geometry.polygon_m) > 4
    bbox_w, bbox_h = geometry.bbox_m[2], geometry.bbox_m[3]
    assert bbox_w * bbox_h > geometry.gross_area_m2, (
        "the bounding box must be strictly larger than the true polygon area for a real L — "
        "otherwise this fixture accidentally tests a rectangle, not the merge case")

    # Renders as a polygon: the contract-level payload transform produces ONE RoomOut, shape "L",
    # with a real polygon, and the two source rooms are gone.
    def _contract_room(zone_id, roles, area, x, y, w, h):
        return contract.RoomOut(id=zone_id, type=roles[0], name=roles[0], x=x, y=y,
                                width_m=w, depth_m=h, area_m2=area, gross_width_m=w,
                                gross_depth_m=h, gross_area_m2=round(w * h, 4), walls={})

    rooms_out = [
        _contract_room("LIVING_1", ("LIVING",), living.net_area_m2, 0.0, 0.0, 4.8, 4.8),
        _contract_room("KITCHEN_1", ("KITCHEN",), kitchen.net_area_m2, 5.0, 1.0, 3.8, 2.8),
        _contract_room("BEDROOM_1", ("BEDROOM",), bedroom.net_area_m2, 20.0, 20.0, 2.8, 2.8),
    ]
    walls = [
        contract.WallSegment(orientation="vertical", coord=5.0, start=1.0, end=4.0,
                             construction="STANDARD_PARTITION", boundary_context="INTERIOR",
                             room_ids=["LIVING_1", "KITCHEN_1"]),
        contract.WallSegment(orientation="horizontal", coord=0.0, start=0.0, end=5.0,
                             construction="STANDARD_PARTITION", boundary_context="EXTERIOR",
                             room_ids=["LIVING_1"]),
    ]
    doors = [
        contract.DoorOut(a="HALL_1", b="LIVING_1", kind="DOOR", width_m=0.9, x=0.0, y=2.0,
                         orientation="vertical"),
    ]
    new_rooms, new_walls, new_opens, new_doors = contract._apply_room_merge(
        result, rooms_out, walls, [], doors)

    ids = {r.id for r in new_rooms}
    assert "LIVING_1" not in ids and "KITCHEN_1" not in ids
    assert result.merged_id in ids
    merged = next(r for r in new_rooms if r.id == result.merged_id)
    assert merged.shape == "L"
    assert merged.polygon_m is not None and len(merged.polygon_m) > 4
    assert merged.area_m2 == pytest.approx(geometry.net_area_m2, abs=0.01)
    assert merged.gross_area_m2 == pytest.approx(geometry.gross_area_m2, abs=0.01)
    assert len(new_rooms) == len(rooms_out) - 1

    # The wall strictly between living and kitchen is gone entirely (interior to one room now,
    # not drawn at all); the exterior wall that used to name "LIVING_1" now names the merged id.
    assert not any(set(w.room_ids) == {"LIVING_1", "KITCHEN_1"} for w in new_walls)
    exterior = next(w for w in new_walls if w.boundary_context == "EXTERIOR")
    assert exterior.room_ids == [result.merged_id]

    # The door from the hall into the (former) living room now names the merged room.
    assert new_doors[0].a == "HALL_1" and new_doors[0].b == result.merged_id


def test_flush_merge_is_a_rectangle_not_a_degenerate_polygon(monkeypatch):
    """A regression guard for a real shapely bug this spike hit while measuring the corpus
    (`oriented_envelope` divides by zero on an already-axis-aligned rectangle): when the two
    source rectangles align flush (the Issue's own "or a rectangle if they happen to align
    flush" case), the union is a plain rectangle and `compute_geometry` must not crash."""
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    living = _living(rect_m=(0.0, 0.0, 5.0, 4.0), net_w_m=4.8, net_h_m=3.8)
    kitchen = _kitchen(rect_m=(5.0, 0.0, 3.0, 4.0), net_w_m=2.8, net_h_m=3.8)
    design = _fake_design([living, kitchen])
    candidate = room_merge.find_merge_candidate(design)
    assert candidate is not None
    geometry = room_merge.compute_geometry(candidate)
    assert geometry.bbox_m == pytest.approx((0.0, 0.0, 8.0, 4.0))
    assert geometry.gross_area_m2 == pytest.approx(32.0, abs=0.01)
    assert geometry.min_rotated_aspect == pytest.approx(2.0, abs=0.01)
    assert len(geometry.polygon_m) == 4


def test_merge_rejected_when_the_combined_pair_is_too_small(monkeypatch):
    """A candidate that IS geometrically CLOSED_ADJACENT but whose own combined size fails C3'
    is reported (`plan_merge` still returns a `MergeResult`) but never applied — the plan is
    drawn exactly as it would be with the flag off (`MergeOut.applied=False` at the contract
    layer)."""
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    tiny_kitchen = _kitchen(rect_m=(3.2, 1.0, 1.5, 1.0), net_w_m=1.3, net_h_m=0.8)
    design = _fake_design([_living(rect_m=(0.0, 0.0, 3.2, 3.2), net_w_m=3.0, net_h_m=3.0),
                           tiny_kitchen])
    report = _passing_report("C7", "C8", "C9", "C19")
    result = room_merge.plan_merge(design, report)
    assert result is not None
    assert result.passed is False
    c3 = next(c for c in result.checks if c.check_id == "C3")
    assert not c3.passed


def test_a_check_the_whole_plan_already_failed_is_not_silently_inherited_as_a_pass(monkeypatch):
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    design = _fake_design([_living(), _kitchen()])
    report = _passing_report("C8", "C9", "C19")  # C7 missing == the plan's own C7 failed
    result = room_merge.plan_merge(design, report)
    assert result is not None
    c7 = next(c for c in result.checks if c.check_id == "C7")
    assert not c7.passed
    assert result.passed is False
