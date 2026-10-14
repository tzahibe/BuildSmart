"""Formulation B of ADR-001 as an ORACLE for formulation A (#197, Gate 2 pivot).

`staircase_sizing` answers "size these bands inside this envelope" exactly at a fixed height
vector, but its height SEARCH (alternating projection, enumeration, branch-and-bound) returns
UNKNOWN on the L and the strip cases — which does not say whether a solution exists. This module
asks that question with a mixed-integer program over the SAME constraints: every band's height is
chosen from a candidate grid by binaries, widths are integer boundary positions on the 5 cm grid,
and each cell's net area / short side / aspect, every contact's door width, band connectivity, the
depth cap and the envelope's horizontal extent per band (through "above/below each step depth"
binaries) are linear. Solved by `scipy.optimize.milp` (HiGHS), already a dependency — no new
spend, no `python-sat`.

What it proves: INFEASIBLE means no band layout with heights on the grid satisfies the
constraints — a statement about formulation A on this candidate, not about the house. FEASIBLE
returns a height vector that the exact width solver then realizes (with alignment) — the oracle
never produces geometry itself. Alignment is NOT in the oracle: it first asks whether the family
has any solution at all; alignment is asked of the found heights afterwards.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from app.vertical_slice.band_sizing import _height_bounds
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.geometry_core.model import UNIT_M, m_to_u
from app.vertical_slice.staircase_sizing import _cells_and_nodes

BIG = 10_000          # units; the envelope is never that wide


@dataclass(frozen=True)
class OracleResult:
    status: str                      # FEASIBLE | INFEASIBLE | UNKNOWN | BAND_GAP
    heights_u: tuple[int, ...] = ()
    detail: str = ""
    #: the full placement when FEASIBLE: per band (start, boundaries..., end) in units
    band_x_u: tuple[tuple[int, ...], ...] = ()
    y_start_u: int = 0
    #: stacks (2D wing): each member's own height, top to bottom inside its column
    member_heights_u: dict = field(default_factory=dict)

    def as_sizing(self):
        """The oracle's placement in the exact sizer's own result type, so `rects()` /
        `band_rects()` and `realize_cells` need no second path."""
        from app.vertical_slice.staircase_sizing import StaircaseSizing
        return StaircaseSizing(self.status, self.heights_u, self.band_x_u, 0, self.detail,
                               y_start_u=self.y_start_u)


def _height_grid(lo: int, hi: int, k: int) -> list[int]:
    if hi <= lo:
        return [lo]
    vals = sorted({lo + round(i * (hi - lo) / (k - 1)) for i in range(k)})
    return vals


def milp_heights(bands, zones, required, envelope: Envelope, *, min_contact_u: dict | None = None,
                 k: int = 10, tol_m2: float = 0.01, time_limit_s: float = 10.0,
                 align: bool = False, sides: dict | None = None,
                 objective: str = "feasible", stacks: dict | None = None) -> OracleResult:
    """`align=True` adds the one-wall-type-per-side rule as a disjunction: a band's start/end
    either coincides with a cell boundary of the band above or lies outside it, and the band
    above's endpoint that falls strictly inside this band becomes one of this band's boundaries.
    `sides` feeds back real wall types for exact insets (the fixed point `milp_placement` runs)."""
    cells, band_nodes, N = _cells_and_nodes(bands, zones, sides)
    R = len(bands)
    req = [tuple(e) for e in required]
    # stacks (the 2D wing, `stacks.py`): a pseudo-cell is replaced by its MEMBERS — same column
    # (c0, c1), own heights summing to the band's. The pseudo's bounds are never applied.
    stacks = stacks or {}
    from app.vertical_slice.band_sizing import CellSpec
    from app.vertical_slice.geometry_core.model import WallType, inset_u
    ext_i, part_i = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION)
    members: list[CellSpec] = []          # CellSpec per member, r/c0/c1 = the column's
    member_of: dict[str, tuple[str, int, int]] = {}   # member id -> (pseudo id, index, count)
    zones_all = dict(zones)
    for c in list(cells):
        if c.zone_id not in stacks:
            continue
        cells.remove(c)
        ms = stacks[c.zone_id]
        for i, m in enumerate(ms):
            known = (sides or {}).get(m.zone_id)
            if known is not None:
                iw = inset_u(known["W"]) + inset_u(known["E"]); ih = inset_u(known["N"]) + inset_u(known["S"])
            else:
                iw = c.inset_w_u
                ih = (ext_i if i == 0 else part_i) + (ext_i if i == len(ms) - 1 else part_i)
            members.append(CellSpec(m.zone_id, c.r, c.c0, c.c1, m.min_area_m2, m.max_area_m2,
                                    m.min_short_side_m, m.max_aspect_ratio, iw, ih))
            member_of[m.zone_id] = (c.zone_id, i, len(ms))
            zones_all[m.zone_id] = m
    by_zone = {c.zone_id: c for c in cells + members}

    # depth: the same start / cap rule as the sizer
    windows = envelope.split_depth_windows_u()
    y_start = 0
    while windows and windows[0][0] <= y_start:
        y_start = windows[0][1]; windows = windows[1:]
    h_cap = envelope.depth_u - y_start
    if windows:
        h_cap = min(h_cap, windows[0][0] - y_start)

    hL0, hU0 = [0] * R, [h_cap] * R
    for pair, need in (min_contact_u or {}).items():
        a, b = tuple(pair)
        if need > 1 and a in by_zone and b in by_zone and by_zone[a].r == by_zone[b].r:
            hL0[by_zone[a].r] = max(hL0[by_zone[a].r], need)
    for c in cells:
        lo, hi = _height_bounds(c, tol_m2, h_cap)
        hL0[c.r] = max(hL0[c.r], lo); hU0[c.r] = min(hU0[c.r], hi)
    for pid in stacks:
        col = [m for m in members if member_of[m.zone_id][0] == pid]
        hL0[col[0].r] = max(hL0[col[0].r], sum(m_to_u(m.min_short_m) + m.inset_h_u for m in col))
    if any(hL0[r] > hU0[r] for r in range(R)):
        return OracleResult("INFEASIBLE", detail="a band's cells have no common feasible depth")
    if sum(hL0) > h_cap:
        return OracleResult("BAND_GAP" if windows else "INFEASIBLE",
                            detail="the bands' minimum depths exceed the usable depth")
    grids = [_height_grid(hL0[r], hU0[r], k) for r in range(R)]

    # the envelope's extent on each depth segment inside [y_start, y_start + h_cap]
    _, miny, _, _ = envelope.polygon.bounds
    step_ys = sorted({y_start, y_start + h_cap} | {m_to_u(vy - miny) for _, vy in envelope.vertices_m
                                                    if y_start < m_to_u(vy - miny) < y_start + h_cap})
    segments = []                                     # (y0, y1, L, R) — one interval each (else BAND_GAP)
    for y0, y1 in itertools.pairwise(step_ys):
        ivs = envelope.extent_u(y0, y1)
        if len(ivs) != 1:
            return OracleResult("BAND_GAP", detail=f"the envelope splits between depths {y0} and {y1} u")
        segments.append((y0, y1, ivs[0][0], ivs[0][1]))
    inner_steps = step_ys[1:-1]

    # ---- variables: x[0..N-1] (int units), z[r][k] (binary), a[r][d], b[r][d] (binary)
    nx = N
    z_idx = {}
    for r in range(R):
        for kk in range(len(grids[r])):
            z_idx[(r, kk)] = nx; nx += 1
    a_idx, b_idx = {}, {}
    for r in range(R):
        for d in inner_steps:
            a_idx[(r, d)] = nx; nx += 1               # band r has some part ABOVE depth d
            b_idx[(r, d)] = nx; nx += 1               # band r has some part BELOW depth d
    # members: one binary per candidate height (every unit from the member's own minimum up to
    # the band's maximum — unit steps so the members' sum can equal any band height exactly)
    mgrid: dict[str, list[int]] = {}
    mz_idx: dict[tuple[str, int], int] = {}
    for m in members:
        lo = m_to_u(m.min_short_m) + m.inset_h_u
        mgrid[m.zone_id] = list(range(lo, hU0[m.r] + 1))
        for j in range(len(mgrid[m.zone_id])):
            mz_idx[(m.zone_id, j)] = nx; nx += 1
    nvar = nx
    rows, lbs, ubs = [], [], []

    def add(coefs: dict[int, float], lb: float, ub: float) -> None:
        rows.append(coefs); lbs.append(lb); ubs.append(ub)

    def h_expr(r: int) -> dict[int, float]:
        return {z_idx[(r, kk)]: float(grids[r][kk]) for kk in range(len(grids[r]))}

    def y_expr(r: int) -> dict[int, float]:           # y_r = y_start + sum_{i<r} h_i
        e: dict[int, float] = {}
        for i in range(r):
            for v, cft in h_expr(i).items():
                e[v] = e.get(v, 0.0) + cft
        return e

    # one height per band
    for r in range(R):
        add({z_idx[(r, kk)]: 1.0 for kk in range(len(grids[r]))}, 1, 1)
    # depth cap
    tot: dict[int, float] = {}
    for r in range(R):
        for v, cft in h_expr(r).items():
            tot[v] = tot.get(v, 0.0) + cft
    add(tot, 0, h_cap)
    # x[0] is the origin
    add({0: 1.0}, 0, 0)
    # cells: width >= 1; net area / short side / aspect at the selected height (big-M on z)
    for c in cells:
        w = {c.c1: 1.0, c.c0: -1.0}
        add(dict(w), 1, BIG)
        a_lo, a_hi = c.min_area_m2 / (UNIT_M * UNIT_M), c.max_area_m2 / (UNIT_M * UNIT_M)
        ms = m_to_u(c.min_short_m)
        for kk, H in enumerate(grids[c.r]):
            hn = H - c.inset_h_u                        # net height at this candidate
            zv = z_idx[(c.r, kk)]
            if hn < 1:
                add({zv: 1.0}, 0, 0); continue        # this height is impossible for this cell
            # (w - iw) * hn >= a_lo  ->  w >= a_lo/hn + iw   (active when z = 1)
            need_w = a_lo / hn + c.inset_w_u
            add({**w, zv: -BIG}, need_w - BIG, BIG)
            # (w - iw) * hn <= a_hi  ->  w <= a_hi/hn + iw
            max_w = a_hi / hn + c.inset_w_u
            add({**w, zv: BIG}, -BIG, max_w + BIG)
            # short side: net width >= min short, and net height >= min short (filter)
            if hn < ms:
                add({zv: 1.0}, 0, 0); continue
            add({**w, zv: -BIG}, ms + c.inset_w_u - BIG, BIG)
            # aspect: net width <= asp * hn ; net width >= hn / asp
            add({**w, zv: BIG}, -BIG, c.max_aspect * hn + c.inset_w_u + BIG)
            add({**w, zv: -BIG}, hn / c.max_aspect + c.inset_w_u - BIG, BIG)
    # members: one height each, the column's heights sum to the band's, own area / short / aspect
    def mh_expr(mid: str) -> dict[int, float]:
        return {mz_idx[(mid, j)]: float(H) for j, H in enumerate(mgrid[mid])}
    for pid in stacks:
        col = [m for m in members if member_of[m.zone_id][0] == pid]
        total = dict(h_expr(col[0].r))
        for m in col:
            add({mz_idx[(m.zone_id, j)]: 1.0 for j in range(len(mgrid[m.zone_id]))}, 1, 1)
            for v, cft in mh_expr(m.zone_id).items():
                total[v] = total.get(v, 0.0) - cft
        add(total, 0, 0)                                  # band height - sum(member heights) = 0
    for m in members:
        w = {m.c1: 1.0, m.c0: -1.0}
        a_lo, a_hi = m.min_area_m2 / (UNIT_M * UNIT_M), m.max_area_m2 / (UNIT_M * UNIT_M)
        ms_ = m_to_u(m.min_short_m)
        for j, H in enumerate(mgrid[m.zone_id]):
            hn = H - m.inset_h_u
            zv = mz_idx[(m.zone_id, j)]
            if hn < 1 or hn < ms_:
                add({zv: 1.0}, 0, 0); continue
            add({**w, zv: -BIG}, a_lo / hn + m.inset_w_u - BIG, BIG)
            add({**w, zv: BIG}, -BIG, a_hi / hn + m.inset_w_u + BIG)
            add({**w, zv: -BIG}, ms_ + m.inset_w_u - BIG, BIG)
            add({**w, zv: BIG}, -BIG, m.max_aspect * hn + m.inset_w_u + BIG)
            add({**w, zv: -BIG}, hn / m.max_aspect + m.inset_w_u - BIG, BIG)
    # required contacts
    for a, b in req:
        ca, cb = by_zone[a], by_zone[b]
        need = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
        ma, mb = member_of.get(a), member_of.get(b)
        if ma and mb and ma[0] == mb[0]:
            if abs(ma[1] - mb[1]) != 1:
                return OracleResult("INFEASIBLE", detail=f"{a}-{b} are not neighbours in their stack")
            add({ca.c1: 1.0, ca.c0: -1.0}, need, BIG)      # they share the column's width
            continue
        if ca.r == cb.r:
            if abs(ca.c0 - cb.c0) != 1:
                return OracleResult("INFEASIBLE", detail=f"{a}-{b} share a band but are not consecutive")
            # a member touches its side neighbour along its OWN height
            for mid, info in ((a, ma), (b, mb)):
                if info and need > 1:
                    add(mh_expr(mid), need, BIG)
            continue
        if abs(ca.r - cb.r) != 1:
            return OracleResult("INFEASIBLE", detail=f"{a}-{b} are not in consecutive bands")
        # a member reaches the band above only from the top of its stack, the band below only from the bottom
        for mid, info, other in ((a, ma, cb), (b, mb, ca)):
            if info:
                upper = other.r < by_zone[mid].r
                if (upper and info[1] != 0) or (not upper and info[1] != info[2] - 1):
                    return OracleResult("INFEASIBLE", detail=f"{mid} is buried in its stack and cannot reach {a if mid == b else b}")
        add({cb.c1: 1.0, ca.c0: -1.0}, need, BIG)
        add({ca.c1: 1.0, cb.c0: -1.0}, need, BIG)
    # consecutive bands overlap by >= 1
    for r in range(R - 1):
        s0, e0 = band_nodes[r][0], band_nodes[r][-1]
        s1, e1 = band_nodes[r + 1][0], band_nodes[r + 1][-1]
        add({e0: 1.0, s1: -1.0}, 1, BIG)
        add({e1: 1.0, s0: -1.0}, 1, BIG)
    # envelope: bbox for every band; per step depth, the extent on the side(s) the band touches
    Lbox, Rbox = min(sg[2] for sg in segments), max(sg[3] for sg in segments)
    for r in range(R):
        s, e = band_nodes[r][0], band_nodes[r][-1]
        add({s: 1.0}, Lbox, BIG); add({e: 1.0}, -BIG, Rbox)
    for d in inner_steps:
        above = [sg for sg in segments if sg[1] <= d]   # segments entirely above d
        below = [sg for sg in segments if sg[0] >= d]
        La, Ra = max(sg[2] for sg in above), min(sg[3] for sg in above)
        Lb, Rb = max(sg[2] for sg in below), min(sg[3] for sg in below)
        for r in range(R):
            s, e = band_nodes[r][0], band_nodes[r][-1]
            av, bv = a_idx[(r, d)], b_idx[(r, d)]
            y = y_expr(r); hr = h_expr(r)
            # a = 0  ->  y_r >= d      (band entirely below d)   : y_r - d >= -BIG * a
            add({**y, av: BIG}, d, BIG + d + BIG)
            # b = 0  ->  y_r + h_r <= d  (band entirely above d) : y_r + h_r <= d + BIG * b
            yh = dict(y)
            for v, cft in hr.items():
                yh[v] = yh.get(v, 0.0) + cft
            yh[bv] = yh.get(bv, 0.0) - BIG
            add(yh, -BIG, d)
            # at least one side is touched (a band cannot vanish)
            add({av: 1.0, bv: 1.0}, 1, 2)
            # extents conditional on the side touched
            add({s: 1.0, av: BIG}, La, BIG + La + BIG)        # a=1 -> s >= La  (s + BIG a >= La + BIG) rewritten below
            # the line above is loosened; write the exact conditional forms instead:
            rows.pop(); lbs.pop(); ubs.pop()
            add({s: 1.0, av: -BIG}, La - BIG, BIG)            # s >= La - BIG(1-a)  ->  s + BIG a >= La ... (a=1 active)
            add({e: 1.0, av: BIG}, -BIG, Ra + BIG)            # e <= Ra + BIG(1-a)
            add({s: 1.0, bv: -BIG}, Lb - BIG, BIG)
            add({e: 1.0, bv: BIG}, -BIG, Rb + BIG)

    first_align_var = nvar
    if align:
        for r in range(R - 1):
            U, D = band_nodes[r], band_nodes[r + 1]
            u0, uk = U[0], U[-1]
            for endpoint, outside_is_left in ((D[0], True), (D[-1], False)):
                # choice: coincide with one of U's boundaries, or lie outside U on the near side
                choice_vars = []
                for uj in U:
                    v = nvar; nvar += 1; choice_vars.append(v)
                    add({endpoint: 1.0, uj: -1.0, v: BIG}, -BIG, BIG)         # |endpoint - uj| <= BIG(1-v)
                    add({endpoint: 1.0, uj: -1.0, v: -BIG}, -BIG, BIG)
                    rows[-2] = {endpoint: 1.0, uj: -1.0, v: BIG}; lbs[-2] = -BIG; ubs[-2] = BIG
                    rows[-1] = {endpoint: 1.0, uj: -1.0, v: -BIG}; lbs[-1] = -BIG; ubs[-1] = BIG
                    # exact forms: endpoint - uj <= BIG*(1-v)  ->  endpoint - uj + BIG v <= BIG
                    rows[-2] = {endpoint: 1.0, uj: -1.0, v: BIG}; lbs[-2] = -BIG * 2; ubs[-2] = BIG
                    #              endpoint - uj >= -BIG*(1-v) ->  endpoint - uj - BIG v >= -BIG
                    rows[-1] = {endpoint: 1.0, uj: -1.0, v: -BIG}; lbs[-1] = -BIG; ubs[-1] = BIG * 2
                v_out = nvar; nvar += 1; choice_vars.append(v_out)
                if outside_is_left:
                    add({endpoint: 1.0, u0: -1.0, v_out: BIG}, -BIG, BIG)     # endpoint <= u0 when v_out
                    # and then u0 must be one of D's interior boundaries
                    ts = []
                    for di in D[1:-1]:
                        t = nvar; nvar += 1; ts.append(t)
                        add({di: 1.0, u0: -1.0, t: BIG}, -BIG * 2, BIG)
                        add({di: 1.0, u0: -1.0, t: -BIG}, -BIG, BIG * 2)
                    add({**{t: 1.0 for t in ts}, v_out: -1.0}, 0, BIG)        # sum t >= v_out
                else:
                    add({endpoint: 1.0, uk: -1.0, v_out: -BIG}, -BIG, BIG)    # endpoint >= uk when v_out
                    ts = []
                    for di in D[1:-1]:
                        t = nvar; nvar += 1; ts.append(t)
                        add({di: 1.0, uk: -1.0, t: BIG}, -BIG * 2, BIG)
                        add({di: 1.0, uk: -1.0, t: -BIG}, -BIG, BIG * 2)
                    add({**{t: 1.0 for t in ts}, v_out: -1.0}, 0, BIG)
                add({v: 1.0 for v in choice_vars}, 1, 1)

    binary_end = nvar
    obj_c: dict[int, float] = {}
    continuous: list[int] = []
    if objective == "target":
        items = [(c, grids[c.r], [z_idx[(c.r, kk)] for kk in range(len(grids[c.r]))]) for c in cells]
        items += [(m, mgrid[m.zone_id], [mz_idx[(m.zone_id, j)] for j in range(len(mgrid[m.zone_id]))])
                  for m in members]
        nvar, obj_c, continuous = _target_objective(items, zones_all, nvar, add, w_hi=envelope.width_u)
    A = lil_matrix((len(rows), nvar))
    for i, coefs in enumerate(rows):
        for v, cft in coefs.items():
            A[i, v] = cft
    integrality = np.ones(nvar)
    for v in continuous:
        integrality[v] = 0.0
    lb = np.zeros(nvar); ub = np.full(nvar, float(BIG))
    for v in list(z_idx.values()) + list(a_idx.values()) + list(b_idx.values()) + list(mz_idx.values()):
        ub[v] = 1.0
    for v in range(first_align_var, binary_end):
        ub[v] = 1.0
    c = np.zeros(nvar)
    for v, cft in obj_c.items():
        c[v] = cft
    if objective == "area":
        # Gate 3's lever, not a shape: grow the HABITABLE rooms (a feasibility program leaves every
        # room at its minimum and hands the rest to circulation). Cell area is width x height and
        # height is a binary choice, so the linear proxy is width weighted by the band's mid-grid
        # height; circulation cells carry no weight and are held by their own bounds.
        from app.vertical_slice.geometry_core.model import ProgramRole
        circ = {ProgramRole.HALL, ProgramRole.CIRCULATION}
        for cell in cells:
            if getattr(zones[cell.zone_id], "role", None) in circ:
                continue
            mid_h = grids[cell.r][len(grids[cell.r]) // 2]
            c[cell.c1] -= float(mid_h)            # minimise -(width) -> maximise width
            c[cell.c0] += float(mid_h)
    res = milp(c=c, constraints=LinearConstraint(A.tocsr(), np.array(lbs, float), np.array(ubs, float)),
               integrality=integrality, bounds=Bounds(lb, ub), options={"time_limit": time_limit_s})
    if res.status == 0 and res.x is not None:
        heights = []
        for r in range(R):
            kk = max(range(len(grids[r])), key=lambda j: res.x[z_idx[(r, j)]])
            heights.append(grids[r][kk])
        band_x = tuple(tuple(int(round(res.x[i])) for i in band_nodes[r]) for r in range(R))
        mh = {m.zone_id: mgrid[m.zone_id][max(range(len(mgrid[m.zone_id])),
                                              key=lambda j: res.x[mz_idx[(m.zone_id, j)]])] for m in members}
        return OracleResult("FEASIBLE", tuple(heights), detail=f"{len(rows)} constraints, {nvar} variables",
                            band_x_u=band_x, y_start_u=y_start, member_heights_u=mh)
    if res.status == 2:
        return OracleResult("INFEASIBLE", detail=f"HiGHS: {res.message}")
    return OracleResult("UNKNOWN", detail=f"HiGHS: {res.message}")


def _target_objective(items, zones, nvar, add, *, w_hi: int, extra=()):
    """Objective "target" (A1): every room's EXACT net area tracks the programme's target.

    Net area is (w - iw)(h - ih) with w = c1 - c0 and h a binary choice from the band's grid, so
    w*h = sum_k H_k * p_k with p_k = w * z_k linearised exactly (McCormick with a binary). The
    objective minimises the RELATIVE deviation |net - target| / target per habitable room, and the
    relative overshoot (net - target)+ / target per circulation room — the hall is no longer the
    sink, and rooms are pulled to their targets rather than to their maxima. `extra` carries cells
    whose net-area expression is already linear (the spine): (zone_id, expr, const).

    Returns (nvar, c, continuous): c the objective coefficients by variable; `continuous` the
    product and deviation variables — p = w*z is exact for a binary z whatever p's integrality, and
    leaving them continuous keeps the branch-and-bound on the heights and boundaries only."""
    from app.vertical_slice.geometry_core.model import ProgramRole
    circ = {ProgramRole.HALL, ProgramRole.CIRCULATION}
    c: dict[int, float] = {}
    continuous: list[int] = []
    terms = []
    for cell, grid, zvars in items:
        w = {cell.c1: 1.0, cell.c0: -1.0}
        expr = {cell.c1: -float(cell.inset_h_u), cell.c0: float(cell.inset_h_u)}     # - ih * w
        for kk, Hk in enumerate(grid):
            zv = zvars[kk]
            pv = nvar; nvar += 1; continuous.append(pv)
            add({pv: 1.0, zv: -float(w_hi)}, -BIG, 0)                                  # p <= wh z
            add({pv: 1.0, zv: -1.0}, 0, BIG)                                           # p >= 1 z
            add({pv: 1.0, **{k: -v for k, v in w.items()}, zv: -1.0}, -BIG, -1)        # p <= w - 1(1-z)
            add({pv: 1.0, **{k: -v for k, v in w.items()}, zv: -float(w_hi)}, -w_hi, BIG)   # p >= w - wh(1-z)
            expr[pv] = float(Hk)
            expr[zv] = expr.get(zv, 0.0) - float(cell.inset_w_u) * Hk                  # - iw * h
        terms.append((cell.zone_id, expr, float(cell.inset_w_u * cell.inset_h_u)))
    terms.extend(extra)
    for zone_id, expr, const in terms:
        z = zones[zone_id]
        target = float(z.target_area_m2) / (UNIT_M * UNIT_M)
        d = nvar; nvar += 1; continuous.append(d)
        # d >= net - target  (net = expr + const). Areas are in u^2 (thousands), so "no bound" here
        # must be a real -inf: BIG (10 000) is a node-position infinity and would bind.
        add({**expr, d: -1.0}, -np.inf, target - const)
        if getattr(z, "role", None) not in circ:
            add({**{k: -v for k, v in expr.items()}, d: -1.0}, -np.inf, const - target)   # d >= target - net
        c[d] = 1.0 / target
    return nvar, c, continuous


def milp_placement(bands, zones, required, envelope: Envelope, *, min_contact_u: dict | None = None,
                   k: int = 12, rounds: int = 3, objective: str = "area", stacks: dict | None = None) -> OracleResult:
    """The aligned oracle as THE sizer: solve, read the real wall types off the placement, re-solve
    with exact insets until they stop changing (the same fixed point the sizer runs), and hand the
    final placement to `realize_cells`. Every refusal downstream is then a validator's own."""
    from app.vertical_slice.staircase_sizing import sides_from_rects
    sides = None
    last = None
    for _ in range(rounds):
        res = milp_heights(bands, zones, required, envelope, min_contact_u=min_contact_u, k=k,
                           align=True, sides=sides, objective=objective, stacks=stacks)
        if res.status != "FEASIBLE":
            return last if (last is not None and last.status == "FEASIBLE") else res
        real = sides_from_rects(*placement_rects(bands, zones, res, stacks))
        if real == sides:
            return res
        sides, last = real, res
    return last


