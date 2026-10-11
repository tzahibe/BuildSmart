"""Enumerate distinct band layouts carrying B01's 6 edges; try to DIMENSION each with the existing GridWing solver."""
import json, sys, os, subprocess
sys.path.insert(0, '.')
from topo_lib import *
G = json.load(open('selected_graphs.json'))['B01']
nodes=[r['id'] for r in G['rooms']]; edges=[tuple(e) for e in G['spatial_adjacency']]
layouts = []
seen = set()
for W,H in grid_shapes(len(nodes), symmetric=False):
    tm = TilingModel([Piece(v,v) for v in nodes], W, H)
    for u,v in edges: tm.require_room_contact(u,v)
    tm.require_band_layout('y')
    s = Cadical153(bootstrap_with=tm.clauses)
    for _ in range(400):
        if not s.solve(): break
        model = s.get_model(); pos=set(l for l in model if l>0)
        rects={}
        for k,pc in enumerate(tm.pieces):
            xs=[i for i in range(W) if tm.colcov[k][i] in pos]; ys=[j for j in range(H) if tm.rowcov[k][j] in pos]
            rects[pc.pid]=(min(xs),max(xs)+1,min(ys),max(ys)+1)
        key = json.dumps(compress(rects), sort_keys=True)
        if key not in seen: seen.add(key); layouts.append(compress(rects))
        # block this exact cover
        s.add_clause([-tm.cov[k][i][j] for k in range(len(tm.pieces)) for i in range(W) for j in range(H) if tm.cov[k][i][j] in pos])
    s.delete()
print('distinct band layouts for B01:', len(layouts))
json.dump(layouts, open('b01_band_layouts.json','w'))
