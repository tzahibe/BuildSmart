"""Room relationships a person asked for, and whether the BUILT plan actually delivers them.

One module, used by two callers that must never disagree: the pipeline consults it to pick between
realized candidates, and `validation.C15` consults it to gate the plan. Both evaluate the SAME
realized geometry through the same function, so a plan cannot be selected on one reading of
"adjacent" and validated on another.

FOUR DISTINCT RELATIONS, deliberately not collapsed into one another
--------------------------------------------------------------------
`ADJACENT` and `DIRECT_ACCESS` are different requests and are kept apart everywhere:
"חדר הורים צמוד לחדר הרחצה" asks for a shared wall, NOT for a door through it. Producing a door
because two rooms touch would be inventing an architectural decision the person never made — the
same class of defect as the renderer inferring doors. `DIRECT_ACCESS` is the wording that does ask
for one ("כניסה מ...", "דלת בין..."), and it reuses the topology the engine already has rather than
inventing a second mechanism.

`NEAR` is NOT a weaker `ADJACENT`. It has one deterministic meaning, fixed here:

    NEAR  ==  the shortest path between the two rooms over the REALIZED access graph is at most
              `NEAR_MAX_GRAPH_STEPS` (2) steps.

That is: you walk out of one room, through at most one other space, and you are there. It is
measured over `validation.realized_connections` — the same physical evidence C5 and C13 use, never
the declared topology — so a corridor between two rooms counts as one step and a wall you cannot
pass through counts not at all. Centroid distance was rejected: two rooms 3 m apart with a sealed
safe-room wall between them are not near each other in any sense a person means.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .geometry_core.model import ConnectionKind, Fixture, ProgramRole, Rect, u_to_m
from .spec import RelationStrength, RoomRelation, RoomRelationshipRequirement

#: A shared boundary shorter than this is a corner touch or a construction artefact, not an
#: adjacency anybody would call one. Set to a standard interior door width: if a boundary could not
#: hold a door, calling the rooms "adjacent" overstates what the plan gives.
MIN_MEANINGFUL_SHARED_BOUNDARY_M = 0.9

#: `NEAR` — at most one intervening space. See the module docstring.
NEAR_MAX_GRAPH_STEPS = 2


@dataclass(frozen=True)
class RelationshipOutcome:
    requirement: RoomRelationshipRequirement
    satisfied: bool
    detail: str                      # measured evidence, for support and tests
    statement: str                   # product language, for the plan screen

    @property
    def is_hard(self) -> bool:
        return self.requirement.strength is RelationStrength.HARD_REQUIREMENT


# --------------------------------------------------------------------------- room references

#: Role token -> how to find the matching zones in a realized fixture. A token may resolve to
#: SEVERAL zones ("חדרי הילדים" is every BEDROOM), which is not ambiguity — see `_holds` for how a
#: set is quantified per relation.
_ROLE_TOKENS = {
    "MASTER_BEDROOM": (ProgramRole.MASTER_BEDROOM,),
    "BEDROOM": (ProgramRole.BEDROOM,),
    "SAFE_ROOM": (ProgramRole.SAFE_ROOM,),
    "KITCHEN": (ProgramRole.KITCHEN,),
    "LIVING": (ProgramRole.LIVING,),
    "DINING": (ProgramRole.DINING,),
    "BATHROOM": (ProgramRole.BATHROOM,),
    "ENTRANCE": (ProgramRole.HALL, ProgramRole.CIRCULATION),
}

#: Tokens that need more than a role to resolve — handled in `resolve_reference`.
_DERIVED_TOKENS = ("ENSUITE", "GUEST_BATHROOM")

SUPPORTED_ROOM_TOKENS = tuple(_ROLE_TOKENS) + _DERIVED_TOKENS


def _ensuite_ids(fixture: Fixture) -> set[str]:
    """Bathrooms entered from a master bedroom, per the concept's own access topology."""
    masters = {z.zone_id for z in fixture.zones if ProgramRole.MASTER_BEDROOM in z.roles}
    baths = {z.zone_id for z in fixture.zones if ProgramRole.BATHROOM in z.roles}
    out = set()
    for edge in fixture.access.edges:
        if edge.kind is not ConnectionKind.DOOR:
            continue
        if edge.a in masters and edge.b in baths:
            out.add(edge.b)
        elif edge.b in masters and edge.a in baths:
            out.add(edge.a)
    return out


