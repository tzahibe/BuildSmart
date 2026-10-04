"""#142I — deterministic pre-realization PROPOSAL CRITIC (prototype, harness code — not production).

Runs on a concept/proposal BEFORE any embedding or geometry and returns structured findings: the
proposal invariants every proposal must satisfy to be worth handing to the realizer. It never
repairs anything (see `proposal_repair.py` for the separate, clearly labelled repair experiment).

Invariants (see docs/reports/142i-proposal-consistency/README.md §2):

  I1  ENTRANCE          the access graph enters the house through an ALLOWED_ENTRANCE role
  I2  LEGAL_ACCESS      every direct-access pair is a legal door pair (`access_rules.edge_role_pair_allowed`)
  I3  ONE_DOOR_WET      a wet room (BATHROOM/TOILET) has exactly ONE door (specs/007 FR-9: an ensuite
                        is entered ONLY from its host, a shared wet room ONLY from circulation)
  I4  WET_ENTRY_POLICY  that one door comes from where the canonical wet-room policy allows
                        (`wet_room_policy.wet_room_entry_allowed`: host bedroom for an ensuite;
                        HALL/CIRCULATION, or LIVING as the specs/009 decision-C public fallback, for a
                        shared wet room; never KITCHEN/DINING, never a non-host bedroom)
  I5  DOOR_NEEDS_WALL   a direct-access pair is also a required contact (a door needs a shared wall);
                        an access pair missing from the spatial adjacency is reported (WARN) and added
                        to the required contacts for I6/I8
  I6  CONTACTS_REPRESENTABLE  spatial ∪ access is planar, free of K4 / triple-lens obstructions, and
                        has a band layout (exact embedder, bounded) — otherwise the proposal's access
                        contradicts its adjacency under rectangles (ACCESS_SPATIAL_CONTRADICTION)
  I7  REACHABLE         every room is reachable from ENTRANCE through LEGAL access edges
  I8  EXPOSURE          no REQUIRED-exposure room is buried in EVERY band layout of the complete family
                        (a proof when the enumeration completed; a WARN when only the search bound was hit)
  I9  ROOM_HAS_DOOR     every room has at least one access edge

Severity: HARD findings mean the unchanged production pipeline cannot pass the proposal as written;
WARN findings are facts the proposer should know (I5) or unproven suspicions (I6/I8 within a bound).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.vertical_slice import access_rules, wet_room_policy
from app.vertical_slice.band_embedding import BandEmbedding, BandEmbeddingRefusal, embed_band, representation_precheck
from app.vertical_slice.band_pipeline import placement_flags
from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.rectilinear_realizer import ZoneIntent
from app.vertical_slice.spec import WetRoomKind
from app.vertical_slice.wet_rooms import ResolvedWetRoom

ENTRANCE_ID = "ENTRANCE"
WET_ROLES = (ProgramRole.BATHROOM, ProgramRole.TOILET)
BEDROOM_ROLES = (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str                 # HARD | WARN
    subjects: tuple               # room ids / pairs the finding is about
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Proposal:
    """The critic's own minimal input: roles, undirected contacts, directed doors. Built from a frozen
    fixture brief (`from_fixture`) or a POC `TopologyProposal` (`from_topology_proposal`)."""
    name: str
    roles: dict                    # room id -> ProgramRole
    spatial: frozenset             # frozenset[frozenset[str]]
    access: tuple                  # tuple[(from, to)], may include ENTRANCE as `from`
    zones: dict | None = None      # room id -> ZoneIntent (needed for the band embedder / exposure)
    wet_rooms: tuple = ()          # resolved kinds if the caller has them; else inferred (see `infer_wet_rooms`)


def from_fixture(bid: str, brief: dict, zones: dict | None = None, wet_rooms: tuple = ()) -> Proposal:
    roles = {r["id"]: ProgramRole(r["role"]) for r in brief["rooms"]}
    return Proposal(bid, roles, frozenset(frozenset(e) for e in brief["spatial_adjacency"]),
                    tuple((a, b) for a, b in brief["access_graph"]), zones, wet_rooms)


def from_topology_proposal(name: str, p, zones: dict | None = None) -> Proposal:
    roles = {rid: ProgramRole(role) for rid, role in p.role_by_id.items()}
    return Proposal(name, roles, frozenset(p.spatial_adjacency), tuple(sorted(p.access_graph)), zones)


def infer_wet_rooms(p: Proposal) -> tuple:
    """The harness's own kind inference (gap_closure_142a.resolve_wet_rooms): the FIRST bedroom entrant
    makes an ENSUITE, otherwise a shared bathroom / guest WC. Kept here only so the critic can say what
    the translation layer WOULD decide — I3 reports the multi-entrant case the inference hides."""
    incoming: dict[str, list[str]] = {}
    for a, b in p.access:
        incoming.setdefault(b, []).append(a)
    out = []
    for rid, role in p.roles.items():
        if role not in WET_ROLES:
            continue
        hosts = [a for a in incoming.get(rid, ()) if p.roles.get(a) in BEDROOM_ROLES]
        if hosts:
            out.append(ResolvedWetRoom(rid, WetRoomKind.ENSUITE, hosts[0], None, True))
        else:
            kind = WetRoomKind.GUEST_WC if role is ProgramRole.TOILET else WetRoomKind.SHARED_BATHROOM
            out.append(ResolvedWetRoom(rid, kind, None, None, True))
    return tuple(out)


@dataclass
class CriticReport:
    name: str
    findings: list
    required_contacts: tuple = ()      # spatial ∪ access (undirected sorted pairs)
    seconds: float = 0.0

    @property
    def hard(self) -> list:
        return [f for f in self.findings if f.severity == "HARD"]

    @property
    def codes(self) -> tuple:
        return tuple(sorted({f.code for f in self.findings}))

    @property
    def hard_codes(self) -> tuple:
        return tuple(sorted({f.code for f in self.hard}))


def _legal_pair(p: Proposal, wet_by_id: dict, a: str, b: str) -> bool:
    if a == ENTRANCE_ID:
        return p.roles.get(b) in ALLOWED_ENTRANCE_ROLES
    if not access_rules.edge_role_pair_allowed((p.roles[a],), (p.roles[b],)):
        return False
    for x, y in ((a, b), (b, a)):
        if x in wet_by_id and not wet_room_policy.wet_room_entry_allowed(wet_by_id[x], y, (p.roles[y],)):
            return False
    return True


def criticize(p: Proposal, *, embed_max_candidates: int = 150, check_exposure: bool = True) -> CriticReport:
    import time
    t0 = time.monotonic()
    F: list[Finding] = []
    ids = list(p.roles)
    wet = p.wet_rooms or infer_wet_rooms(p)
    wet_by_id = {w.zone_id: w for w in wet}
    room_access = [(a, b) for a, b in p.access if a != ENTRANCE_ID and a in p.roles and b in p.roles and a != b]

    # I1 — entrance
    targets = [b for a, b in p.access if a == ENTRANCE_ID]
    if not targets:
        F.append(Finding("NO_ENTRANCE_ACCESS", "HARD", (), "the access graph has no ENTRANCE edge"))
    for t in targets:
        if p.roles.get(t) not in ALLOWED_ENTRANCE_ROLES:
            F.append(Finding("ENTRANCE_INTO_NON_ENTRANCE_ROLE", "HARD", (t,),
                             f"ENTRANCE -> {t} ({p.roles.get(t)}) is not an ALLOWED_ENTRANCE role"))

    # I2 — legal role pairs
    for a, b in room_access:
        if not access_rules.edge_role_pair_allowed((p.roles[a],), (p.roles[b],)):
            F.append(Finding("ILLEGAL_ACCESS_PAIR", "HARD", (a, b),
                             f"{a} -> {b}: {p.roles[a].value} may not open into {p.roles[b].value} (ALLOWED_ENTERED_FROM)"))

    # I3 / I4 — wet rooms: one door, from where the canonical policy allows
    incoming: dict[str, list[str]] = {}
    for a, b in room_access:
        incoming.setdefault(b, []).append(a)
        incoming.setdefault(a, []).append(b)       # a door is two-way; count the pair once per wet room
    for rid, role in p.roles.items():
        if role not in WET_ROLES:
            continue
        entrants = sorted(set(incoming.get(rid, ())))
        if len(entrants) > 1:
            inferred = wet_by_id.get(rid)
            F.append(Finding("WET_ROOM_MULTIPLE_ENTRANTS", "HARD", (rid, *entrants),
                             f"{rid} has {len(entrants)} doors ({', '.join(entrants)}); specs/007 FR-9: a wet room "
                             f"has exactly one — an ensuite only from its host, a shared wet room only from "
                             f"circulation. The harness would silently read it as "
                             f"{inferred.kind.value}{' of ' + inferred.host_zone if inferred and inferred.host_zone else ''} "
                             f"and the other door(s) then fail C17 / the wet-room filter",
                             {"entrants": entrants, "inferred_kind": inferred.kind.value if inferred else None}))
        for e in entrants:
            w = wet_by_id.get(rid)
            if w is not None and not wet_room_policy.wet_room_entry_allowed(w, e, (p.roles[e],)):
                F.append(Finding("WET_ROOM_ENTRY_POLICY", "HARD", (e, rid),
                                 f"{e} ({p.roles[e].value}) -> {rid} ({w.kind.value}"
                                 f"{' of ' + w.host_zone if w.host_zone else ''}): "
                                 + wet_room_policy.describe_rule(w),
                                 {"kind": w.kind.value, "host": w.host_zone}))

    # I9 — every room has a door
    for rid in ids:
        if rid not in incoming and rid not in targets:
            F.append(Finding("ROOM_WITHOUT_ACCESS", "HARD", (rid,), f"{rid} has no access edge at all"))

    # I5 — a door needs a wall
    unbacked = [(a, b) for a, b in room_access if frozenset((a, b)) not in p.spatial]
    if unbacked:
        F.append(Finding("ACCESS_WITHOUT_CONTACT", "WARN", tuple(f"{a}->{b}" for a, b in unbacked),
                         f"{len(unbacked)} direct-access pair(s) have no spatial contact; a door needs a shared "
                         f"wall, so they are required contacts: " + ", ".join(f"{a}->{b}" for a, b in unbacked),
                         {"pairs": unbacked}))
    union = sorted({tuple(sorted(e)) for e in p.spatial} | {tuple(sorted((a, b))) for a, b in room_access})

    # I7 — reachability through LEGAL doors
    legal_adj: dict[str, set] = {}
    for a, b in p.access:
        if (a == ENTRANCE_ID or a in p.roles) and b in p.roles and _legal_pair(p, wet_by_id, a, b):
            legal_adj.setdefault(a, set()).add(b)
            if a != ENTRANCE_ID:
                legal_adj.setdefault(b, set()).add(a)
    seen, stack = set(), [ENTRANCE_ID]
    while stack:
        x = stack.pop()
        for y in legal_adj.get(x, ()):
            if y not in seen:
                seen.add(y); stack.append(y)
    unreachable = sorted(set(ids) - seen)
    if unreachable:
        F.append(Finding("UNREACHABLE_ROOM", "HARD", tuple(unreachable),
                         "not reachable from ENTRANCE through legal doors: " + ", ".join(unreachable)))

    # I6 / I8 — representability of the contacts, and exposure over the band family
    emb = None
    pre = representation_precheck(ids, union)
    if pre is not None:
        spatial_only = representation_precheck(ids, sorted(tuple(sorted(e)) for e in p.spatial))
        code = "ACCESS_SPATIAL_CONTRADICTION" if (unbacked and spatial_only is None) else "CONTACTS_NOT_REPRESENTABLE"
        F.append(Finding(code, "HARD", (), f"{pre.code}: {pre.detail}",
                         {"obstruction": pre.code, "spatial_alone_obstructed": spatial_only is not None}))
    elif p.zones is not None:
        emb = embed_band(p.zones, union, max_candidates=embed_max_candidates)
        if isinstance(emb, BandEmbeddingRefusal):
            sev = "HARD" if emb.code == "BAND_UNSAT" else "WARN"
            spatial_emb = embed_band(p.zones, sorted(tuple(sorted(e)) for e in p.spatial), max_candidates=1)
            code = "ACCESS_SPATIAL_CONTRADICTION" if (unbacked and isinstance(spatial_emb, BandEmbedding)) else "CONTACTS_NOT_REPRESENTABLE"
            F.append(Finding(code, sev, (), f"{emb.code}: {emb.detail}", {"refusal": emb.code}))
        elif check_exposure:
            buried = Counter(); n = len(emb.candidates); exposed_ok = 0
            for c in emb.candidates:
                fl = placement_flags(c, p.zones, wet, tuple(room_access))
                if fl["exposure_ok"]:
                    exposed_ok += 1
                for z in fl["buried_required"]:
                    buried[z] += 1
            if exposed_ok == 0 and n:
                sev = "HARD" if emb.search_complete else "WARN"
                F.append(Finding("EXPOSURE_INFEASIBLE", sev, tuple(sorted(buried)),
                                 f"every one of {n} band layouts ({'complete family' if emb.search_complete else 'search bound'}) "
                                 f"buries a REQUIRED-exposure room: " + ", ".join(f"{z} x{k}" for z, k in buried.most_common()),
                                 {"layouts": n, "complete": emb.search_complete, "buried": dict(buried)}))
    return CriticReport(p.name, F, tuple(union), round(time.monotonic() - t0, 3))


__all__ = ["Finding", "Proposal", "CriticReport", "criticize", "from_fixture", "from_topology_proposal", "infer_wet_rooms"]
