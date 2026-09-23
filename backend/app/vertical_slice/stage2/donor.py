"""Stage 2 (B/2), Issue #134 — loading one donor plan's own partition.

A lean transcription of the fields `spikes/architectural_brain/plan_reference.py` (POC Issue #109,
not merged to `main`, not importable — see `docs/stage2/CONTRACT.md`'s own "transcribed, not
imported" precedent) already gets right, trimmed to exactly what seeding/repair/intent-building need
(room polygon, area, type, exposure; the entrance; adjacency/access edges) — no `Door`/`Window`/
`WallSegment`/`Derived`/`Provenance` metadata, which nothing downstream of this Issue reads.

`load_donor_plan` reads the SAME fixture format Issue #133's own test already uses
(`tests/spikes/fixtures/geometry_shapes/plans/*.json`, `{"architectural_pattern": ..., "plan_reference":
{...}}`) — a real, licensed ResPlan fixture, never a hand-invented one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

Point = tuple[float, float]
Ring = tuple[Point, ...]


@dataclass(frozen=True)
class DonorRoom:
    id: str
    type: str
    polygon_m: Ring
    area_m2: float
    width_m: float
    depth_m: float
    exterior_exposure: tuple[str, ...]
    exposure_known: bool

    @property
    def centroid_m(self) -> Point:
        xs = [p[0] for p in self.polygon_m]
        ys = [p[1] for p in self.polygon_m]
        return (sum(xs) / len(xs), sum(ys) / len(ys))


@dataclass(frozen=True)
class DonorPlan:
    plan_id: str
    footprint_m: Ring
    rooms: tuple[DonorRoom, ...]
    entrance_room_id: str | None
    entrance_side: str
    adjacency_edges: tuple[tuple[str, str], ...]
    access_edges: tuple[tuple[str, str, str], ...]  # (room_a, room_b, kind)

    def room(self, room_id: str) -> DonorRoom | None:
        return next((r for r in self.rooms if r.id == room_id), None)


def _ring(data: list) -> Ring:
    return tuple((float(x), float(y)) for x, y in data)


def load_donor_plan(path: str) -> DonorPlan:
    """`path` names a `tests/spikes/fixtures/geometry_shapes/plans/*.json` file — the SAME real
    ResPlan fixture format Issue #133's own `test_stage2_contract.py` already reads."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    ref = raw["plan_reference"]
    rooms = tuple(
        DonorRoom(
            id=r["id"], type=r["type"], polygon_m=_ring(r["polygon"]), area_m2=float(r["area_m2"]),
            width_m=float(r["width_m"]), depth_m=float(r["depth_m"]),
            exterior_exposure=tuple(r["exterior_exposure"]), exposure_known=bool(r["exposure_known"]),
        )
        for r in ref["rooms"]
    )
    return DonorPlan(
        plan_id=ref["plan_id"],
        footprint_m=_ring(ref["footprint"]),
        rooms=rooms,
        entrance_room_id=ref["entrance"]["room_id"],
        entrance_side=ref["entrance"]["side"],
        adjacency_edges=tuple((e["room_a"], e["room_b"]) for e in ref["adjacency_edges"]),
        access_edges=tuple((e["room_a"], e["room_b"], e["kind"]) for e in ref["access_edges"]),
    )
