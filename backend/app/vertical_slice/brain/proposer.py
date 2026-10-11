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
                                                   build_room_program, scale_program)
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.stage2.contract import ZoneIntent
from app.vertical_slice.wet_rooms import ResolvedWetRoom

#: The circulation node every parti has at least one of.
HALL = "HALL"
#: The second circulation node of the two-hall partis.
HALL_B = "HALL_B"


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

    @property
    def private(self) -> tuple[str, ...]:
        return self.bedrooms + ((self.safe_room,) if self.safe_room else ())


def programme_from_spec(spec, footprint_m: tuple[float, float]) -> Programme:
    """The brief's `ArchitecturalSpec` -> `Programme`, using production's OWN room builder so the
    brain plans the same rooms the product would."""
    rooms = build_room_program(spec)
    by_id = {r.zone_id: r for r in rooms}
    public, bedrooms, shared_wet = [], [], []
    ensuites: dict[str, str] = {}
    safe_room = None
    for r in rooms:
        if r.role is ProgramRole.SAFE_ROOM:
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
    planned = [r for r in rooms if r.role is not ProgramRole.FLEX]
    scaled = scale_program(planned, net_available)

    zones: dict[str, ZoneIntent] = {}
    for r in planned:
        t = r.template
        spec_for_room = scaled.get(r.zone_id)
        target = spec_for_room.net_area_target_m2 if spec_for_room else t.target_area_m2
        ceiling = t.hard_max_area_m2 or t.max_area_m2
        zones[r.zone_id] = ZoneIntent(
            zone_id=r.zone_id, role=r.role, donor_room_id=None,
            target_area_m2=round(max(t.min_area_m2, min(target, ceiling)), 2),
            min_area_m2=t.min_area_m2, max_area_m2=ceiling,
            min_short_side_m=t.min_short_side_m, max_aspect_ratio=t.max_aspect_ratio)
    # The hall is the brain's own room (no template row of its own in the programme): give it a
    # share of the surplus too, so circulation grows with the house instead of staying at 9 m2.
    hall_target = max(9.0, min(0.09 * net_available, 22.0))
    zones[HALL] = _hall_intent(HALL, target=round(hall_target, 2))

    return Programme(public=tuple(public), bedrooms=tuple(bedrooms), ensuites=ensuites,
                     shared_wet=tuple(shared_wet), safe_room=safe_room, zones=zones,
                     wet_rooms=tuple(spec.program.wet_room_kinds or ()),
                     footprint_m=footprint_m,
                     resolved_wet=tuple(r.wet for r in rooms if r.wet is not None))


def _hall_intent(zone_id: str, target: float = 9.0) -> ZoneIntent:
    return ZoneIntent(zone_id=zone_id, role=ProgramRole.HALL, donor_room_id=None,
                      target_area_m2=target, min_area_m2=4.0, max_area_m2=30.0,
                      min_short_side_m=1.2, max_aspect_ratio=8.0)


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
        out: list[TopologyProposal] = []
        for parti_name, rationale, build in self.partis:
            built = build(p)
            if built is None:
                continue                                  # this parti does not apply to this brief
            spatial, access, arrival = built
            spatial = _dedupe_undirected(spatial)
            access = tuple(dict.fromkeys(access))
            out.append(TopologyProposal(
                name=parti_name, rationale=rationale, spatial=spatial,
                access=(("ENTRANCE", arrival),) + access, arrival=arrival))
        return out


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
