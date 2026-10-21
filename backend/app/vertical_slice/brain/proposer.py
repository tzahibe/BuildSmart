"""Deterministic topology proposers — several ARCHITECTURALLY DISTINCT graphs per brief.

WHY THIS EXISTS (Issue #197, grounded in #194's audit). The brain chain on `main` works, but its
only proposal source was an LLM: ~$0.12 and ~90 s per brief, an external dependency and a
nondeterministic result on the critical path. A product cannot be defined by that. So the proposer
becomes an INTERFACE with several implementations, and the primary one is deterministic.

Each proposer emits exactly what `proposal_critic` and `band_pipeline` already consume — an
undirected spatial-adjacency graph plus directed access (door) edges over the brief's own room
programme — so nothing downstream had to change to accept them.

WHAT MAKES THE GRAPHS DIFFERENT, AND WHY THEY ARE REPRESENTABLE. Every parti below is a TREE of
contacts (a hub, or two hubs joined) optionally plus ONE path through the public rooms. That is a
deliberate constraint, not an accident:

  * a tree plus one path contains no K4 and no triple-lens, the two obstructions `band_embedding`
    refuses on (#194 measured 7 of 20 LLM proposals failing exactly there);
  * bedrooms touch ONLY their circulation node and their own ensuite. The moment a bedroom is also
    required to touch LIVING, three such bedrooms create a triple-lens — "a straight wall has only
    two sides" — and no rectangle layout exists. The LLM did that repeatedly; this cannot.

So these proposals are representable BY CONSTRUCTION, and the critic in front of the pipeline is a
check rather than a filter that throws most candidates away.

Access legality is likewise built in, not hoped for: a bedroom is entered only from circulation, an
ensuite only from its host bedroom, a shared wet room only from circulation, and the public rooms
form a chain from the arrival room — which is what `access_rules.ALLOWED_ENTERED_FROM` permits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from app.vertical_slice.concept_generator import (ASSUMED_EFFICIENCY, ZoneGroup,
                                                   build_room_program,
                                                   program_capacity_gross_m2, scale_program)
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.stage2.contract import ZoneIntent
from app.vertical_slice.wet_rooms import ResolvedWetRoom

_WET_ROLES = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET, ProgramRole.LAUNDRY})

#: The circulation node every parti has at least one of.
HALL = "HALL"
#: The second circulation node of the two-hall partis.
HALL_B = "HALL_B"
#: The entry foyer (Issue #197). A SEPARATE room from the hall, of degree 2 — street and hall —
#: because that degree is the whole point: the hall is a hub (it touches every bedroom, every
#: shared wet room and a public room), and in a band layout a hub has to sit in a middle band to
#: reach the bands above and below it. A middle band has no exterior wall, so the hall cannot hold
#: the front door however much the entrance policy would like it to. The #197 audit measured the
#: consequence: 22 of 23 plans arrived in the living room. A degree-2 foyer places trivially in the
#: street band, takes the front door (CIRCULATION outranks LIVING in `ENTRANCE_ZONE_PRIORITY`),
#: gets a window, and gives the plan the arrival sequence it did not have: street -> foyer -> hall.
ENTRY = "ENTRY"
#: Below this much net floor a foyer is a room the brief cannot spare; the parti is offered
#: without one and the plan arrives in a public room, which is honest for a small house.
FOYER_MIN_NET_M2 = 85.0

#: How far a room may sit from its own fair share of the available floor, on the FIRST attempt.
#:
#: THE DEFECT THIS EXISTS FOR (#197 Stage 3). `band_sizing` constrains each cell to
#: `net_area in [min_area, max_area]` and has NO target — it finds *a* feasible tiling, not a good
#: one. The grid tiles the footprint exactly, so surplus area must land somewhere, and it lands in
#: whichever room has the loosest bounds. That was the hall, which has no template row at all.
#: Measured on B11: accepted candidates ranged over 70%–87% of the requested area with nothing
#: choosing between them, and the difference pooled in circulation — the 20–30 m² landlocked halls
#: and the 12.5 × 1.6 m corridor. Those are an ALLOCATION defect showing up in the hall, which is
#: why capping the hall was the wrong fix: it took B16 from three plans to one.
#:
#: `scale_program` already computes each room's fair share. Banding the bounds around that share
#: makes the surplus distribute across the programme instead of pooling. The band is always
#: intersected with the room's own template range, so this only ever NARROWS what was allowed.
AREA_BAND = 0.15

#: The proportion limits the brain asks for, over and above each room's template.
#:
#: Area banding alone does not fix shape: a 20 m² hall can still be 12.5 x 1.6 m, which is the
#: corridor the #197 audit named, and `_hall_intent` was asking for `max_aspect_ratio=8.0` — it was
#: ALLOWED. These are intents, not validator changes: they only ever narrow what the brain asks
#: for, inside the template's own limits, and the widening ladder relaxes them toward the template
#: when a brief cannot otherwise plan.
HALL_MAX_ASPECT = 3.0
HALL_MIN_SHORT_SIDE_M = 1.6
#: 1.25 x 3.90 m is a corridor with a WC in it, not a toilet. Template limits allow it; the brain
#: does not ask for it.
WET_MAX_ASPECT = 2.2
WET_MIN_SHORT_SIDE_M = 1.6


@dataclass(frozen=True)
class TopologyProposal:
    """One architectural concept, before any geometry exists."""

    name: str                                   # the parti's own name, shown to the owner
    rationale: str                              # one line: what this concept IS, architecturally
    spatial: tuple[tuple[str, str], ...]        # undirected required contacts
    access: tuple[tuple[str, str], ...]         # directed doors; "ENTRANCE" allowed as a source
    arrival: str                                # the room the front door opens into

    @property
    def rooms(self) -> tuple[str, ...]:
        seen: list[str] = []
        for a, b in self.spatial:
            for z in (a, b):
                if z not in seen:
                    seen.append(z)
        return tuple(seen)


class Proposer(Protocol):
    """Anything that can turn a room programme into concepts. The LLM is one of these, not THE one."""

    name: str

    def propose(self, programme: "Programme") -> list[TopologyProposal]: ...


@dataclass(frozen=True)
class Programme:
    """The brief's own rooms, grouped the way a parti needs to reason about them."""

    public: tuple[str, ...]            # LIVING / DINING / KITCHEN …, in chain order
    bedrooms: tuple[str, ...]          # MASTER first, then BEDROOM_n
    ensuites: dict[str, str]           # wet zone -> its host bedroom
    shared_wet: tuple[str, ...]        # wet rooms entered from circulation
    safe_room: str | None
    zones: dict[str, ZoneIntent]
    #: The BRIEF's own declared wet-room kinds (`spec.WetRoomRequirement`) — what the critic's
    #: I4b checks the proposal against. NOT `ResolvedWetRoom`, which is the programme's resolved
    #: form and carries `host_zone` rather than the brief's `host` spec.
    wet_rooms: tuple
    footprint_m: tuple[float, float]
    #: the resolved form, for the realizer's own C17/C29
    resolved_wet: tuple[ResolvedWetRoom, ...] = ()
    #: usable floor the programme was scaled against — what decides whether a foyer is affordable
    net_available_m2: float = 0.0
    #: The largest house this room list can responsibly fill — PRODUCTION's own
    #: `program_capacity_gross_m2(hard=True)`, not a second opinion about it. The #197 audit traced
    #: the "53% area fidelity" headline to this number rather than to any sizing bug: B09 asks for
    #: 440 m² from a programme that tops out well below it, so no layout — production's or the
    #: brain's — can fill the footprint. Production already DISCLOSES this to the customer
    #: (`capacity_notice_text`); what the brain adds is that it also GATES on it, and that it can
    #: tell this case apart from a layout that simply fell short.
    capacity_m2: float = 0.0
    #: Every room's FULL template range, so the widening ladder has something to relax toward
    #: without re-deriving template bounds outside this module.
    full_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    #: The BRIEF's own requested built area (`spec.program.target_built_area_m2`) — NOT the
    #: footprint the brain was handed. They differ: production chooses an outline before the brain
    #: runs, and on one unseen brief that outline was 21% larger than the request, so measuring
    #: against the footprint reported a plan as over-delivering when it was the outline that grew.
    #: Fidelity is owed to what the customer asked for.
    requested_m2: float = 0.0

    @property
    def affords_foyer(self) -> bool:
        return self.net_available_m2 >= FOYER_MIN_NET_M2

    #: The brief's multi-purpose room, when it has one. PRODUCTION's own device for the area a
    #: named room list cannot absorb — on the three briefs whose programme underfills the
    #: footprint it carries 54.3 m² (B09), 27.6 (B06) and 14.3 (B02), which is most of the gap
    #: between production and a brain that dropped FLEX on the floor. Treated here as what it is:
    #: a spare room off the circulation, like a bedroom without a bed.
    flex: tuple[str, ...] = ()
    #: The BRIEF's own `ProgramSpec.open_plan_living` (Issue #221) — the same bit production reads
    #: to compile its open group. Carried here so the parti and the realizer can express it;
    #: nothing in the brain's own proposing or ranking reads it.
    open_plan: bool = False

    @property
    def private(self) -> tuple[str, ...]:
        return self.bedrooms + ((self.safe_room,) if self.safe_room else ()) + self.flex

    @property
    def open_group(self) -> tuple[str, ...]:
        """The one open-plan group this brief asks for, by the brief's OWN semantics — the public
        chain, when the brief asked for open-plan living and there is more than one public room.

        This is production's rule (`concept_generator._build_access`: `groups.append(tuple(
        public_ids))` under `open_plan and len(public_ids) > 1`), applied to the brain's own
        `public`. No room is named here: the group is whatever `programme_from_spec` put in the
        public chain (LIVING/DINING/KITCHEN on today's briefs). It differs from production's list
        in one documented way — the brain treats FLEX as a spare room off the circulation
        (`private` above), so a FLEX room never joins the open group."""
        return tuple(self.public) if self.open_plan and len(self.public) > 1 else ()


