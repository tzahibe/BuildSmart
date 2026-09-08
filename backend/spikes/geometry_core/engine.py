"""Geometry Core Proof Spike — the engine under test.

Three stages, exactly as PRIVATE_HOUSE_V1_ENGINE_DECISION.md §3 and §7 claim:

  1. STRUCTURAL wall typing (top-down over the slicing tree, NO geometry).
       Exterior sides, open-plan sides and the safe room's own sides are all knowable
       from the tree + program alone. This is the claim §7 rests on.
  2. SHAPE CURVES (bottom-up). Every leaf's NET requirement is inflated by its own known
       wall insets, so the composed geometry is thickness-correct on the first pass.
  3. ASSIGNMENT (top-down). Pick a split at each node; leaves get exact centerline rects.

The one thing genuinely NOT knowable structurally is "is my neighbour the safe room?",
because that depends on which leaves end up touching. That is resolved by a bounded
re-solve loop, and the iteration count is MEASURED, not assumed — see `solve_fixture`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from model import (
    UNIT_M,
    Cut,
    Fixture,
    Leaf,
    Node,
    Rect,
    Side,
    Split,
    WallType,
    Wing,
    ZoneSpec,
    inset_u,
    leaves_of,
    m_to_u,
    u_to_m,
)

EPS = 1e-9
MAX_SHAPE_POINTS = 400_000  # guard: if a node blows past this, the approach is not viable

# ShapeSet: height(units) -> set of widths(units). Both are CENTERLINE dimensions.
ShapeSet = dict[int, set[int]]

WallMap = dict[tuple[str, Side], WallType]


class SpikeInfeasible(Exception):
    """Raised when a fixture cannot be realized. Carries the diagnosis — an empty shape set
    always names the node that emptied it, so 'it failed' is never the whole answer."""


# ------------------------------------------------------------------ 1. structural wall typing

_OPPOSITE = {Side.N: Side.S, Side.S: Side.N, Side.E: Side.W, Side.W: Side.E}


def leaves_touching(node: Node, side: Side) -> set[str]:
    """Which leaves of `node` touch `side` of node's own rectangle. Purely structural."""
    if isinstance(node, Leaf):
        return {node.zone_id}
    if node.cut is Cut.V:
        if side is Side.W:
            return leaves_touching(node.first, Side.W)
        if side is Side.E:
            return leaves_touching(node.second, Side.E)
        return leaves_touching(node.first, side) | leaves_touching(node.second, side)
    if side is Side.N:
        return leaves_touching(node.first, Side.N)
    if side is Side.S:
        return leaves_touching(node.second, Side.S)
    return leaves_touching(node.first, side) | leaves_touching(node.second, side)


def _mark_exposure(node: Node, exposed: dict[Side, bool], out: dict[tuple[str, Side], bool]) -> None:
    if isinstance(node, Leaf):
        for s in Side:
            out[(node.zone_id, s)] = exposed[s]
        return
    if node.cut is Cut.V:
        first = {**exposed, Side.E: False}
        second = {**exposed, Side.W: False}
    else:
        first = {**exposed, Side.S: False}
        second = {**exposed, Side.N: False}
    _mark_exposure(node.first, first, out)
    _mark_exposure(node.second, second, out)


def _mark_open_interfaces(node: Node, open_groups: tuple[tuple[str, ...], ...], out: WallMap) -> None:
    """Every internal split boundary inside a subtree whose leaves all belong to ONE open
    group carries no wall at all. This is what makes open-plan free of artificial doors."""
    if isinstance(node, Leaf):
        return
    subtree = set(leaves_of(node))
    inside_one_group = any(subtree <= set(g) for g in open_groups)
    if inside_one_group:
        if node.cut is Cut.V:
            a_side, b_side = Side.E, Side.W
        else:
            a_side, b_side = Side.S, Side.N
        for zid in leaves_touching(node.first, a_side):
            out[(zid, a_side)] = WallType.OPEN
        for zid in leaves_touching(node.second, b_side):
            out[(zid, b_side)] = WallType.OPEN
    _mark_open_interfaces(node.first, open_groups, out)
    _mark_open_interfaces(node.second, open_groups, out)


