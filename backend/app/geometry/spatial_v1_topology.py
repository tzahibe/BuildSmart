"""Minimal, unmodified port of the Spatial V1 prototype's AccessTopology/DoorTopology data model
(validated in the SPATIAL_V1_* experimental gates run outside this repository), brought in only as
far as the spatial-edit integration layer needs it. This is NOT the full Spatial V1 topology
generator (capacity estimation, candidate search, CP-SAT integration) -- none of that is needed to
apply or validate a single room move, and none of it is ported here. Logic below is copied
verbatim from the validated prototype, not redesigned.

`AccessEdge`/`AccessTopology` describe which room-instance pairs are REQUIRED to share a real wall
(a `REQUIRED_ACCESS` or `AUTHORITATIVE` edge). `derive_door_topology` verifies each edge still has a
real shared wall in a given room layout and emits one `DoorConnection` per edge -- the SAME
verify-don't-assume check used throughout Spatial V1's CP-SAT pipeline, reused here unchanged so a
spatial edit is checked by the identical rule a freshly-solved layout is checked by.
"""
from dataclasses import dataclass, field


@dataclass
class AccessEdge:
    a: str
    b: str
    kind: str


@dataclass
class AccessTopology:
    name: str
    edges: list[AccessEdge] = field(default_factory=list)
    node_types: dict[str, str] = field(default_factory=dict)


@dataclass
class SpatialV1DoorConnection:
    """Spatial V1's own lightweight door record (from_room/to_room/shared_wall_m/width_m/
    provenance) -- distinct from `app.geometry.geometric_design.DoorConnection`, which carries
    wall-segment geometry (wall_id/coord/center) that only the production `GeometricDesign`
    contract needs. `spatial_edit_adapter.py` converts between the two."""
    from_room: str
    to_room: str
    shared_wall_m: float
    width_m: float
    provenance: str


_MIN_REAL_WALL_M = 0.45  # unmodified Spatial V1 threshold -- see module docstring
_MAX_DOOR_WIDTH_M = 0.9  # unmodified Spatial V1 cap, matches app.geometry.solver._DOOR_OPENING_MIN_M


def _shared_edge_len(a: dict, b: dict) -> float:
    ox = max(0.0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    oy = max(0.0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    touching_x = abs(a["x"] + a["width"] - b["x"]) < 0.15 or abs(b["x"] + b["width"] - a["x"]) < 0.15
    touching_y = abs(a["y"] + a["height"] - b["y"]) < 0.15 or abs(b["y"] + b["height"] - a["y"]) < 0.15
    if touching_x and oy > 0:
        return oy
    if touching_y and ox > 0:
        return ox
    return 0.0


def derive_door_topology(rooms: list[dict], topology: AccessTopology) -> tuple[list[SpatialV1DoorConnection], list[str]]:
    """Returns (doors, mismatches). `rooms` uses Spatial V1's room-dict shape
    (id/type/x/y/width/height/area_m2). mismatches lists any AccessTopology edge whose geometry does
    NOT actually have a real shared wall in this room layout."""
    by_id = {r["id"]: r for r in rooms}
    doors: list[SpatialV1DoorConnection] = []
    mismatches: list[str] = []
    for edge in topology.edges:
        a, b = by_id.get(edge.a), by_id.get(edge.b)
        if a is None or b is None:
            mismatches.append(f"{edge.a}<->{edge.b}: room instance missing")
            continue
        length = _shared_edge_len(a, b)
        if length < _MIN_REAL_WALL_M:
            mismatches.append(f"{edge.a}<->{edge.b}: AccessTopology edge has no real shared wall (L={length:.2f}m)")
            continue
        doors.append(SpatialV1DoorConnection(edge.a, edge.b, round(length, 3), min(_MAX_DOOR_WIDTH_M, length), edge.kind))
    return doors, mismatches
