"""Bounded, deterministic generation of `ArchitecturalConcept` candidates from an ArchitecturalSpec
-- graph-only, no geometry. This is the planning decision that used to be an accident of rectangle
placement: which hub serves each destination room, how hubs connect to the entry hub, and which
specific instance pair realizes each hard type-level relationship.

Generic by construction: driven by transit roles per room type (roles.py), zones (spatial_v2.intent,
which prefers the spec's own zones), the program's instance list, and its relationships -- never by a
scenario name, fixture, or hardcoded topology. A future Architect LLM can steer this by supplying the
same inputs (roles/zones/relationships/circulation) for an unseen program.
"""
import itertools
import math
from dataclasses import dataclass

from app.architect.models import ArchitecturalSpec, ConstraintKind, ConstraintSeverity, ProgramItem
from app.geometry.instances import expand_program_to_instances
from app.geometry.planning.concept import ADJACENCY_MIN_WALL_M, DOOR_MIN_WALL_M, ArchitecturalConcept, InstanceEdge
from app.geometry.planning.roles import ENTRY_HUB_PREFERENCE, LIMITED_HUB_MAX_DESTINATIONS, transit_role
from app.geometry.solver import _ASPECT_RATIOS, _DEFAULT_TARGET_AREA_M2
from app.geometry.spatial_v2.intent import Zone, zone_by_room_type

MAX_CONCEPTS = 8                 # concepts handed to geometry, after tier scoring + dedup
MAX_HUB_DISTRIBUTIONS = 40       # raw destination->hub distributions considered before scoring
MAX_CIRCULATION_SEGMENTS = 3     # bounded escalation -- never unbounded, matches Spatial V1's
                                  # earlier validated "smallest circulation structure that can
                                  # plausibly serve the program" policy
_MIN_CORRIDOR_AREA_M2 = 2.4
_MAX_CORRIDOR_AREA_M2 = 8.0
_CORRIDOR_AREA_STEP_M2 = 0.5
# Usable-perimeter fractions: NOT re-derived here -- these are the exact values previously
# calibrated against direct bisection of the real CP-SAT/backtracking geometry (a functional room's
# own perimeter estimate of ~0.16 matched an observed max degree of 2-3 on rooms this size; a
# circulation room's ~0.40 matched an observed max degree of 3 on a 3 m2 corridor). A first attempt
# at this module used un-calibrated guesses (0.35/0.5) and the resulting capacity estimate was
# proven wrong immediately: it predicted degree 7 for a 20 m2 living room whose REAL ceiling
# (measured directly against generate_valid_candidate_pool's own unconstrained solutions) is 3.
_USABLE_PERIMETER_FRACTION_HUB = 0.40           # circulation-type rooms exist to host openings
_USABLE_PERIMETER_FRACTION_OTHER = 0.16         # functional rooms keep most perimeter for furniture

W_PRIVACY_GATING = 2.0
W_LOAD_BALANCE = 1.0
W_RELATIONSHIP_LOCALITY = 1.5
W_SERVICE_GROUPING = 1.0
_TIER_WEIGHT_TOTAL = W_PRIVACY_GATING + W_LOAD_BALANCE + W_RELATIONSHIP_LOCALITY + W_SERVICE_GROUPING


def estimate_hub_capacity(item: ProgramItem | None, room_type: str) -> int:
    """Coarse pre-geometry reject for obviously impossible hub degrees ("7 doors on a 5 m2
    room"), derived from the most elongated rectangle the solver's own shape candidates can produce
    (`_ASPECT_RATIOS`) and a door width -- geometry remains the feasibility oracle; this only
    filters the absurd. Not a per-type magic number: a 3 m2 corridor and a 30 m2 living room get
    different capacities from the same formula."""
    area = (item.target_area_m2 if item is not None and item.target_area_m2 else None) or _DEFAULT_TARGET_AREA_M2
    max_aspect = max(_ASPECT_RATIOS)
    side = math.sqrt(area * max_aspect)
    perimeter = 2 * (side + area / side)
    fraction = _USABLE_PERIMETER_FRACTION_HUB if room_type in ("corridor", "staircase", "entrance") else _USABLE_PERIMETER_FRACTION_OTHER
    return max(1, math.floor(perimeter * fraction / DOOR_MIN_WALL_M))


@dataclass(frozen=True)
class _Node:
    instance_id: str
    room_type: str
    item: ProgramItem


