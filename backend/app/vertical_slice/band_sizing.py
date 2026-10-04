"""Exact per-cell sizing of a band (GridWing) layout — production replacement for the rank-1
`_solve_grid` (Issue #142E; proven necessary by #142C/#142D: the proportional fit sized 0 of 207
witnesses that had a valid sizing, and the exact oracle lifted validator PASS from 1/13 to 4/13).

The geometry of a band layout is fully determined by R band heights `h` and C column widths `w`
(5 cm grid units, the realizer's own `UNIT_M`); every cell is `h[r] x sum(w[c0:c1])`. This module
finds integer `(h, w)` satisfying, for every cell, exactly what validator C3 later checks on the
realized room — on NET dimensions, i.e. after the wall insets the realizer will assign
(EXTERIOR half-thickness on a wing-boundary side, PARTITION half-thickness elsewhere):

    net_w = width - inset_W - inset_E ;  net_h = height - inset_N - inset_S
    net_area in [min_area, max_area]   (ZoneIntent bounds are NET — see rectilinear_realizer)
    min(net_w, net_h) >= min_short_side
    max(net_w, net_h) <= max_aspect * min(net_w, net_h)
    sum(w) <= w_max (or == w_exact), sum(h) <= h_max (or == h_exact)

Method (dependency-free, deterministic, exact on the unit grid): for a fixed height vector, every
cell constraint is an interval on the cell's width, and widths are differences of column prefix
sums, so feasibility is a system of difference constraints solved by Bellman–Ford. Heights are
searched by interval branch-and-bound: a box of height intervals relaxes each cell's width interval
to its outer envelope (exact for a box), an infeasible relaxation prunes the box, and boxes are
bisected on the widest band (the half containing the rank-1 estimate first) until every band is a
single unit value. INFEASIBLE means every box was pruned (a proof); UNKNOWN means the node budget was
hit. At a feasible leaf, widths are fixed one boundary at a time to the value closest to the
proportional target that keeps the system feasible.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .geometry_core.model import UNIT_M, ProgramRole, WallType, inset_u, m_to_u

#: Node budget — a cost bound, not a structural one (no wall-clock cut-off: deterministic); `UNKNOWN` reports it honestly.
DEFAULT_NODE_LIMIT = 4_000


@dataclass(frozen=True)
class CellSpec:
    zone_id: str
    r: int
    c0: int
    c1: int
    min_area_m2: float
    max_area_m2: float
    min_short_m: float
    max_aspect: float
    inset_w_u: int   # W + E insets, units (from the cell's own wall typing)
    inset_h_u: int   # N + S insets, units


@dataclass(frozen=True)
class SizingResult:
    status: str                       # FEASIBLE | INFEASIBLE | UNKNOWN
    row_h_u: tuple[int, ...] = ()
    col_w_u: tuple[int, ...] = ()
    nodes: int = 0
    detail: str = ""


def cell_insets_u(r: int, c0: int, c1: int, n_rows: int, n_cols: int,
                  rc_sides: frozenset = frozenset()) -> tuple[int, int]:
    """Net insets a cell will receive from `realize_layout`'s wall typing: EXTERIOR on a side that
    lies on the wing boundary, PARTITION on a side another cell touches (no OPEN walls inside a
    GridWing), RC_SAFE_ROOM on every side named in `rc_sides` (a SAFE_ROOM's own sides, and a
    neighbour's side that touches one — Issue #142G; precedence OPEN > RC > EXTERIOR > PARTITION,
    as `geometry_core.engine`). Conservative for multi-wing seams (a seam side is really PARTITION):
    the heavier EXTERIOR inset is assumed, so a net bound is never over-estimated."""
    ext, part, rc = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION), inset_u(WallType.RC_SAFE_ROOM)

    def side(name: str, exterior: bool) -> int:
        if name in rc_sides:
            return rc
        return ext if exterior else part
    iw = side("W", c0 == 0) + side("E", c1 == n_cols)
    ih = side("N", r == 0) + side("S", r == n_rows - 1)
    return iw, ih


def rc_sides_from_rows(rows, n_cols: int, zones) -> dict[str, frozenset]:
    """Per zone, the sides that `realize_layout` will type RC_SAFE_ROOM given these rows: every
    side of a SAFE_ROOM cell, and every side of another cell that shares a positive-length boundary
    with a SAFE_ROOM cell (same-row neighbour on W/E, overlapping cell in the adjacent row on N/S).
    Decided from the cell grid alone, so the sizing and the gate agree with the realized walls."""
    cells = []
    for r, row in enumerate(rows):
        c0 = 0
        for cell in row:
            zid, span = (cell.zone_id, cell.col_span) if hasattr(cell, "zone_id") else cell
            cells.append((zid, r, c0, c0 + int(span))); c0 += int(span)
    safe = {z for z, _, _, _ in cells if getattr(zones[z], "role", None) is ProgramRole.SAFE_ROOM}
    out: dict[str, set] = {z: set() for z, _, _, _ in cells}
    for z in safe:
        out[z] = {"N", "S", "E", "W"}
    for z, r, c0, c1 in cells:
        if z in safe:
            continue
        for sz, sr, sc0, sc1 in cells:
            if sz not in safe:
                continue
            if sr == r and sc1 == c0:
                out[z].add("W")
            elif sr == r and sc0 == c1:
                out[z].add("E")
            elif sr == r - 1 and sc0 < c1 and c0 < sc1:
                out[z].add("N")
            elif sr == r + 1 and sc0 < c1 and c0 < sc1:
                out[z].add("S")
    return {z: frozenset(v) for z, v in out.items()}


def cells_from_rows(rows, n_cols: int, zones) -> list[CellSpec]:
    """`rows`: top-to-bottom tuples of (zone_id, col_span) (or GridCell-like objects); `zones`:
    zone_id -> object with min_area_m2/max_area_m2/min_short_side_m/max_aspect_ratio."""
    cells = []
    R = len(rows)
    rc = rc_sides_from_rows(rows, n_cols, zones)
    for r, row in enumerate(rows):
        c0 = 0
        for cell in row:
            zid, span = (cell.zone_id, cell.col_span) if hasattr(cell, "zone_id") else cell
            z = zones[zid]
            iw, ih = cell_insets_u(r, c0, c0 + span, R, n_cols, rc.get(zid, frozenset()))
            cells.append(CellSpec(zid, r, c0, c0 + span, z.min_area_m2, z.max_area_m2,
                                  z.min_short_side_m, z.max_aspect_ratio, iw, ih))
            c0 += span
        if c0 != n_cols:
            raise ValueError(f"row {r}: spans sum to {c0}, not n_cols={n_cols}")
    return cells


# ----------------------------------------------------------------------------- width intervals

def _width_interval(c: CellSpec, hL: int, hU: int, tol_m2: float) -> tuple[int, int]:
    """[lo, hi] on the cell's GROSS width (units) valid for every height in [hL, hU]."""
    nhL = (hL - c.inset_h_u) * UNIT_M
    nhU = (hU - c.inset_h_u) * UNIT_M
    if nhL <= 0:
        return (10 ** 9, -1)
    lo_net = max(c.min_short_m, (c.min_area_m2 - tol_m2) / nhU, nhL / c.max_aspect)
    hi_net = min((c.max_area_m2 + tol_m2) / nhL, c.max_aspect * nhU)
    lo = c.inset_w_u + int(math.ceil(lo_net / UNIT_M - 1e-9))
    hi = c.inset_w_u + int(math.floor(hi_net / UNIT_M + 1e-9))
    return lo, hi


