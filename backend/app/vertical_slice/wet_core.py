"""Wet-core / plumbing efficiency — Issue #44.

M5 (`quality_metrics.py`) already measures ONE plan-level ratio: the share of wet rooms sharing an
interior wall with another wet room, the kitchen, or the laundry. This module answers the
questions M5 leaves open, per plan, read off the REALIZED geometry (rects, the `WallMap`) exactly
the way `wet_privacy.py` reads privacy facts off the same layer — never off the requirement that
produced it:

    shared_wall_length_m       total length of interior wall shared between two wet rooms (m) —
                                not counting a wet room's wall with the kitchen or anything else,
                                the raw "how much plumbing wall is already being reused" fact.
    clusters                   every group of wet rooms connected edge-to-edge through OTHER wet
                                rooms, as a tuple of zone-id tuples (sorted, deterministic order) —
                                one plumbing stack could plausibly serve a whole cluster. A wet
                                room with no wet neighbour is its own one-element cluster.
    cluster_count               len(clusters) — informational.
    kitchen_adjacent_count      wet rooms sharing an interior wall with a kitchen zone.
    plumbing_complexity_index   an ESTIMATE of how many independent supply/drain runs a plumber
                                would need: the number of connected components of the graph whose
                                nodes are every wet room and every kitchen zone, and whose edges
                                are "shares an interior wall" (wet-wet OR wet-kitchen) — a wet
                                cluster that also touches the kitchen shares the kitchen's own run,
                                so it does not add to the count; kitchen zones with no wet neighbour
                                still count as their own run (a kitchen always needs one).
                                LOWER IS BETTER: fewer, larger clusters mean fewer stacks.

Never a gate: no function here can fail a plan, and none is called from `validation.py`. It is
read-only quality data (`QualityOut.metrics.wet_core`, `app.demo.contract`) plus a ranking
preference (`candidate_wet_core_key`/`better_candidate`, mirroring `wet_privacy.candidate_privacy_
key`/`better_candidate`) for a caller comparing two otherwise-equal candidates — no caller is wired
in by this Issue; the key exists for one to use.

Multi-level alignment (`wet_core_alignment`) is a SEPARATE, optional fact: given the wet rooms of
two REALIZED levels (the same "two `LevelRealization`s" shape `building_validation.py`'s V-checks
already consume), how many of the upper level's wet rooms sit directly over a wet room on the
level below — a real vertical stack, cheaper to plumb than an offset one. It is not wired into
`design_output.assemble` (a single-level function that only ever sees one level's own geometry);
a future caller with both levels' realized rects calls it directly, the same way `LevelRealization`
itself is only assembled by a caller that has both levels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .geometry_core.engine import WallMap
from .geometry_core.model import Fixture, ProgramRole, Rect, Side, WallType, u_to_m

_OPPOSITE_SIDE = {Side.N: Side.S, Side.S: Side.N, Side.E: Side.W, Side.W: Side.E}

#: A wet room's own kind — the nodes `clusters`/`shared_wall_length_m` are built from.
_WET_ROLES = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET})


@dataclass(frozen=True)
class WetCore:
    """One plan's plumbing-efficiency standing — see the module docstring for each field."""

    shared_wall_length_m: float
    clusters: tuple[tuple[str, ...], ...]
    cluster_count: int
    kitchen_adjacent_count: int
    plumbing_complexity_index: int


@dataclass(frozen=True)
class WetCoreAlignment:
    """How many of the UPPER level's wet rooms sit directly over a wet room on the level below —
    see `wet_core_alignment`. `alignment_ratio` is `None` when the upper level has no wet room at
    all (nothing to align, not a zero score)."""

    aligned_count: int
    upper_wet_count: int
    alignment_ratio: float | None


def _side_between(a: Rect, b: Rect) -> Side | None:
    if a.x2 == b.x:
        return Side.E
    if b.x2 == a.x:
        return Side.W
    if a.y2 == b.y:
        return Side.S
    if b.y2 == a.y:
        return Side.N
    return None


def _shares_interior_wall(zone_id: str, other_id: str, rects: dict[str, Rect],
                          walls: WallMap) -> bool:
    rect, other = rects.get(zone_id), rects.get(other_id)
    if rect is None or other is None or rect.shared_edge_len_u(other) <= 0:
        return False
    side = _side_between(rect, other)
    return side is not None and walls.get((zone_id, side)) is not WallType.EXTERIOR