def placement_rects(bands, zones, res: OracleResult, stacks: dict | None = None):
    """(rects, intents) of a placement with every stack expanded into its members — what the
    realizer and the wall-type fixed point see. `stacks`: pseudo id -> member intents, top first."""
    from app.ai_harness.shape_agnostic.stacks import expand_rects
    rects = res.as_sizing().rects(bands)
    if not stacks:
        return rects, zones
    ids = {pid: tuple(m.zone_id for m in ms) for pid, ms in stacks.items()}
    intents = {z: zi for z, zi in zones.items() if z not in stacks}
    for ms in stacks.values():
        for m in ms:
            intents[m.zone_id] = m
    return expand_rects(rects, ids, res.member_heights_u), intents


# ----------------------------------------------------------------------------- the spine (path B)

def milp_spine_placement(layout, zones, required, envelope: Envelope, *, min_contact_u: dict | None = None,
                         k: int = 12, tol_m2: float = 0.01, time_limit_s: float = 10.0,
                         objective: str = "area", rounds: int = 3) -> OracleResult:
    """The spine oracle as THE sizer, like `milp_placement`: solve, read the real wall types off the
    placement, re-solve with exact insets until they stop changing."""
    from app.vertical_slice.staircase_sizing import sides_from_rects
    zones = spine_intents(layout, zones)
    sides = None
    last = None
    for _ in range(rounds):
        res = _spine_once(layout, zones, required, envelope, min_contact_u=min_contact_u, k=k, tol_m2=tol_m2,
                          time_limit_s=time_limit_s, objective=objective, sides=sides)
        if res.status != "FEASIBLE":
            # an earlier round's placement was sized with ESTIMATED insets; the exact ones refuse it,
            # and the realizer's C3 would too — so the refusal is the answer, not the estimate
            return res
        rects, _wings = spine_geometry(layout, res)
        real = sides_from_rects(rects, zones)
        if real == sides:
            return res
        sides, last = real, res
    return last


