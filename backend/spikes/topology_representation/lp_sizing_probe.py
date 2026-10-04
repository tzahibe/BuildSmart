"""#142C attribution probe (experiment-only, NOT a production change): stub `_solve_grid` with the
alternating-LP sizing for each LP-feasible witness and run the UNCHANGED rest of `realize_layout`
(walls, doors, entrance, windows, furniture, `validate`). Answers: if the sizing stage were exact,
how far would the existing downstream machinery take these briefs? The stub lives only in this
process; `app/` is untouched.
Usage (dev venv, PYTHONPATH=backend): python lp_sizing_probe.py <sizing_feasibility.json> <witnesses.json> <out.json>"""
import json, sys
from app.ai_harness.topology_poc import generation_dataset, priors as pm, schema
from app.ai_harness.topology_poc.gap_closure_142a import best_policy_valid_proposal, _zones_for, resolve_wet_rooms
from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency

feas = json.load(open(sys.argv[1])); wit = json.load(open(sys.argv[2]))["briefs"]
ds = generation_dataset.load_dataset(generation_dataset.DEFAULT_GENERATION_DATASET_JSON); pri = pm.load_priors()
recs = {r["brief_id"]: r for r in ds["records"]}

def to_units(vals_m, total_u):
    us = [max(1, int(round(v / 0.05))) for v in vals_m]
    diff = total_u - sum(us); us[us.index(max(us))] += diff
    return us

STUB = {}
def stub_solve_grid(w_u, h_u, rows, n_cols, zones, min_short_u):
    return STUB["row_h"], STUB["col_w"]
rr._solve_grid = stub_solve_grid

out = {}
for bid, f in feas.items():
    rec = recs[bid]; p = best_policy_valid_proposal(rec, pri); zones = _zones_for(p); wet = resolve_wet_rooms(p)
    fw, fd = rec["brief"]["footprint_width_m"], rec["brief"]["footprint_depth_m"]
    buildable = Rect(0, 0, m_to_u(fw) + m_to_u(4.0), m_to_u(fd) + m_to_u(4.0))
    edges = [tuple(e) for e in wit[bid]["edges"]]
    access_edges = [(a, b) for a, b in p.access_graph if a != schema.ENTRANCE_ID]
    tally = {"lp_feasible": 0, "sizing_stub_pass": 0, "realization_pass": 0, "validators_pass": 0, "refusals": {}, "validator_fail_samples": []}
    best = None
    for r in f["records"]:
        if not r["feasible_sizing_found"]:
            continue
        use_a = r["feasible_with_validator_aspect"]
        hs = r["row_heights_aspect_m"] if use_a else r["row_heights_m"]; ws = r["col_widths_aspect_m"] if use_a else r["col_widths_m"]
        tally["lp_feasible"] += 1
        w = wit[bid]["witnesses"][r["index"]]
        rows = tuple(tuple(rr.GridCell(z, int(s)) for z, s in row) for row in w["rows"])
        W = round(sum(ws), 2); H = round(sum(hs), 2)
        STUB["row_h"] = to_units(hs, m_to_u(H)); STUB["col_w"] = to_units(ws, m_to_u(W))
        res = rr.realize_layout(rr.RealizationIntent(name=bid, wings=(rr.GridWing(bid, W, H, int(w["n_cols"]), rows, zones),), wet_rooms=wet), buildable=buildable)
        if isinstance(res, rr.RealizedLayout):
            tally["sizing_stub_pass"] += 1; tally["realization_pass"] += 1; tally["validators_pass"] += 1
            sp = measure_spatial_adjacency(res.rects, p.spatial_adjacency); ac = measure_access_graph(res.fixture.access.edges, access_edges)
            if best is None:
                best = {"witness": r["index"], "envelope_m": [W, H], "spatial": f"{sp.preserved}/{sp.requested}", "access": f"{ac.preserved}/{ac.requested}",
                        "access_lost": sorted(list(e) for e in ac.lost), "rows": w["rows"],
                        "rects_m": {k: [round(x.x*0.05,2), round(x.y*0.05,2), round(x.w*0.05,2), round(x.h*0.05,2), round(x.area_m2(),1)] for k, x in sorted(res.rects.items())}}
        else:
            c = res.constraint
            tally["refusals"][c] = tally["refusals"].get(c, 0) + 1
            if c not in ("AREA_INFEASIBLE", "SHORT_SIDE_INFEASIBLE", "GRID_INFEASIBLE"):
                tally["sizing_stub_pass"] += 1
            if c == "VALIDATION_FAILED":
                tally["realization_pass"] += 1
                if len(tally["validator_fail_samples"]) < 3:
                    tally["validator_fail_samples"].append(res.detail[:300])
    out[bid] = {"tally": tally, "first_success": best}
    print(bid, {k: v for k, v in tally.items() if k != "validator_fail_samples"}, flush=True)
    for s in tally["validator_fail_samples"][:2]: print("    validator:", s[:220])
json.dump(out, open(sys.argv[3], "w"), indent=1)
