"""Production PROPOSAL CRITIC — deterministic proposal invariants, decided BEFORE any embedding or
geometry (Issue #142J; proven as a harness prototype in #142I).

A concept/proposal is rooms with roles, undirected REQUIRED contacts (`spatial`), directed doors
(`access`, "ENTRANCE" allowed as a source) and the BRIEF's declared wet-room kinds. The critic returns
structured findings; it never repairs anything. `proposal_selection` keeps only candidates without a
HARD finding before any scoring.

HARD = the unchanged production pipeline cannot pass the proposal as written. WARN = a fact the
proposer should know, or a question the bounded search could not settle (UNKNOWN is never a HARD).

  I1  ENTRANCE                the house is entered through an ALLOWED_ENTRANCE role
  I2  LEGAL_ACCESS            every direct-access pair is a legal door pair (`access_rules`)
  I3  ONE_DOOR_WET            a wet room (BATHROOM/TOILET) has exactly ONE door
  I4  WET_ENTRY_POLICY        that door comes from where the canonical `wet_room_policy` allows
                              (host bedroom for an ensuite; HALL/CIRCULATION or the LIVING fallback for
                              a shared wet room; never a non-host bedroom, KITCHEN or DINING)
  I4b WET_KIND_FROM_BRIEF     the brief's DECLARED wet-room kinds are the source of truth: a specified
                              ensuite must exist with its declared host, a specified guest WC / shared
                              bathroom must exist with public access; count-derived defaults the brief
                              never stated are matched as classes and only WARN when they differ
  I5  DOOR_NEEDS_WALL         a direct door requires a shared wall: an access pair missing from the
                              required contacts is reported (WARN) and becomes a required contact — a
                              corridor between A and B is A->corridor and corridor->B, never A->B
  I6  REPRESENTABLE           spatial ∪ access is planar, free of K4 / triple-lens obstructions and has
                              a band layout: a proven impossibility is HARD (`ACCESS_SPATIAL_CONTRADICTION`
                              when the spatial graph alone embeds, else `CONTACTS_NOT_REPRESENTABLE`);
                              a search bound hit is WARN `REPRESENTABILITY_UNKNOWN`
  I7  REACHABLE               every room is reachable from ENTRANCE through LEGAL doors
  I8  EXPOSURE                a REQUIRED-exposure room buried in EVERY layout of a COMPLETE band family
                              is HARD `EXPOSURE_INFEASIBLE`; within a bound only, WARN `EXPOSURE_UNKNOWN`
  I9  ROOM_HAS_DOOR           every room has at least one door
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from . import access_rules, wet_room_policy
from .band_embedding import BandEmbedding, BandEmbeddingRefusal, embed_band, representation_precheck
from .band_pipeline import placement_flags
from .doors import ALLOWED_ENTRANCE_ROLES
from .exposure_policy import REQUIRED_EXTERIOR_ROLES
from .geometry_core.model import ProgramRole
from .spec import ENSUITE_HOST_BEDROOM, ENSUITE_HOST_MASTER, WetRoomKind, WetRoomOrigin, WetRoomRequirement, WetRoomStrength
from .wet_rooms import ResolvedWetRoom

ENTRANCE_ID = "ENTRANCE"
WET_ROLES = (ProgramRole.BATHROOM, ProgramRole.TOILET)
BEDROOM_ROLES = (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)
PUBLIC_KINDS = (WetRoomKind.SHARED_BATHROOM, WetRoomKind.GUEST_WC)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str                 # HARD | WARN
    subjects: tuple               # room ids / pairs the finding is about
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Proposal:
    """The critic's input. `wet_rooms` are the BRIEF's declared kinds (`spec.WetRoomRequirement`:
    kind, host spec, origin) — programme intent, not a per-room guess. `zones` (ZoneIntent per room)
    are needed for the band embedder (I6/I8); without them those two invariants are skipped."""
    name: str
    roles: dict                    # room id -> ProgramRole
    spatial: frozenset             # frozenset[frozenset[str]]
    access: tuple                  # tuple[(from, to)], may include ENTRANCE as `from`
    zones: dict | None = None
    wet_rooms: tuple = ()          # tuple[WetRoomRequirement]

    @property
    def room_access(self) -> list:
        return [(a, b) for a, b in self.access if a != ENTRANCE_ID and a in self.roles and b in self.roles and a != b]


@dataclass
class CriticReport:
    name: str
    findings: list
    required_contacts: tuple = ()        # spatial ∪ access (undirected sorted pairs)
    wet_rooms: tuple = ()                # the ResolvedWetRooms the realizer/C17 must be held to
    seconds: float = 0.0

    @property
    def hard(self) -> list:
        return [f for f in self.findings if f.severity == "HARD"]

    @property
    def clean(self) -> bool:
        return not self.hard

    @property
    def codes(self) -> tuple:
        return tuple(sorted({f.code for f in self.findings}))

    @property
    def hard_codes(self) -> tuple:
        return tuple(sorted({f.code for f in self.hard}))


# ----------------------------------------------------------------------------- wet-room kinds

def implied_wet_rooms(p: Proposal) -> dict:
    """Per wet room: (implied kind, host, entrants) read off the proposal's doors — what the proposal
    SAYS (a bedroom door makes an ensuite of that bedroom; a public door a shared bathroom / guest WC
    by role). A room with several doors is ambiguous: its first-ranked reading is returned and I3 fires."""
    incoming: dict[str, list[str]] = {}
    for a, b in p.room_access:
        incoming.setdefault(b, []).append(a); incoming.setdefault(a, []).append(b)
    out = {}
    for rid, role in p.roles.items():
        if role not in WET_ROLES:
            continue
        entrants = sorted(set(incoming.get(rid, ())))
        beds = [e for e in entrants if p.roles[e] in BEDROOM_ROLES]
        public = [e for e in entrants if p.roles[e] in wet_room_policy.SHARED_WET_ROOM_ENTRY_ROLES]
        if public:
            kind, host = (WetRoomKind.GUEST_WC if role is ProgramRole.TOILET else WetRoomKind.SHARED_BATHROOM), None
        elif beds:
            kind, host = WetRoomKind.ENSUITE, beds[0]
        else:
            kind, host = (WetRoomKind.GUEST_WC if role is ProgramRole.TOILET else WetRoomKind.SHARED_BATHROOM), None
        out[rid] = (kind, host, tuple(entrants))
    return out


def _host_matches(req_host: str | None, host_id: str | None, roles: dict) -> bool:
    if host_id is None:
        return False
    role = roles.get(host_id)
    if req_host in (None, ENSUITE_HOST_MASTER):
        return role is ProgramRole.MASTER_BEDROOM
    if req_host == ENSUITE_HOST_BEDROOM:
        return role is ProgramRole.BEDROOM
    return host_id == req_host                      # an explicit room id


def assign_wet_room_kinds(p: Proposal) -> tuple[tuple, list]:
    """Match the brief's declared kinds to the proposal's wet rooms (deterministic, specified kinds
    first) and return (ResolvedWetRooms for the realizer / C17, findings). The brief is the source of
    truth: a SPECIFIED kind the proposal contradicts or lacks is HARD; a count-derived default the brief
    never stated adopts the proposal's reading and only WARNs when the classes differ."""
    implied = implied_wet_rooms(p)
    F: list[Finding] = []
    free = sorted(implied)                           # unmatched proposal wet rooms
    resolved: dict[str, ResolvedWetRoom] = {}
    reqs = list(p.wet_rooms)
    specified = [r for r in reqs if r.kind is not WetRoomKind.UNSPECIFIED and r.origin is WetRoomOrigin.EXPLICIT]
    defaults = [r for r in reqs if r not in specified]

    def take(rid, req, kind, host, spec: bool):
        free.remove(rid)
        resolved[rid] = ResolvedWetRoom(rid, kind, host, req.strength if req else WetRoomStrength.REQUIRED,
                                        spec, req.source_text if req else "",
                                        req.origin if req else WetRoomOrigin.COUNT_DERIVED)

    for req in specified:                            # 1. specified kinds must be honoured exactly
        match = None
        for rid in free:
            kind, host, _ = implied[rid]
            if req.kind is WetRoomKind.ENSUITE and kind is WetRoomKind.ENSUITE and _host_matches(req.host, host, p.roles):
                match = rid; break
            if req.kind in PUBLIC_KINDS and kind in PUBLIC_KINDS and \
                    (p.roles[rid] is ProgramRole.TOILET) == (req.kind is WetRoomKind.GUEST_WC):
                match = rid; break
        if match is None:
            F.append(Finding("WET_ROOM_KIND_MISSING", "HARD", (req.kind.value,),
                             f"the brief declares a {req.kind.value}{' of ' + str(req.host) if req.host else ''} and no wet "
                             f"room of the proposal is entered that way",
                             {"declared": req.kind.value, "host": req.host, "implied": {r: (k.value, h) for r, (k, h, _) in implied.items()}}))
            continue
        kind, host, _ = implied[match]
        take(match, req, kind, host, True)
    for req in defaults:                             # 2. defaults take whatever is left, in order
        if not free:
            break
        # prefer the room whose reading matches the default's class
        pick = next((rid for rid in free if (implied[rid][0] is WetRoomKind.ENSUITE) == (req.kind is WetRoomKind.ENSUITE)), free[0])
        kind, host, _ = implied[pick]
        take(pick, req, kind, host, False)
        differs = kind is not req.kind or (kind is WetRoomKind.ENSUITE and not _host_matches(req.host, host, p.roles))
        if req.kind is not WetRoomKind.UNSPECIFIED and differs:
            F.append(Finding("WET_ROOM_KIND_DIFFERS_FROM_DEFAULT", "WARN", (pick,),
                             f"{pick} reads as {kind.value}{' of ' + host if host else ''}; the brief's count-derived default for "
                             f"this room was {req.kind.value} (not stated by the person — the proposal's reading is adopted)",
                             {"default": req.kind.value, "implied": kind.value}))
    for rid in list(free):                           # 3. more wet rooms than the brief counted
        kind, host, _ = implied[rid]
        if reqs:
            F.append(Finding("WET_ROOM_COUNT_MISMATCH", "HARD", (rid,),
                             f"{rid} is a wet room the brief did not count ({len(reqs)} declared, {len(implied)} proposed)"))
        take(rid, None, kind, host, False)
    if reqs and len(implied) < len(reqs) and not any(f.code == "WET_ROOM_KIND_MISSING" for f in F):
        F.append(Finding("WET_ROOM_COUNT_MISMATCH", "HARD", (),
                         f"the brief counts {len(reqs)} wet rooms, the proposal has {len(implied)}"))
    return tuple(resolved[r] for r in sorted(resolved)), F