def spine_intents(layout, zones: dict) -> dict:
    """The programme with the spine's intent declared as a corridor: a cell that spans every band
    is long by nature, so its aspect bound is `SPINE_MAX_ASPECT` (never below the programme's own).
    Everything else — areas, short sides, every other room — is the programme's, untouched; the
    validators then hold the realized spine to exactly this declared intent."""
    z = zones[layout.spine]
    if z.max_aspect_ratio >= SPINE_MAX_ASPECT:
        return zones
    from dataclasses import replace
    return {**zones, layout.spine: replace(z, max_aspect_ratio=SPINE_MAX_ASPECT)}


def _spine_once(layout, zones, required, envelope: Envelope, *, min_contact_u, k, tol_m2, time_limit_s,
                objective, sides, _skip: frozenset = frozenset()):
    """The aligned oracle for a `SpineLayout` (path B): one circulation cell spans EVERY band
    between a shared pair of column nodes (xa, xb); each band is left cells, the spine, right
    cells. Per band the system is `milp_heights`' (cells, contacts, envelope extents, alignment
    with the neighbouring band); the shared nodes make the alignment of a band edge that IS xa or
    xb hold by identity. The spine's own area / short side / aspect are exact through the McCormick
    products below. Returns FEASIBLE with heights and per-band boundaries, or INFEASIBLE/UNKNOWN."""
    from app.vertical_slice.band_sizing import CellSpec
    from app.vertical_slice.doors import ENTRANCE_DOOR_WIDTH_M
    from app.vertical_slice.geometry_core.model import WallType, inset_u

    spine = layout.spine
    R = layout.n_rows
    sec_a, sec_b = layout.section
    ext_i, part_i = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION)

    def spec(zid, r, c0, c1, first, last):
        z = zones[zid]
        known = (sides or {}).get(zid)
        iw = (inset_u(known["W"]) + inset_u(known["E"])) if known else ((ext_i if first else part_i) + (ext_i if last else part_i))
        ih = (inset_u(known["N"]) + inset_u(known["S"])) if known else ext_i * 2
        return CellSpec(zid, r, c0, c1, z.min_area_m2, z.max_area_m2, z.min_short_side_m, z.max_aspect_ratio, iw, ih)

    # ---- nodes: 0 = origin; xa/xb shared by the section's bands; per band s, boundaries..., e
    xa, xb = 1, 2
    nxt = 3
    band_nodes: list[list[int]] = []
    cells: list = []
    plain_rows = [(r, b) for r, b in enumerate(layout.top)] + \
                 [(sec_b + r, b) for r, b in enumerate(layout.bottom)]
    for r, band in plain_rows:
        ids = [nxt]; nxt += 1
        for i, zid in enumerate(band):
            nid = nxt; nxt += 1
            cells.append(spec(zid, r, ids[-1], nid, i == 0, i == len(band) - 1))
            ids.append(nid)
        band_nodes.append((r, ids))
    for rr, (left, right) in enumerate(layout.bands):
        r = sec_a + rr
        ids = []
        if left:
            ids.append(nxt); nxt += 1
            for i, zid in enumerate(left):
                nid = xa if i == len(left) - 1 else nxt
                if nid != xa:
                    nxt += 1
                cells.append(spec(zid, r, ids[-1], nid, i == 0, False))
                ids.append(nid)
        else:
            ids = [xa]
        ids.append(xb)
        for i, zid in enumerate(right):
            nid = nxt; nxt += 1
            cells.append(spec(zid, r, ids[-1], nid, False, i == len(right) - 1))
            ids.append(nid)
        band_nodes.append((r, ids))
    band_nodes = [ids for _, ids in sorted(band_nodes, key=lambda t: t[0])]
    N = nxt
    s_nodes = [bn[0] for bn in band_nodes]
    e_nodes = [bn[-1] for bn in band_nodes]
    by_zone = {c.zone_id: c for c in cells}

    # ---- depth
    windows = envelope.split_depth_windows_u()
    y_start = 0
    while windows and windows[0][0] <= y_start:
        y_start = windows[0][1]; windows = windows[1:]
    h_cap = envelope.depth_u - y_start
    if windows:
        h_cap = min(h_cap, windows[0][0] - y_start)
    hL0, hU0 = [0] * R, [h_cap] * R
    # a spine neighbour's door sits on that band's height
    for pair, need in (min_contact_u or {}).items():
        a, b = tuple(pair)
        if need > 1 and spine in (a, b):
            other = b if a == spine else a
            if other in by_zone and sec_a <= by_zone[other].r < sec_b:
                hL0[by_zone[other].r] = max(hL0[by_zone[other].r], need)
        elif need > 1 and a in by_zone and b in by_zone and by_zone[a].r == by_zone[b].r:
            hL0[by_zone[a].r] = max(hL0[by_zone[a].r], need)
    for c in cells:
        lo, hi = _height_bounds(c, tol_m2, h_cap)
        hL0[c.r] = max(hL0[c.r], lo); hU0[c.r] = min(hU0[c.r], hi)
    if any(hL0[r] > hU0[r] for r in range(R)) or sum(hL0) > h_cap:
        return OracleResult("INFEASIBLE", detail="no common feasible band depths under the spine")
    grids = [_height_grid(hL0[r], hU0[r], k) for r in range(R)]

    _, miny, _, _ = envelope.polygon.bounds
    step_ys = sorted({y_start, y_start + h_cap} | {m_to_u(vy - miny) for _, vy in envelope.vertices_m
                                                    if y_start < m_to_u(vy - miny) < y_start + h_cap})
    segments = []
    for y0, y1 in itertools.pairwise(step_ys):
        ivs = envelope.extent_u(y0, y1)
        if len(ivs) != 1:
            return OracleResult("BAND_GAP", detail=f"the envelope splits between depths {y0} and {y1} u")
        segments.append((y0, y1, ivs[0][0], ivs[0][1]))
    inner_steps = step_ys[1:-1]

    nx = N
    z_idx = {}
    for r in range(R):
        for kk in range(len(grids[r])):
            z_idx[(r, kk)] = nx; nx += 1
    a_idx, b_idx = {}, {}
    for r in range(R):
        for d in inner_steps:
            a_idx[(r, d)] = nx; nx += 1
            b_idx[(r, d)] = nx; nx += 1
    nvar = nx
    rows, lbs, ubs = [], [], []

    def add(coefs, lb, ub):
        rows.append(coefs); lbs.append(lb); ubs.append(ub)

    def h_expr(r):
        return {z_idx[(r, kk)]: float(grids[r][kk]) for kk in range(len(grids[r]))}

    def y_expr(r):
        e = {}
        for i in range(r):
            for v, cft in h_expr(i).items():
                e[v] = e.get(v, 0.0) + cft
        return e

    for r in range(R):
        add({z_idx[(r, kk)]: 1.0 for kk in range(len(grids[r]))}, 1, 1)
    tot = {}
    for r in range(R):
        for v, cft in h_expr(r).items():
            tot[v] = tot.get(v, 0.0) + cft
    add(tot, 0, h_cap)
    add({0: 1.0}, 0, 0)
    # ordinary cells, exactly as milp_heights
    for c in (cells if "cells" not in _skip else ()):
        w = {c.c1: 1.0, c.c0: -1.0}
        add(dict(w), 1, BIG)
        a_lo, a_hi = c.min_area_m2 / (UNIT_M * UNIT_M), c.max_area_m2 / (UNIT_M * UNIT_M)
        ms = m_to_u(c.min_short_m)
        for kk, H in enumerate(grids[c.r]):
            hn = H - c.inset_h_u
            zv = z_idx[(c.r, kk)]
            if hn < 1 or hn < ms:
                add({zv: 1.0}, 0, 0); continue
            add({**w, zv: -BIG}, a_lo / hn + c.inset_w_u - BIG, BIG)
            add({**w, zv: BIG}, -BIG, a_hi / hn + c.inset_w_u + BIG)
            add({**w, zv: -BIG}, ms + c.inset_w_u - BIG, BIG)
            add({**w, zv: BIG}, -BIG, c.max_aspect * hn + c.inset_w_u + BIG)
            add({**w, zv: -BIG}, hn / c.max_aspect + c.inset_w_u - BIG, BIG)
    # the spine: width w = xb - xa between the shared nodes, height H = the SUM of the band heights.
    # Its net area (w - iw)(H - ih) is bilinear, but H is a sum of binary-selected grid heights, so
    # p[r,kk] = w * z[r,kk] linearizes EXACTLY (McCormick with a binary): the spine's area, short
    # side and aspect are then linear in (p, z, w) and hold exactly — no conservative bound, no
    # height windows.
    zs = zones[spine]
    known_s = (sides or {}).get(spine)
    ih_s = (inset_u(known_s["N"]) + inset_u(known_s["S"])) if known_s else ext_i * 2
    iw_s = (inset_u(known_s["W"]) + inset_u(known_s["E"])) if known_s else part_i * 2
    a_lo, a_hi = zs.min_area_m2 / (UNIT_M * UNIT_M), zs.max_area_m2 / (UNIT_M * UNIT_M)
    H_lo = sum(hL0[r] for r in range(sec_a, sec_b))
    wl = max(m_to_u(SPINE_MIN_WIDTH_M), m_to_u(zs.min_short_side_m)) + iw_s
    wh = int(a_hi / max(1, H_lo - ih_s)) + iw_s + 1
    if wl > wh:
        return OracleResult("INFEASIBLE", detail="the spine's own bounds admit no width")
    wvar = {xb: 1.0, xa: -1.0}
    add(dict(wvar), wl, wh)
    net_area = {xb: -float(ih_s), xa: float(ih_s)}          # - ih * w
    hsum = {}                                                # H = sum H[r,kk] z[r,kk]
    for r in range(sec_a, sec_b):
        for kk, Hk in enumerate(grids[r]):
            zv = z_idx[(r, kk)]
            hsum[zv] = float(Hk)
            pv = nvar; nvar += 1
            add({pv: 1.0, zv: -float(wh)}, -BIG, 0)                       # p <= wh z
            add({pv: 1.0, zv: -float(wl)}, 0, BIG)                        # p >= wl z
            add({pv: 1.0, **{k: -v for k, v in wvar.items()}, zv: -float(wl)}, -BIG, -wl)   # p <= w - wl(1-z)
            add({pv: 1.0, **{k: -v for k, v in wvar.items()}, zv: -float(wh)}, -wh, BIG)    # p >= w - wh(1-z)
            net_area[pv] = float(Hk)                                      # + H w
            net_area[zv] = net_area.get(zv, 0.0) - float(iw_s) * Hk       # - iw H
    if "spine" not in _skip:
        add(net_area, a_lo - iw_s * ih_s, a_hi - iw_s * ih_s)
    asp = float(zs.max_aspect_ratio)
    # (H - ih) <= asp (w - iw)   and   (w - iw) <= asp (H - ih)
    if "spine" not in _skip:
        add({**hsum, **{k: -asp * v for k, v in wvar.items()}}, -BIG, ih_s - asp * iw_s)
        add({**{k: -asp * v for k, v in hsum.items()}, **wvar}, -BIG, iw_s - asp * ih_s)
    # the front door: when the spine fronts the street it IS the arrival room (HALL outranks LIVING
    # in `resolve_entrance`) and needs a door width of wall each side of a door — three door widths
    if sec_a == 0 and "entrance" not in _skip:
        add(dict(wvar), 3 * m_to_u(ENTRANCE_DOOR_WIDTH_M), BIG)
    # required contacts: within a side as before; a contact with the spine holds by construction
    # inside the section (innermost cells) and is an overlap with [xa, xb] from a plain band
    for a, b in ([tuple(e) for e in required] if "contacts" not in _skip else ()):
        if spine in (a, b):
            other = by_zone[b if a == spine else a]
            if sec_a <= other.r < sec_b:
                continue
            need = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
            add({xb: 1.0, other.c0: -1.0}, need, BIG)
            add({other.c1: 1.0, xa: -1.0}, need, BIG)
            continue
        ca, cb = by_zone[a], by_zone[b]
        if ca.r == cb.r:
            continue
        if abs(ca.r - cb.r) != 1:
            return OracleResult("INFEASIBLE", detail=f"{a}-{b} are not in consecutive bands")
        need = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
        add({cb.c1: 1.0, ca.c0: -1.0}, need, BIG)
        add({ca.c1: 1.0, cb.c0: -1.0}, need, BIG)
    # consecutive bands overlap (the section's do through the spine); envelope per band
    Lbox, Rbox = min(sg[2] for sg in segments), max(sg[3] for sg in segments)
    for r in range(R):
        add({s_nodes[r]: 1.0}, Lbox, BIG); add({e_nodes[r]: 1.0}, -BIG, Rbox)
        if r + 1 < R and not (sec_a <= r < sec_b and sec_a <= r + 1 < sec_b):
            add({e_nodes[r + 1]: 1.0, s_nodes[r]: -1.0}, 1, BIG)
            add({e_nodes[r]: 1.0, s_nodes[r + 1]: -1.0}, 1, BIG)
    for d in (inner_steps if "envelope" not in _skip else ()):
        above = [sg for sg in segments if sg[1] <= d]; below = [sg for sg in segments if sg[0] >= d]
        La, Ra = max(sg[2] for sg in above), min(sg[3] for sg in above)
        Lb, Rb = max(sg[2] for sg in below), min(sg[3] for sg in below)
        for r in range(R):
            s, e = s_nodes[r], e_nodes[r]
            av, bv = a_idx[(r, d)], b_idx[(r, d)]
            y = y_expr(r); hr = h_expr(r)
            add({**y, av: BIG}, d, BIG + d + BIG)
            yh = dict(y)
            for v, cft in hr.items():
                yh[v] = yh.get(v, 0.0) + cft
            yh[bv] = yh.get(bv, 0.0) - BIG
            add(yh, -BIG, d)
            add({av: 1.0, bv: 1.0}, 1, 2)
            add({s: 1.0, av: -BIG}, La - BIG, BIG); add({e: 1.0, av: BIG}, -BIG, Ra + BIG)
            add({s: 1.0, bv: -BIG}, Lb - BIG, BIG); add({e: 1.0, bv: BIG}, -BIG, Rb + BIG)
    # alignment per band, as in milp_heights (the spine's shared nodes align trivially)
    first_align_var = nvar
    for r in (range(R - 1) if "align" not in _skip else ()):
        U, D = band_nodes[r], band_nodes[r + 1]
        u0, uk = U[0], U[-1]
        for endpoint, outside_is_left in ((D[0], True), (D[-1], False)):
            choice_vars = []
            for uj in U:
                v = nvar; nvar += 1; choice_vars.append(v)
                if uj == endpoint:
                    continue            # the spine's shared node: coincidence holds by identity
                add({endpoint: 1.0, uj: -1.0, v: BIG}, -BIG * 2, BIG)
                add({endpoint: 1.0, uj: -1.0, v: -BIG}, -BIG, BIG * 2)
            v_out = nvar; nvar += 1; choice_vars.append(v_out)
            ref = u0 if outside_is_left else uk
            if outside_is_left:
                add({endpoint: 1.0, ref: -1.0, v_out: BIG}, -BIG, BIG)
            else:
                add({endpoint: 1.0, ref: -1.0, v_out: -BIG}, -BIG, BIG)
            ts = []
            for di in D[1:-1]:
                t = nvar; nvar += 1; ts.append(t)
                if di == ref:
                    continue        # shared node: identity
                add({di: 1.0, ref: -1.0, t: BIG}, -BIG * 2, BIG)
                add({di: 1.0, ref: -1.0, t: -BIG}, -BIG, BIG * 2)
            add({**{t: 1.0 for t in ts}, v_out: -1.0}, 0, BIG)
            add({v: 1.0 for v in choice_vars}, 1, 1)

    binary_end = nvar
    obj_c: dict[int, float] = {}
    continuous: list[int] = []
    if objective == "target":
        items = [(c, grids[c.r], [z_idx[(c.r, kk)] for kk in range(len(grids[c.r]))]) for c in cells]
        nvar, obj_c, continuous = _target_objective(items, zones, nvar, add, w_hi=envelope.width_u,
                                                    extra=[(spine, net_area, float(iw_s * ih_s))])
    A = lil_matrix((len(rows), nvar))
    for i, coefs in enumerate(rows):
        for v, cft in coefs.items():
            A[i, v] = cft
    integrality = np.ones(nvar)
    for v in continuous:
        integrality[v] = 0.0
    lb = np.zeros(nvar); ub = np.full(nvar, float(BIG))
    for v in list(z_idx.values()) + list(a_idx.values()) + list(b_idx.values()):
        ub[v] = 1.0
    for v in range(first_align_var, binary_end):
        ub[v] = 1.0
    c = np.zeros(nvar)
    for v, cft in obj_c.items():
        c[v] = cft
    if objective == "area":
        from app.vertical_slice.geometry_core.model import ProgramRole
        circ = {ProgramRole.HALL, ProgramRole.CIRCULATION}
        for cell in cells:
            if getattr(zones[cell.zone_id], "role", None) in circ:
                continue
            mid_h = grids[cell.r][len(grids[cell.r]) // 2]
            c[cell.c1] -= float(mid_h); c[cell.c0] += float(mid_h)
    res = milp(c=c, constraints=LinearConstraint(A.tocsr(), np.array(lbs, float), np.array(ubs, float)),
               integrality=integrality, bounds=Bounds(lb, ub), options={"time_limit": time_limit_s})
    if res.status == 0 and res.x is not None:
        heights = []
        for r in range(R):
            kk = max(range(len(grids[r])), key=lambda j: res.x[z_idx[(r, j)]])
            heights.append(grids[r][kk])
        band_x = tuple(tuple(int(round(res.x[i])) for i in band_nodes[r]) for r in range(R))
        return OracleResult("FEASIBLE", tuple(heights), detail=f"spine; {len(rows)} constraints, {nvar} variables",
                            band_x_u=band_x, y_start_u=y_start)
    if res.status == 2:
        return OracleResult("INFEASIBLE", detail=f"spine; HiGHS: {res.message}")
    return OracleResult("UNKNOWN", detail=f"spine; HiGHS: {res.message}")


SPINE_MIN_WIDTH_M = 1.8
SPINE_MAX_ASPECT = 6.0


def spine_geometry(layout, res: OracleResult):
    """Cell rects and wing rects from a spine placement: one wing per plain band, and in the
    section each band's left part, each band's right part, and the spine — every cell inside
    exactly one wing, seams declared from geometry by `realize_cells`."""
    from app.vertical_slice.geometry_core.model import Rect
    rects: dict[str, Rect] = {}
    wings: list[Rect] = []
    sec_a, sec_b = layout.section
    y = res.y_start_u
    xa = xb = None
    for r in range(layout.n_rows):
        xs = list(res.band_x_u[r]); h = res.heights_u[r]
        if r < sec_a or r >= sec_b:
            band = layout.top[r] if r < sec_a else layout.bottom[r - sec_b]
            for i, zid in enumerate(band):
                rects[zid] = Rect(xs[i], y, xs[i + 1] - xs[i], h)
            wings.append(Rect(xs[0], y, xs[-1] - xs[0], h))
        else:
            left, right = layout.bands[r - sec_a]
            i_a = len(left)                 # index of xa in xs (s + one boundary per left cell)
            xa, xb = xs[i_a], xs[i_a + 1]
            for i, zid in enumerate(left):
                rects[zid] = Rect(xs[i], y, xs[i + 1] - xs[i], h)
            if left:
                wings.append(Rect(xs[0], y, xa - xs[0], h))
            for i, zid in enumerate(right):
                x0, x1 = xs[i_a + 1 + i], xs[i_a + 2 + i]
                rects[zid] = Rect(x0, y, x1 - x0, h)
            if right:
                wings.append(Rect(xb, y, xs[-1] - xb, h))
        y += h
    y_a = res.y_start_u + sum(res.heights_u[:sec_a])
    H = sum(res.heights_u[sec_a:sec_b])
    rects[layout.spine] = Rect(xa, y_a, xb - xa, H)
    wings.append(rects[layout.spine])
    return rects, tuple(wings)
