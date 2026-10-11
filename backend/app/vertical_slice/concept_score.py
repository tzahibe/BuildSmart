"""Concept-level scoring and the bounded adaptation ladder (Issue #76, Concept Engine v2 3/5).

Moves the quality feedback loop from "generate -> validate -> rank" toward
"concept -> realize -> measure -> adapt -> realize again": `concept_score` reads a REALIZED
plan's own already-computed deterministic facts — never re-solving anything and never touching
`hub_guard`/`l_massing_guard`/quality-twin decisions, which stay the pipeline's own last word on
which realized plan wins a slot — and `adapt` proposes a bounded number of CONCEPT-level changes
(never a geometry change) for a caller to re-realize and re-measure.

    concept_score(plan)   -> ConceptScore   one `RealizedPlan`'s standing, a pure function of data
                                            that already exists on it:
                                              * `hub_guard.proportions_of(plan.design)` for the
                                                bedroom/master aspect and the M5-equivalent wet-
                                                adjacency share (the same touching-rects fact 008's
                                                bound already gates on);
                                              * M3 (circulation share) and M4 (hall door count/
                                                aspect), read directly off `plan.design`'s own
                                                rooms/doors — the `GeometricDesign` analogue of
                                                `quality_metrics.py`'s M3/M4, which this module
                                                cannot import (that module operates on
                                                `app.demo.contract.DemoDesign`, a layer that
                                                imports `app.vertical_slice.*` and would cycle back
                                                here — the same constraint `quality_metrics.py`'s
                                                own docstring documents, and the same "two
                                                independently computed facts at two layers"
                                                precedent `quality_metrics.baseline_summary_from_
                                                metrics` already lives with for M5);
                                              * `plan.design.wet_core` (Issue #44) for the wet-core
                                                grouping (plumbing-complexity index);
                                              * the entrance rank (#20): 0 when the front door
                                                opens into HALL/CIRCULATION, 1 for LIVING, 2
                                                otherwise — the same fact `general_pipeline.
                                                _entrance_rank` computes, read here directly off
                                                `plan.design` (not imported: a private, underscored
                                                symbol of another module) since `RealizedPlan`
                                                itself never stores the rank;
                                              * `concept_spec.verify_class` for whether the
                                                candidate's declared class survived realization.
                                            C24 (access topology) and C19 (required exterior
                                            exposure) are never re-checked here: they already
                                            gate `plan.validation`/`plan.ok` during `_realize`, so
                                            a plan that reaches this function already cleared them
                                            or is marked `rejected`.
    ConceptScore                           the result: a documented weighted total (higher is
                                            better), `rejected` (any validation/safety failure),
                                            `class_verified`, and every component the total is
                                            built from, for diagnostics and for extension hooks
                                            (#36 circulation metrics, #43 residual pockets — an
                                            `extra` slot exists for exactly this, unused today).
    adapt(spec, plan, score)  -> ConceptSpec | None
                                            the bounded ladder: cluster the shared wet rooms (the
                                            `SPINE_SERVICE_CLUSTER` move) when there is more than
                                            one wet-core group and the realized wet standing shows
                                            room for it; else flip the zoning split
                                            (`SIDE_BY_SIDE` <-> `FRONT_REAR`) when the topology
                                            allows it; else give up (`None`). Gives up immediately,
                                            regardless of `attempt`, when the realized plan failed
                                            C24 or C19 — a structural defect no concept-level
                                            metadata change can repair. Never changes
                                            `circulation_class`, and never proposes a move past
                                            `attempt >= ADAPT_LIMIT` re-realizations for one class.
                                            Re-sizing from a witness (008's own pattern,
                                            `_plan_hub_wing(witness=...)`) is deliberately NOT a
                                            third rung here: `ConceptSpec` is a TOPOLOGY contract
                                            (its own docstring) with no numeric sizing field, and
                                            adding a witness AREA to it — as opposed to a witness
                                            TOPOLOGY move — is real generator-facing scope this
                                            Issue does not touch (`hub_guard`/`concept_generator`'s
                                            sizing machinery is explicitly out of scope). `ADAPT_
                                            LIMIT = 2` therefore matches this module's two rungs.

Nothing here is wired into `run_general` (see the ROOT Issue's CE2-4): every caller today is a
test or `spikes/failure_log_sweep/concept_adaptation_report.py`.
"""
from __future__ import annotations

import dataclasses
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import hub_guard
from .concept_spec import ConceptSpec, CirculationClass, ZoningSplit, verify_class
from .geometry_core.model import ProgramRole

if TYPE_CHECKING:
    from .general_pipeline import RealizedPlan

#: Same vocabulary `concept_spec.py` classifies a realized hall against.
_HALL_ROLES = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})

