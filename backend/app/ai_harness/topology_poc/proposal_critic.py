"""#142I prototype, productionized in #142J as `app.vertical_slice.proposal_critic`. This module is a
thin compatibility shim for the harness runners and the repair experiment."""
from __future__ import annotations

from app.vertical_slice.proposal_critic import (  # noqa: F401
    BEDROOM_ROLES, ENTRANCE_ID, WET_ROLES, CriticReport, Finding, Proposal, criticize, implied_wet_rooms,
)
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.spec import WetRoomKind
from app.vertical_slice.wet_rooms import ResolvedWetRoom


def from_fixture(bid: str, brief: dict, zones: dict | None = None, wet_rooms: tuple = ()) -> Proposal:
    roles = {r["id"]: ProgramRole(r["role"]) for r in brief["rooms"]}
    return Proposal(bid, roles, frozenset(frozenset(e) for e in brief["spatial_adjacency"]),
                    tuple((a, b) for a, b in brief["access_graph"]), zones, wet_rooms)


def from_topology_proposal(name: str, p, zones: dict | None = None, wet_rooms: tuple = ()) -> Proposal:
    roles = {rid: ProgramRole(role) for rid, role in p.role_by_id.items()}
    return Proposal(name, roles, frozenset(p.spatial_adjacency), tuple(sorted(p.access_graph)), zones, wet_rooms)


def infer_wet_rooms(p: Proposal) -> tuple:
    """The harness's historical kind inference (first bedroom entrant = ensuite), kept for the #142I
    repair experiment and its tests; production uses the brief's declared kinds (`assign_wet_room_kinds`)."""
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


__all__ = ["Finding", "Proposal", "CriticReport", "criticize", "from_fixture", "from_topology_proposal", "infer_wet_rooms"]
