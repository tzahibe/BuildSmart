"""``realize_concept(concept, adapted, brief, site) -> RealizedPlan | Refusal`` (Issue #96, C/3).

Compiles a synthesized+adapted concept (Issue #95: ``synthesis.ConceptSpec`` +
``adaptation.AdaptedConcept``) into a Geometry Core ``Fixture`` (slicing tree + zones + access),
then hands it to the SAME chain every real BuildSmart plan goes through:
``app.vertical_slice.geometry_core.engine.solve_fixture`` (frozen, unchanged) and
``app.vertical_slice.general_pipeline._realize`` (doors, windows, furniture, validation, assembly —
unchanged). Nothing here re-implements or bypasses a single validator: this module's own job ends
the moment a ``Fixture`` exists, and everything after that is the existing engine.

WHERE THIS REUSES THE EXISTING ENGINE RATHER THAN INVENTING ONE (Concept Engine v2's own
compilers, "where they exist" per Issue #96's Required Behavior 1):

  * ``app.vertical_slice.wet_rooms.resolve_wet_rooms`` / ``.bedroom_zones`` — the SAME zone-naming
    and ensuite-hosting resolver every real brief uses (``MASTER``/``BEDROOM_n``,
    ``BATH_n``/``TOILET_n``, ensuite host assignment). The adapted concept's own
    ``wet_core_strategy`` (Issue #95) decides only WHICH already-resolved wet room, if any, is
    additionally read as this compiler's own ensuite pairing signal (see ``_wet_topology``) — the
    brief's ``ProgramSpec.wet_room_kinds`` stays the one authoritative source `resolve_wet_rooms`
    reads, exactly as every other caller of that function does.
  * ``app.vertical_slice.concept_generator.ROOM_TEMPLATES`` — the SAME per-role min/target/max
    area, min short side and max aspect ratio every real concept's ``ZoneSpec`` is built from.
  * ``app.vertical_slice.general_pipeline._place_footprint`` — the SAME footprint-centring
    convention every real candidate is placed by.
  * ``app.vertical_slice.geometry_core.engine.solve_fixture`` / ``GeometryInfeasible`` and
    ``app.vertical_slice.general_pipeline._realize`` — completely unchanged; see this module's
    own docstring for exactly what "unchanged" is checked against (AC-2).

WHAT IS THIS MODULE'S OWN, MINIMAL SPIKE COMPILATION (no equivalent exists in Concept Engine v2,
which only ever FILTERS ``concept_generator.generate_concepts``'s own candidates for one brief —
it never turns an externally retrieved/adapted room list into a fresh slicing tree):

  * the TREE TOPOLOGY per ``ConceptSpec.circulation_class`` — ``_compile_spine``/
    ``_compile_front_band``/``_compile_two_wing`` below. Every internal split is LEFT UNFORCED
    (``fixed_at_u=None``): the frozen engine's own bottom-up shape-curve search
    (``geometry_core.engine.assign``/``leaf_shapes``) decides every room's actual position and
    size within its own ``ZoneSpec`` bounds, proportioned by target area — the SAME mechanism
    ``concept_generator.py``'s own builders lean on for every split they do not have an
    architectural reason to force. This compiler forces nothing.
  * the WING SIZE search (``_solve_with_size_search``): the compiler does not know in advance
    which (width, height) the combined shape curve admits, so it tries a small deterministic grid
    of plausible sizes (a few overall aspect ratios x a few area paddings) and keeps the first that
    solves — never a hidden retry that could silently prefer a worse plan, since ANY solved size is
    equally valid geometry for a rectangle whose own room mix decides its proportions, not the
    other way round.
  * HUB_LOBBY is NOT compiled (falls back to the SPINE template — see ``_TOPOLOGY_FOR_CLASS``): a
    genuine hub (a compact, near-square lobby reached by every room around it) needs a real 2-D
    layout a minimal single-column compiler cannot produce within a realistic house depth (a
    hub's own ``HUB_TEMPLATE`` bound is far tighter than a spine hall's — see the module's own
    measured infeasibility note in the Issue's report). Documented, not hidden: AC-1 only needs
    TWO distinct realized classes, and SPINE + TWO_WING already delivers that.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.geometry_domain.constraints import SiteConstraints
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import concept_spec
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice import wet_rooms as wet_rooms_module
from app.vertical_slice.concept import Concept
from app.vertical_slice.geometry_core.engine import (
    GeometryInfeasible,
    SolveResult,
    _collect_sets,
    derive_wall_types,
    solve_fixture,
)
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    Node,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
    u_to_m,
)
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt as safe_adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, LaundryDemand, PlotSpec

from spikes.architectural_brain.adaptation import AdaptedConcept
from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.synthesis import ConceptSpec as SynthesizedConcept

#: `SynthesizedConcept.circulation_class` (the corpus vocabulary — `patterns._circulation_class`)
#: -> which template below compiles it. HUB_LOBBY/BRANCHED/OTHER/UNKNOWN fall back to SPINE — see
#: the module docstring for why HUB_LOBBY specifically is not attempted.
_SPINE = "SPINE"
_FRONT_BAND = "FRONT_BAND"
_TWO_WING = "TWO_WING"

#: A full-height single hall leaf only has a satisfiable width when the wing depth is at most
#: sqrt(max_area * max_aspect_ratio) — beyond that no width admits both bounds at once (see
#: `_hall_zone`, which scales `max_area` to how many private rooms this hall must reach). This
#: cap uses `_hall_zone`'s own worst-case ceiling (10 private rooms) with a safety margin, so it
#: stays a fixed, cheap bound to filter trial sizes by rather than a per-call computation.
_MAX_WING_DEPTH_M = 23.0

#: The overall-footprint DEPTHS this compiler tries. Every column's own WIDTH at a given depth is
#: computed deterministically (`_min_width_u_at_height`), never guessed — depth is the only
#: dimension actually searched.
_DEPTH_TRIALS_M = (4.0, 5.0, 6.0, 7.0, 8.5, 10.0, 11.0, 13.0, 15.0, 17.0, 19.0, 20.5, 22.0)


@dataclass(frozen=True)
class Refusal:
    """This concept could not be realized at all — never a silently-wrong plan.

    Distinct from a `RealizedPlan` whose own `.validation` failed some check: that plan DID solve
    and is shown with its failing checks listed (Required Behavior 3). A `Refusal` is returned
    when no geometry could be built in the first place (the adapted concept's own feasibility
    rejection, or every tried footprint size was `GeometryInfeasible`).
    """

    concept_id: str
    reason: str
    failing_checks: tuple[str, ...] = ()


def _room_role(room_type: str) -> ProgramRole | None:
    try:
        return ProgramRole(room_type)
    except ValueError:
        return None


def _h_chain(zone_ids: list[str]) -> Node:
    if len(zone_ids) == 1:
        return Leaf(zone_ids[0])
    return Split(Cut.H, Leaf(zone_ids[0]), _h_chain(zone_ids[1:]), None)


def _adapted_target_area_m2(adapted: AdaptedConcept, role: ProgramRole) -> float | None:
    """The mean area `adaptation.adapt`'s `RESIZE_ROOMS`/`BEDROOM_COUNT_ADJUST` gave this role,
    or `None` if the adapted concept has no room of it — this is the one place the ADAPTED
    concept (as opposed to the brief's own authoritative counts/kinds) actually shapes the
    realized geometry: which target area within `ROOM_TEMPLATES`' own [min, max] bound a room
    starts from."""
    matches = [r.area_m2 for r in adapted.rooms if _room_role(r.room_type) is role]
    return sum(matches) / len(matches) if matches else None


def _zone(zone_id: str, role: ProgramRole, extra_roles: tuple[ProgramRole, ...] = (),
         adapted: AdaptedConcept | None = None) -> ZoneSpec:
    template = generator.ROOM_TEMPLATES[role]
    target = template.target_area_m2
    if adapted is not None:
        override = _adapted_target_area_m2(adapted, role)
        if override is not None:
            target = min(max(override, template.min_area_m2), template.max_area_m2)
    return ZoneSpec(
        zone_id, (role,) + extra_roles,
        template.min_area_m2, target, template.max_area_m2,
        template.min_short_side_m, template.max_aspect_ratio,
    )


def _zone_area_m2(zone: ZoneSpec) -> float:
    return zone.net_area_target_m2


@dataclass(frozen=True)
class _Programme:
    """The room composition this compiler builds a fixture from — derived from the brief's own
    authoritative requirements (bedroom count, wet-room kinds via `wet_rooms.resolve_wet_rooms`),
    never from the donor plan's own room list (Required Behavior 1: authoritative facts always
    win over anything a reference/adapted concept suggests)."""

    public_zones: tuple[ZoneSpec, ...]
    private_zones: tuple[ZoneSpec, ...]
    private_order: tuple[str, ...]
    ensuite_pairs: tuple[tuple[str, str], ...]   # (host bedroom zone id, wet room zone id)
    shared_wet_zone_ids: tuple[str, ...]
    hall_role_zone: ZoneSpec
    entrance_public_zone_id: str


def _wet_topology(program, adapted: AdaptedConcept):
    """The brief's own `resolve_wet_rooms` result, partitioned into (zone_id -> ZoneSpec),
    ensuite (host, wet_zone) pairs and shared (hall-entered) wet zone ids.

    `resolve_wet_rooms` reads `program.wet_room_kinds` — the brief's own stated requirement,
    unaffected by adaptation (`adaptation.adapt` never mutates `brief.program`) — so it is the
    correct, sufficient source for WHICH wet rooms exist and whether each is an ensuite; this
    compiler does not re-derive that from the adapted concept's `wet_core_strategy` (that field
    explains, for the demo's own record, why `adapt` needed a `WET_ZONE_ADJUST` operation to make
    a CLUSTERED donor able to host the brief's ensuite at all — never a second source of truth for
    hosting once the brief itself already states it). `adapted` is threaded through only for its
    per-role target AREAS (`_zone`'s own `adapted` argument).
    """
    resolved = wet_rooms_module.resolve_wet_rooms(program)
    zones: dict[str, ZoneSpec] = {}
    ensuite_pairs: list[tuple[str, str]] = []
    shared: list[str] = []
    for w in resolved:
        role = ProgramRole.TOILET if w.kind.value == "guest_wc" else ProgramRole.BATHROOM
        zones[w.zone_id] = _zone(w.zone_id, role, adapted=adapted)
        if w.host_zone is not None:
            ensuite_pairs.append((w.host_zone, w.zone_id))
        else:
            shared.append(w.zone_id)
    return zones, tuple(ensuite_pairs), tuple(shared), resolved


def _programme_of(brief: Brief, adapted: AdaptedConcept) -> tuple[_Programme, tuple]:
    program = brief.program

    public_zones = [
        _zone("LIVING", ProgramRole.LIVING, adapted=adapted),
        _zone("DINING", ProgramRole.DINING, adapted=adapted),
        _zone("KITCHEN", ProgramRole.KITCHEN, adapted=adapted),
    ]

    bedroom_zone_ids = wet_rooms_module.bedroom_zones(program)
    bedroom_zones = {
        zid: _zone(zid, ProgramRole.MASTER_BEDROOM if zid == "MASTER" else ProgramRole.BEDROOM,
                  adapted=adapted)
        for zid in bedroom_zone_ids
    }

    wet_zones, ensuite_pairs, shared_wet_ids, resolved_wet_rooms = _wet_topology(program, adapted)
    ensuite_by_host = dict(ensuite_pairs)

    order: list[str] = []
    private_zones: list[ZoneSpec] = []
    for zid in bedroom_zone_ids:
        order.append(zid)
        private_zones.append(bedroom_zones[zid])
        if zid in ensuite_by_host:
            wet_zid = ensuite_by_host[zid]
            order.append(wet_zid)
            private_zones.append(wet_zones[wet_zid])

    if program.safe_room:
        order.append("SAFE_ROOM")
        private_zones.append(_zone("SAFE_ROOM", ProgramRole.SAFE_ROOM, adapted=adapted))

    for zid in shared_wet_ids:
        order.append(zid)
        private_zones.append(wet_zones[zid])

    if program.laundry.demand is LaundryDemand.ROOM:
        order.append("LAUNDRY")
        private_zones.append(_zone("LAUNDRY", ProgramRole.LAUNDRY, adapted=adapted))

    hall_zone = _zone("HALL", ProgramRole.HALL, extra_roles=(ProgramRole.CIRCULATION,))

    return _Programme(
        public_zones=tuple(public_zones),
        private_zones=tuple(private_zones),
        private_order=tuple(order),
        ensuite_pairs=ensuite_pairs,
        shared_wet_zone_ids=shared_wet_ids,
        hall_role_zone=hall_zone,
        entrance_public_zone_id="LIVING",
    ), resolved_wet_rooms


def _hall_zone(hall_id: str, room_count: int) -> ZoneSpec:
    """A hall segment's own ZoneSpec, its `max_area_m2` scaled to how many private rooms it
    reaches — the same allowance `concept_generator.py`'s own comment on `ROOM_TEMPLATES[HALL]`
    already describes ("a geometric safety ceiling for long ... spines") and that module's own
    `scale_program` elasticity already lets a real hall grow past for a bigger house. This
    compiler makes that same allowance explicit, per compiled instance — never a change to
    `ROOM_TEMPLATES` itself, and the geometric hard limits (`min_short_side_m`, `max_aspect_ratio`)
    are the template's own, unmodified.
    """
    template = generator.ROOM_TEMPLATES[ProgramRole.HALL]
    max_area = max(template.max_area_m2, 6.0 * room_count)
    return ZoneSpec(
        hall_id, (ProgramRole.HALL, ProgramRole.CIRCULATION),
        template.min_area_m2, template.target_area_m2, max_area,
        template.min_short_side_m, template.max_aspect_ratio,
    )


def _private_groups(programme: _Programme) -> tuple[list[str], list[str]]:
    """`private_order` split into two ORDER-PRESERVING groups (an ensuite stays adjacent to its
    host, never separated) at the point the cumulative target area first reaches half the total —
    see `_hall_and_private_node` for why a single column of many private rooms is split into two
    hall-matched groups at all."""
    order = list(programme.private_order)
    zone_by_id = {z.zone_id: z for z in programme.private_zones}
    total = sum(zone_by_id[z].net_area_target_m2 for z in order)
    cum = 0.0
    split_idx = len(order)
    for i, zid in enumerate(order):
        cum += zone_by_id[zid].net_area_target_m2
        if cum >= total / 2:
            split_idx = i + 1
            break
    group1, group2 = order[:split_idx], order[split_idx:]
    if not group1 or not group2:
        split_idx = max(1, len(order) - 1)
        group1, group2 = order[:split_idx], order[split_idx:]
    return group1, group2


#: Generous bounds for the standalone feasibility probes below (`_probe_shape_set`) — large
#: enough that no real column's own [min_short_side, max_aspect_ratio, max_area] bounds are ever
#: clipped by the probe's own box, so what comes back is the TREE's true feasible set, not an
#: artefact of the bound chosen to query it.
_PROBE_BOUND_W_U = m_to_u(60.0)
_PROBE_BOUND_H_U = m_to_u(400.0)


def _probe_shape_set(tree: Node, zones: tuple[ZoneSpec, ...],
                     open_groups: tuple[tuple[str, ...], ...] = ()):
    """The root `ShapeSet` (height_u -> {width_u, ...}) a tree of `zones` composes to, queried
    directly from the frozen engine's own bottom-up computation
    (`geometry_core.engine._collect_sets`/`leaf_shapes`) — this module's own compiled trees are
    built from EXACTLY this data rather than a guessed proportional split, which is what makes
    every FORCED position below actually land inside the real feasible set (see the module's own
    investigation in the Issue's report for a measured case where a guess did not).

    IMPORTANT: a probe over a SUBTREE in isolation (e.g. just the hall segments, without the
    public/private siblings it will actually be built beside) derives EXTERIOR-thick walls on
    every boundary that would, in the real combined fixture, be a thin PARTITION wall shared with
    a neighbour — the isolated probe is then MORE conservative than reality on those sides and
    can miss real feasible widths (measured in the module's own investigation in the Issue's
    report). Callers computing a FINAL width to build a fixture with therefore probe the WHOLE
    combined tree they are about to build (same zones, same `open_groups`), not a sub-piece of
    it; sub-tree probes here (`_group_height_range_m`) are only ever used for an internal HEIGHT
    decision, never for the width this function is walled/inset-sensitive about."""
    wing = Wing("PROBE", 0, 0, _PROBE_BOUND_W_U, _PROBE_BOUND_H_U, tree)
    fixture = Fixture("PROBE", (wing,), zones, DesiredAccessTopology(()), open_groups=open_groups)
    walls = derive_wall_types(fixture, wing, None, None)
    try:
        return _collect_sets(tree, fixture, walls, _PROBE_BOUND_W_U, _PROBE_BOUND_H_U, {})
    except GeometryInfeasible:
        return None


def _group_height_range_m(zone_ids: list[str], zone_by_id: dict[str, ZoneSpec]) -> tuple[float, float] | None:
    """The (min, max) TOTAL height a stacked H-chain of `zone_ids` can be composed to, at ANY
    width — see `_probe_shape_set`."""
    s = _probe_shape_set(_h_chain(zone_ids), tuple(zone_by_id[z] for z in zone_ids))
    if s is None:
        return None
    heights = sorted(s.keys())
    return u_to_m(heights[0]), u_to_m(heights[-1])


def _feasible_widths_u_at_height(tree: Node, zones: tuple[ZoneSpec, ...], height_u: int,
                                 limit: int = 6,
                                 open_groups: tuple[tuple[str, ...], ...] = ()) -> list[int]:
    """Up to `limit` SMALLEST widths (grid units) a `tree` of `zones` can be composed to at
    EXACTLY `height_u`, ascending — `[]` if no width admits that height at all.

    ALWAYS called on the WHOLE tree that will actually be built (with the SAME `open_groups`),
    never a sub-piece of it — see `_probe_shape_set`'s own docstring for why an isolated sub-tree
    probe's wall-thickness assumptions do not match the real combined fixture's, which is what
    makes this the correct way to find a wing's own total width instead of leaving
    `geometry_core.engine.assign`'s own proportional-to-target-area heuristic to divide it among
    siblings on its own."""
    s = _probe_shape_set(tree, zones, open_groups)
    if s is None:
        return []
    widths = s.get(height_u)
    return sorted(widths)[:limit] if widths else []


def _min_width_u_at_height(tree: Node, zones: tuple[ZoneSpec, ...], height_u: int) -> int | None:
    """The single smallest width — see `_feasible_widths_u_at_height`."""
    widths = _feasible_widths_u_at_height(tree, zones, height_u, limit=1)
    return widths[0] if widths else None


def _widths_at_exact_height(zone_ids: list[str], zone_by_id: dict[str, ZoneSpec],
                            height_u: int) -> set[int]:
    """Widths (grid units) an UNFORCED H-chain of `zone_ids` can be composed to at EXACTLY
    `height_u` — accurate via `_collect_sets` because `zone_ids` here is always a group/leaf list
    with NO forced position of its own (see `_HallPrivateSplit`'s own docstring for why a node
    that DOES carry a forced position cannot be queried this same way)."""
    s = _probe_shape_set(_h_chain(zone_ids), tuple(zone_by_id[z] for z in zone_ids))
    return s.get(height_u, set()) if s else set()


@dataclass(frozen=True)
class _HallPrivateSplit:
    """One candidate (group1, group2) height split, with `private_widths`/`hall_widths` —
    EXACT sets of widths each of `private_tree`/`hall_tree` can ACTUALLY be forced to at this
    split, verified leaf-by-leaf via `_widths_at_exact_height`.

    WHY THIS EXISTS (not `_probe_shape_set` on `private_tree`/`hall_tree` themselves):
    `geometry_core.engine._collect_sets`'s bottom-up combine reports the shape set a node's
    PARENT would see if that node's OWN internal split were free to land anywhere — it does NOT
    filter by the node's own `fixed_at_u`. A node that itself carries a forced split (both
    `private_tree` and `hall_tree` do, at `group1`/`group2`'s and `hall1`/`hall2`'s own forced
    height boundary) therefore reports a WIDER, too-permissive width set to whatever queries it
    directly — measured in the module's own investigation in the Issue's report: `assign()` would
    pick a width from that too-permissive set, then fail exactly at THIS split's own forced
    position once it tried to lay the node out for real. Computing `private_widths`/`hall_widths`
    as the INTERSECTION of each half's own (unforced, thus accurately queryable) width set at its
    OWN forced height is what actually matches what `assign()` can honour.
    """

    private_tree: Node
    hall_tree: Node
    private_widths: list[int]
    hall_widths: list[int]
    hall_zones: tuple[ZoneSpec, ZoneSpec]
    segment_of: dict[str, str]
    primary_hall_id: str

    def combined_tree(self, hall_first: bool, hall_w_u: int, private_w_u: int) -> Node:
        """The (hall | private) subtree with the OUTER split ALSO forced — at `hall_w_u` if hall
        is first, at `private_w_u` otherwise (`Split.fixed_at_u` only fixes the FIRST child) —
        for exactly the same reason `private_tree`/`hall_tree`'s own splits are forced above:
        leaving this position to `assign()`'s own guess reintroduces the identical failure mode
        one level up.
        """
        if hall_first:
            return Split(Cut.V, self.hall_tree, self.private_tree, hall_w_u)
        return Split(Cut.V, self.private_tree, self.hall_tree, private_w_u)


#: How many different (group1, group2) height splits `_hall_and_private_splits` offers.
#: More than one exists because a split that looks feasible from each group's OWN isolated
#: height range (`_group_height_range_m`, computed with pass-1/structural wall types only) can
#: still turn out infeasible once the real multi-pass solve discovers an RC wall neighbouring a
#: SAFE_ROOM in one group — thickening that group's own insets in a way this module's own probes
#: cannot see ahead of an actual solve (see the module's own investigation in the Issue's
#: report). Trying several candidate splits, nearest the area-proportional one first, is what
#: recovers from that without hand-modelling every possible RC adjacency.
_HALL_SPLIT_CANDIDATE_LIMIT = 6

#: How many (width) options `_HallPrivateSplit.private_widths`/`.hall_widths` each keep.
_HALL_WIDTH_CANDIDATE_LIMIT = 8


def _hall_and_private_splits(programme: _Programme, hall_id: str, wing_h_u: int,
                             limit: int = _HALL_SPLIT_CANDIDATE_LIMIT) -> list[_HallPrivateSplit]:
    """Up to `limit` `_HallPrivateSplit` candidates for DIFFERENT (group1, group2) height splits,
    nearest the area-proportional split first — see `_HALL_SPLIT_CANDIDATE_LIMIT`'s own docstring
    for why more than one is offered. `[]` if no split lands inside both groups' real feasible
    height ranges at all, or admits no verified width for either half."""
    group1, group2 = _private_groups(programme)
    zone_by_id = {z.zone_id: z for z in programme.private_zones}
    range1 = _group_height_range_m(group1, zone_by_id)
    range2 = _group_height_range_m(group2, zone_by_id)
    if range1 is None or range2 is None:
        return []
    min1, max1 = range1
    min2, max2 = range2
    wing_h_m = u_to_m(wing_h_u)
    lo_u = max(m_to_u(min1), wing_h_u - m_to_u(max2), 1)
    hi_u = min(m_to_u(max1), wing_h_u - m_to_u(min2), wing_h_u - 1)
    if lo_u > hi_u:
        return []

    total = sum(z.net_area_target_m2 for z in zone_by_id.values())
    frac1 = sum(zone_by_id[z].net_area_target_m2 for z in group1) / total if total else 0.5
    target_u = m_to_u(wing_h_m * frac1)
    split_options = sorted(range(lo_u, hi_u + 1), key=lambda u: abs(u - target_u))[:limit]

    hall1_id, hall2_id = f"{hall_id}_1", f"{hall_id}_2"
    hall_zones = (_hall_zone(hall1_id, len(group1)), _hall_zone(hall2_id, len(group2)))
    hall_zone_by_id = {hall1_id: hall_zones[0], hall2_id: hall_zones[1]}
    segment_of = {zid: hall1_id for zid in group1}
    segment_of.update({zid: hall2_id for zid in group2})

    out = []
    for split_u in split_options:
        rest_u = wing_h_u - split_u
        private_widths = sorted(_widths_at_exact_height(group1, zone_by_id, split_u)
                                & _widths_at_exact_height(group2, zone_by_id, rest_u))
        if not private_widths:
            continue
        hall_widths = sorted(_widths_at_exact_height([hall1_id], hall_zone_by_id, split_u)
                             & _widths_at_exact_height([hall2_id], hall_zone_by_id, rest_u))
        if not hall_widths:
            continue
        private_tree = Split(Cut.H, _h_chain(group1), _h_chain(group2), split_u)
        hall_tree = Split(Cut.H, Leaf(hall1_id), Leaf(hall2_id), split_u)
        out.append(_HallPrivateSplit(
            private_tree, hall_tree,
            private_widths[:_HALL_WIDTH_CANDIDATE_LIMIT], hall_widths[:_HALL_WIDTH_CANDIDATE_LIMIT],
            hall_zones, segment_of, hall1_id))
    return out


def _private_access_edges(programme: _Programme, segment_of: dict[str, str]) -> list[DesiredAccessEdge]:
    """Every private room's own door — to its ensuite host, or to whichever hall segment
    `segment_of` says it borders. Shared with `_compile_two_wing`, which needs these edges
    WITHOUT the public-side ones `_access_for_spine` adds on top (wing B never touches LIVING
    directly; only `HALL_A` does)."""
    edges = [DesiredAccessEdge(host, wet_zid, ConnectionKind.DOOR)
            for host, wet_zid in programme.ensuite_pairs]
    ensuite_ids = {w for _, w in programme.ensuite_pairs}
    for zid in programme.private_order:
        if zid in ensuite_ids:
            continue
        edges.append(DesiredAccessEdge(segment_of[zid], zid, ConnectionKind.DOOR))
    return edges


def _access_for_spine(programme: _Programme, segment_of: dict[str, str],
                      hall_zones: tuple[ZoneSpec, ZoneSpec]) -> DesiredAccessTopology:
    hall1_id, hall2_id = hall_zones[0].zone_id, hall_zones[1].zone_id
    edges = [
        DesiredAccessEdge(hall1_id, "LIVING", ConnectionKind.DOOR),
        DesiredAccessEdge("LIVING", "DINING", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("DINING", "KITCHEN", ConnectionKind.OPEN_CONNECTION),
        # HALL_1 and HALL_2 are adjacent by construction (the two children of one forced H
        # split) — without a door between them, every private room `segment_of` routed to
        # HALL_2 would be unreachable from the entrance (C5) whenever the entrance/public side
        # only connects to HALL_1.
        DesiredAccessEdge(hall1_id, hall2_id, ConnectionKind.DOOR),
    ]
    edges.extend(_private_access_edges(programme, segment_of))
    return DesiredAccessTopology(tuple(edges))


def _compile_spine(programme: _Programme, h_u: int,
                   candidate_rect: Rect) -> tuple[Fixture, SolveResult] | None:
    """Builds and solves the SPINE fixture at the given depth. The hall/private HEIGHT split is a
    real design decision this module makes (`_hall_and_private_candidates`); the overall WING
    WIDTH at that depth is not guessed but read off the WHOLE tree's own true feasible set
    (`_feasible_widths_u_at_height`, probed on the complete tree — see that function's own
    docstring for why a probe on a sub-piece in isolation is not reliable here), leaving
    `geometry_core.engine.assign` to pick every internal split within a width already known to
    admit one. Returns `None` if this depth is infeasible, or no width that fits `candidate_rect`
    both exists and solves."""
    public_tree = _h_chain([z.zone_id for z in programme.public_zones])
    public_widths = _feasible_widths_u_at_height(public_tree, tuple(programme.public_zones), h_u)
    if not public_widths:
        return None
    open_groups = (("LIVING", "DINING", "KITCHEN"),)

    # Every width on every level (public, hall, private) is tried in combination — see
    # `_HallPrivateSplit`'s own docstring for why each is independently verified rather than
    # composed from a single guess at any level.
    for hp in _hall_and_private_splits(programme, "HALL", h_u):
        access = _access_for_spine(programme, hp.segment_of, hp.hall_zones)
        zones = programme.public_zones + hp.hall_zones + programme.private_zones
        for hall_w_u in hp.hall_widths:
            for private_w_u in hp.private_widths:
                hap_w_u = hall_w_u + private_w_u
                hall_and_private = hp.combined_tree(True, hall_w_u, private_w_u)
                for public_w_u in public_widths:
                    w_u = public_w_u + hap_w_u
                    if w_u > candidate_rect.w:
                        continue
                    tree = Split(Cut.V, public_tree, hall_and_private, public_w_u)
                    origin = gp._place_footprint(candidate_rect, u_to_m(w_u), u_to_m(h_u))
                    wing = Wing("W", origin[0], origin[1], w_u, h_u, tree)
                    fixture = Fixture("BRAIN_SPINE", (wing,), zones, access, open_groups=open_groups)
                    try:
                        return fixture, solve_fixture(fixture)
                    except GeometryInfeasible:
                        continue
    return None


def _v_chain(zone_ids: list[str]) -> Node:
    if len(zone_ids) == 1:
        return Leaf(zone_ids[0])
    return Split(Cut.V, Leaf(zone_ids[0]), _v_chain(zone_ids[1:]), None)


def _compile_two_wing(programme: _Programme, public_is_west: bool, ha_u: int, hb_u: int,
                      public_rect: Rect, private_rect: Rect, boundary_x: int, origin_y: int,
                      ) -> tuple[Fixture, SolveResult] | None:
    """Builds and solves both wings at the given depths. `len(fixture.wings) > 1` is exactly
    `realized_circulation_class`'s TWO_WING test, so the topology genuinely reads as two-wing
    regardless of internal structure.

    Every column width is computed via `_feasible_widths_u_at_height`/`_min_width_u_at_height`
    (see those functions' own docstrings) rather than guessed, and both wings are positioned
    flush against `boundary_x` (whichever side each rectangle is on) so however wide each ends
    up, the two halls meet at the exact shared edge between the two safe rectangles, giving the
    cross-wing door a real physical interface. Returns `None` if no computed width combination
    both fits each wing's own rectangle and solves.
    """
    # A safe-adapter "arm" rectangle is typically shallower than the primary one (brief 3's own
    # L site measures 7 m vs 14 m) — side by side (`_v_chain`, sharing height) rather than stacked
    # (`_h_chain`, sharing width and summing height) is what actually fits 3 public rooms into a
    # shallow wing; see the module's own investigation in the Issue's report for the measured
    # minimum stacked height (8.5 m) this avoids depending on.
    public_tree = _v_chain([z.zone_id for z in programme.public_zones])
    public_w_u = _min_width_u_at_height(public_tree, tuple(programme.public_zones), ha_u)
    hall_a_zone = _zone("HALL_A", ProgramRole.HALL, extra_roles=(ProgramRole.CIRCULATION,))
    hall_a_w_u = _min_width_u_at_height(Leaf("HALL_A"), (hall_a_zone,), ha_u)
    if public_w_u is None or hall_a_w_u is None:
        return None
    wa_u = public_w_u + hall_a_w_u
    if wa_u > public_rect.w:
        return None

    # Wing B's private stack gets the SAME hall-matched grouping SPINE uses (see
    # `_hall_and_private_node`) — an L site's primary rectangle is not automatically deep enough
    # for a single-column stack either (measured on brief 3's own site: 14 m offered, >= 18.8 m
    # needed). `hall_first=public_is_west` puts HALL_B on whichever side of wing B actually faces
    # wing A: if public (wing A) is WEST, wing B sits to its east, so HALL_B must be wing B's OWN
    # west-facing (first) side; matching this function's own docstring.
    if public_is_west:
        tree_a = Split(Cut.V, public_tree, Leaf("HALL_A"), public_w_u)
        origin_a = (boundary_x - wa_u, origin_y)
    else:
        tree_a = Split(Cut.V, Leaf("HALL_A"), public_tree, hall_a_w_u)
        origin_a = (boundary_x, origin_y)
    wing_a = Wing("WA", origin_a[0], origin_a[1], wa_u, ha_u, tree_a)

    # Every width on every level (wing B's hall, private, and their combined total) is tried in
    # combination — see `_HallPrivateSplit`'s own docstring for why each is independently
    # verified rather than composed from a single guess at any level.
    for hp in _hall_and_private_splits(programme, "HALL_B", hb_u):
        zones = programme.public_zones + (hall_a_zone,) + hp.hall_zones + programme.private_zones
        for hall_w_u in hp.hall_widths:
            for private_w_u in hp.private_widths:
                wb_u = hall_w_u + private_w_u
                if wb_u > private_rect.w:
                    continue
                hall_and_private_b = hp.combined_tree(public_is_west, hall_w_u, private_w_u)
                origin_b = (boundary_x, origin_y) if public_is_west else (boundary_x - wb_u, origin_y)
                wing_b = Wing("WB", origin_b[0], origin_b[1], wb_u, hb_u, hall_and_private_b)
                fixture = _two_wing_fixture(programme, wing_a, wing_b, zones, hall_a_zone,
                                            hp.hall_zones, hp.segment_of, hp.primary_hall_id)
                try:
                    return fixture, solve_fixture(fixture)
                except GeometryInfeasible:
                    continue
    return None


def _two_wing_fixture(programme: _Programme, wing_a: Wing, wing_b: Wing,
                      zones: tuple[ZoneSpec, ...], hall_a_zone: ZoneSpec,
                      hall_b_zones: tuple[ZoneSpec, ZoneSpec],
                      segment_of: dict[str, str], primary_hall_b: str) -> Fixture:
    hall_b1_id, hall_b2_id = hall_b_zones[0].zone_id, hall_b_zones[1].zone_id
    edges = [
        DesiredAccessEdge("HALL_A", "LIVING", ConnectionKind.DOOR),
        DesiredAccessEdge("LIVING", "DINING", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("DINING", "KITCHEN", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("HALL_A", primary_hall_b, ConnectionKind.DOOR),
        # HALL_B's own two segments are adjacent by construction (the two children of one
        # forced H split) — without this door, every private room `segment_of` routed to the
        # OTHER segment from `primary_hall_b` would be unreachable from the entrance (C5).
        DesiredAccessEdge(hall_b1_id, hall_b2_id, ConnectionKind.DOOR),
    ]
    edges.extend(_private_access_edges(programme, segment_of))
    access = DesiredAccessTopology(tuple(edges))
    open_groups = (("LIVING", "DINING", "KITCHEN"),)
    return Fixture("BRAIN_TWO_WING", (wing_a, wing_b), zones, access, open_groups=open_groups)


def _solve_spine_search(programme: _Programme, candidate_rect: Rect,
                        ) -> tuple[Fixture, SolveResult] | tuple[None, str]:
    """Tries each depth in `_DEPTH_TRIALS_M`; `_compile_spine` computes every column's own width
    deterministically (see its own docstring) and reports infeasibility as `None` rather than an
    exception, so this loop only needs to move on to the next depth."""
    last_error = "no depth trial was attempted"
    for depth_m in _DEPTH_TRIALS_M:
        if depth_m > _MAX_WING_DEPTH_M:
            continue
        h_u = m_to_u(depth_m)
        if h_u > candidate_rect.h:
            continue
        built = _compile_spine(programme, h_u, candidate_rect)
        if built is None:
            last_error = f"depth {depth_m} m: no width combination both fit and solved"
            continue
        return built
    return None, last_error


def _two_wing_layout(public_rect: Rect, private_rect: Rect) -> tuple[bool, int] | None:
    """Whether `public_rect` is the WEST rectangle, and the shared X boundary the two rects meet
    at — `None` if they do not share an exact vertical edge (the only adjacency this compiler's
    minimal two-wing template positions against; see `_compile_two_wing`'s own docstring)."""
    if public_rect.x2 == private_rect.x:
        return True, public_rect.x2
    if private_rect.x2 == public_rect.x:
        return False, private_rect.x2
    return None


def _solve_two_wing_search(programme: _Programme, candidates: tuple,
                           ) -> tuple[Fixture, SolveResult] | tuple[None, str]:
    """Tries the private programme against each of the first two safe candidates (whichever one
    the geometry actually offers as adjacent to the other — see `_two_wing_layout`), and for each
    assignment tries each wing's own depth independently (`_DEPTH_TRIALS_M`); `_compile_two_wing`
    computes every column's own width deterministically for a given depth pair (see its own
    docstring), so no width search is needed here at all."""
    if len(candidates) < 2:
        return None, ("fewer than 2 safe rectangles on this site — TWO_WING needs a second, "
                      "adjacent safe rectangle to place the second wing in")

    last_error = "no candidate pairing shared an exact adjacent edge"
    for private_rect, public_rect in ((candidates[0].rect, candidates[1].rect),
                                      (candidates[1].rect, candidates[0].rect)):
        layout = _two_wing_layout(public_rect, private_rect)
        if layout is None:
            continue
        public_is_west, boundary_x = layout
        origin_y = max(public_rect.y, private_rect.y)
        public_avail_h = public_rect.y2 - origin_y
        private_avail_h = private_rect.y2 - origin_y
        if public_avail_h <= 0 or private_avail_h <= 0:
            last_error = "the two candidates' Y ranges do not overlap"
            continue

        for depth_a_m in _DEPTH_TRIALS_M:
            if depth_a_m > _MAX_WING_DEPTH_M:
                continue
            ha_u = m_to_u(depth_a_m)
            if ha_u > public_avail_h:
                continue
            for depth_b_m in _DEPTH_TRIALS_M:
                hb_u = m_to_u(depth_b_m)
                if hb_u > private_avail_h or depth_b_m > _MAX_WING_DEPTH_M:
                    continue
                built = _compile_two_wing(programme, public_is_west, ha_u, hb_u,
                                          public_rect, private_rect, boundary_x, origin_y)
                if built is None:
                    last_error = (f"wing A depth {depth_a_m} m / wing B depth {depth_b_m} m: "
                                 f"no width combination fit both candidate rectangles and solved")
                    continue
                return built
    return None, last_error


#: `circulation_class` value -> which compiler builds it. Anything not listed (including
#: FRONT_BAND/HUB_LOBBY/BRANCHED/OTHER/UNKNOWN) falls back to SPINE — see the module docstring.
_TOPOLOGY_FOR_CLASS = {_TWO_WING: _TWO_WING}


def realize_concept(concept: SynthesizedConcept, adapted: AdaptedConcept, brief: Brief,
                    site: SiteConstraints, plot_size_m: tuple[float, float], index: int = 0,
                    ) -> "gp.RealizedPlan | Refusal":
    """Compile `concept`/`adapted` into a `Fixture`, then run it through the UNCHANGED
    `solve_fixture` + `general_pipeline._realize` chain (doors, windows, furniture, validation,
    assembly, `concept_spec.realized_circulation_class`).

    Returns a `Refusal` if no geometry could be built at all (adaptation already rejected the
    concept, or every tried footprint size was `GeometryInfeasible`); otherwise a `RealizedPlan`
    — which may itself carry failing validation checks (`.ok is False`), exactly as any other
    realized candidate in this codebase can.
    """
    programme, resolved_wet_rooms = _programme_of(brief, adapted)

    buildable = build_buildable_region(site)
    adapter_result = safe_adapt(buildable)
    if adapter_result.outcome is not AdapterOutcome.SOLVED or not adapter_result.candidates:
        return Refusal(concept.concept_id,
                       f"no safe solver geometry on this site: {adapter_result.outcome.value}")
    candidate_rect = adapter_result.candidates[0].rect

    topology = _TOPOLOGY_FOR_CLASS.get(concept.circulation_class, _SPINE)

    if topology == _TWO_WING:
        fixture, solve_or_error = _solve_two_wing_search(programme, adapter_result.candidates)
        strategy = generator.ConceptStrategy.MULTI_WING_SPLIT
        declared_class = concept_spec.CirculationClass.TWO_WING
        entrance_zone_id = "HALL_A"
    else:
        fixture, solve_or_error = _solve_spine_search(programme, candidate_rect)
        strategy = generator.ConceptStrategy.SPINE_PUBLIC_PRIVATE
        declared_class = concept_spec.CirculationClass.SPINE
        entrance_zone_id = "HALL"

    if fixture is None:
        return Refusal(concept.concept_id,
                       f"no footprint size solved for the {topology} template: {solve_or_error}",
                       failing_checks=(str(solve_or_error),))
    solve = solve_or_error

    inner_concept = Concept(fixture, entrance_zone_id, Side.N,
                           u_to_m(fixture.wings[0].w_u), u_to_m(fixture.wings[0].h_u))
    used_area_m2 = fixture.footprint_area_m2()
    candidate = generator.ConceptCandidate(
        concept=inner_concept,
        strategy=strategy,
        wing_orders=tuple(range(len(fixture.wings))),
        circulation_class=declared_class,
        rationale=f"architectural-brain POC: synthesized {concept.concept_id} "
                 f"(circulation_class={concept.circulation_class}, zoning={concept.zoning}) "
                 f"adapted with {len(adapted.adaptations)} operation(s), compiled to the "
                 f"{topology} template",
        used_area_m2=used_area_m2,
        unused_wing_area_m2=0.0,
        wet_rooms=resolved_wet_rooms,
    )

    arch_spec = ArchitecturalSpec(
        plot=PlotSpec(width_m=plot_size_m[0], depth_m=plot_size_m[1]), program=brief.program)
    plan = gp._realize(arch_spec, buildable, site, candidate, index, solve, ())
    return plan