def resolve_reference(fixture: Fixture, token: str) -> set[str]:
    """Role token -> the zone ids it names in THIS plan. Empty when the plan has no such room."""
    if token == "ENSUITE":
        return _ensuite_ids(fixture)
    if token == "GUEST_BATHROOM":
        # "שירותי אורחים" is the guest WC when the plan actually has one — the room the programme
        # created for exactly this job. Only a plan with no WC falls back to its shared bathrooms.
        wcs = {z.zone_id for z in fixture.zones if ProgramRole.TOILET in z.roles}
        if wcs:
            return wcs
        baths = {z.zone_id for z in fixture.zones if ProgramRole.BATHROOM in z.roles}
        return baths - _ensuite_ids(fixture)
    roles = _ROLE_TOKENS.get(token)
    if roles is None:
        return set()
    return {z.zone_id for z in fixture.zones if any(r in z.roles for r in roles)}


# --------------------------------------------------------------------------- realized measurement

def shared_boundary_m(a: Rect, b: Rect) -> float:
    return u_to_m(a.shared_edge_len_u(b))


def _adjacent(a: str, b: str, rects: dict[str, Rect]) -> bool:
    if a not in rects or b not in rects:
        return False
    return shared_boundary_m(rects[a], rects[b]) >= MIN_MEANINGFUL_SHARED_BOUNDARY_M - 1e-9


def _touching_at_all(a: str, b: str, rects: dict[str, Rect]) -> bool:
    """Any shared boundary at all — what NOT_ADJACENT must rule out.

    Deliberately stricter than `_adjacent`: a request not to put a bedroom against the kitchen is
    not satisfied by giving them a 40 cm shared wall.
    """
    if a not in rects or b not in rects:
        return False
    return shared_boundary_m(rects[a], rects[b]) > 1e-9


def _graph_steps(a: str, b: str, connections) -> int | None:
    """Shortest path over the REALIZED access graph, in steps. `None` when unreachable."""
    adjacency: dict[str, set[str]] = {}
    for conn in connections:
        adjacency.setdefault(conn.a, set()).add(conn.b)
        adjacency.setdefault(conn.b, set()).add(conn.a)
    if a not in adjacency or b not in adjacency:
        return None
    seen = {a}
    queue = deque([(a, 0)])
    while queue:
        node, dist = queue.popleft()
        if node == b:
            return dist
        for nxt in sorted(adjacency.get(node, ())):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    return None


def _has_direct_access(a: str, b: str, connections) -> bool:
    return any({conn.a, conn.b} == {a, b} for conn in connections)


# --------------------------------------------------------------------------- evaluation

