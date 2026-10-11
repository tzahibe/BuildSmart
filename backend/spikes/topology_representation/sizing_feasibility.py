"""#142C failure attribution — is a witness that `_solve_grid` cannot size DIMENSIONALLY feasible at all?

For every band witness the experiment tried, search for ANY row-height / column-width vector that
satisfies exactly the checks `_build_grid_wing` applies (gross cell area within the zone's own
[min_area, max_area]; cell short side >= min_short_side + 0.3 m inset; wing inside the brief
footprint + 4 m) — with the rank-1 proportionality assumption of `_solve_grid` REMOVED. The search is
an alternating LP (fix heights -> LP in widths maximizing the minimum slack; fix widths -> LP in
heights), from the rank-1 point and random starts. It is an existence search, not a proof of
infeasibility: FOUND == a sizing exists (so the blocker is the solver); NOT_FOUND == none found by
this search (reported as such, never as "proven infeasible").

Also reports, per witness, the structural reason the rank-1 fit cannot work when one is evident:
a single-cell band (a room spanning the full wing width — the hub-as-band pattern) whose own max
area caps the wing width at max_area / (min_short + inset).

Runs in the dev venv (scipy is already present as a transitive dependency); isolated under spikes/.
Usage: python sizing_feasibility.py <briefs_142c.json> <witnesses.json> <results.json> <out.json> [max_witnesses]
"""
from __future__ import annotations

import json
import random
import sys
import time

import numpy as np
from scipy.optimize import linprog

INSET = 0.3


def cells_of(rows):
    out = []
    for r_idx, row in enumerate(rows):
        c0 = 0
        for zid, span in row:
            out.append((zid, r_idx, c0, c0 + int(span)))
            c0 += int(span)
    return out


def lp_widths(h, cells, zones, n_cols, w_max, aspect=False):
    """Fix row heights h; variables: w_0..w_{C-1}, t. maximize t."""
    C = n_cols
    A = []; b = []
    for zid, r, c0, c1 in cells:
        z = zones[zid]; hr = h[r]
        if aspect:
            a = z["max_aspect"]
            row = np.zeros(C + 1); row[c0:c1] = 1; row[C] = 1; A.append(row); b.append(a * hr)        # sum(w) <= a*h
            row = np.zeros(C + 1); row[c0:c1] = -a; row[C] = 1; A.append(row); b.append(-hr)          # h <= a*sum(w)
        row = np.zeros(C + 1); row[c0:c1] = -hr; row[C] = 1        # -hr*sum(w) + t <= -min
        A.append(row); b.append(-z["min"])
        row = np.zeros(C + 1); row[c0:c1] = hr; row[C] = 1          # hr*sum(w) + t <= max
        A.append(row); b.append(z["max"])
        s = z["min_short"] + INSET
        row = np.zeros(C + 1); row[c0:c1] = -1; row[C] = 1           # -sum(w) + t <= -s
        A.append(row); b.append(-s)
        if hr < s:                                                     # this h is infeasible for the cell
            row = np.zeros(C + 1); row[C] = 1; A.append(row); b.append(hr - s)
    row = np.zeros(C + 1); row[:C] = 1; A.append(row); b.append(w_max)
    c = np.zeros(C + 1); c[C] = -1
    bounds = [(0.5, None)] * C + [(-50, 50)]
    res = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    if not res.success:
        return None, -1e9
    return res.x[:C], res.x[C]


def lp_heights(w, cells, zones, n_rows, h_max, aspect=False):
    R = n_rows
    A = []; b = []
    for zid, r, c0, c1 in cells:
        z = zones[zid]; width = float(np.sum(w[c0:c1]))
        if aspect:
            a = z["max_aspect"]
            row = np.zeros(R + 1); row[r] = 1; row[R] = 1; A.append(row); b.append(a * width)
            row = np.zeros(R + 1); row[r] = -a; row[R] = 1; A.append(row); b.append(-width)
        row = np.zeros(R + 1); row[r] = -width; row[R] = 1
        A.append(row); b.append(-z["min"])
        row = np.zeros(R + 1); row[r] = width; row[R] = 1
        A.append(row); b.append(z["max"])
        s = z["min_short"] + INSET
        row = np.zeros(R + 1); row[r] = -1; row[R] = 1
        A.append(row); b.append(-s)
        if width < s:
            row = np.zeros(R + 1); row[R] = 1; A.append(row); b.append(width - s)
    row = np.zeros(R + 1); row[:R] = 1; A.append(row); b.append(h_max)
    c = np.zeros(R + 1); c[R] = -1
    bounds = [(0.5, None)] * R + [(-50, 50)]
    res = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    if not res.success:
        return None, -1e9
    return res.x[:R], res.x[R]