def _height_bounds(c: CellSpec, tol_m2: float, h_cap: int) -> tuple[int, int]:
    """Height range a cell admits at all (its own net short side, area and aspect, for SOME width)."""
    lo = c.inset_h_u + int(math.ceil(c.min_short_m / UNIT_M - 1e-9))
    # at the widest net width the cell may have (max area / min short, or aspect*…), height <= max/net_w_min
    hi_net = (c.max_area_m2 + tol_m2) / c.min_short_m
    hi = c.inset_h_u + int(math.floor(hi_net / UNIT_M + 1e-9))
    return lo, min(hi, h_cap)


def _bellman_ford(C: int, cons: list[tuple[int, int, int]]) -> list[int] | None:
    """Difference constraints P[v] - P[u] <= k as edges (u, v, k); returns max-feasible P with
    P[0] = 0 (shortest paths) or None when a negative cycle exists (infeasible)."""
    INF = float("inf")
    dist = [INF] * (C + 1)
    dist[0] = 0
    for _ in range(C + 1):
        changed = False
        for u, v, k in cons:
            if dist[u] + k < dist[v]:
                dist[v] = dist[u] + k
                changed = True
        if not changed:
            return [int(d) if d != INF else 0 for d in dist]
    return None


def _width_system(cells: list[CellSpec], h: list[int], hU: list[int] | None, C: int,
                  w_exact: int | None, w_max: int, tol_m2: float) -> list[tuple[int, int, int]] | None:
    """Difference constraints on column prefix sums P[0..C] for heights in [h, hU] (hU=None: exact)."""
    cons: list[tuple[int, int, int]] = []
    for c in range(C):
        cons.append((c + 1, c, -1))                       # P[c+1] - P[c] >= 1 unit
    for cell in cells:
        lo, hi = _width_interval(cell, h[cell.r], (hU or h)[cell.r], tol_m2)
        if lo > hi:
            return None
        cons.append((cell.c0, cell.c1, hi))               # P[c1] - P[c0] <= hi
        cons.append((cell.c1, cell.c0, -lo))              # P[c0] - P[c1] <= -lo
    if w_exact is not None:
        cons.append((0, C, w_exact)); cons.append((C, 0, -w_exact))
    else:
        cons.append((0, C, w_max))
    return cons