class _UnionFind:
    """Minimal union-find over zone ids — the connectivity `clusters`/`plumbing_complexity_index`
    are read off, private to this module (no other module needs a general-purpose one today)."""

    def __init__(self, ids: Sequence[str]) -> None:
        self._parent = {i: i for i in ids}

    def find(self, i: str) -> str:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]
            i = self._parent[i]
        return i

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def groups(self) -> tuple[tuple[str, ...], ...]:
        by_root: dict[str, list[str]] = {}
        for i in self._parent:
            by_root.setdefault(self.find(i), []).append(i)
        return tuple(sorted((tuple(sorted(g)) for g in by_root.values())))


def compute_wet_core(fixture: Fixture, rects: dict[str, Rect], walls: WallMap) -> WetCore:
    """`WetCore` for one realized plan. Every fact read off `rects`/`walls` for the zone ids
    `fixture.zones` classifies as BATHROOM/TOILET (wet) or KITCHEN — never off a requirement, the
    same discipline `wet_privacy.compute_wet_privacy` already holds to."""
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    wet_ids = [zid for zid, roles in roles_of.items() if set(roles) & _WET_ROLES]
    kitchen_ids = [zid for zid, roles in roles_of.items() if ProgramRole.KITCHEN in roles]

    shared_wall_u = 0
    wet_uf = _UnionFind(wet_ids)
    for i, a in enumerate(wet_ids):
        for b in wet_ids[i + 1:]:
            if _shares_interior_wall(a, b, rects, walls):
                shared_wall_u += rects[a].shared_edge_len_u(rects[b])
                wet_uf.union(a, b)

    kitchen_adjacent = sum(
        1 for w in wet_ids if any(_shares_interior_wall(w, k, rects, walls) for k in kitchen_ids)
    )

    complexity_uf = _UnionFind(wet_ids + kitchen_ids)
    for i, a in enumerate(wet_ids):
        for b in wet_ids[i + 1:]:
            if _shares_interior_wall(a, b, rects, walls):
                complexity_uf.union(a, b)
    for w in wet_ids:
        for k in kitchen_ids:
            if _shares_interior_wall(w, k, rects, walls):
                complexity_uf.union(w, k)

    return WetCore(
        shared_wall_length_m=u_to_m(shared_wall_u),
        clusters=wet_uf.groups(),
        cluster_count=len(wet_uf.groups()),
        kitchen_adjacent_count=kitchen_adjacent,
        plumbing_complexity_index=len(complexity_uf.groups()) if (wet_ids or kitchen_ids) else 0,
    )


def candidate_wet_core_key(core: WetCore) -> tuple[int, float]:
    """(plumbing_complexity_index, -shared_wall_length_m) — LOWER IS BETTER. Fewer independent
    plumbing runs first; a tie on that breaks toward more shared wet wall (more of the runs that
    do exist are already doubled up), the same "cheap-to-plumb" preference the module docstring
    describes. Never a gate — see the module docstring."""
    return (core.plumbing_complexity_index, -round(core.shared_wall_length_m, 4))


def better_candidate(a: WetCore, b: WetCore) -> WetCore:
    """Which of two candidates' wet-core standing reads as more plumbing-efficient — `a` on an
    exact tie, so the choice is deterministic rather than depending on argument order by
    accident (the same tie rule `wet_privacy.better_candidate` uses)."""
    return a if candidate_wet_core_key(a) <= candidate_wet_core_key(b) else b


def _wet_rects(fixture: Fixture, rects: dict[str, Rect]) -> dict[str, Rect]:
    wet_ids = {z.zone_id for z in fixture.zones if set(z.roles) & _WET_ROLES}
    return {zid: r for zid, r in rects.items() if zid in wet_ids}


def wet_core_alignment(lower_fixture: Fixture, lower_rects: dict[str, Rect],
                       upper_fixture: Fixture, upper_rects: dict[str, Rect]) -> WetCoreAlignment:
    """How many of the UPPER level's wet rooms overlap, in plan (the same plot-absolute grid both
    levels are realized on — `building_validation.py`'s V2 already relies on the same fact), a wet
    room on the level below. A real footprint-overlap test (`Rect.overlap_area_u`), never a
    same-zone-id or same-index assumption: the two levels are independent fixtures and may not
    even agree on zone ids."""
    lower_wet = _wet_rects(lower_fixture, lower_rects)
    upper_wet = _wet_rects(upper_fixture, upper_rects)
    aligned = sum(
        1 for r in upper_wet.values()
        if any(r.overlap_area_u(lr) > 0 for lr in lower_wet.values())
    )
    total = len(upper_wet)
    return WetCoreAlignment(aligned_count=aligned, upper_wet_count=total,
                            alignment_ratio=(aligned / total) if total else None)
