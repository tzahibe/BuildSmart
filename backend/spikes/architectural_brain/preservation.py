"""``measure_preservation(intent, plan, donor_room_id_by_zone) -> PreservationReport`` (Issue
#109, Phase 2 Track 3, POC-only): for each ``RealizationIntent`` fact class, how much of it
survived into the REALIZED geometry (``app.vertical_slice.general_pipeline.RealizedPlan``), as a
preserved/total count, and the explicit list of lost facts with a machine-readable reason.

``donor_room_id_by_zone`` (``realize.donor_room_id_by_zone(brief, adapted)``) is the ``zone_id ->
donor room id`` correspondence the SAME ``brief``/``adapted`` concept was compiled with — every
measurement below translates ``intent``'s donor-room-id-keyed facts onto the realized geometry's
own zone ids through it, and a donor room this mapping has no entry for (dropped by
``BEDROOM_COUNT_ADJUST``, or never individually resized) is reported LOST with reason
``DONOR_ROOM_NOT_REALIZED`` — never silently skipped.

WHAT "PRESERVED" MEANS PER FACT CLASS (only the REALIZED geometry is read — a fact is never
credited from the intent itself):

  * ``adjacency`` — the two realized rects (``RoomOut.rect_m``) share a positive-length edge
    (``_rects_touch``).
  * ``access`` — the two realized zones are connected in the realized DOOR graph
    (``interior_doors`` + ``entrance_door``) OR the same open-plan group (``design.open_groups`` —
    an ``OPEN_CONNECTION`` produces no physical door, but is still a real walkable connection).
  * ``exposure`` — compares EXTERIOR-FACING SIDE COUNT, not absolute compass letters: the donor's
    own plan frame and the realized building's are independent coordinate systems, so an "N" on
    one carries no relationship to an "N" on the other (only the COUNT of exposed sides is a
    frame-independent fact). Preserved when the realized room's own exterior side count is >= the
    donor's own.
  * ``placement`` — FRONT/REAR/LEFT/RIGHT/ABOVE/BELOW labels ARE frame-independent (both are
    computed relative to their OWN building's own entrance side and footprint centre, exactly
    ``realization_intent._relative_placement_for``'s own rule, reapplied here to the realized
    geometry via ``_realized_entrance_side``/``_realized_placement_for``). Preserved when every
    non-UNKNOWN axis label matches.
  * ``clusters`` — the donor-mapped PUBLIC (resp. PRIVATE) realized rooms form ONE connected
    component under realized adjacency (never split across an unrelated room).
  * ``wet_core_groups`` — every donor-mapped member of one intent group lands in the SAME realized
    ``design.wet_core`` cluster.
  * ``entrance_relationship`` — the donor's own entrance room TYPE (via ``room_proportions``,
    since ``EntranceRelationship`` itself only carries a room id) classified the SAME way
    ``patterns._entrance_relationship`` classifies a ``PlanReference`` (TO_LIVING/TO_HALL/
    TO_KITCHEN/TO_OTHER), compared against the realized entrance zone's own roles classified
    identically.
  * ``room_proportions`` — the realized room's own area SHARE among realized zones of the same
    role, compared to the donor's own ``area_share_of_type``, within ``_AREA_SHARE_TOLERANCE``.
  * ``footprint_relationships`` — the realized footprint's own ``fill_ratio``/``aspect_ratio``
    (computed identically to ``realization_intent._footprint_relationships``, off
    ``design.footprint_m``), compared to the donor's, within tolerance.

REASON TAXONOMY (every ``LostFact.reason`` is one of these, machine-readable, ``":"``-qualified
where the Issue's own taxonomy names a sub-reason):

  * ``DONOR_ROOM_NOT_REALIZED`` — the fact names a donor room `donor_room_id_by_zone` has no zone
    for (dropped or never individually resized by adaptation).
  * ``GUILLOTINE_IMPOSSIBLE`` — both rooms/facts ARE realized, but the compiled slicing tree did
    not place them the way the fact asked (the guillotine template this POC's ``realize.py`` uses
    never attempted to honour this specific fact — see that module's own docstring for exactly
    which facts it actively tries to satisfy today: room AREA proportions, nothing else).
  * ``BUDGET`` — the realized value is clipped by ``ROOM_TEMPLATES``' own [min, max] area bound
    (``room_proportions`` only).
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass

from spikes.architectural_brain.patterns import _connected_components
from spikes.architectural_brain.realization_intent import RealizationIntent, _relative_placement_for

SCHEMA_VERSION = "1.0"

REASON_DONOR_ROOM_NOT_REALIZED = "DONOR_ROOM_NOT_REALIZED"
REASON_GUILLOTINE_IMPOSSIBLE = "GUILLOTINE_IMPOSSIBLE"
REASON_BUDGET = "BUDGET"

#: `room_proportions`'s own relative-difference tolerance -- the realized area SHARE within this
#: fraction of the donor's own is "preserved" (grid quantization and template clipping mean an
#: exact match is not the honest bar -- see the module docstring's own `BUDGET` reason).
_AREA_SHARE_TOLERANCE = 0.15
#: `footprint_relationships`'s own tolerance, on `fill_ratio`/`aspect_ratio` independently.
_FOOTPRINT_TOLERANCE = 0.15


@dataclass(frozen=True)
class LostFact:
    detail: str
    reason: str

    def to_dict(self) -> dict:
        return {"detail": self.detail, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict) -> "LostFact":
        return cls(detail=d["detail"], reason=d["reason"])


@dataclass(frozen=True)
class FactClassResult:
    fact_class: str
    preserved: int
    total: int
    lost: tuple[LostFact, ...]

    @property
    def preserved_ratio(self) -> float | None:
        return self.preserved / self.total if self.total else None

    def to_dict(self) -> dict:
        return {
            "fact_class": self.fact_class, "preserved": self.preserved, "total": self.total,
            "preserved_ratio": round(self.preserved_ratio, 4) if self.preserved_ratio is not None else None,
            "lost": [f.to_dict() for f in self.lost],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FactClassResult":
        return cls(fact_class=d["fact_class"], preserved=d["preserved"], total=d["total"],
                   lost=tuple(LostFact.from_dict(x) for x in d["lost"]))


@dataclass(frozen=True)
class PreservationReport:
    schema_version: str
    source_plan_id: str
    concept_id: str
    fact_classes: tuple[FactClassResult, ...]

    def fact_class(self, name: str) -> FactClassResult | None:
        return next((f for f in self.fact_classes if f.fact_class == name), None)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source_plan_id": self.source_plan_id,
            "concept_id": self.concept_id,
            "fact_classes": [f.to_dict() for f in self.fact_classes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PreservationReport":
        return cls(schema_version=d["schema_version"], source_plan_id=d["source_plan_id"],
                   concept_id=d["concept_id"],
                   fact_classes=tuple(FactClassResult.from_dict(x) for x in d["fact_classes"]))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "PreservationReport":
        return cls.from_dict(json.loads(text))

    def to_markdown(self) -> str:
        """The PRESERVED / LOST block Issue #109 AC-4 requires in each brief's ``comparison.md``."""
        lines = [f"### PRESERVED / LOST -- {self.concept_id} (donor {self.source_plan_id})", ""]
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
                    lines.append(f"- **{f.fact_class}** {lost.detail} -- {lost.reason}")
            lines.append("")
        else:
            lines.append("LOST facts: none.")
            lines.append("")
        return "\n".join(lines)


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


