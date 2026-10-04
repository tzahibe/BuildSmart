"""Corpus-wide structure of real spatial-touching graphs incl. reconstructed HALL nodes."""
import json, random, statistics, collections, sys, time
from topo_lib import diagnostics, solve_family
C = json.load(open('corpus_graphs3.json'))
random.seed(142)
INDOOR = {'living','kitchen','bedroom','bathroom','storage'}
def graph_of(plan, thresh):
    nodes = [rid for rid, role in plan['rooms'] if role in INDOOR]
    ns = set(nodes)
    return nodes, [(a,b) for a,b,l in plan['edges'] if a in ns and b in ns and l >= thresh]
def q(xs):
    xs=sorted(xs); return [xs[int(len(xs)*f)] for f in (0.1,0.25,0.5,0.75,0.9)]
rows_by = {}
for thresh in (1.0, 1.5):
    rows = []
    for p in C:
        nodes, edges = graph_of(p, thresh)
        if len(nodes) < 3: continue
        d = diagnostics(nodes, edges); roles = dict(p['rooms'])
        hub = max(d['degree'], key=d['degree'].get)
        halls = [r for r in nodes if roles[r]=='hall']
        rows.append({'id': p['id'], 'n': d['n'], 'm': d['m'], 'density': d['density'], 'max_degree': d['max_degree'],
                     'hub_role': roles[hub], 'hub_degree': d['degree'][hub], 'planar': d['planar'], 'k4': len(d['k4']), 'lens3': len(d['lens3']),
                     'k4_roles': [tuple(sorted(roles[v] for v in c)) for c in d['k4']],
                     'lens3_roles': [tuple(sorted((roles[a], roles[b]))) for (a,b),c in d['lens3']],
                     'cycle_rank': d['cycle_rank'], 'connected': d['connected'], 'degree_hist': d['degree_hist'], 'n_hall': len(halls),
                     'hall_degree': max([d['degree'][r] for r in halls], default=0),
                     'obstruction_rooms': sorted({v for c in d['k4'] for v in c} | {v for (a,b),c in d['lens3'] for v in (a,b,*c)}),
                     'nonrect_rooms': [roles[r] for r in nodes if p['shapes'][r]['rect_fill'] < 0.85]})
    rows_by[str(thresh)] = rows
    print(f'### geometric touching, shared boundary >= {thresh} m (v3: deduped nodes, no hall): plans {len(rows)}')
    print(' n rooms q10/25/50/75/90:', q([r['n'] for r in rows]), ' mean', round(statistics.mean(r['n'] for r in rows),2), ' plans with a hall node:', round(sum(r['n_hall']>0 for r in rows)/len(rows),3))
    print(' m edges q:', q([r['m'] for r in rows]), ' mean', round(statistics.mean(r['m'] for r in rows),2))
    print(' density q:', q([r['density'] for r in rows]))
    print(' max degree q:', q([r['max_degree'] for r in rows]), ' hub role:', collections.Counter(r['hub_role'] for r in rows).most_common(4))
    print(' planar:', round(sum(r['planar'] for r in rows)/len(rows),4), ' connected:', round(sum(r['connected'] for r in rows)/len(rows),4))
    print(' has K4:', round(sum(r['k4']>0 for r in rows)/len(rows),4), ' has lens3:', round(sum(r['lens3']>0 for r in rows)/len(rows),4),
          ' K4 or lens3 (provably NOT rectangular-realizable):', round(sum((r['k4']>0 or r['lens3']>0) for r in rows)/len(rows),4))
    print(' K4 role patterns:', collections.Counter(t for r in rows for t in r['k4_roles']).most_common(6))
    print(' lens3 edge roles:', collections.Counter(t for r in rows for t in r['lens3_roles']).most_common(6))
    print(' cycle rank q:', q([r['cycle_rank'] for r in rows]), ' tree-like:', round(sum(r['cycle_rank']==0 for r in rows)/len(rows),4))
    print(' m > 3n-7:', round(sum(r['m']>3*r['n']-7 for r in rows)/len(rows),4))
    deg_all = collections.Counter()
    for r in rows:
        for d,c in r['degree_hist'].items(): deg_all[int(d)] += c
    tot = sum(deg_all.values()); print(' degree distribution (share of rooms):', [(d, round(c/tot,3)) for d,c in sorted(deg_all.items()) if c/tot >= 0.002])
    obs = [r for r in rows if r['k4'] or r['lens3']]
    byid = {p['id']: p for p in C}
    def nonrect(pid, rid): return byid[pid]['shapes'][rid]['rect_fill'] < 0.85
    share_obs = sum(1 for r in obs if any(nonrect(r['id'], v) for v in r['obstruction_rooms'])) / max(1, len(obs))
    share_all = sum(1 for r in rows if any(nonrect(r['id'], v) for v in [rid for rid, role in byid[r['id']]['rooms'] if role in INDOOR])) / len(rows)
    print(f' obstructed plans: {len(obs)}; share with a NON-RECTANGULAR real room (fill<0.85) among the obstruction rooms: {share_obs:.3f}  (any indoor room non-rect, all plans: {share_all:.3f})')
    print(' obstruction-room roles:', collections.Counter(dict(byid[r['id']]['rooms'])[v] for r in obs for v in r['obstruction_rooms']).most_common(5))
    print(' living-room shape: share of plans whose living is non-rect (fill<0.85):', round(sum(1 for r in rows if any(nonrect(r['id'], rid) for rid, role in byid[r['id']]['rooms'] if role=='living'))/len(rows),3))
json.dump(rows_by, open('corpus_rows4.json','w'))
N_SAMPLE = int(sys.argv[1]) if len(sys.argv)>1 else 800
BUD = 150000
by_id = {p['id']: p for p in C}
rows = rows_by['1.0']
sample = random.sample(rows, N_SAMPLE)
lev = collections.Counter(); per = []; t0=time.time()
for i, r in enumerate(sample):
    p = by_id[r['id']]; nodes, edges = graph_of(p, 1.0); lv=None
    if not r['planar']: lv = 'non-planar (spurious edges)'
    elif r['k4'] or r['lens3']:
        for fam, name in (('band_y','band + 1 L-room'), ('slicing','slicing + 1 L-room'), ('rect','rect + 1 L-room')):
            for room in r['obstruction_rooms']:
                ok,_,_ = solve_family(nodes, edges, fam, l_rooms=(room,), conf_budget=BUD)
                if ok: lv = name; break
            if lv: break
        lv = lv or 'needs >1 L-room / other'
    else:
        ok,_,_ = solve_family(nodes, edges, 'band_y', conf_budget=BUD)
        if ok: lv = 'band (GridWing full)'
        else:
            ok2,_,_ = solve_family(nodes, edges, 'slicing', conf_budget=BUD)
            if ok2: lv = 'slicing (Geometry Core tree)'
            else:
                ok3,_,_ = solve_family(nodes, edges, 'rect', conf_budget=BUD)
                if ok3: lv = 'rectangular non-guillotine'
                elif ok3 is False: lv = 'needs L (SAT, no K4/lens3)'
                else: lv = 'UNKNOWN (budget)'
    lev[lv] += 1; per.append({'id': r['id'], 'n': r['n'], 'm': r['m'], 'level': lv, 'hub_degree': r['hub_degree']})
    if i % 100 == 0: print(i, dict(lev), round(time.time()-t0,1), 's', flush=True)
print(f'### SAMPLE N={N_SAMPLE} (>=1.0 m, v3) levels:', dict(lev), flush=True)
json.dump(per, open('corpus_levels_v3.json','w'))
