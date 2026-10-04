"""#142I — B06 exposure: can ANY rectangular dissection (not just a band layout) carry the required
adjacency with every REQUIRED-exposure room on the envelope? Exact SAT over the complete grid family
(topo_lib), with one added clause per REQUIRED room: it covers >= 1 border cell. Research venv only
(python-sat). Usage: PYTHONPATH=backend:backend/tests/vertical_slice python exposure_sat_142i.py B06"""
import json, sys, time
from topo_lib import Piece, TilingModel, grid_shapes, compress, contacts_from_rects
import os
FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tests", "fixtures", "frozen_briefs_142.json")
#: mirrors exposure_policy.REQUIRED_EXTERIOR_ROLES (the research venv cannot import the app: no shapely)
REQUIRED_EXTERIOR_ROLES = {"LIVING", "DINING", "KITCHEN", "FAMILY_ROOM", "BEDROOM", "MASTER_BEDROOM", "STUDY", "SAFE_ROOM", "LAUNDRY"}


def exposure_feasible(nodes, edges, exposed, family):
    """family: 'band' | 'rect'. Returns (ok, rects, seconds); ok None = budget."""
    pieces = [Piece(v, v) for v in nodes]; P = len(pieces); total = 0.0
    for W, H in grid_shapes(P, symmetric=(family == "rect")):
        tm = TilingModel(pieces, W, H)
        for u, v in edges:
            tm.require_room_contact(u, v)
        if family == "band":
            tm.require_band_layout("y")
        for r in exposed:
            p = tm.pid_index[r]
            border = [tm.cov[p][i][j] for i in range(W) for j in range(H) if i in (0, W - 1) or j in (0, H - 1)]
            tm.add(border)
        ok, rects, dt, _, _ = tm.solve(200_000)
        total += dt
        if ok is None:
            return None, None, total
        if ok:
            return True, compress(rects), total
    return False, None, total


def main(bid):
    fx = json.load(open(FIXTURE))["briefs"][bid]
    roles = {r["id"]: r["role"] for r in fx["rooms"]}
    nodes = list(roles); edges = [tuple(e) for e in fx["spatial_adjacency"]]
    exposed = [z for z in nodes if roles[z] in REQUIRED_EXTERIOR_ROLES]
    access = {frozenset((a, b)) for a, b in fx["access_graph"] if a != "ENTRANCE"}
    out = {"brief": bid, "required_exposure": exposed, "spatial_edges": len(edges)}
    for fam in ("band", "rect"):
        ok, rects, dt = exposure_feasible(nodes, edges, exposed, fam)
        out[f"{fam}_all_exposed"] = ok; out[f"{fam}_seconds"] = round(dt, 2); out[f"{fam}_witness"] = rects
        print(bid, fam, "all REQUIRED rooms exposed:", ok, f"{dt:.1f}s", rects, flush=True)
    # which single spatial edge, NOT backed by an access edge, unblocks exposure (band family)?
    fixes = []
    for e in edges:
        if frozenset(e) in access:
            continue
        rest = [x for x in edges if x != e]
        ok, rects, dt = exposure_feasible(nodes, rest, exposed, "band")
        fixes.append({"dropped": e, "band_all_exposed": ok, "seconds": round(dt, 2)})
        print("  drop", e, "->", ok, f"{dt:.1f}s", flush=True)
    out["single_unbacked_edge_removals"] = fixes
    json.dump(out, open(sys.argv[2], "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1])