def _measure_adjacency(intent: RealizationIntent, design, donor_to_zone: dict[str, str],
                       ) -> FactClassResult:
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
            lost.append(LostFact(f"{detail} (realized {za}/{zb} do not touch)",
                                 REASON_GUILLOTINE_IMPOSSIBLE))
    total = len(intent.adjacency_edges)
    return FactClassResult("adjacency", preserved, total, tuple(lost))


def _measure_access(intent: RealizationIntent, design, donor_to_zone: dict[str, str],
                    ) -> FactClassResult:
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
            lost.append(LostFact(f"{detail} (realized {za}/{zb} not reachable)",
                                 REASON_GUILLOTINE_IMPOSSIBLE))
    total = len(intent.access_edges)
    return FactClassResult("access", preserved, total, tuple(lost))


def _exterior_side_count(room) -> int:
    from app.geometry_domain.walls import BoundaryContext
    return sum(1 for facts in room.wall_facts.values() if facts.boundary_context is BoundaryContext.EXTERIOR)


def _measure_exposure(intent: RealizationIntent, design, donor_to_zone: dict[str, str],
                      ) -> FactClassResult:
    rooms = _rooms_by_zone(design)
    preserved = 0
    lost: list[LostFact] = []
    total = 0
    for fact in intent.exterior_exposure:
        if not fact.known or not fact.sides:
            continue  # nothing to preserve: donor itself has no (or zero) required exposure
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
            lost.append(LostFact(
                f"{detail}: realized {zone_id} has {realized_count} exterior side(s)",
                REASON_GUILLOTINE_IMPOSSIBLE))
    return FactClassResult("exposure", preserved, total, tuple(lost))


def _realized_entrance_side(design) -> str:
    """The realized building's own entrance compass side -- whichever edge of ``design.footprint_m``
    the entrance door's own centre sits nearest to, same N=min-y/S=max-y/W=min-x/E=max-x convention
    ``patterns._side_of_bbox_center``/``realization_intent`` already use."""
    fx, fy, fw, fh = design.footprint_m
    cx, cy = design.entrance_door.center_m
    distances = {
        "N": abs(cy - fy), "S": abs(cy - (fy + fh)),
        "W": abs(cx - fx), "E": abs(cx - (fx + fw)),
    }
    return min(distances, key=distances.get)


