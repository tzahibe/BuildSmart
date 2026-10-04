"""Production proposal SELECTION — critic first, then score, then select, then realize (Issue #142J).

    brief -> candidate proposals -> CRITIC -> keep the clean ones -> score/rank -> select -> realizer

A candidate with a HARD finding is never eligible while a clean candidate exists, whatever its
heuristic score. Nothing is repaired. When every candidate has a HARD finding the result is a typed
`NoValidProposal` carrying every candidate's findings (for controlled regeneration later) — never the
least-bad invalid proposal. Clean candidates are tried in score order (ties by index) until the
unchanged production pipeline realizes and validates one; if none does, `NoRealizableProposal`
carries the per-candidate typed diagnoses. Everything here is deterministic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .band_pipeline import PipelineDiagnosis, PipelineInput, PipelineSuccess, run_band_pipeline
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
class ProposalSelection:
    proposal: Proposal
    index: int                     # index in the candidate list
    score: float
    clean_rank: int                # rank among clean candidates by score (0 = best)
    verdicts: list
    pipeline: PipelineSuccess
    tried: list = field(default_factory=list)      # (index, outcome code) for clean candidates tried before
    seconds: float = 0.0


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
    for rank, v in enumerate(ordered[: max_realizations or len(ordered)]):
        p = candidates[v.index]
        res = run_band_pipeline(pipeline_input(p, v.report, footprint_m))
        if isinstance(res, PipelineSuccess):
            return ProposalSelection(p, v.index, v.score, rank, verdicts, res,
                                     [(i, d.code) for i, d in tried], round(time.monotonic() - t0, 3))
        tried.append((v.index, res))
    return NoRealizableProposal("NO_REALIZABLE_PROPOSAL", verdicts, tried,
                                f"{len(clean)} critic-clean candidate(s), none realized: " +
                                ", ".join(f"#{i} {d.code}" for i, d in tried), round(time.monotonic() - t0, 3))


__all__ = ["CandidateVerdict", "ProposalSelection", "NoValidProposal", "NoRealizableProposal", "select_proposal", "pipeline_input"]