def _feasible_box(cells, hL, hU, C, w_exact, w_max, tol_m2) -> bool:
    cons = _width_system(cells, hL, hU, C, w_exact, w_max, tol_m2)
    return cons is not None and _bellman_ford(C, cons) is not None


def _prefix_interval(C: int, cons, c: int) -> tuple[int, int] | None:
    """Feasible [min, max] of P[c] under difference constraints `cons` with P[0] = 0:
    max P[c] = shortest path 0 -> c; min P[c] = -(shortest path c -> 0)."""
    d_from_0 = _bellman_ford_from(C, cons, 0)
    if d_from_0 is None:
        return None
    d_from_c = _bellman_ford_from(C, cons, c)
    if d_from_c is None:
        return None
    return -d_from_c[0], d_from_0[c]


def _choose_widths(cells, h, C, w_exact, w_max, tol_m2, target_w: list[float]) -> list[int] | None:
    """For FIXED heights: fix P[1..C] one at a time to the value nearest the proportional target
    that keeps the difference-constraint system feasible (interval from both-direction shortest
    paths), then read the column widths and verify every cell directly."""
    cons = _width_system(cells, h, None, C, w_exact, w_max, tol_m2)
    if cons is None or _bellman_ford_from(C, cons, 0) is None:
        return None
    fixed: list[tuple[int, int, int]] = []
    cum = 0.0
    P = [0] * (C + 1)
    for c in range(1, C + 1):
        cum += target_w[c - 1]
        iv = _prefix_interval(C, cons + fixed, c)
        if iv is None:
            return None
        lo, hi = iv
        if lo > hi:
            return None
        val = max(lo, min(hi, int(round(cum))))
        fixed.append((0, c, val)); fixed.append((c, 0, -val))
        P[c] = val
    widths = [P[c + 1] - P[c] for c in range(C)]
    if any(x < 1 for x in widths):
        return None
    for cell in cells:
        lo, hi = _width_interval(cell, h[cell.r], h[cell.r], tol_m2)
        wd = sum(widths[cell.c0:cell.c1])
        if not (lo <= wd <= hi):
            return None
    if w_exact is not None and sum(widths) != w_exact:
        return None
    if sum(widths) > w_max:
        return None
    return widths


def _bellman_ford_from(C: int, cons, src: int) -> list[int] | None:
    INF = float("inf")
    dist = [INF] * (C + 1)
    dist[src] = 0
    for _ in range(C + 1):
        changed = False
        for u, v, k in cons:
            if dist[u] + k < dist[v]:
                dist[v] = dist[u] + k
                changed = True
        if not changed:
            return [int(d) if d != INF else 0 for d in dist]
    return None


