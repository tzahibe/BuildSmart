"""Production proposal SELECTION — critic first, then score, then select, then realize (Issue #142J).

    brief -> candidate proposals -> CRITIC -> keep the clean ones -> score/rank -> select -> realizer

A candidate with a HARD finding is never eligible while a clean candidate exists, whatever its
heuristic score. Nothing is repaired. When every candidate has a HARD finding the result is a typed
`NoValidProposal` carrying every candidate's findings (for controlled regeneration later) — never the
least-bad invalid proposal. If no clean candidate realizes, `NoRealizableProposal` carries the
per-candidate typed diagnoses. Everything here is deterministic.

SELECTION ON REALIZED GEOMETRY (Issue #142O, from #142M's measurement). Clean candidates are still
tried in score order inside the SAME `max_realizations` budget, but the loop no longer returns at the
first plan that validates: every PASS plan reached inside the budget is kept, and the winner is the
best of them under

    1. `arrival_policy.arrival_rank`      0 hall/circulation, 1 living, 2 other   (lower wins)
    2. the proposal score                 the existing geometry-free heuristic    (higher wins)
    3. the candidate index                stable identity, so ties never move

and the rest are returned as `alternatives`. Only term 1 is new, and it is the one term #142M proved
strictly better: across both datasets it changes the winner in 4 of 20 and 2 of 19 briefs and in every
single change it replaces a living-room arrival with a hall arrival, never the reverse. Everything
below it is the behaviour this module already had.

NO NEW SCORE AND NO NEW WEIGHT. `PlanOption.circulation` carries each plan's circulation metrics so a
caller can EXPLAIN how two alternatives differ, and it is deliberately not part of the ordering:
`circulation_metrics.circulation_prefers` was measured in #142N to be non-transitive and not even
antisymmetric, so it cannot order a set of plans at all.

BUDGET. `max_realizations` is unchanged and still defaults to `None` (unbounded). Measured on both
#142M datasets, the default truncates nothing and reproduces #142M exactly; see
`docs/reports/142o-realized-selection/`. It is the OUTER budget — how many proposals are tried.
`band_pipeline.run_band_pipeline` keeps its own, separate inner budget over one proposal's band
layouts, so one proposal still yields at most one plan.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from . import circulation_metrics
from .band_pipeline import PipelineDiagnosis, PipelineInput, PipelineSuccess, run_band_pipeline
from .arrival_policy import arrival_rank
from .proposal_critic import ENTRANCE_ID, CriticReport, Proposal, criticize


@dataclass
class CandidateVerdict:
    index: int
    report: CriticReport
    score: float | None            # scored only when eligible (critic-clean)

    @property
    def eligible(self) -> bool:
        return self.report.clean


@dataclass
class PlanOption:
    """One validator-PASS plan reached inside the budget, with everything the ordering reads.

    `sort_key` IS the selection rule — entrance arrival first, then the existing proposal score,
    then the candidate index for a stable identity — so the winner and the alternatives are ordered
    by one expression and can never disagree.
    """

    proposal: Proposal
    index: int                     # index in the candidate list
    score: float
    clean_rank: int                # rank among clean candidates by score (0 = best)
    pipeline: PipelineSuccess
    entrance_rank: int
    #: Explanatory only — NEVER a ranking term (see the module docstring and #142N).
    circulation: circulation_metrics.CirculationMetrics

    @property
    def sort_key(self) -> tuple[int, float, int]:
        return (self.entrance_rank, -self.score, self.index)


@dataclass
class ProposalSelection:
    proposal: Proposal
    index: int                     # index in the candidate list
    score: float
    clean_rank: int                # rank among clean candidates by score (0 = best)
    verdicts: list
    pipeline: PipelineSuccess
    tried: list = field(default_factory=list)      # (index, outcome code) for every clean candidate that did not pass
    seconds: float = 0.0
    #: The winner's own arrival rank — 0 hall/circulation, 1 living, 2 other.
    entrance_rank: int = 0
    #: The winner's circulation metrics. Explanatory only, never a ranking term (#142N).
    circulation: circulation_metrics.CirculationMetrics | None = None
    #: Every other PASS plan reached inside the budget, best first under `PlanOption.sort_key`.
    alternatives: list = field(default_factory=list)

    @property
    def options(self) -> list:
        """Every PASS plan, winner first — the winner and the alternatives as one ordered list."""
        return [PlanOption(self.proposal, self.index, self.score, self.clean_rank, self.pipeline,
                           self.entrance_rank, self.circulation)] + list(self.alternatives)


@dataclass
class NoValidProposal:
    code: str
    verdicts: list                 # every candidate's CriticReport, in order
    detail: str
    seconds: float = 0.0

    @property
    def findings(self) -> dict:
        return {v.index: [(f.code, f.severity, f.detail) for f in v.report.findings] for v in self.verdicts}


@dataclass
class NoRealizableProposal:
    code: str
    verdicts: list
    tried: list                    # (index, PipelineDiagnosis) for every clean candidate, in score order
    detail: str
    seconds: float = 0.0


def pipeline_input(p: Proposal, report: CriticReport, footprint_m) -> PipelineInput:
    """The unchanged pipeline's input for a critic-clean proposal: the brief's wet-room kinds as the
    critic assigned them (C17 is held to these), every direct door as an access edge."""
    spatial = tuple(sorted(tuple(sorted(e)) for e in p.spatial))
    return PipelineInput(p.name, p.zones, spatial, tuple(footprint_m), tuple(report.wet_rooms),
                         tuple((a, b) for a, b in p.access if a != ENTRANCE_ID))


def select_proposal(candidates: list, *, score: Callable[[Proposal], float], footprint_m,
                    max_realizations: int | None = None,
                    embed_max_candidates: int = 150) -> ProposalSelection | NoValidProposal | NoRealizableProposal:
    t0 = time.monotonic()
    verdicts = [CandidateVerdict(i, criticize(p, embed_max_candidates=embed_max_candidates), None)
                for i, p in enumerate(candidates)]
    clean = [v for v in verdicts if v.eligible]
    if not clean:
        codes = sorted({c for v in verdicts for c in v.report.hard_codes})
        return NoValidProposal("NO_VALID_PROPOSAL", verdicts,
                               f"every one of {len(candidates)} candidate proposal(s) has a HARD finding: " + ", ".join(codes),
                               round(time.monotonic() - t0, 3))
    for v in clean:
        v.score = float(score(candidates[v.index]))
    ordered = sorted(clean, key=lambda v: (-v.score, v.index))
    tried: list = []
    options: list[PlanOption] = []
    for rank, v in enumerate(ordered[: max_realizations or len(ordered)]):
        p = candidates[v.index]
        res = run_band_pipeline(pipeline_input(p, v.report, footprint_m))
        if isinstance(res, PipelineSuccess):
            design = res.realized.design
            options.append(PlanOption(p, v.index, v.score, rank, res, arrival_rank(design),
                                      circulation_metrics.measure(design)))
            continue                       # #142O: every PASS inside the budget is kept, not just the first
        tried.append((v.index, res))
    if options:
        options.sort(key=lambda o: o.sort_key)
        best = options[0]
        return ProposalSelection(best.proposal, best.index, best.score, best.clean_rank, verdicts,
                                 best.pipeline, [(i, d.code) for i, d in tried],
                                 round(time.monotonic() - t0, 3), best.entrance_rank,
                                 best.circulation, options[1:])
    return NoRealizableProposal("NO_REALIZABLE_PROPOSAL", verdicts, tried,
                                f"{len(clean)} critic-clean candidate(s), none realized: " +
                                ", ".join(f"#{i} {d.code}" for i, d in tried), round(time.monotonic() - t0, 3))


__all__ = ["CandidateVerdict", "PlanOption", "ProposalSelection", "NoValidProposal",
           "NoRealizableProposal", "select_proposal", "pipeline_input"]