# --------------------------------------------------------------------------- weights (documented)
#
# HIGHER total is better. Ordinal, not fit to data — no corpus of "good"/"bad" concepts exists yet
# to calibrate against (that is what this module's own report, run over time, would build). M4/M5
# dominate because they read the PARTI itself: how circulation and plumbing are organised, the
# thing a concept-level adaptation can actually change. M1 (bedroom/master proportions) is a
# secondary quality signal a later re-sizing pass could fix without touching the concept. Wet-core
# complexity and the entrance rank are tertiary tie-breaking signals. One place to change if this
# needs recalibrating against a real "which of these two houses reads better" corpus later.

#: M1 — bedroom/master long-short aspect, penalised past a perfect square (1.0).
W_BEDROOM_ASPECT = 4.0
W_MASTER_ASPECT = 4.0
#: M3 — share of gross area spent on circulation; lower is better.
W_CIRCULATION_SHARE = 20.0
#: M4 — hall long/short aspect (lower/more compact is better) and the doors that open onto it
#: (more is a richer lobby, the HUB_LOBBY signal `concept_spec.realized_circulation_class` gates
#: on) — the same two facts, scored rather than thresholded.
W_HALL_ASPECT = 6.0
W_HALL_DOOR_COUNT = 0.5
#: M5 — share of wet rooms adjacent to another wet room or the kitchen.
W_WET_ADJACENCY = 10.0
#: wet_core (#44) — independent plumbing runs; fewer is better.
W_PLUMBING_COMPLEXITY = 1.0
#: #20 — 0 (HALL/CIRCULATION), 1 (LIVING) or 2 (elsewhere).
W_ENTRANCE_RANK = 3.0

#: `adapt`'s bound — at most this many re-realizations of one class's concept before giving up
#: (see the module docstring for why this matches the ladder's two rungs).
ADAPT_LIMIT = 2

#: A realized plan that failed either of these already failed for a reason no concept-level
#: metadata change repairs — `adapt` gives up outright rather than proposing a move.
_HARD_REJECT_CHECKS = frozenset({"C24", "C19"})


@dataclass(frozen=True)
class ConceptScore:
    """One `RealizedPlan`'s concept-level standing — see the module docstring for how each field
    is read and `key()` for the total order `adapt`'s caller ranks by."""

    index: int
    rejected: bool
    class_verified: bool
    circulation_class: CirculationClass | None
    bedroom_aspect: float | None
    master_aspect: float | None
    circulation_share: float
    hall_door_count: int | None
    hall_aspect_median: float | None
    wet_adjacency_share: float | None
    plumbing_complexity_index: int
    entrance_rank: int
    total: float
    #: Hook for a future measured component (#36 circulation metrics, #43 residual pockets) —
    #: `(name, value)` pairs already folded into `total`; empty until a caller passes one to
    #: `concept_score`.
    extra: tuple[tuple[str, float], ...] = ()

    def key(self) -> tuple:
        """Deterministic total order, ascending = better: a rejected plan sorts after every
        accepted one regardless of its total (a defect is not something a higher M1 buys back);
        among plans of the same standing, higher `total` sorts first; `index` is the last-resort
        tie-break (never reached unless `total` is exactly equal)."""
        return (self.rejected, -self.total, self.index)


def better(a: ConceptScore, b: ConceptScore) -> ConceptScore:
    """Which of two scores reads as the better concept — `a` on an exact tie, so the choice is
    deterministic rather than depending on argument order (the same tie rule `wet_core.
    better_candidate`/`wet_privacy.better_candidate` use)."""
    return a if a.key() <= b.key() else b


# --------------------------------------------------------------------------- reading the plan


def _circulation_share(design) -> float:
    if not design.gross_area_m2:
        return 0.0
    hall_area = sum(r.net_area_m2 for r in design.rooms if _HALL_ROLES & set(r.roles))
    return hall_area / design.gross_area_m2


def _hall_stats(design) -> tuple[int | None, float | None]:
    hall_ids = {r.zone_id for r in design.rooms if _HALL_ROLES & set(r.roles)}
    hall_rooms = [r for r in design.rooms if r.zone_id in hall_ids]
    if not hall_rooms:
        return None, None
    aspects = []
    for r in hall_rooms:
        _, _, w, h = r.rect_m
        aspects.append(max(w, h) / max(min(w, h), 1e-6))
    door_count = sum(1 for d in design.interior_doors if d.a in hall_ids or d.b in hall_ids)
    return door_count, statistics.median(aspects)


def _entrance_rank(design) -> int:
    """0 when the realized front door opens into HALL/CIRCULATION, 1 for LIVING, 2 otherwise —
    the same fact `general_pipeline._entrance_rank` computes (Issue #20), read here directly off
    `design` since that function is private to its own module and `RealizedPlan` does not carry
    the rank itself."""
    target = design.entrance_door.b
    roles = next((r.roles for r in design.rooms if r.zone_id == target), ())
    if _HALL_ROLES & set(roles):
        return 0
    if ProgramRole.LIVING in roles:
        return 1
    return 2


