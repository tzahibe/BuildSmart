"""Extracts "the current generator's best topology" for a brief (Issue #151, requirement 5).

Runs the REAL, unmodified pipeline (`app.demo.service.generate_demo_design` — the exact function
`tests/regression_corpus/freeze_corpus.py` uses to freeze the 432-context corpus) and derives a
`schema.TopologyProposal` from its SOLVED output — never a re-implementation of the generator, and
never touching production code (requirement 10, out-of-scope: "no product path changes").

SPATIAL ADJACENCY is computed the identical way `app.vertical_slice.adjacency_priors._rects_adjacent`
does at ranking time (`shared_boundary_m(...) >= MIN_MEANINGFUL_SHARED_BOUNDARY_M`), on each room's
GROSS rectangle (`RoomOut.x`/`.y`/`.gross_width_m`/`.gross_depth_m` — the centerline allocation walls
actually run along) — this is "our own `y`" the corrected #149 report's own module docstring names
as the thing `spatial_touching` is comparable to.

ACCESS is read from `DemoDesign.doors` AND `DemoDesign.open_interfaces`: every interior `DoorOut`
becomes a pair of directed edges (a door has no inherent direction); the one `is_entrance=True` door
becomes a single `ENTRANCE -> room` edge (its own `.a` is the sentinel `"OUTSIDE"`, not a room —
discarded, never promoted into a fabricated room id). An open-plan boundary
(`OpenInterface.room_ids` — two spaces joined with NO wall, e.g. an opened hall<->LDK corridor, see
`app.demo.contract._open_corridor_to_public`) is at least as much "access" as a door — a free
opening, not a barrier — so it becomes a directed edge pair too. Without this, an open-plan brief's
public rooms would wrongly read as unreachable from the entrance (measured while building this
adapter: LIVING/KITCHEN/DINING joined to HALL by an opened interface, not a door).

ZONES are assigned from each room's role via `_ZONE_FOR_ROLE`, mirroring `concept_generator.
build_room_program`'s own `ZoneGroup` assignment (PUBLIC: LIVING/DINING/KITCHEN/FAMILY_ROOM;
CIRCULATION: HALL/CIRCULATION/STAIRWELL; PRIVATE: MASTER_BEDROOM/BEDROOM/SAFE_ROOM/STUDY/
DRESSING_ROOM; SERVICE: BATHROOM/TOILET/LAUNDRY/STORAGE/FLEX) — read off that module's own source,
not re-guessed.

CLUSTERS["wet_core"] reads `DemoDesign.quality.metrics.wet_core.clusters` (Issue #44's own measured
wet-room clustering) when present; falls back to "every wet room, ungrouped" (a single flat list)
only when that field is absent (a payload predating Issue #44) — documented, never silently
treated as "no wet rooms".
"""
from __future__ import annotations

from app.ai_harness.topology_poc.schema import ENTRANCE_ID, RoomRef, TopologyProposal
from app.demo.contract import DemoDesign
from app.demo.service import generate_demo_design
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.relationships import MIN_MEANINGFUL_SHARED_BOUNDARY_M, shared_boundary_m
from spikes.failure_log_sweep.sweep import project_from_context

_ZONE_FOR_ROLE = {
    "LIVING": "public", "DINING": "public", "KITCHEN": "public", "FAMILY_ROOM": "public",
    "HALL": "circulation", "CIRCULATION": "circulation", "STAIRWELL": "circulation",
    "MASTER_BEDROOM": "private", "BEDROOM": "private", "SAFE_ROOM": "private",
    "STUDY": "private", "DRESSING_ROOM": "private",
    "BATHROOM": "service", "TOILET": "service", "LAUNDRY": "service", "STORAGE": "service",
    "FLEX": "service",  # genuine unassigned area — no better-fitting zone exists (see model.py)
}

_WET_ROLES = frozenset({"BATHROOM", "TOILET"})


def _rect_of(room) -> Rect:
    return Rect(x=m_to_u(room.x), y=m_to_u(room.y),
               w=m_to_u(room.gross_width_m), h=m_to_u(room.gross_depth_m))


def topology_from_demo_design(design: DemoDesign) -> TopologyProposal:
    rooms = tuple(RoomRef(id=r.id, role=r.type) for r in design.rooms)
    room_ids = frozenset(r.id for r in rooms)
    rects = {r.id: _rect_of(r) for r in design.rooms}

    spatial_adjacency = set()
    room_id_list = list(room_ids)
    for i in range(len(room_id_list)):
        for j in range(i + 1, len(room_id_list)):
            a, b = room_id_list[i], room_id_list[j]
            if shared_boundary_m(rects[a], rects[b]) >= MIN_MEANINGFUL_SHARED_BOUNDARY_M - 1e-9:
                spatial_adjacency.add(frozenset((a, b)))

    access_graph = set()
    for door in design.doors:
        if door.is_entrance:
            if door.b in room_ids:
                access_graph.add((ENTRANCE_ID, door.b))
            continue
        if door.a in room_ids and door.b in room_ids:
            access_graph.add((door.a, door.b))
            access_graph.add((door.b, door.a))
    for interface in design.open_interfaces:
        ids = [rid for rid in interface.room_ids if rid in room_ids]
        for i in range(len(ids)):
            for j in range(len(ids)):
                if i != j:
                    access_graph.add((ids[i], ids[j]))

    zones: dict = {}
    for room in rooms:
        zone_key = _ZONE_FOR_ROLE.get(room.role, "service")
        zones.setdefault(zone_key, []).append(room.id)
    zones = {k: tuple(v) for k, v in zones.items()}

    wet_ids = [r.id for r in rooms if r.role in _WET_ROLES]
    wet_core_cluster = tuple(wet_ids)
    quality = getattr(design, "quality", None)
    metrics = getattr(quality, "metrics", None) if quality is not None else None
    wet_core_out = getattr(metrics, "wet_core", None) if metrics is not None else None
    if wet_core_out is not None and wet_core_out.clusters:
        flat = [rid for cluster in wet_core_out.clusters for rid in cluster if rid in room_ids]
        if flat:
            wet_core_cluster = tuple(flat)
    clusters = {"wet_core": wet_core_cluster} if wet_ids else {}

    return TopologyProposal(
        rooms=rooms, spatial_adjacency=frozenset(spatial_adjacency),
        access_graph=frozenset(access_graph), zones=zones, clusters=clusters,
        relative_position=(), entrance_relation=None,
        design_tradeoff="Current generator's chosen topology for this brief.")


def extract_topology_from_generator(context: dict) -> TopologyProposal:
    """Runs the real pipeline for `context` (the exact 10-field dict the frozen corpus's own
    `source_key` is built from) and returns its topology. Raises whatever
    `app.demo.service.DemoGenerationError` the pipeline itself raises for a context that refuses —
    callers select only PLANNED briefs (`briefs.py`), so this is never expected to happen for a
    committed brief, but is never silently swallowed here either."""
    project = project_from_context(context)
    result = generate_demo_design(project)
    return topology_from_demo_design(result.design)
