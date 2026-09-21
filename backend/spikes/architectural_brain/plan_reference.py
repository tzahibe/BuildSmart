"""``PlanReference`` — a versioned, metric JSON schema for one normalised ResPlan floor plan.

This is the shared contract POC agent A hands to agents B (retrieval/synthesis/adaptation) and C
(realization/demo). See ``resplan_ingest.py`` for how a raw ResPlan plan dict becomes a
``PlanReference``, ``patterns.py`` for the ``ArchitecturalPattern`` derived from one, and
``docs/reports/poc-architectural-brain/dataset.md`` for the field-by-field description of what is
derived by which rule.

Every coordinate is metric (metres), in the plan's own local frame (footprint at the origin
region as given by ResPlan's pixel grid, scaled — never re-centred or re-rotated). Anything not
measurably derivable from the source geometry is ``None`` / ``"UNKNOWN"`` — never guessed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0"

UNKNOWN = "UNKNOWN"
SIDES = ("N", "S", "E", "W")

Point = tuple[float, float]
Ring = tuple[Point, ...]


def _ring_to_list(ring: Ring) -> list[list[float]]:
    return [[round(float(x), 4), round(float(y), 4)] for x, y in ring]


def _ring_from_list(data: list) -> Ring:
    return tuple((float(x), float(y)) for x, y in data)


@dataclass(frozen=True)
class Room:
    """One functional room, or one residual CIRCULATION component.

    ``width_m``/``depth_m`` are the room's axis-aligned bounding-box extents (ResPlan geometry is
    grid-aligned) — never a claim about which axis architecturally reads as "width".

    ``exposure_known=False`` means the source plan carries no window geometry at all, so exposure
    cannot be measured; it is the honest UNKNOWN, distinct from ``exposure_known=True`` with an
    empty ``exterior_exposure`` (measured: no exposed side).
    """

    id: str
    type: str
    polygon: Ring
    area_m2: float
    width_m: float
    depth_m: float
    exterior_exposure: tuple[str, ...]
    exposure_known: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "polygon": _ring_to_list(self.polygon),
            "area_m2": round(self.area_m2, 4),
            "width_m": round(self.width_m, 4),
            "depth_m": round(self.depth_m, 4),
            "exterior_exposure": list(self.exterior_exposure),
            "exposure_known": self.exposure_known,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Room":
        return cls(
            id=d["id"], type=d["type"], polygon=_ring_from_list(d["polygon"]),
            area_m2=float(d["area_m2"]), width_m=float(d["width_m"]), depth_m=float(d["depth_m"]),
            exterior_exposure=tuple(d["exterior_exposure"]), exposure_known=bool(d["exposure_known"]),
        )


@dataclass(frozen=True)
class WallSegment:
    """One connected component of the plan's wall geometry, metric."""

    id: str
    polygon: Ring

    def to_dict(self) -> dict:
        return {"id": self.id, "polygon": _ring_to_list(self.polygon)}

    @classmethod
    def from_dict(cls, d: dict) -> "WallSegment":
        return cls(id=d["id"], polygon=_ring_from_list(d["polygon"]))


@dataclass(frozen=True)
class Door:
    """A door opening. ``room_ids`` holds the room(s) it joins — two rooms for an interior door,
    one room for an exterior door (the room it opens the building envelope from), empty if no
    room could be matched to its geometry (honestly reported, not guessed)."""

    id: str
    polygon: Ring
    room_ids: tuple[str, ...]
    is_exterior: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id, "polygon": _ring_to_list(self.polygon),
            "room_ids": list(self.room_ids), "is_exterior": self.is_exterior,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Door":
        return cls(id=d["id"], polygon=_ring_from_list(d["polygon"]),
                    room_ids=tuple(d["room_ids"]), is_exterior=bool(d["is_exterior"]))


@dataclass(frozen=True)
class Window:
    """A window opening. ``room_id`` is ``None`` (UNKNOWN) if no room could be matched; ``side`` is
    the footprint side (N/S/E/W) it sits on, or ``"UNKNOWN"`` if it is not near any footprint edge."""

    id: str
    polygon: Ring
    room_id: str | None
    side: str

    def to_dict(self) -> dict:
        return {"id": self.id, "polygon": _ring_to_list(self.polygon),
                "room_id": self.room_id, "side": self.side}

    @classmethod
    def from_dict(cls, d: dict) -> "Window":
        return cls(id=d["id"], polygon=_ring_from_list(d["polygon"]),
                    room_id=d["room_id"], side=d["side"])


