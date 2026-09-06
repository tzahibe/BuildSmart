"""`ArchitecturalConcept`: an instance-level room-access graph decided BEFORE geometry.

Two layouts belong to the same architectural CONCEPT when their instance-level, door-capable
adjacency graph is the same -- a translation, a mirror, or a small nudge that keeps every room
touching the same partners is the same concept expressed with different coordinates; a layout in
which a bedroom now opens off a corridor instead of the living room is a different concept. This
is the "concept vs. geometric variant" distinction: it is defined on WHICH room instances share a
door-capable wall, never on coordinates.

Edges are between room INSTANCES (e.g. "SAFE_ROOM" <-> "BEDROOM_2"), not types -- a type-level
rule ("safe_room direct_access bedroom") is satisfied by ANY pair; a concept commits to ONE pair,
and geometry is then required to realize exactly that pair.
"""
from dataclasses import dataclass, field

from app.geometry.models import RoomInstance
from app.geometry.solver import _DOOR_OPENING_MIN_M, _EPSILON, _shared_edge_length

# An `adjacency`-kind relationship only needs a nonzero shared wall (mirrors _relationship_satisfied);
# access/backbone/direct_access edges need a door-width one.
ADJACENCY_MIN_WALL_M = 0.05
DOOR_MIN_WALL_M = _DOOR_OPENING_MIN_M


@dataclass(frozen=True)
class InstanceEdge:
    a: str
    b: str
    kind: str  # "backbone" | "access" | "relationship:adjacency" | "relationship:direct_access"
    min_shared_wall_m: float = DOOR_MIN_WALL_M

    def key(self) -> frozenset[str]:
        return frozenset((self.a, self.b))


@dataclass(frozen=True)
class ArchitecturalConcept:
    concept_id: str
    entry_hub: str
    edges: tuple[InstanceEdge, ...]
    hub_of: dict[str, str] = field(default_factory=dict)  # destination instance -> hub instance
    tier_score: float = 0.0
    tier_components: dict[str, float] = field(default_factory=dict)
    hub_load: dict[str, int] = field(default_factory=dict)
    hub_capacity: dict[str, int] = field(default_factory=dict)

    @property
    def signature(self) -> frozenset[frozenset[str]]:
        return frozenset(edge.key() for edge in self.edges)


def unsatisfied_edges(edges: tuple[InstanceEdge, ...] | list[InstanceEdge], instances: list[RoomInstance]) -> list[InstanceEdge]:
    by_id = {room.id: room for room in instances}
    missing: list[InstanceEdge] = []
    for edge in edges:
        a, b = by_id.get(edge.a), by_id.get(edge.b)
        if a is None or b is None or _shared_edge_length(a, b) + _EPSILON < edge.min_shared_wall_m:
            missing.append(edge)
    return missing


def edges_satisfied(edges, instances: list[RoomInstance]) -> bool:
    return not unsatisfied_edges(edges, instances)


def realized_concept_signature(instances: list[RoomInstance]) -> frozenset[frozenset[str]]:
    """The concept a realized layout actually EXPRESSES: every instance pair sharing a door-capable
    wall. Invariant under translation/reflection/nudges that keep partners touching; changes when
    the access structure changes."""
    pairs: set[frozenset[str]] = set()
    for i in range(len(instances)):
        for j in range(i + 1, len(instances)):
            a, b = instances[i], instances[j]
            if _shared_edge_length(a, b) + _EPSILON >= DOOR_MIN_WALL_M:
                pairs.add(frozenset((a.id, b.id)))
    return frozenset(pairs)
