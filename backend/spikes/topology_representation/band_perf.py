"""#142E Part G — performance of the production band path on the 20 frozen briefs.

Measures, per brief: embedding runtime and candidate counts, sizing runtime per candidate,
realization runtime, total pipeline runtime, peak memory (tracemalloc), and deterministic
repeatability (two runs must produce identical placements / geometry).
Usage (dev venv, PYTHONPATH=backend): python band_perf.py <out.json>
"""
import json
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tests", "vertical_slice"))
from frozen_briefs import load_fixture, pipeline_input  # noqa: E402

from app.vertical_slice.band_embedding import BandEmbedding, embed_band  # noqa: E402
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline  # noqa: E402
from app.vertical_slice.band_sizing import solve_band_sizing  # noqa: E402


def main(out_path):
    fx = load_fixture()
    rows = []
    for bid in sorted(fx["briefs"]):
        inp = pipeline_input(bid, fx["briefs"][bid])
        fw, fd = inp.footprint_m
        t = time.perf_counter(); emb = embed_band(inp.zones, inp.required_edges); t_emb = time.perf_counter() - t
        rec = {"brief": bid, "n": len(inp.zones), "m": len(inp.required_edges), "embed_s": round(t_emb, 4)}
        if isinstance(emb, BandEmbedding):
            rec.update({"candidates": len(emb.candidates), "layouts_found": emb.layouts_found,
                        "search_complete": emb.search_complete, "nodes": emb.nodes_explored})
            ts = []; feas = 0
            for c in emb.candidates:
                t = time.perf_counter()
                r = solve_band_sizing(c.rows, c.n_cols, inp.zones, w_max_m=fw + 4, h_max_m=fd + 4)
                ts.append(time.perf_counter() - t); feas += r.status == "FEASIBLE"
            rec.update({"sizing_ms_mean": round(sum(ts) / len(ts) * 1000, 3), "sizing_ms_max": round(max(ts) * 1000, 3),
                        "sizable": feas})
        else:
            rec.update({"refusal": emb.code})
        # wall-clock of an UNINSTRUMENTED run (tracemalloc slows Python several-fold), then a separate
        # instrumented run for peak memory, then a third run for determinism
        t = time.perf_counter(); r1 = run_band_pipeline(inp); t_pipe = time.perf_counter() - t
        tracemalloc.start()
        run_band_pipeline(inp)
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        r2 = run_band_pipeline(inp)
        same = (type(r1) is type(r2)) and (
            (r1.placement.rows == r2.placement.rows and
             {k: (x.x, x.y, x.w, x.h) for k, x in r1.realized.rects.items()} == {k: (x.x, x.y, x.w, x.h) for k, x in r2.realized.rects.items()})
            if isinstance(r1, PipelineSuccess) else (r1.code == r2.code and r1.candidates_tried == r2.candidates_tried))
        rec.update({"pipeline_s": round(t_pipe, 3), "peak_mb": round(peak / 1e6, 2), "deterministic": same,
                    "outcome": "PASS" if isinstance(r1, PipelineSuccess) else r1.code,
                    "realizations": sum(1 for x in r1.records if x.stage_reached in ("SIZING", "REALIZATION", "VALIDATORS") and x.refusal != "NOT_REALIZED_BUDGET")})
        rows.append(rec)
        print(rec, flush=True)
    summary = {"worst_pipeline_s": max(r["pipeline_s"] for r in rows), "worst_embed_s": max(r["embed_s"] for r in rows),
               "worst_sizing_ms": max(r.get("sizing_ms_max", 0) for r in rows), "worst_peak_mb": max(r["peak_mb"] for r in rows),
               "all_deterministic": all(r["deterministic"] for r in rows), "total_s": round(sum(r["pipeline_s"] for r in rows), 2)}
    print(summary)
    json.dump({"rows": rows, "summary": summary}, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