def _compositions(n: int, bins: int):
    """All ways to split n identical items across `bins` ordered bins (deterministic order)."""
    if bins == 1:
        yield (n,)
        return
    for first in range(n, -1, -1):
        for rest in _compositions(n - first, bins - 1):
            yield (first, *rest)


def _entry_hub(spec: ArchitecturalSpec, hubs: list[_Node]) -> _Node | None:
    if spec.circulation is not None:
        for hub in hubs:
            if hub.room_type == spec.circulation.entry_room_type:
                return hub
    for preferred in ENTRY_HUB_PREFERENCE:
        for hub in hubs:
            if hub.room_type == preferred:
                return hub
    return hubs[0] if hubs else None


_AREA_SAFETY_MARGIN_M2 = 1.0  # matches the earlier-validated finding: an area picked as the EXACT
# minimum reaching a target capacity sits right at the formula's own margin of error (proven
# directly in this program: capacity-4 corridor at its raw minimal area realized 0/N geometrically;
# the identical topology at minimal-area + 1.0 m2, same estimated capacity, realized fully).


def _min_area_for_capacity(target_capacity: int) -> float:
    area = _MIN_CORRIDOR_AREA_M2
    while area < _MAX_CORRIDOR_AREA_M2:
        if estimate_hub_capacity(ProgramItem(room_type="corridor", count=1, target_area_m2=area, min_width_m=1.0), "corridor") >= target_capacity:
            return min(area + _AREA_SAFETY_MARGIN_M2, _MAX_CORRIDOR_AREA_M2)
        area += _CORRIDOR_AREA_STEP_M2
    return _MAX_CORRIDOR_AREA_M2


def _ensure_sufficient_backbone_capacity(spec: ArchitecturalSpec, min_segments: int = 0) -> ArchitecturalSpec:
    """Escalates circulation the same way as `estimate_hub_capacity` reasons about any other hub:
    if the program's own hubs (living_room/kitchen/dining/entrance/...) cannot seat every
    destination even after paying for their own backbone connectors, add the smallest bounded
    number of `corridor` instances (never more than MAX_CIRCULATION_SEGMENTS) sized to close the
    gap -- generic, capacity-derived, never a fixed count/area and never keyed on a scenario name.
    A program whose existing hubs already suffice is returned unchanged."""
    nodes = [_Node(iid, rt, item) for iid, rt, item in expand_program_to_instances(spec.program)]
    hubs = [n for n in nodes if transit_role(n.room_type) in ("HUB", "LIMITED_HUB")]
    n_destinations = sum(1 for n in nodes if transit_role(n.room_type) == "DESTINATION")
    if not hubs:
        return spec

    hub_capacity = {h.instance_id: estimate_hub_capacity(h.item, h.room_type) for h in hubs}
    connectors = max(0, len(hubs) - 1)  # every non-entry hub connects to the backbone
    available = sum(hub_capacity.values()) - 2 * connectors
    deficit = n_destinations - available
    if deficit <= 0 and min_segments <= 0:
        return spec

    for n_segments in range(max(1, min_segments), MAX_CIRCULATION_SEGMENTS + 1):
        # each new segment also spends 2 capacity units connecting itself to the backbone, plus 1
        # extra unit of degree headroom: a corridor sized to sit EXACTLY at its estimated ceiling
        # while also directly bearing its own backbone connector was proven (in this exact
        # program) to be geometrically infeasible even though the estimate said it should just
        # fit -- the same "exact minimum is too tight" pattern the area safety margin above
        # already accounts for on the area axis; this is its degree-axis counterpart.
        per_segment_needed = 3 + math.ceil(max(deficit, 0) / n_segments)
        area = _min_area_for_capacity(per_segment_needed)
        new_item = ProgramItem(room_type="corridor", count=n_segments, target_area_m2=area, min_width_m=1.0, source="SYSTEM_POLICY")
        candidate_spec = spec.model_copy(update={"program": list(spec.program) + [new_item]})
        corridor_cap = estimate_hub_capacity(new_item, "corridor")
        if n_segments * (corridor_cap - 2) >= deficit:
            return candidate_spec
    return candidate_spec  # bounded: hand back the largest tried even if still short -- geometry/realization will report infeasibility honestly rather than looping forever


