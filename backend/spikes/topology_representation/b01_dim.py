import json, sys, os
from app.ai_harness.topology_poc import gap_closure_142a as g, generation_dataset, priors as pm
from app.vertical_slice.rectilinear_realizer import GridWing, GridCell, RealizationIntent, RealizedLayout, realize_layout
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.topology_preservation import measure_spatial_adjacency, measure_access_graph
S = sys.argv[1]
ds = generation_dataset.load_dataset(S + '/omain/docs/reports/llm-topology-poc/generation-dataset.json'); pri = pm.load_priors()
rec = {r['brief_id']: r for r in ds['records']}['B01']; p = g.best_policy_valid_proposal(rec, pri)
zones = g._zones_for(p); wet = g.resolve_wet_rooms(p)
print({z: (zi.role.value, zi.min_area_m2, zi.target_area_m2, zi.max_area_m2, zi.min_short_side_m) for z, zi in zones.items()})
fw, fd = rec['brief']['footprint_width_m'], rec['brief']['footprint_depth_m']
buildable = Rect(0, 0, m_to_u(fw) + m_to_u(4.0), m_to_u(fd) + m_to_u(4.0))
layouts = json.load(open(S + '/b01_band_layouts.json'))
grid_m = [round(5.0 + 0.3*i, 2) for i in range(31)]
n_ok = 0; reasons = {}; realized_dump = []
for li, rects in enumerate(layouts):
    W = max(r[1] for r in rects.values()); bands = sorted(set((r[2], r[3]) for r in rects.values()))
    rows = tuple(tuple(GridCell(pid, r[1]-r[0]) for _x, pid, r in sorted((r[0], pid, r) for pid, r in rects.items() if (r[2], r[3]) == b)) for b in bands)
    hit = None; last=None
    for wm in grid_m:
        for hm in grid_m:
            res = realize_layout(RealizationIntent(name='B01', wings=(GridWing('B01', wm, hm, W, rows, zones),), wet_rooms=wet), buildable=buildable)
            if isinstance(res, RealizedLayout): hit=(wm,hm,res); break
            last=res
        if hit: break
    if hit:
        n_ok += 1; wm,hm,res = hit
        sp = measure_spatial_adjacency(res.rects, p.spatial_adjacency)
        acc = measure_access_graph(res.fixture.access.edges, [(a,b) for a,b in p.access_graph if a != 'ENTRANCE'])
        print(f'layout {li} rows={[[(c.zone_id,c.col_span) for c in row] for row in rows]} REALIZED at {wm}x{hm} m; validator ok={res.report.ok}; spatial {sp.preserved}/{sp.requested}; access {acc.preserved}/{acc.requested}; failed checks={[c.check_id for c in res.report.checks if not c.passed] if hasattr(res.report, "checks") else "?"}')
        for k, r in sorted(res.rects.items()): print('     ', k, 'w=%.1f d=%.1f area=%.1f' % (r.w*0.05, r.h*0.05, r.area_m2()))
        realized_dump.append({'layout_index': li, 'rows': [[(c.zone_id, c.col_span) for c in row] for row in rows], 'envelope_m': (wm, hm), 'rects_u': {k: (r.x, r.y, r.w, r.h) for k, r in res.rects.items()}, 'spatial': f'{sp.preserved}/{sp.requested}', 'access': f'{acc.preserved}/{acc.requested}', 'validator_ok': res.report.ok, 'access_edges': sorted(str(e) for e in res.fixture.access.edges)})
    else:
        reasons[last.constraint] = reasons.get(last.constraint, 0) + 1
print('dimensioned', n_ok, 'of', len(layouts), 'band layouts; last-refusal constraints of the rest:', reasons)
json.dump({'n_layouts': len(layouts), 'n_realized': n_ok, 'refusals_of_rest': reasons, 'realized': realized_dump}, open(S + '/b01_realized.json', 'w'), indent=1, default=str)