def rank1_start(rows, n_cols, zones):
    T = sum(z["target"] for z in zones.values())
    row_tot = [sum(zones[c[0]]["target"] for c in row) for row in rows]
    col_tot = [0.0] * n_cols
    for row in rows:
        c0 = 0
        for zid, span in row:
            for c in range(c0, c0 + int(span)):
                col_tot[c] += zones[zid]["target"] / int(span)
            c0 += int(span)
    side = T ** 0.5
    return np.array([side * rt / T for rt in row_tot]), np.array([side * ct / T for ct in col_tot])


def feasible_sizing(rows, n_cols, zones, w_max, h_max, starts=10, iters=8, seed=0, aspect=False):
    cells = cells_of(rows); R = len(rows)
    rng = random.Random(seed)
    best = (-1e9, None, None)
    h0, _ = rank1_start(rows, n_cols, zones)
    for k in range(starts):
        h = h0.copy() if k == 0 else np.array([rng.uniform(1.5, 6.0) for _ in range(R)])
        t = -1e9
        for _ in range(iters):
            w, t = lp_widths(h, cells, zones, n_cols, w_max, aspect)
            if w is None:
                break
            h2, t2 = lp_heights(w, cells, zones, R, h_max, aspect)
            if h2 is None:
                break
            h, t = h2, t2
            if t >= 0:
                return True, [round(float(x), 2) for x in h], [round(float(x), 2) for x in w], round(float(t), 3)
        if t > best[0]:
            best = (t, h, None)
    return False, None, None, round(float(best[0]), 3) if best[0] > -1e8 else None


def hub_band_cap(rows, n_cols, zones):
    """Single-cell bands: the room spans the full width; its max area / (min_short+inset) caps the
    wing width. Returns the tightest such cap (room, cap_m) or None."""
    caps = []
    for row in rows:
        if len(row) == 1:
            z = zones[row[0][0]]
            caps.append((row[0][0], round(z["max"] / (z["min_short"] + INSET), 2)))
    return min(caps, key=lambda c: c[1]) if caps else None


def main(argv):
    briefs = json.load(open(argv[1]))["briefs"]
    wit = json.load(open(argv[2]))["briefs"]
    results = {r["brief_id"]: r for r in json.load(open(argv[3]))} if argv[3] != "-" else {}
    maxw = int(argv[5]) if len(argv) > 5 else 100
    out = {}
    for bid, w in wit.items():
        if w["classification"] != "BAND_REPRESENTABLE":
            continue
        b = briefs[bid]; zones = b["zones"]
        fw, fd = b["footprint_m"]; w_max, h_max = fw + 4.0, fd + 4.0
        t0 = time.time(); recs = []
        for i, wt in enumerate(w["witnesses"][:maxw]):
            rows = [[(z, int(s)) for z, s in row] for row in wt["rows"]]
            ok, h, wv, slack = feasible_sizing(rows, wt["n_cols"], zones, w_max, h_max)
            ok_a, h_a, w_a, slack_a = feasible_sizing(rows, wt["n_cols"], zones, w_max, h_max, aspect=True) if ok else (False, None, None, None)
            cap = hub_band_cap(rows, wt["n_cols"], zones)
            exp = results[bid]["witness_results"][i] if bid in results and i < len(results[bid]["witness_results"]) else None
            recs.append({"index": i, "feasible_sizing_found": ok, "row_heights_m": h, "col_widths_m": wv,
                         "best_slack": slack, "feasible_with_validator_aspect": ok_a, "row_heights_aspect_m": h_a, "col_widths_aspect_m": w_a, "hub_band_width_cap": cap, "n_rows": len(rows), "n_cols": wt["n_cols"],
                         "rank1_best_stage": exp["best_stage_reached"] if exp else None})
        n_ok = sum(1 for r in recs if r["feasible_sizing_found"])
        n_ok_a = sum(1 for r in recs if r["feasible_with_validator_aspect"])
        n_rank1_sized = sum(1 for r in recs if r["rank1_best_stage"] in ("SIZING", "REALIZATION", "VALIDATORS"))
        caps = [r["hub_band_width_cap"] for r in recs if r["hub_band_width_cap"]]
        out[bid] = {"witnesses_checked": len(recs), "feasible_sizing_found": n_ok, "feasible_with_validator_aspect": n_ok_a,
                    "rank1_solver_sized": n_rank1_sized, "footprint_plus4": [w_max, h_max],
                    "witnesses_with_single_cell_band": len(caps),
                    "single_cell_band_width_caps_m": sorted(set(caps))[:6] if caps else [],
                    "records": recs, "seconds": round(time.time() - t0, 1)}
        print(f"{bid}: {n_ok}/{len(recs)} witnesses have a feasible sizing under the realizer's own checks, {n_ok_a} also under the validators' max-aspect (alternating LP); rank-1 `_solve_grid` sized "
              f"{n_rank1_sized}/{len(recs)}; single-cell bands in {len(caps)} witnesses, width caps {sorted(set(caps))[:4]}; "
              f"{out[bid]['seconds']}s", flush=True)
    json.dump(out, open(argv[4], "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv)
