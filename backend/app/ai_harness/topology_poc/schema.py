"""Structured topology proposal schema (Issue #151, AC-1).

The LLM produces no geometry — no coordinates, no widths, no polygons. `TopologyProposal` is the
object the critic (`critic.py`) actually scores, and it is deliberately the ONLY thing the critic
ever sees: no `source` field, no `realizability` field, nothing identifying where a proposal came
from lives on this type (see `critic.py`'s own docstring, AC-10). Provenance/realizability are
tracked on the separate `ProposalRecord` wrapper below, which is never passed to the critic.

ROOM IDENTITY vs ProgramRole (owner correction, AC-1): every room is `{id, role}` — `id` is the
specific instance ("BEDROOM_2"), `role` is the `ProgramRole` ("BEDROOM"). Every graph, zone and
cluster below references room IDS, never roles — two bedrooms or two bathrooms are always distinct
nodes. Role-level aggregation happens only inside the critic, to meet the corpus priors' own
role-pair grain (`critic.py`).

`ENTRANCE` is a reserved id, never a member of `rooms` — it mirrors the corrected #149 corpus's own
`front_door` graph node, which is not a room-role node either. It is valid ONLY as an endpoint of
`access_graph` edges (never `spatial_adjacency` — the front door does not "share a wall" with a
room; it is entered through).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.vertical_slice.geometry_core.model import ProgramRole

#: Reserved access-graph anchor id — never a room, never valid in `rooms` or `spatial_adjacency`.
ENTRANCE_ID = "ENTRANCE"

#: A room's own role may be any `ProgramRole` EXCEPT `ENTRANCE` itself — `ENTRANCE` names the
#: access anchor, never a habitable/functional room a proposal declares.
VALID_ROOM_ROLES = frozenset(r.value for r in ProgramRole if r is not ProgramRole.ENTRANCE)

VALID_ZONE_KEYS = frozenset({"public", "private", "service", "circulation"})

#: Qualitative-only vocabulary — never a number, never a coordinate (AC-1: no geometry fields).
RELATIVE_POSITION_RELATIONS = frozenset({"NORTH_OF", "SOUTH_OF", "EAST_OF", "WEST_OF"})

#: Exact key names (case-insensitive) that mark a geometry field wherever they appear, at any
#: nesting depth, in a raw proposal dict — AC-1's "no geometry field of any kind, proven by a test
#: that rejects any proposal carrying coordinates or dimensions". Matched by exact key name, never
#: substring, so legitimate schema field names (`relative_position`, `id`, `role`) are unaffected.
FORBIDDEN_GEOMETRY_KEYS = frozenset({
    "x", "y", "z", "x_m", "y_m", "z_m", "cx", "cy",
    "width", "width_m", "height", "height_m", "depth", "depth_m", "length", "length_m",
    "area", "area_m2", "gross_area_m2", "net_area_m2", "size_m2",
    "coordinates", "coords", "coordinate", "point", "points", "polygon", "polygons",
    "vertex", "vertices", "wall", "walls", "rect", "rectangle", "bbox", "bounding_box",
    "dimensions", "dims", "footprint", "centroid", "origin", "offset", "svg", "path",
})


class SchemaViolationError(ValueError):
    """Raised by every parsing/validation function in this module — never caught and hidden."""


def validate_no_geometry(raw: object, *, _path: str = "$") -> None:
    """Recursively rejects any dict key in `FORBIDDEN_GEOMETRY_KEYS` (exact match, case
    -insensitive) anywhere in `raw`. Called before a raw dict is trusted as a proposal at all."""
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str) and key.strip().lower() in FORBIDDEN_GEOMETRY_KEYS:
                raise SchemaViolationError(
                    f"geometry field {key!r} found at {_path}.{key} — proposals carry no "
                    "geometry of any kind (AC-1)")
            validate_no_geometry(value, _path=f"{_path}.{key}")
    elif isinstance(raw, (list, tuple)):
        for i, value in enumerate(raw):
            validate_no_geometry(value, _path=f"{_path}[{i}]")


@dataclass(frozen=True)
class RoomRef:
    id: str
    role: str


@dataclass(frozen=True)
class RelativePosition:
    room_id: str
    relation: str
    reference_room_id: str


@dataclass(frozen=True)
class EntranceRelation:
    opens_into: str
    sequence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TopologyProposal:
    """The ONLY object `critic.score_topology` accepts. No `source`, no `realizability`, no
    geometry field of any kind — see module docstring and `critic.py`'s AC-10 docstring."""

    rooms: tuple[RoomRef, ...]
    spatial_adjacency: frozenset  # frozenset[frozenset[str]] — unordered room-id pairs
    access_graph: frozenset  # frozenset[tuple[str, str]] — DIRECTED (from_id, to_id)
    zones: dict  # dict[str, tuple[str, ...]] — keys subset of VALID_ZONE_KEYS
    clusters: dict  # dict[str, tuple[str, ...]] — e.g. {"wet_core": (...)}
    relative_position: tuple  # tuple[RelativePosition, ...]
    entrance_relation: "EntranceRelation | None"
    design_tradeoff: str  # free text — explicitly NOT evidence, the critic never reads this

    @property
    def room_ids(self) -> frozenset:
        return frozenset(r.id for r in self.rooms)

    @property
    def role_by_id(self) -> dict:
        return {r.id: r.role for r in self.rooms}