def derive_wall_types(
    fixture: Fixture,
    wing: Wing,
    safe_room_neighbours: dict[str, set[Side]] | None = None,
) -> WallMap:
    """Stage 1. `safe_room_neighbours` is the ONLY input that needs geometry; it is empty on
    the first pass and filled by `solve_fixture`'s bounded re-solve."""
    exposure: dict[tuple[str, Side], bool] = {}
    _mark_exposure(wing.tree, {s: True for s in Side}, exposure)
    # An archetype-declared seam side abuts another wing, so it is NOT exterior.
    for zid, side in wing.seam_leaf_sides:
        exposure[(zid, side)] = False

    walls: WallMap = {}
    _mark_open_interfaces(wing.tree, fixture.open_groups, walls)

    # PRECEDENCE MATTERS, and getting it wrong is a real defect the spike caught on its first
    # run: a safe room's EXTERIOR wall is still a safe-room wall. Exposure must not outrank
    # safe-room membership, or the envelope side of the ממ"ד is typed as ordinary exterior and
    # every downstream ממ"ד construction rule silently stops applying to it.
    #   OPEN  >  RC_SAFE_ROOM  >  EXTERIOR  >  PARTITION
    for zid in leaves_of(wing.tree):
        zone = fixture.zone(zid)
        for s in Side:
            if (zid, s) in walls:  # already OPEN — same open-plan space, no wall at all
                continue
            touches_safe_room = zone.is_safe_room or (
                bool(safe_room_neighbours) and s in safe_room_neighbours.get(zid, set())
            )
            if touches_safe_room:
                walls[(zid, s)] = WallType.RC_SAFE_ROOM
            elif exposure[(zid, s)]:
                walls[(zid, s)] = WallType.EXTERIOR
            else:
                walls[(zid, s)] = WallType.PARTITION
    return walls


def leaf_insets_u(zone_id: str, walls: WallMap) -> tuple[int, int]:
    """(total width inset, total height inset) in units — what this leaf loses off centerline."""
    iw = inset_u(walls[(zone_id, Side.W)]) + inset_u(walls[(zone_id, Side.E)])
    ih = inset_u(walls[(zone_id, Side.N)]) + inset_u(walls[(zone_id, Side.S)])
    return iw, ih


# ------------------------------------------------------------------ 2. shape curves

def leaf_shapes(zone: ZoneSpec, walls: WallMap, bound_w: int, bound_h: int) -> ShapeSet:
    """All CENTERLINE (w,h) that satisfy the zone's NET area/dimension requirements."""
    iw, ih = leaf_insets_u(zone.zone_id, walls)
    min_side_u = m_to_u(zone.min_short_side_m)

    out: ShapeSet = {}
    net_w_u = min_side_u
    while net_w_u + iw <= bound_w:
        net_w_m = u_to_m(net_w_u)
        # area range, min short side, and the aspect gate all bound h at once
        h_lo_m = max(zone.min_short_side_m,
                     zone.net_area_min_m2 / net_w_m,
                     net_w_m / zone.max_aspect_ratio)
        h_hi_m = min(zone.net_area_max_m2 / net_w_m,
                     net_w_m * zone.max_aspect_ratio)
        net_h_lo = max(min_side_u, math.ceil(h_lo_m / UNIT_M - EPS))
        net_h_hi = math.floor(h_hi_m / UNIT_M + EPS)
        for net_h_u in range(net_h_lo, net_h_hi + 1):
            h_u = net_h_u + ih
            if h_u > bound_h:
                break
            out.setdefault(h_u, set()).add(net_w_u + iw)
        net_w_u += 1
    return out


def _transpose(s: ShapeSet) -> ShapeSet:
    t: ShapeSet = {}
    for h, ws in s.items():
        for w in ws:
            t.setdefault(w, set()).add(h)
    return t


def _count(s: ShapeSet) -> int:
    return sum(len(v) for v in s.values())