# ----------------------------------------------------------------------------- the solver

def solve_band_sizing(rows, n_cols: int, zones, *, w_max_m: float, h_max_m: float,
                      w_exact_m: float | None = None, h_exact_m: float | None = None,
                      tol_m2: float = 0.01, node_limit: int = DEFAULT_NODE_LIMIT) -> SizingResult:
    """Exact per-cell sizing (see module docstring). `rows`: top-to-bottom tuples of
    (zone_id, col_span) or `GridCell`s; `zones`: zone_id -> ZoneIntent-like. `tol_m2` mirrors
    validator C3's own area tolerance (TOL_M2 = 0.01)."""
    cells = cells_from_rows(rows, n_cols, zones)
    R = len(rows); C = n_cols
    w_max = m_to_u(w_exact_m) if w_exact_m is not None else m_to_u(w_max_m)
    h_cap = m_to_u(h_exact_m) if h_exact_m is not None else m_to_u(h_max_m)
    w_exact = m_to_u(w_exact_m) if w_exact_m is not None else None
    h_exact = m_to_u(h_exact_m) if h_exact_m is not None else None

    hL0 = [0] * R; hU0 = [h_cap] * R
    for cell in cells:
        lo, hi = _height_bounds(cell, tol_m2, h_cap)
        hL0[cell.r] = max(hL0[cell.r], lo)
        hU0[cell.r] = min(hU0[cell.r], hi)
    if any(hL0[r] > hU0[r] for r in range(R)):
        return SizingResult("INFEASIBLE", nodes=0,
                            detail="a band's cells have no common feasible depth (min short side / max area)")
    # proportional (rank-1) estimates only ORDER the search
    total = sum(z.target_area_m2 for z in zones.values()) or 1.0
    row_tot = [sum(zones[(c.zone_id if hasattr(c, "zone_id") else c[0])].target_area_m2 for c in row) for row in rows]
    col_tot = [0.0] * C
    for cell in cells:
        for c in range(cell.c0, cell.c1):
            col_tot[c] += zones[cell.zone_id].target_area_m2 / (cell.c1 - cell.c0)
    H_est = h_exact if h_exact is not None else min(h_cap, m_to_u(math.sqrt(total)))
    W_est = w_exact if w_exact is not None else min(w_max, m_to_u(math.sqrt(total)))
    h_est = [H_est * rt / total for rt in row_tot]
    target_w = [W_est * ct / total for ct in col_tot]

    def sum_ok(hL, hU) -> bool:
        if h_exact is not None:
            return sum(hL) <= h_exact <= sum(hU)
        return sum(hL) <= h_cap

    def point_in_box(hL, hU) -> list[int] | None:
        """The estimate clamped into the box, with the exact-sum condition repaired greedily."""
        h = [max(hL[r], min(hU[r], int(round(h_est[r])))) for r in range(R)]
        if h_exact is not None:
            diff = h_exact - sum(h)
            order = sorted(range(R), key=lambda i: -(hU[i] - hL[i]))
            for i in order:
                if diff == 0:
                    break
                room = (hU[i] - h[i]) if diff > 0 else (h[i] - hL[i])
                step = max(-room, min(room, diff))
                h[i] += step; diff -= step
            if diff != 0:
                return None
        elif sum(h) > h_cap:
            return None
        return h

    t0 = time.monotonic()
    stack = [(hL0, hU0)]
    nodes = 0
    while stack:
        hL, hU = stack.pop()
        nodes += 1
        if nodes > node_limit:
            return SizingResult("UNKNOWN", nodes=nodes, detail=f"node budget exhausted ({node_limit} nodes)")
        if not sum_ok(hL, hU):
            continue
        if not _feasible_box(cells, hL, hU, C, w_exact, w_max, tol_m2):
            continue
        # try the most plausible point of this box before splitting it further
        h = point_in_box(hL, hU)
        if h is not None:
            widths = _choose_widths(cells, h, C, w_exact, w_max, tol_m2, target_w)
            if widths is not None:
                return SizingResult("FEASIBLE", tuple(h), tuple(widths), nodes)
        if hL == hU:
            continue
        # branch on the widest band; explore the half containing the estimate first (pushed last)
        r = max(range(R), key=lambda i: (hU[i] - hL[i], -i))
        mid = (hL[r] + hU[r]) // 2
        lower = (list(hL), hU[:r] + [mid] + hU[r + 1:])
        upper = (hL[:r] + [mid + 1] + hL[r + 1:], list(hU))
        if h_est[r] > mid + 0.5:
            stack.append(lower); stack.append(upper)
        else:
            stack.append(upper); stack.append(lower)
    return SizingResult("INFEASIBLE", nodes=nodes,
                        detail="every height box was pruned by its width-system relaxation (proof)")


