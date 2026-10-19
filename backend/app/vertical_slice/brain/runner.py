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

from app.vertical_slice.band_pipeline import (
    PipelineInput,
    PipelineSuccess,
    run_band_pipeline,
)
from app.vertical_slice.brain.area import AREA_TOLERANCE, AreaVerdict, assess_area
from app.vertical_slice.brain.proposer import (
    AREA_BAND,
    HALL_CEILING_M2,
    DeterministicProposer,
    Programme,
    TopologyProposal,
    band_around,
    programme_from_spec,
)
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
    #: which sizer made the plan ("production" | "exact") and which family of layout
    sizer: str = "production"
    family: str = "band"
    notes: tuple = ()
    #: the brain's preference key for this plan (`_plan_key`), set by `run_brain` so partis can be
    #: ranked against each other; `None` for a plan that did not realize
    rank_key: tuple | None = None
    #: Which rung of `AREA_BAND_LADDER` produced this plan. `None` means the last rung — the full
    #: template range — so a loosely-proportioned result is visible rather than silently equal to
    #: a tight one.
    area_band: float | None = AREA_BAND

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

        The order is the brain's own preference (`BrainPlan.rank_key`, best first — the same key
        that chose between candidates inside each parti), so the primary the product shows is the
        best plan the brain made and not the first parti the proposer happened to list. Plans
        without a key keep their arrival order after the ranked ones.
        """
        out, seen = [], set()
        ranked = sorted(self.accepted, key=lambda pl: (pl.rank_key is None, pl.rank_key or ()))
        for plan in ranked:
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


#: Which preference `run_brain` hands the pipeline (#197, owner item 2 — 2026-10-14):
#: "entrance" is the preference above; "proportion" adds, BELOW its three hard-priority keys and
#: ABOVE its ornament keys, the two measures the frozen-six work showed a plan is judged by —
#: how far the rooms sit from their targets and how much floor circulation takes. Evaluated on the
#: same candidate pool before it is made the default; see `proportion_metrics`.
SELECTION = "proportion"


def proportion_metrics(realized, zones: dict) -> tuple[float, float]:
    """(mean relative |net - target| over habitable rooms in %, circulation share of net in %),
    read off the realized design — the two numbers `_proportion_preference` ranks by."""
    devs, circ_net, total = [], 0.0, 0.0
    for r in realized.design.rooms:
        zi = zones.get(r.zone_id)
        total += r.net_area_m2
        if zi is None:
            continue
        if zi.role in _CIRC_ROLES:
            circ_net += r.net_area_m2
        elif zi.target_area_m2 > 0:
            devs.append(abs(r.net_area_m2 - zi.target_area_m2) / zi.target_area_m2)
    return (100.0 * sum(devs) / len(devs) if devs else 0.0, 100.0 * circ_net / total if total else 0.0)


def _proportion_preference(prop: TopologyProposal, zones: dict, programme: Programme):
    """`_entrance_preference` with proportion decided before ornament (owner item 2):

      0-2. unchanged — the parti's arrival room, the street elevation, the area tolerance. These are
           the architectural priorities and a proportion never outranks them.
      3. mean relative deviation of the habitable rooms from their targets (whole per cent)
      4. circulation's share of the net floor (whole per cent)
      5-7. unchanged — garden elevation, closest area, worst wet-room proportion.

    Hard constraints are not in play here at all: the pipeline only ever offers candidates the
    validators accepted, so no key of this function can trade one away."""
    base = _entrance_preference(prop, zones, programme)

    def prefer(realized, placement, inp):
        k = base(realized, placement, inp)
        dev, circ = proportion_metrics(realized, zones)
        return k[:3] + (round(dev), round(circ)) + k[3:]

    return prefer


def _preference(prop: TopologyProposal, zones: dict, programme: Programme):
    return (_proportion_preference if SELECTION == "proportion" else _entrance_preference)(prop, zones, programme)



#: Sizing refusals that mean "the rooms do not fit the footprint under these bounds" — the ones a
#: wider area band can resolve. A representation or access refusal is not one of them and is never
#: retried: no amount of extra room makes a K4 placeable.
_ROOM_SHORTAGE = ("SIZING_INFEASIBLE", "BAND_GEOMETRY_LIMIT", "SHORT_SIDE_INFEASIBLE",
                  "AREA_INFEASIBLE", "GRID_INFEASIBLE")

#: The widening ladder (#197 Stage 3). Each rung is how far a room may sit from its own fair share
#: of the floor; `None` is the full template range, which is exactly the behaviour that existed
#: before this change.
#:
#: Tight first, because that is what stops circulation hoarding the surplus. But a tight band can
#: make a brief unplannable — Stage 2 capped the hall alone and took B16 from three plans to one,
#: every loss a `SIZING_INFEASIBLE` — so feasibility is never traded for proportion: the ladder
#: loosens until the brief plans, and the last rung guarantees nothing that planned before stops
#: planning. The rung that succeeded is recorded on the plan, so a loose result is visible rather
#: than silently equivalent to a tight one.
AREA_BAND_LADDER: tuple[float | None, ...] = (0.15, 0.30, 0.50, None)

#: A parti's second corridor serves a bedroom wing, not a whole house, so it aims small.
SECOND_CORRIDOR_TARGET_M2 = 7.0


def _pipeline(prop: TopologyProposal, zones: dict, p: Programme,
              max_candidates: int, max_realizations: int):
    return run_band_pipeline(PipelineInput(
        name=prop.name, zones=zones,
        required_edges=tuple(prop.spatial), footprint_m=p.footprint_m,
        wet_rooms=p.resolved_wet,
        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE")),
        max_candidates=max_candidates, max_realizations=max_realizations,
        prefer=_preference(prop, zones, p))


def _needs_more_room(out) -> bool:
    return not isinstance(out, PipelineSuccess) and getattr(out, "code", "") in _ROOM_SHORTAGE


def _rebanded(zones: dict, p: Programme, frac: float | None) -> dict:
    """The same zones with every room's area band re-cut at `frac` around its own target.

    Nothing else moves — no validator, no access rule, no short side, no aspect ratio — and every
    band stays inside the room's own template range (`Programme.full_bounds`), so a wider rung can
    never allow a size the template did not already allow.
    """
    from dataclasses import replace

    out = dict(zones)
    for zone_id, zi in zones.items():
        # A parti's own second corridor is created here rather than in `programme_from_spec`, so it
        # has no `full_bounds` entry. Falling back to its CURRENT band would let the ladder re-cut
        # a band against itself and widen nothing, so fall back to the hall's outer clamp instead.
        default = ((4.0, HALL_CEILING_M2) if zi.role in _CIRC_ROLES
                   else (zi.min_area_m2, zi.max_area_m2))
        floor, ceiling = p.full_bounds.get(zone_id, default)
        lo, hi = band_around(zi.target_area_m2, frac, floor, ceiling)
        out[zone_id] = replace(zi, min_area_m2=lo, max_area_m2=hi)
    return out

#: `run_brain(sizer=...)` (#197 item 4): "production" is `band_pipeline`'s own sizer, exactly as
#: before; "exact" is the MILP placement with the target objective and, with `families`, the
#: cross-band layouts measured on the frozen six. The exact path falls back to production, typed,
#: when scipy is missing or every solve times out — the plan then says which sizer made it.
SIZER_PRODUCTION, SIZER_EXACT = "production", "exact"
#: one wall-clock budget per request, shared by every parti
REQUEST_BUDGET_S = 30.0
#: How many partis the exact sizer is spent on per request (#197, 2026-10-16). The first preview
#: shared the budget equally across every parti — 30 s / 8 partis — and on the 10–14-room briefs
#: every exact solve timed out inside its 3–4 s share, so the request fell back to production AND
#: took 38–43 s. Measured before this was chosen: a cheap unaligned MILP probe does NOT predict
#: which parti the exact sizer makes the best plan from (B02: probe 0.2 % -> 21.6 % realized,
#: probe 0.3 % -> 1.2 %), and on B16/B19 the exact band placement is INFEASIBLE for every parti,
#: so no ranking can buy a plan there. What does rank is production's own plan for the parti — it
#: is the fallback anyway, costs 0.2–6 s per brief on the briefs the exact sizer can improve, and
#: yields the same preference key the exact plan is judged by. So: production sizes every parti
#: first, the partis are ranked by that key, and the exact sizer gets the WHOLE remaining budget
#: for the top few — a plan is replaced only when the exact one ranks at least as well, so the
#: exact sizer can improve a parti and never worsen one (B20 was the case it worsened).
EXACT_TOP = 3
#: after the top partis, a further parti is sized exactly only if at least this much budget is left
EXACT_EXTRA_MIN_S = 5.0


def run_brain(spec, footprint_m: tuple[float, float], *, brief: str = "brief",
              proposer=None, max_candidates: int = 80,
              max_realizations: int = MAX_REALIZATIONS_PREFERRED,
              sizer: str = SIZER_PRODUCTION, families: tuple[str, ...] = ("band",),
              budget_s: float = REQUEST_BUDGET_S, exact_top: int = EXACT_TOP) -> BrainResult:
    t0 = time.monotonic()
    programme = programme_from_spec(spec, footprint_m)
    proposals = (proposer or DeterministicProposer()).propose(programme)
    result = BrainResult(brief=brief)
    deadline = t0 + budget_s
    # 1. production sizes every parti — the ranking, and the plan the exact sizer must beat
    for prop in proposals:
        result.plans.append(_one(prop, programme, max_candidates, max_realizations))
    _rank(result, proposals, programme)
    if sizer == SIZER_EXACT:
        _improve_exactly(result, proposals, programme, max_candidates, max_realizations,
                         families=families, deadline=deadline, top=exact_top)
        _rank(result, proposals, programme)
    result.seconds = round(time.monotonic() - t0, 3)
    return result


def _rank(result: BrainResult, proposals, p: Programme) -> None:
    for plan, prop in zip(result.plans, proposals):
        plan.rank_key = _plan_key(plan, prop, p) if plan.realized is not None else None


def _plan_key(plan: BrainPlan, prop: TopologyProposal, p: Programme):
    """The brain's own preference, read off a finished plan, so a production plan and an exact
    plan of the same parti compare on the one scale the pipeline already ranks candidates by."""
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    return _preference(prop, zones, p)(plan.realized, None, None)


def _key_text(key: tuple) -> str:
    """The first five keys of a preference, named, for a plan's notes."""
    arrived, street, area, dev, circ = key[:5]
    return (f"arrival {'ok' if arrived == 0 else 'NOT the parti`s'}, street {'ok' if street == 0 else 'no'}, "
            f"area {'in' if area == 0 else 'out of'} tolerance, rooms {dev} %, circulation {circ} %")


