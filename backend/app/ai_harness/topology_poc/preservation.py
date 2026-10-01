"""Preservation measurement (Issue #160, AC-6, AC-9).

"A valid house that destroys the requested topology is a FAIL, not a pass" (the Issue's own
words) — `measure_preservation` compares the REALIZED geometry against the REQUESTED
`TopologyProposal`, room id for room id (the bridge never renames a room, so a realized zone's own
id IS a requested room id), across the six dimensions the Issue names. `verdict` turns that into
PASS/FAIL — a plan the realizer and validator both accepted can still be `FAIL` here, by design
(AC-9): "realized" and "preserved" are different questions, and this module answers the second one
only.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.vertical_slice import access_rules
from app.vertical_slice.doors import resolve_entrance

from .schema import ENTRANCE_ID, TopologyProposal


@dataclass(frozen=True)
class DimensionResult:
    name: str
    preserved: int
    requested: int
    lost: tuple  # names of every lost requested relationship, by name (Issue's own requirement)

    @property
    def pct(self) -> float:
        return 100.0 if self.requested == 0 else 100.0 * self.preserved / self.requested

    @property
    def fully_preserved(self) -> bool:
        return self.requested == 0 or self.preserved == self.requested


@dataclass(frozen=True)
class PreservationReport:
    room_identity: DimensionResult
    spatial_adjacency: DimensionResult
    access_graph: DimensionResult
    zoning: DimensionResult
    wet_core: DimensionResult
    entrance_relation: DimensionResult

    @property
    def dimensions(self) -> tuple:
        return (self.room_identity, self.spatial_adjacency, self.access_graph, self.zoning,
                self.wet_core, self.entrance_relation)

    @property
    def all_preserved(self) -> bool:
        return all(d.fully_preserved for d in self.dimensions)


def verdict(report: PreservationReport) -> str:
    """PASS only when every dimension with at least one requested relationship kept all of
    them — never merely "the realizer/validator accepted this plan" (AC-9)."""
    return "PASS" if report.all_preserved else "FAIL"


_ZONE_KEY_ROLE_SETS = {
    "public": access_rules.PUBLIC_ROLES,
    "private": access_rules.PRIVATE_ROLES,
    "service": access_rules.WET_ROLES | access_rules.SERVICE_ROLES,
    "circulation": access_rules.CIRCULATION_ROLES,
}


def _touching_pairs(rects: dict) -> set:
    ids = list(rects.keys())
    pairs = set()
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if rects[ids[i]].shared_edge_len_u(rects[ids[j]]) > 0:
                pairs.add(frozenset((ids[i], ids[j])))
    return pairs


def measure_preservation(proposal: TopologyProposal, realized) -> PreservationReport:
    """`realized` is a `rectilinear_realizer.RealizedLayout` — never called on a `Refusal` (a
    refused case has nothing to measure; see the report's own per-case REFUSED handling)."""
    zone_of = dict(realized.zone_of_cell)
    room_ids = proposal.room_ids
    realized_room_ids = frozenset(zone_of.values()) | frozenset(realized.rects.keys())

    # 1. room identity
    missing = tuple(sorted(room_ids - realized_room_ids))
    room_identity = DimensionResult("room_identity", len(room_ids) - len(missing), len(room_ids),
                                     missing)

    # 2. spatial adjacency — physical touching, collapsed from cell id to owning zone id.
    touching_cells = _touching_pairs(realized.rects)
    touching_zones = {frozenset((zone_of.get(a, a), zone_of.get(b, b))) for pair in touching_cells
                       for a, b in (tuple(pair),)}
    lost_adj, kept_adj = [], 0
    for pair in proposal.spatial_adjacency:
        a, b = tuple(pair)
        if frozenset((a, b)) in touching_zones:
            kept_adj += 1
        else:
            lost_adj.append(f"{a}-{b}")
    spatial_adjacency = DimensionResult("spatial_adjacency", kept_adj,
                                         len(proposal.spatial_adjacency), tuple(lost_adj))

    # 3. access graph — real doors only (every realized access edge IS a door; see
    # `rectilinear_realizer.realize_layout`'s own `ConnectionKind.DOOR` construction).
    realized_access_pairs = {frozenset((zone_of.get(e.a, e.a), zone_of.get(e.b, e.b)))
                              for e in realized.fixture.access.edges}
    room_access_edges = [(a, b) for a, b in proposal.access_graph if a != ENTRANCE_ID]
    lost_access, kept_access = [], 0
    for a, b in room_access_edges:
        if frozenset((a, b)) in realized_access_pairs:
            kept_access += 1
        else:
            lost_access.append(f"{a}->{b}")
    access_graph = DimensionResult("access_graph", kept_access, len(room_access_edges),
                                    tuple(lost_access))

    # 4. public/private zoning — the realized room's OWN role (the bridge never changes a role)
    # must belong to the production role-set the proposal's own zone key names; only a room that
    # also actually realized counts as preserved.
    lost_zoning, kept_zoning, total_zoning = [], 0, 0
    role_by_id = proposal.role_by_id
    for zone_key, ids in proposal.zones.items():
        allowed_roles = _ZONE_KEY_ROLE_SETS.get(zone_key, frozenset())
        for rid in ids:
            total_zoning += 1
            role = access_rules.ProgramRole(role_by_id[rid]) if role_by_id.get(rid) else None
            if rid in realized_room_ids and role in allowed_roles:
                kept_zoning += 1
            else:
                lost_zoning.append(f"{rid}:{zone_key}")
    zoning = DimensionResult("zoning", kept_zoning, total_zoning, tuple(lost_zoning))

    # 5. wet-core intent — every pair within the declared wet_core cluster must end up physically
    # touching (a real, if coarse, proxy for "the wet rooms share one cluster" the way
    # `app.vertical_slice.wet_core` itself groups by adjacency).
    wet_cluster = proposal.clusters.get("wet_core", ())
    lost_wet, kept_wet, total_wet = [], 0, 0
    for i in range(len(wet_cluster)):
        for j in range(i + 1, len(wet_cluster)):
            a, b = wet_cluster[i], wet_cluster[j]
            total_wet += 1
            if frozenset((a, b)) in touching_zones:
                kept_wet += 1
            else:
                lost_wet.append(f"{a}-{b}")
    wet_core = DimensionResult("wet_core", kept_wet, total_wet, tuple(lost_wet))

    # 6. entrance relation — the realized arrival zone must be the proposal's own
    # `entrance_relation.opens_into`, re-derived from the SAME unchanged `doors.resolve_entrance`
    # `realize_layout` itself already called (a real fact, re-read, never guessed).
    entrance_total, entrance_kept, entrance_lost = 0, 0, []
    if proposal.entrance_relation is not None:
        entrance_total = 1
        resolved = resolve_entrance(realized.fixture, realized.rects, realized.site.footprint,
                                     realized.site.wings)
        realized_entrance_zone = zone_of.get(resolved[0], resolved[0]) if resolved else None
        if realized_entrance_zone == proposal.entrance_relation.opens_into:
            entrance_kept = 1
        else:
            entrance_lost.append(
                f"opens_into:{proposal.entrance_relation.opens_into} "
                f"(realized: {realized_entrance_zone})")
    entrance_relation = DimensionResult("entrance_relation", entrance_kept, entrance_total,
                                         tuple(entrance_lost))

    return PreservationReport(room_identity, spatial_adjacency, access_graph, zoning, wet_core,
                               entrance_relation)
