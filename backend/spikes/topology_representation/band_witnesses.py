"""#142C stage 1 — EXACT band embedding (isolated; needs `python-sat`, NOT a project dependency).

For every frozen brief: classify the required spatial-adjacency graph exactly, and for every
band-representable graph enumerate distinct band layouts (the `GridWing` dataclass's own family:
horizontal bands, every room spanning its band's full height, globally aligned column boundaries)
that carry EVERY required edge — each one a complete `GridWing` witness (rows of (zone_id, col_span),
n_cols). Nothing partial is ever emitted: a brief is either BAND_REPRESENTABLE with >= 1 witness, or
UNSAT with its proven class.

Classes (exact, see `topo_lib.py` / docs/reports/142b-minimum-topological-representation):
  NON_PLANAR               — no partition of the plane has a non-planar contact graph
  RECTANGULAR_OBSTRUCTION  — K4 or an edge with >= 3 common neighbours (separating triangle in every
                             planar embedding): no dissection into rectangles carries the graph
  BAND_UNSAT               — planar, no obstruction, but SAT proves no band layout exists
  BAND_REPRESENTABLE       — >= 1 exact witness

Witness ranking is a generic, brief-independent plausibility score mirroring `_solve_grid`'s own
rank-1 proportional fit (row height ∝ row target total, column width ∝ column target total): the
relative violation of each cell's own [min, max] area and minimum short side under that fit at
scale 1. It only ORDERS witnesses; the downstream experiment tries them in that order and never
alters a witness.

Usage (isolated venv):  python band_witnesses.py <briefs_142c.json> <out witnesses.json> [K] [seconds] [B06,B07,...]
"""
from __future__ import annotations

import json
import sys
import time

from pysat.solvers import Cadical153

from topo_lib import Piece, TilingModel, compress, contacts_from_rects, diagnostics, grid_shapes

INSET_MARGIN_M = 0.3   # rectilinear_realizer._INSET_MARGIN_M (gross = net + inset)


def rows_from_rects(rects: dict) -> tuple[list[list[list]], int]:
    W = max(r[1] for r in rects.values())
    bands = sorted(set((r[2], r[3]) for r in rects.values()))
    rows = []
    for b in bands:
        cells = sorted((r[0], pid, r[1] - r[0]) for pid, r in rects.items() if (r[2], r[3]) == b)
        assert sum(c[2] for c in cells) == W and cells[0][0] == 0
        rows.append([[pid, span] for _x, pid, span in cells])
    return rows, W


def plausibility(rows, n_cols, zones) -> float:
    """Rank-1 proportional fit at scale 1 (envelope area == total target): sum of relative
    violations of per-cell [min,max] area and min short side (+inset). 0.0 == every cell fits."""
    T = sum(z["target"] for z in zones.values())
    row_tot = [sum(zones[c[0]]["target"] for c in row) for row in rows]
    col_tot = [0.0] * n_cols
    for row in rows:
        c0 = 0
        for zid, span in row:
            for c in range(c0, c0 + span):
                col_tot[c] += zones[zid]["target"] / span
            c0 += span
    # square envelope of area T: H = W = sqrt(T); row heights / column widths proportional
    side = T ** 0.5
    h = [side * rt / T for rt in row_tot]
    w = [side * ct / T for ct in col_tot]
    score = 0.0
    for r_idx, row in enumerate(rows):
        c0 = 0
        for zid, span in row:
            z = zones[zid]
            width = sum(w[c0:c0 + span]); height = h[r_idx]
            area = width * height
            if area < z["min"]:
                score += (z["min"] - area) / z["target"]
            elif area > z["max"]:
                score += (area - z["max"]) / z["target"]
            short = min(width, height)
            need = z["min_short"] + INSET_MARGIN_M
            if short < need:
                score += (need - short) / need
            c0 += span
    return round(score, 4)


