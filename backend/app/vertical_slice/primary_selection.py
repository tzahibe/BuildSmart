"""Multi-level candidate ranking — `select_primary`: `[BuildingCandidate] -> one primary`.

A SEPARATE function from `plan_buildings`, by design (`MULTI_LEVEL_CANDIDATE_RANKING
_INVESTIGATION_REPORT.md`, approved as the policy this module implements): the coordinator's job
is to produce every valid candidate; this module's job is to pick one, and nothing here feeds
back into search or validation. Every candidate this module reads already passed every active
per-level C-check and building-level V-check — `plan_buildings` only ever appends a
`BuildingCandidate` after `validate_building(...).ok` (see that module) — so no filtering happens
here; ranking never compensates for invalid geometry because invalid geometry never arrives.

THE POLICY IS LEXICOGRAPHIC, NOT WEIGHTED — a tuple comparison, stage by stage, never a scored
sum (the investigation report's own finding, §5: "do not invent an arbitrary weighted sum unless
the data proves they are needed" — it did not):

    A. explicit user preference satisfaction    (fewer violations first)
    B. worst bedroom-class aspect                (lower first)
    C. master aspect                             (lower first)
    D. remaining quality/wet-access warnings      (fewer first)
    E. circulation + core burden                  (lower first)
    F. |delivered / requested - 1|                (lower first)
    G. deterministic candidate order               (final fallback only)

NO STRATEGY, LOBBY FORM, RETREAT OR `k` EVER RECEIVES A BONUS — every stage above reads either an
explicit preference (§ below) or a REALIZED quality measurement off `candidate.building`; nothing
compares `candidate.strategy == "..."` for its own sake.

EXPLICIT PREFERENCES (stage A) — the investigation report's finding, §1-2: the only two that are
measurable without inventing one are already threaded through, both from EXISTING fields:

  * `ProgramSpec.open_plan_living` (structural, already binding): violated when a candidate's
    ground is `closed_kitchen` while the person asked for open living/dining
    (`BuildingCandidate.ground_layout`, set by `level_program.py` — never re-derived from warning
    TEXT, which is why `_open_plan_violated` below is a structural check, not a string match).
  * `HouseConcept.public_private_strategy` (`spec.py`, PREFERENCE-strength only — a HARD-bound one
    is gated in `plan_buildings` itself, before this module ever sees the excluded allocation):
    violated when a candidate's `.strategy` does not match the person's stated one.

Nothing else is invented. A future preference (e.g. `master_level`) needs its own violation
predicate added here, the same shape as these two — never folded into the generic "warnings" pool.
"""
from __future__ import annotations

from dataclasses import dataclass

from .building_coordinator import BuildingCandidate
from .spec import HouseConcept, ProgramSpec, PublicPrivateStrategy

#: The open-plan trade-off notice fires when honouring the preference selects a primary whose
#: worst bedroom-class aspect is either past this ABSOLUTE bound, or worse than the best
#: preference-violating alternative's by at least this MARGIN — task-specified thresholds, not
#: derived from this investigation's data (which only established that the trade-off is real and
#: sometimes severe, e.g. 1.61 -> 2.35 in the ranking report's own §6).
OPEN_PLAN_ASPECT_ABSOLUTE_THRESHOLD = 2.0
OPEN_PLAN_ASPECT_RELATIVE_THRESHOLD = 0.25

_BED_CLASS_PREFIXES = ("BEDROOM", "MASTER", "SAFE_ROOM")


@dataclass(frozen=True)
class QualityMetrics:
    """Realized quality, read off `candidate.building` — never off which generator path
    produced it. Every field here is a MEASUREMENT; ranking never trusts a label instead."""

    worst_bed_aspect: float
    master_aspect: float
    ground_circ_pct: float
    upper_circ_pct: float
    total_circ_core_pct: float
    delivered: float

    @property
    def delivered_dist(self) -> float:
        return abs(self.delivered - 1.0)


