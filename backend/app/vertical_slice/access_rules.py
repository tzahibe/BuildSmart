"""Stage 8 — Access-topology door rules (Issue #18).

`doors.py::generate_interior_doors` places one `Door` per non-OPEN_CONNECTION edge in the
fixture's `DesiredAccessTopology`, but nothing previously said WHICH role pairs a door may
legitimately connect, or how wide a door should be for the room it serves. Both live here:

  * `ALLOWED_ENTERED_FROM` — for every `ProgramRole`, which roles the room may be entered FROM.
    A PRIVATE room (bedroom-class) is entered only from circulation; a wet room (BATHROOM/
    TOILET) additionally from its own hosting bedroom (an ensuite) and, as the last public-access
    fallback, from LIVING — `specs/009-guest-wc-placement` decision C names HALL/circulation, then
    the hosting bedroom, then LIVING as the guest WC's third-choice public-access zone; KITCHEN and
    DINING stay disallowed, decision C excludes them explicitly; a narrow SERVICE room
    (LAUNDRY/STORAGE) additionally from the kitchen; a public room from any public/circulation
    room. `edge_role_pair_allowed` checks one edge against the table; together these are what
    rules out a bedroom-to-bedroom door without naming that pair specially — it is simply never
    in any role's allowed set.
  * `DoorKind`/`DOOR_WIDTH_M` — the physical door width class: `ROOM_DOOR` (0.9 m, the historic
    interior width, unchanged), `SERVICE_DOOR` (0.8 m, narrower — LAUNDRY, STORAGE, TOILET only),
    `ENTRANCE_DOOR` (1.0 m, unchanged). `door_kind_for_zones` picks the class for one edge from
    the two zones' roles.
  * `check_access_topology` — C24's three rules, evaluated together: every enclosed (non-open)
    room has at least one declared DOOR/CASED_OPENING edge; every declared edge's role pair is
    one the table allows; and no room is reachable from the entrance only by continuing past
    another PRIVATE room (walked over the REALIZED graph, not the declared one — a wall
    accidentally typed OPEN between two rooms creates a real connection the declared topology
    never mentioned, and the chain rule has to see that too, not just re-check declared edges).
    `validation.py` wires this in as check C24.
"""
from __future__ import annotations

from enum import Enum

from .geometry_core.model import ConnectionKind, Fixture, ProgramRole

# --------------------------------------------------------------------------- door kinds/widths

class DoorKind(str, Enum):
    ROOM_DOOR = "ROOM_DOOR"
    SERVICE_DOOR = "SERVICE_DOOR"
    ENTRANCE_DOOR = "ENTRANCE_DOOR"


DOOR_WIDTH_M: dict[DoorKind, float] = {
    DoorKind.ROOM_DOOR: 0.9,
    DoorKind.SERVICE_DOOR: 0.8,
    DoorKind.ENTRANCE_DOOR: 1.0,
}

#: Roles whose door is a SERVICE_DOOR rather than a ROOM_DOOR. BATHROOM keeps ROOM_DOOR width —
#: only the utility rooms and the WC-only wet room take the narrower leaf.
SERVICE_DOOR_ROLES = frozenset({ProgramRole.LAUNDRY, ProgramRole.STORAGE, ProgramRole.TOILET})


def door_kind_for_zones(roles_a: tuple[ProgramRole, ...], roles_b: tuple[ProgramRole, ...]) -> DoorKind:
    """The door kind for an interior edge between two zones, from their roles alone."""
    if SERVICE_DOOR_ROLES.intersection(roles_a) or SERVICE_DOOR_ROLES.intersection(roles_b):
        return DoorKind.SERVICE_DOOR
    return DoorKind.ROOM_DOOR


# --------------------------------------------------------------------------- role-pair table

#: Public/habitable rooms a person moves through freely.
PUBLIC_ROLES = frozenset({
    ProgramRole.ENTRANCE, ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN,
    ProgramRole.FAMILY_ROOM, ProgramRole.FLEX,
})
#: Circulation proper.
CIRCULATION_ROLES = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})
PUBLIC_OR_CIRCULATION = PUBLIC_ROLES | CIRCULATION_ROLES
#: Habitable PRIVATE rooms: entered only from circulation, never from each other.
PRIVATE_ROLES = frozenset({
    ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM, ProgramRole.SAFE_ROOM,
    ProgramRole.STUDY, ProgramRole.DRESSING_ROOM,
})
#: The bedroom-class roles that may host an ensuite.
BEDROOM_HOST_ROLES = frozenset({ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM})
#: Wet rooms: circulation, or (for an ensuite) their own hosting bedroom, or (last public-access
#: fallback, specs/009-guest-wc-placement decision C) LIVING. KITCHEN and DINING stay disallowed.
WET_ROLES = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET})
#: Narrow service rooms: circulation, or the kitchen they serve.
SERVICE_ROLES = frozenset({ProgramRole.LAUNDRY, ProgramRole.STORAGE})