def programme_from_spec(spec, footprint_m: tuple[float, float]) -> Programme:
    """The brief's `ArchitecturalSpec` -> `Programme`, using production's OWN room builder so the
    brain plans the same rooms the product would."""
    rooms = build_room_program(spec)
    by_id = {r.zone_id: r for r in rooms}
    public, bedrooms, shared_wet, flex = [], [], [], []
    ensuites: dict[str, str] = {}
    safe_room = None
    for r in rooms:
        if r.role is ProgramRole.FLEX:
            flex.append(r.zone_id)
        elif r.role is ProgramRole.SAFE_ROOM:
            safe_room = r.zone_id
        elif r.group is ZoneGroup.PUBLIC and r.role is not ProgramRole.FLEX:
            public.append(r.zone_id)
        elif r.role in (ProgramRole.MASTER_BEDROOM, ProgramRole.BEDROOM):
            bedrooms.append(r.zone_id)
        elif r.wet is not None or r.group is ZoneGroup.SERVICE:
            if r.entered_from:
                ensuites[r.zone_id] = r.entered_from
            else:
                shared_wet.append(r.zone_id)
    # MASTER first so a parti that gives one bedroom a privileged position gives it to the master.
    bedrooms.sort(key=lambda z: (by_id[z].role is not ProgramRole.MASTER_BEDROOM, z))

    # AREA FIDELITY. Sizing every room at its template target ignores what the person asked for:
    # measured on the eight audit briefs, that delivered 78 m2 against a 216 m2 request (B02) and
    # 98 against 440 (B09). Production does not do that — it scales the programme to the area
    # actually available (`scale_program`, distributing surplus by each room's own elasticity and
    # capping at its own maximum), and the brain now uses the SAME function rather than a second
    # opinion about room sizes.
    net_available = (footprint_m[0] * footprint_m[1]) * ASSUMED_EFFICIENCY
    planned = list(rooms)
    scaled = scale_program(planned, net_available)

    zones: dict[str, ZoneIntent] = {}
    full_bounds: dict[str, tuple[float, float]] = {}
    for r in planned:
        t = r.template
        spec_for_room = scaled.get(r.zone_id)
        target = spec_for_room.net_area_target_m2 if spec_for_room else t.target_area_m2
        ceiling = t.hard_max_area_m2 or t.max_area_m2
        target = round(max(t.min_area_m2, min(target, ceiling)), 2)
        full_bounds[r.zone_id] = (t.min_area_m2, ceiling)
        lo, hi = band_around(target, AREA_BAND, t.min_area_m2, ceiling)
        short, aspect = t.min_short_side_m, t.max_aspect_ratio
        if r.role in _WET_ROLES:
            short = max(short, WET_MIN_SHORT_SIDE_M)
            aspect = min(aspect, WET_MAX_ASPECT)
        zones[r.zone_id] = ZoneIntent(
            zone_id=r.zone_id, role=r.role, donor_room_id=None,
            target_area_m2=target, min_area_m2=lo, max_area_m2=hi,
            min_short_side_m=short, max_aspect_ratio=aspect)
    # The hall is the brain's own room — no template row — so its share is computed here rather
    # than by `scale_program`. With every room now banded around its own share (`AREA_BAND`), the
    # hall is an ORDINARY room with an ordinary band: the capacity-dependent ceiling that Stage 2
    # used is gone. That ceiling was treating the symptom — circulation absorbing the surplus —
    # and squeezing it took B16 from three plans to one without giving the customer a square metre.
    # Circulation is a share of THE ROOMS IT SERVES, not of the plot. Sizing it against the plot
    # is what produced 20% circulation on the underfilled briefs: B09's hall was given 9% of a
    # 396 m² plot while the programme only makes a ~180 m² house, so the corridor was 12% of the
    # building before the foyer was even added. The scaled programme is what will actually be
    # built, so that is what the hall is measured against.
    programme_net = sum(z.target_area_m2 for z in zones.values())
    hall_target = round(max(9.0, min(0.09 * programme_net, 22.0)), 2)
    full_bounds[HALL] = (4.0, HALL_CEILING_M2)
    hall_lo, hall_hi = band_around(hall_target, AREA_BAND, 4.0, HALL_CEILING_M2)
    zones[HALL] = _hall_intent(HALL, target=hall_target, floor=hall_lo, ceiling=hall_hi)
    # The canonical capacity formula, never re-derived here. It excludes FLEX deliberately — FLEX
    # exists to absorb what the rooms cannot. The foyer is deliberately NOT added either: leaving
    # it out understates capacity by a few m², which biases a borderline brief toward "the layout
    # fell short" rather than "your brief does not add up". Of the two misclassifications that is
    # the one to prefer — it blames this code, not the customer.
    capacity = program_capacity_gross_m2(planned, hard=True)
    # The foyer is banded like everything else. Left at 3.5–9.0 it was the second-loosest zone in
    # the programme, and the loosest zone is always where the surplus goes.
    full_bounds[ENTRY] = (3.5, 9.0)
    entry = _entry_intent()
    entry_lo, entry_hi = band_around(entry.target_area_m2, AREA_BAND, 3.5, 9.0)
    from dataclasses import replace as _replace
    zones[ENTRY] = _replace(entry, min_area_m2=entry_lo, max_area_m2=entry_hi)

    return Programme(public=tuple(public), bedrooms=tuple(bedrooms), ensuites=ensuites, flex=tuple(flex),
                     open_plan=bool(getattr(spec.program, "open_plan_living", False)),
                     shared_wet=tuple(shared_wet), safe_room=safe_room, zones=zones,
                     wet_rooms=tuple(spec.program.wet_room_kinds or ()),
                     footprint_m=footprint_m,
                     resolved_wet=tuple(r.wet for r in rooms if r.wet is not None),
                     net_available_m2=round(net_available, 2),
                     capacity_m2=round(capacity + HALL_CEILING_M2, 2),
                     requested_m2=float(getattr(spec.program, "target_built_area_m2", 0.0) or 0.0),
                     full_bounds=full_bounds)