class Realizability(str, Enum):
    REALIZABLE = "REALIZABLE_BY_CURRENT_ENGINE"
    NOT_REALIZABLE = "NOT_REALIZABLE_BY_CURRENT_ENGINE"
    UNKNOWN = "UNKNOWN"


class ProposalSource(str, Enum):
    CURRENT_GENERATOR = "CURRENT_GENERATOR"
    LLM = "LLM"


@dataclass(frozen=True)
class ProposalRecord:
    """Provenance/realizability wrapper — NEVER passed to `critic.score_topology` (AC-9, AC-10).
    Only the runner/report layer reads `source` and `realizability`."""

    brief_id: str
    proposal: TopologyProposal
    source: ProposalSource
    realizability: Realizability
    raw_index: int


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SchemaViolationError(message)


def _norm(value: object) -> object:
    """Strips incidental leading/trailing whitespace off a string id — pure formatting hygiene
    (an LLM emitting `" MASTER"` instead of `"MASTER"`), never a semantic relaxation: the id still
    has to match a real, declared room id exactly after normalization."""
    return value.strip() if isinstance(value, str) else value


def rooms_from_raw(raw_rooms: object) -> tuple:
    _require(isinstance(raw_rooms, list) and len(raw_rooms) > 0, "rooms must be a non-empty list")
    rooms = []
    seen_ids = set()
    for entry in raw_rooms:
        _require(isinstance(entry, dict), "each room must be an object")
        room_id = _norm(entry.get("id"))
        role = _norm(entry.get("role"))
        _require(isinstance(room_id, str) and room_id.strip() != "", "room id must be a non-empty string")
        _require(room_id != ENTRANCE_ID, f"{ENTRANCE_ID!r} is a reserved access anchor, not a room id")
        _require(room_id not in seen_ids, f"duplicate room id {room_id!r}")
        _require(isinstance(role, str) and role in VALID_ROOM_ROLES,
                 f"room {room_id!r} has invalid role {role!r} — must be one of {sorted(VALID_ROOM_ROLES)}")
        seen_ids.add(room_id)
        rooms.append(RoomRef(id=room_id, role=role))
    return tuple(rooms)


def _pair_from_raw(entry: object, *, directed: bool) -> tuple:
    _require(isinstance(entry, (list, tuple)) and len(entry) == 2,
             f"each {'access_graph' if directed else 'spatial_adjacency'} entry must be a 2-element pair")
    a, b = entry
    _require(isinstance(a, str) and isinstance(b, str), "pair endpoints must be room ids (strings)")
    return (_norm(a), _norm(b))


def spatial_adjacency_from_raw(raw_pairs: object, room_ids: frozenset) -> frozenset:
    _require(isinstance(raw_pairs, list), "spatial_adjacency must be a list")
    pairs = set()
    for entry in raw_pairs:
        a, b = _pair_from_raw(entry, directed=False)
        _require(a != ENTRANCE_ID and b != ENTRANCE_ID,
                 f"{ENTRANCE_ID!r} is not valid in spatial_adjacency — it has no shared wall, only access")
        _require(a in room_ids and b in room_ids,
                 f"spatial_adjacency references unknown room id(s): {a!r}, {b!r}")
        _require(a != b, f"spatial_adjacency cannot pair a room with itself: {a!r}")
        pairs.add(frozenset((a, b)))
    return frozenset(pairs)


def access_graph_from_raw(raw_pairs: object, room_ids: frozenset) -> frozenset:
    _require(isinstance(raw_pairs, list), "access_graph must be a list")
    valid_ids = room_ids | {ENTRANCE_ID}
    edges = set()
    for entry in raw_pairs:
        a, b = _pair_from_raw(entry, directed=True)
        _require(a in valid_ids and b in valid_ids,
                 f"access_graph references unknown room id(s): {a!r}, {b!r}")
        _require(b != ENTRANCE_ID, f"{ENTRANCE_ID!r} may only be an access source, never a target")
        _require(a != b, f"access_graph cannot pair a room with itself: {a!r}")
        edges.add((a, b))
    return frozenset(edges)


