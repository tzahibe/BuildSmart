"""Real-plan room-proportion priors (Issue #140) — STEP 2: a soft, LOWEST-precedence ranking
preference, never a gate.

Reads the artifact `app.knowledge.room_proportion_priors` measured in Step 1 and scores a
`concept_generator.ConceptCandidate` by how far its rooms' PRE-SOLVE TARGET areas
(`ZoneSpec.net_area_target_m2` — the figure Geometry Core tiles toward, the only per-room area
available before the expensive solver runs) sit from real plans' own median for that role/bucket,
relative to that bucket's own p25-p75 spread — lower is closer to real planning.

NEVER A GATE, NEVER A VALIDATOR: `concept_generator.generate_concepts` appends `priors_score(c)` as
the LAST element of its own sort key, strictly after area proximity, `over_preferred`/`shrunk` and
the `strategy.value` determinism tiebreak — it can only ever reorder candidates every one of those
EXISTING criteria already left exactly tied. It never touches which of `accepted`/`tier2`/`quality`
a candidate belongs to (those blocks, and their strict ordering, are decided before this score is
ever read) and never removes or refuses a candidate.

Disabled by default (`ROOM_PROPORTION_PRIORS_ENABLED = False`). With the flag OFF this module
returns a constant `0.0` for every candidate — a genuine no-op on ordering, since Python's
`list.sort` is stable and appending the SAME value to every key can never change relative order.
"""
from __future__ import annotations

from app.knowledge.room_proportion_priors import (
    PriorsTable,
    RoomProportionPriorsError,
    bedroom_count_bucket,
    house_size_bucket,
    load_priors_table,
)

from .geometry_core.model import ProgramRole

ROOM_PROPORTION_PRIORS_ENABLED = False

#: ResPlan's own room labelling (the Step 1 artifact's source) has no MASTER_BEDROOM type distinct
#: from BEDROOM — every real "bedroom" instance is typed BEDROOM regardless of size. Score both
#: engine roles against the priors table's one BEDROOM row rather than skip MASTER_BEDROOM for
#: want of a row that will never exist in this data.
_ROLE_TO_PRIORS_ROLE: dict[ProgramRole, str] = {
    ProgramRole.MASTER_BEDROOM: ProgramRole.BEDROOM.value,
}

_BEDROOM_ROLES = frozenset({ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM})

_MIN_SPREAD_M2 = 1e-3

_table_cache: PriorsTable | None = None
_table_load_failed = False


def _priors_role(role: ProgramRole) -> str:
    return _ROLE_TO_PRIORS_ROLE.get(role, role.value)


def _table() -> PriorsTable | None:
    """`None` when the committed artifact is missing/empty. Step 1's `load_priors_table` fails
    loudly for the SCANNER's own callers (a CLI, a test) — but a ranking signal that could crash
    plan generation over a missing report is worse than the report being missing, so this caches
    the failure once and returns a neutral `None` (read as "no evidence, score 0.0") forever
    after, rather than raising into `generate_concepts` on every sort."""
    global _table_cache, _table_load_failed
    if _table_cache is not None or _table_load_failed:
        return _table_cache
    try:
        _table_cache = load_priors_table()
    except RoomProportionPriorsError:
        _table_load_failed = True
        return None
    return _table_cache


def _candidate_bedroom_count(candidate) -> int:
    return sum(1 for zone in candidate.concept.fixture.zones if zone.primary_role in _BEDROOM_ROLES)


def priors_score(candidate) -> float:
    """The candidate's own room-proportion-fidelity score — LOWER is closer to the measured real
    distribution. Always `0.0` when disabled, when the artifact is unavailable, or when none of
    the candidate's rooms have a matching measured row (a candidate is NEVER penalised for a role
    this measurement simply has no evidence about)."""
    if not ROOM_PROPORTION_PRIORS_ENABLED:
        return 0.0
    table = _table()
    if table is None:
        return 0.0
    house_bucket = house_size_bucket(candidate.used_area_m2, table.edges)
    bedroom_bucket = bedroom_count_bucket(_candidate_bedroom_count(candidate), table.edges)
    deviations: list[float] = []
    for zone in candidate.concept.fixture.zones:
        row = table.row_for(_priors_role(zone.primary_role), house_bucket, bedroom_bucket)
        if row is None:
            continue
        spread = max(row.p75_area_m2 - row.p25_area_m2, _MIN_SPREAD_M2)
        deviations.append(abs(zone.net_area_target_m2 - row.median_area_m2) / spread)
    if not deviations:
        return 0.0
    return round(sum(deviations) / len(deviations), 6)
