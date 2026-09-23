"""Stage 2 (B/2), Issue #134 — measuring what survived: PRESERVED/LOST per `RealizationIntent`
fact class.

Adapted from POC Issue #109's own `spikes/architectural_brain/preservation.py` (not merged to
`main`, transcribed per `docs/stage2/CONTRACT.md`'s own precedent), with two structural changes:

1. The donor-room <-> realized-zone correspondence comes from `contract.RoomIdentityChain`
   (`RealizedZone.donor_room_ids`) — never an ad hoc `donor_room_id_by_zone` dict rebuilt by
   re-matching. This is the exact bug `docs/stage2/CONTRACT.md` names as the root cause of the
   POC's own 38/136 `DONOR_ROOM_NOT_REALIZED` losses (Issue #133's own module docstring).
2. `REASON_GUILLOTINE_IMPOSSIBLE` does not exist here at all — Stage 2 never calls the guillotine
   engine (Required Behaviour 3), so a lost fact never carries that reason (AC-4). A donor fact the
   realized geometry did not honour is `REASON_NOT_HONOURED` here instead — the honest, Stage-2-own
   name for "both sides are realized, but this specific fact was not satisfied," e.g. by the
   ROW_ORDER_FROM_DONOR_PLACEMENT repair step collapsing a 2D adjacency graph into a 1D row.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .contract import RealizationIntent, RoomIdentityChain
from .intent import UNKNOWN, _connected_components, _relative_placement_for
from .realizer import RealizedLayout

SCHEMA_VERSION = "1.0"

REASON_DONOR_ROOM_NOT_REALIZED = "DONOR_ROOM_NOT_REALIZED"
REASON_NOT_HONOURED = "NOT_HONOURED"
REASON_BUDGET = "BUDGET"

_AREA_SHARE_TOLERANCE = 0.15
_FOOTPRINT_TOLERANCE = 0.15


@dataclass(frozen=True)
class LostFact:
    detail: str
    reason: str


@dataclass(frozen=True)
class FactClassResult:
    fact_class: str
    preserved: int
    total: int
    lost: tuple[LostFact, ...]

    @property
    def preserved_ratio(self) -> float | None:
        return self.preserved / self.total if self.total else None


@dataclass(frozen=True)
class PreservationReport:
    schema_version: str
    source_plan_id: str
    concept_id: str
    fact_classes: tuple[FactClassResult, ...]

    def fact_class(self, name: str) -> FactClassResult | None:
        return next((f for f in self.fact_classes if f.fact_class == name), None)

    def to_markdown(self) -> str:
        lines = [f"### PRESERVED / LOST — {self.concept_id} (donor {self.source_plan_id})", ""]
        lines.append("| fact class | preserved | total | ratio |")
        lines.append("|---|---|---|---|")
        for f in self.fact_classes:
            ratio = f"{f.preserved_ratio:.0%}" if f.preserved_ratio is not None else "n/a"
            lines.append(f"| {f.fact_class} | {f.preserved} | {f.total} | {ratio} |")
        lines.append("")
        any_lost = any(f.lost for f in self.fact_classes)
        if any_lost:
            lines.append("LOST facts:")
            lines.append("")
            for f in self.fact_classes:
                for lost in f.lost:
                    lines.append(f"- **{f.fact_class}** {lost.detail} — {lost.reason}")
            lines.append("")
        else:
            lines.append("LOST facts: none.")
            lines.append("")
        return "\n".join(lines)


def _zone_by_donor_id(chain: RoomIdentityChain) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for z in chain.realized_zones:
        for donor_id in z.donor_room_ids:
            mapping[donor_id] = z.zone_id
    return mapping


def _rects_touch(a: tuple[float, float, float, float], b: tuple[float, float, float, float],
                  eps: float = 1e-3) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2, bx2, by2 = ax + aw, ay + ah, bx + bw, by + bh
    vertical_touch = (abs(ax2 - bx) < eps or abs(bx2 - ax) < eps) and (min(ay2, by2) - max(ay, by) > eps)
    horizontal_touch = (abs(ay2 - by) < eps or abs(by2 - ay) < eps) and (min(ax2, bx2) - max(ax, bx) > eps)
    return vertical_touch or horizontal_touch


def _door_graph(design) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for room in design.rooms:
        graph.setdefault(room.zone_id, set())
    edges = [(d.a, d.b) for d in design.interior_doors]
    edges.append((design.entrance_door.a, design.entrance_door.b))
    for group in design.open_groups:
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                edges.append((a, b))
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph


def _reachable(graph: dict[str, set[str]], start: str, goal: str) -> bool:
    if start not in graph or goal not in graph:
        return False
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == goal:
            return True
        for nb in graph.get(node, ()):
            if nb not in seen:
                seen.add(nb)
                queue.append(nb)
    return start == goal


def _rooms_by_zone(design) -> dict:
    return {r.zone_id: r for r in design.rooms}


def _measure_adjacency(intent: RealizationIntent, design, donor_to_zone: dict[str, str]) -> FactClassResult:
    rooms = _rooms_by_zone(design)
    preserved = 0
    lost: list[LostFact] = []
    for fact in intent.adjacency_edges:
        za, zb = donor_to_zone.get(fact.room_a), donor_to_zone.get(fact.room_b)
        detail = f"{fact.room_a}-{fact.room_b}"
        if za is None or zb is None or za not in rooms or zb not in rooms:
            lost.append(LostFact(detail, REASON_DONOR_ROOM_NOT_REALIZED))
            continue
        if _rects_touch(rooms[za].rect_m, rooms[zb].rect_m):
            preserved += 1
        else:
            lost.append(LostFact(f"{detail} (realized {za}/{zb} do not touch)", REASON_NOT_HONOURED))
    return FactClassResult("adjacency", preserved, len(intent.adjacency_edges), tuple(lost))


def _measure_access(intent: RealizationIntent, design, donor_to_zone: dict[str, str]) -> FactClassResult:
    graph = _door_graph(design)
    preserved = 0
    lost: list[LostFact] = []
    for fact in intent.access_edges:
        za, zb = donor_to_zone.get(fact.room_a), donor_to_zone.get(fact.room_b)
        detail = f"{fact.room_a}-{fact.room_b} ({fact.kind})"
        if za is None or zb is None:
            lost.append(LostFact(detail, REASON_DONOR_ROOM_NOT_REALIZED))
            continue
        if _reachable(graph, za, zb):
            preserved += 1
        else:
            lost.append(LostFact(f"{detail} (realized {za}/{zb} not reachable)", REASON_NOT_HONOURED))
    return FactClassResult("access", preserved, len(intent.access_edges), tuple(lost))


def _exterior_side_count(room) -> int:
    from app.geometry_domain.walls import BoundaryContext
    return sum(1 for facts in room.wall_facts.values() if facts.boundary_context is BoundaryContext.EXTERIOR)


def _measure_exposure(intent: RealizationIntent, design, donor_to_zone: dict[str, str]) -> FactClassResult:
    rooms = _rooms_by_zone(design)
    preserved = 0
    lost: list[LostFact] = []
    total = 0
    for fact in intent.exterior_exposure:
        if not fact.known or not fact.sides:
            continue
        total += 1
        zone_id = donor_to_zone.get(fact.room_id)
        detail = f"{fact.room_id} (donor sides={list(fact.sides)})"
        if zone_id is None or zone_id not in rooms:
            lost.append(LostFact(detail, REASON_DONOR_ROOM_NOT_REALIZED))
            continue
        realized_count = _exterior_side_count(rooms[zone_id])
        if realized_count >= len(fact.sides):
            preserved += 1
        else:
            lost.append(LostFact(f"{detail}: realized {zone_id} has {realized_count} exterior "
                                  f"side(s)", REASON_NOT_HONOURED))
    return FactClassResult("exposure", preserved, total, tuple(lost))


def _realized_entrance_side(design) -> str:
    fx, fy, fw, fh = design.footprint_m
    cx, cy = design.entrance_door.center_m
    distances = {
        "N": abs(cy - fy), "S": abs(cy - (fy + fh)),
        "W": abs(cx - fx), "E": abs(cx - (fx + fw)),
    }
    return min(distances, key=distances.get)


def _measure_placement(intent: RealizationIntent, design, donor_to_zone: dict[str, str]) -> FactClassResult:
    rooms = _rooms_by_zone(design)
    fx, fy, fw, fh = design.footprint_m
    center = (fx + fw / 2.0, fy + fh / 2.0)
    entrance_side = _realized_entrance_side(design)

    preserved = 0
    lost: list[LostFact] = []
    total = 0
    for fact in intent.relative_placement:
        if fact.primary_axis == UNKNOWN and fact.secondary_axis == UNKNOWN:
            continue
        total += 1
        zone_id = donor_to_zone.get(fact.room_id)
        detail = f"{fact.room_id} (donor {fact.primary_axis}/{fact.secondary_axis})"
        if zone_id is None or zone_id not in rooms:
            lost.append(LostFact(detail, REASON_DONOR_ROOM_NOT_REALIZED))
            continue
        rx, ry, rw, rh = rooms[zone_id].rect_m
        centroid = (rx + rw / 2.0, ry + rh / 2.0)
        realized = _relative_placement_for(zone_id, centroid, center, entrance_side)
        primary_ok = fact.primary_axis == UNKNOWN or fact.primary_axis == realized.primary_axis
        secondary_ok = fact.secondary_axis == UNKNOWN or fact.secondary_axis == realized.secondary_axis
        if primary_ok and secondary_ok:
            preserved += 1
        else:
            lost.append(LostFact(
                f"{detail}: realized {zone_id} is {realized.primary_axis}/{realized.secondary_axis}",
                REASON_NOT_HONOURED))
    return FactClassResult("placement", preserved, total, tuple(lost))


def _cluster_result(name: str, donor_ids: tuple[str, ...], design, donor_to_zone: dict[str, str],
                     ) -> tuple[int, int, list[LostFact]]:
    rooms = _rooms_by_zone(design)
    zone_ids = [donor_to_zone[d] for d in donor_ids if d in donor_to_zone and donor_to_zone[d] in rooms]
    missing = [d for d in donor_ids if d not in donor_to_zone or donor_to_zone.get(d) not in rooms]
    lost: list[LostFact] = []
    for d in missing:
        lost.append(LostFact(f"{name}: {d}", REASON_DONOR_ROOM_NOT_REALIZED))
    if len(zone_ids) <= 1:
        return (1 if zone_ids or not donor_ids else 0), (1 if donor_ids else 0), lost
    edges = {
        frozenset((a, b))
        for i, a in enumerate(zone_ids) for b in zone_ids[i + 1:]
        if _rects_touch(rooms[a].rect_m, rooms[b].rect_m)
    }
    components = _connected_components(zone_ids, edges)
    if len(components) == 1:
        return 1, 1, lost
    lost.append(LostFact(f"{name}: split across {len(components)} disconnected groups",
                          REASON_NOT_HONOURED))
    return 0, 1, lost


def _measure_clusters(intent: RealizationIntent, design, donor_to_zone: dict[str, str]) -> FactClassResult:
    preserved = 0
    total = 0
    lost: list[LostFact] = []
    for name, ids in (("public", intent.public_private_clusters.public),
                       ("private", intent.public_private_clusters.private)):
        if not ids:
            continue
        p, t, cluster_lost = _cluster_result(name, ids, design, donor_to_zone)
        preserved += p
        total += t
        lost.extend(cluster_lost)
    return FactClassResult("clusters", preserved, total, tuple(lost))


def _measure_wet_core_groups(intent: RealizationIntent, design, donor_to_zone: dict[str, str],
                              ) -> FactClassResult:
    realized_clusters = design.wet_core.clusters if design.wet_core is not None else ()
    cluster_of: dict[str, int] = {}
    for i, cluster in enumerate(realized_clusters):
        for zid in cluster:
            cluster_of[zid] = i

    preserved = 0
    lost: list[LostFact] = []
    for group in intent.wet_core_groups:
        zone_ids = [donor_to_zone[d] for d in group if d in donor_to_zone]
        missing = [d for d in group if d not in donor_to_zone]
        detail = f"group {list(group)}"
        if missing or not zone_ids:
            lost.append(LostFact(f"{detail}: {missing or group} not realized",
                                  REASON_DONOR_ROOM_NOT_REALIZED))
            continue
        cluster_ids = {cluster_of.get(z) for z in zone_ids}
        if len(cluster_ids) == 1 and None not in cluster_ids:
            preserved += 1
        else:
            lost.append(LostFact(f"{detail}: realized zones {zone_ids} span different wet-core "
                                  f"clusters", REASON_NOT_HONOURED))
    return FactClassResult("wet_core_groups", preserved, len(intent.wet_core_groups), tuple(lost))


def _entrance_class_from_type(room_type: str | None) -> str:
    if room_type == "LIVING":
        return "TO_LIVING"
    if room_type == "CIRCULATION":
        return "TO_HALL"
    if room_type == "KITCHEN":
        return "TO_KITCHEN"
    return "TO_OTHER"


def _entrance_class_from_roles(roles: tuple[str, ...]) -> str:
    if "HALL" in roles or "CIRCULATION" in roles:
        return "TO_HALL"
    if "LIVING" in roles:
        return "TO_LIVING"
    if "KITCHEN" in roles:
        return "TO_KITCHEN"
    return "TO_OTHER"


def _measure_entrance_relationship(intent: RealizationIntent, design) -> FactClassResult:
    room_id = intent.entrance_relationship.room_id
    if room_id is None:
        return FactClassResult("entrance_relationship", 0, 0, ())
    room_type = next((p.room_type for p in intent.room_proportions if p.room_id == room_id), None)
    if room_type is None:
        return FactClassResult("entrance_relationship", 0, 0, ())
    donor_class = _entrance_class_from_type(room_type)
    realized_room = next((r for r in design.rooms if r.zone_id == design.entrance_door.b), None)
    realized_class = _entrance_class_from_roles(realized_room.roles if realized_room else ())
    if donor_class == realized_class:
        return FactClassResult("entrance_relationship", 1, 1, ())
    lost = LostFact(f"donor entrance -> {donor_class}, realized entrance -> {realized_class}",
                     REASON_NOT_HONOURED)
    return FactClassResult("entrance_relationship", 0, 1, (lost,))


def _measure_room_proportions(intent: RealizationIntent, design, donor_id_by_zone: dict[str, str],
                               ) -> FactClassResult:
    rooms = _rooms_by_zone(design)
    mapped_zone_ids = set(donor_id_by_zone)
    role_areas: dict[tuple[str, ...], list[float]] = {}
    for room in design.rooms:
        if room.zone_id in mapped_zone_ids:
            role_areas.setdefault(room.roles, []).append(room.net_area_m2)
    role_mean = {roles: sum(areas) / len(areas) for roles, areas in role_areas.items()}

    proportions_by_id = {p.room_id: p for p in intent.room_proportions}
    preserved = 0
    total = 0
    lost: list[LostFact] = []
    for zone_id, donor_id in donor_id_by_zone.items():
        proportion = proportions_by_id.get(donor_id)
        if proportion is None or zone_id not in rooms:
            continue
        total += 1
        room = rooms[zone_id]
        mean_for_role = role_mean.get(room.roles, room.net_area_m2)
        realized_share = room.net_area_m2 / mean_for_role if mean_for_role > 1e-9 else 1.0
        diff = abs(realized_share - proportion.area_share_of_type)
        if diff <= _AREA_SHARE_TOLERANCE * max(proportion.area_share_of_type, 1e-9):
            preserved += 1
        else:
            lost.append(LostFact(
                f"{donor_id}/{zone_id}: donor share={proportion.area_share_of_type:.3f}, "
                f"realized share={realized_share:.3f}", REASON_BUDGET))
    return FactClassResult("room_proportions", preserved, total, tuple(lost))


def _footprint_fill_ratio(design) -> float:
    fx, fy, fw, fh = design.footprint_m
    bbox_area = fw * fh
    if bbox_area <= 1e-9:
        return 1.0
    wings_area = sum(w[2] * w[3] for w in design.footprints_m)
    return min(wings_area / bbox_area, 1.0)


def _measure_footprint_relationships(intent: RealizationIntent, design) -> FactClassResult:
    donor = intent.footprint_relationships
    fx, fy, fw, fh = design.footprint_m
    realized_aspect = max(fw, fh) / min(fw, fh) if min(fw, fh) > 1e-9 else None
    realized_fill = _footprint_fill_ratio(design)

    preserved = 0
    total = 0
    lost: list[LostFact] = []
    if donor.aspect_ratio is not None and realized_aspect is not None:
        total += 1
        if abs(realized_aspect - donor.aspect_ratio) <= _FOOTPRINT_TOLERANCE * donor.aspect_ratio:
            preserved += 1
        else:
            lost.append(LostFact(
                f"aspect_ratio: donor={donor.aspect_ratio:.3f}, realized={realized_aspect:.3f}",
                REASON_NOT_HONOURED))
    if donor.fill_ratio is not None:
        total += 1
        if abs(realized_fill - donor.fill_ratio) <= _FOOTPRINT_TOLERANCE:
            preserved += 1
        else:
            lost.append(LostFact(
                f"fill_ratio: donor={donor.fill_ratio:.3f}, realized={realized_fill:.3f}",
                REASON_NOT_HONOURED))
    return FactClassResult("footprint_relationships", preserved, total, tuple(lost))


def measure_preservation(intent: RealizationIntent, realized: RealizedLayout,
                          chain: RoomIdentityChain) -> PreservationReport:
    """Every `RealizationIntent` fact class, measured against `realized.design` (a
    `design_output.GeometricDesign`) — `chain.realized_zones` (never an ad hoc dict) is the
    donor-room <-> realized-zone correspondence every measurement below uses."""
    design = realized.design
    donor_to_zone = _zone_by_donor_id(chain)
    donor_id_by_zone = {v: k for k, v in donor_to_zone.items()}
    fact_classes = (
        _measure_adjacency(intent, design, donor_to_zone),
        _measure_access(intent, design, donor_to_zone),
        _measure_exposure(intent, design, donor_to_zone),
        _measure_placement(intent, design, donor_to_zone),
        _measure_clusters(intent, design, donor_to_zone),
        _measure_wet_core_groups(intent, design, donor_to_zone),
        _measure_entrance_relationship(intent, design),
        _measure_room_proportions(intent, design, donor_id_by_zone),
        _measure_footprint_relationships(intent, design),
    )
    return PreservationReport(
        schema_version=SCHEMA_VERSION, source_plan_id=intent.source_plan_id,
        concept_id=intent.concept_id, fact_classes=fact_classes,
    )
