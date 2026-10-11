"""brief -> several distinct concepts -> exact geometry, through the UNCHANGED pipeline.

The order is the point. The critic runs BEFORE any placement is attempted (#194 measured 7 of 20
LLM proposals as geometrically unrepresentable, and #160 spent its whole budget trying to place
three of them). Then the existing band pipeline does embedding, exact sizing, non-guillotine
realization and the unchanged validators, and reports preservation of the requested graph.

A plan counts only if ALL of these hold — this is the "not merely validator success" bar:

    critic-clean BEFORE placement · realizes · every unchanged validator passes
    · spatial preserved n/n · access preserved n/n · bands >= 2 (a row collapse is a FAIL)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.vertical_slice.band_pipeline import PipelineInput, PipelineSuccess, run_band_pipeline
from app.vertical_slice.brain.proposer import (DeterministicProposer, Programme, TopologyProposal,
                                               programme_from_spec)
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.proposal_critic import Proposal, criticize


@dataclass
class BrainPlan:
    """One concept carried all the way to geometry, with the facts that decide whether it counts."""

    parti: str
    rationale: str
    ok: bool
    reason: str = ""
    stage: str = ""
    spatial_preserved: str = ""
    access_preserved: str = ""
    bands: int = 0
    realized: object = None
    seconds: float = 0.0
    critic_findings: tuple = ()

    @property
    def geometry_signature(self) -> tuple:
        """What the drawing actually is: every room's rounded rectangle. Two plans with the same
        signature ARE the same plan, whatever concept produced them."""
        if self.realized is None:
            return ()
        return tuple(sorted(
            (z, round(r.x, 2), round(r.y, 2), round(r.w, 2), round(r.h, 2))
            for z, r in self.realized.rects.items()))

    @property
    def counts(self) -> bool:
        """The bar from this module's docstring, in one place so no caller can lower it."""
        return bool(self.ok and self.bands >= 2
                    and _full(self.spatial_preserved) and _full(self.access_preserved))


def _full(ratio: str) -> bool:
    if not ratio or "/" not in ratio:
        return False
    got, want = ratio.split("/", 1)
    return got == want


@dataclass
class BrainResult:
    brief: str
    plans: list[BrainPlan] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def accepted(self) -> list[BrainPlan]:
        return [p for p in self.plans if p.counts]

    @property
    def distinct(self) -> list[BrainPlan]:
        """Accepted plans with duplicate GEOMETRY removed, first parti wins.

        Two partis can converge legitimately — on a brief with only two public rooms, "every
        public room meets the hall" and "the public rooms chain off its head" describe the same
        contacts. Offering the owner the same drawing twice under two names would be exactly the
        fake diversity this work exists to avoid, so distinctness is decided on the REALIZED
        rectangles, never on the parti's name.
        """
        out, seen = [], set()
        for plan in self.accepted:
            sig = plan.geometry_signature
            if sig in seen:
                continue
            seen.add(sig)
            out.append(plan)
        return out


def run_brain(spec, footprint_m: tuple[float, float], *, brief: str = "brief",
              proposer=None, max_candidates: int = 150,
              max_realizations: int = 6) -> BrainResult:
    t0 = time.monotonic()
    programme = programme_from_spec(spec, footprint_m)
    proposals = (proposer or DeterministicProposer()).propose(programme)
    result = BrainResult(brief=brief)
    for prop in proposals:
        result.plans.append(_one(prop, programme, max_candidates, max_realizations))
    result.seconds = round(time.monotonic() - t0, 3)
    return result


def _one(prop: TopologyProposal, p: Programme, max_candidates: int,
         max_realizations: int) -> BrainPlan:
    t0 = time.monotonic()
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    missing = [z for z in prop.rooms if z not in p.zones]
    if missing:
        from app.vertical_slice.brain.proposer import _hall_intent
        for z in missing:                               # a parti's own second corridor
            zones[z] = _hall_intent(z, target=7.0)

    roles = {z: zones[z].role for z in zones}
    # 1. THE CRITIC, BEFORE ANY PLACEMENT.
    report = criticize(Proposal(
        name=prop.name, roles=roles,
        spatial=frozenset(frozenset(e) for e in prop.spatial),
        access=tuple(prop.access), zones=zones, wet_rooms=p.wet_rooms))
    hard = tuple(f for f in report.findings if getattr(f, "severity", "") == "HARD")
    if hard:
        return BrainPlan(prop.name, prop.rationale, False,
                         reason="; ".join(f"{f.code}: {f.detail[:90]}" for f in hard[:3]),
                         stage="CRITIC", seconds=round(time.monotonic() - t0, 3),
                         critic_findings=tuple(f.code for f in hard))

    # 2. the UNCHANGED pipeline: embedding -> sizing -> realization -> validators -> preservation.
    out = run_band_pipeline(PipelineInput(
        name=prop.name, zones=zones,
        required_edges=tuple(prop.spatial), footprint_m=p.footprint_m,
        wet_rooms=p.resolved_wet,
        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE")),
        max_candidates=max_candidates, max_realizations=max_realizations)
    secs = round(time.monotonic() - t0, 3)
    if not isinstance(out, PipelineSuccess):
        return BrainPlan(prop.name, prop.rationale, False,
                         reason=f"{getattr(out, 'code', '?')}: {str(getattr(out, 'detail', ''))[:110]}",
                         stage=getattr(out, "stage", "PIPELINE"), seconds=secs)
    return BrainPlan(prop.name, prop.rationale, True, reason="realized",
                     stage="REALIZED", spatial_preserved=out.spatial_preserved,
                     access_preserved=out.access_preserved,
                     bands=len(getattr(out.placement, "bands", ()) or getattr(out.placement, "rows", ())),
                     realized=out.realized, seconds=secs)
