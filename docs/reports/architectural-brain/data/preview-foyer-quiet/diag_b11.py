"""#226 Part A — why B11's exact plan appears on the control and not on the branch.

Prints every parti's full notes (the metrics table truncates them at 160 characters) plus the
remaining budget each parti was handed, for one tree, so the control and the branch can be read
side by side. usage: diag_b11.py <tree> <brief> [families]"""
import sys, time

ROOT = sys.argv[1]; sys.path.insert(0, f"{ROOT}/backend")
BRIEF = sys.argv[2] if len(sys.argv) > 2 else "B11"
FAMS = tuple((sys.argv[3] if len(sys.argv) > 3 else "band").split(","))

from tests.vertical_slice.test_brain import _spec_and_footprint
from app.vertical_slice.brain import exact_pipeline as xp
from app.vertical_slice.brain.runner import run_brain

calls = []
_orig = xp.run_exact_pipeline


def traced(inp, **k):
    t = time.monotonic(); r = _orig(inp, **k)
    calls.append((inp.name, round(k["deadline"] - t, 3), round(time.monotonic() - t, 3)))
    return r


xp.run_exact_pipeline = traced
print("TREE", ROOT, "brief", BRIEF, "families", FAMS,
      "solve_time_limit(2.0) =", round(xp.solve_time_limit(2.0), 3) if hasattr(xp, "solve_time_limit") else "n/a")
spec, fp = _spec_and_footprint(BRIEF)
t = time.monotonic(); res = run_brain(spec, fp, brief=BRIEF, sizer="exact", families=FAMS)
print(f"total {time.monotonic() - t:.2f} s, {len(res.distinct)} distinct of {len(res.plans)} partis")
print("exact-pipeline calls (parti, share handed, seconds used):")
for c in calls:
    print("   ", c)
for p in res.plans:
    mark = "SHOWN" if res.distinct and p is res.distinct[0] else ("counts" if p.counts else "      ")
    print(f"-- {mark:6s} {p.parti:22s} sizer={p.sizer} family={p.family} stage={p.stage} key={p.rank_key}")
    for n in p.notes:
        print(f"      {n}")
