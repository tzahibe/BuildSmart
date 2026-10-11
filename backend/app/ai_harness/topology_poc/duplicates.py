"""Duplicate detection and materially-distinct counting (Issue #151, AC-4).

`canonical_hash` hashes the canonical form over room IDS, their ROLES, AND edge types (spatial
adjacency vs access are two distinct edge families) — so BEDROOM_1-BATHROOM_1 and BEDROOM_2-
BATHROOM_1 hash differently even when both are "a bedroom next to a bathroom" at the role level,
because the two proposals reference different room ids (proven by
`tests/ai_harness/test_topology_duplicates.py`).

"Materially different" is measured by INSTANCE-level graph-edit distance (`graph_edit_distance`) —
never role-level normalization first, which would erase exactly the BEDROOM_1-vs-BEDROOM_2
distinction AC-4 requires kept. Role-level normalization is available separately
(`role_level_signature`) for STATISTICS only, never for the distinctness count itself.
"""
from __future__ import annotations

import hashlib
import json

from app.ai_harness.topology_poc.schema import TopologyProposal

#: Two proposals are counted as "the same graph" for the materially-distinct count when their
#: instance-level graph-edit distance is below this floor — a single cosmetic edge/zone tweak (e.g.
#: moving one FLEX-adjacent boundary) should not count as a second distinct idea.
MATERIAL_DISTINCTNESS_THRESHOLD = 2


def _canonical_rooms(proposal: TopologyProposal) -> tuple:
    return tuple(sorted((r.id, r.role) for r in proposal.rooms))


def _canonical_adjacency(proposal: TopologyProposal) -> tuple:
    return tuple(sorted(tuple(sorted(pair)) for pair in proposal.spatial_adjacency))


def _canonical_access(proposal: TopologyProposal) -> tuple:
    return tuple(sorted(proposal.access_graph))


def _canonical_zones(proposal: TopologyProposal) -> tuple:
    return tuple(sorted((k, tuple(sorted(v))) for k, v in proposal.zones.items()))


def _canonical_clusters(proposal: TopologyProposal) -> tuple:
    return tuple(sorted((k, tuple(sorted(v))) for k, v in proposal.clusters.items()))


def canonical_form(proposal: TopologyProposal) -> dict:
    """The exact structure `canonical_hash` hashes — room ids+roles, adjacency edges (one edge
    type) and access edges (a second, distinct edge type), plus zones/clusters. Never role-only."""
    return {
        "rooms": _canonical_rooms(proposal),
        "spatial_adjacency": _canonical_adjacency(proposal),
        "access_graph": _canonical_access(proposal),
        "zones": _canonical_zones(proposal),
        "clusters": _canonical_clusters(proposal),
    }


def canonical_hash(proposal: TopologyProposal) -> str:
    canonical = canonical_form(proposal)
    blob = json.dumps(canonical, sort_keys=True, default=list)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def role_level_signature(proposal: TopologyProposal) -> tuple:
    """Role-pair normalized form — STATISTICS ONLY (module docstring). Never used to decide
    duplicate/distinct status."""
    role_by_id = proposal.role_by_id
    adjacency_roles = tuple(sorted(
        tuple(sorted((role_by_id[a], role_by_id[b]))) for a, b in (tuple(pair) for pair in proposal.spatial_adjacency)))
    access_roles = tuple(sorted(
        (role_by_id.get(a, a), role_by_id.get(b, b)) for a, b in proposal.access_graph))
    return (adjacency_roles, access_roles)


def graph_edit_distance(a: TopologyProposal, b: TopologyProposal) -> int:
    """Instance-level edit distance: the count of edges (adjacency + access) and zone/cluster
    memberships that differ between two proposals over the SAME brief's room-id vocabulary. Two
    proposals for different briefs (different room ids) are never compared."""
    adjacency_a, adjacency_b = set(_canonical_adjacency(a)), set(_canonical_adjacency(b))
    access_a, access_b = set(_canonical_access(a)), set(_canonical_access(b))
    zones_a, zones_b = set(_canonical_zones(a)), set(_canonical_zones(b))
    clusters_a, clusters_b = set(_canonical_clusters(a)), set(_canonical_clusters(b))

    distance = 0
    distance += len(adjacency_a ^ adjacency_b)
    distance += len(access_a ^ access_b)
    distance += len(zones_a ^ zones_b)
    distance += len(clusters_a ^ clusters_b)
    return distance


def count_materially_distinct(proposals: tuple) -> int:
    """Greedy clustering by `graph_edit_distance`: a proposal joins the first existing
    representative within `MATERIAL_DISTINCTNESS_THRESHOLD`, else starts a new one. Deterministic
    given `proposals`' own order."""
    representatives: list = []
    for proposal in proposals:
        if all(graph_edit_distance(proposal, rep) >= MATERIAL_DISTINCTNESS_THRESHOLD for rep in representatives):
            representatives.append(proposal)
    return len(representatives)


def deduplicate_exact(proposals: tuple) -> tuple:
    """Drops exact duplicates by `canonical_hash`, keeping the first occurrence — order-preserving."""
    seen = set()
    kept = []
    for proposal in proposals:
        h = canonical_hash(proposal)
        if h in seen:
            continue
        seen.add(h)
        kept.append(proposal)
    return tuple(kept)