@dataclass(frozen=True)
class Entrance:
    """The main entrance, from ResPlan's ``front_door``. Both fields are UNKNOWN together: a room
    could not be honestly attributed to a side without knowing which room it is."""

    room_id: str | None
    side: str

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "side": self.side}

    @classmethod
    def from_dict(cls, d: dict) -> "Entrance":
        return cls(room_id=d["room_id"], side=d["side"])


@dataclass(frozen=True)
class AdjacencyEdge:
    """Two rooms whose polygons share a wall (physically next to each other), independent of
    whether a door connects them."""

    room_a: str
    room_b: str

    def to_dict(self) -> dict:
        return {"room_a": self.room_a, "room_b": self.room_b}

    @classmethod
    def from_dict(cls, d: dict) -> "AdjacencyEdge":
        return cls(room_a=d["room_a"], room_b=d["room_b"])


@dataclass(frozen=True)
class AccessEdge:
    """Two rooms walkable between one another — via a door (``kind="DOOR"``)."""

    room_a: str
    room_b: str
    kind: str

    def to_dict(self) -> dict:
        return {"room_a": self.room_a, "room_b": self.room_b, "kind": self.kind}

    @classmethod
    def from_dict(cls, d: dict) -> "AccessEdge":
        return cls(room_a=d["room_a"], room_b=d["room_b"], kind=d["kind"])


@dataclass(frozen=True)
class Derived:
    """Basic measured facts about the normalisation itself — not architectural semantics (that is
    ``ArchitecturalPattern``, built from a ``PlanReference`` by ``patterns.py``)."""

    scale_m_per_px: float
    wall_thickness_m: float
    footprint_area_m2: float
    room_type_counts: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "scale_m_per_px": round(self.scale_m_per_px, 8),
            "wall_thickness_m": round(self.wall_thickness_m, 4),
            "footprint_area_m2": round(self.footprint_area_m2, 4),
            "room_type_counts": dict(self.room_type_counts),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Derived":
        return cls(scale_m_per_px=float(d["scale_m_per_px"]), wall_thickness_m=float(d["wall_thickness_m"]),
                    footprint_area_m2=float(d["footprint_area_m2"]), room_type_counts=dict(d["room_type_counts"]))


@dataclass(frozen=True)
class Provenance:
    source_dataset: str
    source_plan_id: str
    unit_type: str
    licence: str
    citation: str

    def to_dict(self) -> dict:
        return {
            "source_dataset": self.source_dataset, "source_plan_id": self.source_plan_id,
            "unit_type": self.unit_type, "licence": self.licence, "citation": self.citation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Provenance":
        return cls(source_dataset=d["source_dataset"], source_plan_id=d["source_plan_id"],
                    unit_type=d["unit_type"], licence=d["licence"], citation=d["citation"])


@dataclass(frozen=True)
class PlanReference:
    plan_id: str
    footprint: Ring
    rooms: tuple[Room, ...]
    walls: tuple[WallSegment, ...]
    doors: tuple[Door, ...]
    windows: tuple[Window, ...]
    entrance: Entrance
    adjacency_edges: tuple[AdjacencyEdge, ...]
    access_edges: tuple[AccessEdge, ...]
    derived: Derived
    provenance: Provenance
    schema_version: str = SCHEMA_VERSION

    def room(self, room_id: str) -> Room | None:
        return next((r for r in self.rooms if r.id == room_id), None)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "footprint": _ring_to_list(self.footprint),
            "rooms": [r.to_dict() for r in self.rooms],
            "walls": [w.to_dict() for w in self.walls],
            "doors": [d.to_dict() for d in self.doors],
            "windows": [w.to_dict() for w in self.windows],
            "entrance": self.entrance.to_dict(),
            "adjacency_edges": [e.to_dict() for e in self.adjacency_edges],
            "access_edges": [e.to_dict() for e in self.access_edges],
            "derived": self.derived.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanReference":
        return cls(
            schema_version=d["schema_version"],
            plan_id=d["plan_id"],
            footprint=_ring_from_list(d["footprint"]),
            rooms=tuple(Room.from_dict(r) for r in d["rooms"]),
            walls=tuple(WallSegment.from_dict(w) for w in d["walls"]),
            doors=tuple(Door.from_dict(x) for x in d["doors"]),
            windows=tuple(Window.from_dict(x) for x in d["windows"]),
            entrance=Entrance.from_dict(d["entrance"]),
            adjacency_edges=tuple(AdjacencyEdge.from_dict(x) for x in d["adjacency_edges"]),
            access_edges=tuple(AccessEdge.from_dict(x) for x in d["access_edges"]),
            derived=Derived.from_dict(d["derived"]),
            provenance=Provenance.from_dict(d["provenance"]),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "PlanReference":
        return cls.from_dict(json.loads(text))