# ----------------------------------------------------------------------------- the critic

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
    t0 = time.monotonic()
    F: list[Finding] = []
    ids = list(p.roles)
    room_access = p.room_access
    wet, kind_findings = assign_wet_room_kinds(p)
    wet_by_id = {w.zone_id: w for w in wet}
    implied = implied_wet_rooms(p)

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

    # I3 / I4 — one door per wet room, from where the policy allows
    for rid, (kind, host, entrants) in implied.items():
        if len(entrants) > 1:
            F.append(Finding("WET_ROOM_MULTIPLE_ENTRANTS", "HARD", (rid, *entrants),
                             f"{rid} has {len(entrants)} doors ({', '.join(entrants)}); a wet room has exactly one "
                             f"(specs/007 FR-9): an ensuite only from its host, a shared wet room only from circulation",
                             {"entrants": entrants}))
        w = wet_by_id.get(rid)
        for e in entrants:
            if w is not None and not wet_room_policy.wet_room_entry_allowed(w, e, (p.roles[e],)):
                F.append(Finding("WET_ROOM_ENTRY_POLICY", "HARD", (e, rid),
                                 f"{e} ({p.roles[e].value}) -> {rid} ({w.kind.value}{' of ' + w.host_zone if w.host_zone else ''}): "
                                 + wet_room_policy.describe_rule(w), {"kind": w.kind.value, "host": w.host_zone}))
    F.extend(kind_findings)                           # I4b

    # I9 — every room has a door
    touched = {x for a, b in room_access for x in (a, b)} | set(targets)
    for rid in ids:
        if rid not in touched:
            F.append(Finding("ROOM_WITHOUT_ACCESS", "HARD", (rid,), f"{rid} has no access edge at all"))

    # I5 — a door needs a wall
    unbacked = [(a, b) for a, b in room_access if frozenset((a, b)) not in p.spatial]
    if unbacked:
        F.append(Finding("ACCESS_WITHOUT_CONTACT", "WARN", tuple(f"{a}->{b}" for a, b in unbacked),
                         f"{len(unbacked)} direct door(s) have no required contact; a door needs a shared wall, so they are "
                         f"required contacts: " + ", ".join(f"{a}->{b}" for a, b in unbacked), {"pairs": unbacked}))
    union = tuple(sorted({tuple(sorted(e)) for e in p.spatial} | {tuple(sorted((a, b))) for a, b in room_access}))

    # I7 — reachability through LEGAL doors
    adj: dict[str, set] = {}
    for a, b in p.access:
        if (a == ENTRANCE_ID or a in p.roles) and b in p.roles and _legal_pair(p, wet_by_id, a, b):
            adj.setdefault(a, set()).add(b)
            if a != ENTRANCE_ID:
                adj.setdefault(b, set()).add(a)
    seen, stack = set(), [ENTRANCE_ID]
    while stack:
        x = stack.pop()
        for y in sorted(adj.get(x, ())):
            if y not in seen:
                seen.add(y); stack.append(y)
    unreachable = sorted(set(ids) - seen)
    if unreachable:
        F.append(Finding("UNREACHABLE_ROOM", "HARD", tuple(unreachable),
                         "not reachable from ENTRANCE through legal doors: " + ", ".join(unreachable)))

    # I6 / I8 — representability of the contacts; exposure over the band family
    pre = representation_precheck(ids, list(union))
    if pre is not None:
        spatial_only = representation_precheck(ids, sorted(tuple(sorted(e)) for e in p.spatial))
        code = "ACCESS_SPATIAL_CONTRADICTION" if (unbacked and spatial_only is None) else "CONTACTS_NOT_REPRESENTABLE"
        F.append(Finding(code, "HARD", (), f"{pre.code}: {pre.detail}",
                         {"obstruction": pre.code, "spatial_alone_obstructed": spatial_only is not None}))
    elif p.zones is not None:
        emb = embed_band(p.zones, list(union), max_candidates=embed_max_candidates)
        if isinstance(emb, BandEmbeddingRefusal):
            if emb.code == "BAND_UNSAT":
                spatial_emb = embed_band(p.zones, sorted(tuple(sorted(e)) for e in p.spatial), max_candidates=1)
                code = "ACCESS_SPATIAL_CONTRADICTION" if (unbacked and isinstance(spatial_emb, BandEmbedding)) else "CONTACTS_NOT_REPRESENTABLE"
                F.append(Finding(code, "HARD", (), f"{emb.code}: {emb.detail}", {"refusal": emb.code}))
            else:
                F.append(Finding("REPRESENTABILITY_UNKNOWN", "WARN", (), f"{emb.code}: {emb.detail}", {"refusal": emb.code}))
        elif check_exposure:
            buried: Counter = Counter(); n = len(emb.candidates); exposed_ok = 0
            for c in emb.candidates:
                fl = placement_flags(c, p.zones, wet, tuple(room_access))
                if fl["exposure_ok"]:
                    exposed_ok += 1
                for z in fl["buried_required"]:
                    buried[z] += 1
            if exposed_ok == 0 and n:
                if emb.search_complete:
                    F.append(Finding("EXPOSURE_INFEASIBLE", "HARD", tuple(sorted(buried)),
                                     f"every one of the {emb.layouts_found} band layouts (complete family) buries a REQUIRED-exposure "
                                     f"room: " + ", ".join(f"{z} x{k}" for z, k in buried.most_common()),
                                     {"layouts": emb.layouts_found, "complete": True, "buried": dict(buried)}))
                else:
                    F.append(Finding("EXPOSURE_UNKNOWN", "WARN", tuple(sorted(buried)),
                                     f"no exposure-feasible band layout among the {n} found within the search bound (not a proof)",
                                     {"layouts": n, "complete": False, "buried": dict(buried)}))
    return CriticReport(p.name, F, union, wet, round(time.monotonic() - t0, 3))


__all__ = ["Finding", "Proposal", "CriticReport", "criticize", "implied_wet_rooms", "assign_wet_room_kinds",
           "ENTRANCE_ID", "WET_ROLES", "BEDROOM_ROLES"]
