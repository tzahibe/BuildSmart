"""Builds the 20-plan test fixture set: backend/tests/architectural_brain/fixtures/plans/*.json
plus expected_patterns.json (the hand-checked expectation file AC-2 verifies against).

    RESPLAN_PKL=/path/to/ResPlan.pkl uv run python3 spikes/architectural_brain/build_fixtures.py

19 plans are real ResPlan plans (by dataset list index, chosen by inspecting each one's derived pattern to get
coverage of every circulation class the corpus actually produces: FRONT_BAND, TWO_WING, BRANCHED,
HUB_LOBBY, OTHER). SPINE (a single residual component with long/short > 3 and >= 3 doors) does not
occur anywhere in the 17,107-plan ResPlan dataset under this measurable rule — every plan was
checked (see docs/reports/poc-architectural-brain/dataset.md) — so the 20th fixture is one
hand-built synthetic plan that exercises the SPINE rule directly; it is clearly marked
``source_dataset: "SYNTHETIC"`` in its provenance, never claimed as a real ResPlan plan.

This script is a one-off generator, not exercised by the test suite (which reads only the
committed JSON it produces) — matching how build_corpus.py builds the main corpus.
"""
from __future__ import annotations

import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from spikes.architectural_brain.patterns import derive_pattern
from spikes.architectural_brain.plan_reference import (
    AccessEdge,
    AdjacencyEdge,
    Derived,
    Door,
    Entrance,
    PlanReference,
    Provenance,
    Room,
    WallSegment,
)
from spikes.architectural_brain.resplan_ingest import normalise
from spikes.architectural_brain.build_corpus import DEFAULT_RESPLAN_PKL

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests", "architectural_brain", "fixtures", "plans",
)

REAL_PLAN_INDICES_BY_CLASS = {
    "HUB_LOBBY": [13587],
    "BRANCHED": [23, 1078, 1093, 1264],
    "TWO_WING": [3, 6, 26, 35],
    "FRONT_BAND": [1, 14, 15, 24, 44],
    "OTHER": [7, 11, 22, 28, 29],
}


def _synthetic_spine_plan() -> PlanReference:
    """Hand-built: a 6x3 m footprint, one long straight corridor (aspect 6.0) with three bedroom
    doors off it — exercises the SPINE rule (aspect > 3, >= 3 doors) directly and deterministically.
    """
    corridor = Room(
        id="CIRCULATION_0", type="CIRCULATION",
        polygon=((0.0, 0.0), (6.0, 0.0), (6.0, 1.0), (0.0, 1.0)),
        area_m2=6.0, width_m=6.0, depth_m=1.0,
        exterior_exposure=(), exposure_known=True,
    )
    bedrooms = [
        Room(id=f"BEDROOM_{i}", type="BEDROOM",
             polygon=((x, 1.0), (x + 2.0, 1.0), (x + 2.0, 3.0), (x, 3.0)),
             area_m2=4.0, width_m=2.0, depth_m=2.0,
             exterior_exposure=("N",), exposure_known=True)
        for i, x in enumerate((0.0, 2.0, 4.0))
    ]
    rooms = (corridor,) + tuple(bedrooms)
    doors = tuple(
        Door(id=f"DOOR_{i}", polygon=((x + 0.8, 0.9), (x + 1.2, 0.9), (x + 1.2, 1.1), (x + 0.8, 1.1)),
             room_ids=("CIRCULATION_0", f"BEDROOM_{i}"), is_exterior=False)
        for i, x in enumerate((0.0, 2.0, 4.0))
    )
    access_edges = tuple(
        AccessEdge(room_a="CIRCULATION_0", room_b=f"BEDROOM_{i}", kind="DOOR") for i in range(3)
    )
    adjacency_edges = tuple(
        AdjacencyEdge(room_a="CIRCULATION_0", room_b=f"BEDROOM_{i}") for i in range(3)
    )
    return PlanReference(
        plan_id="synthetic-spine-01",
        footprint=((0.0, 0.0), (6.0, 0.0), (6.0, 3.0), (0.0, 3.0)),
        rooms=rooms,
        walls=(WallSegment(id="WALL_0", polygon=((0.0, 0.0), (6.0, 0.0), (6.0, 0.1), (0.0, 0.1))),),
        doors=doors,
        windows=(),
        entrance=Entrance(room_id="CIRCULATION_0", side="W"),
        adjacency_edges=adjacency_edges,
        access_edges=access_edges,
        derived=Derived(
            scale_m_per_px=1.0, wall_thickness_m=0.2, footprint_area_m2=18.0,
            room_type_counts={"CIRCULATION": 1, "BEDROOM": 3},
        ),
        provenance=Provenance(
            source_dataset="SYNTHETIC", source_plan_id="synthetic-spine-01", unit_type="UNKNOWN",
            licence="N/A (synthetic fixture)",
            citation="Hand-built for architectural_brain test fixtures -- not derived from ResPlan.",
        ),
    )


def build_fixtures(pkl_path: str) -> dict:
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)
    by_index = {i: p for i, p in enumerate(data)}

    os.makedirs(FIXTURES_DIR, exist_ok=True)
    for name in os.listdir(FIXTURES_DIR):
        if name.endswith(".json"):
            os.remove(os.path.join(FIXTURES_DIR, name))

    expected: dict[str, str] = {}

    def _write(ref: PlanReference, pattern) -> None:
        out = {"plan_reference": ref.to_dict(), "architectural_pattern": pattern.to_dict()}
        path = os.path.join(FIXTURES_DIR, f"{ref.plan_id}.json")
        with open(path, "w") as f:
            json.dump(out, f, indent=2, sort_keys=True)
        expected[ref.plan_id] = pattern.circulation_class

    for expected_class, ids in REAL_PLAN_INDICES_BY_CLASS.items():
        for pid in ids:
            plan = by_index[pid]
            ref = normalise(plan)
            pattern = derive_pattern(ref)
            assert pattern.circulation_class == expected_class, (
                f"plan {pid} expected {expected_class}, measured {pattern.circulation_class}"
            )
            _write(ref, pattern)

    spine_ref = _synthetic_spine_plan()
    spine_pattern = derive_pattern(spine_ref)
    assert spine_pattern.circulation_class == "SPINE", spine_pattern.circulation_class
    _write(spine_ref, spine_pattern)

    with open(os.path.join(FIXTURES_DIR, "..", "expected_patterns.json"), "w") as f:
        json.dump(expected, f, indent=2, sort_keys=True)

    return expected


if __name__ == "__main__":
    pkl_path = os.environ.get("RESPLAN_PKL", DEFAULT_RESPLAN_PKL)
    result = build_fixtures(pkl_path)
    print(f"wrote {len(result)} fixtures")
    for plan_id, cls in sorted(result.items()):
        print(f"  {plan_id}: {cls}")
