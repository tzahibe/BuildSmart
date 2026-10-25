"""#226 Part B.1/B.2 — where a `?engine=brain` request spends its seconds, and what it costs.

Measured on the REAL request path, `svc.generate_demo_design(project, brain=True)`, not on
`run_brain` alone: the preview endpoint runs the whole production pipeline first (it needs
`selection.primary`'s outline) and only then calls the brain, so the request is production's cost
PLUS the brain's 30 s wall-clock budget. Stages are timed by wrapping the module attribute each
caller actually looks up, so nothing in the engine changes.

usage: perf_stages.py <out.json> [brief ...]
"""
import json, os, resource, sys, time

ROOT = "/Users/mymacbook/projects/sddproject-brain"
sys.path.insert(0, f"{ROOT}/backend")
OUT = os.path.abspath(sys.argv[1])
BRIEFS = sys.argv[2:] or ["B02", "B06", "B08", "B09", "B11", "B16", "B19", "B20"]

from tests.vertical_slice.test_brain import _brief
from tests.vertical_slice.test_hub_guard import _project
from app.demo import service as svc
from app.vertical_slice.brain import exact_pipeline as xp
from app.vertical_slice.brain import runner as br
from app.vertical_slice.exact import milp_cells as mc
from app.vertical_slice.exact import milp_oracle as mo

BUCKETS = {}


def wrap(module, name, bucket, *, count_status=False):
    original = getattr(module, name)

    def timed(*a, **k):
        t = time.monotonic()
        try:
            return_value = original(*a, **k)
        finally:
            d = time.monotonic() - t
            b = BUCKETS.setdefault(bucket, {"s": 0.0, "n": 0, "status": {}})
            b["s"] += d; b["n"] += 1
        if count_status:
            st = str(getattr(return_value, "status", "?"))
            b["status"][st] = b["status"].get(st, 0) + 1
        return return_value

    setattr(module, name, timed)


wrap(xp, "embed_band", "embedding")
wrap(xp, "placement_flags", "screens")
wrap(xp, "hard_rejections", "screens")
wrap(xp, "realize_cells", "realization")
# the three oracles are imported INSIDE `run_exact_pipeline`, so the source module is what to wrap
wrap(mo, "milp_placement", "milp", count_status=True)
wrap(mo, "milp_spine_placement", "milp", count_status=True)
wrap(mc, "cells_placement", "milp", count_status=True)
wrap(br, "run_band_pipeline", "production_sizer")
wrap(svc, "to_demo_design", "payload")
if hasattr(xp, "embed_spine"):
    wrap(xp, "embed_spine", "embedding")


def project_for(bid):
    b = _brief(bid)
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def usage():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return dict(maxrss_mb=round(r.ru_maxrss / (1024 * 1024), 1),
                cpu_s=round(r.ru_utime + r.ru_stime, 2))


rows = []
for bid in BRIEFS:
    project = project_for(bid)
    for engine in ("production", "brain"):
        BUCKETS.clear()
        u0 = usage(); t = time.monotonic()
        error = None
        try:
            res = svc.generate_demo_design(project, brain=(engine == "brain"))
            plans = 1 + len(res.alternatives)
        except Exception as exc:                                   # the refusal is a result too
            error = f"{type(exc).__name__}: {str(exc)[:120]}"; plans = 0
        el = time.monotonic() - t; u1 = usage()
        stages = {k: dict(s=round(v["s"], 2), n=v["n"], **({"status": v["status"]} if v["status"] else {}))
                  for k, v in sorted(BUCKETS.items())}
        acc = sum(v["s"] for v in BUCKETS.values())
        rows.append(dict(brief=bid, engine=engine, total_s=round(el, 2), plans=plans, error=error,
                         stages=stages, accounted_s=round(acc, 2),
                         cpu_s=round(u1["cpu_s"] - u0["cpu_s"], 2), maxrss_mb_after=u1["maxrss_mb"]))
        print(f"{bid} {engine:10s} total {el:6.2f} s  cpu {u1['cpu_s'] - u0['cpu_s']:6.2f} s  "
              f"maxrss {u1['maxrss_mb']:6.1f} MB  plans {plans}  "
              + "  ".join(f"{k}={v['s']:.2f}/{v['n']}" for k, v in stages.items())
              + (f"  ERROR {error}" if error else ""), flush=True)

json.dump(dict(rows=rows, final=usage()), open(OUT, "w"), indent=1)
print("DONE", usage())