def _measure_placement(intent: RealizationIntent, design, donor_to_zone: dict[str, str],
                       ) -> FactClassResult:
    from spikes.architectural_brain.plan_reference import UNKNOWN

    rooms = _rooms_by_zone(design)
    fx, fy, fw, fh = design.footprint_m
    center = (fx + fw / 2.0, fy + fh / 2.0)
    entrance_side = _realized_entrance_side(design)

    preserved = 0
    lost: list[LostFact] = []
    total = 0
    for fact in intent.relative_placement:
        if fact.primary_axis == UNKNOWN and fact.secondary_axis == UNKNOWN:
            continue  # nothing measurable on the donor itself
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
                REASON_GUILLOTINE_IMPOSSIBLE))
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
                         REASON_GUILLOTINE_IMPOSSIBLE))
    return 0, 1, lost


def _measure_clusters(intent: RealizationIntent, design, donor_to_zone: dict[str, str],
                      ) -> FactClassResult:
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
            lost.append(LostFact(f"{detail}: realized zones {zone_ids} span different wet-core clusters",
                                 REASON_GUILLOTINE_IMPOSSIBLE))
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
                    REASON_GUILLOTINE_IMPOSSIBLE)
    return FactClassResult("entrance_relationship", 0, 1, (lost,))


def _measure_room_proportions(intent: RealizationIntent, design, donor_id_by_zone: dict[str, str],
                              ) -> FactClassResult:
    """Unlike every other `_measure_*` here, this one takes the ORIGINAL `zone_id -> donor room
    id` direction (`realize.donor_room_id_by_zone`'s own return shape) -- it needs to group
    realized rooms by ROLE first, which only the zone-keyed direction makes a single dict-comprehension."""
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
    """The realized footprint's own fill ratio -- 1.0 for a one-wing house (its footprint bounding
    box IS the footprint); the true fraction of the bounding box the summed wings occupy for a
    multi-wing (TWO_WING) plan, the same measure `realization_intent._footprint_relationships`
    uses on the donor."""
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
                REASON_GUILLOTINE_IMPOSSIBLE))
    if donor.fill_ratio is not None:
        total += 1
        if abs(realized_fill - donor.fill_ratio) <= _FOOTPRINT_TOLERANCE:
            preserved += 1
        else:
            lost.append(LostFact(
                f"fill_ratio: donor={donor.fill_ratio:.3f}, realized={realized_fill:.3f}",
                REASON_GUILLOTINE_IMPOSSIBLE))
    return FactClassResult("footprint_relationships", preserved, total, tuple(lost))


def measure_preservation(intent: RealizationIntent, plan, donor_room_id_by_zone: dict[str, str],
                         ) -> PreservationReport:
    """Issue #109 AC-3: measures every `RealizationIntent` fact class against `plan`'s own REALIZED
    geometry (`plan.design`, a `general_pipeline.RealizedPlan`'s own `GeometricDesign`) --
    `donor_room_id_by_zone` (`realize.donor_room_id_by_zone(brief, adapted)`) is the correspondence
    the SAME `brief`/`adapted` concept was compiled with. Nothing here re-reads `intent` itself as
    evidence -- every "preserved" count is a fact independently re-measured on `plan.design`.

    `intent`'s own facts (adjacency/access/exposure/placement/clusters/wet_core_groups) are keyed
    by DONOR room id, so every one of those measurements below needs the INVERSE correspondence
    (`zone_by_donor_id`) to reach a realized zone -- `_measure_room_proportions` is the one
    exception, needing the original zone-keyed direction (see its own docstring)."""
    design = plan.design
    zone_by_donor_id = {donor_id: zone_id for zone_id, donor_id in donor_room_id_by_zone.items()}
    fact_classes = (
        _measure_adjacency(intent, design, zone_by_donor_id),
        _measure_access(intent, design, zone_by_donor_id),
        _measure_exposure(intent, design, zone_by_donor_id),
        _measure_placement(intent, design, zone_by_donor_id),
        _measure_clusters(intent, design, zone_by_donor_id),
        _measure_wet_core_groups(intent, design, zone_by_donor_id),
        _measure_entrance_relationship(intent, design),
        _measure_room_proportions(intent, design, donor_room_id_by_zone),
        _measure_footprint_relationships(intent, design),
    )
    return PreservationReport(
        schema_version=SCHEMA_VERSION,
        source_plan_id=intent.source_plan_id,
        concept_id=intent.concept_id,
        fact_classes=fact_classes,
    )
