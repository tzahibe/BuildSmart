"""#142I — REPAIR EXPERIMENT (clearly labelled; harness code; never wired into production).

Given a proposal the `proposal_critic` fails, apply only MINIMAL, intent-preserving repairs, each one
recorded (rule, original relation, changed relation, reason, evidence that intent is preserved), then
hand the repaired proposal to the UNCHANGED production pipeline. No rule may invent a room, change a
role, or add a door the proposal did not ask for.

Rules, in order (each only when the critic reports the matching finding):

  R1 ONE_DOOR_WET      a wet room with several doors keeps ONE: the circulation door if the proposal
                       asked for one (the room is then the shared bathroom the hall door implies; every
                       bedroom that lost its direct door still reaches the room through the hall — the
                       evidence recorded), else LIVING (specs/009 fallback), else the FIRST bedroom
                       (an ensuite of that bedroom). The alternative reading ("keep the master door, the
                       hall door was the mistake") is recorded as `alternatives`, not applied.
  R2 ILLEGAL_ENTRANT   a wet room whose single door comes from a forbidden entrant (non-host bedroom,
                       KITCHEN, DINING) is re-doored from a legal spatial neighbour (circulation first,
                       then LIVING); no legal neighbour -> UNREPAIRABLE, nothing changed.
  R3 REROUTE_ACCESS    a direct-access pair with no spatial contact is re-routed through a legal
                       neighbour of the target that is itself reachable from the source (circulation
                       first, then public rooms); no such neighbour -> the contact is kept as required
                       (what the production pipeline does anyway).
  R4 DEMOTE_CONTACT    if spatial ∪ access is still not representable, the smallest set (1, then 2) of
                       spatial contacts NOT backed by any door whose removal makes the union embeddable
                       is demoted from REQUIRED to PREFERRED (a wall preference, never a door). Priority:
                       wet room ↔ public room, wet ↔ bedroom, wet ↔ wet, others.
  R5 DEMOTE_FOR_EXPOSURE  if every band layout buries a REQUIRED-exposure room, the same demotion
                       search, accepting the first set whose family has an exposure-feasible layout.

Nothing else. A proposal the rules cannot fix is reported UNREPAIRED with the critic's findings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations

from app.vertical_slice import access_rules, wet_room_policy
from app.vertical_slice.band_embedding import BandEmbedding, embed_band, representation_precheck
from app.vertical_slice.band_pipeline import placement_flags
from app.vertical_slice.geometry_core.model import ProgramRole

from .proposal_critic import BEDROOM_ROLES, ENTRANCE_ID, WET_ROLES, CriticReport, Proposal, criticize, infer_wet_rooms

PUBLIC_ROLES = (ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN, ProgramRole.FAMILY_ROOM)


@dataclass
class Repair:
    rule: str
    original: str
    changed: str
    reason: str
    evidence: dict = field(default_factory=dict)
    alternatives: tuple = ()


@dataclass
class RepairResult:
    name: str
    repairs: list
    unrepaired: list                 # critic HARD findings left (codes + details)
    before: CriticReport
    after: CriticReport
    proposal: Proposal


def _legal_path_steps(access, roles, wet_by_id, src, dst) -> int | None:
    adj: dict[str, set] = {}
    for a, b in access:
        if a == ENTRANCE_ID or a not in roles or b not in roles:
            continue
        if not access_rules.edge_role_pair_allowed((roles[a],), (roles[b],)):
            continue
        ok = all(wet_room_policy.wet_room_entry_allowed(wet_by_id[x], y, (roles[y],))
                 for x, y in ((a, b), (b, a)) if x in wet_by_id)
        if ok:
            adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    dist = {src: 0}; q = [src]
    while q:
        x = q.pop(0)
        if x == dst:
            return dist[x]
        for y in adj.get(x, ()):
            if y not in dist:
                dist[y] = dist[x] + 1; q.append(y)
    return None


def _neighbours(p: Proposal, rid: str) -> list[str]:
    return sorted(o for e in p.spatial if rid in e for o in e if o != rid)


def _entry_rank(role: ProgramRole) -> int:
    if role in wet_room_policy.CIRCULATION_ENTRY_ROLES:
        return 0
    if role in wet_room_policy.PUBLIC_FALLBACK_ENTRY_ROLES:
        return 1
    if role in PUBLIC_ROLES:
        return 2
    return 3


def _demotion_priority(p: Proposal, e: frozenset) -> tuple:
    a, b = sorted(e)
    ra, rb = p.roles[a], p.roles[b]
    wet = {x for x in (a, b) if p.roles[x] in WET_ROLES}
    if wet and ({ra, rb} & set(PUBLIC_ROLES)):
        k = 0
    elif wet and ({ra, rb} & set(BEDROOM_ROLES)):
        k = 1
    elif len(wet) == 2:
        k = 2
    else:
        k = 3
    return (k, a, b)


def _representable(p: Proposal, spatial: frozenset, access) -> tuple[bool, object]:
    ids = list(p.roles)
    union = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted((a, b))) for a, b in access})
    if representation_precheck(ids, union) is not None or p.zones is None:
        return False, None
    emb = embed_band(p.zones, union, max_candidates=120)
    return isinstance(emb, BandEmbedding), emb


def _exposure_ok(p: Proposal, emb, wet, access) -> bool:
    return any(placement_flags(c, p.zones, wet, tuple(access))["exposure_ok"] for c in emb.candidates)


def repair(p: Proposal) -> RepairResult:
    before = criticize(p)
    repairs: list[Repair] = []
    roles = p.roles
    access = list(p.access)
    spatial = set(p.spatial)
    room_access = lambda: [(a, b) for a, b in access if a != ENTRANCE_ID and a in roles and b in roles]

    # ---- R1: one door per wet room
    for f in [f for f in before.findings if f.code == "WET_ROOM_MULTIPLE_ENTRANTS"]:
        rid = f.subjects[0]
        entrants = sorted({a if b == rid else b for a, b in room_access() if rid in (a, b)})
        ranked = sorted(entrants, key=lambda e: (_entry_rank(roles[e]), e))
        keep = ranked[0]
        wet_after = infer_wet_rooms(Proposal(p.name, roles, frozenset(spatial),
                                             tuple((a, b) for a, b in access if rid not in (a, b) or keep in (a, b)), p.zones))
        wet_by_id = {w.zone_id: w for w in wet_after}
        dropped = [e for e in entrants if e != keep]
        for e in dropped:
            access = [(a, b) for a, b in access if not ({a, b} == {rid, e})]
        kept_kind = next(w for w in wet_after if w.zone_id == rid)
        evidence = {"kept": keep, "kept_kind": kept_kind.kind.value, "dropped": dropped,
                    "dropped_still_reach_room_in_steps": {e: _legal_path_steps(access, roles, wet_by_id, e, rid) for e in dropped}}
        repairs.append(Repair("R1_ONE_DOOR_WET", f"{rid} doors from {entrants}", f"{rid} door from {keep} only",
                              f"a wet room has exactly one door (specs/007 FR-9); the proposal asked for a {roles[keep].value} "
                              f"door, which makes {rid} a {kept_kind.kind.value}; the dropped entrants still reach it through legal doors",
                              evidence, tuple(f"keep {e} only ({'ensuite of ' + e if roles[e] in BEDROOM_ROLES else 'shared'})" for e in dropped)))

    # ---- R2: illegal single entrant
    cur = Proposal(p.name, roles, frozenset(spatial), tuple(access), p.zones)
    wet_by_id = {w.zone_id: w for w in infer_wet_rooms(cur)}
    for a, b in list(room_access()):
        for x, y in ((a, b), (b, a)):
            if x in wet_by_id and not wet_room_policy.wet_room_entry_allowed(wet_by_id[x], y, (roles[y],)):
                cands = sorted((n for n in _neighbours(cur, x) if n != y and roles[n] not in WET_ROLES
                                and wet_room_policy.wet_room_entry_allowed(wet_by_id[x], n, (roles[n],))
                                and access_rules.edge_role_pair_allowed((roles[n],), (roles[x],))),
                               key=lambda n: (_entry_rank(roles[n]), n))
                if cands:
                    access = [(u, v) for u, v in access if {u, v} != {x, y}] + [(cands[0], x)]
                    repairs.append(Repair("R2_ILLEGAL_ENTRANT", f"{y}->{x}", f"{cands[0]}->{x}",
                                          f"{wet_room_policy.describe_rule(wet_by_id[x])}; {cands[0]} touches {x} and is a legal entrant",
                                          {"neighbours": _neighbours(cur, x)}))
                break

    # ---- R3: re-route unbacked direct access through a legal touching neighbour
    cur = Proposal(p.name, roles, frozenset(spatial), tuple(access), p.zones)
    wet_by_id = {w.zone_id: w for w in infer_wet_rooms(cur)}
    for a, b in list(room_access()):
        if frozenset((a, b)) in spatial:
            continue
        # which end is the "target" being entered: the one whose neighbours we search (try both)
        done = False
        for src, dst in ((a, b), (b, a)):
            if roles[dst] in WET_ROLES or roles[dst] in BEDROOM_ROLES or roles[dst] is ProgramRole.SAFE_ROOM:
                pass            # private/wet targets: a different entrant is a policy question, handled by R1/R2
            cands = []
            for n in _neighbours(cur, dst):
                if n == src or roles[n] in WET_ROLES:
                    continue
                if not access_rules.edge_role_pair_allowed((roles[n],), (roles[dst],)):
                    continue
                if dst in wet_by_id and not wet_room_policy.wet_room_entry_allowed(wet_by_id[dst], n, (roles[n],)):
                    continue
                if roles[dst] in BEDROOM_ROLES and roles[n] not in wet_room_policy.CIRCULATION_ENTRY_ROLES:
                    continue
                steps = _legal_path_steps([e for e in access if {e[0], e[1]} != {a, b}], roles, wet_by_id, src, n)
                if steps is not None:
                    cands.append((_entry_rank(roles[n]), steps, n))
            if cands:
                cands.sort(); n = cands[0][2]
                access = [(u, v) for u, v in access if {u, v} != {a, b}] + [(n, dst)]
                repairs.append(Repair("R3_REROUTE_ACCESS", f"{a}->{b} (no shared wall)", f"{n}->{dst}",
                                      f"a door needs a shared wall; {dst} touches {n}, a legal entrant reachable from {src} "
                                      f"in {cands[0][1]} legal step(s) — direct access becomes access through {n}",
                                      {"candidates": [c[2] for c in cands]}))
                done = True
                break
        if not done:
            repairs.append(Repair("R3_KEEP_AS_CONTACT", f"{a}->{b} (no shared wall)", f"{a}->{b} + required contact {a}-{b}",
                                  "no legal touching entrant can replace this door; the contact is required (as production does)"))

    # ---- R4 / R5: demote unbacked spatial contacts
    def demote(reason_code: str, accept) -> bool:
        nonlocal spatial
        cur_access = room_access()
        backed = {frozenset(e) for e in cur_access}
        pool = sorted((e for e in spatial if e not in backed), key=lambda e: _demotion_priority(cur, e))
        for k in (1, 2):
            for combo in combinations(pool, k):
                trial = frozenset(spatial - set(combo))
                ok, emb = _representable(cur, trial, cur_access)
                if ok and accept(emb, trial):
                    spatial = set(trial)
                    for e in combo:
                        a, b = sorted(e)
                        repairs.append(Repair(reason_code, f"required contact {a}-{b}", f"preferred contact {a}-{b} (not required)",
                                              "a wall contact no door uses; demoting it to a preference removes the obstruction",
                                              {"pool_size": len(pool), "set_size": k}))
                    return True
        return False

    cur = Proposal(p.name, roles, frozenset(spatial), tuple(access), p.zones)
    ok, emb = _representable(cur, frozenset(spatial), room_access())
    if not ok:
        demote("R4_DEMOTE_CONTACT", lambda e, s: True)
        cur = Proposal(p.name, roles, frozenset(spatial), tuple(access), p.zones)
        ok, emb = _representable(cur, frozenset(spatial), room_access())
    if ok and p.zones is not None and not _exposure_ok(cur, emb, infer_wet_rooms(cur), room_access()):
        demote("R5_DEMOTE_FOR_EXPOSURE", lambda e, s: _exposure_ok(cur, e, infer_wet_rooms(cur), room_access()))

    fixed = Proposal(p.name, roles, frozenset(spatial), tuple(access), p.zones)
    after = criticize(fixed)
    return RepairResult(p.name, repairs, [f"{f.code}: {f.detail}" for f in after.hard], before, after, fixed)


__all__ = ["Repair", "RepairResult", "repair"]
