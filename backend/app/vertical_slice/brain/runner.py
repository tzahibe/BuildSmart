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
from app.vertical_slice.brain.area import AREA_TOLERANCE, AreaVerdict, assess_area
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
    area: AreaVerdict | None = None

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
        """The bar from this module's docstring, in one place so no caller can lower it.

        #197 RAISED this bar rather than relaxing it: a plan that misses the requested area by
        more than the stated tolerance, when its own programme could have reached it, no longer
        counts. A brief whose room list cannot fill the footprint at any size is a different
        thing and still counts, carrying the explanation (`AreaVerdict.acceptable`).
        """
        return bool(self.ok and self.bands >= 2
                    and _full(self.spatial_preserved) and _full(self.access_preserved)
                    and (self.area is None or self.area.acceptable))


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


#: Roles that are circulation. `band_pipeline` orients so that SOME allowed-entrance room fronts
#: the street; these are the ones a parti can nominate as the room that RECEIVES arrival.
_CIRC_ROLES = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})
_PUBLIC_ROLES = frozenset({ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN,
                           ProgramRole.FAMILY_ROOM})
_WET_ROLES = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET, ProgramRole.LAUNDRY})
#: With a preference the loop can no longer stop at the first success, so it needs a bigger budget
#: than the plain first-wins path — but every extra candidate is a full realization plus the
#: validators. This number is a LATENCY bound, not a quality one: at 12 the eight audit briefs take
#: 0.9–23.5 s each, and the large ones are already too slow for a live request path. The honest
#: fix is to realize the independent partis in parallel, which has not been done.
MAX_REALIZATIONS_PREFERRED = 12


def _arrival_zone(realized) -> str | None:
    """Which room the realized front door actually opens into."""
    door = getattr(realized, "entrance_door", None)
    if door is None:
        return None
    return next((z for z in (door.a, door.b) if z not in ("ENTRANCE", "OUTSIDE", "")), None)


def _entrance_preference(prop: TopologyProposal, zones: dict, programme: Programme):
    """The parti's own entrance intent, made to decide between candidates (#197).

    THE DEFECT THIS FIXES. Every parti already declared `arrival` — the room its front door should
    open into — and nothing ever read it. `band_pipeline` realized candidates in the embedder's
    plausibility order and returned the first the validators accepted, so the arrival room was
    whatever that candidate happened to put on the street. The #197 render audit measured the
    result: 22 of 23 plans put circulation in an INTERIOR band, where it has no exterior wall at
    all, and all 22 therefore arrived in the living room. The single plan whose hall reached the
    street arrived in the hall. A perfect 1:1 — the entrance regression and the landlocked hall
    were one defect.

    Note what is NOT needed here: `ENTRANCE_ZONE_PRIORITY` already ranks HALL above LIVING, so
    once the hall reaches the street wall the production entrance policy picks it unaided. This
    preference only decides WHICH accepted candidate to keep, and never overrides that policy.

    Lower is better, lexicographically:

      0. the front door opens into the room the parti nominated
      1. the arrival room reaches the street elevation, so it CAN hold a front door
      2. the built area lands within tolerance of what was asked for. This has to be a selection
         criterion and not only a bound, because `solve_band_layout` returns A feasible tiling,
         not the largest one — candidates differed by 70%–87% of the requested area on one brief
         with nothing choosing between them. Coarse (in/out of tolerance) so that it outranks
         ornament without letting a square metre outrank the entrance.
      3. every public room that can be on the garden elevation is (the E1/#186 orientation idea,
         which only ever reached 1 of 8 briefs through the production generator)
      4. closest to the requested area
      5. less floor given to circulation — the audit found 29.6 m² landlocked halls, and that is
         how the good aspect ratio was bought. Ranked BELOW area on purpose: a smaller hall that
         shrinks the whole house is not an improvement, which is the tension the audit missed.
      6. the worst wet-room proportion, because 1.15 x 4.00 m toilets are a visible defect
    """
    intent = prop.arrival
    circ = tuple(z for z, zi in zones.items() if zi.role in _CIRC_ROLES)
    public = tuple(z for z, zi in zones.items() if zi.role in _PUBLIC_ROLES)
    requested = programme.requested_m2 or (programme.footprint_m[0] * programme.footprint_m[1])
    lo, hi = requested * (1 - AREA_TOLERANCE), requested * (1 + AREA_TOLERANCE)

    def prefer(realized, _placement, _inp):
        rects, fp = realized.rects, realized.site.footprint
        south = fp.y + fp.h
        arrived = _arrival_zone(realized)
        target = rects.get(intent)
        gross, _net = _areas(realized)
        circ_area = sum((rects[z].w * rects[z].h) for z in circ if z in rects) * 0.0025
        on_garden = sum(1 for z in public if z in rects and rects[z].y + rects[z].h == south)
        worst_wet = max((max(r.w, r.h) / max(min(r.w, r.h), 1)
                         for z, r in rects.items()
                         if zones.get(z) is not None and zones[z].role in _WET_ROLES), default=0.0)
        return (
            0 if arrived == intent else 1,
            0 if (target is not None and target.y == fp.y) else 1,
            0 if lo <= gross <= hi else 1,
            -on_garden,
            round(abs(gross - requested), 1),
            round(circ_area, 1),
            round(worst_wet, 2),
        )

    return prefer



