"""Realizability classification — METADATA ONLY (Issue #151, AC-6, AC-9, owner correction).

This module is never imported by `critic.py`, and nothing it produces feeds the quality score in
any form — no bonus, no penalty, no tie-break (proven by
`tests/ai_harness/test_topology_critic.py::test_score_is_independent_of_realizability_label`, which
scores the identical `TopologyProposal` and asserts a bit-identical `ScoreBreakdown` regardless of
what label this module would assign).

HEURISTIC, DOCUMENTED AS SUCH: today's engine (`app.vertical_slice.concept_generator`) builds
exactly one circulation spine (a single `HALL`) that every private room hangs off, one wet-core
cluster, and an entrance that opens into a public room. A proposal matching that shape is labelled
`REALIZABLE_BY_CURRENT_ENGINE`; a proposal whose access graph needs more than one circulation node,
or whose wet rooms are not co-clustered, is labelled `NOT_REALIZABLE_BY_CURRENT_ENGINE`; anything
this heuristic cannot classify with confidence — e.g. zero rooms typed `CIRCULATION`/`HALL` at all —
is `UNKNOWN`. This is a coarse proxy, not a re-run of the real solver: it exists only to LABEL a
proposal, never to filter, edit, or rank it (requirement 6 — proposals are never edited to suit the
realizer either).
"""
from __future__ import annotations

from app.ai_harness.topology_poc.schema import ENTRANCE_ID, Realizability, TopologyProposal

_CIRCULATION_ROLES = frozenset({"HALL", "CIRCULATION"})
_WET_ROLES = frozenset({"BATHROOM", "TOILET"})
_PRIVATE_ROLES = frozenset({"BEDROOM", "MASTER_BEDROOM", "SAFE_ROOM", "STUDY", "DRESSING_ROOM"})


def classify_realizability(proposal: TopologyProposal) -> Realizability:
    role_by_id = proposal.role_by_id
    circulation_ids = tuple(rid for rid, role in role_by_id.items() if role in _CIRCULATION_ROLES)
    wet_ids = frozenset(rid for rid, role in role_by_id.items() if role in _WET_ROLES)
    private_ids = frozenset(rid for rid, role in role_by_id.items() if role in _PRIVATE_ROLES)

    if not circulation_ids and private_ids:
        return Realizability.UNKNOWN

    if len(circulation_ids) > 1:
        return Realizability.NOT_REALIZABLE

    entrance_targets = frozenset(b for a, b in proposal.access_graph if a == ENTRANCE_ID)
    if entrance_targets and entrance_targets & private_ids:
        return Realizability.NOT_REALIZABLE

    if wet_ids:
        wet_core = frozenset(proposal.clusters.get("wet_core", ()))
        if wet_ids - wet_core:
            return Realizability.NOT_REALIZABLE

    if circulation_ids:
        hub = circulation_ids[0]
        served_by_hub = {b for a, b in proposal.access_graph if a == hub} | \
            {a for a, b in proposal.access_graph if b == hub}
        unserved_private = private_ids - served_by_hub
        if unserved_private:
            return Realizability.NOT_REALIZABLE

    return Realizability.REALIZABLE