def enumerate_band_witnesses(nodes, edges, K: int, seconds: float, per_grid_cap: int | None = None):
    """Distinct compressed band layouts carrying every edge, over every grid W+H = n+1 — round-robin
    across grids (per-grid cap = max(10, K // #grids)) so no single grid shape (hence no single band
    count) dominates the witness set; total capped at K unique layouts / `seconds`."""
    seen = set(); out = []; t0 = time.time(); models = 0; per_grid = {}
    shapes = grid_shapes(len(nodes), symmetric=False)
    cap_per_grid = per_grid_cap or max(10, K // len(shapes))
    for W, H in shapes:
        tm = TilingModel([Piece(v, v) for v in nodes], W, H)
        for u, v in edges:
            tm.require_room_contact(u, v)
        tm.require_band_layout("y")
        s = Cadical153(bootstrap_with=tm.clauses)
        got_here = 0
        while got_here < cap_per_grid and len(out) < K and time.time() - t0 <= seconds:
            if not s.solve():
                break
            models += 1
            pos = set(l for l in s.get_model() if l > 0)
            rects = {}
            lits = []
            for k, pc in enumerate(tm.pieces):
                xs = [i for i in range(W) if tm.colcov[k][i] in pos]
                ys = [j for j in range(H) if tm.rowcov[k][j] in pos]
                rects[pc.pid] = (min(xs), max(xs) + 1, min(ys), max(ys) + 1)
                lits += [tm.cov[k][i][j] for i in range(W) for j in range(H) if tm.cov[k][i][j] in pos]
            comp = compress(rects)
            got = contacts_from_rects(comp)
            assert all(frozenset(e) in got for e in edges)
            key = json.dumps(comp, sort_keys=True)
            if key not in seen:
                seen.add(key); out.append(comp); got_here += 1
            s.add_clause([-l for l in lits])
        s.delete()
        per_grid[f"{W}x{H}"] = got_here
        if len(out) >= K or time.time() - t0 > seconds:
            break
    return out, {"grids_tried": len(per_grid), "per_grid_unique": per_grid, "models": models,
                 "unique": len(out), "seconds": round(time.time() - t0, 1),
                 "capped": len(out) >= K or time.time() - t0 > seconds,
                 "complete": (len(out) < K and time.time() - t0 <= seconds and all(v < cap_per_grid for v in per_grid.values()))}


def main(argv):
    briefs = json.load(open(argv[1]))
    K = int(argv[3]) if len(argv) > 3 else 150
    seconds = float(argv[4]) if len(argv) > 4 else 120.0
    only = set(argv[5].split(",")) if len(argv) > 5 and argv[5] != "-" else None
    per_grid_cap = int(argv[6]) if len(argv) > 6 else None
    out = {"dataset_sha256": briefs["dataset_sha256"], "K": K, "seconds_cap": seconds, "briefs": {}}
    for bid, b in briefs["briefs"].items():
        if only and bid not in only:
            continue
        nodes = [r["id"] for r in b["rooms"]]; edges = [tuple(e) for e in b["spatial_adjacency"]]
        d = diagnostics(nodes, edges)
        rec = {"n": len(nodes), "m": len(edges), "edges": edges, "planar": d["planar"],
               "k4": d["k4"], "lens3": d["lens3"], "max_degree": d["max_degree"], "witnesses": []}
        if not d["planar"]:
            rec["classification"] = "NON_PLANAR"
            rec["reason"] = "non-planar graph: no partition of the plane has a non-planar contact graph"
        elif d["k4"] or d["lens3"]:
            rec["classification"] = "RECTANGULAR_OBSTRUCTION"
            rec["reason"] = ("K4 " + ", ".join("/".join(c) for c in d["k4"]) if d["k4"] else "") + \
                            (("; " if d["k4"] and d["lens3"] else "") +
                             ("; ".join(f"edge {a}-{b} with common neighbours {'/'.join(c)}" for (a, b), c in d["lens3"]) if d["lens3"] else ""))
        else:
            wits, stats = enumerate_band_witnesses(nodes, edges, K, seconds, per_grid_cap)
            rec["enumeration"] = stats
            if not wits:
                rec["classification"] = "BAND_UNSAT"
                rec["reason"] = "planar, no K4/triple-lens, but no band layout carries every edge (SAT UNSAT over every grid W+H=n+1)"
            else:
                rec["classification"] = "BAND_REPRESENTABLE"
                ws = []
                for comp in wits:
                    rows, n_cols = rows_from_rects(comp)
                    ws.append({"rows": rows, "n_cols": n_cols, "score": plausibility(rows, n_cols, b["zones"])})
                ws.sort(key=lambda w: (w["score"], len(w["rows"]), w["n_cols"]))
                rec["witnesses"] = ws
        out["briefs"][bid] = rec
        print(bid, rec["classification"], f"n={rec['n']} m={rec['m']}",
              (f"witnesses={len(rec['witnesses'])} best_score={rec['witnesses'][0]['score']} {rec.get('enumeration')}" if rec["witnesses"] else rec.get("reason", "")), flush=True)
    json.dump(out, open(argv[2], "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv)