#: Sizing refusals that mean "the rooms do not fit the footprint under these bounds" — the ones a
#: wider hall can resolve. A representation or access refusal is not one of them and is not retried.
_ROOM_SHORTAGE = ("SIZING_INFEASIBLE", "BAND_GEOMETRY_LIMIT", "SHORT_SIDE_INFEASIBLE",
                  "AREA_INFEASIBLE", "GRID_INFEASIBLE")
#: What the hall may reach on the second attempt. The first attempt's ceiling comes from
#: `programme_from_spec`, which keeps circulation near its target where the rooms can fill the plan.
RELAXED_HALL_CEILING_M2 = 30.0


def _pipeline(prop: TopologyProposal, zones: dict, p: Programme,
              max_candidates: int, max_realizations: int):
    return run_band_pipeline(PipelineInput(
        name=prop.name, zones=zones,
        required_edges=tuple(prop.spatial), footprint_m=p.footprint_m,
        wet_rooms=p.resolved_wet,
        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE")),
        max_candidates=max_candidates, max_realizations=max_realizations,
        prefer=_entrance_preference(prop, zones, p))


def _needs_more_room(out) -> bool:
    return not isinstance(out, PipelineSuccess) and getattr(out, "code", "") in _ROOM_SHORTAGE


def _with_relaxed_hall(zones: dict) -> dict:
    """The same zones with every circulation room's ceiling widened. Nothing else moves — no room
    bound, no validator, no access rule."""
    from dataclasses import replace
    out = dict(zones)
    for zone_id, zi in zones.items():
        if zi.role in _CIRC_ROLES and zi.max_area_m2 < RELAXED_HALL_CEILING_M2:
            out[zone_id] = replace(zi, max_area_m2=RELAXED_HALL_CEILING_M2)
    return out

def run_brain(spec, footprint_m: tuple[float, float], *, brief: str = "brief",
              proposer=None, max_candidates: int = 80,
              max_realizations: int = MAX_REALIZATIONS_PREFERRED) -> BrainResult:
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
    #
    # Twice, when the first attempt dies for want of room. The band grid tiles the footprint
    # exactly, so whatever the rooms' own maxima do not absorb has to go to the hall — the one
    # room here with no template row. #197 capped the hall to stop it reaching 29.6 m² while the
    # master bedroom sat at 13.7, and that cap is right where the programme can fill the plan and
    # fatal where it cannot: B16 went from three plans to one, every loss a SIZING_INFEASIBLE.
    # So: ask for the better-proportioned house first, and widen the hall rather than refuse.
    out = _pipeline(prop, zones, p, max_candidates, max_realizations)
    if _needs_more_room(out):
        out = _pipeline(prop, _with_relaxed_hall(zones), p, max_candidates, max_realizations)
    secs = round(time.monotonic() - t0, 3)
    if not isinstance(out, PipelineSuccess):
        return BrainPlan(prop.name, prop.rationale, False,
                         reason=f"{getattr(out, 'code', '?')}: {str(getattr(out, 'detail', ''))[:110]}",
                         stage=getattr(out, "stage", "PIPELINE"), seconds=secs)
    gross, net = _areas(out.realized)
    requested = p.requested_m2 or (p.footprint_m[0] * p.footprint_m[1])
    return BrainPlan(prop.name, prop.rationale, True, reason="realized",
                     stage="REALIZED", spatial_preserved=out.spatial_preserved,
                     access_preserved=out.access_preserved,
                     bands=len(getattr(out.placement, "bands", ()) or getattr(out.placement, "rows", ())),
                     realized=out.realized, seconds=secs,
                     area=assess_area(requested, gross, net, p.capacity_m2))


def _areas(realized) -> tuple[float, float]:
    """(gross, net) in m², read off `GeometricDesign`, which already computes both.

    They must not be conflated and the first brain report conflated them: GROSS is built area
    including the walls — what a brief's "216 m²" means — and NET is the usable floor inside them,
    7–9 points lower on these briefs. Measuring a gross request against a net result understates
    every plan by that margin, which is a reporting bug, not a design one.
    """
    design = realized.design
    gross = float(getattr(design, "gross_area_m2", 0.0) or 0.0)
    net = float(getattr(design, "net_area_m2", 0.0) or 0.0)
    if not net:
        net = sum(r.w * r.h for r in realized.rects.values()) * 0.0025
    return round(gross or net, 2), round(net, 2)