def _level_metrics(level_plan) -> tuple[float, float, float, dict[str, float]]:
    rooms = {r.zone_id: r for r in level_plan.design.rooms}
    net = sum(r.net_area_m2 for r in level_plan.design.rooms)
    circ = sum(rooms[z].net_area_m2 for z in ("HALL", "HALL_2") if z in rooms)
    stair = rooms["STAIR"].net_area_m2 if "STAIR" in rooms else 0.0
    aspects = {r.zone_id: max(r.net_w_m, r.net_h_m) / max(min(r.net_w_m, r.net_h_m), 1e-6)
              for r in level_plan.design.rooms}
    return net, circ, stair, aspects


def quality_metrics_of(candidate: BuildingCandidate, requested_total_m2: float) -> QualityMetrics:
    """The realized quality of one candidate — public so a caller can report it without
    re-deriving the policy's own measurements (item 5 of the ranking task)."""
    ground, upper = candidate.building.levels
    g_net, g_circ, g_stair, g_aspects = _level_metrics(ground)
    u_net, u_circ, u_stair, u_aspects = _level_metrics(upper)
    bed_aspects = [v for aspects in (g_aspects, u_aspects) for zid, v in aspects.items()
                  if zid.startswith(_BED_CLASS_PREFIXES)]
    master_aspect = u_aspects.get("MASTER") or g_aspects.get("MASTER") or 0.0
    total_net = g_net + u_net
    total_gross = ground.design.gross_area_m2 + upper.design.gross_area_m2
    total_circ_core = g_circ + g_stair + u_circ + u_stair
    return QualityMetrics(
        worst_bed_aspect=max(bed_aspects) if bed_aspects else 0.0,
        master_aspect=master_aspect,
        ground_circ_pct=(g_circ / g_net) if g_net else 0.0,
        upper_circ_pct=(u_circ / u_net) if u_net else 0.0,
        total_circ_core_pct=(total_circ_core / total_net) if total_net else 0.0,
        delivered=(total_gross / requested_total_m2) if requested_total_m2 else 1.0,
    )


def _open_plan_violated(candidate: BuildingCandidate, program: ProgramSpec) -> bool:
    """A structural check, not a string match on warning text: `ground_layout` is set to
    `closed_kitchen` by `level_program.py` in exactly the case that also carries the
    reinterpretation warning (`_closed_kitchen_program`) — checking the field the allocation
    stage already computed is the single source of truth, not a second, textual one."""
    return program.open_plan_living and candidate.ground_layout == "closed_kitchen"


def _strategy_preference_violated(candidate: BuildingCandidate, concept: HouseConcept | None) -> bool:
    if concept is None or concept.public_private_strategy is PublicPrivateStrategy.ENGINE:
        return False
    return candidate.strategy != concept.public_private_strategy.value


def preference_violations(candidate: BuildingCandidate, program: ProgramSpec,
                          concept: HouseConcept | None) -> int:
    """Stage A's own count — public so a caller can explain WHY a candidate ranked where it did."""
    return (1 if _open_plan_violated(candidate, program) else 0) + \
           (1 if _strategy_preference_violated(candidate, concept) else 0)


def quality_warning_count(candidate: BuildingCandidate, program: ProgramSpec) -> int:
    """Stage D's own count — every REMAINING `LevelProgram.warning` after the ones already
    counted as an explicit-preference violation (stage A) are excluded, so nothing is counted
    twice under two different names.

    `level_program._split` builds ONE warnings list and hands it to BOTH the ground and upper
    `LevelProgram`s unchanged (a pre-existing property of that module, out of this task's scope
    to change) — so `ground_warnings`/`upper_warnings` can carry the SAME string on both levels.
    Counted by DISTINCT text, not by raw length: the fact is one warning ("the ground level has
    no bathroom"), not two, and a candidate should not be penalised twice for one gap merely
    because both levels' `LevelProgram`s happen to repeat it."""
    ground_warnings = list(candidate.ground_warnings)
    if _open_plan_violated(candidate, program):
        # `_closed_kitchen_program` always appends the reinterpretation warning LAST
        # (`(*warnings, reinterpretation)`) — positional, not a text match against a string that
        # has no importable constant (it is a local variable in that function).
        ground_warnings = ground_warnings[:-1]
    return len(set(ground_warnings) | set(candidate.upper_warnings))