def _improve_exactly(result: BrainResult, proposals, p: Programme, max_candidates: int,
                     max_realizations: int, *, families, deadline: float, top: int) -> None:
    """2. the exact sizer, on the best-ranked partis, with the whole remaining budget.

    Order: partis production planned, best preference key first; then partis production could not
    plan (the exact placement is the stronger sizer and may plan what the heuristic could not).
    Each gets an equal share of what is left. The exact plan replaces production's only when it
    counts and its key is no worse; otherwise the production plan stays and says why."""
    ranked = sorted((i for i, pl in enumerate(result.plans) if pl.counts),
                    key=lambda i: result.plans[i].rank_key)
    ranked += [i for i, pl in enumerate(result.plans) if not pl.counts and pl.stage != "CRITIC"]
    for n, i in enumerate(ranked):
        remaining = deadline - time.monotonic()
        if n < top:
            share = remaining / (top - n)             # the top partis divide the budget
        elif remaining >= EXACT_EXTRA_MIN_S:
            share = remaining                         # a small brief finished early: keep improving
        else:
            break
        if share <= 0:
            break
        prod, prop = result.plans[i], proposals[i]
        exact = _one(prop, p, max_candidates, max_realizations, sizer=SIZER_EXACT, families=families,
                     deadline=time.monotonic() + share, fallback=False)
        if exact.sizer != SIZER_EXACT:
            # typed: unavailable (no scipy), every solve timed out, or nothing kept
            prod.notes = (*prod.notes, *exact.notes)
            if exact.stage == "UNAVAILABLE":
                for other in result.plans:
                    if other is not prod and other.stage != "CRITIC":
                        other.notes = (*other.notes, *exact.notes)
                return
            continue
        if not exact.counts:
            why = "area" if exact.area and not exact.area.acceptable else "preservation"
            prod.notes = (*prod.notes, f"exact sizer's {exact.family} plan did not count ({why}); production kept")
            continue
        ek, pk = _plan_key(exact, prop, p), _plan_key(prod, prop, p)
        if prod.counts and ek > pk:
            prod.notes = (*prod.notes, (f"exact sizer's {exact.family} plan ranked below production's "
                                        f"({_key_text(ek)} vs {_key_text(pk)}); production kept"))
            continue
        exact.notes = (*exact.notes, "exact sizer improved on production's plan" if prod.counts
                       else f"exact sizer planned what production could not ({prod.reason[:60]})")
        exact.seconds = round(exact.seconds + prod.seconds, 3)
        result.plans[i] = exact