def _holds(requirement: RoomRelationshipRequirement, sources: set[str], targets: set[str],
           rects: dict[str, Rect], connections) -> tuple[bool, str]:
    """Does the realized plan satisfy one requirement? Returns (satisfied, measured evidence).

    Quantification over a set-valued reference is fixed per relation and is the reading a person
    means: a POSITIVE relation asks for at least one pair ("the safe room near the children's
    rooms" — near one of them is near them), a SEPARATION asks for every pair ("no bedroom next to
    the kitchen" — one offending bedroom breaks it).
    """
    pairs = [(s, t) for s in sorted(sources) for t in sorted(targets) if s != t]
    if not pairs:
        return False, "the plan has no such rooms"

    if requirement.relation is RoomRelation.NOT_ADJACENT:
        offending = [f"{s}/{t} {shared_boundary_m(rects[s], rects[t]):.2f} m"
                     for s, t in pairs if _touching_at_all(s, t, rects)]
        return (not offending), ("; ".join(offending) if offending
                                 else "no shared wall between any of them")

    if requirement.relation is RoomRelation.ADJACENT:
        best = max(((shared_boundary_m(rects[s], rects[t]) if s in rects and t in rects else 0.0),
                    f"{s}/{t}") for s, t in pairs)
        return (best[0] >= MIN_MEANINGFUL_SHARED_BOUNDARY_M - 1e-9,
                f"longest shared wall {best[1]} = {best[0]:.2f} m "
                f"(needs {MIN_MEANINGFUL_SHARED_BOUNDARY_M:.2f} m)")

    if requirement.relation is RoomRelation.DIRECT_ACCESS:
        ok = any(_has_direct_access(s, t, connections) for s, t in pairs)
        return ok, ("a door connects them" if ok else "no door or open join between them")

    # NEAR
    steps = [d for d in (_graph_steps(s, t, connections) for s, t in pairs) if d is not None]
    if not steps:
        return False, "no walking route between them"
    return (min(steps) <= NEAR_MAX_GRAPH_STEPS,
            f"{min(steps)} steps apart on foot (allowed {NEAR_MAX_GRAPH_STEPS})")


#: Product wording. Deliberately free of solver vocabulary — no zone ids, no graph steps.
#: Each token carries its subject form, its object form (already carrying the ל prefix, so the
#: sentence does not come out as "להמטבח"), and whether it is plural, so the verb agrees.
_ROOM_WORDS = {
    "MASTER_BEDROOM": ("חדר ההורים", "לחדר ההורים", False),
    "BEDROOM": ("חדרי השינה", "לחדרי השינה", True),
    "SAFE_ROOM": ('הממ"ד', 'לממ"ד', False),
    "KITCHEN": ("המטבח", "למטבח", False),
    "LIVING": ("הסלון", "לסלון", False),
    "DINING": ("פינת האוכל", "לפינת האוכל", False),
    "BATHROOM": ("חדרי הרחצה", "לחדרי הרחצה", True),
    "ENSUITE": ("חדר הרחצה של ההורים", "לחדר הרחצה של ההורים", False),
    "GUEST_BATHROOM": ("שירותי האורחים", "לשירותי האורחים", False),
    "ENTRANCE": ("הכניסה", "לכניסה", False),
}

#: relation -> (singular phrase, plural phrase)
_RELATION_WORDS = {
    RoomRelation.ADJACENT: ("צמוד", "צמודים"),
    RoomRelation.NOT_ADJACENT: ("אינו צמוד", "אינם צמודים"),
    RoomRelation.NEAR: ("קרוב", "קרובים"),
    RoomRelation.DIRECT_ACCESS: ("עם מעבר ישיר", "עם מעבר ישיר"),
}


def describe(requirement: RoomRelationshipRequirement) -> str:
    subject, _, plural = _ROOM_WORDS.get(
        requirement.source_role, (requirement.source_role, requirement.source_role, False))
    _, target, _ = _ROOM_WORDS.get(
        requirement.target_role, (requirement.target_role, requirement.target_role, False))
    phrase = _RELATION_WORDS[requirement.relation][1 if plural else 0]
    return f"{subject} {phrase} {target}"


def evaluate(fixture: Fixture, rects: dict[str, Rect], connections,
             requirements) -> list[RelationshipOutcome]:
    """Every requirement measured against the plan that was actually built."""
    out: list[RelationshipOutcome] = []
    for requirement in requirements:
        sources = resolve_reference(fixture, requirement.source_role)
        targets = resolve_reference(fixture, requirement.target_role)
        satisfied, detail = _holds(requirement, sources, targets, rects, connections)
        out.append(RelationshipOutcome(requirement, satisfied, detail, describe(requirement)))
    return out
