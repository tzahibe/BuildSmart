import json, sys, time
from topo_lib import *
G = json.load(open('selected_graphs.json'))
out = {}
for bid in ['B10','B15','B16','B13']:
    g = G[bid]; nodes = [r['id'] for r in g['rooms']]; edges = [tuple(e) for e in g['spatial_adjacency']]
    print('==', bid, flush=True); o = {}
    for fam in ('band_y','slicing','rect'):
        t=time.time(); k, kept, rects = max_edges_family(nodes, edges, fam, lo=len(edges)-6)
        o[f'max_{fam}'] = {'k': k, 'kept': kept, 'rects': rects}
        print(f'   max edges carried by {fam}: {k}/{len(edges)} ({time.time()-t:.1f}s)', flush=True)
    d = diagnostics(nodes, edges)
    if d['k4'] or d['lens3']:
        obs = set()
        for k4 in d['k4']: obs |= set(k4)
        for (a,b), c in d['lens3']: obs |= {a,b,*c}
        o['band_plus_L'] = {}
        for r in sorted(obs):
            ok, rects, dt = solve_family(nodes, edges, 'band_y', l_rooms=(r,))
            o['band_plus_L'][r] = {'ok': ok, 'rects': rects}
            print(f'   band + L({r}): {ok} ({dt:.1f}s)', flush=True)
        o['slicing_plus_L'] = {}
        for r in sorted(obs):
            ok, rects, dt = solve_family(nodes, edges, 'slicing', l_rooms=(r,))
            o['slicing_plus_L'][r] = {'ok': ok, 'rects': rects}
            print(f'   slicing + L({r}): {ok} ({dt:.1f}s)', flush=True)
    # per-edge deletion analysis: which single edge removal makes the graph rectangular / band
    o['edge_deletion'] = {}
    for e in edges:
        rest = [x for x in edges if x != e]
        dd = diagnostics(nodes, rest)
        rect_ok = not (dd['k4'] or dd['lens3'])
        if rect_ok:
            r_ok,_,_ = solve_family(nodes, rest, 'rect', conf_budget=300000)
            rect_ok = r_ok
        b_ok = None
        if rect_ok:
            b_ok,_,_ = solve_family(nodes, rest, 'band_y', conf_budget=300000)
        o['edge_deletion'][f'{e[0]}--{e[1]}'] = {'rect_without_it': rect_ok, 'band_without_it': b_ok}
    print('   edges whose removal alone makes it rectangular:', [k for k,v in o['edge_deletion'].items() if v['rect_without_it']], flush=True)
    print('   edges whose removal alone makes it band/GridWing:', [k for k,v in o['edge_deletion'].items() if v['band_without_it']], flush=True)
    out[bid] = o
    json.dump(out, open('extra.json','w'), indent=1, default=str)
print('done')
