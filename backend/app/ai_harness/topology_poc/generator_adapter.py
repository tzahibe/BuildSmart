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

MERGED LIVING_KITCHEN ROOMS (found during independent review of the results, 2026-10-01): when
`app.vertical_slice.room_merge` (`LIVING_KITCHEN_MERGE_ENABLED`) collapses a brief's LIVING and
KITCHEN into one open-plan polygon, `app.demo.contract._apply_room_merge` emits it as a single
`RoomOut` with `type="LIVING_KITCHEN"` — a real production room type, but NOT a `ProgramRole`
(`app.vertical_slice.geometry_core.model.ProgramRole` has no such member) and NOT one of
`priors.MEASURABLE_ROLES`. Passed through unchanged, that role never matches any #149 corpus row,
so every adjacency/access pair for that brief silently reads as "no evidence" (`None`) — not a
genuine absence of signal, but an artifact of this adapter's own representation choice; measured
across the 20 frozen briefs, this is 11/20, not a one-off (`generation-dataset.json`'s briefs
B01/B03/B04/B06/B07/B09/B10/B12/B14/B15/B17). `_expand_merged_rooms` below splits it back into two
role-tagged room refs, `{id}::LIVING` and `{id}::KITCHEN`, sharing the merged room's own geometry
(so any neighbour's adjacency check sees both) and always mutually touching/accessible (the two
roles share one undivided polygon, by construction — there is no wall between them to run
`shared_boundary_m` against). This never reaches `app.demo`/`app.vertical_slice` — the split exists
only in this adapter's own `TopologyProposal` construction.
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

#: `app.demo.contract._apply_room_merge`'s own room type for a collapsed LIVING+KITCHEN polygon —
#: see the module docstring's "MERGED LIVING_KITCHEN ROOMS" section.
_MERGED_LIVING_KITCHEN_ROLE = "LIVING_KITCHEN"


def _rect_of(room) -> Rect:
    return Rect(x=m_to_u(room.x), y=m_to_u(room.y),
               w=m_to_u(room.gross_width_m), h=m_to_u(room.gross_depth_m))


def _expand_merged_rooms(rooms_out) -> tuple:
    """Splits every `LIVING_KITCHEN` `RoomOut` into two role-tagged `(new_id, role, source_room)`
    entries sharing the merged room's own geometry; every other room passes through with its
    original id. Returns `(expanded, id_remap)` where `id_remap[old_id]` is the tuple of new id(s)
    standing in for `old_id` in `design.doors`/`design.open_interfaces` (one id for an unmerged
    room, two for a merged one)."""
    expanded = []
    id_remap: dict = {}
    for room in rooms_out:
        if room.type == _MERGED_LIVING_KITCHEN_ROLE:
            living_id, kitchen_id = f"{room.id}::LIVING", f"{room.id}::KITCHEN"
            expanded.append((living_id, "LIVING", room))
            expanded.append((kitchen_id, "KITCHEN", room))
            id_remap[room.id] = (living_id, kitchen_id)
        else:
            expanded.append((room.id, room.type, room))
            id_remap[room.id] = (room.id,)
    return tuple(expanded), id_remap


def topology_from_demo_design(design: DemoDesign) -> TopologyProposal:
    expanded, id_remap = _expand_merged_rooms(design.rooms)
    rooms = tuple(RoomRef(id=new_id, role=role) for new_id, role, _ in expanded)
    room_ids = frozenset(r.id for r in rooms)
    rects = {new_id: _rect_of(source) for new_id, _, source in expanded}
    #: which original room id each new id came from — used below to skip running
    #: `shared_boundary_m` on the two halves of the same merged polygon (identical geometry, no
    #: wall between them to measure) in favour of an explicit "always touching/accessible" edge.
    source_of = {new_id: source.id for new_id, _, source in expanded}
    merged_pairs = [ids for ids in id_remap.values() if len(ids) == 2]

    spatial_adjacency = set()
    room_id_list = list(room_ids)
    for i in range(len(room_id_list)):
        for j in range(i + 1, len(room_id_list)):
            a, b = room_id_list[i], room_id_list[j]
            if source_of[a] == source_of[b]:
                continue
            if shared_boundary_m(rects[a], rects[b]) >= MIN_MEANINGFUL_SHARED_BOUNDARY_M - 1e-9:
                spatial_adjacency.add(frozenset((a, b)))
    for living_id, kitchen_id in merged_pairs:
        spatial_adjacency.add(frozenset((living_id, kitchen_id)))

    access_graph = set()
    for door in design.doors:
        if door.is_entrance:
            for target in id_remap.get(door.b, ()):
                access_graph.add((ENTRANCE_ID, target))
            continue
        if door.a in id_remap and door.b in id_remap:
            for a2 in id_remap[door.a]:
                for b2 in id_remap[door.b]:
                    access_graph.add((a2, b2))
                    access_graph.add((b2, a2))
    for interface in design.open_interfaces:
        ids = [new_id for rid in interface.room_ids for new_id in id_remap.get(rid, ())]
        for i in range(len(ids)):
            for j in range(len(ids)):
                if i != j:
                    access_graph.add((ids[i], ids[j]))
    for living_id, kitchen_id in merged_pairs:
        access_graph.add((living_id, kitchen_id))
        access_graph.add((kitchen_id, living_id))

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
