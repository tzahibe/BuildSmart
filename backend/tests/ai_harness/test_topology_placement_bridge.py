"""Issue #160 — the topology->placement bridge spike.

AC-3: the bridge converts a frozen topology object into a `RealizationIntent` without modifying
the proposal. AC-4: the bridge REFUSES — never falls back to a row — when the requested graph
needs more spatial-adjacency relationships than a single row (or a 5-room pinwheel) can hold.
AC-9: a plan that validates but loses requested relationships is a preservation FAIL, not a pass —
proven directly against `preservation.measure_preservation`, independent of how such a geometry
came to exist (the #134 donor-collapse failure mode this Issue exists to catch).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai_harness.topology_poc import placement_bridge, preservation, schema
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Rect,
)
from app.vertical_slice.rectilinear_realizer import RealizationIntent

_FIVE_ROOM_RAW = {
    "rooms": [
        {"id": "LIVING", "role": "LIVING"},
        {"id": "KITCHEN", "role": "KITCHEN"},
        {"id": "HALL", "role": "HALL"},
        {"id": "MASTER", "role": "MASTER_BEDROOM"},
        {"id": "BATHROOM_1", "role": "BATHROOM"},
    ],
    "spatial_adjacency": [
        ["BATHROOM_1", "MASTER"], ["HALL", "KITCHEN"], ["HALL", "LIVING"],
        ["HALL", "MASTER"], ["KITCHEN", "LIVING"], ["LIVING", "MASTER"],
    ],
    "access_graph": [
        ["ENTRANCE", "LIVING"], ["HALL", "KITCHEN"], ["HALL", "MASTER"],
        ["LIVING", "HALL"], ["MASTER", "BATHROOM_1"],
    ],
    "zones": {"public": ["LIVING", "KITCHEN"], "private": ["MASTER"],
              "service": ["BATHROOM_1"], "circulation": ["HALL"]},
    "clusters": {"wet_core": ["BATHROOM_1"]},
    "relative_position": [],
    "entrance_relation": {"opens_into": "LIVING", "sequence": ["ENTRANCE", "LIVING", "HALL", "MASTER"]},
    "design_tradeoff": "B01's own real rank-1 policy-valid proposal (fixture copy)",
}


def _dense_raw(n: int, edges_per_room: int) -> dict:
    """A synthetic proposal with `n` rooms and a spatial_adjacency graph deliberately denser than
    n-1 — every room near-fully connected, never realizable by a single row."""
    ids = [f"R{i}" for i in range(n)]
    rooms = [{"id": rid, "role": "BEDROOM"} for rid in ids]
    pairs = []
    for i in range(n):
        for j in range(i + 1, min(i + 1 + edges_per_room, n)):
            pairs.append([ids[i], ids[j]])
    return {
        "rooms": rooms, "spatial_adjacency": pairs, "access_graph": [],
        "zones": {"private": ids}, "clusters": {}, "relative_position": [],
        "entrance_relation": None, "design_tradeoff": "synthetic AC-4 fixture",
    }


# --------------------------------------------------------------------------- AC-3

def test_bridge_does_not_mutate_proposal():
    proposal = schema.proposal_from_dict(_FIVE_ROOM_RAW)
    rooms_before = proposal.rooms
    spatial_before = proposal.spatial_adjacency
    access_before = proposal.access_graph
    zones_before = dict(proposal.zones)
    clusters_before = dict(proposal.clusters)
    entrance_before = proposal.entrance_relation

    result = placement_bridge.build_realization_intent(proposal, "B01")

    assert isinstance(result, RealizationIntent)
    assert proposal.rooms == rooms_before
    assert proposal.spatial_adjacency == spatial_before
    assert proposal.access_graph == access_before
    assert proposal.zones == zones_before
    assert proposal.clusters == clusters_before
    assert proposal.entrance_relation == entrance_before
    # frozen dataclass identity: the SAME object, never replaced or copied-and-edited
    assert proposal is proposal


def test_bridge_builds_realization_intent_from_five_room_proposal():
    """A sanity companion to AC-3: the 5-room case goes through the PinwheelWing path and the
    `RealizationIntent` it returns is a real, usable input to the UNCHANGED realizer's own type."""
    proposal = schema.proposal_from_dict(_FIVE_ROOM_RAW)
    result = placement_bridge.build_realization_intent(proposal, "B01")
    assert isinstance(result, RealizationIntent)
    assert len(result.wings) == 1


# --------------------------------------------------------------------------- AC-4

def test_bridge_refuses_when_graph_exceeds_row_capacity():
    """8 rooms, every room adjacent to its next 3 neighbours — far denser than the row's own n-1
    capacity (7), and n != 5 so PinwheelWing is not available either. No row is ever emitted."""
    proposal = schema.proposal_from_dict(_dense_raw(8, edges_per_room=3))
    n = len(proposal.rooms)
    edges = len(proposal.spatial_adjacency)
    assert edges > n - 1  # the precondition AC-4 names

    result = placement_bridge.build_realization_intent(proposal, "dense")

    assert isinstance(result, placement_bridge.BridgeRefusal)
    assert result.reason == "ROW_CAPACITY_EXCEEDED"
    assert str(n) in result.detail
    assert str(edges) in result.detail
    assert placement_bridge.classify_failure(result) == "BRIDGE"


def test_bridge_accepts_a_graph_within_row_capacity():
    """The mirror case: a graph with exactly n-1 edges (a simple path) DOES get a `RealizationIntent`
    — the refusal is specifically about exceeding capacity, not about avoiding rows altogether."""
    proposal = schema.proposal_from_dict(_dense_raw(8, edges_per_room=1))  # a path: 7 edges, n-1=7
    result = placement_bridge.build_realization_intent(proposal, "sparse")
    assert isinstance(result, RealizationIntent)