__all__ = ["CellSpec", "SizingResult", "cell_insets_u", "cells_from_rows", "solve_band_sizing"]


# ----------------------------------------------------------------------------- free-staircase sizing

@dataclass(frozen=True)
class LayoutSizing:
    """A sized band layout: band heights, per-band boundary positions, and the equivalent GridWing
    rows (zone, col_span) over the global columns = the sorted distinct boundary positions."""

    status: str                                   # FEASIBLE | INFEASIBLE | UNKNOWN
    row_h_u: tuple[int, ...] = ()
    band_positions_u: tuple[tuple[int, ...], ...] = ()   # per band: 0 = B[0] < B[1] < ... < B[k] = W
    rows: tuple[tuple[tuple[str, int], ...], ...] = ()
    n_cols: int = 0
    col_w_u: tuple[int, ...] = ()
    nodes: int = 0
    detail: str = ""


def _layout_cells(bands, zones, rc_sides: dict | None = None) -> tuple[list[CellSpec], list[int]]:
    """Cells over PER-BAND boundary nodes. Node ids: 0 is the shared left edge, then each band's
    interior boundaries in order, then node W (shared right edge). Returns cells (c0/c1 = node ids)
    and the list of node ids per band (len k+1)."""
    R = len(bands)
    next_id = 1
    band_nodes: list[list[int]] = []
    for band in bands:
        k = len(band)
        ids = [0] + [next_id + i for i in range(k - 1)]
        next_id += k - 1
        band_nodes.append(ids)
    W_node = next_id
    for ids in band_nodes:
        ids.append(W_node)
    cells = []
    for r, band in enumerate(bands):
        for i, zid in enumerate(band):
            z = zones[zid]
            rc = (rc_sides or {}).get(zid, frozenset())
            if getattr(z, "role", None) is ProgramRole.SAFE_ROOM:
                rc = frozenset({"N", "S", "E", "W"})       # a SAFE_ROOM's own envelope is always RC
            ext, part, rcu = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION), inset_u(WallType.RC_SAFE_ROOM)
            iw = (rcu if "W" in rc else (ext if i == 0 else part)) + (rcu if "E" in rc else (ext if i == len(band) - 1 else part))
            ih = (rcu if "N" in rc else (ext if r == 0 else part)) + (rcu if "S" in rc else (ext if r == R - 1 else part))
            cells.append(CellSpec(zid, r, band_nodes[r][i], band_nodes[r][i + 1], z.min_area_m2,
                                  z.max_area_m2, z.min_short_side_m, z.max_aspect_ratio, iw, ih))
    return cells, [W_node]


