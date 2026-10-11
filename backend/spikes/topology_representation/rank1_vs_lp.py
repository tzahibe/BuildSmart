"""#142C attribution, decisive check: for every witness the alternating LP found a feasible sizing for,
hand the UNCHANGED GridWing path that sizing's OWN envelope (sum of column widths x sum of row heights).
If `_solve_grid` still refuses, the blocker is its rank-1 proportionality, not the envelope ladder.
Usage (dev venv, PYTHONPATH=backend): python rank1_vs_lp.py <sizing_feasibility.json> <witnesses.json> <out.json>"""
import json, sys
from app.ai_harness.topology_poc import generation_dataset, priors as pm
from app.ai_harness.topology_poc.gap_closure_142a import best_policy_valid_proposal, _zones_for, resolve_wet_rooms
from app.vertical_slice.rectilinear_realizer import GridWing, GridCell, RealizationIntent, RealizedLayout, realize_layout
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.topology_preservation import measure_spatial_adjacency

feas = json.load(open(sys.argv[1])); wit = json.load(open(sys.argv[2]))["briefs"]
ds = generation_dataset.load_dataset(generation_dataset.DEFAULT_GENERATION_DATASET_JSON); pri = pm.load_priors()
recs = {r["brief_id"]: r for r in ds["records"]}
out = {}
for bid, f in feas.items():
    rec = recs[bid]; p = best_policy_valid_proposal(rec, pri); zones = _zones_for(p); wet = resolve_wet_rooms(p)
    fw, fd = rec["brief"]["footprint_width_m"], rec["brief"]["footprint_depth_m"]
    buildable = Rect(0, 0, m_to_u(fw) + m_to_u(4.0), m_to_u(fd) + m_to_u(4.0))
    tally = {"lp_feasible": 0, "rank1_sized_with_lp_envelope": 0, "realized_validated": 0, "refusals": {}}
    examples = []
    for r in f["records"]:
        key = "row_heights_aspect_m" if r["feasible_with_validator_aspect"] else "row_heights_m"
        keyw = "col_widths_aspect_m" if r["feasible_with_validator_aspect"] else "col_widths_m"
        if not r["feasible_sizing_found"]:
            continue
        tally["lp_feasible"] += 1
        w = wit[bid]["witnesses"][r["index"]]
        rows = tuple(tuple(GridCell(z, int(s)) for z, s in row) for row in w["rows"])
        W = round(sum(r[keyw]), 1); H = round(sum(r[key]), 1)
        res = realize_layout(RealizationIntent(name=bid, wings=(GridWing(bid, W, H, int(w["n_cols"]), rows, zones),), wet_rooms=wet), buildable=buildable)
        if isinstance(res, RealizedLayout):
            tally["rank1_sized_with_lp_envelope"] += 1; tally["realized_validated"] += 1
        else:
            if res.constraint not in ("AREA_INFEASIBLE", "SHORT_SIDE_INFEASIBLE", "GRID_INFEASIBLE"):
                tally["rank1_sized_with_lp_envelope"] += 1
            tally["refusals"][res.constraint] = tally["refusals"].get(res.constraint, 0) + 1
            if len(examples) < 2:
                examples.append({"witness": r["index"], "lp_envelope_m": [W, H], "lp_row_heights": r[key], "lp_col_widths": r[keyw],
                                 "rows": w["rows"], "rank1_refusal": f"{res.constraint}: {res.detail[:160]}"})
    out[bid] = {"tally": tally, "examples": examples}
    print(bid, tally, flush=True)
json.dump(out, open(sys.argv[3], "w"), indent=1)
