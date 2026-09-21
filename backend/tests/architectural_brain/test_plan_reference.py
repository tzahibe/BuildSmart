"""Verifies Issue #94's PlanReference / ArchitecturalPattern acceptance criteria against the
committed 20-plan fixture set (backend/tests/architectural_brain/fixtures/plans/*.json). These
tests never open ResPlan.pkl -- see spikes/architectural_brain/build_fixtures.py for how the
fixtures were produced.
"""
from __future__ import annotations

import json
import os

import pytest

from spikes.architectural_brain.patterns import derive_pattern
from spikes.architectural_brain.plan_reference import PlanReference

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PLANS_DIR = os.path.join(FIXTURES_DIR, "plans")


def _fixture_ids() -> list[str]:
    return sorted(name[:-5] for name in os.listdir(PLANS_DIR) if name.endswith(".json"))


def _load_fixture(plan_id: str) -> dict:
    with open(os.path.join(PLANS_DIR, f"{plan_id}.json")) as f:
        return json.load(f)


def test_fixture_plans_round_trip_with_metric_scale():
    fixture_ids = _fixture_ids()
    assert len(fixture_ids) == 20, f"expected 20 fixture plans, found {len(fixture_ids)}"

    for plan_id in fixture_ids:
        raw = _load_fixture(plan_id)
        ref = PlanReference.from_dict(raw["plan_reference"])

        # Round-trips through the JSON schema, exactly.
        assert PlanReference.from_json(ref.to_json()).to_dict() == ref.to_dict()

        wall_thickness = ref.derived.wall_thickness_m
        assert 0.08 <= wall_thickness <= 0.45, (
            f"{plan_id}: implied wall thickness {wall_thickness}m out of the 8-45cm band"
        )

        assert ref.rooms, f"{plan_id}: no rooms"
        for room in ref.rooms:
            assert len(room.polygon) >= 3
            for x, y in room.polygon:
                assert isinstance(x, float) and isinstance(y, float)
            assert room.area_m2 > 0

        for door in ref.doors:
            assert len(door.polygon) >= 3
            for rid in door.room_ids:
                assert ref.room(rid) is not None, f"{plan_id}: door {door.id} names unknown room {rid}"

        if ref.entrance.room_id is not None:
            assert ref.room(ref.entrance.room_id) is not None, (
                f"{plan_id}: entrance names unknown room {ref.entrance.room_id}"
            )


def test_derived_circulation_classes_match_the_hand_checked_expectations():
    with open(os.path.join(FIXTURES_DIR, "expected_patterns.json")) as f:
        expected = json.load(f)

    fixture_ids = _fixture_ids()
    assert set(fixture_ids) == set(expected.keys())

    measured_classes = set()
    for plan_id in fixture_ids:
        raw = _load_fixture(plan_id)
        ref = PlanReference.from_dict(raw["plan_reference"])

        pattern_first = derive_pattern(ref)
        pattern_second = derive_pattern(ref)
        assert pattern_first.to_dict() == pattern_second.to_dict(), (
            f"{plan_id}: derive_pattern is not deterministic"
        )

        assert pattern_first.circulation_class == expected[plan_id], (
            f"{plan_id}: expected {expected[plan_id]!r}, measured {pattern_first.circulation_class!r}"
        )
        measured_classes.add(pattern_first.circulation_class)

    assert "SPINE" in measured_classes
    assert "HUB_LOBBY" in measured_classes
    assert measured_classes & {"TWO_WING", "BRANCHED", "FRONT_BAND"}


def test_underivable_semantics_are_unknown_never_guessed():
    from spikes.architectural_brain.plan_reference import (
        AccessEdge,
        AdjacencyEdge,
        Derived,
        Entrance,
        Provenance,
        Room,
    )

    # A synthetic plan with no front_door and no window geometry at all -- the honest answer for
    # both entrance and exposure is UNKNOWN, never a guess (e.g. "probably the living room").
    living = Room(
        id="LIVING_0", type="LIVING",
        polygon=((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)),
        area_m2=16.0, width_m=4.0, depth_m=4.0,
        exterior_exposure=(), exposure_known=False,
    )
    bedroom = Room(
        id="BEDROOM_0", type="BEDROOM",
        polygon=((4.0, 0.0), (7.0, 0.0), (7.0, 4.0), (4.0, 4.0)),
        area_m2=12.0, width_m=3.0, depth_m=4.0,
        exterior_exposure=(), exposure_known=False,
    )
    ref = PlanReference(
        plan_id="synthetic-no-entrance-no-windows",
        footprint=((0.0, 0.0), (7.0, 0.0), (7.0, 4.0), (0.0, 4.0)),
        rooms=(living, bedroom),
        walls=(),
        doors=(),
        windows=(),
        entrance=Entrance(room_id=None, side="UNKNOWN"),
        adjacency_edges=(AdjacencyEdge(room_a="LIVING_0", room_b="BEDROOM_0"),),
        access_edges=(AccessEdge(room_a="LIVING_0", room_b="BEDROOM_0", kind="DOOR"),),
        derived=Derived(scale_m_per_px=1.0, wall_thickness_m=0.2, footprint_area_m2=28.0,
                         room_type_counts={"LIVING": 1, "BEDROOM": 1}),
        provenance=Provenance(source_dataset="SYNTHETIC", source_plan_id="synthetic-no-entrance-no-windows",
                               unit_type="UNKNOWN", licence="N/A (synthetic fixture)",
                               citation="Hand-built for the UNKNOWN-never-guessed test."),
    )

    assert ref.entrance.room_id is None
    assert ref.entrance.side == "UNKNOWN"
    for room in ref.rooms:
        assert room.exposure_known is False
        assert room.exterior_exposure == ()

    pattern = derive_pattern(ref)
    assert pattern.entrance_relationship == "UNKNOWN"
    assert pattern.exposure_pattern is None
    assert pattern.topology_depth is None

    # Round-trips cleanly too -- UNKNOWN is a first-class, serialisable value, not an exception path.
    assert PlanReference.from_json(ref.to_json()).to_dict() == ref.to_dict()