def _layout_system(cells, bands, band_nodes_count, required, h, hU, w_exact, w_max, tol_m2):
    """Difference constraints over per-band boundary nodes for heights in [h, hU]:
    cell widths from `_width_interval`; consecutive boundaries >= 1 unit; required cross pairs
    overlap by >= 1 unit; all bands end at the shared W node (<= w_max or == w_exact)."""
    N = band_nodes_count
    cons: list[tuple[int, int, int]] = []
    for cell in cells:
        lo, hi = _width_interval(cell, h[cell.r], (hU or h)[cell.r], tol_m2)
        if lo > hi:
            return None
        cons.append((cell.c0, cell.c1, hi))
        cons.append((cell.c1, cell.c0, -lo))
    by_zone = {cell.zone_id: cell for cell in cells}
    for a, b in required:
        ca, cb = by_zone[a], by_zone[b]
        if ca.r == cb.r:
            continue                       # consecutive in the same band: touching by construction
        if abs(ca.r - cb.r) != 1:
            return None
        # overlap > 0: x0_a < x1_b  and  x0_b < x1_a   (strict, in units)
        cons.append((cb.c1, ca.c0, -1))    # ca.c0 - cb.c1 <= -1
        cons.append((ca.c1, cb.c0, -1))    # cb.c0 - ca.c1 <= -1
    if w_exact is not None:
        cons.append((0, N - 1, w_exact)); cons.append((N - 1, 0, -w_exact))
    else:
        cons.append((0, N - 1, w_max))
    return cons


def solve_band_layout(bands, zones, required, *, w_max_m: float, h_max_m: float,
                      w_exact_m: float | None = None, h_exact_m: float | None = None,
                      tol_m2: float = 0.01, node_limit: int = DEFAULT_NODE_LIMIT) -> LayoutSizing:
    """Size an ORDERED band layout (`bands`: top-to-bottom tuples of zone ids) choosing the column
    interleaving between consecutive bands itself: every `required` pair must share a boundary of
    positive length, every cell meets its NET bounds (see module docstring), bands tile the same
    width. Same height branch-and-bound as `solve_band_sizing`; the width system is over per-band
    boundary nodes instead of a fixed global grid.

    SAFE_ROOM (Issue #142G): a safe room's own sides are RC (inset 0.15 m); which NEIGHBOUR sides
    touch it depends on the interleaving the solver chooses, so the solve is repeated with the RC
    sides read off its own result until they stop changing (bounded; the fixed-column re-solve in
    `_build_grid_wing` is exact for the final rows)."""
    rc_sides = None
    for _round in range(4):
        res = _solve_band_layout_once(bands, zones, required, w_max_m=w_max_m, h_max_m=h_max_m,
                                      w_exact_m=w_exact_m, h_exact_m=h_exact_m, tol_m2=tol_m2,
                                      node_limit=node_limit, rc_sides=rc_sides)
        if res.status != "FEASIBLE":
            return res
        found = rc_sides_from_rows(res.rows, res.n_cols, zones)
        found = {z: v for z, v in found.items() if v}
        if found == (rc_sides or {}):
            return res
        rc_sides = found
    return res


