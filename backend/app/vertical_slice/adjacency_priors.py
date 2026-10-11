"""Real-plan adjacency priors (Issue #141) — STEP 5: a soft, LOWEST-precedence ranking preference,
never a gate.

Reads the artifact `app.knowledge.adjacency_priors` measured in Step 1 and scores a
`concept_generator.ConceptCandidate` by the log-likelihood (`plan_log_likelihood`) of its OWN
adjacency pattern under the measured real distribution — computed on the candidate's SOLVED Rect
geometry (`geometry_core.engine.solve_fixture`), the earliest point in the pipeline real room
positions exist. Unlike `room_proportion_priors` (areas are known pre-solve, from `ZoneSpec.
net_area_target_m2`), adjacency genuinely needs positions, so this module solves the fixture itself
rather than reading a pre-solve field. `solve_fixture` is the same deterministic, cheap placement
`general_pipeline.py` calls again later for the candidate the pipeline actually tries to realize —
calling it here a second time (only when `ADJACENCY_PRIORS_ENABLED`, off by default) costs nothing
in the shipped configuration.

NEVER A GATE, NEVER A VALIDATOR: `concept_generator.generate_concepts` appends `adjacency_score(c)`
as the LAST element of its own sort key, strictly after `room_proportion_priors.priors_score` (this
module's own precedence sits BELOW #140's already-verified soft signal, never above it) — it can
only ever reorder candidates every existing criterion already left exactly tied. It never touches
which of `accepted`/`tier2`/`quality` a candidate belongs to, and never removes or refuses one.

Disabled by default (`ADJACENCY_PRIORS_ENABLED = False`). With the flag OFF this module returns a
constant `0.0` for every candidate — a genuine no-op on ordering, since Python's `list.sort` is
stable and appending the SAME value to every key can never change relative order.
"""
from __future__ import annotations

from app.knowledge.adjacency_priors import (
    AdjacencyPriorsError,
    AdjacencyPriorsTable,
    eligible_pairs_for_roles,
    load_priors_table,
    plan_log_likelihood,
)

from .geometry_core.engine import GeometryInfeasible, solve_fixture
from .geometry_core.model import ProgramRole, Rect
from .relationships import MIN_MEANINGFUL_SHARED_BOUNDARY_M, shared_boundary_m

ADJACENCY_PRIORS_ENABLED = False

#: ResPlan's own room labelling (the Step 1 artifact's source) has no MASTER_BEDROOM type distinct
#: from BEDROOM — identical mapping to `room_proportion_priors._ROLE_TO_PRIORS_ROLE`, same reason.
_ROLE_TO_PRIORS_ROLE: dict[ProgramRole, str] = {
    ProgramRole.MASTER_BEDROOM: ProgramRole.BEDROOM.value,
}

_table_cache: AdjacencyPriorsTable | None = None
_table_load_failed = False


def _priors_role(role: ProgramRole) -> str:
    return _ROLE_TO_PRIORS_ROLE.get(role, role.value)


def _table() -> AdjacencyPriorsTable | None:
    """`None` when the committed artifact is missing/empty. See `room_proportion_priors._table`
    for why this caches the failure once and returns a neutral `None` forever after, rather than
    raising into `generate_concepts` on every sort."""
    global _table_cache, _table_load_failed
    if _table_cache is not None or _table_load_failed:
        return _table_cache
    try:
        _table_cache = load_priors_table()
    except AdjacencyPriorsError:
        _table_load_failed = True
        return None
    return _table_cache


def _rects_adjacent(a_id: str, b_id: str, rects: dict[str, Rect]) -> bool:
    if a_id not in rects or b_id not in rects:
        return False
    return shared_boundary_m(rects[a_id], rects[b_id]) >= MIN_MEANINGFUL_SHARED_BOUNDARY_M - 1e-9


def candidate_role_zone_ids(candidate) -> dict[str, list[str]]:
    """The candidate's own zones, grouped by the artifact's role naming — every instance kept (no
    single-largest reduction: unlike the real-plan corpus's ResPlan labelling, the engine's own
    programme never doubles up a role as a mislabeled fragment)."""
    role_zone_ids: dict[str, list[str]] = {}
    for zone in candidate.concept.fixture.zones:
        role_zone_ids.setdefault(_priors_role(zone.primary_role), []).append(zone.zone_id)
    return role_zone_ids


def candidate_eligible_pair_outcomes(candidate) -> list[tuple[str, str, bool]] | None:
    """`(role_a, role_b, adjacent)` for every unordered pair of distinct roles the candidate's own
    programme carries, measured on its SOLVED geometry. `None` — no evidence, not a fabricated
    empty list treated as a real measurement — when the fixture cannot be solved at all."""
    try:
        solve = solve_fixture(candidate.concept.fixture)
    except GeometryInfeasible:
        return None
    role_zone_ids = candidate_role_zone_ids(candidate)
    outcomes = []
    for role_a, role_b in eligible_pairs_for_roles(role_zone_ids):
        adjacent = any(_rects_adjacent(a, b, solve.rects)
                       for a in role_zone_ids[role_a] for b in role_zone_ids[role_b])
        outcomes.append((role_a, role_b, adjacent))
    return outcomes


def adjacency_score(candidate) -> float:
    """The candidate's own adjacency-fidelity score — LOWER is closer to the measured real
    distribution (the negated log-likelihood, so this follows the same "lower is better" sort
    convention as `room_proportion_priors.priors_score`). Always `0.0` when disabled, when the
    artifact is unavailable, when the candidate's fixture cannot be solved, or when no eligible pair
    has a supported row — a candidate is NEVER penalised for evidence this measurement lacks."""
    if not ADJACENCY_PRIORS_ENABLED:
        return 0.0
    table = _table()
    if table is None:
        return 0.0
    outcomes = candidate_eligible_pair_outcomes(candidate)
    if not outcomes:
        return 0.0
    score = plan_log_likelihood(outcomes, table)
    if score is None:
        return 0.0
    return round(-score, 6)
