import json, sys, time
from topo_lib import *
G = json.load(open('selected_graphs.json'))
briefs = sys.argv[1].split(',') if len(sys.argv) > 1 else ['B10','B13','B15','B16']
res = {}
for bid in briefs:
    g = G[bid]; nodes = [r['id'] for r in g['rooms']]; edges = [tuple(e) for e in g['spatial_adjacency']]
    print(f"== {bid} n={len(nodes)} m={len(edges)}", flush=True)
    d = diagnostics(nodes, edges)
    print("   planar", d['planar'], "K4", d['k4'], "lens3", d['lens3'], "maxdeg", d['max_degree'], flush=True)
    t=time.time(); l0 = l0_exact(nodes, edges)
    print("   L0 exact per n_rows:", {k: v['embeddable'] for k, v in l0.items()}, f"({time.time()-t:.1f}s)", flush=True)
    lv = minimal_level(nodes, edges, verbose=True)
    # band in the other orientation only matters if band_y failed (rotation symmetric) - record anyway
    res[bid] = {'diag': d, 'l0': {str(k): {kk: (list(vv) if isinstance(vv, tuple) else vv) for kk, vv in v.items()} for k, v in l0.items()}, 'levels': lv}
    json.dump(res, open(f'levels_{"_".join(briefs)}.json','w'), indent=1, default=str)
print("done")
