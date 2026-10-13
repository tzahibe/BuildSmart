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

from dataclasses import dataclass

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
                 align: bool = False, sides: dict | None = None) -> OracleResult:
    """`align=True` adds the one-wall-type-per-side rule as a disjunction: a band's start/end
    either coincides with a cell boundary of the band above or lies outside it, and the band
    above's endpoint that falls strictly inside this band becomes one of this band's boundaries.
    `sides` feeds back real wall types for exact insets (the fixed point `milp_placement` runs)."""
    cells, band_nodes, N = _cells_and_nodes(bands, zones, sides)
    R = len(bands)
    req = [tuple(e) for e in required]
    by_zone = {c.zone_id: c for c in cells}

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
    for y0, y1 in zip(step_ys, step_ys[1:]):
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
    # required contacts
    for a, b in req:
        ca, cb = by_zone[a], by_zone[b]
        if ca.r == cb.r:
            if abs(ca.c0 - cb.c0) != 1:
                return OracleResult("INFEASIBLE", detail=f"{a}-{b} share a band but are not consecutive")
            continue
        if abs(ca.r - cb.r) != 1:
            return OracleResult("INFEASIBLE", detail=f"{a}-{b} are not in consecutive bands")
        need = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
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

    A = lil_matrix((len(rows), nvar))
    for i, coefs in enumerate(rows):
        for v, cft in coefs.items():
            A[i, v] = cft
    integrality = np.ones(nvar)
    lb = np.zeros(nvar); ub = np.full(nvar, float(BIG))
    for v in list(z_idx.values()) + list(a_idx.values()) + list(b_idx.values()):
        ub[v] = 1.0
    for v in range(first_align_var, nvar):
        ub[v] = 1.0
    res = milp(c=np.zeros(nvar), constraints=LinearConstraint(A.tocsr(), np.array(lbs, float), np.array(ubs, float)),
               integrality=integrality, bounds=Bounds(lb, ub), options={"time_limit": time_limit_s})
    if res.status == 0 and res.x is not None:
        heights = []
        for r in range(R):
            kk = max(range(len(grids[r])), key=lambda j: res.x[z_idx[(r, j)]])
            heights.append(grids[r][kk])
        band_x = tuple(tuple(int(round(res.x[i])) for i in band_nodes[r]) for r in range(R))
        return OracleResult("FEASIBLE", tuple(heights), detail=f"{len(rows)} constraints, {nvar} variables",
                            band_x_u=band_x, y_start_u=y_start)
    if res.status == 2:
        return OracleResult("INFEASIBLE", detail=f"HiGHS: {res.message}")
    return OracleResult("UNKNOWN", detail=f"HiGHS: {res.message}")


def milp_placement(bands, zones, required, envelope: Envelope, *, min_contact_u: dict | None = None,
                   k: int = 12, rounds: int = 3) -> OracleResult:
    """The aligned oracle as THE sizer: solve, read the real wall types off the placement, re-solve
    with exact insets until they stop changing (the same fixed point the sizer runs), and hand the
    final placement to `realize_cells`. Every refusal downstream is then a validator's own."""
    from app.vertical_slice.staircase_sizing import sides_from_rects
    sides = None
    last = None
    for _ in range(rounds):
        res = milp_heights(bands, zones, required, envelope, min_contact_u=min_contact_u, k=k,
                           align=True, sides=sides)
        if res.status != "FEASIBLE":
            return last if (last is not None and last.status == "FEASIBLE") else res
        real = sides_from_rects(res.as_sizing().rects(bands), zones)
        if real == sides:
            return res
        sides, last = real, res
    return last