def _one(prop: TopologyProposal, p: Programme, max_candidates: int,
         max_realizations: int, *, sizer: str = SIZER_PRODUCTION, families: tuple[str, ...] = ("band",),
         deadline: float | None = None, fallback: bool = True) -> BrainPlan:
    """One parti to geometry. `fallback=False` returns the exact sizer's refusal as a plan that did
    not realize (stage UNAVAILABLE / SIZING ...) instead of running the production sizer after it —
    `_improve_exactly` already holds production's plan for that parti."""
    t0 = time.monotonic()
    zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
    missing = [z for z in prop.rooms if z not in p.zones]
    if missing:
        from app.vertical_slice.brain.proposer import _hall_intent
        # A parti's own second corridor. It is BANDED like every other room — left at the default
        # 4–30 m² it becomes the loosest-bounded zone in the programme and inherits exactly the
        # job the hall used to do: on B09 TWO_HALL it absorbed the surplus to 48.7 m² of total
        # circulation while every other room sat tight at its fair share (#197 Stage 3).
        for z in missing:
            lo, hi = band_around(SECOND_CORRIDOR_TARGET_M2, AREA_BAND, 4.0, HALL_CEILING_M2)
            zones[z] = _hall_intent(z, target=SECOND_CORRIDOR_TARGET_M2, floor=lo, ceiling=hi)

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
    # Once per rung of the widening ladder, stopping at the first rung that plans. The grid tiles
    # the footprint exactly, so the surplus the rooms' own bands do not absorb has to go somewhere;
    # the tight rung spreads it across the programme, and each looser rung trades proportion for
    # feasibility only when the tighter one could not plan at all.
    band = AREA_BAND_LADDER[0]
    made_by, family, notes = SIZER_PRODUCTION, "band", ()
    out = None
    if sizer == SIZER_EXACT:
        from app.vertical_slice.brain.exact_pipeline import run_exact_pipeline
        out = run_exact_pipeline(
            PipelineInput(name=prop.name, zones=zones, required_edges=tuple(prop.spatial),
                          footprint_m=p.footprint_m, wet_rooms=p.resolved_wet,
                          access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE"),
                          open_groups=(p.open_group,) if p.open_group else ()),
            prefer=_preference(prop, zones, p), ladder=AREA_BAND_LADDER,
            rebanded=lambda zs, rung: _rebanded(zs, p, rung), families=families, deadline=deadline,
            arrival=prop.arrival)
        if isinstance(out, PipelineSuccess):
            made_by, family = SIZER_EXACT, getattr(out.placement, "family", "band")
            band = None
            notes = out.warnings
        else:
            # typed fallback: the preview never loses a parti production can plan. The reason the
            # exact path gave up (no solver, every solve timed out, or nothing kept within the
            # budget) travels with the plan.
            code = getattr(out, 'code', '?')
            notes = (f"exact sizer fell back to production: {code}: {str(getattr(out, 'detail', ''))[:80]}",)
            if not fallback:
                return BrainPlan(prop.name, prop.rationale, False, reason=f"{code}: {str(getattr(out, 'detail', ''))[:110]}",
                                 stage="UNAVAILABLE" if code == "EXACT_SIZER_UNAVAILABLE" else getattr(out, "stage", "SIZING"),
                                 seconds=round(time.monotonic() - t0, 3), sizer=SIZER_PRODUCTION, notes=notes)
            out = None
    if out is None:
        out = _pipeline(prop, zones, p, max_candidates, max_realizations)
        for rung in AREA_BAND_LADDER[1:]:
            if not _needs_more_room(out):
                break
            band = rung
            out = _pipeline(prop, _rebanded(zones, p, rung), p, max_candidates, max_realizations)
    secs = round(time.monotonic() - t0, 3)
    if not isinstance(out, PipelineSuccess):
        return BrainPlan(prop.name, prop.rationale, False,
                         reason=f"{getattr(out, 'code', '?')}: {str(getattr(out, 'detail', ''))[:110]}",
                         stage=getattr(out, "stage", "PIPELINE"), seconds=secs, sizer=made_by, notes=tuple(notes))
    gross, net = _areas(out.realized)
    requested = p.requested_m2 or (p.footprint_m[0] * p.footprint_m[1])
    # OPEN PLAN, DISCLOSED (Issue #221). The brief asked for it and the delivered plan does not
    # have it: either the production sizer realized this parti (`realize_layout` cannot express a
    # join between two different zones) or the placement left no member pair fully adjacent, in
    # which case `realize_cells` already said which pair and why. Never silent.
    if p.open_group and not getattr(out.realized.design, "open_groups", ()):
        notes = (*notes, "open plan was requested and is NOT expressed in this plan: "
                         f"{'/'.join(p.open_group)} are walled"
                         + (f" (the {made_by} sizer cannot type an interface OPEN)"
                            if made_by == SIZER_PRODUCTION else ""))
    return BrainPlan(prop.name, prop.rationale, True, reason="realized",
                     stage="REALIZED", spatial_preserved=out.spatial_preserved,
                     access_preserved=out.access_preserved,
                     bands=len(getattr(out.placement, "bands", ()) or getattr(out.placement, "rows", ())),
                     realized=out.realized, seconds=secs, area_band=band,
                     area=assess_area(requested, gross, net, p.capacity_m2),
                     sizer=made_by, family=family, notes=tuple(notes))


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