def concept_score(plan: "RealizedPlan", *, extra: tuple[tuple[str, float], ...] = ()) -> ConceptScore:
    """`ConceptScore` for one realized plan — see the module docstring. Deterministic: every
    input is a field already on `plan`/`plan.design`, or a pure function of them."""
    design = plan.design
    proportions = hub_guard.proportions_of(design)
    hall_door_count, hall_aspect_median = _hall_stats(design)
    plumbing_complexity = design.wet_core.plumbing_complexity_index if design.wet_core is not None else 0
    mismatch = verify_class(plan.concept, plan)

    bedroom_component = (-W_BEDROOM_ASPECT * (proportions.bedroom_max - 1.0)
                        if proportions.bedroom_max is not None else 0.0)
    master_component = (-W_MASTER_ASPECT * (proportions.master - 1.0)
                        if proportions.master is not None else 0.0)
    circulation_share = _circulation_share(design)
    circulation_component = -W_CIRCULATION_SHARE * circulation_share
    hall_aspect_component = (-W_HALL_ASPECT * (hall_aspect_median - 1.0)
                             if hall_aspect_median is not None else 0.0)
    hall_door_component = W_HALL_DOOR_COUNT * hall_door_count if hall_door_count is not None else 0.0
    wet_adjacency_share = proportions.wet_share if proportions.wet_total else None
    wet_component = W_WET_ADJACENCY * wet_adjacency_share if wet_adjacency_share is not None else 0.0
    plumbing_component = -W_PLUMBING_COMPLEXITY * plumbing_complexity
    entrance_rank = _entrance_rank(design)
    entrance_component = -W_ENTRANCE_RANK * entrance_rank
    extra_total = sum(value for _, value in extra)

    total = (bedroom_component + master_component + circulation_component + hall_aspect_component
            + hall_door_component + wet_component + plumbing_component + entrance_component
            + extra_total)

    return ConceptScore(
        index=plan.index,
        rejected=not plan.ok,
        class_verified=mismatch is None,
        circulation_class=plan.circulation_class,
        bedroom_aspect=proportions.bedroom_max,
        master_aspect=proportions.master,
        circulation_share=circulation_share,
        hall_door_count=hall_door_count,
        hall_aspect_median=hall_aspect_median,
        wet_adjacency_share=wet_adjacency_share,
        plumbing_complexity_index=plumbing_complexity,
        entrance_rank=entrance_rank,
        total=total,
        extra=extra,
    )


# --------------------------------------------------------------------------- the adaptation ladder


_ZONING_FLIP = {
    ZoningSplit.SIDE_BY_SIDE: ZoningSplit.FRONT_REAR,
    ZoningSplit.FRONT_REAR: ZoningSplit.SIDE_BY_SIDE,
}


def _hard_rejected(plan: "RealizedPlan") -> bool:
    return any(c.check_id in _HARD_REJECT_CHECKS and not c.passed for c in plan.validation.checks)


def _cluster_wet_rooms(spec: ConceptSpec, score: ConceptScore) -> ConceptSpec | None:
    """The `SPINE_SERVICE_CLUSTER` move: merge every wet-core group into one shared group.
    Applicable only when there is more than one group to merge AND the realized plan's own wet
    standing shows room for it (an imperfect M5 share, or more than one independent plumbing run)
    — a plan already at 100% wet adjacency with one plumbing run has nothing this move improves."""
    if len(spec.wet_core_groups) <= 1:
        return None
    already_efficient = (
        (score.wet_adjacency_share is None or score.wet_adjacency_share >= 1.0 - 1e-9)
        and score.plumbing_complexity_index <= 1)
    if already_efficient:
        return None
    merged = tuple(sorted(zone_id for group in spec.wet_core_groups for zone_id in group))
    return dataclasses.replace(spec, wet_core_groups=(merged,), wet_core_strategy="ALL_SHARED")


def _flip_zoning(spec: ConceptSpec) -> ConceptSpec | None:
    """Flip the zoning split (`SIDE_BY_SIDE` <-> `FRONT_REAR`), same `circulation_class`. `None`
    for `WRAPPED` (the L parti) — it has no side-by-side/front-rear complement to flip to."""
    flipped = _ZONING_FLIP.get(spec.zoning)
    return None if flipped is None else dataclasses.replace(spec, zoning=flipped)


def adapt(spec: ConceptSpec, plan: "RealizedPlan", score: ConceptScore,
         *, attempt: int = 0) -> ConceptSpec | None:
    """The next concept to try, or `None` to give up — see the module docstring for the ladder
    and the give-up conditions. Never returns a spec whose `circulation_class` differs from
    `spec.circulation_class`: neither rung below ever touches that field."""
    if attempt >= ADAPT_LIMIT or _hard_rejected(plan):
        return None
    return _cluster_wet_rooms(spec, score) or _flip_zoning(spec)