def generate_concepts(
    spec: ArchitecturalSpec, max_concepts: int = MAX_CONCEPTS, min_circulation_segments: int = 0
) -> tuple[ArchitecturalSpec, list[ArchitecturalConcept]]:
    """`min_circulation_segments`: forces at least this many corridor segments regardless of the
    analytical capacity estimate -- used by the planner's bounded geometry-probe escalation (the
    estimate is a precheck, not a feasibility guarantee; when the smallest analytically-sufficient
    circulation size turns out not to realize geometrically, the planner retries here with one more
    segment, exactly as Spatial V1's own earlier validated escalation did)."""
    spec = _ensure_sufficient_backbone_capacity(spec, min_segments=min_circulation_segments)
    nodes = [_Node(instance_id, room_type, item) for instance_id, room_type, item in expand_program_to_instances(spec.program)]
    hubs = [n for n in nodes if transit_role(n.room_type) in ("HUB", "LIMITED_HUB")]
    destinations = [n for n in nodes if transit_role(n.room_type) == "DESTINATION"]
    if not hubs:
        return spec, []
    entry = _entry_hub(spec, hubs)
    hubs = [entry] + [h for h in hubs if h is not entry]  # entry first, then declaration order
    zones = zone_by_room_type(spec.zones, {n.room_type for n in nodes})

    capacity = {}
    for hub in hubs:
        cap = estimate_hub_capacity(hub.item, hub.room_type)
        if transit_role(hub.room_type) == "LIMITED_HUB":
            cap = min(cap, LIMITED_HUB_MAX_DESTINATIONS + 1)  # + its own backbone connector
        capacity[hub.instance_id] = cap

    # --- backbone: every non-entry hub connects to whichever already-connected hub currently has
    #     the MOST remaining capacity (never blindly "the entry hub"). Pairing two already
    #     heavily-loaded hubs directly is exactly the tight combination proven earlier (in this
    #     same investigation) to tip an otherwise-feasible degree profile into geometric
    #     infeasibility -- spreading connector load across whichever hub has slack avoids stacking
    #     a high-degree hub's own connector directly onto another high-degree hub.
    # Circulation-to-circulation direct backbone edges are avoided as a PREFERENCE (never a hard
    # ban): chaining two circulation nodes directly was proven, in earlier work this same
    # investigation builds on, to be a specific tipping point into geometric infeasibility even
    # when both nodes individually have capacity to spare -- prefer a non-circulation target while
    # one has slack, falling back to circulation-to-circulation only if that's the only option.
    hub_room_type = {h.instance_id: h.room_type for h in hubs}
    backbone: list[InstanceEdge] = []
    remaining = dict(capacity)
    connected = [entry.instance_id]
    for hub in hubs[1:]:
        non_circulation_options = [c for c in connected if hub_room_type[c] != "corridor" and remaining[c] > 0]
        pool_for_target = non_circulation_options or connected
        target = max(pool_for_target, key=lambda c: remaining[c])
        backbone.append(InstanceEdge(target, hub.instance_id, "backbone", DOOR_MIN_WALL_M))
        remaining[target] -= 1
        remaining[hub.instance_id] -= 1
        connected.append(hub.instance_id)
    load = {h.instance_id: capacity[h.instance_id] - remaining[h.instance_id] for h in hubs}

    # --- destination -> hub distributions, enumerated per destination CLASS (room type) so that
    #     interchangeable instances don't multiply the search (symmetry reduction) ---
    by_class: dict[str, list[_Node]] = {}
    for d in destinations:
        by_class.setdefault(d.room_type, []).append(d)
    class_names = sorted(by_class)
    per_class_options = [list(_compositions(len(by_class[c]), len(hubs))) for c in class_names]

    raw_distributions = []
    for combo in itertools.product(*per_class_options) if class_names else [()]:
        hub_load = dict(load)
        for counts in combo:
            for hub, count in zip(hubs, counts):
                hub_load[hub.instance_id] += count
        overflow = sum(max(0, hub_load[h.instance_id] - capacity[h.instance_id]) for h in hubs)
        imbalance = max(hub_load.values()) - min(hub_load.values()) if hub_load else 0
        raw_distributions.append((overflow, imbalance, combo))
    raw_distributions.sort(key=lambda t: (t[0], t[1], t[2]))
    raw_distributions = [d for d in raw_distributions if d[0] == 0][:MAX_HUB_DISTRIBUTIONS]

    hard_relationships = [
        rel for rel in spec.relationships
        if rel.severity == ConstraintSeverity.hard and rel.kind in (ConstraintKind.adjacency, ConstraintKind.direct_access)
    ]
    by_type: dict[str, list[_Node]] = {}
    for n in nodes:
        by_type.setdefault(n.room_type, []).append(n)

    concepts: list[ArchitecturalConcept] = []
    seen: set[frozenset] = set()
    for index, (_overflow, _imbalance, combo) in enumerate(raw_distributions):
        hub_of: dict[str, str] = {}
        for class_name, counts in zip(class_names, combo):
            instances = by_class[class_name]  # declaration order -> deterministic
            cursor = 0
            for hub, count in zip(hubs, counts):
                for d in instances[cursor:cursor + count]:
                    hub_of[d.instance_id] = hub.instance_id
                cursor += count

        edges: dict[frozenset[str], InstanceEdge] = {e.key(): e for e in backbone}
        for d_id, h_id in hub_of.items():
            edges[frozenset((h_id, d_id))] = InstanceEdge(h_id, d_id, "access", DOOR_MIN_WALL_M)

        # --- relationship partner choice: the concept commits to ONE instance pair per hard rule ---
        def _hub_or_self(instance_id: str) -> str:
            return hub_of.get(instance_id, instance_id)

        for rel in hard_relationships:
            a_nodes, b_nodes = by_type.get(rel.room_type_a, []), by_type.get(rel.room_type_b, [])
            if not a_nodes or not b_nodes:
                continue
            pairs = [(a, b) for a in a_nodes for b in b_nodes]
            pairs.sort(key=lambda p: (0 if _hub_or_self(p[0].instance_id) == _hub_or_self(p[1].instance_id) else 1, p[0].instance_id, p[1].instance_id))
            a, b = pairs[0]
            min_wall = DOOR_MIN_WALL_M if rel.kind == ConstraintKind.direct_access else ADJACENCY_MIN_WALL_M
            key = frozenset((a.instance_id, b.instance_id))
            existing = edges.get(key)
            if existing is None or existing.min_shared_wall_m < min_wall:
                edges[key] = InstanceEdge(a.instance_id, b.instance_id, f"relationship:{rel.kind.value}", max(min_wall, existing.min_shared_wall_m if existing else 0.0))

        edge_tuple = tuple(sorted(edges.values(), key=lambda e: (e.kind, e.a, e.b)))
        signature = frozenset(e.key() for e in edge_tuple)
        if signature in seen:
            continue

        degree = {h.instance_id: 0 for h in hubs}
        for e in edge_tuple:
            for end in (e.a, e.b):
                if end in degree:
                    degree[end] += 1
        if any(degree[h] > capacity[h] for h in degree):
            continue  # capacity precheck: obviously unrealizable, don't spend geometry on it

        components = _tier_components(hub_of, entry.instance_id, edge_tuple, degree, capacity, zones, nodes)
        tier = sum(w * components[k] for k, w in (
            ("privacy_gating", W_PRIVACY_GATING), ("load_balance", W_LOAD_BALANCE),
            ("relationship_locality", W_RELATIONSHIP_LOCALITY), ("service_grouping", W_SERVICE_GROUPING),
        )) / _TIER_WEIGHT_TOTAL
        seen.add(signature)
        concepts.append(ArchitecturalConcept(
            concept_id=f"concept_{index}", entry_hub=entry.instance_id, edges=edge_tuple, hub_of=dict(hub_of),
            tier_score=round(tier, 4), tier_components={k: round(v, 4) for k, v in components.items()},
            hub_load=degree, hub_capacity=dict(capacity),
        ))

    concepts.sort(key=lambda c: (-c.tier_score, c.concept_id))
    return spec, concepts[:max_concepts]


def _tier_components(hub_of, entry_id, edges, degree, capacity, zones, nodes) -> dict[str, float]:
    type_of = {n.instance_id: n.room_type for n in nodes}
    private = [d for d in hub_of if zones.get(type_of[d]) == Zone.PRIVATE]
    service = [d for d in hub_of if zones.get(type_of[d]) == Zone.SERVICE]

    privacy_gating = (sum(1 for d in private if hub_of[d] != entry_id) / len(private)) if private else 1.0
    load_balance = 1.0 - max(degree[h] / capacity[h] for h in degree) if degree else 1.0
    rel_edges = [e for e in edges if e.kind.startswith("relationship:")]
    relationship_locality = (
        sum(1 for e in rel_edges if hub_of.get(e.a, e.a) == hub_of.get(e.b, e.b) or e.a in hub_of.values() or e.b in hub_of.values())
        / len(rel_edges)
    ) if rel_edges else 1.0
    private_hubs = {hub_of[d] for d in private}
    service_grouping = (sum(1 for d in service if hub_of[d] in private_hubs) / len(service)) if service and private else 1.0
    return {
        "privacy_gating": privacy_gating, "load_balance": max(0.0, load_balance),
        "relationship_locality": relationship_locality, "service_grouping": service_grouping,
    }