def band_around(target: float, frac: float, floor: float, ceiling: float) -> tuple[float, float]:
    """A room's allowed area band around its own fair share, clamped to its template range.

    Always a SUBSET of [floor, ceiling]: this narrows what the sizer may choose, it never permits
    a size the template did not already allow. `frac = None` means "no band" — the full range,
    which is the behaviour that existed before #197 Stage 3 and the last rung of the ladder.
    """
    if frac is None:
        return round(floor, 2), round(ceiling, 2)
    lo = max(floor, target * (1 - frac))
    hi = min(ceiling, target * (1 + frac))
    if lo > hi:                      # the target sits outside its own template range
        lo, hi = floor, ceiling
    return round(lo, 2), round(hi, 2)


#: The widest a hall may ever be, at the last rung of the widening ladder. It is the outer bound
#: the band is clamped into, not the size anything aims for.
HALL_CEILING_M2 = 30.0


def _hall_intent(zone_id: str, target: float = 9.0, floor: float = 4.0,
                 ceiling: float = HALL_CEILING_M2) -> ZoneIntent:
    """The hall, as an ordinary banded room.

    Its bounds used to be the loosest in the programme — no template row, 4–30 m² — which is
    precisely why the exact sizer dumped every surplus square metre here (#197 Stage 3). It is now
    banded around its own share like everything else, and `floor`/`ceiling` are the outer clamp the
    widening ladder relaxes toward, not a target.
    """
    return ZoneIntent(zone_id=zone_id, role=ProgramRole.HALL, donor_room_id=None,
                      target_area_m2=min(max(target, floor), ceiling),
                      min_area_m2=floor, max_area_m2=ceiling,
                      min_short_side_m=HALL_MIN_SHORT_SIDE_M, max_aspect_ratio=HALL_MAX_ASPECT)


