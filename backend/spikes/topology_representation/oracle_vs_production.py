"""#142E Part F — the #142D research oracle vs the production solvers, on the frozen witness sets.

For every committed #142D witness (band layouts carrying every required edge) compare:
  (1) sizing: `cell_sizing_oracle.decide` under CORRECTED (net + aspect) semantics — the semantics
      production now implements — vs `band_sizing.solve_band_sizing`;
  (2) embedding: the production `embed_band` candidates for the same brief (count, all verified).
Disagreements are listed per brief; a production INFEASIBLE where the oracle says FEASIBLE is a
false negative and must be explained.

Usage (dev venv, PYTHONPATH=backend): python oracle_vs_production.py <witnesses_main.json> [<witnesses_B07.json> ...]
Needs scipy for the oracle (transitive dev dependency), never for production code.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cell_sizing_oracle import Semantics, decide  # noqa: E402

from app.vertical_slice.band_embedding import BandEmbedding, embed_band, verify_rows  # noqa: E402
from app.vertical_slice.band_sizing import cell_insets_u, solve_band_layout, solve_band_sizing  # noqa: E402
from app.vertical_slice.geometry_core.model import UNIT_M, ProgramRole  # noqa: E402
from app.vertical_slice.rectilinear_realizer import ZoneIntent  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "tests", "fixtures", "frozen_briefs_142.json")


def main(paths):
    fx = json.load(open(FIXTURE))["briefs"]
    wit = {}
    for p in paths:
        for bid, rec in json.load(open(p))["briefs"].items():
            if rec.get("witnesses") and (bid not in wit or len(rec["witnesses"]) > len(wit[bid]["witnesses"])):
                wit[bid] = rec
    report = {}
    for bid in sorted(wit):
        b = fx[bid]
        zones = {z: ZoneIntent(z, ProgramRole(v["role"]), v["target"], v["min"], v["max"], v["min_short"], v["max_aspect"])
                 for z, v in b["zones"].items()}
        zb = {z: {"min": v["min"], "max": v["max"], "target": v["target"], "min_short": v["min_short"], "max_aspect": v["max_aspect"]}
              for z, v in b["zones"].items()}
        fw, fd = b["footprint_m"]
        agree = {"both_feasible": 0, "both_infeasible": 0, "oracle_F_prod_I": [], "oracle_I_prod_F": [], "prod_unknown": [], "oracle_unknown": 0, "fixed_columns_agree": 0, "fixed_columns_disagree": []}
        t_prod = 0.0; t_orc = 0.0
        for i, wt in enumerate(wit[bid]["witnesses"]):
            rows = [[(z, int(s)) for z, s in row] for row in wt["rows"]]
            C = wt["n_cols"]; R = len(rows)
            # oracle in CORRECTED semantics with the same per-cell insets production uses
            bw = {}; bh = {}
            for r, row in enumerate(rows):
                c0 = 0
                for z, span in row:
                    iw, ih = cell_insets_u(r, c0, c0 + span, R, C)
                    bw[z] = iw * UNIT_M; bh[z] = ih * UNIT_M; c0 += span
            sem = Semantics(area="net", aspect=True, net_inset_w=bw, net_inset_h=bh, label="corrected")
            t = time.perf_counter(); o = decide(rows, C, zb, fw + 4.0, fd + 4.0, sem); t_orc += time.perf_counter() - t
            bands = tuple(tuple(z for z, _ in row) for row in rows)
            edges_b = [tuple(e) for e in b["spatial_adjacency"]]
            t = time.perf_counter(); p = solve_band_layout(bands, zones, edges_b, w_max_m=fw + 4.0, h_max_m=fd + 4.0); t_prod += time.perf_counter() - t
            # the fixed-column solver (same columns as the oracle) for a like-for-like check
            pf = solve_band_sizing(rows, C, zones, w_max_m=fw + 4.0, h_max_m=fd + 4.0)
            os_, ps = o["status"], p.status
            if pf.status == o["status"]:
                agree["fixed_columns_agree"] += 1
            elif "UNKNOWN" not in (pf.status, o["status"]):
                agree["fixed_columns_disagree"].append(i)
            if os_ == "UNKNOWN":
                agree["oracle_unknown"] += 1
            elif ps == "UNKNOWN":
                agree["prod_unknown"].append(i)
            elif os_ == ps == "FEASIBLE":
                agree["both_feasible"] += 1
            elif os_ == ps == "INFEASIBLE":
                agree["both_infeasible"] += 1
            elif os_ == "FEASIBLE":
                agree["oracle_F_prod_I"].append(i)
            else:
                agree["oracle_I_prod_F"].append(i)
        n = len(wit[bid]["witnesses"])
        edges = [tuple(e) for e in b["spatial_adjacency"]]
        t = time.perf_counter(); emb = embed_band(zones, edges); t_emb = time.perf_counter() - t
        emb_info = {"candidates": len(emb.candidates), "layouts_found": emb.layouts_found, "complete": emb.search_complete,
                    "unverified": sum(1 for c in emb.candidates if verify_rows(c.rows, c.n_cols, edges)),
                    "sizable_candidates": sum(1 for c in emb.candidates if solve_band_layout(c.bands, zones, edges, w_max_m=fw + 4.0, h_max_m=fd + 4.0).status == "FEASIBLE"),
                    "seconds": round(t_emb, 3)} if isinstance(emb, BandEmbedding) else {"refusal": emb.code}
        report[bid] = {"witnesses": n, **{k: (v if not isinstance(v, list) else len(v)) for k, v in agree.items()},
                       "false_negative_indices": agree["oracle_F_prod_I"][:10], "false_positive_indices": agree["oracle_I_prod_F"][:10],
                       "ms_per_witness_oracle": round(t_orc / n * 1000, 2), "ms_per_witness_production": round(t_prod / n * 1000, 3),
                       "production_embedding": emb_info}
        print(bid, {k: v for k, v in report[bid].items() if k not in ("false_negative_indices", "false_positive_indices")}, flush=True)
    return report


if __name__ == "__main__":
    rep = main(sys.argv[1:])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_vs_production.json")
    json.dump(rep, open(out, "w"), indent=1)
    print("wrote", out)