def _lex_key(candidate: BuildingCandidate, metrics: QualityMetrics, program: ProgramSpec,
            concept: HouseConcept | None, index: int) -> tuple:
    return (preference_violations(candidate, program, concept), metrics.worst_bed_aspect,
           metrics.master_aspect, quality_warning_count(candidate, program),
           metrics.total_circ_core_pct, metrics.delivered_dist, index)


@dataclass(frozen=True)
class RankedCandidate:
    """One candidate as the policy scored it — the full ranked list, for a caller that wants to
    show alternatives or explain the choice, not just the winner."""

    candidate: BuildingCandidate
    metrics: QualityMetrics
    preference_violations: int
    quality_warnings: int


@dataclass(frozen=True)
class TradeOffNotice:
    """A NOTICE, never a refusal and never a preference override (task item 4) — the explicit
    preference stays authoritative; this only makes its realized cost visible. `alternative_*`
    names the best candidate the policy would have picked had stage A been ignored, so the notice
    can say exactly what was traded and for what."""

    kind: str
    message_he: str
    selected_worst_bed_aspect: float
    alternative_worst_bed_aspect: float
    alternative_family: str


@dataclass(frozen=True)
class SelectionResult:
    primary: BuildingCandidate | None
    primary_metrics: QualityMetrics | None
    ranked: tuple[RankedCandidate, ...]
    notice: TradeOffNotice | None

    @property
    def any(self) -> bool:
        return self.primary is not None


def select_primary(candidates: tuple[BuildingCandidate, ...], program: ProgramSpec,
                   requested_total_m2: float, *, concept: HouseConcept | None = None,
                   ) -> SelectionResult:
    """The policy described in the module docstring, applied to a `CoordinatorResult.candidates`
    tuple exactly as `plan_buildings` returned it — no filtering, no re-validation; every
    candidate here already passed every active C and V check by construction.

    `program`/`requested_total_m2` are the SAME values the caller already passed to
    `plan_buildings` — nothing here is a second source of truth for the request; `concept` is the
    same `HouseConcept` too (`None` when the person expressed no multi-level preference at all,
    matching `plan_buildings`'s own default)."""
    if not candidates:
        return SelectionResult(None, None, (), None)

    scored = [(c, quality_metrics_of(c, requested_total_m2)) for c in candidates]

    full_order = sorted(range(len(scored)),
                        key=lambda i: _lex_key(scored[i][0], scored[i][1], program, concept, i))
    ranked = tuple(RankedCandidate(scored[i][0], scored[i][1],
                                   preference_violations(scored[i][0], program, concept),
                                   quality_warning_count(scored[i][0], program))
                  for i in full_order)
    primary, primary_metrics = scored[full_order[0]]

    # The trade-off notice compares the primary against the best candidate the SAME lexicographic
    # policy would pick with stage A dropped (quality only) — the exact "another valid candidate"
    # item 4 asks for, not an arbitrary runner-up.
    quality_order = sorted(range(len(scored)),
                           key=lambda i: _lex_key(scored[i][0], scored[i][1], program, concept, i)[1:])
    best_quality, best_quality_metrics = scored[quality_order[0]]

    notice = None
    if (primary is not best_quality and not _open_plan_violated(primary, program)
            and _open_plan_violated(best_quality, program)):
        selected = primary_metrics.worst_bed_aspect
        alternative = best_quality_metrics.worst_bed_aspect
        if selected > OPEN_PLAN_ASPECT_ABSOLUTE_THRESHOLD or \
           (selected - alternative) >= OPEN_PLAN_ASPECT_RELATIVE_THRESHOLD:
            notice = TradeOffNotice(
                kind="OPEN_PLAN_BEDROOM_TRADEOFF",
                message_he="העדפת חלל ציבורי פתוח נשמרה, אך היא גורמת לחדר שינה צר יותר בתוכנית זו.",
                selected_worst_bed_aspect=round(selected, 3),
                alternative_worst_bed_aspect=round(alternative, 3),
                alternative_family=best_quality.family)

    return SelectionResult(primary, primary_metrics, ranked, notice)
