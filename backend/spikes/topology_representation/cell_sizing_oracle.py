"""#142D — exact per-cell sizing ORACLE for a band (GridWing) witness. Experimental, isolated; not a
production solver.

A band witness fixes the topology: R horizontal bands, each tiled left-to-right by cells spanning
contiguous global columns. The only free geometry is the vector of band heights h (R) and column
widths w (C); every cell is h[r] x sum(w[c0:c1]). `_solve_grid` ties these to ONE proportional
(rank-1) fit; this oracle treats them as independent variables and decides, per witness, whether
ANY assignment satisfies the realizer's own per-cell checks (plus, optionally, the validators' own
aspect / net-area semantics), with three tools of increasing strength:

  1. `necessary_conditions`  — closed-form interval certificates (W and H bounds, area totals). A
                               violated one is a human-readable proof of infeasibility.
  2. `alternating_lp`        — fast existence search (fix h -> LP in w, fix w -> LP in h).
  3. `branch_and_bound`      — exact decision on the continuous model: spatial B&B over band
                               heights with McCormick relaxations of h*w (LP per node); INFEASIBLE
                               is a proof (every node pruned by an infeasible LP relaxation),
                               FEASIBLE returns a point, UNKNOWN when the node/time limit is hit.

Constraints modelled (metres; the realizer works in 5 cm units, so a continuous point is rounded
to units and re-verified by the real `_build_grid_wing` downstream — the continuous model is a
superset of the unit model, so INFEASIBLE here implies infeasible there):
  - cell area in [min_area - tol, max_area + tol]        (production: GROSS rect area vs the
    ZoneIntent bounds, exactly as `_build_grid_wing`; corrected: NET area, see `Semantics`)
  - both cell dimensions >= min_short_side + 0.3 m inset  (`_build_grid_wing` short-side check)
  - optional max aspect (validators C3/C20)               (`Semantics.aspect`)
  - sum(w) <= W_max, sum(h) <= H_max                       (brief footprint + 4 m, `ENVELOPE_TOO_LARGE`)
  - band tiling / non-overlap / full coverage are structural (every row tiles all columns).
NOT modelled (downstream checks): entrance resolution, door placement (C5/C24), windows/exposure
(C8/C19), circulation ratio (C26), furniture (C9/C30), wet-room rules (C17), safe-room RC (C4).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

INSET_MARGIN_M = 0.3   # rectilinear_realizer._INSET_MARGIN_M
AREA_TOL = 0.02        # `_build_grid_wing`: zi.min_area_m2 - 0.02 <= area <= zi.max_area_m2 + 0.02


@dataclass
class Semantics:
    area: str = "gross"          # "gross" (production `_build_grid_wing`) | "net" (validator C3 counterfactual)
    aspect: bool = False         # enforce max_aspect (validators C3/C20)
    net_inset_w: dict = field(default_factory=dict)   # cell zone -> total horizontal inset (m) under "net"
    net_inset_h: dict = field(default_factory=dict)   # cell zone -> total vertical inset (m) under "net"
    label: str = "production"


@dataclass
class Cell:
    zone: str
    r: int
    c0: int
    c1: int
    lo: float      # area lower bound incl. tolerance
    hi: float
    s: float       # minimum of BOTH dimensions (min_short + inset margin)
    amax: float
    bw: float = 0.0   # net inset (w) when semantics.area == "net"
    bh: float = 0.0


def build_cells(rows, n_cols, zones, sem: Semantics) -> list[Cell]:
    cells = []
    for r, row in enumerate(rows):
        c0 = 0
        for zid, span in row:
            z = zones[zid]
            # production: gross dims >= min_short + 0.3 (the realizer's conservative pre-check);
            # net (corrected): NET dims >= min_short exactly, with the real per-side insets
            s_dim = z["min_short"] + (INSET_MARGIN_M if sem.area != "net" else 0.0)
            cells.append(Cell(zid, r, c0, c0 + int(span),
                              z["min"] - (AREA_TOL if sem.area != "net" else 0.01),
                              z["max"] + (AREA_TOL if sem.area != "net" else 0.01),
                              s_dim, z["max_aspect"] if sem.aspect else 1e9,
                              sem.net_inset_w.get(zid, 0.0) if sem.area == "net" else 0.0,
                              sem.net_inset_h.get(zid, 0.0) if sem.area == "net" else 0.0))
            c0 += int(span)
        assert c0 == n_cols
    return cells


# ----------------------------------------------------------------------------- 1. certificates

def necessary_conditions(cells: list[Cell], R: int, C: int, w_max: float, h_max: float) -> dict:
    """Closed-form bounds every feasible (h, w) must satisfy. Returns the bounds and the first
    violated condition as a readable certificate (or None)."""
    rows = {r: [c for c in cells if c.r == r] for r in range(R)}
    # every cell: width >= s and height >= s; width <= hi/height <= hi/s ; height <= hi/width <= hi/s
    W_lo = max(sum(c.s + c.bw for c in rows[r]) for r in range(R))
    W_hi = min(min(sum((c.hi + 0.0) / (c.s + c.bh) + c.bw for c in rows[r]), w_max) for r in range(R))
    H_lo = sum(max(c.s + c.bh for c in rows[r]) for r in range(R))
    H_hi = min(sum(min(c.hi / (c.s + c.bw) + c.bh for c in rows[r]) for r in range(R)), h_max)
    A_lo = sum(c.lo for c in cells)
    A_hi = sum(c.hi for c in cells)
    cert = None
    if W_lo > W_hi + 1e-9:
        tight_lo = max(range(R), key=lambda r: sum(c.s + c.bw for c in rows[r]))
        tight_hi = min(range(R), key=lambda r: sum(c.hi / (c.s + c.bh) + c.bw for c in rows[r]))
        cert = (f"WIDTH: band {tight_lo} needs width >= {W_lo:.2f} m (sum of its cells' minimum "
                f"dimensions {[(c.zone, round(c.s, 2)) for c in rows[tight_lo]]}) but band {tight_hi} "
                f"allows at most {W_hi:.2f} m (each cell's max area / its minimum depth: "
                f"{[(c.zone, round(c.hi / (c.s + c.bh), 2)) for c in rows[tight_hi]]}"
                + (f"; footprint cap {w_max} m" if w_max < W_hi + 1e-9 else "") + ")")
    elif H_lo > H_hi + 1e-9:
        cert = (f"HEIGHT: bands need total depth >= {H_lo:.2f} m but can be at most {H_hi:.2f} m "
                f"(per band: min of max area / min width over its cells; footprint cap {h_max} m)")
    elif A_lo > W_hi * H_hi + 1e-9:
        cert = f"AREA: cells need >= {A_lo:.1f} m2 but W*H <= {W_hi:.2f}*{H_hi:.2f} = {W_hi * H_hi:.1f} m2"
    elif A_hi < W_lo * H_lo - 1e-9:
        cert = f"AREA: cells allow <= {A_hi:.1f} m2 but W*H >= {W_lo:.2f}*{H_lo:.2f} = {W_lo * H_lo:.1f} m2"
    return {"W_lo": round(W_lo, 2), "W_hi": round(W_hi, 2), "H_lo": round(H_lo, 2), "H_hi": round(H_hi, 2),
            "A_lo": round(A_lo, 1), "A_hi": round(A_hi, 1), "certificate": cert}


# ----------------------------------------------------------------------------- 2. alternating LP

def _lp_w(h, cells, C, w_max):
    A = []; b = []
    for c in cells:
        hr = h[c.r]
        hr_n = hr - c.bh
        row = np.zeros(C + 1); row[c.c0:c.c1] = -hr_n; row[C] = 1; A.append(row); b.append(-c.lo - hr_n * c.bw)
        row = np.zeros(C + 1); row[c.c0:c.c1] = hr_n; row[C] = 1; A.append(row); b.append(c.hi + hr_n * c.bw)
        row = np.zeros(C + 1); row[c.c0:c.c1] = -1; row[C] = 1; A.append(row); b.append(-(c.s + c.bw))
        if c.amax < 1e8:
            row = np.zeros(C + 1); row[c.c0:c.c1] = 1; row[C] = 1; A.append(row); b.append(c.amax * hr_n + c.bw)
            row = np.zeros(C + 1); row[c.c0:c.c1] = -c.amax; row[C] = 1; A.append(row); b.append(-hr_n - c.amax * c.bw)
        if hr < c.s + c.bh:
            row = np.zeros(C + 1); row[C] = 1; A.append(row); b.append(hr - c.s - c.bh)
    row = np.zeros(C + 1); row[:C] = 1; A.append(row); b.append(w_max)
    obj = np.zeros(C + 1); obj[C] = -1
    res = linprog(obj, A_ub=np.array(A), b_ub=np.array(b), bounds=[(0.05, None)] * C + [(-50, 50)], method="highs")
    return (res.x[:C], res.x[C]) if res.success else (None, -1e9)


def _lp_h(w, cells, R, h_max):
    A = []; b = []
    for c in cells:
        width = float(np.sum(w[c.c0:c.c1])); wn = width - c.bw
        row = np.zeros(R + 1); row[c.r] = -wn; row[R] = 1; A.append(row); b.append(-c.lo - wn * c.bh)
        row = np.zeros(R + 1); row[c.r] = wn; row[R] = 1; A.append(row); b.append(c.hi + wn * c.bh)
        row = np.zeros(R + 1); row[c.r] = -1; row[R] = 1; A.append(row); b.append(-(c.s + c.bh))
        if c.amax < 1e8:
            row = np.zeros(R + 1); row[c.r] = 1; row[R] = 1; A.append(row); b.append(c.amax * wn + c.bh)
            row = np.zeros(R + 1); row[c.r] = -c.amax; row[R] = 1; A.append(row); b.append(-wn - c.amax * c.bh)
        if width < c.s + c.bw:
            row = np.zeros(R + 1); row[R] = 1; A.append(row); b.append(width - c.s - c.bw)
    row = np.zeros(R + 1); row[:R] = 1; A.append(row); b.append(h_max)
    obj = np.zeros(R + 1); obj[R] = -1
    res = linprog(obj, A_ub=np.array(A), b_ub=np.array(b), bounds=[(0.05, None)] * R + [(-50, 50)], method="highs")
    return (res.x[:R], res.x[R]) if res.success else (None, -1e9)


def check_point(h, w, cells, w_max, h_max, sem: Semantics, eps=1e-6) -> list[str]:
    """Direct verification of a (h, w) point against every modelled constraint."""
    viol = []
    if sum(w) > w_max + eps: viol.append(f"W {sum(w):.2f} > {w_max}")
    if sum(h) > h_max + eps: viol.append(f"H {sum(h):.2f} > {h_max}")
    for c in cells:
        width = sum(w[c.c0:c.c1]); height = h[c.r]
        wn, hn = width - c.bw, height - c.bh
        area = wn * hn
        if area < c.lo - eps or area > c.hi + eps: viol.append(f"{c.zone} area {area:.2f} not in [{c.lo:.2f},{c.hi:.2f}]")
        if min(width, height) < c.s - eps: viol.append(f"{c.zone} short {min(width, height):.2f} < {c.s:.2f}")
        if sem.aspect and max(wn, hn) > c.amax * min(wn, hn) + eps: viol.append(f"{c.zone} aspect {max(wn, hn) / max(min(wn, hn), 1e-9):.2f} > {c.amax}")
    return viol


def alternating_lp(cells, R, C, w_max, h_max, sem: Semantics, starts=12, iters=10, seed=0):
    rng = np.random.default_rng(seed)
    for k in range(starts):
        h = np.array([max(c.s + c.bh for c in cells if c.r == r) + (0.5 if k == 0 else rng.uniform(0.0, 3.0)) for r in range(R)])
        for _ in range(iters):
            w, t = _lp_w(h, cells, C, w_max)
            if w is None: break
            h2, t2 = _lp_h(w, cells, R, h_max)
            if h2 is None: break
            h = h2
            if t2 >= -1e-9 and not check_point(h, w, cells, w_max, h_max, sem):
                return list(map(float, h)), list(map(float, w))
    return None


# ----------------------------------------------------------------------------- 3. exact B&B

def _node_lp(cells, R, C, hL, hU, wL, wU, w_max, h_max):
    """McCormick relaxation of a_rc = h_r * w_c within the box. Variables [h(R), w(C), a(R*C)].
    Returns (feasible, x)."""
    n = R + C + R * C
    ai = lambda r, c: R + C + r * C + c  # noqa: E731
    A = []; b = []
    def add(coefs, rhs):
        row = np.zeros(n)
        for i, v in coefs: row[i] += v
        A.append(row); b.append(rhs)
    for r in range(R):
        for c in range(C):
            # a >= hL w + h wL - hL wL ; a >= hU w + h wU - hU wU ; a <= hU w + h wL - hU wL ; a <= hL w + h wU - hL wU
            add([(ai(r, c), -1), (R + c, hL[r]), (r, wL[c])], hL[r] * wL[c])
            add([(ai(r, c), -1), (R + c, hU[r]), (r, wU[c])], hU[r] * wU[c])
            add([(ai(r, c), 1), (R + c, -hU[r]), (r, -wL[c])], -hU[r] * wL[c])
            add([(ai(r, c), 1), (R + c, -hL[r]), (r, -wU[c])], -hL[r] * wU[c])
    for cl in cells:
        cols = range(cl.c0, cl.c1)
        # net area = sum a - bw*h - bh*sum(w) + bw*bh  in [lo, hi]
        const = cl.bw * cl.bh
        add([(ai(cl.r, c), -1) for c in cols] + [(cl.r, cl.bw)] + [(R + c, cl.bh) for c in cols], -cl.lo + const)
        add([(ai(cl.r, c), 1) for c in cols] + [(cl.r, -cl.bw)] + [(R + c, -cl.bh) for c in cols], cl.hi - const)
        add([(R + c, -1) for c in cols], -(cl.s + cl.bw))
        add([(cl.r, -1)], -(cl.s + cl.bh))
        if cl.amax < 1e8:
            # (sum w - bw) <= amax (h - bh)  ;  (h - bh) <= amax (sum w - bw)
            add([(R + c, 1) for c in cols] + [(cl.r, -cl.amax)], cl.bw - cl.amax * cl.bh)
            add([(cl.r, 1)] + [(R + c, -cl.amax) for c in cols], cl.bh - cl.amax * cl.bw)
    add([(R + c, 1) for c in range(C)], w_max)
    add([(r, 1) for r in range(R)], h_max)
    bounds = [(hL[r], hU[r]) for r in range(R)] + [(wL[c], wU[c]) for c in range(C)] + [(None, None)] * (R * C)
    res = linprog(np.zeros(n), A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    return res.success, (res.x if res.success else None)


def branch_and_bound(cells, R, C, w_max, h_max, sem: Semantics, node_limit=4000, time_limit=60.0):
    """Exact decision of the continuous model. Returns dict(status, h, w, nodes, seconds)."""
    t0 = time.time()
    hL0 = np.array([max(c.s + c.bh for c in cells if c.r == r) for r in range(R)])
    hU0 = np.array([h_max - (hL0.sum() - hL0[r]) for r in range(R)])
    wL0 = np.zeros(C) + 0.05
    for c in cells:
        if c.c1 - c.c0 == 1:
            wL0[c.c0] = max(wL0[c.c0], c.s + c.bw)
    wU0 = np.array([w_max - (wL0.sum() - wL0[c]) for c in range(C)])
    if np.any(hU0 < hL0) or np.any(wU0 < wL0):
        return {"status": "INFEASIBLE", "nodes": 0, "seconds": 0.0, "why": "box empty (minimum dimensions exceed the footprint)"}
    stack = [(hL0, hU0)]
    nodes = 0
    while stack:
        if nodes >= node_limit or time.time() - t0 > time_limit:
            return {"status": "UNKNOWN", "nodes": nodes, "seconds": round(time.time() - t0, 2)}
        hL, hU = stack.pop()
        nodes += 1
        ok, x = _node_lp(cells, R, C, hL, hU, wL0, wU0, w_max, h_max)
        if not ok:
            continue
        h = x[:R]; w = x[R:R + C]; a = x[R + C:].reshape(R, C)
        gap = np.abs(a - np.outer(h, w))
        if not check_point(h, w, cells, w_max, h_max, sem):
            return {"status": "FEASIBLE", "h": list(map(float, h)), "w": list(map(float, w)), "nodes": nodes, "seconds": round(time.time() - t0, 2)}
        # polish: fix h from the LP point, LP in w, then LP in h
        w2, t = _lp_w(h, cells, C, w_max)
        if w2 is not None:
            h2, t2 = _lp_h(w2, cells, R, h_max)
            if h2 is not None and not check_point(h2, w2, cells, w_max, h_max, sem):
                return {"status": "FEASIBLE", "h": list(map(float, h2)), "w": list(map(float, w2)), "nodes": nodes, "seconds": round(time.time() - t0, 2)}
        r = int(np.argmax(gap.sum(axis=1)))
        if hU[r] - hL[r] < 0.0125:   # a quarter unit: the box is effectively a point
            continue
        mid = float(np.clip(h[r], hL[r] + 0.25 * (hU[r] - hL[r]), hU[r] - 0.25 * (hU[r] - hL[r])))
        a1 = hU.copy(); a1[r] = mid
        b1 = hL.copy(); b1[r] = mid
        stack.append((hL, a1)); stack.append((b1, hU))
    return {"status": "INFEASIBLE", "nodes": nodes, "seconds": round(time.time() - t0, 2), "why": "every node's McCormick relaxation infeasible or exhausted"}


def decide(rows, n_cols, zones, w_max, h_max, sem: Semantics, node_limit=4000, time_limit=60.0) -> dict:
    """Full oracle: certificates -> alternating LP -> exact B&B."""
    cells = build_cells(rows, n_cols, zones, sem)
    R = len(rows); C = n_cols
    nc = necessary_conditions(cells, R, C, w_max, h_max)
    if nc["certificate"]:
        return {"status": "INFEASIBLE", "method": "certificate", "certificate": nc["certificate"], "bounds": nc}
    pt = alternating_lp(cells, R, C, w_max, h_max, sem)
    if pt:
        return {"status": "FEASIBLE", "method": "alternating_lp", "h": pt[0], "w": pt[1], "bounds": nc}
    bb = branch_and_bound(cells, R, C, w_max, h_max, sem, node_limit, time_limit)
    bb["method"] = "branch_and_bound"; bb["bounds"] = nc
    return bb


def to_units(vals_m, total_u=None):
    """Round metres to 5 cm units (>= 1); optionally force the exact total the realizer expects."""
    us = [max(1, int(round(v / 0.05))) for v in vals_m]
    if total_u is not None:
        us[int(np.argmax(us))] += total_u - sum(us)
    return us
