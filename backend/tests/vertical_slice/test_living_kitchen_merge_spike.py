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
from app.vertical_slice import quality_metrics, reference_benchmark, room_merge
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
    opens = [
        contract.OpenInterface(orientation="vertical", coord=9.0, start=1.0, end=3.0,
                               room_ids=["KITCHEN_1", "DINING_1"]),
    ]
    new_rooms, new_walls, new_opens, new_doors = contract._apply_room_merge(
        result, rooms_out, walls, opens, doors)

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

    # The open interface from the (former) kitchen to DINING now names the merged room too.
    assert new_opens[0].room_ids == [result.merged_id, "DINING_1"]


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


# ------------------------------------------------------------------- AC-1 (Issue #118): quality


def _contract_room(zone_id, type_, area, x, y, w, h) -> contract.RoomOut:
    return contract.RoomOut(id=zone_id, type=type_, name=type_, x=x, y=y,
                            width_m=w, depth_m=h, area_m2=area, gross_width_m=w,
                            gross_depth_m=h, gross_area_m2=round(w * h, 4), walls={})


def _merged_design_with_hall_and_bedroom():
    """A LIVING(5x5)+KITCHEN(4x1.5, partial-edge) merge — a genuine L (the bbox is strictly
    larger than the true union area, same shape family as
    `test_merged_room_passes_validation_and_renders_as_polygon`) whose KITCHEN arm ALONE would
    have read as a strip (gross aspect 4.0/1.5 = 2.67) had it stayed a standalone room — plus an
    unrelated HALL and BEDROOM so M2/M3/M6 have something else to measure against. Built via
    `room_merge.compute_geometry` + `contract._apply_room_merge` directly (not `plan_merge`'s own
    validation, already covered above) — this fixture is about what `quality_metrics`/
    `reference_benchmark` read off an ALREADY-APPLIED merge, matching a real
    `MergeOut.applied=True` plan."""
    living = _living()
    kitchen = _kitchen(rect_m=(5.0, 1.0, 4.0, 1.5), net_w_m=3.8, net_h_m=1.3)
    candidate = room_merge.MergeCandidate(living=living, kitchen=kitchen, side="E")
    geometry = room_merge.compute_geometry(candidate)
    merge = room_merge.MergeResult(living_id="LIVING_1", kitchen_id="KITCHEN_1",
                                   merged_id="LIVING_1+KITCHEN_1", side="E",
                                   geometry=geometry, checks=())
    rooms_out = [
        _contract_room("LIVING_1", "LIVING", living.net_area_m2, 0.0, 0.0, 5.0, 5.0),
        _contract_room("KITCHEN_1", "KITCHEN", kitchen.net_area_m2, 5.0, 1.0, 4.0, 1.5),
        _contract_room("HALL_1", "HALL", 4.5, 10.0, 0.0, 2.0, 2.25),
        _contract_room("BEDROOM_1", "BEDROOM", 15.0, 20.0, 0.0, 4.0, 4.0),
    ]
    new_rooms, new_walls, new_opens, new_doors = contract._apply_room_merge(
        merge, rooms_out, [], [], [])
    merged_room = next(r for r in new_rooms if r.id == merge.merged_id)
    design = SimpleNamespace(rooms=new_rooms, walls=new_walls, open_interfaces=new_opens,
                             doors=new_doors)
    return design, merged_room, kitchen, geometry


def test_m1_aspect_reads_the_merged_rooms_own_shape_not_a_strip_arm_penalty():
    """AC-1: M1's aspect for the merged room is the union's OWN bounding-box aspect — never
    either source arm's own standalone aspect, which for the KITCHEN arm alone would have read as
    a strip."""
    design, merged_room, kitchen, geometry = _merged_design_with_hall_and_bedroom()
    kitchen_standalone_aspect = kitchen.rect_m[2] / kitchen.rect_m[3]
    assert kitchen_standalone_aspect == pytest.approx(2.667, abs=0.01)

    aspects_by_type = dict(quality_metrics._habitable_aspects(design))
    assert "LIVING" not in aspects_by_type and "KITCHEN" not in aspects_by_type, (
        "the two source rooms must not appear standalone once merged")
    assert aspects_by_type["LIVING_KITCHEN"] == pytest.approx(geometry.min_rotated_aspect, abs=0.01)
    assert aspects_by_type["LIVING_KITCHEN"] < kitchen_standalone_aspect, (
        "the merged room's own aspect must not inherit the strip penalty either arm would have "
        "carried standalone")

    metrics = quality_metrics.measure_design(design)
    assert metrics.m1_habitable_aspect_max == pytest.approx(
        max(aspects_by_type["LIVING_KITCHEN"], 1.0), abs=0.01)  # BEDROOM_1 is 4x4, aspect 1.0


def test_m3_circulation_share_uses_the_merged_rooms_own_true_area_not_its_bounding_box():
    """AC-1: the merged room's own AREA — the true union polygon area (`gross_area_m2`) — feeds
    M3's plan-total denominator, never the bounding box's `width x depth` product, which
    overstates a real (non-flush) L's true footprint."""
    design, merged_room, kitchen, geometry = _merged_design_with_hall_and_bedroom()
    bbox_w, bbox_h = geometry.bbox_m[2], geometry.bbox_m[3]
    assert bbox_w * bbox_h > merged_room.gross_area_m2 + 0.01, (
        "fixture must be a genuine (non-flush) L for this test to be meaningful")

    metrics = quality_metrics.measure_design(design)
    hall_area, bedroom_area = 4.5, 16.0
    true_total = hall_area + bedroom_area + merged_room.gross_area_m2
    bbox_total = hall_area + bedroom_area + bbox_w * bbox_h
    assert metrics.m3_circulation_share == pytest.approx(hall_area / true_total, abs=1e-6)
    assert metrics.m3_circulation_share != pytest.approx(hall_area / bbox_total, abs=1e-6)


def test_public_zone_and_zoning_section_count_the_merged_room_as_one_contiguous_public_room():
    """AC-1: with the merge collapsing LIVING+KITCHEN into the plan's only public room (no
    DINING), both M6 (`quality_metrics`) and reference_benchmark's zoning section (C) must read
    this as ONE contiguous public room, not 'nothing to measure' (`_zone_contiguous`'s own
    escape hatch for fewer than two rooms in a zone)."""
    design, merged_room, kitchen, geometry = _merged_design_with_hall_and_bedroom()

    metrics = quality_metrics.measure_design(design)
    assert metrics.m6_public_zone_contiguous is True

    full_design = SimpleNamespace(
        rooms=design.rooms, walls=design.walls, open_interfaces=design.open_interfaces,
        doors=design.doors, windows=[], outline=None, quality=None,
        gross_area_m2=sum(r.gross_area_m2 for r in design.rooms),
        footprint=SimpleNamespace(width_m=14.0, depth_m=10.0))
    report = reference_benchmark.benchmark(full_design, [])
    c = report.section("C")
    assert c.value["public_contiguous"] is True


def test_a_check_the_whole_plan_already_failed_is_not_silently_inherited_as_a_pass(monkeypatch):
    monkeypatch.setattr(room_merge, "LIVING_KITCHEN_MERGE_ENABLED", True)
    design = _fake_design([_living(), _kitchen()])
    report = _passing_report("C8", "C9", "C19")  # C7 missing == the plan's own C7 failed
    result = room_merge.plan_merge(design, report)
    assert result is not None
    c7 = next(c for c in result.checks if c.check_id == "C7")
    assert not c7.passed
    assert result.passed is False