def zones_from_raw(raw_zones: object, room_ids: frozenset) -> dict:
    _require(isinstance(raw_zones, dict), "zones must be an object")
    _require(set(raw_zones.keys()) <= VALID_ZONE_KEYS,
             f"zones keys must be a subset of {sorted(VALID_ZONE_KEYS)}, got {sorted(raw_zones.keys())}")
    zones = {}
    for key, ids in raw_zones.items():
        _require(isinstance(ids, list), f"zones[{key!r}] must be a list of room ids")
        normalized = [_norm(rid) for rid in ids]
        for rid in normalized:
            _require(rid in room_ids, f"zones[{key!r}] references unknown room id {rid!r}")
        zones[key] = tuple(normalized)
    return zones


def clusters_from_raw(raw_clusters: object, room_ids: frozenset) -> dict:
    _require(isinstance(raw_clusters, dict), "clusters must be an object")
    clusters = {}
    for key, ids in raw_clusters.items():
        _require(isinstance(ids, list), f"clusters[{key!r}] must be a list of room ids")
        normalized = [_norm(rid) for rid in ids]
        for rid in normalized:
            _require(rid in room_ids, f"clusters[{key!r}] references unknown room id {rid!r}")
        clusters[key] = tuple(normalized)
    return clusters


def relative_position_from_raw(raw_list: object, room_ids: frozenset) -> tuple:
    if raw_list is None:
        return ()
    _require(isinstance(raw_list, list), "relative_position must be a list")
    out = []
    for entry in raw_list:
        _require(isinstance(entry, dict), "each relative_position entry must be an object")
        room_id = _norm(entry.get("room_id"))
        relation = _norm(entry.get("relation"))
        reference_room_id = _norm(entry.get("reference_room_id"))
        _require(room_id in room_ids, f"relative_position references unknown room id {room_id!r}")
        _require(reference_room_id in room_ids,
                 f"relative_position references unknown reference room id {reference_room_id!r}")
        _require(relation in RELATIVE_POSITION_RELATIONS,
                 f"relative_position relation {relation!r} must be one of {sorted(RELATIVE_POSITION_RELATIONS)}")
        out.append(RelativePosition(room_id=room_id, relation=relation, reference_room_id=reference_room_id))
    return tuple(out)


def entrance_relation_from_raw(raw: object, room_ids: frozenset) -> "EntranceRelation | None":
    if raw is None:
        return None
    _require(isinstance(raw, dict), "entrance_relation must be an object")
    opens_into = _norm(raw.get("opens_into"))
    _require(opens_into in room_ids, f"entrance_relation.opens_into references unknown room id {opens_into!r}")
    sequence = raw.get("sequence") or []
    _require(isinstance(sequence, list), "entrance_relation.sequence must be a list")
    #: ENTRANCE_ID is a legitimate first step of a qualitative entry sequence (describing the walk
    #: FROM the entrance) even though it is never a room in `rooms` itself.
    valid_sequence_ids = room_ids | {ENTRANCE_ID}
    normalized_sequence = [_norm(rid) for rid in sequence]
    for rid in normalized_sequence:
        _require(rid in valid_sequence_ids, f"entrance_relation.sequence references unknown room id {rid!r}")
    return EntranceRelation(opens_into=opens_into, sequence=tuple(normalized_sequence))


def proposal_from_dict(raw: dict) -> TopologyProposal:
    """Parses and fully validates one raw JSON-shaped proposal dict (AC-1). Raises
    `SchemaViolationError` on any geometry field, invalid role, dangling room-id reference, or
    malformed graph/zone/cluster entry — never silently drops or repairs bad data."""
    _require(isinstance(raw, dict), "a proposal must be a JSON object")
    validate_no_geometry(raw)

    rooms = rooms_from_raw(raw.get("rooms"))
    room_ids = frozenset(r.id for r in rooms)

    spatial_adjacency = spatial_adjacency_from_raw(raw.get("spatial_adjacency", []), room_ids)
    access_graph = access_graph_from_raw(raw.get("access_graph", []), room_ids)
    zones = zones_from_raw(raw.get("zones", {}), room_ids)
    clusters = clusters_from_raw(raw.get("clusters", {}), room_ids)
    relative_position = relative_position_from_raw(raw.get("relative_position"), room_ids)
    entrance_relation = entrance_relation_from_raw(raw.get("entrance_relation"), room_ids)
    design_tradeoff = raw.get("design_tradeoff", "")
    _require(isinstance(design_tradeoff, str), "design_tradeoff must be a string")

    return TopologyProposal(
        rooms=rooms, spatial_adjacency=spatial_adjacency, access_graph=access_graph,
        zones=zones, clusters=clusters, relative_position=relative_position,
        entrance_relation=entrance_relation, design_tradeoff=design_tradeoff)
