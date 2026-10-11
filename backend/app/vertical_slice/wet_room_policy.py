"""Canonical wet-room ENTRY policy — the ONE source of truth for "who may open a door into a wet
room" (Issue #142I). Every consumer derives from here:

  * `access_rules.ALLOWED_ENTERED_FROM` (role-level table, C24)   — `SHARED_WET_ROOM_ENTRY_ROLES`
  * `validation.py` C17 (realized doors vs the wet-room requirement) — `wet_room_entry_allowed`
  * `rectilinear_realizer._wet_room_edge_allowed` (door candidates) — `wet_room_entry_allowed`
  * `band_pipeline` selection legality / `access_policy_conflicts`  — `wet_room_entry_allowed`
  * `ai_harness.topology_poc.proposal_critic` (pre-realization)     — `wet_room_entry_allowed`

The rule (specs/007 FR-9 + specs/009 decision C):

  ENSUITE            exactly one door, from its host bedroom and nothing else.
  SHARED_BATHROOM /  exactly one door, from the public-access side of the house in this order of
  GUEST_WC           preference: HALL / CIRCULATION, then — as the last public-access fallback —
                     LIVING (specs/009 §0 decision C: "foyer / hall → public circulation → living
                     room. Never through a bedroom, never through the kitchen"; FR-4: "a public-access
                     zone counts as circulation for this purpose even when it is the living room").
                     KITCHEN and DINING are excluded by the same decision (and C29 fails closed on them).

History of the divergence this module closes (measured in docs/reports/142i-proposal-consistency):
`access_rules` (Issue #18) already encoded decision C for C24 — LIVING in the wet roles' allowed set;
`wet_privacy` C29 (Issue #37) deliberately left LIVING out of its hard-fail set citing the same
decision; but C17 (written for 007 before 009) and the realizer's `_wet_room_edge_allowed` (copied
from C17) still said "HALL/CIRCULATION only". Two rules, two answers, for the same door. Preference
among the allowed entries is a RANKING concern (`wet_privacy.candidate_privacy_key`), never a gate.
"""
from __future__ import annotations

from .geometry_core.model import ProgramRole
from .spec import WetRoomKind

#: Circulation-class entries for a shared wet room — the preferred ones.
CIRCULATION_ENTRY_ROLES: frozenset[ProgramRole] = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})
#: The last public-access fallback (specs/009 decision C, third choice). Ranked below circulation by
#: `wet_privacy`, never refused by a gate.
PUBLIC_FALLBACK_ENTRY_ROLES: frozenset[ProgramRole] = frozenset({ProgramRole.LIVING})
#: Everything a SHARED_BATHROOM / GUEST_WC may be entered from.
SHARED_WET_ROOM_ENTRY_ROLES: frozenset[ProgramRole] = CIRCULATION_ENTRY_ROLES | PUBLIC_FALLBACK_ENTRY_ROLES
#: Roles a wet room must never be entered from directly (decision C; C29's hard rule).
FORBIDDEN_ENTRY_ROLES: frozenset[ProgramRole] = frozenset({ProgramRole.KITCHEN, ProgramRole.DINING})


def wet_room_entry_allowed(wet, entrant_id: str, entrant_roles: tuple[ProgramRole, ...]) -> bool:
    """May a door connect `wet` (a `ResolvedWetRoom`-like: `.kind`, `.host_zone`) and the zone
    `entrant_id` carrying `entrant_roles`? Direction-free: a door is two-way."""
    if wet.kind is WetRoomKind.ENSUITE:
        return entrant_id == wet.host_zone
    roles = set(entrant_roles)
    if roles & FORBIDDEN_ENTRY_ROLES:
        return False
    return bool(roles & SHARED_WET_ROOM_ENTRY_ROLES)


def entry_rank(wet, entrant_id: str, entrant_roles: tuple[ProgramRole, ...]) -> int:
    """Preference order among ALLOWED entries (lower is better): 0 the host (ensuite) or circulation;
    1 the LIVING public fallback; 99 not allowed. A realizer that can give a shared wet room several
    legal doors keeps only the best-ranked class — a wet room has exactly ONE door (007 FR-9), and
    specs/009 decision C orders the public-access choices."""
    if not wet_room_entry_allowed(wet, entrant_id, entrant_roles):
        return 99
    if wet.kind is WetRoomKind.ENSUITE or set(entrant_roles) & CIRCULATION_ENTRY_ROLES:
        return 0
    return 1


def entry_roles_for(kind: WetRoomKind) -> frozenset[ProgramRole] | None:
    """The role set a wet room of this kind may be entered from; `None` for an ENSUITE (its entry is a
    specific zone, its host, not a role)."""
    if kind is WetRoomKind.ENSUITE:
        return None
    return SHARED_WET_ROOM_ENTRY_ROLES


def describe_rule(wet) -> str:
    if wet.kind is WetRoomKind.ENSUITE:
        return f"an ENSUITE is entered only from its host ({wet.host_zone})"
    names = "/".join(sorted(r.value for r in CIRCULATION_ENTRY_ROLES))
    fallback = "/".join(sorted(r.value for r in PUBLIC_FALLBACK_ENTRY_ROLES))
    return (f"a {wet.kind.value} is entered only from circulation ({names}) or, as the public-access "
            f"fallback, {fallback} (specs/009 decision C); never from a bedroom, KITCHEN or DINING")


__all__ = ["CIRCULATION_ENTRY_ROLES", "PUBLIC_FALLBACK_ENTRY_ROLES", "SHARED_WET_ROOM_ENTRY_ROLES",
           "FORBIDDEN_ENTRY_ROLES", "wet_room_entry_allowed", "entry_rank", "entry_roles_for", "describe_rule"]
