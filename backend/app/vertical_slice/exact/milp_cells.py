"""The exact sizer for cross-band cells (#200): one MILP over a `CellLayout` — rows with chosen
heights, every cell with its own column nodes, spanning cells with exact areas.

What is new against `milp_oracle.milp_heights` / `_spine_once`: nothing in the rules, everything
in the uniformity. Every cell's net area is `(w - iw)(H - ih)` with `H` the sum of the heights of
the rows it spans; `w * H` is linearised exactly through `p = w * z` products with the rows'
height binaries (McCormick with a binary), so area, short side and aspect are all linear for every
cell, spanning or not, and the big-M-per-grid-value loops of the band oracle disappear. Contacts
are a shared wall's length (the sum of the rows two sequence-neighbours share) or an x-overlap
(two cells in adjacent rows); the envelope, the alignment rule (C22) and the entrance rule
(`doors.resolve_entrance`: a fronting hall holds the door and needs three door widths) are the
band oracle's, applied per row. The target objective is the one of day 3.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from app.vertical_slice.band_sizing import CellSpec, _height_bounds
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.exact.cells import CIRC, CellLayout
from app.vertical_slice.exact.milp_oracle import BIG, _height_grid
from app.vertical_slice.geometry_core.model import (
    UNIT_M,
    Rect,
    WallType,
    inset_u,
    m_to_u,
)

HALL_MIN_WIDTH_M = 1.8      # the spine's corridor width, for any circulation cell spanning rows


@dataclass(frozen=True)
class CellsResult:
    status: str
    detail: str = ""
    heights_u: tuple[int, ...] = ()
    x_u: dict = field(default_factory=dict)          # zone -> (x0, x1)
    y_start_u: int = 0


def cells_rects(layout: CellLayout, res: CellsResult) -> dict[str, Rect]:
    ys = [res.y_start_u]
    for h in res.heights_u:
        ys.append(ys[-1] + h)
    out = {}
    for z in layout.zones:
        r0, r1 = layout.span(z)
        x0, x1 = res.x_u[z]
        out[z] = Rect(x0, ys[r0], x1 - x0, ys[r1 + 1] - ys[r0])
    return out


def cells_wings(layout: CellLayout, res: CellsResult) -> tuple[Rect, ...]:
    """Every cell is its own wing: each wall is then a declared seam and C22 holds it to one wall
    type along its length — exactly the fact the layout kept structurally."""
    return tuple(cells_rects(layout, res).values())


def _insets(layout: CellLayout, zones: dict, sides: dict | None):
    ext_i, part_i, rc_i = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION), inset_u(WallType.RC_SAFE_ROOM)
    from app.vertical_slice.geometry_core.model import ProgramRole
    out = {}
    R = layout.n_rows
    for z in layout.zones:
        known = (sides or {}).get(z)
        if known is not None:
            out[z] = (inset_u(known["W"]) + inset_u(known["E"]), inset_u(known["N"]) + inset_u(known["S"]))
            continue
        r0, r1 = layout.span(z)
        safe = getattr(zones[z], "role", None) is ProgramRole.SAFE_ROOM
        first = layout.rows[r0][0] == z
        last = layout.rows[r0][-1] == z
        w_in = (rc_i if safe else (ext_i if first else part_i)) + (rc_i if safe else (ext_i if last else part_i))
        h_in = (rc_i if safe else (ext_i if r0 == 0 else part_i)) + (rc_i if safe else (ext_i if r1 == R - 1 else part_i))
        out[z] = (w_in, h_in)
    return out


def milp_cells(layout: CellLayout, zones: dict, required, envelope: Envelope, *, min_contact_u: dict | None = None,
               k: int = 12, tol_m2: float = 0.01, time_limit_s: float = 10.0, objective: str = "target",
               sides: dict | None = None, _skip: frozenset = frozenset()) -> CellsResult:
    """`_skip` is a diagnostic hook naming constraint groups to leave out ("cells", "contacts",
    "envelope", "align", "entrance") — tests and diagnosis only."""
    problems = layout.problems()
    if problems:
        return CellsResult("INFEASIBLE", "; ".join(problems))
    req = [tuple(e) for e in required]
    if not layout.admits(req):
        return CellsResult("INFEASIBLE", "a required contact is structurally impossible in this layout")
    R = layout.n_rows
    insets = _insets(layout, zones, sides)
    span = {z: layout.span(z) for z in layout.zones}

    # ---- depth: the same start / cap rule as the band oracle
    windows = envelope.split_depth_windows_u()
    y_start = 0
    while windows and windows[0][0] <= y_start:
        y_start = windows[0][1]; windows = windows[1:]
    h_cap = envelope.depth_u - y_start
    if windows:
        h_cap = min(h_cap, windows[0][0] - y_start)
    hL0, hU0 = [1] * R, [h_cap] * R
    for z in layout.zones:
        r0, r1 = span[z]
        zi = zones[z]
        iw, ih = insets[z]
        if r0 == r1:
            c = CellSpec(z, r0, 0, 0, zi.min_area_m2, zi.max_area_m2, zi.min_short_side_m, zi.max_aspect_ratio, iw, ih)
            lo, hi = _height_bounds(c, tol_m2, h_cap)
            hL0[r0] = max(hL0[r0], lo); hU0[r0] = min(hU0[r0], hi)
    if any(hL0[r] > hU0[r] for r in range(R)):
        return CellsResult("INFEASIBLE", "a row's cells have no common feasible depth")
    if sum(hL0) > h_cap:
        return CellsResult("BAND_GAP" if windows else "INFEASIBLE", "the rows' minimum depths exceed the usable depth")
    grids = [_height_grid(hL0[r], hU0[r], k) for r in range(R)]

    _, miny, _, _ = envelope.polygon.bounds
    step_ys = sorted({y_start, y_start + h_cap} | {m_to_u(vy - miny) for _, vy in envelope.vertices_m
                                                    if y_start < m_to_u(vy - miny) < y_start + h_cap})
    segments = []
    for y0, y1 in itertools.pairwise(step_ys):
        ivs = envelope.extent_u(y0, y1)
        if len(ivs) != 1:
            return CellsResult("BAND_GAP", f"the envelope splits between depths {y0} and {y1} u")
        segments.append((y0, y1, ivs[0][0], ivs[0][1]))
    inner_steps = step_ys[1:-1]

    # ---- variables
    nvar = 0
    x0_idx, x1_idx = {}, {}
    for z in layout.zones:
        x0_idx[z] = nvar; nvar += 1
        x1_idx[z] = nvar; nvar += 1
    z_idx = {}
    for r in range(R):
        for kk in range(len(grids[r])):
            z_idx[(r, kk)] = nvar; nvar += 1
    a_idx, b_idx = {}, {}
    for r in range(R):
        for d in inner_steps:
            a_idx[(r, d)] = nvar; nvar += 1
            b_idx[(r, d)] = nvar; nvar += 1
    binaries = list(z_idx.values()) + list(a_idx.values()) + list(b_idx.values())
    continuous: list[int] = []
    rows_, lbs, ubs = [], [], []

    def add(coefs, lb, ub):
        rows_.append(coefs); lbs.append(lb); ubs.append(ub)

    def h_expr(r):
        return {z_idx[(r, kk)]: float(grids[r][kk]) for kk in range(len(grids[r]))}

    def y_expr(r):
        e = {}
        for i in range(r):
            for v, cft in h_expr(i).items():
                e[v] = e.get(v, 0.0) + cft
        return e

    def merged(*ds):
        e = {}
        for d in ds:
            for v, cft in d.items():
                e[v] = e.get(v, 0.0) + cft
        return e

    for r in range(R):
        add({z_idx[(r, kk)]: 1.0 for kk in range(len(grids[r]))}, 1, 1)
    tot = merged(*[h_expr(r) for r in range(R)])
    add(tot, 0, h_cap)

    # ---- row sequences: neighbours share a node; ends inside the envelope's box
    Lbox, Rbox = min(sg[2] for sg in segments), max(sg[3] for sg in segments)
    s_nodes, e_nodes, row_nodes = [], [], []
    for r, row in enumerate(layout.rows):
        for a, b in itertools.pairwise(row):
            add({x1_idx[a]: 1.0, x0_idx[b]: -1.0}, 0, 0)
        s_nodes.append(x0_idx[row[0]]); e_nodes.append(x1_idx[row[-1]])
        row_nodes.append([x0_idx[row[0]]] + [x1_idx[z] for z in row])
        add({s_nodes[r]: 1.0}, Lbox, BIG); add({e_nodes[r]: 1.0}, -BIG, Rbox)
    W_hi = Rbox - Lbox

    # ---- cells: exact net area, short side, aspect
    net_expr: dict[str, tuple[dict, float]] = {}
    for z in layout.zones:
        zi = zones[z]
        r0, r1 = span[z]
        iw, ih = insets[z]
        w = {x1_idx[z]: 1.0, x0_idx[z]: -1.0}
        add(dict(w), 1, BIG)
        H = merged(*[h_expr(r) for r in range(r0, r1 + 1)])
        area = {x1_idx[z]: -float(ih), x0_idx[z]: float(ih)}              # - ih * w
        for r in range(r0, r1 + 1):
            for kk, Hk in enumerate(grids[r]):
                zv = z_idx[(r, kk)]
                pv = nvar; nvar += 1; continuous.append(pv)
                add({pv: 1.0, zv: -float(W_hi)}, -BIG, 0)                                   # p <= Wh z
                add({pv: 1.0, zv: -1.0}, 0, BIG)                                            # p >= z
                add({pv: 1.0, **{v: -c for v, c in w.items()}, zv: -1.0}, -BIG, -1)         # p <= w - (1-z)
                add({pv: 1.0, **{v: -c for v, c in w.items()}, zv: -float(W_hi)}, -W_hi, BIG)   # p >= w - Wh(1-z)
                area[pv] = float(Hk)
                area[zv] = area.get(zv, 0.0) - float(iw) * Hk                               # - iw * H
        const = float(iw * ih)
        a_lo, a_hi = zi.min_area_m2 / (UNIT_M * UNIT_M), zi.max_area_m2 / (UNIT_M * UNIT_M)
        if "cells" not in _skip:
            add(area, a_lo - const, a_hi - const)
            ms = m_to_u(zi.min_short_side_m)
            add(dict(w), ms + iw, BIG)                                                       # net width >= short side
            add(dict(H), ms + ih, BIG)                                                       # net height >= short side
            asp = float(zi.max_aspect_ratio)
            add(merged(w, {v: -asp * c for v, c in H.items()}), -np.inf, iw - asp * ih)    # (w-iw) <= asp (H-ih)
            add(merged(H, {v: -asp * c for v, c in w.items()}), -np.inf, ih - asp * iw)    # (H-ih) <= asp (w-iw)
        net_expr[z] = (area, const)
        # a fronting circulation cell holds the front door (HALL outranks LIVING): three door widths
        if getattr(zi, "role", None) in CIRC and r0 == 0 and "entrance" not in _skip:
            from app.vertical_slice.doors import ENTRANCE_DOOR_WIDTH_M
            add(dict(w), 3 * m_to_u(ENTRANCE_DOOR_WIDTH_M), BIG)
        if getattr(zi, "role", None) in CIRC and r1 > r0:
            add(dict(w), m_to_u(HALL_MIN_WIDTH_M) + iw, BIG)

    # ---- contacts
    for a, b in (req if "contacts" not in _skip else ()):
        need = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
        shared_rows = [r for r, row in enumerate(layout.rows)
                       if a in row and b in row and abs(row.index(a) - row.index(b)) == 1]
        if shared_rows:
            add(merged(*[h_expr(r) for r in shared_rows]), need, BIG)       # the shared wall's length
            continue
        (a0, a1), (b0, b1) = span[a], span[b]
        if a1 + 1 == b0 or b1 + 1 == a0:
            add({x1_idx[b]: 1.0, x0_idx[a]: -1.0}, need, BIG)
            add({x1_idx[a]: 1.0, x0_idx[b]: -1.0}, need, BIG)
            continue
        return CellsResult("INFEASIBLE", f"{a}-{b}: no wall to share in this layout")
    # consecutive rows overlap
    for r in range(R - 1):
        add({e_nodes[r + 1]: 1.0, s_nodes[r]: -1.0}, 1, BIG)
        add({e_nodes[r]: 1.0, s_nodes[r + 1]: -1.0}, 1, BIG)

    # ---- envelope steps (a: some part above d, b: some part below d), as the band oracle
    for d in (inner_steps if "envelope" not in _skip else ()):
        above = [sg for sg in segments if sg[1] <= d]; below = [sg for sg in segments if sg[0] >= d]
        La, Ra = max(sg[2] for sg in above), min(sg[3] for sg in above)
        Lb, Rb = max(sg[2] for sg in below), min(sg[3] for sg in below)
        for r in range(R):
            s, e = s_nodes[r], e_nodes[r]
            av, bv = a_idx[(r, d)], b_idx[(r, d)]
            y = y_expr(r); hr = h_expr(r)
            add({**y, av: BIG}, d, BIG + d + BIG)
            yh = merged(y, hr); yh[bv] = yh.get(bv, 0.0) - BIG
            add(yh, -BIG, d)
            add({av: 1.0, bv: 1.0}, 1, 2)
            add({s: 1.0, av: -BIG}, La - BIG, BIG); add({e: 1.0, av: BIG}, -BIG, Ra + BIG)
            add({s: 1.0, bv: -BIG}, Lb - BIG, BIG); add({e: 1.0, bv: BIG}, -BIG, Rb + BIG)

    # ---- alignment (C22): a row's end coincides with a boundary of the row above or lies outside it,
    # and an end of the row above that falls inside this row is one of this row's boundaries
    for r in (range(R - 1) if "align" not in _skip else ()):
        U, D = row_nodes[r], row_nodes[r + 1]
        u0, uk = U[0], U[-1]
        for endpoint, outside_is_left in ((D[0], True), (D[-1], False)):
            choice = []
            for uj in U:
                v = nvar; nvar += 1; choice.append(v); binaries.append(v)
                if uj == endpoint:
                    continue                                       # the same node: coincides by identity
                add({endpoint: 1.0, uj: -1.0, v: BIG}, -BIG * 2, BIG)
                add({endpoint: 1.0, uj: -1.0, v: -BIG}, -BIG, BIG * 2)
            v_out = nvar; nvar += 1; choice.append(v_out); binaries.append(v_out)
            ref = u0 if outside_is_left else uk
            if outside_is_left:
                add({endpoint: 1.0, ref: -1.0, v_out: BIG}, -BIG, BIG)
            else:
                add({endpoint: 1.0, ref: -1.0, v_out: -BIG}, -BIG, BIG)
            ts = []
            for di in D[1:-1]:
                t = nvar; nvar += 1; ts.append(t); binaries.append(t)
                if di == ref:
                    continue
                add({di: 1.0, ref: -1.0, t: BIG}, -BIG * 2, BIG)
                add({di: 1.0, ref: -1.0, t: -BIG}, -BIG, BIG * 2)
            add({**{t: 1.0 for t in ts}, v_out: -1.0}, 0, BIG)
            add({v: 1.0 for v in choice}, 1, 1)

    # ---- objective
    obj: dict[int, float] = {}
    if objective == "target":
        for z, (expr, const) in net_expr.items():
            zi = zones[z]
            target = float(zi.target_area_m2) / (UNIT_M * UNIT_M)
            d = nvar; nvar += 1; continuous.append(d)
            add({**expr, d: -1.0}, -np.inf, target - const)                      # d >= net - target
            if getattr(zi, "role", None) not in CIRC:
                add({**{v: -cf for v, cf in expr.items()}, d: -1.0}, -np.inf, const - target)
            obj[d] = 1.0 / target
    elif objective == "area":
        for z, (expr, const) in net_expr.items():
            if getattr(zones[z], "role", None) in CIRC:
                continue
            for v, cf in expr.items():
                obj[v] = obj.get(v, 0.0) - cf
    c = np.zeros(nvar)
    for v, cf in obj.items():
        c[v] = cf
    A = lil_matrix((len(rows_), nvar))
    for i, coefs in enumerate(rows_):
        for v, cf in coefs.items():
            A[i, v] = cf
    integrality = np.ones(nvar)
    for v in continuous:
        integrality[v] = 0.0
    lb = np.zeros(nvar); ub = np.full(nvar, float(BIG))
    for v in binaries:
        ub[v] = 1.0
    res = milp(c=c, constraints=LinearConstraint(A.tocsr(), np.array(lbs, float), np.array(ubs, float)),
               integrality=integrality, bounds=Bounds(lb, ub), options={"time_limit": time_limit_s})
    if res.status == 0 and res.x is not None:
        heights = tuple(grids[r][max(range(len(grids[r])), key=lambda j: res.x[z_idx[(r, j)]])] for r in range(R))
        xs = {z: (int(round(res.x[x0_idx[z]])), int(round(res.x[x1_idx[z]]))) for z in layout.zones}
        return CellsResult("FEASIBLE", f"cells; {len(rows_)} constraints, {nvar} variables", heights, xs, y_start)
    if res.status == 2:
        return CellsResult("INFEASIBLE", f"cells; HiGHS: {res.message}")
    return CellsResult("UNKNOWN", f"cells; HiGHS: {res.message}")


def cells_placement(layout: CellLayout, zones: dict, required, envelope: Envelope, *, min_contact_u=None,
                    k: int = 12, rounds: int = 3, objective: str = "target", time_limit_s: float = 10.0) -> CellsResult:
    """The fixed point on wall types: solve, read the real sides off the placement, re-solve with
    exact insets; an exact-inset refusal is returned as such."""
    from app.vertical_slice.staircase_sizing import sides_from_rects
    sides = None
    last = None
    for _ in range(rounds):
        res = milp_cells(layout, zones, required, envelope, min_contact_u=min_contact_u, k=k,
                         objective=objective, sides=sides, time_limit_s=time_limit_s)
        if res.status != "FEASIBLE":
            return res
        real = sides_from_rects(cells_rects(layout, res), zones)
        if real == sides:
            return res
        sides, last = real, res
    return last