def test_row_capacity_is_n_minus_1_regardless_of_edge_count_requested():
    """A graph needing exactly n-1 at n=6 (5 edges) is accepted; one more edge (6) at the same n is
    refused — the boundary AC-4 names is exact, not approximate."""
    ok = schema.proposal_from_dict(_dense_raw(6, edges_per_room=1))
    assert len(ok.spatial_adjacency) == 5
    assert isinstance(placement_bridge.build_realization_intent(ok, "n6ok"), RealizationIntent)

    raw = _dense_raw(6, edges_per_room=1)
    raw["spatial_adjacency"].append(["R0", "R2"])  # one extra edge -> 6 > n-1(5)
    too_dense = schema.proposal_from_dict(raw)
    assert len(too_dense.spatial_adjacency) == 6
    refusal = placement_bridge.build_realization_intent(too_dense, "n6bad")
    assert isinstance(refusal, placement_bridge.BridgeRefusal)
    assert refusal.reason == "ROW_CAPACITY_EXCEEDED"


# --------------------------------------------------------------------------- AC-9

@dataclass
class _FakeAccess:
    edges: tuple


@dataclass
class _FakeFixture:
    access: _FakeAccess


@dataclass
class _FakeRealizedLayout:
    """The minimal subset of `rectilinear_realizer.RealizedLayout` that `preservation.
    measure_preservation` actually reads — standing in for a REAL realized layout here so the test
    can hand-construct the exact "collapsed to a row" geometry the #134 donor failure produced,
    without needing a full `realize_layout` run to reach it."""

    rects: dict
    zone_of_cell: dict
    fixture: _FakeFixture


def _row_collapsed_fake_layout(ids: list) -> _FakeRealizedLayout:
    """`ids`, placed left to right, each 2x2 grid units, touching ONLY its immediate neighbour —
    exactly what a single `RowWing` (or a donor's 2D arrangement collapsed into one) produces: a
    straight chain, never the 2D graph a wheel/pinwheel topology actually requested."""
    rects = {rid: Rect(i * 2, 0, 2, 2) for i, rid in enumerate(ids)}
    zone_of_cell = {rid: rid for rid in ids}
    edges = tuple(DesiredAccessEdge(ids[i], ids[i + 1], ConnectionKind.DOOR)
                  for i in range(len(ids) - 1))
    return _FakeRealizedLayout(rects, zone_of_cell, _FakeFixture(_FakeAccess(edges)))


def test_row_collapsed_realization_of_a_2d_graph_is_a_preservation_failure():
    """A requested WHEEL graph on 5 rooms (A=hub, B/C/D/E on the rim, in a cycle) — genuinely 2D:
    A touches all 4, and the rim forms its own cycle. A row can physically realize at most a
    4-edge PATH among these 5 rooms; this fixture hands `measure_preservation` exactly that
    collapsed path (B-A-C-D-E) as the "realized" geometry and proves it is reported as a FAIL,
    not a PASS, with every lost relationship named — never silently accepted because the chosen
    4 edges all happen to be real."""
    raw = {
        "rooms": [{"id": rid, "role": role} for rid, role in
                  (("A", "HALL"), ("B", "LIVING"), ("C", "KITCHEN"), ("D", "BEDROOM"),
                   ("E", "BEDROOM"))],
        "spatial_adjacency": [
            ["A", "B"], ["A", "C"], ["A", "D"], ["A", "E"],  # spokes
            ["B", "C"], ["C", "D"], ["D", "E"], ["E", "B"],  # rim cycle
        ],
        "access_graph": [],
        "zones": {"circulation": ["A"], "public": ["B", "C"], "private": ["D", "E"]},
        "clusters": {},
        "relative_position": [],
        "entrance_relation": None,
        "design_tradeoff": "AC-9 fixture: a genuinely 2D wheel graph",
    }
    proposal = schema.proposal_from_dict(raw)
    assert len(proposal.spatial_adjacency) == 8  # more than any row of 5 could ever hold (n-1=4)

    collapsed = _row_collapsed_fake_layout(["B", "A", "C", "D", "E"])
    report = preservation.measure_preservation(proposal, collapsed)

    # exactly the 4 path edges survive; the other 4 requested relationships are lost
    assert report.spatial_adjacency.requested == 8
    assert report.spatial_adjacency.preserved == 4
    lost_pairs = {frozenset(name.split("-")) for name in report.spatial_adjacency.lost}
    assert lost_pairs == {frozenset(("A", "D")), frozenset(("A", "E")),
                           frozenset(("B", "C")), frozenset(("E", "B"))}

    # the headline claim AC-9 makes: realized-and-incomplete is a FAIL, never a PASS.
    assert report.all_preserved is False
    assert preservation.verdict(report) == "FAIL"


def test_fully_preserved_realization_is_a_pass():
    """The companion case: when the realized geometry DOES keep every requested relationship, the
    verdict is PASS — `verdict` is not a function that always says FAIL, only when something is
    genuinely missing."""
    raw = {
        "rooms": [{"id": rid, "role": "BEDROOM"} for rid in ("A", "B", "C")],
        "spatial_adjacency": [["A", "B"], ["B", "C"]],
        "access_graph": [],
        "zones": {"private": ["A", "B", "C"]},
        "clusters": {},
        "relative_position": [],
        "entrance_relation": None,
        "design_tradeoff": "AC-9 companion: a path graph a row CAN realize in full",
    }
    proposal = schema.proposal_from_dict(raw)
    full = _row_collapsed_fake_layout(["A", "B", "C"])
    report = preservation.measure_preservation(proposal, full)
    assert report.spatial_adjacency.preserved == report.spatial_adjacency.requested == 2
    assert report.all_preserved is True
    assert preservation.verdict(report) == "PASS"