def _entry_intent(target: float = 5.0) -> ZoneIntent:
    """The foyer. CIRCULATION, not HALL, so that where both front the street the hall still wins
    the door — this never outranks a hall that genuinely reached the street. Kept small on purpose:
    a foyer that grows into a second hall is the 29.6 m2 landlocked room the audit named."""
    return ZoneIntent(zone_id=ENTRY, role=ProgramRole.CIRCULATION, donor_room_id=None,
                      target_area_m2=target, min_area_m2=3.5, max_area_m2=9.0,
                      min_short_side_m=1.5, max_aspect_ratio=2.5)


# ---------------------------------------------------------------------------- the partis
#
# Each builder returns (spatial, access, arrival). They share two helpers so the rules that keep a
# graph representable and legal are written ONCE.

def _chain(ids: Iterable[str]) -> list[tuple[str, str]]:
    ids = list(ids)
    return [(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]


def _hub(hub: str, members: Iterable[str]) -> list[tuple[str, str]]:
    return [(hub, m) for m in members]


def _private_edges(p: Programme, hub: str) -> tuple[list, list]:
    """Bedrooms (and the safe room) off `hub`; each ensuite off ITS OWN bedroom; shared wet off
    `hub`. This is the whole reason these graphs are representable — a bedroom touches its
    circulation node and nothing else public."""
    spatial = _hub(hub, p.private)
    access = [(hub, z) for z in p.private]
    for wet, host in p.ensuites.items():
        spatial.append((host, wet))
        access.append((host, wet))
    spatial += _hub(hub, p.shared_wet)
    access += [(hub, z) for z in p.shared_wet]
    return spatial, access


def parti_hall_spine(p: Programme):
    """One hall serving everything; the public rooms chain off its head — the classic corridor
    house. Only the FIRST public room touches the hall."""
    spatial, access = _private_edges(p, HALL)
    spatial += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    access += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    return spatial, access, HALL


def parti_public_band(p: Programme):
    """EVERY public room meets the hall, so the public rooms read as one band across the plan with
    the circulation behind it, rather than a tail hanging off the corridor's head. A genuinely
    different contact graph from HALL_SPINE — which is what decides the geometry."""
    if len(p.public) < 2:
        return None
    spatial, access = _private_edges(p, HALL)
    spatial += _hub(HALL, p.public) + _chain(p.public)
    access += [(HALL, p.public[0])] + _chain(p.public)
    return spatial, access, HALL


def parti_bedroom_wing(p: Programme):
    """The bedrooms form a contiguous WING — each still entered from the hall (never through
    another bedroom: C24 forbids it) but also touching its neighbour, so they group into a block
    instead of being spread along the corridor."""
    if len(p.bedrooms) < 3:
        return None
    spatial, access = _private_edges(p, HALL)
    spatial += _chain(p.bedrooms)                      # contacts only — the doors stay off the hall
    spatial += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    access += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    return spatial, access, HALL


def parti_two_hall(p: Programme):
    """An entry hall for the public half and a quieter bedroom corridor behind it — the BRANCHED
    organisation #185 proved realizable. Needs enough bedrooms to be worth a second corridor."""
    if len(p.bedrooms) < 3:
        return None
    front, back = p.bedrooms[:1], p.bedrooms[1:]
    spatial = [(HALL, HALL_B)]
    access = [(HALL, HALL_B)]
    spatial += _hub(HALL, front) + _hub(HALL_B, back)
    access += [(HALL, z) for z in front] + [(HALL_B, z) for z in back]
    if p.safe_room:
        spatial.append((HALL_B, p.safe_room)); access.append((HALL_B, p.safe_room))
    for wet, host in p.ensuites.items():
        spatial.append((host, wet)); access.append((host, wet))
    for i, wet in enumerate(p.shared_wet):
        hub = HALL if i == 0 else HALL_B
        spatial.append((hub, wet)); access.append((hub, wet))
    spatial += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    access += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    return spatial, access, HALL


def parti_service_core(p: Programme):
    """The shared wet rooms grouped against each other as one plumbing core off the hall, instead
    of scattered along it — fewer stacks, and it keeps wet rooms off the good elevations."""
    if len(p.shared_wet) < 2:
        return None
    spatial, access = [], []
    spatial += _hub(HALL, p.private); access += [(HALL, z) for z in p.private]
    for wet, host in p.ensuites.items():
        spatial.append((host, wet)); access.append((host, wet))
    spatial += _hub(HALL, p.shared_wet) + _chain(p.shared_wet)   # the core: wet rooms touching
    access += [(HALL, w) for w in p.shared_wet]
    spatial += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    access += _chain(p.public) + ([(HALL, p.public[0])] if p.public else [])
    return spatial, access, HALL


#: (name, rationale, builder). Order is the order the owner sees them offered in.
PARTIS: tuple[tuple[str, str, Callable], ...] = (
    ("HALL_SPINE", "one hall serves every room; the public rooms chain off its head", parti_hall_spine),
    ("PUBLIC_BAND", "every public room meets the hall, reading as one band with circulation behind",
     parti_public_band),
    ("BEDROOM_WING", "the bedrooms group into a contiguous wing instead of spreading along the hall",
     parti_bedroom_wing),
    ("TWO_HALL", "an entry hall for the public half, a quieter corridor for the bedrooms", parti_two_hall),
    ("SERVICE_CORE", "the wet rooms grouped as one plumbing core rather than scattered", parti_service_core),
)


@dataclass
class DeterministicProposer:
    """Free, instant, reproducible — and diverse by construction rather than by sampling."""

    name: str = "deterministic"
    partis: tuple = field(default=PARTIS)

    def propose(self, p: Programme) -> list[TopologyProposal]:
        """Every applicable parti, and — where the brief can afford one — the same parti with an
        entry foyer, which is a different concept and a different contact graph, not a tweak.

        The foyer variant comes FIRST. On the eight audit briefs the plain variant arrives in a
        public room, because the hall is a hub and hubs land in interior bands (see `ENTRY`); the
        foyer variant gives the plan an actual entrance sequence. Both are offered because they
        are genuinely different buildings, and because a brief too tight for a foyer must still
        get a plan rather than a refusal.
        """
        out: list[TopologyProposal] = []
        for parti_name, rationale, build in self.partis:
            built = build(p)
            if built is None:
                continue                                  # this parti does not apply to this brief
            spatial, access, arrival = built
            for name, sp, ac, arr in _with_and_without_foyer(parti_name, spatial, access, arrival, p):
                out.append(TopologyProposal(
                    name=name, rationale=rationale, spatial=_dedupe_undirected(sp),
                    access=(("ENTRANCE", arr),) + tuple(dict.fromkeys(ac)), arrival=arr))
        return out


def _with_and_without_foyer(parti: str, spatial, access, arrival, p: Programme):
    """(name, spatial, access, arrival) for each variant, foyer first when the brief affords it."""
    if p.affords_foyer and ENTRY in p.zones:
        yield (f"{parti}+FOYER",
               list(spatial) + [(ENTRY, arrival)],
               list(access) + [(ENTRY, arrival)],
               ENTRY)
    yield (parti, list(spatial), list(access), arrival)


def _dedupe_undirected(pairs) -> tuple[tuple[str, str], ...]:
    seen, out = set(), []
    for a, b in pairs:
        if a == b:
            continue
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        out.append((a, b))
    return tuple(out)