#: For each `ProgramRole`, the roles a room of that role may be entered FROM. A `STAIRWELL` is
#: circulation itself (a vertical core may sit directly off an open-plan public room, not only
#: off a hall), so it is held to the same set as HALL/CIRCULATION rather than to PRIVATE_ROLES'
#: narrower one.
ALLOWED_ENTERED_FROM: dict[ProgramRole, frozenset[ProgramRole]] = {
    **{role: PUBLIC_OR_CIRCULATION for role in PUBLIC_ROLES},
    ProgramRole.HALL: PUBLIC_OR_CIRCULATION,
    ProgramRole.CIRCULATION: PUBLIC_OR_CIRCULATION,
    ProgramRole.STAIRWELL: PUBLIC_OR_CIRCULATION,
    **{role: CIRCULATION_ROLES for role in PRIVATE_ROLES},
    **{role: CIRCULATION_ROLES | BEDROOM_HOST_ROLES | {ProgramRole.LIVING} for role in WET_ROLES},
    **{role: CIRCULATION_ROLES | {ProgramRole.KITCHEN} for role in SERVICE_ROLES},
}


def _enterable_from(role: ProgramRole, other_roles: tuple[ProgramRole, ...]) -> bool:
    allowed = ALLOWED_ENTERED_FROM.get(role)
    if allowed is None:
        return True
    return any(r in allowed for r in other_roles)


def edge_role_pair_allowed(roles_a: tuple[ProgramRole, ...], roles_b: tuple[ProgramRole, ...]) -> bool:
    """Is a DOOR/CASED_OPENING edge between a zone carrying `roles_a` and one carrying `roles_b`
    permitted, in either direction? A zone can carry more than one role (a safe room that is also
    a bedroom), so this passes when ANY role on either side is a legal "entered from" for ANY
    role on the other."""
    return (any(_enterable_from(ra, roles_b) for ra in roles_a)
            or any(_enterable_from(rb, roles_a) for rb in roles_b))


# --------------------------------------------------------------------------- C24

def _missing_door_defects(fixture: Fixture) -> list[str]:
    open_zone_ids = {zone_id for group in fixture.open_groups for zone_id in group}
    touched = {zone_id for e in fixture.access.edges if e.kind is not ConnectionKind.OPEN_CONNECTION
               for zone_id in (e.a, e.b)}
    return [f"{z.zone_id}: no DOOR/CASED_OPENING edge at all — an enclosed room with no way in"
            for z in fixture.zones if z.zone_id not in open_zone_ids and z.zone_id not in touched]


def _role_pair_defects(fixture: Fixture) -> list[str]:
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    defects = []
    for e in fixture.access.edges:
        if e.kind is ConnectionKind.OPEN_CONNECTION:
            continue
        roles_a, roles_b = roles_of.get(e.a), roles_of.get(e.b)
        if roles_a is None or roles_b is None:
            continue  # a zone missing from the plan is C13's concern, not this table's
        if not edge_role_pair_allowed(roles_a, roles_b):
            defects.append(
                f"{e.a}-{e.b} ({e.kind.value}): role pair "
                f"{[r.value for r in roles_a]}/{[r.value for r in roles_b]} is not allowed by "
                f"the access-rules table")
    return defects


def _private_chain_defects(fixture: Fixture, graph: dict[str, set[str]], entry_seed: str) -> list[str]:
    roles_of = {z.zone_id: z.roles for z in fixture.zones}

    def is_private(zone_id: str) -> bool:
        return bool(PRIVATE_ROLES.intersection(roles_of.get(zone_id, ())))

    def legitimate_child_of_private(parent: str, child: str) -> bool:
        # The one sanctioned continuation past a PRIVATE room: its own ensuite.
        return (bool(WET_ROLES.intersection(roles_of.get(child, ())))
                and bool(BEDROOM_HOST_ROLES.intersection(roles_of.get(parent, ()))))

    def walk(*, allow_chain: bool) -> set[str]:
        seen = {entry_seed}
        frontier = [entry_seed]
        while frontier:
            cur = frontier.pop()
            for nxt in graph.get(cur, ()):
                if nxt in seen:
                    continue
                if is_private(cur) and not (allow_chain or legitimate_child_of_private(cur, nxt)):
                    continue
                seen.add(nxt)
                frontier.append(nxt)
        return seen

    reachable = walk(allow_chain=True)
    clean = walk(allow_chain=False)
    all_zone_ids = {z.zone_id for z in fixture.zones}
    return [f"{zone_id}: reachable from the entrance only by continuing on through another "
            f"PRIVATE room"
            for zone_id in sorted((reachable - clean) & all_zone_ids)]


def check_access_topology(fixture: Fixture, graph: dict[str, set[str]], entry_seed: str) -> list[str]:
    """All of C24's defects for one fixture: missing doors, disallowed role pairs (which also
    covers "no PRIVATE-to-PRIVATE door except the ensuite host"), and private-room chains,
    evaluated over the REALIZED access `graph` (as built for C5 — zone id -> connected zone ids)
    seeded at `entry_seed`."""
    return (_missing_door_defects(fixture)
            + _role_pair_defects(fixture)
            + _private_chain_defects(fixture, graph, entry_seed))