def _combine(cut: Cut, a: ShapeSet, b: ShapeSet, bound_w: int, bound_h: int) -> ShapeSet:
    """V-cut children share the node's height; H-cut children share its width. So composition
    is a join on the shared dimension plus a Minkowski sum on the other. ONE implementation."""
    if cut is Cut.V:
        out: ShapeSet = {}
        for h in a.keys() & b.keys():
            bw = b[h]
            ws = {x + y for x in a[h] for y in bw if x + y <= bound_w}
            if ws:
                out[h] = ws
        return out
    at, bt = _transpose(a), _transpose(b)
    tmp: ShapeSet = {}
    for w in at.keys() & bt.keys():
        bh = bt[w]
        hs = {x + y for x in at[w] for y in bh if x + y <= bound_h}
        if hs:
            tmp[w] = hs
    return _transpose(tmp)


# ------------------------------------------------------------------ 3. assignment

def _target_area_u(node: Node, fixture: Fixture) -> float:
    return sum(fixture.zone(z).net_area_target_m2 for z in leaves_of(node))


def assign(
    node: Node,
    rect: Rect,
    fixture: Fixture,
    walls: WallMap,
    sets: dict[int, ShapeSet],
    out: dict[str, Rect],
) -> None:
    """Stage 3, top-down. Splits are chosen closest to the children's target-area ratio, so
    the tiling is not merely feasible but proportioned like the program asked for."""
    if isinstance(node, Leaf):
        out[node.zone_id] = rect
        return

    a_set, b_set = sets[id(node.first)], sets[id(node.second)]
    ta, tb = _target_area_u(node.first, fixture), _target_area_u(node.second, fixture)
    frac = ta / (ta + tb) if (ta + tb) > 0 else 0.5

    if node.cut is Cut.V:
        options = sorted(w for w in a_set.get(rect.h, ()) if (rect.w - w) in b_set.get(rect.h, ()))
        if node.fixed_at_u is not None:
            options = [w for w in options if w == node.fixed_at_u]
        if not options:
            raise SpikeInfeasible(
                f"no V split of {rect} for [{', '.join(leaves_of(node))}]"
                + (f" at forced position {node.fixed_at_u}" if node.fixed_at_u is not None else "")
            )
        want = frac * rect.w
        first_w = min(options, key=lambda w: abs(w - want))
        assign(node.first, Rect(rect.x, rect.y, first_w, rect.h), fixture, walls, sets, out)
        assign(node.second, Rect(rect.x + first_w, rect.y, rect.w - first_w, rect.h), fixture, walls, sets, out)
    else:
        at, bt = _transpose(a_set), _transpose(b_set)
        options = sorted(h for h in at.get(rect.w, ()) if (rect.h - h) in bt.get(rect.w, ()))
        if node.fixed_at_u is not None:
            options = [h for h in options if h == node.fixed_at_u]
        if not options:
            raise SpikeInfeasible(
                f"no H split of {rect} for [{', '.join(leaves_of(node))}]"
                + (f" at forced position {node.fixed_at_u}" if node.fixed_at_u is not None else "")
            )
        want = frac * rect.h
        first_h = min(options, key=lambda h: abs(h - want))
        assign(node.first, Rect(rect.x, rect.y, rect.w, first_h), fixture, walls, sets, out)
        assign(node.second, Rect(rect.x, rect.y + first_h, rect.w, rect.h - first_h), fixture, walls, sets, out)


def _collect_sets(node: Node, fixture: Fixture, walls: WallMap, bw: int, bh: int, into: dict[int, ShapeSet]) -> ShapeSet:
    """Stage 2, bottom-up — computes and MEMOISES every node's shape set (assignment needs them)."""
    if isinstance(node, Leaf):
        s = leaf_shapes(fixture.zone(node.zone_id), walls, bw, bh)
        if not s:
            raise SpikeInfeasible(
                f"leaf '{node.zone_id}' has an EMPTY shape curve inside {u_to_m(bw)}x{u_to_m(bh)} m "
                f"— its net area / min-dimension requirements cannot be met at all"
            )
    else:
        a = _collect_sets(node.first, fixture, walls, bw, bh, into)
        b = _collect_sets(node.second, fixture, walls, bw, bh, into)
        s = _combine(node.cut, a, b, bw, bh)
        if not s:
            raise SpikeInfeasible(
                f"{node.cut.value}-cut over [{', '.join(leaves_of(node))}] composed to EMPTY "
                f"— its children share no common dimension inside the wing"
            )
        if _count(s) > MAX_SHAPE_POINTS:
            raise SpikeInfeasible(f"shape set exploded past {MAX_SHAPE_POINTS} points")
    into[id(node)] = s
    return s


