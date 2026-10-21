"""Every exact solve of one brief/config: family, orientation, rung, status, seconds."""
import sys, time; sys.path.insert(0, '/Users/mymacbook/projects/sddproject-brain/backend')
from tests.vertical_slice.test_brain import _spec_and_footprint
from app.vertical_slice.brain import exact_pipeline as ep
from app.vertical_slice.brain.runner import run_brain
from app.vertical_slice.exact import milp_oracle as mo
BID, FAM = sys.argv[1], tuple(sys.argv[2].split(","))
log = []
_mp = mo.milp_placement
def traced(bands, *a, street="N", time_limit_s=10.0, **k):
    t = time.monotonic(); o = _mp(bands, *a, street=street, time_limit_s=time_limit_s, **k)
    log.append((street, o.status, round(time.monotonic() - t, 2), round(time_limit_s, 1), len(bands))); return o
mo.milp_placement = traced
spec, fp = _spec_and_footprint(BID)
t = time.monotonic(); res = run_brain(spec, fp, brief=BID, sizer="exact", families=FAM); el = time.monotonic() - t
print(BID, FAM, f"{el:.1f}s", "first:", res.distinct[0].parti, res.distinct[0].sizer, res.distinct[0].rank_key)
for p in res.plans:
    if p.notes: print("  ", p.parti, p.sizer, [n[:140] for n in p.notes])
print("band solves:", len(log))
for x in log: print("  ", x)
