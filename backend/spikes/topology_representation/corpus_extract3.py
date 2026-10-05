"""ResPlan geometric spatial-touching graphs, v3: duplicate node geometries dropped (ResPlan quirk: 4,852/17,107 plans
repeat one polygon under several node ids), no hall reconstruction ('inner' == union of rooms, there is no corridor polygon)."""
import pickle, json, math, sys, time
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
plans = pickle.load(open('/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl','rb'))
out = []; t0=time.time()
def pieces(mp):
    if mp is None or mp.is_empty: return []
    if isinstance(mp, MultiPolygon): return [p for p in mp.geoms if p.area > 0]
    return [mp] if mp.area > 0 else []
for k, p in enumerate(plans):
    G = p['graph']
    rooms = []
    for nd, d in G.nodes(data=True):
        if d['type'] == 'front_door': continue
        geom = d['geometry']
        if geom is None or geom.is_empty: continue
        if isinstance(geom, MultiPolygon): geom = max(geom.geoms, key=lambda g: g.area)
        if any(geom.equals(r[2]) for r in rooms): continue   # duplicate node geometry
        rooms.append((nd, d['type'], geom))
    for i, poly in enumerate(pieces(p.get('storage'))):
        rooms.append((f'storage_{i}', 'storage', poly))
    indoor_area = sum(r[2].area for r in rooms if r[1] != 'balcony')
    net = float(p.get('net_area') or 0) or float(p.get('area') or 0)
    if indoor_area <= 0 or net <= 0: continue
    inner = p.get('inner')
    if inner is None or inner.is_empty: continue
    s0 = math.sqrt(net / inner.area)        # metres per unit, from the interior shell
    wd_u = float(p.get('wall_depth') or 0)
    occupied = unary_union([r[2] for r in rooms] + pieces(p.get('wall')))
    try:
        free = inner.difference(occupied.buffer(wd_u*0.5, join_style=2))
    except Exception:
        continue
    halls = []
    s = s0
    buf = (wd_u * 0.5 + 0.05 / s)
    edges = []
    bufs = [r[2].buffer(buf, join_style=2) for r in rooms]
    for i in range(len(rooms)):
        for j in range(i+1, len(rooms)):
            inter = bufs[i].intersection(bufs[j])
            if inter.is_empty: continue
            length_m = inter.area / (2*buf) * s
            if length_m >= 0.5:
                edges.append((rooms[i][0], rooms[j][0], round(length_m, 2)))
    shapes = {}
    for rid, role, poly in rooms:
        mrr = poly.minimum_rotated_rectangle
        simp = poly.simplify(0.10/s, preserve_topology=True)
        shapes[rid] = {'area_m2': round(poly.area*s*s,2), 'rect_fill': round(poly.area/mrr.area,3) if mrr.area>0 else 0,
                       'n_vertices': len(simp.exterior.coords)-1}
    out.append({'id': p['id'], 'unitType': p.get('unitType'), 'net_area': net, 'wall_depth_m': round(wd_u*s,2),
                'rooms': [(r[0], r[1]) for r in rooms], 'edges': edges, 'shapes': shapes,
                'hall_area_m2': round(sum(h.area for h in halls)*s*s, 2)})
    if k % 3000 == 0: print(k, round(time.time()-t0,1), 's', file=sys.stderr, flush=True)
json.dump(out, open('corpus_graphs3.json','w'))
print('plans written', len(out), 'in', round(time.time()-t0,1), 's')
