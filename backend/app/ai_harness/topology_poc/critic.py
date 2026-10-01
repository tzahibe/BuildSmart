"""Deterministic, geometry-free critic (Issue #151, AC-5, AC-9, AC-10, AC-12).

BLIND TO SOURCE (AC-10, owner correction): `score_topology`'s only parameters are a
`schema.TopologyProposal` and a `priors.Priors` — no `source`, no `realizability`, no provenance of
any kind. `TopologyProposal` itself (`schema.py`) carries no such field either — there is nothing
here for a `source` value to travel THROUGH even if a caller wanted to pass one. The current
generator's own topology and every LLM proposal are wrapped in the identical `TopologyProposal`
before reaching this module, so this function cannot tell them apart — proven by
`tests/ai_harness/test_topology_critic.py::test_critic_is_blind_to_source`.

REALIZABILITY IS METADATA ONLY (AC-9): `Realizability` never appears in this module's imports or
signatures. `score_topology`'s output is bit-identical no matter what `realizability.py` later
labels the SAME proposal — proven by
`tests/ai_harness/test_topology_critic.py::test_score_is_independent_of_realizability_label`.

ADJACENCY PRIOR READS ONLY `spatial_touching`; ACCESS PRIOR READS ONLY `access` (AC-12): this
module never imports `priors.Priors.diagnostic_touching_without_door_rows` — grep confirms it below
is the only reference to that field in this whole package (report-only, in `report.py`).

SCORING MODEL (documented once, since the acceptance criteria ask for one deterministic score to
rank proposals against): `plan_log_likelihood` (reused unmodified from `app.knowledge.
adjacency_priors`) returns a log-likelihood in (-inf, 0], or `None` when zero role pairs are
eligible — a genuine "no evidence", never a fabricated 0.0. Combining a possibly-`None` value into
one final ranking number needs a neutral fallback: `_NO_EVIDENCE_FALLBACK = log(0.5)` (the
log-likelihood of a coin flip — neither rewarded nor punished for being unmeasurable). The report
(AC-5) always surfaces the TRUE `adjacency_similarity`/`access_similarity` (including `None` when
genuine), never the fallback-substituted number — only `total_score`'s internal combination uses
the fallback.

Every hard-rule violation subtracts `_HARD_VIOLATION_PENALTY` from `total_score` — large enough
that a single hard violation outranks any plausible combination of the soft scores, matching how a
validator gate behaves today (a violation should not be out-argued by otherwise-good adjacency).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.ai_harness.topology_poc.priors import Priors, eligible_pairs_for_roles, score_role_pairs
from app.ai_harness.topology_poc.schema import ENTRANCE_ID, TopologyProposal

_NO_EVIDENCE_FALLBACK = math.log(0.5)
_HARD_VIOLATION_PENALTY = 10.0

#: Roles the entrance must never open directly into (bypassing every public room) — the "no
#: bedroom-to-bedroom access" anti-pattern's entrance-specific cousin (quality rubric section I).
_PRIVATE_OR_SERVICE_ROLES = frozenset({
    "BEDROOM", "MASTER_BEDROOM", "SAFE_ROOM", "STUDY", "DRESSING_ROOM",
    "BATHROOM", "TOILET", "LAUNDRY", "STORAGE",
})
_BEDROOM_ROLES = frozenset({"BEDROOM", "MASTER_BEDROOM"})
_WET_ROLES = frozenset({"BATHROOM", "TOILET"})


@dataclass(frozen=True)
class ScoreBreakdown:
    adjacency_similarity: "float | None"
    access_similarity: "float | None"
    wet_core_similarity: "float | None"
    entrance_relation_score: "float | None"
    hard_violations: tuple  # tuple[str, ...] — empty when none
    total_score: float


def _instance_pair_positive(proposal: TopologyProposal, role_a: str, role_b: str, pairs: frozenset) -> bool:
    ids_a = [r.id for r in proposal.rooms if r.role == role_a]
    ids_b = [r.id for r in proposal.rooms if r.role == role_b]
    return any(frozenset((a, b)) in pairs for a in ids_a for b in ids_b)


def _adjacency_similarity(proposal: TopologyProposal, priors: Priors) -> "float | None":
    roles = sorted({r.role for r in proposal.rooms})
    outcomes = [(a, b, _instance_pair_positive(proposal, a, b, proposal.spatial_adjacency))
                for a, b in eligible_pairs_for_roles(roles)]
    return score_role_pairs(outcomes, priors.adjacency_table)


def _access_similarity(proposal: TopologyProposal, priors: Priors) -> "float | None":
    roles = sorted({r.role for r in proposal.rooms})
    undirected_access = frozenset(frozenset((a, b)) for a, b in proposal.access_graph if a != ENTRANCE_ID)
    outcomes = [(a, b, _instance_pair_positive(proposal, a, b, undirected_access))
                for a, b in eligible_pairs_for_roles(roles)]
    return score_role_pairs(outcomes, priors.access_table)


def _wet_core_similarity(proposal: TopologyProposal) -> "float | None":
    wet_ids = frozenset(r.id for r in proposal.rooms if r.role in _WET_ROLES)
    if not wet_ids:
        return None
    clustered = frozenset(proposal.clusters.get("wet_core", ()))
    return len(wet_ids & clustered) / len(wet_ids)


def _entrance_targets(proposal: TopologyProposal) -> tuple:
    return tuple(b for a, b in proposal.access_graph if a == ENTRANCE_ID)


def _entrance_relation_score(proposal: TopologyProposal, priors: Priors) -> "float | None":
    targets = _entrance_targets(proposal)
    if not targets:
        return None
    role_by_id = proposal.role_by_id
    rates = []
    for target in targets:
        role = role_by_id.get(target)
        stats = priors.front_door_direct_access.get(role)
        if stats is not None:
            rates.append(stats["rate"])
    if not rates:
        return None
    return sum(rates) / len(rates)


def _access_reachable_ids(proposal: TopologyProposal) -> frozenset:
    adjacency: dict = {}
    for a, b in proposal.access_graph:
        adjacency.setdefault(a, set()).add(b)
    seen = set()
    frontier = [ENTRANCE_ID]
    while frontier:
        node = frontier.pop()
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return frozenset(seen)


def _hard_violations(proposal: TopologyProposal) -> tuple:
    violations = []
    role_by_id = proposal.role_by_id
    room_ids = proposal.room_ids

    zoned_ids: dict = {}
    for zone_key, ids in proposal.zones.items():
        for rid in ids:
            zoned_ids.setdefault(rid, []).append(zone_key)
    for rid in room_ids:
        memberships = zoned_ids.get(rid, [])
        if not memberships:
            violations.append(f"ROOM_NOT_ZONED:{rid}")
        elif len(memberships) > 1:
            violations.append(f"ROOM_MULTI_ZONED:{rid}")

    targets = _entrance_targets(proposal)
    if not targets:
        violations.append("NO_ENTRANCE_ACCESS")
    else:
        for target in targets:
            if role_by_id.get(target) in _PRIVATE_OR_SERVICE_ROLES:
                violations.append(f"ENTRANCE_INTO_PRIVATE:{target}")

    reachable = _access_reachable_ids(proposal)
    for rid in sorted(room_ids - reachable):
        violations.append(f"DISCONNECTED_ROOM:{rid}")

    incoming: dict = {}
    for a, b in proposal.access_graph:
        incoming.setdefault(b, []).append(a)
    for rid in room_ids:
        if role_by_id.get(rid) not in _BEDROOM_ROLES:
            continue
        sources = incoming.get(rid, [])
        if sources and all(role_by_id.get(src) in _BEDROOM_ROLES for src in sources):
            violations.append(f"BEDROOM_TO_BEDROOM_ONLY_ACCESS:{rid}")

    return tuple(violations)


def score_topology(proposal: TopologyProposal, priors: Priors) -> ScoreBreakdown:
    """The one scoring entrypoint. Deterministic, geometry-free, and blind to source (see module
    docstring). `proposal` must already be a validated `schema.TopologyProposal` — this function
    does no parsing of its own."""
    adjacency_similarity = _adjacency_similarity(proposal, priors)
    access_similarity = _access_similarity(proposal, priors)
    wet_core_similarity = _wet_core_similarity(proposal)
    entrance_relation_score = _entrance_relation_score(proposal, priors)
    hard_violations = _hard_violations(proposal)

    total = 0.0
    total += adjacency_similarity if adjacency_similarity is not None else _NO_EVIDENCE_FALLBACK
    total += access_similarity if access_similarity is not None else _NO_EVIDENCE_FALLBACK
    total += wet_core_similarity if wet_core_similarity is not None else 0.0
    total += entrance_relation_score if entrance_relation_score is not None else 0.0
    total -= _HARD_VIOLATION_PENALTY * len(hard_violations)

    return ScoreBreakdown(
        adjacency_similarity=adjacency_similarity, access_similarity=access_similarity,
        wet_core_similarity=wet_core_similarity, entrance_relation_score=entrance_relation_score,
        hard_violations=hard_violations, total_score=round(total, 6))