def _solve_band_layout_once(bands, zones, required, *, w_max_m, h_max_m, w_exact_m, h_exact_m,
                            tol_m2, node_limit, rc_sides) -> LayoutSizing:
    cells, (W_node,) = _layout_cells(bands, zones, rc_sides)
    N = W_node + 1
    R = len(bands)
    req = [tuple(e) for e in required]
    w_max = m_to_u(w_exact_m) if w_exact_m is not None else m_to_u(w_max_m)
    h_cap = m_to_u(h_exact_m) if h_exact_m is not None else m_to_u(h_max_m)
    w_exact = m_to_u(w_exact_m) if w_exact_m is not None else None
    h_exact = m_to_u(h_exact_m) if h_exact_m is not None else None

    hL0 = [0] * R; hU0 = [h_cap] * R
    for cell in cells:
        lo, hi = _height_bounds(cell, tol_m2, h_cap)
        hL0[cell.r] = max(hL0[cell.r], lo); hU0[cell.r] = min(hU0[cell.r], hi)
    if any(hL0[r] > hU0[r] for r in range(R)):
        return LayoutSizing("INFEASIBLE", nodes=0, detail="a band's cells have no common feasible depth")
    total = sum(z.target_area_m2 for z in zones.values()) or 1.0
    row_tot = [sum(zones[z].target_area_m2 for z in band) for band in bands]
    H_est = h_exact if h_exact is not None else min(h_cap, m_to_u(math.sqrt(total)))
    W_est = w_exact if w_exact is not None else min(w_max, m_to_u(math.sqrt(total)))
    h_est = [H_est * rt / total for rt in row_tot]

    def feasible_box(hL, hU):
        cons = _layout_system(cells, bands, N, req, hL, hU, w_exact, w_max, tol_m2)
        return cons is not None and _bellman_ford_from(N - 1, cons, 0) is not None

    def choose(h):
        cons = _layout_system(cells, bands, N, req, h, None, w_exact, w_max, tol_m2)
        if cons is None or _bellman_ford_from(N - 1, cons, 0) is None:
            return None
        # fix the shared width first (closest to the estimate), then each band's boundaries left to
        # right at the value closest to the proportional target
        fixed: list[tuple[int, int, int]] = []
        P = [0] * N
        iv = _prefix_interval(N - 1, cons, W_node)
        if iv is None:
            return None
        Wv = max(iv[0], min(iv[1], int(round(W_est))))
        fixed += [(0, W_node, Wv), (W_node, 0, -Wv)]; P[W_node] = Wv
        for r, band in enumerate(bands):
            cum = 0.0
            ids = [cell for cell in cells if cell.r == r]
            for cell in ids[:-1]:
                cum += zones[cell.zone_id].target_area_m2 / row_tot[r] * Wv
                iv = _prefix_interval(N - 1, cons + fixed, cell.c1)
                if iv is None or iv[0] > iv[1]:
                    return None
                val = max(iv[0], min(iv[1], int(round(cum))))
                fixed += [(0, cell.c1, val), (cell.c1, 0, -val)]; P[cell.c1] = val
        if _bellman_ford_from(N - 1, cons + fixed, 0) is None:
            return None
        return P

    def point_in_box(hL, hU):
        h = [max(hL[r], min(hU[r], int(round(h_est[r])))) for r in range(R)]
        if h_exact is not None:
            diff = h_exact - sum(h)
            for i in sorted(range(R), key=lambda i: -(hU[i] - hL[i])):
                if diff == 0:
                    break
                room = (hU[i] - h[i]) if diff > 0 else (h[i] - hL[i])
                step = max(-room, min(room, diff)); h[i] += step; diff -= step
            if diff != 0:
                return None
        elif sum(h) > h_cap:
            return None
        return h

    def sum_ok(hL, hU):
        return (sum(hL) <= h_exact <= sum(hU)) if h_exact is not None else sum(hL) <= h_cap

    def finish(h, P, nodes):
        positions = tuple(tuple(P[i] for i in [c.c0 for c in cells if c.r == r] + [W_node]) for r in range(R))
        xs = sorted({x for band in positions for x in band})
        col_of = {x: i for i, x in enumerate(xs)}
        rows = tuple(tuple((bands[r][i], col_of[positions[r][i + 1]] - col_of[positions[r][i]])
                           for i in range(len(bands[r]))) for r in range(R))
        col_w = tuple(xs[i + 1] - xs[i] for i in range(len(xs) - 1))
        return LayoutSizing("FEASIBLE", tuple(h), positions, rows, len(xs) - 1, col_w, nodes)

    t0 = time.monotonic()
    stack = [(hL0, hU0)]
    nodes = 0
    while stack:
        hL, hU = stack.pop()
        nodes += 1
        if nodes > node_limit:
            return LayoutSizing("UNKNOWN", nodes=nodes, detail=f"node budget exhausted ({node_limit} nodes)")
        if not sum_ok(hL, hU) or not feasible_box(hL, hU):
            continue
        h = point_in_box(hL, hU)
        if h is not None:
            P = choose(h)
            if P is not None:
                return finish(h, P, nodes)
        if hL == hU:
            continue
        r = max(range(R), key=lambda i: (hU[i] - hL[i], -i))
        mid = (hL[r] + hU[r]) // 2
        lower = (list(hL), hU[:r] + [mid] + hU[r + 1:])
        upper = (hL[:r] + [mid + 1] + hL[r + 1:], list(hU))
        if h_est[r] > mid + 0.5:
            stack.append(lower); stack.append(upper)
        else:
            stack.append(upper); stack.append(lower)
    return LayoutSizing("INFEASIBLE", nodes=nodes, detail="every height box was pruned by its width-system relaxation (proof)")


__all__ += ["LayoutSizing", "solve_band_layout", "rc_sides_from_rows"]
