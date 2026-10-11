"""Within each production slot structure: exact maximum edges carried vs the heuristic's score."""
import json
from pysat.card import CardEnc, EncType
from pysat.solvers import Cadical153
from topo_lib import row_lengths_for, slot_positions, slot_adjacency
import itertools
G = json.load(open('selected_graphs.json')); H = json.load(open('heuristic_dump.json'))
def exact_max(nodes, edges, sadj, n_slots):
    idx = {v:i for i,v in enumerate(nodes)}; n=len(nodes)
    var = lambda v,s: 1+idx[v]*n_slots+s
    top = n*n_slots; cl=[]
    for v in nodes:
        cl.append([var(v,t) for t in range(n_slots)])
        for t1,t2 in itertools.combinations(range(n_slots),2): cl.append([-var(v,t1),-var(v,t2)])
    for t in range(n_slots):
        for v1,v2 in itertools.combinations(nodes,2): cl.append([-var(v1,t),-var(v2,t)])
    sel=[]
    for a,b in edges:
        top+=1; s=top; sel.append(s)
        for t1 in range(n_slots):
            for t2 in range(n_slots):
                if t1==t2 or frozenset((t1,t2)) in sadj: continue
                cl.append([-s,-var(a,t1),-var(b,t2)])
    for k in range(len(edges),0,-1):
        card = CardEnc.atleast(lits=sel, bound=k, top_id=top, encoding=EncType.seqcounter)
        S = Cadical153(bootstrap_with=cl+card.clauses); ok=S.solve(); S.delete()
        if ok: return k
    return 0
out={}
for bid in ('B10','B13','B15','B16'):
    g=G[bid]; nodes=[r['id'] for r in g['rooms']]; edges=[tuple(e) for e in g['spatial_adjacency']]
    out[bid]={}
    for sh in H[bid]['per_shape']:
        n_rows=sh['n_rows']; rl=row_lengths_for(len(nodes),n_rows); nc=max(rl); slots=slot_positions(rl,nc); sadj=slot_adjacency(slots)
        ex = exact_max(nodes, edges, sadj, len(slots))
        out[bid][n_rows]={'heuristic':sh['score'],'exact_max':ex,'m':len(edges)}
        print(bid, f'rows={n_rows} ({rl}): heuristic {sh["score"]} vs exact max {ex} of {len(edges)}', flush=True)
json.dump(out, open('slot_exact.json','w'), indent=1)
