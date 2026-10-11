import json, sys
from dataclasses import asdict
from app.ai_harness.topology_poc import exact_sizing_142d as X
sem_name = sys.argv[1]; out = sys.argv[2]; paths = sys.argv[3].split(',')
briefs = tuple(sys.argv[4].split(',')) if len(sys.argv) > 4 and sys.argv[4] != '-' else None
sem = X.Semantics(label=sem_name) if sem_name == 'production' else None
if sem_name in ('corrected', 'corrected_netgate'):
    sem = X.Semantics(area='net', aspect=True, label=sem_name)
    sem.net_gate = (sem_name == 'corrected_netgate')
order = sys.argv[6] if len(sys.argv) > 6 else None
if order: sem.label = sem.label + '+' + order
res = X.run_all(paths, sem, brief_ids=briefs, orders=order)
json.dump([asdict(r) for r in res], open(out, 'w'), indent=1)
print('wrote', out)