# ------------------------------------------------------------------ solve

@dataclass
class SolveResult:
    rects: dict[str, Rect]
    walls: WallMap
    wall_iterations: int
    notes: list[str]


def _neighbour_sides(rects: dict[str, Rect], target: str) -> dict[str, set[Side]]:
    """Which side of each leaf faces `target`. Needs geometry — the one non-structural input."""
    tr = rects[target]
    found: dict[str, set[Side]] = {}
    for zid, r in rects.items():
        if zid == target or r.shared_edge_len_u(tr) <= 0:
            continue
        if r.x2 == tr.x:
            found.setdefault(zid, set()).add(Side.E)
        elif tr.x2 == r.x:
            found.setdefault(zid, set()).add(Side.W)
        elif r.y2 == tr.y:
            found.setdefault(zid, set()).add(Side.S)
        elif tr.y2 == r.y:
            found.setdefault(zid, set()).add(Side.N)
    return found


def solve_wing(fixture: Fixture, wing: Wing, extra_rc: dict[str, set[Side]] | None) -> tuple[dict[str, Rect], WallMap]:
    walls = derive_wall_types(fixture, wing, extra_rc)
    sets: dict[int, ShapeSet] = {}
    root = _collect_sets(wing.tree, fixture, walls, wing.w_u, wing.h_u, sets)
    if wing.h_u not in root or wing.w_u not in root[wing.h_u]:
        raise SpikeInfeasible(
            f"wing '{wing.wing_id}' {u_to_m(wing.w_u)}x{u_to_m(wing.h_u)} m is not in the root "
            f"shape curve — no tiling of this wing satisfies every zone"
        )
    out: dict[str, Rect] = {}
    assign(wing.tree, wing.rect(), fixture, walls, sets, out)
    return out, walls


def solve_fixture(fixture: Fixture, max_wall_iterations: int = 3) -> SolveResult:
    """Bounded re-solve. Pass 1 uses purely structural wall types; later passes only add
    RC where geometry revealed a safe-room neighbour. The iteration count is the measured
    answer to the report's §7 claim."""
    notes: list[str] = []
    extra_rc: dict[str, set[Side]] = {}

    for iteration in range(1, max_wall_iterations + 1):
        rects: dict[str, Rect] = {}
        walls: WallMap = {}
        for wing in fixture.wings:
            r, w = solve_wing(fixture, wing, extra_rc)
            rects.update(r)
            walls.update(w)

        safe_rooms = [z.zone_id for z in fixture.zones if z.is_safe_room and z.zone_id in rects]
        discovered: dict[str, set[Side]] = {}
        for sr in safe_rooms:
            for zid, sides in _neighbour_sides(rects, sr).items():
                if fixture.zone(zid).is_safe_room:
                    continue
                discovered.setdefault(zid, set()).update(sides)

        new = {z: s - extra_rc.get(z, set()) for z, s in discovered.items()}
        new = {z: s for z, s in new.items() if s}
        if not new:
            notes.append(f"wall types converged after {iteration} iteration(s)")
            return SolveResult(rects=rects, walls=walls, wall_iterations=iteration, notes=notes)

        for z, s in new.items():
            extra_rc.setdefault(z, set()).update(s)
        notes.append(
            f"iteration {iteration}: found safe-room neighbours "
            + ", ".join(f"{z}:{''.join(x.value for x in sorted(s, key=lambda k: k.value))}" for z, s in new.items())
        )

    raise SpikeInfeasible(f"wall types did not converge within {max_wall_iterations} iterations")


# ------------------------------------------------------------------ net geometry

def net_rect_m(zone_id: str, rect: Rect, walls: WallMap) -> tuple[float, float, float]:
    """(net width m, net depth m, net area m2) — centerline minus this leaf's own wall insets."""
    nw = rect.w - inset_u(walls[(zone_id, Side.W)]) - inset_u(walls[(zone_id, Side.E)])
    nh = rect.h - inset_u(walls[(zone_id, Side.N)]) - inset_u(walls[(zone_id, Side.S)])
    return u_to_m(nw), u_to_m(nh), round(u_to_m(nw) * u_to_m(nh), 4)
